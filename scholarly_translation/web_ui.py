"""Local browser shell over the existing CLI. No runtime service beyond localhost."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from urllib.parse import quote

from .gui import STEPS, build_command
from .ui_decisions import (
    UIDecisionError, glossary_action, glossary_options, source_decisions, source_options,
)
from . import model_settings, review_salvage, target_languages, user_glossary
from .model_settings import ModelSettingsError


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = ROOT / "outputs" / "ui"
MAX_UPLOAD = 100 * 1024 * 1024
UI_DIR = Path(__file__).resolve().parent
_PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def public_steps() -> list[dict]:
    return [
        {"command": step.command, "title": step.title, "help": step.help,
         "result": step.result, "fields": [vars(item) for item in step.fields]}
        for step in STEPS
    ]


def _read_artifact(path: str, expected: str) -> dict | None:
    if not path:
        return None
    candidate = Path(path).resolve()
    if not candidate.is_relative_to((ROOT / "outputs").resolve()) or not candidate.is_file():
        raise ValueError("artifact must be a local output file")
    if candidate.stat().st_size > 5 * 1024 * 1024:
        raise ValueError("artifact is too large for preview")
    with candidate.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or (
        expected == "structure" and data.get("stage") not in ("structure@1", "structure@2")
    ):
        raise ValueError("artifact has an unexpected format")
    return data


def _title(uri: str) -> str:
    try:
        return Path(unquote(urlparse(uri).path)).name or "מסמך מקומי"
    except (TypeError, ValueError):
        return "מסמך מקומי"


def preview_artifacts(paths: dict) -> dict:
    document = _read_artifact(paths.get("document_json", ""), "document")
    structure = _read_artifact(paths.get("structure_json", ""), "structure")
    draft = _read_artifact(paths.get("draft", ""), "draft")
    review = _read_artifact(paths.get("review", ""), "review")
    if document and structure and document.get("document_id") != structure.get("document_id"):
        raise ValueError("document and structure refer to different sources")
    if structure and draft and structure.get("document_id") != draft.get("document_id"):
        raise ValueError("structure and draft refer to different sources")
    source = structure or document or draft
    if not source:
        return {"loaded": False}
    units = [unit for unit in (structure or {}).get("units", []) if isinstance(unit, dict)]
    chosen_id = paths.get("unit_id") or (draft or {}).get("unit_id")
    unit = next((u for u in units if u.get("unit_id") == chosen_id), None)
    if unit is None and units:
        unit = units[0]
    if unit:
        source_text = unit.get("text", "")
    elif document:
        pages = document.get("pages", [])
        first = pages[0] if pages else {}
        source_text = first.get("source_text") or "\n".join(
            segment.get("text", "") for segment in first.get("segments", []))
    else:
        source_text = ""
    matching_draft = None
    if unit and draft and draft.get("unit_id") == unit.get("unit_id"):
        expected = hashlib.sha256(unit.get("text", "").encode("utf-8")).hexdigest()
        if draft.get("source_text_hash") == expected:
            matching_draft = draft
    return {
        "loaded": True,
        "title": _title(source.get("source_uri", "")),
        "language": source.get("language") or source.get("source_language") or "",
        "document_id": source.get("document_id", ""),
        "source_text": source_text[:20000],
        "translation_text": (matching_draft or {}).get("draft_text") or "",
        "translation_status": (matching_draft or {}).get("status") or "not_started",
        "review_status": (review or {}).get("status") or "not_started",
        "source_status": (structure or document or {}).get("status") or
                         ("resolved" if unit else "needs_human"),
        "units": [{"unit_id": u.get("unit_id", ""), "page_number": u.get("page_number", "")}
                  for u in units[:500]],
        "unit_id": unit.get("unit_id", "") if unit else "",
        "page_count": len((document or {}).get("pages", [])),
    }


def local_library() -> list[dict]:
    entries = []
    for path in (OUTPUT_ROOT).glob("**/document.json"):
        if len(entries) >= 50:
            break
        try:
            document = _read_artifact(str(path), "document")
            entries.append({"path": str(path), "title": _title(document.get("source_uri", "")),
                            "language": document.get("language", ""),
                            "pages": len(document.get("pages", [])), "modified": path.stat().st_mtime})
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return sorted(entries, key=lambda item: item["modified"], reverse=True)


MAX_LIBRARY_DOCUMENTS = 200


def _document_library(document_jobs) -> list[dict]:
    """Completed document jobs, newest first, without source text or local
    paths. Unreadable or corrupt job folders are skipped, never fatal."""
    stamped = []
    try:
        candidates = list(document_jobs.root.glob("*/job.json"))
    except OSError:
        return []
    for candidate in candidates:
        try:
            stamped.append((candidate.stat().st_mtime, candidate))
        except OSError:
            continue
    stamped.sort(key=lambda item: item[0], reverse=True)
    documents = []
    for mtime, candidate in stamped:
        if len(documents) >= MAX_LIBRARY_DOCUMENTS:
            break
        try:
            job = document_jobs.get(candidate.parent.name)
            if not isinstance(job, dict) or job.get("status") != "completed":
                continue
            source_kind = job.get("source_kind", "pdf")
            units = job.get("units")
            filename = job.get("filename")
            if source_kind not in ("pdf", "epub") or not isinstance(units, list) or not units:
                continue
            if not isinstance(filename, str) or not Path(filename).name:
                continue
            settings = job.get("settings") if isinstance(job.get("settings"), dict) else {}
            font_id = settings.get("font_id")
            completed_at = job.get("completed_at")
            if isinstance(completed_at, bool) or not isinstance(completed_at, (int, float)):
                completed_at = mtime
            documents.append({
                "job_id": candidate.parent.name,
                "filename": Path(filename).name,
                "source_kind": source_kind,
                "completed_at": float(completed_at),
                "unit_count": len(units),
                "font_id": font_id if isinstance(font_id, str) else None,
                "formats": [source_kind, "html"],
            })
        except (ValueError, TypeError, KeyError, AttributeError, OSError):
            continue
    documents.sort(key=lambda item: item["completed_at"], reverse=True)
    return documents


def _document_in_progress(document_jobs) -> list[dict]:
    """Unfinished automation jobs with saved work, newest first: progress, spend
    and the current block (if any). No source text or local paths."""
    try:
        stamped = sorted(((c.stat().st_mtime, c) for c in document_jobs.root.glob("*/job.json")), reverse=True)
    except OSError:
        return []
    documents = []
    for mtime, candidate in stamped:
        if len(documents) >= MAX_LIBRARY_DOCUMENTS:
            break
        try:
            job = document_jobs.get(candidate.parent.name)
            settings = job.get("settings") if isinstance(job.get("settings"), dict) else {}
            if job.get("status") == "completed" or not settings.get("automation") or not job.get("structure"):
                continue
            source_kind = job.get("source_kind", "pdf")
            units = job.get("units") if isinstance(job.get("units"), list) else []
            progress = job.get("progress") if isinstance(job.get("progress"), dict) else {}
            blocker = document_jobs.blocker(job["job_id"], job)
            budget = job.get("budget_status") or {}
            documents.append({
                "job_id": job["job_id"], "filename": Path(job.get("filename") or "document").name,
                "source_kind": source_kind, "status": job.get("status"), "updated_at": mtime,
                "error": None if blocker else job.get("error"),
                "translated_units": len(units), "total_units": len(job["structure"].get("units", [])),
                "completed_chapters": progress.get("completed_chapters"), "total_chapters": progress.get("total_chapters"),
                "spent_usd": budget.get("list_estimated_spent_usd"), "budget_usd": settings.get("budget_usd"),
                "blocker": {"kind": blocker["kind"], "message": blocker["message"]} if blocker else None,
                "formats": [source_kind, "html"] if units else [],
            })
        except (ValueError, TypeError, KeyError, AttributeError, OSError):
            continue
    return documents


def make_handler(token: str, model_config_path: str | None = None, *, learning_service=None, key_store=None):
    from .document_draft import (
        DocumentDraftError, DocumentJobs, MAX_FILE_BYTES, MODEL_CHOICES, QUALITY_MODES, render_download, validate_settings,
    )
    from . import chapter_pipeline
    from .export_common import list_pdf_fonts
    from .model_adapter import build_translation_adapter
    from .model_config import ModelConfiguration
    from .translation_profiles import SUPPORTED_PROFILE_IDS

    server_model_config = None
    if model_config_path:
        server_model_config = json.loads(Path(model_config_path).read_text(encoding="utf-8"))
        ModelConfiguration.from_dict(server_model_config)  # fail fast on an invalid deployment file

    session_settings = {"api_key": None}
    # Provider API keys for the multi-provider UI flow, keyed by provider_id.
    # Never written to os.environ, project/job files, logs or any HTTP
    # response. Memory-only unless the user ticks "remember": then key_store
    # (Windows Credential Manager) keeps them for later server runs.
    session_keys: dict[str, str] = {}
    saved_key_ids: set[str] = set()
    if key_store is not None:
        try:
            stored = {pid: key for pid, key in key_store.load_all().items()
                      if _PROVIDER_ID_RE.fullmatch(pid) and key.strip() and "\n" not in key and "\r" not in key}
        except OSError:
            stored = {}
        session_keys.update({pid: key.strip() for pid, key in stored.items()})
        saved_key_ids.update(stored)
    session_outputs: set[Path] = set()
    settings_lock = threading.Lock()
    user_glossary_path = OUTPUT_ROOT / "user_glossary.json"
    document_jobs = DocumentJobs(OUTPUT_ROOT, user_glossary_path=user_glossary_path)
    learning_holder = [learning_service]
    learning_lock = threading.Lock()

    def _learning():
        with learning_lock:
            if learning_holder[0] is None:
                from .learning_service import LearningService
                learning_holder[0] = LearningService(OUTPUT_ROOT.parent / "learning")
            return learning_holder[0]

    def _learning_adapter():
        from .learning_contracts import require
        configuration = model_settings.build_configuration({"translator": {
            "source": "catalog", "provider": "openai", "model": "gpt-6-luna"}})
        keys = _key_snapshot(configuration)
        require(bool(keys.get("openai")), "missing_api_key")
        return configuration, _adapter_factory_for(configuration, keys)

    def _learning_action(path, data):
        from .learning_contracts import require
        service = _learning()
        if path == "/learning/state":
            return service.summary()
        if path == "/learning/language":
            return service.select_language(data.get("language"))
        if path == "/learning/import-translation":
            snapshot = document_jobs.get(data.get("job_id", ""))
            # Validate completed Hebrew content before opening the saved source.
            from .learning_import import import_translation_job
            import_translation_job(snapshot)
            template = None
            if snapshot.get('source_kind') == 'epub':
                try:
                    original = document_jobs.source_path(snapshot['job_id'], 'epub')
                    template = render_download(snapshot, 'epub', source_path=original)
                except (DocumentDraftError, OSError, ValueError):
                    # Legacy/missing original: import remains useful as text;
                    # book metadata and export UI report the missing layout.
                    template = None
            return service.import_translation(snapshot, epub_template=template)
        if path == "/learning/effort":
            return service.set_effort(data.get("level_id"))
        if path == "/learning/prepare":
            configuration, factory = _learning_adapter()
            return service.start(data.get("book_id"), data.get("budget_usd"), configuration, factory,
                                 context_chars=data.get('context_chars', 4000), output_tokens=data.get('output_tokens', 6000))
        if path == "/learning/resume":
            _configuration, factory = _learning_adapter()
            return service.resume(data.get("session_id"), factory, budget_usd=data.get("budget_usd"),
                                  context_chars=data.get('context_chars'), output_tokens=data.get('output_tokens'),
                                  retry=data.get('retry', False))
        if path == "/learning/pause":
            return service.pause(data.get("session_id"))
        if path == "/learning/abandon":
            return service.abandon(data.get("session_id"))
        if path == "/learning/read":
            return service.reader(data.get("session_id"), data.get("chapter_index", 0),
                                  gloss_on_click=data.get("gloss_on_click", False))
        if path == "/learning/cursor":
            return service.cursor(data.get("session_id"), data.get("chapter_index"))
        if path == "/learning/complete":
            return service.complete(data.get("session_id"), data.get("prepared_hash"), data.get("completion_id"))
        if path == "/learning/grammar-notebook":
            return service.grammar_notebook()
        require(False, "unknown_action")

    def _environment_key(definition):
        # Only standard native endpoints or the locally supplied deployment
        # file can authorize reading an environment credential. A submitted
        # custom endpoint cannot borrow an unrelated environment secret.
        trusted = (definition.base_url is None and
                   definition.provider_type in ("openai", "anthropic") and
                   definition.credential_env == {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}[definition.provider_type])
        if server_model_config:
            trusted = trusted or server_model_config["providers"].get(definition.provider_id) == definition.to_dict()
        return os.environ.get(definition.credential_env) if trusted and definition.credential_env else None

    def _key_snapshot(configuration):
        with settings_lock:
            result = dict(session_keys)
        for pid, definition in configuration.providers.items():
            trusted_deployment = bool(server_model_config and server_model_config["providers"].get(pid) == definition.to_dict())
            if definition.base_url and not trusted_deployment and pid != model_settings.endpoint_provider_id(definition.provider_type, definition.base_url):
                result.pop(pid, None)
            if not result.get(pid):
                result[pid] = _environment_key(definition)
        return result

    def _requirements(configuration, settings):
        snapshot = _key_snapshot(configuration)
        return [{"id": definition.provider_id, "type": definition.provider_type,
                 "endpoint": definition.base_url, "key_available": bool(snapshot.get(definition.provider_id))}
                for definition in {definition.provider_id: definition for _, definition in
                    _required_roles_for(configuration, settings).values() if definition.provider_type != "mock"}.values()]

    def _required_roles_for(configuration, settings):
        # Both the automation chapter pipeline and the legacy per-unit
        # configured path dispatch real semantic_reviewer/chapter_qa calls
        # whenever quality != "fast" (document_draft._run_configured_mode
        # resolves and calls them too, not only chapter_pipeline); gate on
        # quality the same way in both modes so preflight never under-covers
        # a required provider credential.
        return chapter_pipeline._resolve_required_roles(configuration, settings["quality"])

    def _missing_credential_providers(configuration, settings, keys_snapshot=None):
        keys_snapshot = _key_snapshot(configuration) if keys_snapshot is None else keys_snapshot
        missing = set()
        for _role, (selection, definition) in _required_roles_for(configuration, settings).items():
            if definition.provider_type != "mock" and not keys_snapshot.get(definition.provider_id):
                missing.add(definition.provider_id)
        return sorted(missing)

    def _preflight_credentials(configuration, settings):
        keys_snapshot = _key_snapshot(configuration)
        missing = _missing_credential_providers(configuration, settings, keys_snapshot)
        if missing:
            raise DocumentDraftError(
                "יש לשמור מפתח API עבור: " + ", ".join(missing) + " לפני התחלת עבודה אמיתית."
            )
        return keys_snapshot

    def _adapter_factory_for(configuration, keys_snapshot):

        def adapter_factory(role, request):
            selection, definition = configuration.resolve(role)
            if definition.provider_type != "mock" and not keys_snapshot.get(definition.provider_id):
                raise DocumentDraftError("מפתח הספק אינו זמין לעבודה זו; הזינו אותו לפני המשך.")
            max_output_tokens = getattr(request, "max_output_tokens", None)
            if max_output_tokens is None:
                max_output_tokens = selection.capabilities.max_output_tokens if selection.capabilities else None
            return build_translation_adapter(
                selection.provider, selection.model, provider_definition=definition,
                max_output_tokens=max_output_tokens, api_key=keys_snapshot.get(definition.provider_id),
            )
        return adapter_factory

    def _resolve_model_config(settings):
        """Build settings['model_config'] from the new per-role UI selections
        (settings['role_selections']) when present, else keep the legacy
        single-file server_model_config/model_config path unchanged."""
        if settings.get("model") != "configured" or settings.get("model_config") is not None:
            return settings
        role_selections = settings.get("role_selections")
        if role_selections is not None:
            try:
                configuration = model_settings.build_configuration(role_selections)
            except ModelSettingsError as exc:
                raise DocumentDraftError(str(exc)) from None
            settings = dict(settings)
            settings["model_config"] = configuration.to_dict()
            return settings
        if server_model_config is None:
            raise DocumentDraftError("לא הוגדר קובץ תצורת מודל בשרת.")
        settings = dict(settings)
        settings["model_config"] = server_model_config
        return settings

    def _validated_settings(settings):
        if not isinstance(settings, dict) or set(settings) - {
            "profile", "quality", "language", "budget_usd", "model", "model_config",
            "automation", "font_id", "role_selections", "use_server_config", "ocr_review", "target_language"}:
            raise DocumentDraftError("הגדרות המסמך אינן תקינות.")
        try:
            resolved = _resolve_model_config(dict(settings))
            if resolved.get("model") == "configured":
                resolved["automation"] = True
                resolved.setdefault("quality", "checked")
            return validate_settings(resolved)
        except (ValueError, TypeError, KeyError):
            raise DocumentDraftError("הגדרות המודל או המסמך אינן תקינות; בדקו מזהה, מגבלות, תעריפים וכתובת ספק.") from None

    def decision_file(data: dict, key: str) -> tuple[str, dict]:
        path = data.get(key, "")
        if not isinstance(path, str) or not path:
            raise ValueError(f"{key} is required")
        loaded = _read_artifact(path, "structure" if key == "structure_json" else "glossary")
        return str(Path(path).resolve()), loaded

    def action_dir(prefix: str) -> Path:
        path = OUTPUT_ROOT / f"{prefix}-{secrets.token_hex(10)}"
        path.mkdir(parents=True, exist_ok=False)
        return path

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            pass

        def _reply(self, status: int, body: bytes, content_type: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, value: dict) -> None:
            self._reply(status, json.dumps(value, ensure_ascii=False).encode("utf-8"))

        def do_GET(self) -> None:
            if urlparse(self.path).path == "/learning/wordlist":
                language = parse_qs(urlparse(self.path).query).get('language', [''])[0]
                if language not in ('fr', 'de', 'es', 'yi', 'it'):
                    self._json(404, {"error": "not found"})
                    return
                self._reply(200, (ROOT / 'prompts' / 'language_learning' / 'wordlists' / (language + '_500.md')).read_bytes(), 'text/plain')
                return
            if urlparse(self.path).path == '/learning/help':
                self._reply(200, (UI_DIR / 'learning_help.html').read_bytes(), 'text/html')
                return
            if self.path in ("/learning.js", "/learning.css"):
                name = self.path.removeprefix("/")
                self._reply(200, (UI_DIR / name).read_bytes(), "text/javascript" if name.endswith(".js") else "text/css")
                return
            if urlparse(self.path).path == "/learning":
                config = json.dumps({"token": token}, ensure_ascii=False)
                self._reply(200, (UI_DIR / "learning.html").read_text(encoding="utf-8").replace("__CONFIG__", config).encode("utf-8"), "text/html")
                return
            if self.path == "/help":
                try:
                    rows = "".join(
                        "<tr><td>{provider}</td><td dir=\"ltr\">{model}</td>"
                        "<td dir=\"ltr\">{inp:g}</td><td dir=\"ltr\">{out:g}</td>"
                        "<td dir=\"ltr\">{cached:g}</td><td dir=\"ltr\">{write:g}</td><td dir=\"ltr\">{write1h}</td></tr>".format(
                            provider=entry["provider"], model=entry["model"],
                            inp=entry["rates_per_million"]["input"], out=entry["rates_per_million"]["output"],
                            cached=entry["rates_per_million"].get("cached", entry["rates_per_million"]["input"]),
                            write=entry["rates_per_million"].get("cache_write", entry["rates_per_million"]["input"]),
                            write1h=(f"{entry['rates_per_million']['cache_write_1h']:g}" if "cache_write_1h" in entry["rates_per_million"] else "—"),
                        )
                        for entry in model_settings.catalogue()
                    )
                    from .model_catalog import CATALOG_VERSION
                    fonts_rows = "".join(
                        f"<li><strong>{f['name']}</strong> — {f['license']}"
                        + (f" ({f['embedding_note']})" if f.get("embedding_note") else "") + "</li>"
                        for f in list_pdf_fonts()
                    )
                    html = (UI_DIR / "help.html").read_text(encoding="utf-8")
                    html = (html.replace("__PRICING_ROWS__", rows)
                                .replace("__CATALOG_VERSION__", CATALOG_VERSION)
                                .replace("__FONT_LIST__", fonts_rows))
                except OSError:
                    self._json(404, {"error": "not found"})
                    return
                self._reply(200, html.encode("utf-8"), "text/html")
                return
            if self.path in ("/ui.css", "/ui.js"):
                name = self.path.removeprefix("/")
                kind = "text/css" if name.endswith(".css") else "text/javascript"
                self._reply(200, (UI_DIR / name).read_bytes(), kind)
                return
            if self.path == "/book-sprite.svg":
                self._reply(200, (UI_DIR / "assets" / "book-sprite.svg").read_bytes(), "image/svg+xml")
                return
            if self.path != "/":
                self._json(404, {"error": "not found"})
                return
            config = json.dumps({"token": token}, ensure_ascii=False)
            html = (UI_DIR / "ui.html").read_text(encoding="utf-8").replace("__CONFIG__", config)
            self._reply(200, html.encode("utf-8"), "text/html")

        def do_POST(self) -> None:
            origin = self.headers.get("Origin")
            expected = f"http://127.0.0.1:{self.server.server_port}"
            if self.headers.get("X-UI-Token") != token or (origin and origin != expected):
                # Unread small request bodies can reset a Windows socket
                # before the client receives the intended rejection response.
                try:
                    rejected_length = int(self.headers.get('Content-Length', '0'))
                    if 0 < rejected_length <= 65536:
                        self.connection.settimeout(2)
                        self.rfile.read(rejected_length)
                except (ValueError, OSError):
                    pass
                self._json(403, {"error": "request refused"})
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if length < 0 or length > MAX_UPLOAD:
                self._json(413, {"error": "invalid or oversized request"})
                return
            route = urlparse(self.path)
            if route.path == "/learning/upload-epub":
                from .learning_contracts import LearningError
                if length > MAX_FILE_BYTES:
                    self._json(413, {"error": "הקובץ גדול מדי.", "code": "oversized_epub"})
                    return
                try:
                    name = parse_qs(route.query).get("name", [""])[0]
                    if not name.lower().endswith(".epub"):
                        raise LearningError("unsupported_format")
                    content = self.rfile.read(length)
                    if len(content) != length:
                        raise LearningError("incomplete_upload")
                    self._json(200, _learning().import_epub(content))
                except (LearningError, ValueError, OSError):
                    self._json(400, {"error": "לא ניתן לקלוט את הספר. בדקו שזה EPUB בעברית ללא הגנה.", "code": "epub_import_failed"})
                return
            if route.path == "/upload":
                name = Path(parse_qs(route.query).get("name", [""])[0]).name
                if not name or name in (".", ".."):
                    self._json(400, {"error": "invalid filename"})
                    return
                destination = OUTPUT_ROOT / "uploads" / secrets.token_hex(10) / name
                destination.parent.mkdir(parents=True, exist_ok=False)
                with destination.open("xb") as handle:
                    remaining = length
                    while remaining:
                        chunk = self.rfile.read(min(65536, remaining))
                        if not chunk:
                            raise ConnectionError("incomplete upload")
                        handle.write(chunk)
                        remaining -= len(chunk)
                self._json(200, {"path": str(destination)})
                return
            if length > 65536:
                self._json(413, {"error": "request too large"})
                return
            try:
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("invalid request")
                if route.path.startswith("/learning/"):
                    from .learning_contracts import LearningError
                    try:
                        if route.path == '/learning/export':
                            result = _learning().export_book(data.get('session_id'),
                                format=data.get('format', 'epub'), include_meanings=data.get('include_meanings', True),
                                preserve_layout=data.get('preserve_layout', True))
                            self.send_response(200)
                            self.send_header('Content-Type', result['media_type'])
                            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(result['filename']))
                            self.send_header('Content-Length', str(len(result['body'])))
                            self.send_header('Cache-Control', 'no-store')
                            self.send_header('X-Content-Type-Options', 'nosniff')
                            self.send_header('X-Learning-Export-Warnings', ','.join(result['warnings']))
                            self.end_headers()
                            self.wfile.write(result['body'])
                        else:
                            self._json(200, _learning_action(route.path, data))
                    except LearningError as exc:
                        self._json(400, {"error": "פעולת הלמידה לא הושלמה.", "code": exc.code})
                    except (ValueError, TypeError, KeyError, OSError):
                        self._json(400, {"error": "פעולת הלמידה לא הושלמה.", "code": "invalid_learning_request"})
                    return
                if route.path == "/document-config":
                    translator_label = None
                    if server_model_config is not None:
                        translator = server_model_config.get("models", {}).get("translator", {})
                        translator_label = f"{translator.get('provider')}/{translator.get('model')}"
                    with settings_lock:
                        available_keys = {pid: True for pid in session_keys}
                        entered_ids = set(session_keys)
                    for pid, env in (("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY")):
                        if os.environ.get(env):
                            available_keys[pid] = True
                    configured_requirements = []
                    if server_model_config:
                        configuration = ModelConfiguration.from_dict(server_model_config)
                        configured_requirements = [{"id": pid, "type": definition.provider_type,
                            "endpoint": definition.base_url, "key_available": bool(_key_snapshot(configuration).get(pid))}
                            for pid, definition in configuration.providers.items() if definition.provider_type != "mock"]
                    self._json(200, {
                        "profiles": [{"id": pid} for pid in SUPPORTED_PROFILE_IDS],
                        "qualities": [{"id": q} for q in sorted(QUALITY_MODES)],
                        "model_choices": sorted(MODEL_CHOICES),
                        "model_config_available": server_model_config is not None,
                        "configured_translator_model": translator_label,
                        "max_file_bytes": MAX_FILE_BYTES,
                        "model_catalog": model_settings.catalogue(),
                        "pdf_fonts": list_pdf_fonts(),
                        "qa_roles": ["semantic_reviewer", "chapter_qa"],
                        "key_providers_available": available_keys,
                        "key_providers_saved": {pid: True for pid in sorted(saved_key_ids)},
                        # Keys that come from outside the UI (environment / server configuration).
                        "key_providers_external": {pid: True for pid in sorted(available_keys) if pid not in entered_ids},
                        "key_remember_supported": key_store is not None,
                        "configured_requirements": configured_requirements,
                    })
                elif route.path == "/document-translate":
                    source = Path(data.get("path", "")).resolve()
                    if not source.is_relative_to((OUTPUT_ROOT / "uploads").resolve()) or not source.is_file():
                        raise DocumentDraftError("בחרו קובץ שהועלה דרך הממשק.")
                    if source.suffix.lower() not in (".pdf", ".epub") or not 0 < source.stat().st_size <= MAX_FILE_BYTES:
                        raise DocumentDraftError("בחרו קובץ PDF או EPUB עד 25 MB.")
                    settings = data.get("settings")
                    if not isinstance(settings, dict):
                        raise DocumentDraftError("הגדרות המסמך חסרות.")
                    settings = _validated_settings(settings)
                    adapter_factory = None
                    if settings.get("model") == "configured":
                        configuration = ModelConfiguration.from_dict(settings["model_config"])
                        keys_snapshot = _preflight_credentials(configuration, settings)
                        adapter_factory = _adapter_factory_for(configuration, keys_snapshot)
                    self._json(200, document_jobs.start(source, settings, paid_confirm=data.get("paid_confirm"),
                                                         adapter_factory=adapter_factory))
                elif route.path in ("/user-glossary", "/user-glossary-save"):
                    target = data.get("target_language", target_languages.DEFAULT)
                    if target not in target_languages.available():
                        raise DocumentDraftError("שפת היעד אינה נתמכת.")
                    try:
                        with settings_lock:
                            terms = user_glossary.load(user_glossary_path)
                            if route.path == "/user-glossary-save":
                                mine = user_glossary.parse_text(data.get("text", ""), target)
                                terms = user_glossary.save(user_glossary_path, [
                                    t for t in terms if t["target_language"] != target] + mine)
                    except user_glossary.UserGlossaryError as exc:
                        raise DocumentDraftError(str(exc)) from None
                    mine = user_glossary.for_target(terms, target)
                    self._json(200, {"text": user_glossary.format_text(mine), "count": len(mine)})
                elif route.path == "/document-job":
                    job = document_jobs.get(data.get("job_id"))
                    job["blocker"] = document_jobs.blocker(job["job_id"], job)
                    job["recheck_candidates"] = sum(review_salvage.candidates(job))
                    job["cross_review_available"] = chapter_pipeline.cross_review_available(job)
                    self._json(200, job)
                elif route.path == "/document-recheck-reviews":
                    self._json(200, document_jobs.recheck_saved_reviews(data.get("job_id")))
                elif route.path == "/document-cross-review":
                    self._json(200, document_jobs.cross_chapter_review(data.get("job_id")))
                elif route.path == "/document-decide":
                    value = data.get("value")
                    if value is not None and (type(value) not in (int, float) or isinstance(value, bool)):
                        raise DocumentDraftError("ערך ההחלטה אינו תקין.")
                    self._json(200, document_jobs.decide(data.get("job_id"), data.get("option"), value))
                elif route.path == "/document-delete":
                    if data.get("confirm") is not True:
                        raise DocumentDraftError("המחיקה דורשת אישור.")
                    self._json(200, document_jobs.delete(data.get("job_id")))
                elif route.path == "/document-in-progress":
                    self._json(200, {"documents": _document_in_progress(document_jobs)})
                elif route.path == "/document-pause":
                    self._json(200, document_jobs.pause(data.get("job_id")))
                elif route.path == "/document-resume":
                    job = document_jobs.get(data.get("job_id"))
                    adapter_factory = None
                    if job["status"] != "completed" and job["settings"].get("model") == "configured":
                        configuration = ModelConfiguration.from_dict(job["settings"]["model_config"])
                        keys_snapshot = _preflight_credentials(configuration, job["settings"])
                        adapter_factory = _adapter_factory_for(configuration, keys_snapshot)
                    self._json(200, document_jobs.resume(data.get("job_id"), adapter_factory=adapter_factory))
                elif route.path == "/model-keys":
                    keys = data.get("keys")
                    remember = data.get("remember")
                    if remember is not None and not isinstance(remember, bool):
                        raise ValueError("בקשת מפתחות אינה תקינה.")
                    if data.get("forget_saved") is True and key_store is not None:
                        with settings_lock:
                            for provider_id in sorted(saved_key_ids):
                                key_store.delete(provider_id)
                                saved_key_ids.discard(provider_id)
                    if keys is not None:
                        if not isinstance(keys, dict):
                            raise ValueError("בקשת מפתחות אינה תקינה.")
                        removals, updates = [], {}
                        for provider_id, value in keys.items():
                            if (not isinstance(provider_id, str) or not _PROVIDER_ID_RE.fullmatch(provider_id)
                                    or provider_id.startswith('sk-')):
                                raise ValueError("בקשת מפתחות אינה תקינה.")
                            if value is None or value == "":
                                removals.append(provider_id)
                                continue
                            if not isinstance(value, str) or len(value) > 4096 or "\n" in value or "\r" in value:
                                raise ValueError("מפתח API אינו תקין.")
                            stripped = value.strip()
                            if not stripped:
                                raise ValueError("מפתח API אינו תקין.")
                            updates[provider_id] = stripped
                        with settings_lock:
                            if key_store is not None:
                                # A replaced or cleared key never lingers in the
                                # store; it is saved only when asked to remember.
                                for provider_id in removals + list(updates):
                                    if remember is True and provider_id in updates:
                                        key_store.save(provider_id, updates[provider_id])
                                        saved_key_ids.add(provider_id)
                                    elif provider_id in saved_key_ids:
                                        key_store.delete(provider_id)
                                        saved_key_ids.discard(provider_id)
                            for provider_id in removals:
                                session_keys.pop(provider_id, None)
                            session_keys.update(updates)
                    with settings_lock:
                        available = {pid: True for pid in session_keys}
                        entered_ids = set(session_keys)
                        saved = {pid: True for pid in sorted(saved_key_ids)}
                    for pid, env in (("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY")):
                        if os.environ.get(env):
                            available[pid] = True
                    if server_model_config:
                        available.update({pid: True for pid, key in _key_snapshot(ModelConfiguration.from_dict(server_model_config)).items() if key})
                    self._json(200, {"available": available, "saved": saved,
                                     "external": {pid: True for pid in sorted(available) if pid not in entered_ids},
                                     "remember_supported": key_store is not None})
                elif route.path == "/document-preview":
                    source = Path(data.get("path", "")).resolve()
                    if not source.is_relative_to((OUTPUT_ROOT / "uploads").resolve()) or not source.is_file():
                        raise DocumentDraftError("בחרו קובץ שהועלה דרך הממשק.")
                    if source.suffix.lower() not in (".pdf", ".epub") or not 0 < source.stat().st_size <= MAX_FILE_BYTES:
                        raise DocumentDraftError("בחרו קובץ PDF או EPUB עד 25 MB.")
                    settings = data.get("settings")
                    if not isinstance(settings, dict):
                        raise DocumentDraftError("הגדרות המסמך חסרות.")
                    settings = _validated_settings(settings)
                    preview = document_jobs.preview(source, settings)
                    configuration = ModelConfiguration.from_dict(settings["model_config"])
                    preview["required_providers"] = _requirements(configuration, settings)
                    from .model_catalog import CATALOG_VERSION
                    preview["catalog_version"] = CATALOG_VERSION
                    self._json(200, preview)
                elif route.path == "/document-models":
                    settings = _validated_settings(data.get("settings"))
                    if settings["model"] != "configured":
                        self._json(200, {"required_providers": []})
                    else:
                        configuration = ModelConfiguration.from_dict(settings["model_config"])
                        self._json(200, {"required_providers": _requirements(configuration, settings)})
                elif route.path == "/document-recent":
                    candidates = sorted(document_jobs.root.glob("*/job.json"), key=lambda path: path.stat().st_mtime, reverse=True)
                    recent = None
                    for candidate in candidates[:10]:
                        try:
                            job = document_jobs.get(candidate.parent.name)
                            recent = {"job_id": job["job_id"], "filename": job["filename"], "status": job["status"]}
                            break
                        except (ValueError, OSError):
                            continue
                    self._json(200, {"job": recent})
                elif route.path == "/document-library":
                    self._json(200, {"documents": _document_library(document_jobs)})
                elif route.path == "/document-review":
                    self._json(200, document_jobs.review(data.get("job_id"), data.get("unit_index"),
                               data.get("target_text"), data.get("expected_revision")))
                elif route.path == "/document-download":
                    job = document_jobs.get(data.get("job_id"))
                    partial = data.get("partial") is True
                    if job["status"] != "completed" and not partial:
                        raise DocumentDraftError("עדיין אין תוצאה להורדה.")
                    source_kind = job.get("source_kind", "pdf")
                    requested = data.get("format")
                    if requested is None or requested == source_kind:
                        kind = source_kind
                    elif requested == "html":
                        kind = "html"
                    else:
                        raise DocumentDraftError("פורמט ההורדה אינו נתמך.")
                    font_id = data.get("font_id")
                    if font_id is not None:
                        if kind == "epub" or not isinstance(font_id, str) or font_id not in {
                            f["id"] for f in list_pdf_fonts() if f["available"]
                        }:
                            raise DocumentDraftError("בחרו פונט PDF זמין מהרשימה.")
                    source_path = document_jobs.source_path(job["job_id"], "epub") if kind == "epub" else None
                    body = render_download(job, kind, source_path=source_path, font_id=font_id, partial=partial)
                    content_type = {"epub": "application/epub+zip", "html": "text/html; charset=utf-8"}.get(kind, "application/pdf")
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(Path(job["filename"]).stem + (".he.partial" if partial else ".he") + f".{kind}"))
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    self.wfile.write(body)
                elif route.path == "/document-notebook":
                    try:
                        job = document_jobs.get(data.get("job_id"))
                    except DocumentDraftError:
                        job = None
                    notebook = job.get("book_notebook") if job else None
                    if not notebook:
                        self._json(404, {"error": "notebook not found"})
                        return
                    from .book_notebook import render_markdown
                    from .name_table import render_markdown as render_names_markdown
                    names = render_names_markdown(job.get("name_table"))
                    body = (render_markdown(notebook).rstrip("\n") + "\n\n" + names if names
                            else render_markdown(notebook)).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/markdown; charset=utf-8")
                    self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(Path(job["filename"]).stem + ".notebook.md"))
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    self.wfile.write(body)
                elif route.path == "/document-sample":
                    from reportlab.pdfgen import canvas as _rl_canvas
                    destination = OUTPUT_ROOT / "uploads" / secrets.token_hex(10) / "sample.pdf"
                    destination.parent.mkdir(parents=True, exist_ok=False)
                    pdf = _rl_canvas.Canvas(str(destination))
                    pdf.drawString(72, 700, "A short sample")
                    pdf.drawString(72, 680, "Some scholars do not accept the claim. The document contains 3 arguments.")
                    pdf.showPage()
                    pdf.save()
                    self._json(200, {"path": str(destination), "name": destination.name, "size": destination.stat().st_size})
                elif route.path == "/run":
                    command = data.get("command")
                    step = next((s for s in STEPS if s.command == command), None)
                    if step is None or not isinstance(data.get("values"), dict):
                        raise ValueError("unknown step")
                    values = data["values"]
                    if not isinstance(data.get("output"), str) or any(
                        not isinstance(value, str) for value in values.values()
                    ):
                        raise ValueError("invalid step values")
                    if values.get("provider") == "openai" and data.get("paid_confirm") is not True:
                        raise ValueError("paid provider requires confirmation")
                    argv = build_command(step, values, data.get("output", ""))
                    environment = os.environ.copy()
                    with settings_lock:
                        if session_settings["api_key"]:
                            environment["OPENAI_API_KEY"] = session_settings["api_key"]
                    result = subprocess.run(argv, cwd=ROOT, env=environment, capture_output=True,
                                            text=True, encoding="utf-8", errors="replace", timeout=1800)
                    if result.returncode == 0 and data.get("output"):
                        with settings_lock:
                            session_outputs.add(Path(data["output"]).resolve())
                    self._json(200, {"code": result.returncode,
                                     "stdout": result.stdout[-40000:], "stderr": result.stderr[-40000:]})
                elif route.path == "/settings":
                    key = data.get("api_key")
                    if key is not None and (not isinstance(key, str) or len(key) > 4096 or "\n" in key):
                        raise ValueError("invalid API key")
                    with settings_lock:
                        if key is not None:
                            session_settings["api_key"] = key.strip() or None
                            if key.strip():
                                session_keys["openai"] = key.strip()
                            else:
                                session_keys.pop("openai", None)
                        available = bool(session_settings["api_key"] or os.environ.get("OPENAI_API_KEY"))
                    self._json(200, {"api_key_available": available})
                elif route.path == "/preview":
                    self._json(200, preview_artifacts(data))
                elif route.path == "/library":
                    self._json(200, {"documents": local_library()})
                elif route.path == "/source-options":
                    _, structure = decision_file(data, "structure_json")
                    self._json(200, source_options(structure))
                elif route.path == "/source-decide":
                    structure_path, structure = decision_file(data, "structure_json")
                    document_path, _ = decision_file(data, "document_json")
                    decisions = source_decisions(structure, data)
                    ocr_path = data.get("ocr", "")
                    if ocr_path:
                        if not isinstance(ocr_path, str):
                            raise ValueError("invalid OCR path")
                        _read_artifact(ocr_path, "ocr")
                    directory = action_dir("source-choice")
                    action_path = directory / "decisions.json"
                    action_path.write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
                    target = directory / "structure.json"
                    argv = [sys.executable, "-B", "-m", "scholarly_translation", "structure",
                            document_path, "--output", str(target), "--decisions", str(action_path),
                            "--previous", structure_path]
                    if ocr_path:
                        argv.extend(["--ocr", ocr_path])
                    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                                            encoding="utf-8", errors="replace", timeout=1800)
                    if result.returncode:
                        raise UIDecisionError((result.stderr or "source resolution failed")[-500:])
                    self._json(200, {"structure_json": str(target), "decisions_json": str(action_path),
                                     "stdout": result.stdout[-1000:]})
                elif route.path == "/glossary-options":
                    structure_path, structure = decision_file(data, "structure_json")
                    from .glossary import new_store
                    glossary_path = data.get("glossary", "")
                    glossary = decision_file(data, "glossary")[1] if glossary_path else new_store()
                    self._json(200, glossary_options(structure, glossary))
                elif route.path == "/glossary-action":
                    structure_path, structure = decision_file(data, "structure_json")
                    from .glossary import new_store
                    glossary_path = data.get("glossary", "")
                    glossary = decision_file(data, "glossary")[1] if glossary_path else new_store()
                    action = glossary_action(structure, glossary, data)
                    directory = action_dir("term-action")
                    action_path = directory / "action.json"
                    action_path.write_text(json.dumps(action, ensure_ascii=False, indent=2), encoding="utf-8")
                    glossary_input = glossary_path or str(directory / "new_glossary.json")
                    argv = [sys.executable, "-B", "-m", "scholarly_translation", "terminology",
                            structure_path, "--glossary", glossary_input, "--action", str(action_path),
                            "--output", str(directory)]
                    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                                            encoding="utf-8", errors="replace", timeout=1800)
                    if result.returncode:
                        raise UIDecisionError((result.stderr or "terminology action failed")[-500:])
                    self._json(200, {"glossary": str(directory / "glossary.json"),
                                     "action_json": str(action_path), "stdout": result.stdout[-1000:]})
                elif route.path == "/open":
                    path = Path(data.get("path", "")).resolve()
                    with settings_lock:
                        allowed = path.is_relative_to((ROOT / "outputs").resolve()) or any(
                            path == directory or path.is_relative_to(directory)
                            for directory in session_outputs
                        )
                    if not path.exists() or not allowed:
                        raise ValueError("result is unavailable")
                    webbrowser.open(path.as_uri())
                    self._json(200, {"opened": True})
                else:
                    self._json(404, {"error": "not found"})
            except (ValueError, TypeError, OSError, subprocess.TimeoutExpired) as exc:
                self._json(400, {"error": str(exc)[:300]})

    return Handler


def main() -> int:
    token = secrets.token_urlsafe(24)
    model_config_path = os.environ.get("SCHOLARLY_TRANSLATION_MODEL_CONFIG")
    from .key_store import default_key_store
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(token, model_config_path, key_store=default_key_store()))
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Local UI: {url}", flush=True)
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
