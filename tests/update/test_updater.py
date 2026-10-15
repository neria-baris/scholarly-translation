import json
import tempfile
import unittest
from pathlib import Path

from scholarly_translation import app_paths
from scholarly_translation.update import manifest as mf
from scholarly_translation.update import updater as up
from tests.update import REPO, FakeTransport, make_key, make_release

V1 = {
    "requirements.txt": b"pkg==1\n",
    "scholarly_translation/a.py": b"A1\n",
    "scholarly_translation/b.py": b"B1\n",
}
V2 = {
    "requirements.txt": b"pkg==1\n",
    "scholarly_translation/a.py": b"A2 changed\n",
    "scholarly_translation/b.py": b"B1\n",
    "scholarly_translation/new.py": b"NEW\n",
}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "ScholarlyTranslation"
        self.key, self.pub = make_key()
        self.install("1.0.0", V1)
        (self.root / "install.marker").write_text("1")
        app_paths.atomic_write_text(self.root / "app" / "current.txt", "1.0.0\n")
        self.now = 1_800_000_000.0

    def install(self, version, files):
        for path, body in files.items():
            target = self.root / "app" / version / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)

    def updater(self, transport, **kw):
        return up.Updater(self.root, transport=transport, clock=lambda: self.now,
                          public_key_b64=self.pub, dist_repo=REPO, **kw)

    def transport_v2(self, files=V2, **kw):
        transport = FakeTransport()
        transport.release_routes("1.1.0", files, self.key, **kw)
        return transport

    def current(self):
        return (self.root / "app" / "current.txt").read_text().strip()


