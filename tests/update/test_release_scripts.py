import base64
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

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
                    min_launcher=1, notes_he_file=None, notes_en_file=None, execute=False)
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
