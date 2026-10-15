"""Where the app and the user's data live (development checkout vs. installed).

Installed layout (created by install.ps1, switched by run-ui.ps1):

    %LOCALAPPDATA%\\ScholarlyTranslation\\
        install.marker          marks an installation
        app\\<version>\\         runtime files of one version
        app\\current.txt         the active version (written atomically)
        data\\                   user data; an update never touches it
        heartbeat.txt           refreshed by the running app (see write_heartbeat)

A development checkout has no install marker and keeps ``<repo>/outputs``.
Standard library only.
"""

from __future__ import annotations

import os
import re
import shutil
import threading
import time
from pathlib import Path

APP_FOLDER_NAME = "ScholarlyTranslation"
INSTALL_MARKER = "install.marker"
HEARTBEAT_NAME = "heartbeat.txt"
LEGACY_POINTER_NAME = "legacy_outputs.txt"
MIGRATION_MARKER = ".legacy_outputs_migrated"
DEV_VERSION = "0.0.0-dev"
DATA_ROOT_ENV = "SCHOLARLY_DATA_ROOT"
VERSION_RE = re.compile(r"^\d+(\.\d+){0,3}$")

REPO_ROOT = Path(__file__).resolve().parents[1]


def detect_install_root(code_root: Path | None = None) -> Path | None:
    """The install root when this code runs from ``<root>/app/<version>`` and
    ``<root>/install.marker`` exists, else None (development checkout)."""
    code_root = Path(code_root) if code_root is not None else REPO_ROOT
    app_dir = code_root.parent
    if app_dir.name != "app":
        return None
    root = app_dir.parent
    return root if (root / INSTALL_MARKER).is_file() else None


def install_root(code_root: Path | None = None) -> Path | None:
    return detect_install_root(code_root)


def default_install_root(environ=None) -> Path:
    """Where install.ps1 places a new installation."""
    env = os.environ if environ is None else environ
    base = env.get("LOCALAPPDATA")
    base_path = Path(base) if base else Path.home() / "AppData" / "Local"
    return base_path / APP_FOLDER_NAME


def data_root_for_install(root: Path, environ=None) -> Path:
    env = os.environ if environ is None else environ
    override = (env.get(DATA_ROOT_ENV) or "").strip()
    return Path(override) if override else Path(root) / "data"


def data_root(code_root: Path | None = None, environ=None) -> Path:
    """Env override, else installed ``<root>/data``, else ``<repo>/outputs``."""
    env = os.environ if environ is None else environ
    override = (env.get(DATA_ROOT_ENV) or "").strip()
    if override:
        return Path(override)
    root = detect_install_root(code_root)
    if root is not None:
        return root / "data"
    return (Path(code_root) if code_root is not None else REPO_ROOT) / "outputs"


def current_version(code_root: Path | None = None) -> str:
    """The version folder name when installed, else the development marker."""
    code_root = Path(code_root) if code_root is not None else REPO_ROOT
    if detect_install_root(code_root) is not None and VERSION_RE.fullmatch(code_root.name):
        return code_root.name
    return DEV_VERSION


def atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def read_pointer(path: Path) -> str | None:
    """A one-line version pointer file (current.txt etc.), validated."""
    try:
        value = Path(path).read_text(encoding="utf-8-sig").strip()
    except OSError:
        return None
    return value if VERSION_RE.fullmatch(value) else None


# --- heartbeat ------------------------------------------------------------

def heartbeat_path(code_root: Path | None = None) -> Path:
    """Next to install.marker when installed (the launcher reads it there)."""
    root = detect_install_root(code_root)
    base = root if root is not None else data_root(code_root)
    return base / HEARTBEAT_NAME


def write_heartbeat(code_root: Path | None = None, clock=time.time) -> Path | None:
    """Record that the app is up. Call once from web_ui main after the server
    is listening; best effort, never raises."""
    path = heartbeat_path(code_root)
    try:
        atomic_write_text(path, f"{clock():.3f}\n")
        return path
    except OSError:
        return None


def start_heartbeat_thread(interval: float = 10.0, code_root: Path | None = None) -> threading.Thread:
    def loop():
        while True:
            write_heartbeat(code_root)
            time.sleep(interval)

    thread = threading.Thread(target=loop, name="heartbeat", daemon=True)
    thread.start()
    return thread


# --- one-time migration of an older <install>/outputs ------------------------

_SKIP_TOP_LEVEL = {"tooling"}  # virtual environments are rebuilt, not copied


def _legacy_candidates(root: Path | None, legacy: Path | None) -> list[Path]:
    found: list[Path] = []
    if legacy is not None:
        found.append(Path(legacy))
    if root is not None:
        found.append(root / "outputs")
        pointer = root / LEGACY_POINTER_NAME
        try:
            text = pointer.read_text(encoding="utf-8-sig").strip()
        except OSError:
            text = ""
        if text:
            found.append(Path(text))
    return found


def migrate_legacy_outputs(code_root: Path | None = None, *, data: Path | None = None,
                           legacy: Path | None = None, root: Path | None = None) -> dict:
    """Copy an older ``outputs`` folder into data/ once. Never deletes or
    overwrites anything; idempotent through a marker file inside data/.

    Returns ``{"status": "not-installed"|"already"|"none"|"migrated", "copied": n}``.
    """
    root = root if root is not None else detect_install_root(code_root)
    if data is None:
        if root is None:
            return {"status": "not-installed", "copied": 0}
        data = data_root_for_install(root)
    data = Path(data)
    marker = data / MIGRATION_MARKER
    if marker.exists():
        return {"status": "already", "copied": 0}
    sources = [p for p in _legacy_candidates(root, legacy) if p.is_dir()]
    sources = [p for p in sources if p.resolve() != data.resolve()]
    if not sources:
        return {"status": "none", "copied": 0}
    copied = 0
    data.mkdir(parents=True, exist_ok=True)
    for source in sources:
        for path in source.rglob("*"):
            relative = path.relative_to(source)
            if relative.parts[0] in _SKIP_TOP_LEVEL or not path.is_file():
                continue
            target = data / relative
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied += 1
    atomic_write_text(marker, "\n".join(str(p) for p in sources) + "\n")
    return {"status": "migrated", "copied": copied}
