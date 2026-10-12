"""Shared, defensive EPUB-archive-reading primitives.

Used by both ``export_epub.py`` (translated-EPUB export, schema
``epub-structure@1``) and ``epub_extract.py`` (schema-2-compatible
"digital-text" source extraction). Factored out so the archive/XML safety
checks -- DOCTYPE/ENTITY rejection, encrypted-content rejection,
out-of-archive/out-of-bounds reference rejection, XHTML media-type checks --
exist in exactly one place instead of being duplicated across the two
EPUB-reading entry points.

Raises only :class:`EpubArchiveError`; each caller module catches it and
re-raises its own module-specific exception type (``ExportError`` /
``EpubExtractionError``) so neither module's public exception contract
changes.
"""
from __future__ import annotations

import posixpath
import zipfile
from urllib.parse import unquote
from xml.etree import ElementTree as ET

MAX_ENTRIES = 5000
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_ENTRY_BYTES = 10 * 1024 * 1024

XHTML_MEDIA_TYPES = ("application/xhtml+xml", "text/html")

HEADING_TAGS = {f"h{i}": i for i in range(1, 7)}
BLOCK_TAGS = {"p", "li", "blockquote"} | set(HEADING_TAGS)
MEDIA_TAGS = {"img", "svg", "table", "audio", "video", "object", "picture"}
INLINE_LINK_TAG = "a"

# Keep re-serialized XHTML/OPF close to idiomatic EPUB markup (default
# xmlns on <html>, a short "opf"/"dc" prefix) instead of ElementTree's
# auto-generated "ns0:" prefixes. Purely cosmetic -- both forms are
# equally well-formed, namespace-correct XML.
ET.register_namespace("", "http://www.w3.org/1999/xhtml")
ET.register_namespace("opf", "http://www.idpf.org/2007/opf")
ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")


class EpubArchiveError(Exception):
    """Raised for any invalid, encrypted, oversized or malformed EPUB
    archive. Never carries page/book content; callers translate this into
    their own module-specific exception type. ``code`` is a stable machine
    identifier (e.g. ``drm``, ``bad_spine_item``) or ``None``."""

    def __init__(self, message: str, code=None):
        super().__init__(message)
        self.code = code


def local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_xml(content: bytes):
    upper = content.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise EpubArchiveError("EPUB contains an unsupported XML structure (DOCTYPE/ENTITY)")
    try:
        return ET.fromstring(content)
    except ET.ParseError as exc:
        raise EpubArchiveError(f"EPUB contains malformed XML: {exc}") from None


def archive_path(base: str, reference: str) -> str:
    reference = unquote(reference.split("#", 1)[0])
    if not reference or ":" in reference or "\\" in reference or reference.startswith("/"):
        raise EpubArchiveError("EPUB contains an invalid internal reference")
    path = posixpath.normpath(posixpath.join(base, reference))
    if path == ".." or path.startswith("../"):
        raise EpubArchiveError("EPUB reference escapes the archive")
    return path


def open_validated_archive(path_or_bytes) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(path_or_bytes)
    except (zipfile.BadZipFile, OSError) as exc:
        raise EpubArchiveError(f"EPUB archive could not be opened: {exc.__class__.__name__}") from None
    entries = archive.infolist()
    if len(entries) > MAX_ENTRIES or sum(e.file_size for e in entries) > MAX_TOTAL_BYTES or \
            any(e.file_size > MAX_ENTRY_BYTES for e in entries):
        raise EpubArchiveError("EPUB archive is too large after extraction")
    if len({e.filename for e in entries}) != len(entries) or any(e.flag_bits & 1 for e in entries):
        raise EpubArchiveError("EPUB archive is encrypted or internally inconsistent")
    return archive


def resolve_package(archive: zipfile.ZipFile):
    try:
        container_bytes = archive.read("META-INF/container.xml")
    except KeyError:
        raise EpubArchiveError("EPUB is missing META-INF/container.xml") from None
    container = parse_xml(container_bytes)
    rootfile = next((e.get("full-path") for e in container.iter() if local_tag(e.tag) == "rootfile"), None)
    if not rootfile:
        raise EpubArchiveError("EPUB container does not reference a package document")
    package_path = archive_path("", rootfile)
    try:
        package_bytes = archive.read(package_path)
    except KeyError:
        raise EpubArchiveError("EPUB package document is missing") from None
    package = parse_xml(package_bytes)
    base = posixpath.dirname(package_path)
    return package_path, package, base


