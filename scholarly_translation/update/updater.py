"""Background update check, staging, switch and rollback.

Nothing here switches the running version: ``check`` only stages a verified
folder ``app/<version>`` plus ``app/staged.txt``. The launcher (run-ui.ps1)
applies it at the next start through the command line of this module:

    python -B -m scholarly_translation.update.updater <command> --install-root R

Only anonymous GETs to GitHub hosts are made; no telemetry. HTTP transport and
clock are injectable for offline tests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .. import app_paths
from . import manifest as mf

MANIFEST_NAME = ".manifest.json"
SIGNATURE_NAME = ".manifest.json.sig"
STAGED_FILE = "staged.txt"
CURRENT_FILE = "current.txt"
PREVIOUS_FILE = "previous.txt"
STATUS_FILE = "update_status.json"
SETTINGS_REL = Path("settings") / "update.json"
LOG_NAME = "update.log"
KEEP_VERSIONS = 2
SHORT_TIMEOUT = 10.0


class UpdateError(Exception):
    pass


@dataclass
class Response:
    status: int
    url: str
    body: bytes


class UrllibTransport:
    """HTTPS GET that refuses redirects to hosts outside the allow-list."""

    class _Redirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not mf.is_allowed_url(newurl):
                raise urllib.error.URLError(f"redirect to a disallowed host: {newurl}")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    def get(self, url: str, timeout: float, max_bytes: int) -> Response:
        opener = urllib.request.build_opener(self._Redirects)
        request = urllib.request.Request(url, headers={"User-Agent": "ScholarlyTranslation-updater"})
        with opener.open(request, timeout=timeout) as handle:
            body = handle.read(max_bytes + 1)
            return Response(getattr(handle, "status", 200), handle.geturl(), body)


@dataclass
class UpdateStatus:
    current: str = ""
    auto_update: bool = True
    staged: str | None = None
    available: str | None = None
    notes_he: str = ""
    notes_en: str = ""
    last_error: str = ""
    last_check: float | None = None
    updated_to: str | None = None       # set by switch: "updated to X" notice
    updated_notes_he: str = ""
    updated_notes_en: str = ""
    rejected: list = field(default_factory=list)  # versions that failed to start

    def to_dict(self) -> dict:
        return asdict(self)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_join(base: Path, relative: str) -> Path:
    target = (base / mf.normalize_path(relative)).resolve()
    if not target.is_relative_to(base.resolve()):
        raise UpdateError(f"path escapes the version folder: {relative}")
    return target


def _utc(clock) -> str:
    return datetime.fromtimestamp(clock(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- on-disk state ------------------------------------------------------------

def app_dir(root: Path) -> Path:
    return Path(root) / "app"


def load_status(root: Path) -> UpdateStatus:
    try:
        raw = json.loads((app_dir(root) / STATUS_FILE).read_text(encoding="utf-8"))
        known = {k: v for k, v in raw.items() if k in UpdateStatus.__dataclass_fields__}
        return UpdateStatus(**known)
    except (OSError, ValueError, TypeError):
        return UpdateStatus()


def save_status(root: Path, status: UpdateStatus) -> None:
    app_paths.atomic_write_text(app_dir(root) / STATUS_FILE, json.dumps(status.to_dict(), indent=2))


def settings_path(data_dir: Path) -> Path:
    return Path(data_dir) / SETTINGS_REL


def get_auto_update(data_dir: Path) -> bool:
    try:
        value = json.loads(settings_path(data_dir).read_text(encoding="utf-8")).get("auto_update", True)
    except (OSError, ValueError, AttributeError):
        return True
    return value if isinstance(value, bool) else True


def set_auto_update(data_dir: Path, enabled: bool) -> None:
    app_paths.atomic_write_text(settings_path(data_dir), json.dumps({"auto_update": bool(enabled)}))


def write_log(data_dir: Path, message: str, clock=time.time) -> None:
    try:
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        with open(Path(data_dir) / LOG_NAME, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{_utc(clock)} {message}\n")
    except OSError:
        pass


def version_dirs(root: Path) -> list:
    base = app_dir(root)
    if not base.is_dir():
        return []
    return [p.name for p in base.iterdir() if p.is_dir() and app_paths.VERSION_RE.fullmatch(p.name)]


def prune_versions(root: Path, keep=KEEP_VERSIONS) -> list:
    """Keep the current and previous versions (at most ``keep``), staged one
    too; remove the rest and stale partial folders."""
    base = app_dir(root)
    protected = {v for v in (app_paths.read_pointer(base / CURRENT_FILE),
                             app_paths.read_pointer(base / PREVIOUS_FILE),
                             app_paths.read_pointer(base / STAGED_FILE)) if v}
    removed = []
    # Newest unprotected folders fill any free slot up to ``keep``; the rest go.
    slots = max(0, keep - len(protected))
    for name in sorted(version_dirs(root), key=mf.parse_version, reverse=True):
        if name in protected:
            continue
        if slots > 0:
            slots -= 1
            continue
        shutil.rmtree(base / name, ignore_errors=True)
        removed.append(name)
    for stale in base.glob("*.partial") if base.is_dir() else []:
        shutil.rmtree(stale, ignore_errors=True)
        removed.append(stale.name)
    return removed


def choose_rollback_target(current: str | None, previous: str | None, existing) -> str | None:
    """Pure rollback selection: the previous version if it is distinct from
    the current one and its folder still exists."""
    if previous and previous != current and previous in set(existing):
        return previous
    return None


# --- the updater --------------------------------------------------------------

class Updater:
    def __init__(self, root: Path, *, transport=None, clock=time.time, public_key_b64=None,
                 dist_repo: str = mf.DIST_REPO, data_dir: Path | None = None,
                 current: str | None = None, timeout: float = SHORT_TIMEOUT):
        self.root = Path(root)
        self.transport = transport or UrllibTransport()
        self.clock = clock
        self.public_key_b64 = public_key_b64
        self.dist_repo = dist_repo
        self.data_dir = Path(data_dir) if data_dir is not None else app_paths.data_root_for_install(self.root)
        self.timeout = timeout
        self._current = current
        self.downloaded: list = []
        self.reused: list = []
        self._lock = threading.Lock()

    @property
    def app(self) -> Path:
        return app_dir(self.root)

    def current_version(self) -> str:
        return self._current or app_paths.read_pointer(self.app / CURRENT_FILE) or app_paths.DEV_VERSION

    def auto_update_enabled(self) -> bool:
        return get_auto_update(self.data_dir)

    def set_auto_update(self, enabled: bool) -> None:
        set_auto_update(self.data_dir, enabled)

    def status(self) -> UpdateStatus:
        status = load_status(self.root)
        status.current = self.current_version()
        status.auto_update = self.auto_update_enabled()
        staged = app_paths.read_pointer(self.app / STAGED_FILE)
        status.staged = staged if staged and (self.app / staged).is_dir() else None
        return status

    # -- network --
    def _fetch(self, url: str, max_bytes: int) -> bytes:
        if not mf.is_allowed_url(url):
            raise UpdateError(f"disallowed URL: {url}")
        response = self.transport.get(url, self.timeout, max_bytes)
        if not mf.is_allowed_url(response.url):
            raise UpdateError(f"redirected to a disallowed host: {response.url}")
        if response.status != 200:
            raise UpdateError(f"HTTP {response.status} for {url}")
        if len(response.body) > max_bytes:
            raise UpdateError(f"response too large for {url}")
        return response.body

    # -- check --
    def check(self) -> UpdateStatus:
        with self._lock:
            status = self.status()
            status.last_check = self.clock()
            status.last_error = ""
            try:
                self._check(status)
            except (UpdateError, mf.ManifestError, OSError, urllib.error.URLError, ValueError) as exc:
                status.last_error = str(exc) or exc.__class__.__name__
            save_status(self.root, status)
            return self.status()

    def _check(self, status: UpdateStatus) -> None:
        data = self._fetch(mf.manifest_url(self.dist_repo), mf.MAX_MANIFEST_BYTES)
        sig = self._fetch(mf.signature_url(self.dist_repo), 4096)
        manifest = mf.load_verified_manifest(data, sig, self.public_key_b64)
        if mf.compare_versions(manifest.version, self.current_version()) <= 0:
            status.available = None
            status.notes_he = status.notes_en = ""
            return
        if manifest.min_launcher > mf.LAUNCHER_VERSION:
            raise UpdateError("this update needs a newer installer; download the latest setup")
        if manifest.version in status.rejected:
            raise UpdateError(f"version {manifest.version} previously failed to start; skipped")
        status.available = manifest.version
        status.notes_he, status.notes_en = manifest.notes_he, manifest.notes_en
        if not self.auto_update_enabled():
            return
        if status.staged == manifest.version:
            return
        self._stage(manifest, data, sig)
        status.staged = manifest.version

    # -- staging --
    def _stage(self, manifest: mf.Manifest, manifest_bytes: bytes, sig: bytes) -> None:
        current_dir = self.app / self.current_version()
        final = self.app / manifest.version
        partial = self.app / f"{manifest.version}.partial"
        for leftover in (partial, final):
            if leftover.exists():
                shutil.rmtree(leftover)
        self.downloaded, self.reused = [], []
        try:
            partial.mkdir(parents=True)
            for path, entry in sorted(manifest.files.items()):
                target = _safe_join(partial, path)
                target.parent.mkdir(parents=True, exist_ok=True)
                source = current_dir / path
                if (source.is_file() and source.stat().st_size == entry.size
                        and sha256_file(source) == entry.sha256):
                    shutil.copy2(source, target)
                    self.reused.append(path)
                    continue
                body = self._fetch(mf.file_url(self.dist_repo, manifest.tag, path), entry.size)
                if len(body) != entry.size or hashlib.sha256(body).hexdigest() != entry.sha256:
                    raise UpdateError(f"downloaded file failed verification: {path}")
                target.write_bytes(body)
                self.downloaded.append(path)
            (partial / MANIFEST_NAME).write_bytes(manifest_bytes)
            (partial / SIGNATURE_NAME).write_bytes(sig)
            os.replace(partial, final)
        except BaseException:
            shutil.rmtree(partial, ignore_errors=True)
            raise
        app_paths.atomic_write_text(self.app / STAGED_FILE, manifest.version + "\n")


# --- launcher-side steps (also unit tested) -------------------------------------

def verify_staged(root: Path, public_key_b64: str | None = None) -> dict:
    """Re-verify the staged folder from disk. Returns
    ``{"status": "none"|"ready"|"invalid", ...}``."""
    base = app_dir(root)
    version = app_paths.read_pointer(base / STAGED_FILE)
    if not version:
        return {"status": "none"}
    folder = base / version
    current = app_paths.read_pointer(base / CURRENT_FILE)
    try:
        if not folder.is_dir():
            raise UpdateError("staged folder is missing")
        manifest = mf.load_verified_manifest((folder / MANIFEST_NAME).read_bytes(),
                                             (folder / SIGNATURE_NAME).read_bytes(), public_key_b64)
        if manifest.version != version:
            raise UpdateError("staged folder does not match its manifest")
        if current and mf.compare_versions(version, current) <= 0:
            raise UpdateError("staged version is not newer than the current one")
        for path, entry in manifest.files.items():
            file = _safe_join(folder, path)
            if not file.is_file() or file.stat().st_size != entry.size or sha256_file(file) != entry.sha256:
                raise UpdateError(f"staged file failed verification: {path}")
        known = set(manifest.files) | {MANIFEST_NAME, SIGNATURE_NAME}
        for found in folder.rglob("*"):
            relative = found.relative_to(folder).as_posix()
            if found.is_file() and relative not in known and "__pycache__" not in relative.split("/"):
                raise UpdateError(f"unexpected file in staged folder: {relative}")
        old_req = base / current / "requirements.txt" if current else None
        changed = not (old_req and old_req.is_file() and sha256_file(old_req) == manifest.requirements_sha256)
    except (UpdateError, mf.ManifestError, OSError) as exc:
        return {"status": "invalid", "version": version, "reason": str(exc)}
    return {"status": "ready", "version": version, "previous": current,
            "requirements_changed": changed,
            "requirements": str(folder / "requirements.txt")}


def reject_staged(root: Path, reason: str, clock=time.time) -> None:
    """Drop the staged version (verification or pip failed); stay on current."""
    base = app_dir(root)
    version = app_paths.read_pointer(base / STAGED_FILE)
    try:
        (base / STAGED_FILE).unlink()
    except OSError:
        pass
    if version:
        shutil.rmtree(base / version, ignore_errors=True)
        status = load_status(root)
        status.last_error = f"update {version} not applied: {reason}"
        status.staged = None
        save_status(root, status)
    write_log(app_paths.data_root_for_install(root), f"update to {version} not applied, staying on current: {reason}", clock)


def switch_to_staged(root: Path, clock=time.time, public_key_b64: str | None = None) -> dict:
    """Atomically make the staged version current (previous is kept)."""
    base = app_dir(root)
    info = verify_staged(root, public_key_b64)
    if info["status"] != "ready":
        raise UpdateError(info.get("reason", "nothing staged"))
    version, previous = info["version"], info["previous"]
    if previous:
        app_paths.atomic_write_text(base / PREVIOUS_FILE, previous + "\n")
    app_paths.atomic_write_text(base / CURRENT_FILE, version + "\n")
    try:
        (base / STAGED_FILE).unlink()
    except OSError:
        pass
    manifest = mf.parse_manifest((base / version / MANIFEST_NAME).read_bytes())
    status = load_status(root)
    status.updated_to = version
    status.updated_notes_he, status.updated_notes_en = manifest.notes_he, manifest.notes_en
    status.staged = None
    status.last_error = ""
    save_status(root, status)
    write_log(app_paths.data_root_for_install(root), f"switched from {previous} to {version}", clock)
    prune_versions(root)
    return {"version": version, "previous": previous}


def rollback(root: Path, reason: str, clock=time.time) -> dict:
    """The new version did not start: switch back to the previous one."""
    base = app_dir(root)
    current = app_paths.read_pointer(base / CURRENT_FILE)
    target = choose_rollback_target(current, app_paths.read_pointer(base / PREVIOUS_FILE), version_dirs(root))
    data_dir = app_paths.data_root_for_install(root)
    if target is None:
        write_log(data_dir, f"rollback from {current} impossible: no previous version ({reason})", clock)
        return {"rolled_back": False, "current": current}
    app_paths.atomic_write_text(base / CURRENT_FILE, target + "\n")
    status = load_status(root)
    if current and current not in status.rejected:
        status.rejected.append(current)
    status.updated_to = None
    status.last_error = f"version {current} failed to start and was rolled back: {reason}"
    save_status(root, status)
    write_log(data_dir, f"rolled back from {current} to {target}: {reason}", clock)
    return {"rolled_back": True, "from": current, "to": target}


# --- app integration -------------------------------------------------------------

def ui_status(code_root: Path | None = None) -> dict | None:
    """Status for the UI, or None for a development checkout (no updates)."""
    root = app_paths.install_root(code_root)
    if root is None:
        return None
    return Updater(root).status().to_dict()


def start_background_check(code_root: Path | None = None, **kwargs) -> threading.Thread | None:
    """Fire-and-forget check at app start. No-op in a development checkout."""
    root = app_paths.install_root(code_root)
    if root is None:
        return None
    updater = Updater(root, **kwargs)
    thread = threading.Thread(target=updater.check, name="update-check", daemon=True)
    thread.start()
    return thread


# --- command line used by run-ui.ps1 -------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="scholarly_translation.update.updater")
    parser.add_argument("command", choices=["prepare", "switch", "reject", "rollback", "check"])
    parser.add_argument("--install-root", required=True)
    parser.add_argument("--reason", default="")
    args = parser.parse_args(argv)
    root = Path(args.install_root)
    try:
        if args.command == "prepare":
            result = verify_staged(root)
        elif args.command == "switch":
            result = switch_to_staged(root)
        elif args.command == "reject":
            reject_staged(root, args.reason or "unspecified")
            result = {"ok": True}
        elif args.command == "rollback":
            result = rollback(root, args.reason or "unspecified")
        else:
            result = Updater(root).check().to_dict()
    except Exception as exc:  # the launcher must always get one JSON line
        result = {"status": "error", "reason": str(exc)}
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
