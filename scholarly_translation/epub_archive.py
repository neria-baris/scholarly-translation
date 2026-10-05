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
    their own module-specific exception type."""


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


def block_text(el) -> str:
    return "".join(el.itertext()).strip()


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
            raise EpubArchiveError("EPUB spine references a missing or non-XHTML chapter")
        chapter_path = archive_path(base, item.get("href", ""))
        if chapter_path in encrypted:
            raise EpubArchiveError("EPUB chapter is protected by DRM and cannot be translated")
        spine_paths.append(chapter_path)
    return spine_paths