def encrypted_paths(archive: zipfile.ZipFile) -> set:
    if "META-INF/encryption.xml" not in archive.namelist():
        return set()
    encryption = parse_xml(archive.read("META-INF/encryption.xml"))
    return {archive_path("", e.get("URI", "")) for e in encryption.iter() if local_tag(e.tag) == "CipherReference"}


MATH_OPEN, MATH_CLOSE = "⟦", "⟧"   # protected-formula markers: ⟦ … ⟧
_SUPERSCRIPT = str.maketrans("0123456789+-=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹"
                                                  "⁺⁻⁼⁽⁾ⁿⁱ")
_SUBSCRIPT = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉"
                                              "₊₋₌₍₎")


def math_text(el) -> str:
    """Readable one-line Unicode form of a MathML element (alttext when given)."""
    alt = el.get("alttext")
    if local_tag(el.tag) == "math" and alt and alt.strip():
        return " ".join(alt.split()).replace(MATH_OPEN, "").replace(MATH_CLOSE, "")

    def lin(node):
        tag = local_tag(node.tag)
        kids = [k for k in node if local_tag(k.tag) != "annotation-xml" and local_tag(k.tag) != "annotation"]
        if tag == "mo":
            op = (node.text or "").strip()
            return op if op in ("", "(", ")", "[", "]", "{", "}", "|", ",", ".", "⁡", "⁢") else " " + op + " "
        if tag in ("mi", "mn", "mtext", "ms"):
            return (node.text or "").strip()
        if tag == "semantics" and kids:
            return lin(kids[0])
        if tag in ("msup", "msub") and len(kids) == 2:
            base, script = lin(kids[0]), lin(kids[1])
            table = _SUPERSCRIPT if tag == "msup" else _SUBSCRIPT
            converted = script.translate(table)
            if all(ch != orig or ch.isspace() for ch, orig in zip(converted, script)):
                return base + converted
            return base + ("^" if tag == "msup" else "_") + "(" + script + ")"
        if tag == "msubsup" and len(kids) == 3:
            return lin(kids[0]) + "_(" + lin(kids[1]) + ")^(" + lin(kids[2]) + ")"
        if tag == "mfrac" and len(kids) == 2:
            return "(" + lin(kids[0]) + ")/(" + lin(kids[1]) + ")"
        if tag == "msqrt":
            return "√(" + "".join(lin(k) for k in kids) + ")"
        if tag == "mroot" and len(kids) == 2:
            return "√[" + lin(kids[1]) + "](" + lin(kids[0]) + ")"
        return "".join(lin(k) for k in kids) if kids else (node.text or "").strip()

    text = " ".join(lin(el).split())
    return text.replace(MATH_OPEN, "").replace(MATH_CLOSE, "") or "math"


def block_text(el) -> str:
    """Block text with every inline MathML element replaced by ⟦readable form⟧,
    so formulas travel through translation as protected tokens."""
    parts = []

    def walk(node):
        if node.text:
            parts.append(node.text)
        for child in node:
            if local_tag(child.tag) == "math":
                parts.append(MATH_OPEN + math_text(child) + MATH_CLOSE)
            else:
                walk(child)
            if child.tail:
                parts.append(child.tail)

    walk(el)
    return "".join(parts).strip()


def resolve_spine(archive: zipfile.ZipFile, package, base: str) -> list:
    """Return ordered, validated chapter archive paths for the package's
    linear spine itemrefs. Raises :class:`EpubArchiveError` for a spine
    entry that is missing, not a real XHTML media type, or DRM-encrypted."""
    items = {e.get("id"): e for e in package.iter() if local_tag(e.tag) == "item"}
    spine_refs = [e.get("idref") for e in package.iter()
                  if local_tag(e.tag) == "itemref" and e.get("linear", "yes") != "no"]
    encrypted = encrypted_paths(archive)
    spine_paths = []
    for item_id in spine_refs:
        item = items.get(item_id)
        if item is None or item.get("media-type") not in XHTML_MEDIA_TYPES:
            raise EpubArchiveError("EPUB spine references a missing or non-XHTML chapter", code="bad_spine_item")
        chapter_path = archive_path(base, item.get("href", ""))
        if chapter_path in encrypted:
            raise EpubArchiveError("EPUB chapter is protected by DRM and cannot be translated", code="drm")
        spine_paths.append(chapter_path)
    return spine_paths


