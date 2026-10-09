"""COMIC pipeline (audit/contracts/comic_translation.md): input loading, mock end-to-end,
resume without resend, overflow shortening, failure isolation and automatic retry.
Offline: detection/typesetting are stubs, models are fake adapters."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas

from scholarly_translation import comic_pipeline as cp
from scholarly_translation import comic_records as records
from scholarly_translation.model_adapter import TextGenerationResult
from tests.comic_fixtures import LATIN_FONT, make_page

CONFIG = {"schema_version": 1,
          "providers": {"fake": {"type": "openai", "credential_env": "FAKE_TEST_API_KEY"}},
          "models": {role: {"provider": "fake", "model": "fake-vision-1",
                            "capabilities": {"context_window": 200000, "usable_context_tokens": 200000,
                                             "max_output_tokens": 16384}}
                     for role in ("translator", "semantic_reviewer", "chapter_qa")}}


def png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def stub_stages(limit=1000, calls=None):
    """Two fixed candidates per page, a capacity/fit that overflows beyond ``limit`` characters."""
    def detect(image):
        w, h = image.size
        return [{"bbox": [w // 10, h // 10, w // 3, h // 5], "interior": None, "background": [255, 255, 255],
                 "plain_background": True, "line_height": 20.0, "confidence": 0.9},
                {"bbox": [w // 2, h // 2, w * 3 // 4, h * 3 // 5], "interior": None, "background": [255, 255, 255],
                 "plain_background": True, "line_height": 20.0, "confidence": 0.9}]

    def snap(image, box):
        return {"bbox": list(box), "interior": None, "background": [255, 255, 255], "plain_background": True,
                "line_height": 20.0, "confidence": 0.5}

    def fit(region, text, font, rtl, page_height, page_width=None):
        if calls is not None:
            calls.append(("fit", region["region_id"], text))
        return {"style": "bubble", "font_size": 20, "line_height": 24, "lines": [{"text": text, "x": 0, "y": 0,
                                                                                   "width": 10}],
                "box": list(region["bbox"]), "overflow": len(text) > limit}

    def render(image, regions):
        out = image.copy()
        draw = ImageDraw.Draw(out)
        for region in regions:
            draw.rectangle(region["bbox"], fill=(200, 255, 200))
        return out
    return SimpleNamespace(DETECT_VERSION="stub-detect@1", TYPESET_VERSION="stub-typeset@1",
                           detect_candidates=detect, snap_region=snap, font_for=lambda code: LATIN_FONT,
                           min_font_px=lambda h: 12, capacity=lambda region, font, rtl, h: 50, fit=fit,
                           render_page=render)


class FakeConfigured:
    """A 'real' provider stand-in: metered completed results, valid JSON derived from the prompt."""

    def __init__(self, bad_recognitions=0, transport_failures=0, translation_text=None):
        self.mock = cp.MockComicAdapter()
        self.calls = []
        self.bad_recognitions, self.transport_failures = bad_recognitions, transport_failures
        self.translation_text = translation_text

    def kind(self, text):
        return ("recognition" if text.startswith("# Comic Text Recognition")
                else "shorten" if text.startswith("# Comic Shortening") else "translation")

    def generate(self, prompt, model):
        kind = self.kind(str(prompt))
        self.calls.append(kind)
        if self.transport_failures:
            self.transport_failures -= 1
            return TextGenerationResult("failed_transport", None, {"input": 100, "output": 0}, model, 0.0,
                                        error="connection reset")
        if kind == "recognition" and self.bad_recognitions:
            self.bad_recognitions -= 1
            return TextGenerationResult("completed", "I cannot read this page.", {"input": 100, "output": 5},
                                        model, 0.0)
        raw = self.mock.generate(prompt, "mock-translation-1")
        text = raw.text
        if kind == "translation" and self.translation_text:
            body = json.loads(text)
            for item in body["translations"]:
                item["text"] = self.translation_text
            text = json.dumps(body, ensure_ascii=False)
        return TextGenerationResult("completed", text, {"input": 120, "output": 60}, model, 0.0,
                                    observed_provider="fake")


class TempCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write_pages(self, folder, names=("1.png", "2.png"), scale=0.4):
        folder.mkdir(parents=True, exist_ok=True)
        for i, name in enumerate(names):
            image = make_page(scale).image if i % 2 == 0 else Image.new("RGB", (300 + i, 500), (240, 240, 250))
            image.save(folder / name)
        return folder


class InputTests(TempCase):
    def names(self, path, stack=None):
        import contextlib
        with contextlib.ExitStack() as stack:
            return [name for name, _ in cp.open_input(path, stack)]

    def test_natural_sort_folder_ignores_other_files(self):
        folder = self.write_pages(self.root / "in", ["10.png", "2.png", "1.png", "page 3.jpg"])
        (folder / "notes.txt").write_text("x")
        self.assertEqual(self.names(folder), ["1.png", "2.png", "10.png", "page 3.jpg"])

    def test_single_image(self):
        folder = self.write_pages(self.root / "in", ["a.png"])
        self.assertEqual(self.names(folder / "a.png"), ["a.png"])

    def test_cbz_in_memory_with_traversal_and_junk_ignored(self):
        data = png(Image.new("RGB", (50, 60), "white"))
        path = self.root / "book.cbz"
        with zipfile.ZipFile(path, "w") as archive:
            for name in ("ch/10.png", "ch/2.png", "../evil.png", "/abs.png", "C:/drive.png", "ch/notes.txt",
                         "__MACOSX/ch/3.png", "ch\\..\\..\\up.png"):
                archive.writestr(name, data)
        import contextlib
        with contextlib.ExitStack() as stack:
            sources = cp.open_input(path, stack)
            self.assertEqual([n for n, _ in sources], ["2.png", "10.png"])
            image, raw = sources[0][1]()
            self.assertEqual(image.size, (50, 60))
            self.assertEqual(raw, data)
        self.assertFalse((self.root.parent / "evil.png").exists())

    def test_pdf_pages_rendered(self):
        path = self.root / "two.pdf"
        pdf = canvas.Canvas(str(path), pagesize=(200, 300))
        for label in ("one", "two"):
            pdf.drawString(50, 150, label)
            pdf.showPage()
        pdf.save()
        import contextlib
        with contextlib.ExitStack() as stack:
            sources = cp.open_input(path, stack)
            self.assertEqual(len(sources), 2)
            image, raw = sources[1][1]()
            self.assertEqual(image.size, (400, 600))     # 2x render
            self.assertTrue(raw.startswith(b"\x89PNG"))

    def test_bad_inputs(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            with self.assertRaises(cp.ComicPipelineError):
                cp.open_input(self.root / "missing.png", stack)
            bad = self.root / "x.txt"
            bad.write_text("x")
            with self.assertRaises(cp.ComicPipelineError):
                cp.open_input(bad, stack)

    def test_pages_spec(self):
        self.assertEqual(cp.parse_pages("1-3,8"), {1, 2, 3, 8})
        self.assertEqual(cp.parse_pages("2-4,9", 5), {2, 3, 4})
        self.assertIsNone(cp.parse_pages(None))
        for bad in ("a", "3-1", "0", "1-"):
            with self.assertRaises(cp.ComicPipelineError):
                cp.parse_pages(bad)
        with self.assertRaises(cp.ComicPipelineError):
            cp.parse_pages("9", 5)


class MockEndToEndTests(TempCase):
    def test_outputs_and_valid_comic(self):
        src = self.write_pages(self.root / "in")
        before = {p.name: p.read_bytes() for p in src.iterdir()}
        out = self.root / "out"
        notebook = self.root / "nb.json"
        progress = []
        comic = cp.run_comic(src, out, "en", "he", stages=stub_stages(), notebook_path=notebook,
                             progress=lambda *a: progress.append(a))
        for name in ("pages/001.png", "pages/002.png", "originals/001.png", "comic.cbz", "comic.pdf", "comic.json",
                     "review.html"):
            self.assertTrue((out / name).is_file(), name)
        loaded = json.loads((out / "comic.json").read_text(encoding="utf-8"))
        records.validate_comic(loaded)
        self.assertEqual([p["status"] for p in loaded["pages"]], ["rendered", "rendered"])
        region = loaded["pages"][0]["regions"][0]
        self.assertEqual(region["source_text"], "[source 1]")
        self.assertTrue(region["translation"]["text"].startswith("[\u05ea\u05e8\u05d2\u05d5\u05dd-"))
        self.assertEqual(region["translation"]["status"], "ok")
        self.assertEqual(progress[-1], (2, 2, "p002"))
        with zipfile.ZipFile(out / "comic.cbz") as archive:
            self.assertEqual(archive.namelist(), ["001.png", "002.png"])
        self.assertTrue((out / "comic.pdf").read_bytes().startswith(b"%PDF"))
        review = (out / "review.html").read_text(encoding="utf-8")
        self.assertIn('href="originals/001.png"', review)
        self.assertIn('dir="rtl"', review)
        self.assertIn("[source 1]", review)
        self.assertIn("Mock run", review)
        self.assertEqual(json.loads(notebook.read_text(encoding="utf-8")), {"characters": [], "terms": []})
        self.assertEqual({p.name: p.read_bytes() for p in src.iterdir()}, before)     # sources untouched
        translated = Image.open(out / "pages" / "001.png").convert("RGB")
        self.assertEqual(translated.getpixel((region["bbox"][0] + 1, region["bbox"][1] + 1)), (200, 255, 200))
        self.assertEqual(comic["pages"][0]["versions"]["detect"], "stub-detect@1")

    def test_pages_subset_keeps_numbering(self):
        src = self.write_pages(self.root / "in", ["1.png", "2.png", "3.png"])
        comic = cp.run_comic(src, self.root / "out", "en", "he", pages="2-3", stages=stub_stages())
        self.assertEqual([p["page_id"] for p in comic["pages"]], ["p002", "p003"])
        self.assertTrue((self.root / "out" / "pages" / "003.png").is_file())
        self.assertFalse((self.root / "out" / "pages" / "001.png").exists())

    def test_notebook_read_at_start_and_written(self):
        src = self.write_pages(self.root / "in", ["1.png"])
        notebook = self.root / "nb.json"
        notebook.write_text(json.dumps({"characters": [{"name": "Dana", "target_name": "דנה", "gender": "female",
                                                         "note": ""}], "terms": []}), encoding="utf-8")
        comic = cp.run_comic(src, self.root / "out", "en", "he", stages=stub_stages(), notebook_path=notebook)
        self.assertEqual(comic["notebook"]["characters"][0]["target_name"], "דנה")
        self.assertEqual(json.loads(notebook.read_text(encoding="utf-8")), comic["notebook"])

    def test_cli_runs_and_prints_ascii(self):
        import contextlib
        from unittest import mock
        src = self.write_pages(self.root / "in", ["1.png"])
        buffer = io.StringIO()
        with mock.patch.object(cp, "default_stages", lambda: stub_stages()), contextlib.redirect_stdout(buffer):
            code = cp.main([str(src), "--out", str(self.root / "out"), "--source-language", "en", "--target", "he"])
        self.assertEqual(code, 0)
        self.assertIn("pages: 1 (rendered 1)", buffer.getvalue())
        buffer.getvalue().encode("cp1252")

    def test_configured_needs_a_config(self):
        src = self.write_pages(self.root / "in", ["1.png"])
        with self.assertRaises(cp.ComicPipelineError):
            cp.run_comic(src, self.root / "out", "en", "he", model="configured", stages=stub_stages())


class ConfiguredTests(TempCase):
    def setUp(self):
        super().setUp()
        self.config = self.root / "model.json"
        self.config.write_text(json.dumps(CONFIG), encoding="utf-8")
        self.src = self.write_pages(self.root / "in")

    def run_comic(self, model, out="out", stages=None, **extra):
        return cp.run_comic(self.src, self.root / out, "en", "he", model="configured", model_config=self.config,
                            budget_usd=5.0, stages=stages or stub_stages(), adapter_factory=lambda r, d: model,
                            sleep=lambda s: None, **extra)

    def test_rerun_makes_no_new_calls(self):
        model = FakeConfigured()
        first = self.run_comic(model)
        self.assertEqual(model.calls, ["recognition", "translation"] * 2)
        before = (self.root / "out" / "comic.json").read_text(encoding="utf-8")
        again = self.run_comic(model)
        self.assertEqual(len(model.calls), 4)
        self.assertEqual((self.root / "out" / "comic.json").read_text(encoding="utf-8"), before)
        self.assertEqual(first["pages"][0]["regions"][0]["translation"], again["pages"][0]["regions"][0]["translation"])

    def test_overflow_triggers_exactly_one_shorten_call(self):
        model = FakeConfigured()
        calls = []
        comic = self.run_comic(model, stages=stub_stages(limit=12, calls=calls), pages="1")
        self.assertEqual(model.calls, ["recognition", "translation", "shorten"])
        regions = comic["pages"][0]["regions"]
        self.assertEqual([r["translation"]["status"] for r in regions], ["ok", "ok"])
        self.assertTrue(all(r["translation"]["text"].startswith("[\u05e7\u05e6\u05e8-") for r in regions))
        self.assertEqual(len([c for c in calls if c[0] == "fit"]), 4)       # fit, then re-fit of both
        self.assertEqual(comic["pages"][0]["status"], "rendered")

    def test_overflow_that_remains_is_reported(self):
        model = FakeConfigured()
        comic = self.run_comic(model, stages=stub_stages(limit=3), pages="1")
        self.assertEqual(model.calls.count("shorten"), 1)
        regions = comic["pages"][0]["regions"]
        self.assertEqual([r["translation"]["status"] for r in regions], ["overflow", "overflow"])
        self.assertIn("overflow", regions[0]["warnings"])
        self.assertEqual(regions[0]["warnings"].count("overflow"), 1)

    def test_failing_validator_fails_one_page_only(self):
        model = FakeConfigured(bad_recognitions=cp.AUTO_ACCEPT_MAX_STREAK + 1)
        comic = self.run_comic(model)
        self.assertEqual([p["status"] for p in comic["pages"]], ["failed", "rendered"])
        self.assertTrue(any(w.startswith("error: ") for w in comic["pages"][0]["warnings"]))
        self.assertEqual(model.calls.count("recognition"), cp.AUTO_ACCEPT_MAX_STREAK + 2)
        self.assertTrue((self.root / "out" / "pages" / "001.png").is_file())      # failed page keeps its original
        self.assertIn("This page failed", (self.root / "out" / "review.html").read_text(encoding="utf-8"))
        records.validate_comic(comic)
        # A rerun neither resends the failed page's calls nor the finished page's.
        calls = len(model.calls)
        model.bad_recognitions = 0
        again = self.run_comic(model)
        self.assertEqual(again["pages"][1]["status"], "rendered")
        self.assertEqual(again["pages"][0]["status"], "rendered")           # a fresh attempt succeeds
        # Page 1 recognition + translation are new; page 2 is only asked again for its translation,
        # whose prompt now carries page 1's summary (a changed prompt is a new step, never a stale replay).
        self.assertEqual(model.calls[calls:], ["recognition", "translation", "translation"])

    def test_cheap_failure_is_retried_automatically(self):
        slept = []
        model = FakeConfigured(transport_failures=1)
        comic = cp.run_comic(self.src, self.root / "out", "en", "he", model="configured", model_config=self.config,
                             budget_usd=5.0, stages=stub_stages(), adapter_factory=lambda r, d: model,
                             sleep=slept.append, pages="1")
        self.assertEqual(comic["pages"][0]["status"], "rendered")
        self.assertEqual(model.calls, ["recognition", "recognition", "translation"])
        self.assertEqual(slept, [cp.AUTO_RETRY_DELAYS[0]])

    def test_budget_exhaustion_stops_the_remaining_pages(self):
        model = FakeConfigured()
        comic = cp.run_comic(self.src, self.root / "out", "en", "he", model="configured", model_config=self.config,
                             budget_usd=0.0001, stages=stub_stages(), adapter_factory=lambda r, d: model,
                             sleep=lambda s: None)
        self.assertEqual([p["status"] for p in comic["pages"]], ["failed", "failed"])
        self.assertEqual(model.calls, [])


if __name__ == "__main__":
    unittest.main()
