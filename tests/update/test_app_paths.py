import tempfile
import unittest
from pathlib import Path

from scholarly_translation import app_paths as ap


class DataRootTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def installed(self, version="1.0.0"):
        root = self.tmp / "ScholarlyTranslation"
        code = root / "app" / version
        code.mkdir(parents=True)
        (root / ap.INSTALL_MARKER).write_text("1")
        return root, code

    def test_dev_checkout_keeps_repo_outputs(self):
        repo = self.tmp / "repo"
        repo.mkdir()
        self.assertEqual(ap.data_root(repo, environ={}), repo / "outputs")
        self.assertIsNone(ap.install_root(repo))
        self.assertEqual(ap.current_version(repo), ap.DEV_VERSION)

    def test_installed_uses_data_folder_and_version_from_folder(self):
        root, code = self.installed("1.2.3")
        self.assertEqual(ap.install_root(code), root)
        self.assertEqual(ap.data_root(code, environ={}), root / "data")
        self.assertEqual(ap.current_version(code), "1.2.3")

    def test_app_folder_without_marker_is_not_an_install(self):
        code = self.tmp / "x" / "app" / "1.0.0"
        code.mkdir(parents=True)
        self.assertIsNone(ap.install_root(code))

    def test_env_override_wins(self):
        root, code = self.installed()
        self.assertEqual(ap.data_root(code, environ={ap.DATA_ROOT_ENV: str(self.tmp / "elsewhere")}),
                         self.tmp / "elsewhere")

    def test_default_install_root_under_localappdata(self):
        self.assertEqual(ap.default_install_root({"LOCALAPPDATA": "C:/L"}), Path("C:/L") / "ScholarlyTranslation")

    def test_heartbeat_written_next_to_marker(self):
        root, code = self.installed()
        path = ap.write_heartbeat(code, clock=lambda: 12.5)
        self.assertEqual(path, root / ap.HEARTBEAT_NAME)
        self.assertEqual(path.read_text().strip(), "12.500")


class MigrationTests(DataRootTests):
    def test_copies_once_never_deletes_and_is_idempotent(self):
        root, code = self.installed()
        legacy = root / "outputs"
        (legacy / "ui" / "job1").mkdir(parents=True)
        (legacy / "ui" / "job1" / "job.json").write_text("{}")
        (legacy / "tooling" / "runtime-venv").mkdir(parents=True)
        (legacy / "tooling" / "runtime-venv" / "big.bin").write_text("x")
        first = ap.migrate_legacy_outputs(code)
        self.assertEqual(first, {"status": "migrated", "copied": 1})
        data = root / "data"
        self.assertEqual((data / "ui" / "job1" / "job.json").read_text(), "{}")
        self.assertFalse((data / "tooling").exists())
        self.assertTrue((legacy / "ui" / "job1" / "job.json").exists())  # old copy kept
        # later user edits in data/ and new legacy files: second run does nothing
        (data / "ui" / "job1" / "job.json").write_text('{"edited": true}')
        (legacy / "ui" / "late.txt").write_text("late")
        self.assertEqual(ap.migrate_legacy_outputs(code)["status"], "already")
        self.assertEqual((data / "ui" / "job1" / "job.json").read_text(), '{"edited": true}')
        self.assertFalse((data / "ui" / "late.txt").exists())

    def test_existing_data_files_never_overwritten(self):
        root, code = self.installed()
        (root / "outputs").mkdir()
        (root / "outputs" / "a.txt").write_text("old")
        (root / "data").mkdir()
        (root / "data" / "a.txt").write_text("new")
        ap.migrate_legacy_outputs(code)
        self.assertEqual((root / "data" / "a.txt").read_text(), "new")

    def test_pointer_file_from_installer_is_followed(self):
        root, code = self.installed()
        old = self.tmp / "old-project" / "outputs"
        old.mkdir(parents=True)
        (old / "k.txt").write_text("k")
        (root / ap.LEGACY_POINTER_NAME).write_text(str(old))
        self.assertEqual(ap.migrate_legacy_outputs(code)["copied"], 1)
        self.assertEqual((root / "data" / "k.txt").read_text(), "k")

    def test_nothing_to_migrate_and_dev_checkout(self):
        root, code = self.installed()
        self.assertEqual(ap.migrate_legacy_outputs(code)["status"], "none")
        self.assertFalse((root / "data" / ap.MIGRATION_MARKER).exists())
        repo = self.tmp / "repo"
        repo.mkdir()
        self.assertEqual(ap.migrate_legacy_outputs(repo)["status"], "not-installed")


if __name__ == "__main__":
    unittest.main()
