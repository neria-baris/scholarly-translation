"""Local browser shell over the existing CLI. No runtime service beyond localhost."""

from __future__ import annotations

import dataclasses
import hashlib
import html as html_lib
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from urllib.parse import quote

from .gui import STEPS, build_command
from .ui_decisions import (
    UIDecisionError, glossary_action, glossary_options, source_decisions, source_options,
)
from ..models import settings as model_settings
from ..review import review_salvage
from ..core import target_languages
from ..translate import user_glossary
from ..models.settings import ModelSettingsError
from .. import app_paths
from ..account.google_auth import (
    AccountConfigError, GoogleAccount, GoogleClientConfig, SignedOut, SignInError, default_google_store,
)
from ..account.drive_library import (
    DriveError, DriveLibrary, DriveNetworkError, DriveQuotaError, SyncConflict, validate_job_id,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = app_paths.data_root() / "ui"
PENDING_SIGN_IN_SECONDS = 600


def _under_outputs(candidate: Path) -> bool:
    """True when the path is inside a dev checkout's outputs/ or the data root."""
    return any(candidate.is_relative_to(base.resolve()) for base in (ROOT / "outputs", app_paths.data_root()))


def ui_status() -> dict | None:
    """Updater status for the UI; None in a development checkout or on any error."""
    try:
        from ..update import updater
        return updater.ui_status()
    except Exception:
        return None


def set_auto_update(enabled: bool) -> None:
    from ..update import updater
    updater.set_auto_update(app_paths.data_root(), enabled)


def _default_account():
    """The production Google account object, or None when the feature is unavailable
    (no client id configured, or no credential store on this platform)."""
    try:
        config = GoogleClientConfig.load(config_path=ROOT / "account_config.json")
    except AccountConfigError:
        return None
    store = default_google_store()
    if store is None:
        return None
    return GoogleAccount(config, store)


_SIGN_IN_PAGE = """<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="referrer" content="no-referrer">
<title>{title}</title><style>body{{font-family:"Segoe UI",Arial,sans-serif;background:#f6f0e1;color:#342c19;margin:0;
display:grid;place-items:center;min-height:100vh}}main{{background:#fff;border:1px solid #e9e6de;border-radius:12px;
padding:28px 32px;max-width:420px;margin:16px;text-align:center}}h1{{font-size:20px;margin:0 0 10px}}
p{{margin:6px 0;line-height:1.6}}.en{{color:#6b6352;direction:ltr}}</style></head><body><main>
<h1>{he_title}</h1><p>{he_text}</p><p class="en">{en_title} {en_text}</p></main></body></html>"""


def _sign_in_page(ok: bool, detail: str = "") -> bytes:
    esc = html_lib.escape
    if ok:
        he_title, en_title = "ההתחברות הושלמה", "Signed in."
        he_text = "אפשר לסגור את הלשונית ולחזור ליישום." + (f" ({esc(detail)})" if detail else "")
        en_text = "You can close this tab and return to the app."
    else:
        he_title, en_title = "ההתחברות לא הושלמה", "Sign-in did not complete."
        he_text = "חזרו ליישום ונסו להתחבר שוב." + (f" ({esc(detail)})" if detail else "")
        en_text = "Return to the app and try again."
    return _SIGN_IN_PAGE.format(title=esc(en_title), he_title=he_title, he_text=he_text,
                                en_title=en_title, en_text=en_text).encode("utf-8")


def _drive_error(exc: Exception) -> tuple[int, dict]:
    """Map a Drive/sign-in failure to (status, safe JSON). Never includes raw detail."""
    if isinstance(exc, SignedOut):
        return 401, {"error": "ההתחברות ל־Google פגה. התחברו שוב.", "code": "signed_out"}
    if isinstance(exc, SyncConflict):
        return 409, {"error": "ספר עם המזהה הזה כבר קיים במחשב; לא בוצעה דריסה.", "code": "conflict"}
    if isinstance(exc, DriveQuotaError):
        return 507, {"error": "האחסון ב־Google Drive מלא.", "code": "quota"}
    if isinstance(exc, (DriveNetworkError, SignInError)):
        return 503, {"error": "אין חיבור ל־Google Drive כרגע. נסו שוב מאוחר יותר.", "code": "network"}
    if isinstance(exc, DriveError):
        return 502, {"error": "הפעולה מול Google Drive נכשלה.", "code": "drive"}
    return 500, {"error": "הפעולה מול Google Drive נכשלה.", "code": "unknown"}
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
    if not _under_outputs(candidate) or not candidate.is_file():
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


def make_handler(token: str, model_config_path: str | None = None, *, learning_service=None, key_store=None,
                 account_factory=None, drive_factory=None):
    from ..translate.document_draft import (
        DocumentDraftError, DocumentJobs, MAX_FILE_BYTES, MODEL_CHOICES, QUALITY_MODES, render_download, validate_settings,
    )
    from ..translate import chapter_pipeline
    from ..export.common import list_pdf_fonts
    from ..models.adapter import build_translation_adapter
    from ..models.config import ModelConfiguration
    from ..translate.translation_profiles import SUPPORTED_PROFILE_IDS

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
                from ..learning.service import LearningService
                learning_holder[0] = LearningService(OUTPUT_ROOT.parent / "learning")
            return learning_holder[0]

    def _learning_adapter(model=None, reasoning=None, configuration=None):
        """A new preparation's chosen model, or a saved job's own configuration
        on resume; the key of that model's provider must be available."""
        from ..learning.contracts import require
        from ..learning.controls import learning_model_selection
        if configuration is None:
            configuration = model_settings.build_configuration({"translator": learning_model_selection(model, reasoning)})
        keys = _key_snapshot(configuration)
        require(bool(keys.get(configuration.resolve("translator")[0].provider)), "missing_api_key")
        return configuration, _adapter_factory_for(configuration, keys)

    def _learning_action(path, data):
        from ..learning.contracts import require
        service = _learning()
        if path == "/learning/state":
            from ..learning.controls import learning_model_options
            summary = service.summary()
            summary["keys_available"] = {}
            for entry in learning_model_options():
                if entry["provider"] not in summary["keys_available"]:
                    configuration = model_settings.build_configuration({"translator": {
                        "source": "catalog", "provider": entry["provider"], "model": entry["model"]}})
                    summary["keys_available"][entry["provider"]] = bool(_key_snapshot(configuration).get(entry["provider"]))
            return summary
        if path == "/learning/language":
            return service.select_language(data.get("language"))
        if path == "/learning/import-translation":
            snapshot = document_jobs.get(data.get("job_id", ""))
            # Validate completed Hebrew content before opening the saved source.
            from ..learning.importer import import_translation_job
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
        if path == "/learning/rename-book":
            return service.rename_book(data.get("book_id"), data.get("title"))
        if path == "/learning/delete-book":
            return service.delete_book(data.get("book_id"))
        if path == "/learning/effort":
            return service.set_effort(data.get("level_id"))
        if path == "/learning/prepare":
            configuration, factory = _learning_adapter(data.get("model"), data.get("reasoning"))
            return service.start(data.get("book_id"), data.get("budget_usd"), configuration, factory,
                                 context_chars=data.get('context_chars'), output_tokens=data.get('output_tokens'),
                                 skip_initial_chapters=data.get('skip_initial_chapters', 0))
        if path == "/learning/resume":
            _configuration, factory = _learning_adapter(configuration=service.job_configuration(data.get("session_id")))
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
                reasoning=selection.capabilities.reasoning if selection.capabilities else None,
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

    # ---- Google account + Drive library sync (CLOUD-LIBRARY C3) ----
    # Tokens, the client secret and refresh tokens never leave GoogleAccount:
    # no response, log or page below contains them.
    try:
        account = (account_factory or _default_account)()
    except Exception:
        account = None
    if account is not None:
        try:
            account.restore()  # offline: re-adopts a stored sign-in
        except Exception:
            pass
    account_lock = threading.Lock()
    pending_sign_in = {"value": None, "at": 0.0}
    sync_state = {"state": "idle", "last_sync_at": None, "last_error": None, "last_summary": None}
    sync_flags = {"running": False, "again": False}
    completed_seen: set[str] = set()

    def _signed_in() -> bool:
        return account is not None and bool(account.signed_in)

    def _account_view() -> dict:
        if account is None:
            return {"available": False}
        signed_in = _signed_in()
        who = account.account if signed_in else None
        with account_lock:
            sync = dict(sync_state)
        if not signed_in:
            sync["state"] = "signed_out"
        return {"available": True, "signed_in": signed_in,
                "email": getattr(who, "email", None) if who else None,
                "name": getattr(who, "name", None) if who else None, "sync": sync}

    def _make_drive():
        if drive_factory is not None:
            return drive_factory(account, document_jobs.root)
        return DriveLibrary(account.access_token, document_jobs.root,
                            invalidate_token=account.invalidate_access_token)

    def _sync_once() -> None:
        try:
            summary = _make_drive().sync_pending()
            failed = len(summary.get("failed") or [])
            with account_lock:
                sync_state["last_summary"] = {"uploaded": len(summary.get("uploaded") or []),
                                              "skipped": len(summary.get("skipped") or []), "failed": failed}
                sync_state["last_sync_at"] = time.time()
                sync_state["state"] = "error" if failed else "idle"
                sync_state["last_error"] = "upload_failed" if failed else None
        except Exception as exc:  # a sync failure never touches translation jobs
            code = _drive_error(exc)[1]["code"]
            with account_lock:
                sync_state["state"] = "signed_out" if code == "signed_out" else "error"
                sync_state["last_error"] = code

    def _sync_worker() -> None:
        while True:
            try:
                _sync_once()
            finally:
                with account_lock:
                    again = sync_flags["again"]
                    sync_flags["again"] = False
                    if again:
                        sync_state["state"] = "running"
                    else:
                        sync_flags["running"] = False
            if not again:
                return

    def _start_sync() -> bool:
        """Start a background sync, or queue one more run if one is in flight.
        One worker thread, one sync at a time. False when not signed in."""
        if not _signed_in():
            return False
        with account_lock:
            if sync_flags["running"]:
                sync_flags["again"] = True
                return True
            sync_flags["running"] = True
            sync_state["state"] = "running"
        threading.Thread(target=_sync_worker, name="drive-sync", daemon=True).start()
        return True

    def _note_completed(job_ids) -> None:
        """Sync when a completed job appears that has not triggered a sync yet."""
        if not _signed_in():
            return
        fresh = [job_id for job_id in job_ids if isinstance(job_id, str) and job_id not in completed_seen]
        if fresh:
            completed_seen.update(fresh)
            _start_sync()

    def _require_signed_in():
        if account is None:
            return 404, {"error": "החיבור ל־Google אינו זמין בגרסה זו.", "code": "unavailable"}
        if not _signed_in():
            return 401, {"error": "לא מחוברים ל־Google.", "code": "signed_out"}
        return None

    def _account_action(path: str, data: dict, port: int) -> tuple[int, dict]:
        if path == "/account":
            return 200, _account_view()
        if account is None:
            return 404, {"error": "החיבור ל־Google אינו זמין בגרסה זו.", "code": "unavailable"}
        if path == "/account/sign-in":
            try:
                url, pending = account.begin_sign_in(f"http://127.0.0.1:{port}/oauth/callback")
            except Exception:
                return 400, {"error": "לא ניתן להתחיל התחברות ל־Google.", "code": "sign_in_unavailable"}
            with account_lock:
                pending_sign_in["value"], pending_sign_in["at"] = pending, time.monotonic()
            try:
                webbrowser.open(url)
            except Exception:
                pass
            return 200, {"url": url}
        if path == "/account/sign-out":
            with account_lock:
                pending_sign_in["value"] = None
                sync_state.update(state="idle", last_sync_at=None, last_error=None, last_summary=None)
            try:
                account.sign_out()
            except Exception:
                pass
            completed_seen.clear()
            return 200, {"ok": True}
        refused = _require_signed_in()
        if refused:
            return refused
        if path == "/account/sync":
            _start_sync()
            return 200, {"started": True, "sync": _account_view()["sync"]}
        try:
            if path == "/account/remote-library":
                books = [dataclasses.asdict(b) if dataclasses.is_dataclass(b) else dict(b)
                         for b in _make_drive().list_remote()]
                return 200, {"books": books}
            if path == "/account/restore":
                try:
                    job_id = validate_job_id(data.get("job_id"))
                except ValueError:
                    return 400, {"error": "מזהה הספר אינו תקין.", "code": "bad_id"}
                _make_drive().download(job_id)
                return 200, {"ok": True, "job_id": job_id}
        except Exception as exc:
            return _drive_error(exc)
        return 404, {"error": "not found"}

    def _oauth_callback(query: dict) -> bytes:
        with account_lock:
            pending = pending_sign_in["value"]
            if pending is not None and time.monotonic() - pending_sign_in["at"] > PENDING_SIGN_IN_SECONDS:
                pending = pending_sign_in["value"] = None
        if account is None or pending is None:
            return _sign_in_page(False)
        try:
            who = account.complete_sign_in(pending, query)
        except SignInError as exc:
            if exc.reason != "state_mismatch":  # a stray request must not cancel the real attempt
                with account_lock:
                    pending_sign_in["value"] = None
            return _sign_in_page(False, str(getattr(exc, "reason", "")))
        except Exception:
            with account_lock:
                pending_sign_in["value"] = None
            return _sign_in_page(False)
        with account_lock:
            pending_sign_in["value"] = None
            sync_state.update(state="idle", last_error=None)
        _start_sync()
        return _sign_in_page(True, str(getattr(who, "email", "") or ""))

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
            if urlparse(self.path).path == "/oauth/callback":
                # The browser redirect from Google: no UI token possible. Safe because
                # the one-time state (plus PKCE) must match the pending sign-in.
                query = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items() if v}
                self._reply(200, _oauth_callback(query), "text/html")
                return
            if urlparse(self.path).path == "/learning/wordlist":
                language = parse_qs(urlparse(self.path).query).get('language', [''])[0]
                if language not in ('fr', 'de', 'es', 'yi', 'it', 'ar'):
                    self._json(404, {"error": "not found"})
                    return
                self._reply(200, (ROOT / 'prompts' / 'language_learning' / 'wordlists' / ('ar_starter.md' if language == 'ar' else language + '_500.md')).read_bytes(), 'text/plain')
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
            if urlparse(self.path).path == "/keys-guide":
                self._reply(200, (UI_DIR / "keys_guide.html").read_bytes(), "text/html")
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
                    from ..models.catalog import CATALOG_VERSION
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
                self._reply(200, (UI_DIR.parent / "assets" / "book-sprite.svg").read_bytes(), "image/svg+xml")
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
                from ..learning.contracts import LearningError
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
                    from ..learning.importer import title_from_filename
                    self._json(200, _learning().import_epub(content, title=title_from_filename(name)))
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
                if route.path == "/account" or route.path.startswith("/account/"):
                    status, body = _account_action(route.path, data, self.server.server_port)
                    self._json(status, body)
                    return
                if route.path == "/update-status":
                    self._json(200, {"status": ui_status()})
                    return
                if route.path == "/update-settings":
                    enabled = data.get("auto_update")
                    if not isinstance(enabled, bool):
                        self._json(400, {"error": "auto_update must be true or false"})
                    elif ui_status() is None:
                        self._json(404, {"error": "updates are not available in this installation"})
                    else:
                        set_auto_update(enabled)
                        self._json(200, {"ok": True, "auto_update": enabled})
                    return
                if route.path.startswith("/learning/"):
                    from ..learning.contracts import LearningError
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
                    job["review_suggestions"] = sum(chapter_pipeline.review_suggestions(job).values())
                    if job.get("status") == "completed":
                        _note_completed([job.get("job_id")])
                    self._json(200, job)
                elif route.path == "/document-recheck-reviews":
                    self._json(200, document_jobs.recheck_saved_reviews(data.get("job_id")))
                elif route.path == "/document-apply-suggestions":
                    self._json(200, document_jobs.apply_review_suggestions(data.get("job_id")))
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
                    from ..models.catalog import CATALOG_VERSION
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
                    documents = _document_library(document_jobs)
                    _note_completed([d.get("job_id") for d in documents])
                    self._json(200, {"documents": documents})
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
                    from ..translate.book_notebook import render_markdown
                    from ..translate.name_table import render_markdown as render_names_markdown
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
                    from ..translate.glossary import new_store
                    glossary_path = data.get("glossary", "")
                    glossary = decision_file(data, "glossary")[1] if glossary_path else new_store()
                    self._json(200, glossary_options(structure, glossary))
                elif route.path == "/glossary-action":
                    structure_path, structure = decision_file(data, "structure_json")
                    from ..translate.glossary import new_store
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
                        allowed = _under_outputs(path) or any(
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


def claim_single_instance(folder: Path):
    """One server per data folder. Two servers would each keep their own
    in-memory view of running jobs while sharing (and overwriting) the same
    saved state: a job shows as stopped in one and refuses to resume as
    already running in the other. Returns the open lock handle (held until the
    process exits; the OS releases it even after a crash), or None when
    another live server holds the folder."""
    folder.mkdir(parents=True, exist_ok=True)
    handle = open(folder / "web_ui.lock", "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def running_instance_url(folder: Path) -> str | None:
    """The address the live server recorded, if it is a local UI address."""
    try:
        url = (folder / "web_ui.url").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return url if re.fullmatch(r"http://127\.0\.0\.1:\d{1,5}/", url) else None


def main() -> int:
    try:
        app_paths.migrate_legacy_outputs()
    except Exception:
        pass  # a failed one-time copy must never stop the app starting
    instance_folder = OUTPUT_ROOT.parent
    instance_lock = claim_single_instance(instance_folder)
    if instance_lock is None:
        existing = running_instance_url(instance_folder)
        print("The server is already running in another window; opening it instead of starting a second one." +
              (f" ({existing})" if existing else ""), flush=True)
        if existing:
            webbrowser.open(existing)
        return 0
    token = secrets.token_urlsafe(24)
    model_config_path = os.environ.get("SCHOLARLY_TRANSLATION_MODEL_CONFIG")
    from ..models.key_store import default_key_store
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(token, model_config_path, key_store=default_key_store()))
    url = f"http://127.0.0.1:{server.server_port}/"
    (instance_folder / "web_ui.url").write_text(url, encoding="utf-8")
    print(f"Local UI: {url}", flush=True)
    try:
        app_paths.start_heartbeat_thread()
    except Exception:
        pass
    try:
        from ..update import updater
        updater.start_background_check()
    except Exception:
        pass
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        instance_lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
