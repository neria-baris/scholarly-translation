"""Translated EPUB export (Session X).

There is currently no canonical ``document_structure`` producer for EPUB
input: ``segmentation.build_readings``/``document_structure.py`` hard-
require a schema-3 *PDF* ``Document`` (``source_reading.build_readings``
asserts ``document.source_kind == "pdf"``). Building a PDF-style, heuristic
line classifier for EPUB content would itself be exactly the "second
independent interpretation of chapters/headings" the contract forbids --
and would be the wrong tool besides, since EPUB already encodes its block
structure unambiguously in its own XHTML markup (h1..h6/p/li/blockquote).

So this module treats the EPUB's own existing HTML block structure as the
(only) source of truth for EPUB "nodes": :func:`extract_epub_structure`
discovers it directly from the archive's spine chapters -- reusing the
same defensive zipfile/XML parsing posture as
``document_draft.py``'s existing EPUB spine reader (reject DOCTYPE/ENTITY,
reject encrypted content, reject out-of-archive/out-of-bounds references,
require real XHTML chapter media types) -- and produces a small,
EPUB-specific structure (schema ``epub-structure@1``, *not* claiming to be
``document_structure`` schema 2) with the same conceptual shape (nodes,
units, unit_node_links, unit_id/node_id traceability) so
:func:`export_epub` can substitute translated text into the existing
elements exactly, then :func:`export_epub` rebuilds the archive, copying
every other file (package metadata, CSS, images, nav/TOC, fonts) through
byte-for-byte unchanged.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from .epub_archive import (
    BLOCK_TAGS as _BLOCK_TAGS,
    EpubArchiveError,
    HEADING_TAGS as _HEADING_TAGS,
    INLINE_LINK_TAG as _INLINE_LINK_TAG,
    MEDIA_TAGS as _MEDIA_TAGS,
    XHTML_MEDIA_TYPES as _XHTML_MEDIA_TYPES,
    archive_path as _archive_path,
    block_text as _block_text,
    encrypted_paths as _encrypted_paths,
    local_tag as _local,
    open_validated_archive as _open_validated_archive,
    parse_xml as _xml,
    resolve_package as _resolve_package,
    resolve_spine as _resolve_spine,
)
from .export_common import ExportError, validate_translations_mapping
from .store import deterministic_id

SCHEMA = "epub-structure@1"


def extract_epub_structure(path_or_bytes) -> dict:
    """Discover translatable blocks directly from an EPUB's own spine
    XHTML structure. Returns a dict shaped like (but not claiming to be)
    the canonical ``document_structure``: ``nodes`` (one per translatable
    block element, kind in ``heading``/``paragraph``/``list``/``quotation``,
    in document order across the whole spine), ``units`` (one per node --
    EPUB HTML blocks are already natural translation-unit boundaries, so
    no further word-count grouping is applied), and ``unit_node_links``.
    Also returns ``spine`` (ordered chapter paths) and ``package_path`` for
    :func:`export_epub` to reuse without re-parsing the archive.

    Raises :class:`ExportError` (never a raw internal traceback) for an
    invalid, encrypted, oversized or otherwise unreadable EPUB archive.
    """
    try:
        archive = _open_validated_archive(path_or_bytes)
        with archive:
            package_path, package, base = _resolve_package(archive)
            spine_paths = _resolve_spine(archive, package, base)

            nodes, units, links = [], [], []
            order = 0
            for chapter_index, chapter_path in enumerate(spine_paths):
                root = _xml(archive.read(chapter_path))
                body = next((e for e in root.iter() if _local(e.tag) == "body"), root)
                element_index = 0
                for el in body.iter():
                    tag = _local(el.tag)
                    if tag not in _BLOCK_TAGS:
                        continue
                    text = _block_text(el)
                    if not text:
                        element_index += 1
                        continue
                    kind = "heading" if tag in _HEADING_TAGS else (
                        "quotation" if tag == "blockquote" else ("list" if tag == "li" else "paragraph"))
                    level = _HEADING_TAGS.get(tag)
                    has_media = any(_local(child.tag) in _MEDIA_TAGS for child in el.iter())
                    order += 1
                    node_id = deterministic_id("epub-node", chapter_path, str(element_index), tag)
                    unit_id = deterministic_id("epub-unit", chapter_path, str(element_index), tag)
                    nodes.append({
                        "node_id": node_id, "kind": kind, "level": level, "order": order,
                        "chapter_path": chapter_path, "chapter_index": chapter_index,
                        "element_index": element_index, "tag": tag, "text": text,
                        "has_media": has_media,
                    })
                    units.append({"unit_id": unit_id, "text": text, "order": order})
                    links.append({"unit_id": unit_id, "node_ids": [node_id]})
                    element_index += 1

            return {
                "schema": SCHEMA,
                "package_path": package_path,
                "spine": spine_paths,
                "nodes": nodes,
                "units": units,
                "unit_node_links": links,
            }
    except ExportError:
        raise
    except EpubArchiveError as exc:
        raise ExportError(str(exc)) from None
    except KeyError as exc:
        raise ExportError(f"EPUB archive is missing an expected member: {exc}") from None
    except Exception as exc:
        raise ExportError(f"EPUB could not be read ({exc.__class__.__name__})") from None


@dataclass
class EpubExportResult:
    content: bytes
    manifest: list = field(default_factory=list)
    limitations: list = field(default_factory=list)


def _set_rtl_attributes(root) -> None:
    for el in root.iter():
        if _local(el.tag) in ("html", "body"):
            el.set("dir", "rtl")
            if _local(el.tag) == "html":
                el.set("lang", "he")
                el.set("{http://www.w3.org/XML/1998/namespace}lang", "he")


def _apply_translation_to_element(el, translated_text: str, node: dict, unit_id: str, limitations: list) -> None:
    """Substitute ``el``'s content with ``translated_text``.

    - A block containing any media descendant (img/svg/table/audio/video/
      object/picture) is left completely untouched (original-language text
      and media both kept) rather than risk losing the embedded media --
      recorded as ``media_block_not_translated``.
    - A block with only inline formatting/link children is flattened to
      plain translated text; any *direct-child* ``<a>`` elements are
      re-appended after the translated text so their ``href`` target keeps
      working (its exact inline position relative to the translation is
      lost) -- recorded as ``inline_markup_flattened``. A link nested more
      deeply (e.g. inside ``<em><a>...</a></em>``) is not specially
      preserved and is flattened away with the rest of that inline markup;
      this is a documented limitation of the smallest-robust-exporter scope.
    """
    if node["has_media"]:
        limitations.append({
            "kind": "media_block_not_translated", "unit_id": unit_id, "node_id": node["node_id"],
            "detail": "block contains an image/table/audio/video element; left in its original "
                      "language untouched rather than risk losing the embedded media on substitution",
        })
        return
    children = list(el)
    links = [child for child in children if _local(child.tag) == _INLINE_LINK_TAG]
    for child in children:
        el.remove(child)
    el.text = translated_text
    if links:
        el.text += " "
        for link in links:
            link.tail = " "
            el.append(link)
        links[-1].tail = None
        limitations.append({
            "kind": "inline_markup_flattened", "unit_id": unit_id, "node_id": node["node_id"],
            "detail": "nested inline formatting/links inside this block were flattened to plain "
                      "translated text; link targets are preserved but relocated to the end of the block",
        })
    elif children:
        limitations.append({
            "kind": "inline_markup_flattened", "unit_id": unit_id, "node_id": node["node_id"],
            "detail": "nested inline formatting inside this block was dropped on substitution",
        })


def export_epub(path_or_bytes, epub_structure, translations) -> EpubExportResult:
    """Rebuild the EPUB at ``path_or_bytes`` with translated Hebrew text
    substituted into the blocks described by ``epub_structure`` (from
    :func:`extract_epub_structure`). Every file in the archive that is not
    a rewritten spine chapter -- package metadata, CSS, images, fonts,
    nav/TOC -- is copied through byte-for-byte unchanged, so spine order,
    manifest, CSS links and image references all keep working.

    ``translations`` maps ``unit_id -> {"text", "approved", ...}``; a unit
    with no entry keeps its original (untranslated) source text and
    records a ``missing_translation`` limitation rather than being dropped.

    Raises :class:`ExportError` for an invalid archive/structure/mapping.
    """
    if not isinstance(epub_structure, dict) or epub_structure.get("schema") != SCHEMA:
        raise ExportError("export_epub requires a structure produced by extract_epub_structure")
    translations = validate_translations_mapping(translations)

    nodes_by_chapter = {}
    for node in epub_structure["nodes"]:
        nodes_by_chapter.setdefault(node["chapter_path"], []).append(node)
    units_by_node_id = {link["node_ids"][0]: link["unit_id"] for link in epub_structure["unit_node_links"]}

    manifest, limitations = [], []
    package_path = epub_structure.get("package_path")
    out_buf = io.BytesIO()
    try:
        source_archive = _open_validated_archive(path_or_bytes)
        with source_archive:
            with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as out_archive:
                for item in source_archive.infolist():
                    raw = source_archive.read(item.filename)
                    if item.filename in nodes_by_chapter:
                        raw, chapter_manifest = _rewrite_chapter(
                            raw, nodes_by_chapter[item.filename], units_by_node_id,
                            translations, limitations,
                        )
                        manifest.extend(chapter_manifest)
                    elif item.filename == package_path:
                        raw = _rewrite_package_language(raw)
                    out_archive.writestr(item, raw)
    except ExportError:
        raise
    except EpubArchiveError as exc:
        raise ExportError(str(exc)) from None
    except KeyError as exc:
        raise ExportError(f"EPUB archive is missing an expected member: {exc}") from None
    except Exception as exc:
        raise ExportError(f"EPUB could not be rebuilt ({exc.__class__.__name__})") from None

    return EpubExportResult(content=out_buf.getvalue(), manifest=manifest, limitations=limitations)


def _rewrite_package_language(raw: bytes) -> bytes:
    """Set ``dc:language`` to ``he`` in the package document, since the
    whole translated book is now in Hebrew. Every other package metadata
    field (title, creator, identifiers, rights) is preserved unchanged --
    Session X translates body content only, not front-matter metadata."""
    root = _xml(raw)
    found = False
    for el in root.iter():
        if _local(el.tag) == "language":
            el.text = "he"
            found = True
    if not found:
        return raw
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _rewrite_chapter(raw: bytes, nodes: list, units_by_node_id: dict, translations: dict, limitations: list):
    root = _xml(raw)
    body = next((e for e in root.iter() if _local(e.tag) == "body"), root)
    by_index = {}
    index = 0
    for el in body.iter():
        tag = _local(el.tag)
        if tag in _BLOCK_TAGS:
            by_index[index] = el
            index += 1

    manifest = []
    for node in nodes:
        el = by_index.get(node["element_index"])
        if el is None:
            continue
        unit_id = units_by_node_id[node["node_id"]]
        record = translations.get(unit_id)
        if record is None:
            limitations.append({
                "kind": "missing_translation", "unit_id": unit_id, "node_id": node["node_id"],
                "detail": "no translation supplied; left in its original source language",
            })
            manifest.append({"unit_id": unit_id, "node_ids": [node["node_id"]], "kind": node["kind"],
                              "rendered": True, "translated": False})
            continue
        _apply_translation_to_element(el, record["text"], node, unit_id, limitations)
        manifest.append({
            "unit_id": unit_id, "node_ids": [node["node_id"]], "kind": node["kind"],
            "rendered": True, "translated": True,
            "approved": record.get("approved", False), "status": record.get("status", "unreviewed"),
        })

    _set_rtl_attributes(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), manifest
