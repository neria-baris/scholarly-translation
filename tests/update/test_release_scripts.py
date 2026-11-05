import base64
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scholarly_translation.update import manifest as mf
from tests.update import make_key

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / "release" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_release = _load("build_release")
sign_manifest = _load("sign_manifest")

GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=GIT_ENV)


class AllowListTests(unittest.TestCase):
    def test_excludes_everything_not_runtime(self):
        for path in ("audit/current_state.md", "docs/user/INSTALL_HE.md", "tests/update/test_x.py",
                     "outputs/ui/job/job.json", ".claude/settings.json", "scripts/release/build_release.py",
                     "prompts/p.md", "LICENSE", "LICENSE.txt", "README.md", "AGENTS.md", "CLAUDE.md",
                     "scholarly_translation/__pycache__/a.cpython-312.pyc", "scholarly_translation/ui/__pycache__/x.py",
                     "scholarly_translation/a.pyc", "config.example.json", ".gitignore"):
            self.assertFalse(build_release.is_runtime_path(path), path)

    def test_includes_runtime(self):
        for path in ("scholarly_translation/ui/web_ui.py", "scholarly_translation/ui/ui.html", "requirements.txt",
                     "run-ui.ps1", "install.ps1", "Install.bat", "Run Scholarly Translation.vbs"):
            self.assertTrue(build_release.is_runtime_path(path), path)

    def test_every_allowed_path_passes_manifest_path_rules(self):
        for path in mf.RUNTIME_ROOT_FILES:
            self.assertEqual(mf.normalize_path(path), path)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.repo = tmp / "private"
        self.dist = tmp / "dist"
        self.dist.mkdir()
        (self.dist / ".git").mkdir()
        (self.dist / "site").mkdir()
        (self.dist / "site" / "index.html").write_text("keep me")
        files = {
            "scholarly_translation/__init__.py": "",
            "scholarly_translation/ui/web_ui.py": "x = 1\n",
            "requirements.txt": "pkg==1\n",
            "run-ui.ps1": "# launcher\n",
            "install.ps1": "# install\n",
            "Install.bat": "@echo off\n",
            "Run Scholarly Translation.vbs": "' vbs\n",
            "LICENSE": "secret license\n",
            "audit/current_state.md": "private\n",
            "docs/a.md": "private\n",
            "tests/t.py": "private\n",
            "outputs/ui/x.json": "private\n",
            ".claude/settings.json": "private\n",
        }
        for name, text in files.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode())
        git(self.repo, "init", "-q")
        git(self.repo, "add", "-f", "-A")
        git(self.repo, "commit", "-q", "-m", "init")

    def args(self, **kw):
        base = dict(version="1.2.0", dist_checkout=str(self.dist), out_dir=None, dist_repo="O/R",
                    min_launcher=1, notes_he_file=None, notes_en_file=None, execute=False, no_exe=True)
        base.update(kw)
        return SimpleNamespace(**base)

    def run_release(self, **kw):
        lines = []
        code = build_release.run(self.args(**kw), repo=self.repo, out=lines.append)
        return code, lines

    def test_dry_run_writes_nothing_and_prints_commands(self):
        code, lines = self.run_release()
        self.assertEqual(code, 0)
        text = "\n".join(lines)
        self.assertIn("Dry run", text)
        self.assertIn("git tag v1.2.0", text)
        self.assertIn("gh release create v1.2.0 --repo O/R", text)
        self.assertIn("sign_manifest.py", text)
        self.assertFalse((self.dist / "scholarly_translation").exists())
        self.assertFalse(any("git push" in l and "--force" in l for l in lines))

    def test_execute_exports_allow_list_manifest_and_zip(self):
        code, _ = self.run_release(execute=True)
        self.assertEqual(code, 0)
        exported = sorted(p.relative_to(self.dist).as_posix() for p in self.dist.rglob("*")
                          if p.is_file() and ".git" not in p.parts)
        self.assertEqual(exported, ["Install.bat", "Run Scholarly Translation.vbs", "install.ps1", "requirements.txt",
                                    "run-ui.ps1", "scholarly_translation/__init__.py",
                                    "scholarly_translation/ui/web_ui.py", "site/index.html"])
        out_dir = self.dist.parent / f"{self.dist.name}-release-1.2.0"
        manifest = mf.parse_manifest((out_dir / "manifest.json").read_bytes())
        self.assertEqual(manifest.version, "1.2.0")
        self.assertEqual(manifest.requirements_sha256, manifest.files["requirements.txt"].sha256)
        for forbidden in ("audit", "docs", "tests", "outputs", ".claude", "LICENSE"):
            self.assertFalse(any(p.startswith(forbidden) for p in manifest.files), forbidden)
        with zipfile.ZipFile(out_dir / "ScholarlyTranslation-Setup.zip") as archive:
            names = set(archive.namelist())
            self.assertEqual(json.loads(archive.read("release.json")), {"version": "1.2.0"})
        self.assertEqual(names, set(manifest.files) | {"release.json"})

    def test_dirty_runtime_path_fails(self):
        (self.repo / "scholarly_translation" / "ui" / "web_ui.py").write_text("x = 2\n")
        with self.assertRaises(build_release.ReleaseError):
            self.run_release()

    def test_untracked_runtime_file_fails_but_private_dirt_is_ignored(self):
        (self.repo / "audit" / "current_state.md").write_text("changed\n")
        self.assertEqual(self.run_release()[0], 0)
        (self.repo / "scholarly_translation" / "new.py").write_text("y\n")
        with self.assertRaises(build_release.ReleaseError):
            self.run_release()

    def test_dist_checkout_inside_repo_refused(self):
        inner = self.repo / "dist"
        inner.mkdir()
        with self.assertRaises(build_release.ReleaseError):
            self.run_release(dist_checkout=str(inner))

    def commit_template(self, files):
        for name, text in files.items():
            path = self.repo / "scripts" / "release" / "dist" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode())
        git(self.repo, "add", "-f", "-A")
        git(self.repo, "commit", "-q", "-m", "template")

    def test_template_files_copied_with_repo_filled_but_not_in_manifest(self):
        self.commit_template({"README.md": "Download: https://github.com/{{DIST_REPO}}/releases\n",
                              ".gitignore": ".venv/\n"})
        code, _ = self.run_release(execute=True)
        self.assertEqual(code, 0)
        self.assertEqual((self.dist / "README.md").read_text(), "Download: https://github.com/O/R/releases\n")
        self.assertEqual((self.dist / ".gitignore").read_text(), ".venv/\n")
        out_dir = self.dist.parent / f"{self.dist.name}-release-1.2.0"
        manifest = mf.parse_manifest((out_dir / "manifest.json").read_bytes())
        self.assertNotIn("README.md", manifest.files)
        self.assertFalse(any(p.startswith("scripts") for p in manifest.files))
        self.assertFalse((out_dir / build_release.SETUP_EXE_NAME).exists())  # --no-exe

    def test_template_may_not_replace_app_files(self):
        self.commit_template({"run-ui.ps1": "# hijack\n"})
        with self.assertRaises(build_release.ReleaseError):
            self.run_release()

    def test_owner_commands_upload_exe_only_when_built(self):
        _, lines = self.run_release(no_exe=False)
        upload = [l for l in lines if "gh release create" in l][0]
        self.assertIn(build_release.SETUP_EXE_NAME, upload)
        _, lines = self.run_release()
        upload = [l for l in lines if "gh release create" in l][0]
        self.assertNotIn(build_release.SETUP_EXE_NAME, upload)
        self.assertIn(build_release.SETUP_ZIP_NAME, upload)

    @unittest.skipUnless(build_release.find_csc(), "csc.exe (.NET Framework 4) not available")
    def test_execute_builds_setup_exe_embedding_the_zip(self):
        # A neutral file name: antivirus products (seen: Sophos Intercept X) may
        # hold a fresh unsigned "*Setup*.exe" and deny reads; content is what counts.
        with mock.patch.object(build_release, "SETUP_EXE_NAME", "built-launcher.exe"):
            code, _ = self.run_release(execute=True, no_exe=False)
        self.assertEqual(code, 0)
        out_dir = self.dist.parent / f"{self.dist.name}-release-1.2.0"
        exe_path = out_dir / "built-launcher.exe"
        zip_size = (out_dir / build_release.SETUP_ZIP_NAME).stat().st_size
        self.assertGreater(exe_path.stat().st_size, zip_size)
        try:
            exe = exe_path.read_bytes()
        except PermissionError:
            self.skipTest("the built EXE is held by an antivirus scan; size check passed")
        self.assertEqual(exe[:2], b"MZ")
        zip_bytes = (out_dir / build_release.SETUP_ZIP_NAME).read_bytes()
        self.assertIn(zip_bytes, exe)  # embedded verbatim as the payload resource
        self.assertIn("1.2.0.0".encode("utf-16-le"), exe)  # file version resource


