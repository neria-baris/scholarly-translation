"""Offline tests for the Drive library sync (in-memory fake Drive, no network)."""
import json
import re
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from scholarly_translation.account import drive_library as dl
from scholarly_translation.account.drive_library import (
    DriveError, DriveLibrary, DriveNetworkError, DriveQuotaError, SyncConflict,
)
from scholarly_translation.account.google_auth import SignedOut

TOKEN_1 = "TOKEN-ONE-SECRET"
TOKEN_2 = "TOKEN-TWO-SECRET"
JOB_A = "a" * 32
JOB_B = "b" * 32


class FakeDrive:
    """Implements the transport subset DriveLibrary uses."""

    def __init__(self, valid_tokens=(TOKEN_1,)):
        self.files = {}
        self.valid = set(valid_tokens)
        self.seq = 0
        self.calls = []
        self.uploads = []  # (kind, method, id_or_None, name)
        self.fail = []  # queue of (status, body) or Exception for next call

    def _id(self):
        self.seq += 1
        return f"id{self.seq}"

    def _gate(self, token):
        if self.fail:
            item = self.fail.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        if token not in self.valid:
            return 401, {"error": {"errors": [{"reason": "authError"}]}}
        return None

    def json(self, method, url, token, body=None):
        self.calls.append((method, url))
        blocked = self._gate(token)
        if blocked:
            return blocked
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        if method == "GET":
            q = params["q"][0]
            result = [self._meta(f) for f in self.files.values() if self._match(f, q)]
            return 200, {"files": result}
        if method == "POST":
            fid = self._id()
            self.files[fid] = {"id": fid, "name": body["name"], "mimeType": body.get("mimeType", ""),
                               "parents": body.get("parents", []), "description": body.get("description"),
                               "appProperties": dict(body.get("appProperties", {})), "content": None}
            return 200, {"id": fid}
        return 400, {}

    @staticmethod
    def _meta(f):
        return {k: v for k, v in f.items() if k != "content"}

    @staticmethod
    def _match(f, q):
        folder = f["mimeType"] == dl.FOLDER_MIME
        if "key='scholarly_library'" in q:
            return folder and f["appProperties"].get("scholarly_library") == "1"
        parent = re.search(r"'([^']+)' in parents", q).group(1)
        if parent not in f["parents"]:
            return False
        return folder if "mimeType='" + dl.FOLDER_MIME in q else not folder

    def _upload(self, kind, method, url, token, metadata, path):
        self.calls.append((method, url))
        blocked = self._gate(token)
        if blocked:
            return blocked
        content = Path(path).read_bytes()
        if method == "POST":
            fid = self._id()
            self.files[fid] = {"id": fid, "name": metadata["name"], "mimeType": "application/octet-stream",
                               "parents": metadata["parents"], "description": None,
                               "appProperties": dict(metadata["appProperties"]), "content": content}
            self.uploads.append((kind, "create", fid, metadata["name"]))
        else:
            fid = re.search(r"/files/([^?]+)", url).group(1)
            self.files[fid]["content"] = content
            self.files[fid]["appProperties"] = dict(metadata["appProperties"])
            self.uploads.append((kind, "update", fid, self.files[fid]["name"]))
        return 200, {"id": fid}

    def upload_multipart(self, method, url, token, metadata, path):
        return self._upload("multipart", method, url, token, metadata, path)

    def upload_resumable(self, method, url, token, metadata, path):
        return self._upload("resumable", method, url, token, metadata, path)

    def download(self, url, token, dest):
        self.calls.append(("GET", url))
        blocked = self._gate(token)
        if blocked:
            return blocked
        fid = re.search(r"/files/([^?]+)", url).group(1)
        Path(dest).write_bytes(self.files[fid]["content"])
        return 200, {}


def make_job(root: Path, job_id, filename="book.pdf", extra=None, status="completed"):
    folder = root / job_id
    folder.mkdir(parents=True)
    job = {"job_id": job_id, "status": status, "filename": filename, "source_kind": "pdf",
           "units": [{"unit_id": "u1", "target_text": "שלום"}], "completed_at": 1234.5}
    (folder / "job.json").write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    (folder / "source.pdf").write_bytes(b"%PDF-source")
    (folder / "controls.sqlite3").write_bytes(b"live-db")
    (folder / "ocr").mkdir()
    (folder / "ocr" / "bundle.json").write_text("{}", encoding="utf-8")
    for name, data in (extra or {}).items():
        (folder / name).write_bytes(data)
    return folder


