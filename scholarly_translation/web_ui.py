"""Local browser shell over the existing CLI. No runtime service beyond localhost."""

from __future__ import annotations

import hashlib
import json
import os
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


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = ROOT / "outputs" / "ui"
MAX_UPLOAD = 100 * 1024 * 1024
UI_DIR = Path(__file__).resolve().parent


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


def make_handler(token: str, model_config_path: str | None = None):
    from .document_draft import (
        DocumentDraftError, DocumentJobs, MAX_FILE_BYTES, MODEL_CHOICES, QUALITY_MODES, render_download,
    )
    from .model_config import ModelConfiguration
    from .translation_profiles import SUPPORTED_PROFILE_IDS

    server_model_config = None
    if model_config_path:
        server_model_config = json.loads(Path(model_config_path).read_text(encoding="utf-8"))
        ModelConfiguration.from_dict(server_model_config)  # fail fast on an invalid deployment file

    session_settings = {"api_key": None}
    session_outputs: set[Path] = set()
    settings_lock = threading.Lock()
    document_jobs = DocumentJobs(OUTPUT_ROOT)

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
            if self.path == "/help":
                self._reply(200, (ROOT / "UI_README_HE.md").read_bytes(), "text/plain")
                return
            if self.path in ("/ui.css", "/ui.js"):
                name = self.path.removeprefix("/")
                kind = "text/css" if name.endswith(".css") else "text/javascript"
                self._reply(200, (UI_DIR / name).read_bytes(), kind)
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
                if route.path == "/document-config":
                    translator_label = None
                    if server_model_config is not None:
                        translator = server_model_config.get("models", {}).get("translator", {})
                        translator_label = f"{translator.get('provider')}/{translator.get('model')}"
                    self._json(200, {
                        "profiles": [{"id": pid} for pid in SUPPORTED_PROFILE_IDS],
                        "qualities": [{"id": q} for q in sorted(QUALITY_MODES)],
                        "model_choices": sorted(MODEL_CHOICES),
                        "model_config_available": server_model_config is not None,
                        "configured_translator_model": translator_label,
                        "max_file_bytes": MAX_FILE_BYTES,
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
                    settings = dict(settings)
                    if settings.get("model") == "configured" and settings.get("model_config") is None:
                        if server_model_config is None:
                            raise DocumentDraftError("לא הוגדר קובץ תצורת מודל בשרת.")
                        settings["model_config"] = server_model_config
                    self._json(200, document_jobs.start(source, settings, paid_confirm=data.get("paid_confirm")))
                elif route.path == "/document-job":
                    self._json(200, document_jobs.get(data.get("job_id")))
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
                elif route.path == "/document-review":
                    self._json(200, document_jobs.review(data.get("job_id"), data.get("unit_index"),
                               data.get("target_text"), data.get("expected_revision")))
                elif route.path == "/document-download":
                    job = document_jobs.get(data.get("job_id"))
                    if job["status"] != "completed":
                        raise DocumentDraftError("עדיין אין תוצאה להורדה.")
                    kind = job.get("source_kind", "pdf")
                    source_path = document_jobs.source_path(job["job_id"], "epub") if kind == "epub" else None
                    body = render_download(job, kind, source_path=source_path)
                    content_type = "application/epub+zip" if kind == "epub" else "application/pdf"
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(Path(job["filename"]).stem + f".he.{kind}"))
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
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(token, model_config_path))
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
