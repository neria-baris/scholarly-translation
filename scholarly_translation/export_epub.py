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
import posixpath
import zipfile
from dataclasses import dataclass, field
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from .export_common import ExportError, validate_translations_mapping
from .store import deterministic_id

MAX_ENTRIES = 5000
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_ENTRY_BYTES = 10 * 1024 * 1024

_XHTML_MEDIA_TYPES = ("application/xhtml+xml", "text/html")

_HEADING_TAGS = {f"h{i}": i for i in range(1, 7)}
_BLOCK_TAGS = {"p", "li", "blockquote"} | set(_HEADING_TAGS)
_MEDIA_TAGS = {"img", "svg", "table", "audio", "video", "object", "picture"}
_INLINE_LINK_TAG = "a"

SCHEMA = "epub-structure@1"

# Keep re-serialized XHTML/OPF close to idiomatic EPUB markup (default
# xmlns on <html>, a short "opf"/"dc" prefix) instead of ElementTree's
# auto-generated "ns0:" prefixes. Purely cosmetic -- both forms are
# equally well-formed, namespace-correct XML.
ET.register_namespace("", "http://www.w3.org/1999/xhtml")
ET.register_namespace("opf", "http://www.idpf.org/2007/opf")
ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _xml(content: bytes):
    upper = content.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ExportError("EPUB contains an unsupported XML structure (DOCTYPE/ENTITY)")
    try:
        return ET.fromstring(content)
    except ET.ParseError as exc:
        raise ExportError(f"EPUB contains malformed XML: {exc}") from None


def _archive_path(base: str, reference: str) -> str:
    reference = unquote(reference.split("#", 1)[0])
    if not reference or ":" in reference or "\\" in reference or reference.startswith("/"):
        raise ExportError("EPUB contains an invalid internal reference")
    path = posixpath.normpath(posixpath.join(base, reference))
    if path == ".." or path.startswith("../"):
        raise ExportError("EPUB reference escapes the archive")
    return path


def _open_validated_archive(path_or_bytes) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(path_or_bytes)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ExportError(f"EPUB archive could not be opened: {exc.__class__.__name__}") from None
    entries = archive.infolist()
    if len(entries) > MAX_ENTRIES or sum(e.file_size for e in entries) > MAX_TOTAL_BYTES or \
            any(e.file_size > MAX_ENTRY_BYTES for e in entries):
        raise ExportError("EPUB archive is too large after extraction")
    if len({e.filename for e in entries}) != len(entries) or any(e.flag_bits & 1 for e in entries):
        raise ExportError("EPUB archive is encrypted or internally inconsistent")
    return archive


def _resolve_package(archive: zipfile.ZipFile):
    try:
        container_bytes = archive.read("META-INF/container.xml")
    except KeyError:
        raise ExportError("EPUB is missing META-INF/container.xml") from None
    container = _xml(container_bytes)
    rootfile = next((e.get("full-path") for e in container.iter() if _local(e.tag) == "rootfile"), None)
    if not rootfile:
        raise ExportError("EPUB container does not reference a package document")
    package_path = _archive_path("", rootfile)
    try:
        package_bytes = archive.read(package_path)
    except KeyError:
        raise ExportError("EPUB package document is missing") from None
    package = _xml(package_bytes)
    base = posixpath.dirname(package_path)
    return package_path, package, base


def _encrypted_paths(archive: zipfile.ZipFile) -> set:
    if "META-INF/encryption.xml" not in archive.namelist():
        return set()
    encryption = _xml(archive.read("META-INF/encryption.xml"))
    return {_archive_path("", e.get("URI", "")) for e in encryption.iter() if _local(e.tag) == "CipherReference"}


def _block_text(el) -> str:
    return "".join(el.itertext()).strip()


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
            items = {e.get("id"): e for e in package.iter() if _local(e.tag) == "item"}
            spine_refs = [e.get("idref") for e in package.iter()
                          if _local(e.tag) == "itemref" and e.get("linear", "yes") != "no"]
            encrypted = _encrypted_paths(archive)

            spine_paths = []
            nodes, units, links = [], [], []
            order = 0
            for chapter_index, item_id in enumerate(spine_refs):
                item = items.get(item_id)
                if item is None or item.get("media-type") not in _XHTML_MEDIA_TYPES:
                    raise ExportError("EPUB spine references a missing or non-XHTML chapter")
                chapter_path = _archive_path(base, item.get("href", ""))
                if chapter_path in encrypted:
                    raise ExportError("EPUB chapter is protected by DRM and cannot be translated")
                spine_paths.append(chapter_path)
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
