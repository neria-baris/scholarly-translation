"""The bundled Tesseract engine: pinned files, licenses, lookup order and a real run."""
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scholarly_translation.sources import scanned_ocr

BUNDLE = scanned_ocr.BUNDLED_TESSERACT.parent
SPEC = json.loads((BUNDLE / "sources.json").read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class BundleContentsTests(unittest.TestCase):
    def test_every_pinned_file_is_present_with_its_hash(self):
        self.assertEqual(len(SPEC["files"]), 27)
        names = {entry["path"] for entry in SPEC["files"]}
        self.assertIn("tesseract.exe", names)
        self.assertIn("libtesseract-5.dll", names)
        for entry in SPEC["files"]:
            path = BUNDLE / entry["path"]
            self.assertEqual(path.stat().st_size, entry["size"], entry["path"])
            self.assertEqual(sha256(path), entry["sha256"], entry["path"])

    def test_no_unlisted_binaries(self):
        listed = {entry["path"] for entry in SPEC["files"]}
        binaries = {p.name for p in BUNDLE.iterdir() if p.suffix.lower() in (".exe", ".dll")}
        self.assertEqual(binaries, listed)

    def test_license_texts_for_every_component(self):
        licenses = BUNDLE / "LICENSES"
        for component in ("tesseract", "leptonica", "openssl", "libiconv", "jbigkit", "gcc-libs", "giflib",
                          "lz4", "zlib", "libpng", "libtiff", "libjpeg-turbo", "libwebp", "openjpeg",
                          "libarchive", "zstd", "xz", "bzip2", "expat", "lerc", "libb2", "libdeflate",
                          "libwinpthread"):
            texts = [p for p in (licenses / component).rglob("*") if p.is_file() and p.stat().st_size > 0]
            self.assertTrue(texts, component)
        self.assertIn("GCC RUNTIME LIBRARY EXCEPTION", (licenses / "gcc-libs" / "COPYING.RUNTIME").read_text(encoding="utf-8"))
        sources = SPEC["copyleft_sources"]
        self.assertEqual(set(sources) - {"note"}, {"libiconv-1.17.tar.gz", "jbigkit-2.1.tar.gz"})

    def test_bundled_language_models_cover_every_ocr_language(self):
        for language in ("en", "fr", "ja"):
            self.assertEqual(scanned_ocr.tessdata_for(language, str(scanned_ocr.BUNDLED_TESSERACT)),
                             str(scanned_ocr.BUNDLED_TESSDATA))


class LookupOrderTests(unittest.TestCase):
    def test_explicit_override_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "tesseract.exe"
            custom.write_bytes(b"")
            with mock.patch.dict(os.environ, {"SCHOLARLY_TESSERACT": str(custom)}):
                self.assertEqual(scanned_ocr.find_tesseract(), str(custom))

    @unittest.skipUnless(os.name == "nt", "the bundled engine is a Windows build")
    def test_bundled_engine_used_without_any_system_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"PATH": tmp, "ProgramFiles": tmp, "ProgramFiles(x86)": tmp, "LOCALAPPDATA": tmp}
            with mock.patch.dict(os.environ, env, clear=False):
                os.environ.pop("SCHOLARLY_TESSERACT", None)
                self.assertEqual(scanned_ocr.find_tesseract(), str(scanned_ocr.BUNDLED_TESSERACT))
                self.assertEqual(scanned_ocr.ocr_ready("en")[0], True)


@unittest.skipUnless(os.name == "nt", "the bundled engine is a Windows build")
class BundledEngineRunsTests(unittest.TestCase):
    def test_reads_an_english_page(self):
        from PIL import Image, ImageDraw, ImageFont
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "page.png"
            canvas = Image.new("L", (1400, 220), 255)
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/times.ttf", 52)
            except OSError:
                self.skipTest("Times New Roman is not available")
            ImageDraw.Draw(canvas).text((40, 60), "The history of reading", font=font, fill=0)
            canvas.save(image)
            result = subprocess.run([str(scanned_ocr.BUNDLED_TESSERACT), str(image), "stdout", "-l", "eng",
                                     "--tessdata-dir", str(scanned_ocr.BUNDLED_TESSDATA)],
                                    capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertIn("history of reading", result.stdout.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
