"""Offline helpers for the C6 update tests (no network, no real keys)."""

import base64
import hashlib
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scholarly_translation.update import manifest as mf
from scholarly_translation.update.updater import Response

REPO = "TEST/dist-repo"


def make_key():
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return key, base64.b64encode(public).decode("ascii")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_release(version, files, key, notes_he="", notes_en="", min_launcher=1):
    """files: {path: bytes}. Returns (manifest_bytes, sig_bytes)."""
    doc = {
        "schema": 1, "version": version, "tag": f"v{version}", "min_launcher": min_launcher,
        "requirements_sha256": sha(files.get("requirements.txt", b"")),
        "files": {p: {"sha256": sha(b), "size": len(b)} for p, b in files.items()},
        "notes_he": notes_he, "notes_en": notes_en,
    }
    data = json.dumps(doc, sort_keys=True).encode("utf-8")
    return data, base64.b64encode(key.sign(data))


class FakeTransport:
    """Serves URL -> bytes; ``redirects`` maps URL -> final URL reported."""

    def __init__(self, routes=None, redirects=None):
        self.routes = dict(routes or {})
        self.redirects = dict(redirects or {})
        self.calls = []

    def get(self, url, timeout, max_bytes):
        self.calls.append(url)
        if url not in self.routes:
            return Response(404, url, b"")
        body = self.routes[url]
        if isinstance(body, Exception):
            raise body
        return Response(200, self.redirects.get(url, url), body[: max_bytes + 1])

    def release_routes(self, version, files, key, **kw):
        data, sig = make_release(version, files, key, **kw)
        self.routes[mf.manifest_url(REPO)] = data
        self.routes[mf.signature_url(REPO)] = sig
        for path, body in files.items():
            self.routes[mf.file_url(REPO, f"v{version}", path)] = body
        return data, sig
