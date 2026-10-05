"""Static, offline checks of the Windows installer/launcher scripts.

These tests only read script text; they never run the installer, install
Python or packages, or touch the network.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Distribution name -> import name, where they differ.
IMPORT_NAMES = {"pillow": "PIL"}


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _requirement_imports() -> set:
    names = set()
    for line in _read("requirements.txt").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        dist = re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0].strip()
        names.add(IMPORT_NAMES.get(dist.lower(), dist.replace("-", "_")))
    return names


def _verify_modules(text: str) -> set:
    match = re.search(r"\$verifyModules\s*=\s*@\(([^)]*)\)", text)
    if not match:
        raise AssertionError("$verifyModules list not found")
    return set(re.findall(r"'([^']+)'", match.group(1)))


def _function_body(text: str, name: str) -> str:
    match = re.search(r"function\s+" + re.escape(name) + r"\s*\{", text)
    if not match:
        raise AssertionError(f"function {name} not found")
    depth = 0
    for index in range(match.end() - 1, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[match.end():index]
    raise AssertionError(f"unbalanced braces in {name}")


class InstallScriptTests(unittest.TestCase):
    def setUp(self):
        self.text = _read("install.ps1")

    def test_ascii_only(self):
        # Windows PowerShell 5.1 reads BOM-less scripts in the ANSI code page.
        self.text.encode("ascii")
        _read("run-ui.ps1").encode("ascii")
        _read("Install.bat").encode("ascii")

    def test_winget_per_user_install(self):
        self.assertIn("Get-Command 'winget'", self.text)
        self.assertIn("'Python.Python.3.12'", self.text)
        for token in ("'install'", "'-e'", "'--id'", "'--scope', 'user'", "'--silent'",
                      "'--accept-package-agreements'", "'--accept-source-agreements'"):
            self.assertIn(token, self.text)

    def test_python_org_fallback_https_quiet_per_user(self):
        urls = re.findall(r"'(https?://[^']*python\.org/ftp/[^']*)'", self.text)
        self.assertTrue(urls, "pinned python.org installer URL missing")
        for url in urls:
            self.assertTrue(re.fullmatch(
                r"https://www\.python\.org/ftp/python/3\.1[0-9]\.\d+/python-3\.1[0-9]\.\d+-amd64\.exe", url), url)
        self.assertIn("SecurityProtocolType]::Tls12", self.text)
        self.assertIn("$env:TEMP", self.text)
        self.assertIn("Get-AuthenticodeSignature", self.text)
        self.assertIn("Python Software Foundation", self.text)
        for token in ("'/quiet'", "'InstallAllUsers=0'", "'PrependPath=1'", "'Include_launcher=1'",
                      "'InstallLauncherAllUsers=0'", "'Include_test=0'"):
            self.assertIn(token, self.text)
        self.assertNotIn("InstallAllUsers=1", self.text)
        self.assertNotIn("RunAs", self.text)

    def test_winget_tried_before_download(self):
        body = _function_body(self.text, "Install-PythonForUser")
        self.assertLess(body.index("Install-PythonWithWinget"), body.index("Install-PythonFromPythonOrg"))
        self.assertGreaterEqual(body.count("Update-SessionPath"), 2)
        self.assertGreaterEqual(body.count("Find-Python"), 2)

    def test_path_refresh_from_registry(self):
        body = _function_body(self.text, "Update-SessionPath")
        self.assertIn("GetEnvironmentVariable('Path', 'Machine')", body)
        self.assertIn("GetEnvironmentVariable('Path', 'User')", body)
        self.assertIn("$env:Path", body)

    def test_find_python_probes_explicit_versions_first(self):
        body = _function_body(self.text, "Find-Python")
        self.assertIn("'3.13', '3.12', '3.11', '3.10'", body)
        self.assertIn("@('py', @(\"-$version\"))", body)
        explicit = body.index("'3.13', '3.12'")
        self.assertLess(explicit, body.index("@('python', @())"))
        self.assertLess(explicit, body.index("@('py', @())"))
        self.assertLess(body.index("Get-PerUserPythonPaths"), body.index("@('python', @())"))
        probe = _function_body(self.text, "Test-PythonCandidate")
        self.assertIn("sys.executable", probe)
        self.assertIn("$minor -lt 10", probe)

    def test_per_user_install_dirs_probed(self):
        body = _function_body(self.text, "Get-PerUserPythonPaths")
        self.assertIn("Join-Path $env:LOCALAPPDATA 'Programs\\Python'", body)
        self.assertIn("'^Python3\\d+$'", body)

    def test_missing_python_triggers_install_and_retry(self):
        body = _function_body(self.text, "Run-Install")
        self.assertIn("Install-PythonForUser", body)
        self.assertIn("$retryButton.Enabled = $true", body)
        self.assertNotIn("Install it from https://www.python.org/downloads/ (check", body)

    def test_ui_stays_responsive(self):
        self.assertIn("[System.Windows.Forms.Application]::DoEvents()", _function_body(self.text, "Invoke-ProcessWithUi"))
        self.assertIn("[System.Windows.Forms.Application]::DoEvents()", _function_body(self.text, "Write-Log"))

    def test_pip_upgraded_before_requirements(self):
        body = _function_body(self.text, "Run-Install")
        upgrade = body.index("'--upgrade', 'pip'")
        self.assertLess(upgrade, body.index("'-r', $requirements"))

    def test_unhealthy_venv_fallback_kept(self):
        body = _function_body(self.text, "Run-Install")
        self.assertIn("outputs\\tooling\\runtime-venv", body)
        self.assertIn("Test-VenvHealthy", body)

    def test_verify_list_matches_requirements(self):
        self.assertEqual(_verify_modules(self.text), _requirement_imports())
        self.assertIn("import $($verifyModules -join ', ')", self.text)


class RunUiScriptTests(unittest.TestCase):
    def setUp(self):
        self.text = _read("run-ui.ps1")

    def test_no_python39_candidate(self):
        self.assertNotIn("python39", self.text.lower())

    def test_explicit_versions_before_bare_commands(self):
        explicit = self.text.index("'3.13', '3.12', '3.11', '3.10'")
        self.assertLess(self.text.index(".venv\\Scripts\\python.exe"), explicit)
        self.assertLess(explicit, self.text.index("@('python', @())"))
        self.assertLess(explicit, self.text.index("@('py', @())"))
        self.assertIn("Programs\\Python", self.text)
        self.assertIn("-ge 310", self.text)

    def test_checks_version_and_requirements(self):
        self.assertIn("sys.version_info >= (3, 10)", self.text)
        self.assertEqual(_verify_modules(self.text), _requirement_imports())


class InstallBatAndDocTests(unittest.TestCase):
    def test_install_bat_checks_powershell_and_pauses(self):
        text = _read("Install.bat")
        self.assertIn("where powershell.exe", text)
        self.assertIn("pause", text)
        self.assertIn('-File "%~dp0install.ps1"', text)

    def test_install_doc_describes_automatic_python(self):
        text = _read("INSTALL_HE.md")
        self.assertIn("winget", text)
        self.assertIn("python.org", text)
        self.assertIn("אינטרנט", text)
        self.assertIn("pip", text)
        self.assertNotIn("אין התקנת תוכנה חיצונית לא-Python", text)


if __name__ == "__main__":
    unittest.main()
