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


def _map_canonical_units_to_epub_units(structure: dict, epub_structure: dict):
    """Positionally match the canonical schema-2 ``document_structure``'s
    EPUB ("digital-text" origin) nodes to this module's own
    ``epub-structure@1`` nodes, without touching either module's node
    identity scheme (Session G: the smallest adapter reconciling the two
    independent EPUB structures named in audit/current_state.md).

    Both epub_extract.py (which produces the canonical nodes) and this
    module's own :func:`extract_epub_structure` walk the *same* spine
    chapters, filtering the *same* ``BLOCK_TAGS`` with the *same*
    ``block_text`` and skipping the same empty blocks -- so the Kth
    non-empty block in one chapter is provably the Kth entry in the
    other's per-chapter node list, even though neither module's element
    indexing agrees. Matching therefore only needs page/chapter number
    and within-page document order (``source_char_start``), never a
    second independent interpretation of EPUB structure.

    A unit spanning more than one canonical node (segmentation.py only
    ever merges consecutive ``paragraph`` nodes -- STRUCTURE_SCHEMA.md)
    maps to more than one EPUB block; only the first carries the
    translated text (mirroring export_pdf.py's own one-block-per-unit
    rendering), and this is recorded as a ``units_merged_multiple_blocks``
    limitation rather than silently duplicating or dropping text.
    """
    canonical_nodes_by_page = {}
    for node in structure.get("nodes", []):
        canonical_nodes_by_page.setdefault(node["page_id"], []).append(node)
    for nodes in canonical_nodes_by_page.values():
        nodes.sort(key=lambda n: n["source_char_start"])

    epub_nodes_by_chapter_index = {}
    for node in epub_structure["nodes"]:
        epub_nodes_by_chapter_index.setdefault(node["chapter_index"], []).append(node)
    epub_unit_by_node_id = {link["node_ids"][0]: link["unit_id"] for link in epub_structure["unit_node_links"]}

    node_id_map = {}
    for reading in structure.get("readings", []):
        selected = reading.get("selected")
        if not selected or selected.get("origin") != "digital-text":
            continue
        canonical_nodes = canonical_nodes_by_page.get(reading["page_id"], [])
        if not canonical_nodes:
            continue
        epub_nodes = epub_nodes_by_chapter_index.get(reading["page_number"] - 1, [])
        if len(canonical_nodes) != len(epub_nodes):
            raise ExportError(
                "EPUB chapter block count does not match the canonical document structure; "
                "cannot safely export"
            )
        for canonical_node, epub_node in zip(canonical_nodes, epub_nodes):
            node_id_map[canonical_node["node_id"]] = epub_node["node_id"]

    unit_id_map, limitations = {}, []
    for link in structure.get("unit_node_links", []):
        mapped_node_ids = [node_id_map[nid] for nid in link["node_ids"] if nid in node_id_map]
        mapped_unit_ids = [epub_unit_by_node_id[nid] for nid in mapped_node_ids if nid in epub_unit_by_node_id]
        if not mapped_unit_ids:
            continue
        unit_id_map[link["unit_id"]] = mapped_unit_ids
        if len(mapped_unit_ids) > 1:
            limitations.append({
                "kind": "units_merged_multiple_blocks", "unit_id": link["unit_id"],
                "node_ids": mapped_unit_ids,
                "detail": f"{len(mapped_unit_ids)} original EPUB blocks were combined into one "
                          "translation unit; only the first block carries the translated text, the "
                          "remaining original-language block(s) were left untouched below it",
            })
    return unit_id_map, limitations


def export_epub_from_document_structure(path_or_bytes, structure, translations) -> EpubExportResult:
    """Export a translated EPUB from the *canonical* schema-2
    ``document_structure`` (as produced by ``segmentation.build_structure``
    for an EPUB's "digital-text" source, see ``epub_extract.py``) plus a
    ``unit_id -> translation`` mapping keyed by that same canonical
    ``structure``'s unit ids -- the same mapping shape
    ``export_pdf.export_pdf`` accepts, so the simple-UI job runner (or any
    other caller) needs no second translations format for EPUB.

    Internally re-keys the mapping onto this module's own
    ``epub-structure@1`` unit ids (see :func:`_map_canonical_units_to_epub_units`)
    and reuses :func:`export_epub` unchanged, so every existing export/
    rebuild guarantee (byte-for-byte copy of everything but rewritten
    chapters, RTL attributes, media/link preservation) is unaffected.
    """
    if not isinstance(structure, dict) or structure.get("schema_version") != 2:
        raise ExportError("EPUB export requires a schema-2 document_structure with nodes")
    translations = validate_translations_mapping(translations)
    epub_structure = extract_epub_structure(path_or_bytes)
    unit_id_map, extra_limitations = _map_canonical_units_to_epub_units(structure, epub_structure)

    epub_translations = {}
    for unit_id, record in translations.items():
        mapped = unit_id_map.get(unit_id)
        if mapped:
            epub_translations[mapped[0]] = record

    result = export_epub(path_or_bytes, epub_structure, epub_translations)
    result.limitations = list(result.limitations) + extra_limitations
    return result


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
