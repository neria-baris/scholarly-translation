"""Drive library sync (CLOUD-LIBRARY C2): keeps completed translation jobs in
the user's own Google Drive (scope drive.file), via Drive REST v3 over urllib.

Consumes sign-in only through an injected ``access_token()`` callable. The HTTP
layer is an injectable transport so tests run against an in-memory fake Drive.

Files synced per completed job (allow-list; everything else, e.g. the live
``controls.sqlite3`` budget store, caches and temp files, is never uploaded):
    job.json, source.pdf / source.epub, ocr/bundle.json (stored in Drive under
    the flat name ``ocr__bundle.json``).
Translated text lives inside job.json (units); PDF/EPUB/HTML exports are
re-rendered on demand from it, so they are not stored separately.

Nothing here ever deletes a Drive file, and nothing here modifies local job
files except ``download`` creating a brand-new job folder.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from scholarly_translation.account.google_auth import SignedOut

API = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
FOLDER_MIME = "application/vnd.google-apps.folder"
APP_FOLDER_NAME = "Scholarly Translation"
LIBRARY_PROP = "scholarly_library"
RESUMABLE_THRESHOLD = 5 * 1024 * 1024
CHUNK_SIZE = 8 * 1024 * 1024  # multiple of 256 KiB, as Drive requires
TIMEOUT = 60
QUOTA_REASONS = {"storageQuotaExceeded", "quotaExceeded", "driveStorageLimitExceeded"}
_SAFE_JOB_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")

# (local relative path, flat Drive name)
SYNC_FILES = (
    ("job.json", "job.json"),
    ("source.pdf", "source.pdf"),
    ("source.epub", "source.epub"),
    ("ocr/bundle.json", "ocr__bundle.json"),
)


class DriveError(Exception):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class DriveQuotaError(DriveError):
    """Drive storage quota is exhausted; shown to the user."""


class DriveNetworkError(DriveError):
    """Network trouble or a transient server error; retry later."""


class SyncConflict(DriveError):
    """A local job with this id already exists; nothing was overwritten."""


@dataclass(frozen=True)
class RemoteBook:
    job_id: str
    filename: str
    completed_at: Optional[float]
    files: tuple


# --------------------------------------------------------------- transport

class UrllibTransport:
    """Default transport. Every method returns (http_status, parsed_json_dict);
    HTTP error statuses are returned, network failures raise DriveNetworkError.
    The bearer token only ever goes into the Authorization header."""

    def __init__(self, timeout: int = TIMEOUT):
        self.timeout = timeout

    def _http(self, method, url, headers, data=None):
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, dict(exc.headers), exc.read()
            finally:
                exc.close()
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise DriveNetworkError("Network error talking to Google Drive.") from None

    @staticmethod
    def _parse(raw):
        try:
            value = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def json(self, method, url, token, body=None):
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=UTF-8"
        status, _, raw = self._http(method, url, headers, data)
        return status, self._parse(raw)

    def upload_multipart(self, method, url, token, metadata, path):
        boundary = "st" + uuid.uuid4().hex
        head = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(metadata)}\r\n--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n")
        body = head.encode("utf-8") + Path(path).read_bytes() + f"\r\n--{boundary}--".encode()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json",
                   "Content-Type": f"multipart/related; boundary={boundary}"}
        status, _, raw = self._http(method, url, headers, body)
        return status, self._parse(raw)

    def upload_resumable(self, method, url, token, metadata, path):
        path = Path(path)
        size = path.stat().st_size
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json",
                   "Content-Type": "application/json; charset=UTF-8",
                   "X-Upload-Content-Length": str(size)}
        status, resp_headers, raw = self._http(method, url, headers, json.dumps(metadata).encode("utf-8"))
        if status != 200:
            return status, self._parse(raw)
        location = {k.lower(): v for k, v in resp_headers.items()}.get("location")
        if not location:
            raise DriveError("Drive did not return a resumable upload location.", status)
        with open(path, "rb") as handle:
            offset = 0
            while True:
                chunk = handle.read(CHUNK_SIZE)
                end = offset + len(chunk) - 1
                put_headers = {"Authorization": f"Bearer {token}", "Accept": "application/json",
                               "Content-Range": (f"bytes {offset}-{end}/{size}" if chunk else f"bytes */{size}")}
                status, _, raw = self._http("PUT", location, put_headers, chunk)
                if status == 308:
                    offset += len(chunk)
                    continue
                return status, self._parse(raw)

    def download(self, url, token, dest):
        headers = {"Authorization": f"Bearer {token}"}
        status, _, raw = self._http("GET", url, headers)
        if status != 200:
            return status, self._parse(raw)
        Path(dest).write_bytes(raw)
        return status, {}


# ----------------------------------------------------------------- helpers

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _q(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _error_reason(body: dict) -> str:
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        for item in error.get("errors") or []:
            if isinstance(item, dict) and isinstance(item.get("reason"), str):
                return item["reason"]
        if isinstance(error.get("status"), str):
            return error["status"]
    return ""


def validate_job_id(job_id) -> str:
    if (not isinstance(job_id, str) or not _SAFE_JOB_ID.fullmatch(job_id)
            or job_id in (".", "..")):
        raise ValueError("Unsafe job id.")
    return job_id


# ------------------------------------------------------------------ library

class DriveLibrary:
    def __init__(self, access_token: Callable[[], str], jobs_root, transport=None,
                 clock: Callable[[], float] = time.time,
                 invalidate_token: Optional[Callable[[], None]] = None):
        """``invalidate_token`` (e.g. GoogleAccount.invalidate_access_token) is
        called after a 401 so the retry gets a refreshed, not cached, token."""
        self._access_token = access_token
        self._invalidate_token = invalidate_token
        self.jobs_root = Path(jobs_root)
        self.transport = transport or UrllibTransport()
        self.clock = clock
        self._token: Optional[str] = None
        self._root_id: Optional[str] = None

    # -- request plumbing -------------------------------------------------
    def _call(self, fn):
        """fn(token) -> (status, body). Handles 401 (one refresh), quota, network."""
        for attempt in (0, 1):
            if attempt == 1 and self._invalidate_token is not None:
                self._invalidate_token()
            if self._token is None or attempt == 1:
                self._token = self._access_token()
            token = self._token
            try:
                status, body = fn(token)
            except DriveError:
                raise
            except (OSError, TimeoutError):
                raise DriveNetworkError("Network error talking to Google Drive.") from None
            if status == 401:
                if attempt == 0:
                    continue
                self._token = None
                raise SignedOut("Google rejected the stored sign-in; please sign in again.")
            return self._check(status, body)
        raise SignedOut("Google rejected the stored sign-in; please sign in again.")  # pragma: no cover

    @staticmethod
    def _check(status, body):
        if 200 <= status < 300:
            return body
        reason = _error_reason(body)
        if status == 403 and (reason in QUOTA_REASONS or "quota" in reason.lower()):
            raise DriveQuotaError("Google Drive storage is full or the quota is exceeded.", status)
        if status == 429 or status >= 500:
            raise DriveNetworkError(f"Google Drive is temporarily unavailable (HTTP {status}).", status)
        raise DriveError(f"Google Drive request failed (HTTP {status}{', ' + reason if reason else ''}).", status)

    def _json(self, method, url, body=None):
        return self._call(lambda token: self.transport.json(method, url, token, body))

    def _list(self, q, fields="id,name,description,appProperties"):
        files, page = [], None
        while True:
            params = {"q": q, "spaces": "drive", "pageSize": "1000",
                      "fields": f"nextPageToken,files({fields})"}
            if page:
                params["pageToken"] = page
            body = self._json("GET", f"{API}/files?{urllib.parse.urlencode(params)}")
            files.extend(item for item in body.get("files", []) if isinstance(item, dict))
            page = body.get("nextPageToken")
            if not page:
                return files

    # -- folders ----------------------------------------------------------
    def _ensure_root(self) -> str:
        if self._root_id:
            return self._root_id
        found = self._list(f"mimeType='{FOLDER_MIME}' and trashed=false and "
                           f"appProperties has {{ key='{LIBRARY_PROP}' and value='1' }}")
        if found:
            self._root_id = found[0]["id"]
        else:
            created = self._json("POST", f"{API}/files?fields=id", {
                "name": APP_FOLDER_NAME, "mimeType": FOLDER_MIME,
                "appProperties": {LIBRARY_PROP: "1"}})
            self._root_id = created["id"]
        return self._root_id

    def _job_folders(self) -> dict:
        root = self._ensure_root()
        folders = self._list(f"'{_q(root)}' in parents and mimeType='{FOLDER_MIME}' and trashed=false")
        result = {}
        for item in folders:
            job_id = (item.get("appProperties") or {}).get("job_id")
            if isinstance(job_id, str) and job_id not in result:
                result[job_id] = item
        return result

    def _folder_files(self, folder_id) -> dict:
        items = self._list(f"'{_q(folder_id)}' in parents and mimeType!='{FOLDER_MIME}' and trashed=false",
                           fields="id,name,appProperties")
        result = {}
        for item in items:
            name = (item.get("appProperties") or {}).get("name") or item.get("name")
            if isinstance(name, str) and name not in result:
                result[name] = item
        return result

    # -- local jobs -------------------------------------------------------
    def _read_job(self, job_dir: Path) -> Optional[dict]:
        try:
            job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if (not isinstance(job, dict) or job.get("status") != "completed"
                or not isinstance(job.get("units"), list) or not job["units"]
                or not isinstance(job.get("filename"), str) or not Path(job["filename"]).name):
            return None
        return job

    def local_completed(self) -> list:
        ids = []
        try:
            dirs = sorted(p for p in self.jobs_root.iterdir() if p.is_dir())
        except OSError:
            return ids
        for job_dir in dirs:
            if _SAFE_JOB_ID.fullmatch(job_dir.name) and self._read_job(job_dir) is not None:
                ids.append(job_dir.name)
        return ids

    def _local_files(self, job_dir: Path) -> list:
        out = []
        for rel, flat in SYNC_FILES:
            path = job_dir / rel
            if path.is_file():
                out.append((flat, path))
        return out

    # -- upload -----------------------------------------------------------
    def upload_job(self, job_id, _folders=None) -> str:
        """Upload one completed local job. Returns 'uploaded' or 'skipped'."""
        validate_job_id(job_id)
        job_dir = self.jobs_root / job_id
        job = self._read_job(job_dir)
        if job is None:
            raise DriveError("Job is not a completed local job.")
        folders = _folders if _folders is not None else self._job_folders()
        folder = folders.get(job_id)
        completed_at = job.get("completed_at")
        if isinstance(completed_at, bool) or not isinstance(completed_at, (int, float)):
            try:
                completed_at = (job_dir / "job.json").stat().st_mtime
            except OSError:
                completed_at = self.clock()
        if folder is None:
            folder = self._json("POST", f"{API}/files?fields=id", {
                "name": f"{Path(job['filename']).name} [{job_id[:8]}]", "mimeType": FOLDER_MIME,
                "description": Path(job["filename"]).name, "parents": [self._ensure_root()],
                "appProperties": {"job_id": job_id, "completed_at": repr(float(completed_at))}})
            folders[job_id] = folder
        existing = self._folder_files(folder["id"])
        changed = False
        for flat, path in self._local_files(job_dir):
            digest = _sha256(path)
            current = existing.get(flat)
            if current and (current.get("appProperties") or {}).get("sha256") == digest:
                continue
            props = {"job_id": job_id, "name": flat, "sha256": digest}
            if current:
                url, method, metadata = f"{{base}}/files/{current['id']}", "PATCH", {"appProperties": props}
            else:
                url, method = "{base}/files", "POST"
                metadata = {"name": flat, "parents": [folder["id"]], "appProperties": props}
            self._upload(method, url, metadata, path)
            changed = True
        return "uploaded" if changed else "skipped"

    def _upload(self, method, url, metadata, path: Path):
        resumable = path.stat().st_size > RESUMABLE_THRESHOLD
        kind = "resumable" if resumable else "multipart"
        full = url.format(base=UPLOAD_API) + f"?uploadType={kind}&fields=id"
        send = self.transport.upload_resumable if resumable else self.transport.upload_multipart
        return self._call(lambda token: send(method, full, token, metadata, path))

    def sync_pending(self) -> dict:
        """Upload every local completed job that is not fully in Drive. A
        failure for one job is recorded and never stops the others or touches
        local files. SignedOut propagates (every job would fail the same way)."""
        self._root_id = None  # rediscover; the user may have moved/deleted it
        summary = {"uploaded": [], "skipped": [], "failed": []}
        ids = self.local_completed()
        if not ids:
            return summary
        try:
            folders = self._job_folders()
        except SignedOut:
            raise
        except DriveError as exc:
            summary["failed"] = [{"job_id": i, "error": str(exc)} for i in ids]
            return summary
        for job_id in ids:
            try:
                summary[self.upload_job(job_id, folders)].append(job_id)
            except SignedOut:
                raise
            except (DriveError, OSError, ValueError) as exc:
                summary["failed"].append({"job_id": job_id, "error": str(exc)})
        return summary

    # -- remote -----------------------------------------------------------
    def list_remote(self) -> list:
        books = []
        for job_id, folder in self._job_folders().items():
            props = folder.get("appProperties") or {}
            try:
                validate_job_id(job_id)
            except ValueError:
                continue
            files = self._folder_files(folder["id"])
            try:
                completed_at = float(props["completed_at"])
            except (KeyError, ValueError, TypeError):
                completed_at = None
            filename = folder.get("description")
            if not isinstance(filename, str) or not filename:
                filename, completed_at = self._filename_from_job_json(files, job_id, completed_at)
            books.append(RemoteBook(job_id, filename, completed_at, tuple(sorted(files))))
        books.sort(key=lambda b: b.completed_at or 0.0, reverse=True)
        return books

    def _filename_from_job_json(self, files, job_id, completed_at):
        item = files.get("job.json")
        if not item:
            return job_id, completed_at
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "job.json"
            self._fetch(item["id"], dest)
            try:
                job = json.loads(dest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return job_id, completed_at
        name = Path(job.get("filename")).name if isinstance(job, dict) and isinstance(job.get("filename"), str) else job_id
        done = job.get("completed_at") if isinstance(job, dict) else None
        if completed_at is None and isinstance(done, (int, float)) and not isinstance(done, bool):
            completed_at = float(done)
        return name or job_id, completed_at

    def _fetch(self, file_id, dest: Path):
        url = f"{API}/files/{urllib.parse.quote(file_id, safe='')}?alt=media"
        self._call(lambda token: self.transport.download(url, token, dest))

    def download(self, job_id) -> Path:
        """Restore a Drive job into jobs_root/<job_id>; never overwrites."""
        validate_job_id(job_id)
        final = self.jobs_root / job_id
        if final.exists():
            raise SyncConflict("A local job with this id already exists; it was not overwritten.")
        folder = self._job_folders().get(job_id)
        if folder is None:
            raise DriveError("This book is not in Google Drive.")
        files = self._folder_files(folder["id"])
        if "job.json" not in files:
            raise DriveError("The Drive copy has no job.json.")
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix=".restore-", dir=self.jobs_root.parent))
        try:
            for rel, flat in SYNC_FILES:
                item = files.get(flat)
                if not item:
                    continue
                dest = temp / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                self._fetch(item["id"], dest)
                expected = (item.get("appProperties") or {}).get("sha256")
                if expected and _sha256(dest) != expected:
                    raise DriveError("A downloaded file failed its integrity check.")
            if final.exists():
                raise SyncConflict("A local job with this id already exists; it was not overwritten.")
            try:
                os.rename(temp, final)
            except OSError:
                raise SyncConflict("A local job with this id already exists; it was not overwritten.") from None
        except BaseException:
            shutil.rmtree(temp, ignore_errors=True)
            raise
        return final
