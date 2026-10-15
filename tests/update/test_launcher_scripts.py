"""Static checks of the C6 steps in run-ui.ps1 / install.ps1 / Install.bat."""

import re
import unittest
from pathlib import Path

from scholarly_translation import app_paths

ROOT = Path(__file__).resolve().parents[2]


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


class RunUiUpdateTests(unittest.TestCase):
    def setUp(self):
        self.text = read("run-ui.ps1")

    def test_installed_mode_needs_marker_and_current_pointer(self):
        self.assertIn("install.marker", self.text)
        self.assertIn("app\\current.txt", self.text)
        self.assertIn("$installMode", self.text)

    def test_dev_checkout_launch_unchanged(self):
        self.assertIn("& $Exe @PrefixArgs -B -m scholarly_translation.ui.web_ui", self.text)
        self.assertIn("if (-not $installMode)", self.text)

    def test_staged_update_flow_order(self):
        body = self.text[self.text.index("function Apply-StagedUpdate"):]
        prepare = body.index("-Command 'prepare'")
        pip = body.index("pip install --disable-pip-version-check -r")
        switch = body.index("-Command 'switch'")
        self.assertLess(prepare, pip)
        self.assertLess(pip, switch)
        self.assertIn("requirements_changed", body)
        # pip failure keeps the old version
        self.assertIn("-Command 'reject'", body[pip:switch])
        self.assertIn("staged.txt", self.text)

    def test_heartbeat_rollback(self):
        self.assertIn(f"'{app_paths.HEARTBEAT_NAME}'", self.text)
        self.assertIn("$heartbeatTimeoutSeconds = 60", self.text)
        self.assertIn("-Command 'rollback'", self.text)
        self.assertIn("no heartbeat within", self.text)

    def test_rollback_runs_previous_versions_code(self):
        # The version that failed to start must not be trusted to roll itself back.
        rollback = self.text[self.text.index("-Command 'rollback'"):].splitlines()[0]
        self.assertIn("-CodeVersion $previousVersion", rollback)
        self.assertIn("previous.txt", self.text)
        self.assertIn("Push-Location (Join-Path $appDir $CodeVersion)", self.text)

    def test_cli_module_exists_and_is_named(self):
        self.assertIn("scholarly_translation.update.updater", self.text)
        self.assertTrue((ROOT / "scholarly_translation" / "update" / "updater.py").is_file())

    def test_cryptography_in_verify_list_and_requirements(self):
        self.assertIn("'cryptography'", self.text)
        self.assertRegex(read("requirements.txt"), r"(?m)^cryptography==50\.0\.2\s*$")

    def test_pip_only_into_project_environment(self):
        self.assertIn("StartsWith($envRoot", self.text)

    def test_ascii(self):
        self.text.encode("ascii")


class InstallUpdateTests(unittest.TestCase):
    def setUp(self):
        self.text = read("install.ps1")

    def test_zip_layout_steps(self):
        for token in ("release.json", "install.marker", "current.txt", "legacy_outputs.txt",
                      "function Install-AppLayout", "app\\$appVersion", "'data'", "ScholarlyTranslation"):
            self.assertIn(token, self.text)
        self.assertIn(app_paths.INSTALL_MARKER, self.text)
        self.assertIn(app_paths.LEGACY_POINTER_NAME, self.text)

    def test_current_pointer_written_last_and_atomically(self):
        body = self.text[self.text.index("function Install-AppLayout"):]
        body = body[:body.index("function Test-VenvHealthy")]
        self.assertGreater(body.index("'current.txt'"), body.index("Copy-Item"))
        self.assertIn("Move-Item", self.text[self.text.index("function Write-AtomicText"):])

    def test_dev_checkout_path_preserved(self):
        self.assertIn("$runtimeRoot = $projectRoot", self.text)
        self.assertIn("if ($installMode) {", self.text)
        self.assertIn("$launchRoot", self.text)

    def test_version_validated(self):
        self.assertIn(r"'^\d+(\.\d+){0,3}$'", self.text)

    def test_cryptography_verified(self):
        self.assertIn("'cryptography'", self.text)

    def test_install_bat_mentions_zip(self):
        text = read("Install.bat")
        self.assertIn("release.json", text)
        self.assertIn("-File \"%~dp0install.ps1\"", text)
        text.encode("ascii")


if __name__ == "__main__":
    unittest.main()
