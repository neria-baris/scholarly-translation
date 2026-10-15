import base64
import json
import unittest

from scholarly_translation.update import manifest as mf
from tests.update import make_key, make_release

FILES = {
    "requirements.txt": b"pkg==1\n",
    "scholarly_translation/a.py": b"print('a')\n",
}


class SignatureTests(unittest.TestCase):
    def setUp(self):
        self.key, self.pub = make_key()
        self.data, self.sig = make_release("1.1.0", FILES, self.key)

    def test_valid_manifest_loads(self):
        manifest = mf.load_verified_manifest(self.data, self.sig, self.pub)
        self.assertEqual(manifest.version, "1.1.0")
        self.assertEqual(manifest.tag, "v1.1.0")
        self.assertEqual(set(manifest.files), set(FILES))

    def test_tampered_manifest_rejected(self):
        tampered = self.data.replace(b"1.1.0", b"9.9.9")
        with self.assertRaises(mf.ManifestError):
            mf.load_verified_manifest(tampered, self.sig, self.pub)

    def test_bad_signature_rejected(self):
        other, _ = make_key()
        _, bad_sig = make_release("1.1.0", FILES, other)
        with self.assertRaises(mf.ManifestError):
            mf.load_verified_manifest(self.data, bad_sig, self.pub)
        with self.assertRaises(mf.ManifestError):
            mf.load_verified_manifest(self.data, b"not base64 !!", self.pub)

    def test_placeholder_public_key_never_verifies(self):
        with self.assertRaises(mf.ManifestError):
            mf.load_verified_manifest(self.data, self.sig)

    def test_requirements_hash_must_match_file(self):
        doc = json.loads(self.data)
        doc["requirements_sha256"] = "0" * 64
        with self.assertRaises(mf.ManifestError):
            mf.parse_manifest(json.dumps(doc).encode())


class PathTests(unittest.TestCase):
    def test_rejects_unsafe_paths(self):
        for bad in ("../x.py", "scholarly_translation/../../x", "/etc/passwd", "C:/x.py", "C:\\x.py",
                    "scholarly_translation\\..\\x", "scholarly_translation//a.py", "", "scholarly_translation/./a.py",
                    "audit/notes.md", "tests/a.py", "evil.exe", "scholarly_translation/a:stream",
                    "\\\\server\\share\\x"):
            with self.assertRaises(mf.ManifestError, msg=bad):
                mf.normalize_path(bad)

    def test_backslashes_normalised(self):
        self.assertEqual(mf.normalize_path("scholarly_translation\\ui\\ui.js"), "scholarly_translation/ui/ui.js")
        self.assertEqual(mf.normalize_path("Run Scholarly Translation.vbs"), "Run Scholarly Translation.vbs")

    def test_manifest_with_traversal_rejected(self):
        key, pub = make_key()
        doc = json.loads(make_release("1.1.0", FILES, key)[0])
        doc["files"]["scholarly_translation/../../evil"] = doc["files"]["requirements.txt"]
        with self.assertRaises(mf.ManifestError):
            mf.parse_manifest(json.dumps(doc).encode())


class VersionAndUrlTests(unittest.TestCase):
    def test_compare(self):
        self.assertEqual(mf.compare_versions("1.2.0", "1.10.0"), -1)
        self.assertEqual(mf.compare_versions("1.2", "1.2.0"), 0)
        self.assertEqual(mf.compare_versions("2.0.0", "1.9.9"), 1)
        with self.assertRaises(mf.ManifestError):
            mf.parse_version("1.2.x")

    def test_allowed_hosts(self):
        for ok in ("https://github.com/o/r/releases/latest/download/manifest.json",
                   "https://objects.githubusercontent.com/x",
                   "https://raw.githubusercontent.com/o/r/v1/a.py",
                   "https://release-assets.githubusercontent.com/x"):
            self.assertTrue(mf.is_allowed_url(ok), ok)
        for bad in ("http://github.com/x", "https://evil.example/x", "https://github.com.evil.example/x",
                    "https://user@github.com/x", "https://github.com:8443/x", "https://gist.githubusercontent.com/x",
                    "file:///C:/x"):
            self.assertFalse(mf.is_allowed_url(bad), bad)

    def test_urls_use_repo_constant(self):
        self.assertIn(mf.DIST_REPO, mf.manifest_url())
        self.assertTrue(mf.signature_url().endswith("manifest.json.sig"))
        self.assertEqual(mf.file_url("o/r", "v1.0.0", "scholarly_translation/a b.py"),
                         "https://raw.githubusercontent.com/o/r/v1.0.0/scholarly_translation/a%20b.py")


if __name__ == "__main__":
    unittest.main()