NCX_MEDIA_TYPE = "application/x-dtbncx+xml"
_OPS_TYPE = "{http://www.idpf.org/2007/ops}type"


def _manifest_xhtml(package, base: str) -> list:
    """Manifest XHTML items as (item, archive_path) in manifest order."""
    result = []
    for e in package.iter():
        if local_tag(e.tag) == "item" and e.get("media-type") in XHTML_MEDIA_TYPES:
            try:
                result.append((e, archive_path(base, e.get("href", ""))))
            except EpubArchiveError:
                continue
    return result


def _ncx_order(archive, package, base: str) -> list:
    for e in package.iter():
        if local_tag(e.tag) == "item" and e.get("media-type") == NCX_MEDIA_TYPE:
            try:
                ncx_path = archive_path(base, e.get("href", ""))
                root = parse_xml(archive.read(ncx_path))
            except (EpubArchiveError, KeyError):
                continue
            ncx_base = posixpath.dirname(ncx_path)
            ranked = []
            for index, point in enumerate(el for el in root.iter() if local_tag(el.tag) == "navPoint"):
                content = next((c for c in point if local_tag(c.tag) == "content"), None)
                if content is None or not content.get("src"):
                    continue
                order = point.get("playOrder", "")
                ranked.append((int(order) if order.isdigit() else 10 ** 9, index, content.get("src")))
            paths = []
            for _, _, src in sorted(ranked):
                try:
                    paths.append(archive_path(ncx_base, src))
                except EpubArchiveError:
                    continue
            if paths:
                return paths
    return []


def _nav_order(archive, package, base: str) -> tuple:
    """Return (ordered toc link paths, nav document path or None)."""
    for e in package.iter():
        if local_tag(e.tag) == "item" and "nav" in (e.get("properties") or "").split():
            try:
                nav_path = archive_path(base, e.get("href", ""))
                root = parse_xml(archive.read(nav_path))
            except (EpubArchiveError, KeyError):
                continue
            navs = [n for n in root.iter() if local_tag(n.tag) == "nav"]
            toc = [n for n in navs if "toc" in (n.get(_OPS_TYPE) or n.get("type") or "").split()] or navs[:1]
            nav_base = posixpath.dirname(nav_path)
            paths = []
            for nav in toc:
                for a in nav.iter():
                    if local_tag(a.tag) == "a" and a.get("href"):
                        try:
                            paths.append(archive_path(nav_base, a.get("href")))
                        except EpubArchiveError:
                            continue
            if paths:
                return paths, nav_path
            return [], nav_path
    return [], None


def resolve_reading_order(archive: zipfile.ZipFile, package, base: str) -> tuple:
    """Return ``(chapter_paths, fallback)``. ``fallback`` is ``None`` when the
    spine was used, else ``"ncx"``, ``"nav"`` or ``"manifest"``. Used when
    the spine has no linear itemrefs but content may still exist. Raises
    EpubArchiveError with code ``empty_spine`` when no usable XHTML exists."""
    spine_paths = resolve_spine(archive, package, base)
    if spine_paths:
        return spine_paths, None
    manifest = _manifest_xhtml(package, base)
    names = set(archive.namelist())
    available = [path for _, path in manifest if path in names]
    if not available:
        raise EpubArchiveError("EPUB spine is empty and no chapter documents were found", code="empty_spine")
    available_set = set(available)
    encrypted = encrypted_paths(archive)

    def finish(paths, label):
        seen, ordered = set(), []
        for path in paths:
            if path in seen or path not in available_set:
                continue
            seen.add(path)
            ordered.append(path)
        if not ordered:
            return None
        if any(path in encrypted for path in ordered):
            raise EpubArchiveError("EPUB chapter is protected by DRM and cannot be translated", code="drm")
        return ordered, label

    nav_links, nav_path = _nav_order(archive, package, base)
    for label, candidate in (("ncx", _ncx_order(archive, package, base)), ("nav", nav_links)):
        # Linked documents first, then any remaining manifest XHTML (except
        # the nav document itself) so content missing from the TOC is kept.
        rest = [path for path in available if path != nav_path]
        result = finish(list(candidate) + rest, label) if candidate else None
        if result:
            return result
    return finish([path for path in available if path != nav_path] or available, "manifest")