class StagingTests(Base):
    def test_stages_new_version_and_reuses_unchanged_files(self):
        transport = self.transport_v2(notes_en="fixes", notes_he="תיקונים")
        updater = self.updater(transport)
        status = updater.check()
        self.assertEqual(status.last_error, "")
        self.assertEqual(status.staged, "1.1.0")
        self.assertEqual(status.notes_en, "fixes")
        self.assertEqual(self.current(), "1.0.0")  # never switched mid-run
        staged = self.root / "app" / "1.1.0"
        self.assertEqual((staged / "scholarly_translation/a.py").read_bytes(), b"A2 changed\n")
        self.assertEqual(sorted(updater.downloaded), ["scholarly_translation/a.py", "scholarly_translation/new.py"])
        self.assertEqual(sorted(updater.reused), ["requirements.txt", "scholarly_translation/b.py"])
        fetched = [u for u in transport.calls if "raw.githubusercontent.com" in u]
        self.assertFalse(any(u.endswith("/b.py") or u.endswith("requirements.txt") for u in fetched))
        self.assertEqual((self.root / "app" / "staged.txt").read_text().strip(), "1.1.0")
        self.assertEqual(up.verify_staged(self.root, self.pub)["status"], "ready")

    def test_tampered_manifest_stages_nothing(self):
        transport = self.transport_v2()
        url = mf.manifest_url(REPO)
        transport.routes[url] = transport.routes[url].replace(b"1.1.0", b"1.2.0")
        status = self.updater(transport).check()
        self.assertTrue(status.last_error)
        self.assertIsNone(status.staged)
        self.assertFalse((self.root / "app" / "staged.txt").exists())

    def test_tampered_file_fails_and_leaves_current_untouched(self):
        transport = self.transport_v2()
        transport.routes[mf.file_url(REPO, "v1.1.0", "scholarly_translation/a.py")] = b"EVIL\n"
        status = self.updater(transport).check()
        self.assertIn("verification", status.last_error)
        self.assertEqual(self.current(), "1.0.0")
        self.assertFalse((self.root / "app" / "1.1.0").exists())
        self.assertFalse((self.root / "app" / "1.1.0.partial").exists())
        self.assertEqual((self.root / "app" / "1.0.0" / "scholarly_translation/a.py").read_bytes(), b"A1\n")

    def test_same_size_tampered_file_fails_hash(self):
        transport = self.transport_v2()
        transport.routes[mf.file_url(REPO, "v1.1.0", "scholarly_translation/a.py")] = b"X" * len(V2["scholarly_translation/a.py"])
        self.assertIn("verification", self.updater(transport).check().last_error)

    def test_failed_download_midway_leaves_no_staged_state(self):
        transport = self.transport_v2()
        transport.routes[mf.file_url(REPO, "v1.1.0", "scholarly_translation/new.py")] = OSError("connection reset")
        status = self.updater(transport).check()
        self.assertTrue(status.last_error)
        self.assertIsNone(status.staged)
        self.assertEqual(self.current(), "1.0.0")
        self.assertEqual(sorted(p.name for p in (self.root / "app").iterdir() if p.is_dir()), ["1.0.0"])

    def test_truncated_download_rejected(self):
        transport = self.transport_v2()
        transport.routes[mf.file_url(REPO, "v1.1.0", "scholarly_translation/new.py")] = b"NE"
        self.assertTrue(self.updater(transport).check().last_error)
        self.assertEqual(self.current(), "1.0.0")

    def test_bad_signature_rejected(self):
        transport = self.transport_v2()
        other, _ = make_key()
        transport.routes[mf.signature_url(REPO)] = make_release("1.1.0", V2, other)[1]
        status = self.updater(transport).check()
        self.assertIn("signature", status.last_error)
        self.assertIsNone(status.staged)

    def test_downgrade_and_same_version_ignored(self):
        for version in ("0.9.0", "1.0.0"):
            transport = FakeTransport()
            transport.release_routes(version, V1, self.key)
            status = self.updater(transport).check()
            self.assertEqual(status.last_error, "")
            self.assertIsNone(status.staged)
            self.assertIsNone(status.available)
            self.assertEqual([u for u in transport.calls if "raw.githubusercontent.com" in u], [])

    def test_disallowed_redirect_host_rejected(self):
        transport = self.transport_v2()
        transport.redirects[mf.manifest_url(REPO)] = "https://evil.example/manifest.json"
        status = self.updater(transport).check()
        self.assertIn("disallowed host", status.last_error)
        self.assertIsNone(status.staged)

    def test_allowed_redirect_host_accepted(self):
        transport = self.transport_v2()
        transport.redirects[mf.manifest_url(REPO)] = "https://objects.githubusercontent.com/abc"
        self.assertEqual(self.updater(transport).check().staged, "1.1.0")

    def test_min_launcher_too_new_not_staged(self):
        transport = self.transport_v2(min_launcher=99)
        status = self.updater(transport).check()
        self.assertIn("newer installer", status.last_error)
        self.assertIsNone(status.staged)

    def test_requirements_change_is_flagged(self):
        files = dict(V2)
        files["requirements.txt"] = b"pkg==2\n"
        self.assertEqual(self.updater(self.transport_v2(files)).check().staged, "1.1.0")
        info = up.verify_staged(self.root, self.pub)
        self.assertEqual(info["status"], "ready")
        self.assertTrue(info["requirements_changed"])

    def test_requirements_unchanged_not_flagged(self):
        self.updater(self.transport_v2()).check()
        self.assertFalse(up.verify_staged(self.root, self.pub)["requirements_changed"])

    def test_launcher_rejects_tampering_after_staging(self):
        self.updater(self.transport_v2()).check()
        (self.root / "app" / "1.1.0" / "scholarly_translation/b.py").write_bytes(b"swapped\n")
        info = up.verify_staged(self.root, self.pub)
        self.assertEqual(info["status"], "invalid")
        (self.root / "app" / "1.1.0" / "scholarly_translation/b.py").write_bytes(V2["scholarly_translation/b.py"])
        (self.root / "app" / "1.1.0" / "scholarly_translation/extra.py").write_bytes(b"x")
        self.assertEqual(up.verify_staged(self.root, self.pub)["status"], "invalid")

    def test_launcher_rejects_wrong_key(self):
        self.updater(self.transport_v2()).check()
        _, other_pub = make_key()
        self.assertEqual(up.verify_staged(self.root, other_pub)["status"], "invalid")


class UpdateDisabledTests(Base):
    def test_disabled_checks_and_reports_but_does_not_stage(self):
        updater = self.updater(self.transport_v2(notes_en="n"))
        updater.set_auto_update(False)
        self.assertFalse(updater.auto_update_enabled())
        status = updater.check()
        self.assertEqual(status.available, "1.1.0")
        self.assertEqual(status.notes_en, "n")
        self.assertIsNone(status.staged)
        self.assertFalse(status.auto_update)
        self.assertFalse((self.root / "app" / "1.1.0").exists())
        self.assertEqual([u for u in updater.transport.calls if "raw.githubusercontent.com" in u], [])

    def test_default_on_and_setting_persists_in_data_root(self):
        updater = self.updater(FakeTransport())
        self.assertTrue(updater.auto_update_enabled())
        updater.set_auto_update(False)
        self.assertTrue((self.root / "data" / "settings" / "update.json").is_file())
        self.assertFalse(self.updater(FakeTransport()).auto_update_enabled())
        updater.set_auto_update(True)
        self.assertTrue(self.updater(FakeTransport()).auto_update_enabled())

    def test_network_failure_is_reported_not_raised(self):
        transport = FakeTransport({mf.manifest_url(REPO): OSError("offline")})
        status = self.updater(transport).check()
        self.assertTrue(status.last_error)
        self.assertEqual(status.last_check, self.now)