class ReleaseTreeIsSelfContainedTests(unittest.TestCase):
    """The installed app contains only the runtime allow-list. Anything the app
    reads from outside it (e.g. prompts/ at the repo root) works in a checkout
    but breaks every real install, so verify from a copy of exactly that set."""

    def test_allow_listed_files_alone_pass_the_installer_verification(self):
        listed = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                                cwd=REPO_ROOT, capture_output=True, check=True).stdout.decode("utf-8").split("\0")
        names = [n for n in listed if n and build_release.is_runtime_path(n) and (REPO_ROOT / n).is_file()]
        with tempfile.TemporaryDirectory() as tmp:
            for name in names:
                target = Path(tmp) / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((REPO_ROOT / name).read_bytes())
            code = ("import scholarly_translation, sys; "
                    "from pathlib import Path; "
                    "assert Path(scholarly_translation.__file__).resolve().is_relative_to(Path.cwd().resolve()), "
                    "scholarly_translation.__file__; "
                    "from scholarly_translation.learning.install_check import verify_learning_assets; "
                    "verify_learning_assets(); "
                    "import scholarly_translation.ui.web_ui; "
                    # Scanned books: with every system Tesseract hidden, the copy finds and runs its own.
                    "import os, subprocess; from scholarly_translation.sources import scanned_ocr; "
                    "engine = scanned_ocr.find_tesseract(); "
                    "assert os.name != 'nt' or (engine and Path(engine).resolve().is_relative_to(Path.cwd().resolve())), engine; "
                    "assert os.name != 'nt' or subprocess.run([engine, '--version'], capture_output=True).returncode == 0; "
                    "assert os.name != 'nt' or all(scanned_ocr.ocr_ready(l)[0] for l in ('en', 'fr', 'ja')); "
                    "print('ok')")
            env = {k: v for k, v in os.environ.items()
                   if k not in ("PYTHONPATH", "SCHOLARLY_DATA_ROOT", "SCHOLARLY_TESSERACT")}
            if os.name == "nt":
                hidden = str(Path(tmp) / "no-system-tesseract")
                env.update({"ProgramFiles": hidden, "ProgramFiles(x86)": hidden, "LOCALAPPDATA": hidden,
                            "PATH": os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")})
            result = subprocess.run([sys.executable, "-B", "-c", code], cwd=tmp, env=env,
                                    capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        self.assertIn("ok", result.stdout)


class SetupExeSourceTests(unittest.TestCase):
    def test_launcher_runs_install_ps1_without_admin_rights(self):
        source = (REPO_ROOT / "scripts" / "release" / "setup_exe" / "SetupLauncher.cs").read_text(encoding="utf-8")
        self.assertIn('"install.ps1"', source)
        self.assertIn('"release.json"', source)
        self.assertIn("-ExecutionPolicy Bypass -File", source)
        self.assertIn("StartsWith(root", source)  # zip-slip guard
        manifest = (REPO_ROOT / "scripts" / "release" / "setup_exe" / "app.manifest").read_text(encoding="utf-8")
        self.assertIn('level="asInvoker"', manifest)

    def test_dist_template_stores_files_byte_for_byte(self):
        # Updates hash raw.githubusercontent.com files against the manifest; a
        # line-ending conversion in the distribution repo would break them.
        attributes = (REPO_ROOT / "scripts" / "release" / "dist" / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("* -text", attributes.splitlines())

    def test_file_version_is_four_numeric_parts(self):
        self.assertEqual(build_release._file_version("1.2"), "1.2.0.0")
        self.assertEqual(build_release._file_version("1.0.3.4"), "1.0.3.4")


class SigningTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_generate_key_outside_repo_and_sign_roundtrip(self):
        out = self.tmp / "keys" / "release.key"
        public = sign_manifest.generate_key(out)
        self.assertTrue(out.is_file())
        self.assertEqual((Path(str(out) + ".pub")).read_text().strip(), public)
        manifest = self.tmp / "manifest.json"
        manifest.write_bytes(b'{"schema": 1}\n')
        sig_path = sign_manifest.sign_file(manifest, out)
        mf.verify_signature(manifest.read_bytes(), sig_path.read_bytes(), public)
        manifest.write_bytes(b'{"schema": 2}\n')
        with self.assertRaises(mf.ManifestError):
            mf.verify_signature(manifest.read_bytes(), sig_path.read_bytes(), public)

    def test_generate_key_refuses_path_inside_repo(self):
        for inside in (REPO_ROOT / "release.key", REPO_ROOT / "scripts" / "k" / "release.key"):
            with self.assertRaises(sign_manifest.SigningError):
                sign_manifest.generate_key(inside)
            self.assertFalse(inside.exists())
        self.assertEqual(sign_manifest.main(["--generate-key", str(REPO_ROOT / "x.key")]), 2)
        self.assertFalse((REPO_ROOT / "x.key").exists())

    def test_generate_key_does_not_overwrite(self):
        out = self.tmp / "k"
        sign_manifest.generate_key(out)
        with self.assertRaises(sign_manifest.SigningError):
            sign_manifest.generate_key(out)

    def test_signing_with_key_inside_repo_refused(self):
        manifest = self.tmp / "manifest.json"
        manifest.write_bytes(b"{}")
        with self.assertRaises(sign_manifest.SigningError):
            sign_manifest.sign_file(manifest, REPO_ROOT / "requirements.txt")


if __name__ == "__main__":
    unittest.main()