def snapshot(folder: Path):
    return {str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


class DriveLibraryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.root = self.base / "documents"
        self.root.mkdir()
        self.drive = FakeDrive()
        self.tokens = [TOKEN_1]
        self.token_calls = 0

    def access_token(self):
        self.token_calls += 1
        return self.tokens[min(self.token_calls - 1, len(self.tokens) - 1)]

    def lib(self):
        return DriveLibrary(self.access_token, self.root, transport=self.drive)

    def names(self):
        return sorted(f["name"] for f in self.drive.files.values())

    def test_first_sync_creates_folders_and_files(self):
        make_job(self.root, JOB_A)
        summary = self.lib().sync_pending()
        self.assertEqual(summary, {"uploaded": [JOB_A], "skipped": [], "failed": []})
        folders = [f for f in self.drive.files.values() if f["mimeType"] == dl.FOLDER_MIME]
        self.assertEqual(len(folders), 2)
        self.assertEqual(sorted(f["name"] for f in folders if f["appProperties"].get("job_id") is None),
                         ["Scholarly Translation"])
        self.assertEqual(sorted(n for n in self.names() if "." in n and not n.endswith("]")),
                         ["job.json", "ocr__bundle.json", "source.pdf"])
        self.assertNotIn("controls.sqlite3", self.names())
        job_file = next(f for f in self.drive.files.values() if f["name"] == "job.json")
        self.assertEqual(job_file["appProperties"]["job_id"], JOB_A)
        self.assertEqual(job_file["appProperties"]["name"], "job.json")
        self.assertEqual(len(job_file["appProperties"]["sha256"]), 64)

    def test_resync_skips_unchanged(self):
        make_job(self.root, JOB_A)
        self.lib().sync_pending()
        before = len(self.drive.uploads)
        summary = self.lib().sync_pending()
        self.assertEqual(summary["skipped"], [JOB_A])
        self.assertEqual(summary["uploaded"], [])
        self.assertEqual(len(self.drive.uploads), before)

    def test_changed_file_updates_same_drive_id(self):
        folder = make_job(self.root, JOB_A)
        self.lib().sync_pending()
        old_id = next(f["id"] for f in self.drive.files.values() if f["name"] == "source.pdf")
        count = len(self.drive.files)
        (folder / "source.pdf").write_bytes(b"%PDF-changed")
        summary = self.lib().sync_pending()
        self.assertEqual(summary["uploaded"], [JOB_A])
        self.assertEqual(len(self.drive.files), count)
        self.assertEqual(self.drive.files[old_id]["content"], b"%PDF-changed")
        self.assertEqual(self.drive.uploads[-1][:2], ("multipart", "update"))

    def test_large_file_uses_resumable(self):
        make_job(self.root, JOB_A, extra={"source.epub": b"x" * (dl.RESUMABLE_THRESHOLD + 1)})
        self.lib().sync_pending()
        kinds = {name: kind for kind, _, _, name in self.drive.uploads}
        self.assertEqual(kinds["source.epub"], "resumable")
        self.assertEqual(kinds["job.json"], "multipart")

    def test_folder_rediscovered_by_app_properties(self):
        make_job(self.root, JOB_A)
        self.lib().sync_pending()
        make_job(self.root, JOB_B, filename="two.pdf")
        fresh = self.lib()
        fresh.sync_pending()
        roots = [f for f in self.drive.files.values() if f["appProperties"].get("scholarly_library") == "1"]
        self.assertEqual(len(roots), 1)
        job_folders = [f for f in self.drive.files.values() if f["appProperties"].get("job_id") and f["mimeType"] == dl.FOLDER_MIME]
        self.assertEqual(len(job_folders), 2)

    def test_incomplete_jobs_not_uploaded(self):
        make_job(self.root, JOB_A, status="translating")
        self.assertEqual(self.lib().sync_pending(), {"uploaded": [], "skipped": [], "failed": []})
        self.assertEqual(self.drive.files, {})

    def test_list_remote(self):
        make_job(self.root, JOB_A, filename="alpha.pdf")
        self.lib().sync_pending()
        books = self.lib().list_remote()
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0].job_id, JOB_A)
        self.assertEqual(books[0].filename, "alpha.pdf")
        self.assertEqual(books[0].completed_at, 1234.5)
        self.assertEqual(books[0].files, ("job.json", "ocr__bundle.json", "source.pdf"))

    def test_list_remote_falls_back_to_job_json(self):
        make_job(self.root, JOB_A, filename="alpha.pdf")
        self.lib().sync_pending()
        for f in self.drive.files.values():
            if f["mimeType"] == dl.FOLDER_MIME and f["appProperties"].get("job_id"):
                f["description"] = None
                f["appProperties"].pop("completed_at")
        book = self.lib().list_remote()[0]
        self.assertEqual((book.filename, book.completed_at), ("alpha.pdf", 1234.5))

    def test_restore_into_empty_root(self):
        folder = make_job(self.root, JOB_A)
        original = snapshot(folder)
        self.lib().sync_pending()
        import shutil
        shutil.rmtree(folder)
        restored = self.lib().download(JOB_A)
        self.assertEqual(restored, self.root / JOB_A)
        expected = {k: v for k, v in original.items() if k != "controls.sqlite3"}
        self.assertEqual(snapshot(restored), expected)
        self.assertEqual([p.name for p in self.base.iterdir()], ["documents"])  # no temp left

    def test_restore_conflict_leaves_local_untouched(self):
        folder = make_job(self.root, JOB_A)
        self.lib().sync_pending()
        before = snapshot(folder)
        with self.assertRaises(SyncConflict):
            self.lib().download(JOB_A)
        self.assertEqual(snapshot(folder), before)

    def test_unsafe_job_id_rejected(self):
        for bad in ("../x", "a/b", "a\\b", "..", ".", "", "x" * 65, None, "a b"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.lib().download(bad)
        self.assertEqual(self.drive.calls, [])

    def test_restore_integrity_failure_cleans_up(self):
        folder = make_job(self.root, JOB_A)
        self.lib().sync_pending()
        for f in self.drive.files.values():
            if f["name"] == "source.pdf":
                f["content"] = b"tampered"
        import shutil
        shutil.rmtree(folder)
        with self.assertRaises(DriveError):
            self.lib().download(JOB_A)
        self.assertFalse((self.root / JOB_A).exists())
        self.assertEqual([p.name for p in self.base.iterdir()], ["documents"])

    def test_401_then_success_after_refresh(self):
        make_job(self.root, JOB_A)
        self.drive.valid = {TOKEN_2}
        self.tokens = [TOKEN_1, TOKEN_2]
        summary = self.lib().sync_pending()
        self.assertEqual(summary["uploaded"], [JOB_A])
        self.assertEqual(self.token_calls, 2)

    def test_401_invalidates_cached_token_before_retry(self):
        make_job(self.root, JOB_A)
        self.drive.valid = {TOKEN_2}
        self.tokens = [TOKEN_1, TOKEN_2]
        invalidated = []
        lib = DriveLibrary(self.access_token, self.root, transport=self.drive,
                           invalidate_token=lambda: invalidated.append(self.token_calls))
        self.assertEqual(lib.sync_pending()["uploaded"], [JOB_A])
        self.assertEqual(invalidated, [1])  # once, after the first token was rejected

    def test_401_twice_raises_signed_out(self):
        folder = make_job(self.root, JOB_A)
        before = snapshot(folder)
        self.drive.valid = set()
        self.tokens = [TOKEN_1, TOKEN_2]
        with self.assertRaises(SignedOut) as ctx:
            self.lib().sync_pending()
        self.assertNotIn(TOKEN_1, str(ctx.exception))
        self.assertNotIn(TOKEN_2, str(ctx.exception))
        self.assertEqual(snapshot(folder), before)

    def test_403_quota(self):
        make_job(self.root, JOB_A)
        quota = (403, {"error": {"errors": [{"reason": "storageQuotaExceeded"}]}})
        self.drive.fail = [(200, {"files": []}), (200, {"id": "root"}), (200, {"files": []}), (200, {"id": "jf"}), (200, {"files": []}), quota]
        summary = self.lib().sync_pending()
        self.assertEqual(len(summary["failed"]), 1)
        with self.assertRaises(DriveQuotaError):
            self.drive.fail = [quota]
            self.lib().list_remote()

    def test_network_error_leaves_local_untouched(self):
        folder = make_job(self.root, JOB_A)
        before = snapshot(folder)
        self.drive.fail = [OSError("connection reset")]
        summary = self.lib().sync_pending()
        self.assertEqual([f["job_id"] for f in summary["failed"]], [JOB_A])
        self.assertEqual(snapshot(folder), before)
        self.drive.fail = [OSError("boom")]
        with self.assertRaises(DriveNetworkError):
            self.lib().list_remote()

    def test_one_failed_job_does_not_stop_others(self):
        make_job(self.root, JOB_A)
        make_job(self.root, JOB_B, filename="two.pdf")
        lib = self.lib()
        original = lib._upload_calls = lib.upload_job

        def flaky(job_id, folders=None):
            if job_id == JOB_A:
                raise DriveNetworkError("down")
            return original(job_id, folders)
        lib.upload_job = flaky
        summary = lib.sync_pending()
        self.assertEqual(summary["uploaded"], [JOB_B])
        self.assertEqual([f["job_id"] for f in summary["failed"]], [JOB_A])

    def test_server_error_is_network_error(self):
        self.drive.fail = [(503, {})]
        with self.assertRaises(DriveNetworkError):
            self.lib().list_remote()

    def test_token_never_in_messages(self):
        make_job(self.root, JOB_A)
        self.drive.fail = [(500, {"error": {"message": TOKEN_1}})]
        summary = self.lib().sync_pending()
        self.assertNotIn(TOKEN_1, json.dumps(summary))
        for status, body in ((403, {"error": {"errors": [{"reason": "storageQuotaExceeded"}]}}),
                             (404, {}), (503, {})):
            self.drive.fail = [(status, body)]
            try:
                self.lib().list_remote()
            except DriveError as exc:
                self.assertNotIn(TOKEN_1, str(exc))


if __name__ == "__main__":
    unittest.main()