class SwitchAndRollbackTests(Base):
    def stage(self):
        self.updater(self.transport_v2(notes_en="n1")).check()

    def test_switch_is_atomic_keeps_previous_and_clears_staged(self):
        self.stage()
        result = up.switch_to_staged(self.root, public_key_b64=self.pub)
        self.assertEqual(result, {"version": "1.1.0", "previous": "1.0.0"})
        self.assertEqual(self.current(), "1.1.0")
        self.assertEqual((self.root / "app" / "previous.txt").read_text().strip(), "1.0.0")
        self.assertFalse((self.root / "app" / "staged.txt").exists())
        self.assertTrue((self.root / "app" / "1.0.0").is_dir())
        status = up.load_status(self.root)
        self.assertEqual(status.updated_to, "1.1.0")
        self.assertEqual(status.updated_notes_en, "n1")
        self.assertFalse(list((self.root / "app").glob("*.tmp")))

    def test_rollback_restores_previous_logs_reason_and_skips_version_next_time(self):
        self.stage()
        up.switch_to_staged(self.root, public_key_b64=self.pub)
        outcome = up.rollback(self.root, "no heartbeat within 60 seconds", clock=lambda: self.now)
        self.assertEqual(outcome, {"rolled_back": True, "from": "1.1.0", "to": "1.0.0"})
        self.assertEqual(self.current(), "1.0.0")
        log = (self.root / "data" / "update.log").read_text()
        self.assertIn("rolled back from 1.1.0 to 1.0.0: no heartbeat within 60 seconds", log)
        status = self.updater(self.transport_v2()).check()
        self.assertIn("previously failed", status.last_error)
        self.assertIsNone(status.staged)

    def test_choose_rollback_target(self):
        self.assertEqual(up.choose_rollback_target("1.1.0", "1.0.0", ["1.0.0", "1.1.0"]), "1.0.0")
        self.assertIsNone(up.choose_rollback_target("1.1.0", "1.0.0", ["1.1.0"]))
        self.assertIsNone(up.choose_rollback_target("1.1.0", None, ["1.1.0"]))
        self.assertIsNone(up.choose_rollback_target("1.1.0", "1.1.0", ["1.1.0"]))

    def test_rollback_without_previous_reports_failure(self):
        outcome = up.rollback(self.root, "x")
        self.assertFalse(outcome["rolled_back"])
        self.assertEqual(self.current(), "1.0.0")

    def test_prune_keeps_current_and_previous_only(self):
        for version in ("0.8.0", "0.9.0"):
            self.install(version, V1)
        app_paths.atomic_write_text(self.root / "app" / "previous.txt", "0.9.0\n")
        (self.root / "app" / "1.2.0.partial").mkdir()
        removed = up.prune_versions(self.root)
        self.assertIn("0.8.0", removed)
        left = sorted(p.name for p in (self.root / "app").iterdir() if p.is_dir())
        self.assertEqual(left, ["0.9.0", "1.0.0"])

    def test_reject_staged_drops_it_and_stays_current(self):
        self.stage()
        up.reject_staged(self.root, "pip failed", clock=lambda: self.now)
        self.assertEqual(self.current(), "1.0.0")
        self.assertFalse((self.root / "app" / "staged.txt").exists())
        self.assertFalse((self.root / "app" / "1.1.0").exists())
        self.assertIn("pip failed", (self.root / "data" / "update.log").read_text())

    def test_cli_prepare_prints_one_json_line(self):
        import contextlib
        import io
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            up.main(["prepare", "--install-root", str(self.root)])
        self.assertEqual(json.loads(buffer.getvalue())["status"], "none")


class IntegrationHelpersTests(Base):
    def test_ui_status_none_for_dev_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(up.ui_status(Path(tmp) / "repo"))
            self.assertIsNone(up.start_background_check(Path(tmp) / "repo"))

    def test_background_thread_runs_check(self):
        code_root = self.root / "app" / "1.0.0"
        thread = up.start_background_check(code_root, transport=self.transport_v2(), public_key_b64=self.pub,
                                           dist_repo=REPO)
        thread.join(10)
        self.assertEqual(up.ui_status(code_root)["staged"], "1.1.0")


if __name__ == "__main__":
    unittest.main()
