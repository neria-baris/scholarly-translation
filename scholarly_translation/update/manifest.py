"""Release manifest: schema, Ed25519 signature check, path/URL/version rules.

Pure functions; no network. ``cryptography`` is imported lazily so the rest of
the app starts even where it is missing (updates are then simply unavailable).
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit

# The public distribution repository (owner decision 2026-11-05).
DIST_REPO = "neria-baris/scholarly-translation-app"

# Base64 of the owner's 32-byte Ed25519 release public key (generated
# 2026-11-05 with scripts/release/sign_manifest.py --generate-key; the private
# key is kept offline by the owner, never in this repository).
PUBLIC_KEY_B64 = "weiLSddVaPQbPFck36ArGA9SMqGY9RKTgcxXiDDEHP8="

SCHEMA = 1
LAUNCHER_VERSION = 1  # bumped when run-ui.ps1 gains behaviour a manifest may require

ALLOWED_HOSTS = frozenset({
    "github.com",
    "objects.githubusercontent.com",
    "raw.githubusercontent.com",
    "release-assets.githubusercontent.com",
})

# Runtime allow-list shared with scripts/release/build_release.py.
RUNTIME_PACKAGE_DIR = "scholarly_translation"
RUNTIME_ROOT_FILES = (
    "requirements.txt",
    "run-ui.ps1",
    "install.ps1",
    "Install.bat",
    "Run Scholarly Translation.vbs",
    # Google Desktop-app OAuth client (installed-app model: not a confidential
    # secret). Shipped only once the owner commits it; web_ui reads it from ROOT.
    "account_config.json",
)

MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 200 * 1024 * 1024

_VERSION_RE = re.compile(r"^\d+(\.\d+){0,3}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class ManifestError(Exception):
    """Manifest, signature, path or URL rejected."""


# --- versions -----------------------------------------------------------------

def parse_version(text: str) -> tuple:
    if not isinstance(text, str) or not _VERSION_RE.fullmatch(text):
        raise ManifestError(f"invalid version: {text!r}")
    parts = [int(p) for p in text.split(".")]
    return tuple(parts + [0] * (4 - len(parts)))


def compare_versions(a: str, b: str) -> int:
    pa, pb = parse_version(a), parse_version(b)
    return (pa > pb) - (pa < pb)


# --- paths and URLs -----------------------------------------------------------

def normalize_path(raw: str) -> str:
    """Normalise a manifest path to forward slashes; reject anything that could
    leave the version folder."""
    if not isinstance(raw, str) or not raw:
        raise ManifestError("empty path")
    path = raw.replace("\\", "/")
    if "\x00" in path or ":" in path or _DRIVE_RE.match(path):
        raise ManifestError(f"drive or stream path: {raw!r}")
    if path.startswith("/"):
        raise ManifestError(f"absolute path: {raw!r}")
    parts = path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ManifestError(f"unsafe path: {raw!r}")
    if any(p != p.strip() or p.endswith(".") for p in parts):
        raise ManifestError(f"unsafe path component: {raw!r}")
    top = parts[0]
    if len(parts) == 1:
        if top not in RUNTIME_ROOT_FILES:
            raise ManifestError(f"path outside the app tree: {raw!r}")
    elif top != RUNTIME_PACKAGE_DIR:
        raise ManifestError(f"path outside the app tree: {raw!r}")
    return path


def is_allowed_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return (parts.scheme == "https" and (parts.hostname or "").lower() in ALLOWED_HOSTS
            and port in (None, 443) and not parts.username and not parts.password)


def manifest_url(repo: str = DIST_REPO) -> str:
    return f"https://github.com/{repo}/releases/latest/download/manifest.json"


def signature_url(repo: str = DIST_REPO) -> str:
    return manifest_url(repo) + ".sig"


def file_url(repo: str, tag: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{tag}/{quote(normalize_path(path))}"


# --- signature ----------------------------------------------------------------

def _decode_signature(sig: bytes) -> bytes:
    if len(sig) == 64:
        return sig
    try:
        raw = base64.b64decode(sig.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ManifestError("signature is not valid base64") from exc
    if len(raw) != 64:
        raise ManifestError("signature has the wrong length")
    return raw


def verify_signature(data: bytes, sig: bytes, public_key_b64: str | None = None) -> None:
    """Raise ManifestError unless ``sig`` is a valid Ed25519 signature of data."""
    key_text = PUBLIC_KEY_B64 if public_key_b64 is None else public_key_b64
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:  # pragma: no cover - dependency missing
        raise ManifestError("the 'cryptography' package is not installed") from exc
    try:
        key_bytes = base64.b64decode(key_text, validate=True)
        if len(key_bytes) != 32:
            raise ValueError("length")
        key = Ed25519PublicKey.from_public_bytes(key_bytes)
    except (binascii.Error, ValueError) as exc:
        raise ManifestError("the embedded update public key is not configured") from exc
    try:
        key.verify(_decode_signature(sig), data)
    except InvalidSignature as exc:
        raise ManifestError("manifest signature is invalid") from exc


# --- manifest -----------------------------------------------------------------

@dataclass(frozen=True)
class FileEntry:
    sha256: str
    size: int


@dataclass(frozen=True)
class Manifest:
    version: str
    tag: str
    min_launcher: int
    requirements_sha256: str
    files: dict = field(default_factory=dict)  # normalised path -> FileEntry
    notes_he: str = ""
    notes_en: str = ""


def parse_manifest(data: bytes) -> Manifest:
    """Validate manifest JSON (call only after the signature verified)."""
    if len(data) > MAX_MANIFEST_BYTES:
        raise ManifestError("manifest is too large")
    try:
        doc = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ManifestError("manifest is not valid JSON") from exc
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise ManifestError("unsupported manifest schema")
    version = doc.get("version")
    parse_version(version)
    tag = doc.get("tag")
    if tag != f"v{version}":
        raise ManifestError("tag does not match version")
    min_launcher = doc.get("min_launcher", 1)
    if not isinstance(min_launcher, int) or isinstance(min_launcher, bool) or min_launcher < 1:
        raise ManifestError("invalid min_launcher")
    req_sha = doc.get("requirements_sha256")
    if not isinstance(req_sha, str) or not _SHA_RE.fullmatch(req_sha):
        raise ManifestError("invalid requirements_sha256")
    raw_files = doc.get("files")
    if not isinstance(raw_files, dict) or not raw_files:
        raise ManifestError("manifest lists no files")
    files: dict = {}
    for raw_path, meta in raw_files.items():
        path = normalize_path(raw_path)
        if path in files:
            raise ManifestError(f"duplicate path: {path}")
        if not isinstance(meta, dict):
            raise ManifestError(f"invalid entry for {path}")
        sha, size = meta.get("sha256"), meta.get("size")
        if not isinstance(sha, str) or not _SHA_RE.fullmatch(sha):
            raise ManifestError(f"invalid sha256 for {path}")
        if not isinstance(size, int) or isinstance(size, bool) or not 0 <= size <= MAX_FILE_BYTES:
            raise ManifestError(f"invalid size for {path}")
        files[path] = FileEntry(sha, size)
    if "requirements.txt" in files and files["requirements.txt"].sha256 != req_sha:
        raise ManifestError("requirements_sha256 does not match requirements.txt")
    notes = []
    for key in ("notes_he", "notes_en"):
        value = doc.get(key, "")
        if not isinstance(value, str) or len(value) > 20000:
            raise ManifestError(f"invalid {key}")
        notes.append(value)
    return Manifest(version, tag, min_launcher, req_sha, files, notes[0], notes[1])


def load_verified_manifest(manifest_bytes: bytes, sig_bytes: bytes,
                           public_key_b64: str | None = None) -> Manifest:
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise ManifestError("manifest is too large")
    verify_signature(manifest_bytes, sig_bytes, public_key_b64)
    return parse_manifest(manifest_bytes)
