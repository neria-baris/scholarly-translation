"""SCANNED-OCR (audit/contracts/scanned_ocr_vision.md): scanned PDFs in the simple
flow, local Tesseract plus a journaled vision review. Offline: fake model adapters;
the end-to-end tests need a local Tesseract and are skipped without one."""
import io
import json
import re
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from scholarly_translation import job_blocks, pdf_extract, scanned_ocr
from scholarly_translation.document_draft import DocumentJobs
from scholarly_translation.model_adapter import (
    AnthropicTextGenerationAdapter, ImagePrompt, OpenAICompatibleTextGenerationAdapter,
    OpenAITextGenerationAdapter, TextGenerationResult,
)
from scholarly_translation.model_config import ProviderDefinition
from scholarly_translation.source_reading import OCR_VISION_STAGE, build_readings

TESSERACT = scanned_ocr.find_tesseract()
LINES = ["The theory of numbers is old.", "Every even number greater than two", "is the sum of two primes."]
CONFIG = {"schema_version": 1,
          "providers": {"fake": {"type": "openai", "credential_env": "FAKE_TEST_API_KEY"}},
          "models": {role: {"provider": "fake", "model": "fake-vision-1",
                            "capabilities": {"context_window": 200000, "usable_context_tokens": 200000,
                                             "max_output_tokens": 16384}}
                     for role in ("translator", "semantic_reviewer", "chapter_qa")}}


def make_scanned_pdf(path, pages=1):
    font = None
    for candidate in ("C:/Windows/Fonts/times.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"):
        try:
            font = ImageFont.truetype(candidate, 44)
            break
        except OSError:
            continue
    pdf = canvas.Canvas(str(path), pagesize=(612, 792))
    for _ in range(pages):
        image = Image.new("L", (1700, 2200), 255)
        draw = ImageDraw.Draw(image)
        for i, line in enumerate(LINES):
            draw.text((180, 200 + 70 * i), line, fill=0, font=font or ImageFont.load_default())
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        pdf.drawImage(ImageReader(buffer), 0, 0, 612, 792)
        pdf.showPage()
    pdf.save()


def result(text, model="fake-vision-1", status="completed"):
    return TextGenerationResult(status, text, {"input": 100, "output": 50}, model, 0.0, observed_provider="fake")


class FakeModel:
    """Vision review returns corrected page text; translation returns Hebrew."""
    def __init__(self, vision_text="The theory of numbers is old.\n\nEvery even number greater than two is the "
                                   "sum of two primes ⟦p + q⟧.", fail_vision=False):
        self.vision_text, self.fail_vision, self.vision_calls, self.translation_calls = vision_text, fail_vision, [], 0

    def generate(self, prompt, model):
        if isinstance(prompt, ImagePrompt):
            self.vision_calls.append(prompt)
            if self.fail_vision:
                return TextGenerationResult("failed_empty_response", None, {"input": 100, "output": 0}, model, 0.0)
            return result(self.vision_text)
        if "TARGET_UNIT_IDS" in prompt:
            self.translation_calls += 1
            suffix = prompt.suffix if hasattr(prompt, "suffix") else prompt
            marker = "TARGET_UNIT_IDS (translate exactly these ids, in exactly this order, each exactly once): "
            ids = json.loads(suffix[suffix.index(marker) + len(marker):].split("\n", 1)[0])
            sources = {}
            for line in str(prompt).splitlines():
                if line.startswith('{"unit_id"'):
                    item = json.loads(line)
                    sources[item["unit_id"]] = item["source_text"]
            # Like a real translator: keep every protected formula of the unit.
            return result(json.dumps([{"unit_id": u, "translation": " ".join(
                ["תורת המספרים"] + re.findall("⟦[^⟧]*⟧", sources.get(u, ""))), "translation_note": None}
                for u in ids], ensure_ascii=False))
        return result('{"ops": [], "chapter_summary": "s", "story_so_far": "s"}')


class UnitTests(unittest.TestCase):
    def entry(self):
        words, text, cursor = [], [], 0
        for i, token in enumerate("The theory of numbers".split()):
            words.append({"text": token, "confidence": 91.0, "source_char_start": cursor,
                          "source_char_end": cursor + len(token), "pixel_bbox": [10 + i * 100, 10, 90 + i * 100, 40],
                          "pdf_bbox": [10 + i * 100, 10, 90 + i * 100, 40]})
            text.append(token)
            cursor += len(token) + 1
        return {"page_id": "p1", "page_number": 1, "image_uri": None, "image_hash": "0" * 64,
                "image_width": 1000, "image_height": 1000, "pdf_width": 1000, "pdf_height": 1000,
                "status": "needs_human", "eligible_for_translation": False, "forced_page_review": False,
                "error": None, "transcription": " ".join(text), "words": words, "warnings": ["ocr_unreviewed"]}

    def test_alignment_keeps_matched_boxes_and_flags_changes(self):
        merged = scanned_ocr.merge_reviewed_entry(self.entry(), "The theory of prime numbers")
        boxes = {w["text"]: (w["pixel_bbox"], w["confidence"]) for w in merged["words"]}
        self.assertEqual(boxes["theory"], ([110, 10, 190, 40], 91.0))
        self.assertEqual(boxes["prime"], ([0, 0, 1000, 1000], 0.0))
        self.assertEqual(merged["vision_changed_words"], 1)
        self.assertIn("vision_reviewed", merged["warnings"])
        self.assertNotIn("ocr_vision_disagreement", merged["warnings"])
        far = scanned_ocr.merge_reviewed_entry(self.entry(), "Completely different words appear here instead")
        self.assertIn("ocr_vision_disagreement", far["warnings"])
        for word in far["words"]:
            self.assertEqual(far["transcription"][word["source_char_start"]:word["source_char_end"]], word["text"])

    def test_vision_text_validator(self):
        self.assertEqual(scanned_ocr.parse_vision_text("```\nPage text\n```")["text"], "Page text")
        for bad in ("", "   ", None, "זה תרגום לעברית של העמוד כולו"):
            with self.assertRaises(ValueError):
                scanned_ocr.parse_vision_text(bad)

    def test_adapters_send_the_image(self):
        prompt = ImagePrompt("read", b"\xff\xd8jpeg", "image/jpeg")
        self.assertIn("[attached page image sha256:", prompt)
        captured = {}
        ok = SimpleNamespace(status="completed", output_text="text", model="m", usage=SimpleNamespace(
            input_tokens=1, output_tokens=1, input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0),
            output_tokens_details=SimpleNamespace(reasoning_tokens=0)))
        openai = OpenAITextGenerationAdapter(client=SimpleNamespace(responses=SimpleNamespace(
            create=lambda **p: captured.setdefault("openai", p) and ok)), max_output_tokens=100)
        openai.generate(prompt, "gpt-6-luna")
        content = captured["openai"]["input"][0]["content"]
        self.assertEqual([c["type"] for c in content], ["input_text", "input_image"])
        self.assertTrue(content[1]["image_url"].startswith("data:image/jpeg;base64,"))
        message = SimpleNamespace(content=[SimpleNamespace(text="t")], model="m", stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1, cache_read_input_tokens=0,
                                  cache_creation_input_tokens=0, cache_creation=None))
        anthropic = AnthropicTextGenerationAdapter(client=SimpleNamespace(messages=SimpleNamespace(
            create=lambda **p: captured.setdefault("anthropic", p) and message)), max_output_tokens=100)
        anthropic.generate(prompt, "claude-sonnet-5-5")
        block = captured["anthropic"]["messages"][0]["content"][0]
        self.assertEqual((block["type"], block["source"]["media_type"]), ("image", "image/jpeg"))
        chat = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="t"), finish_reason="stop")],
                               model="m", usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))
        compatible = OpenAICompatibleTextGenerationAdapter(
            client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
                create=lambda **p: captured.setdefault("chat", p) and chat))),
            provider_definition=ProviderDefinition("x", "openai_compatible", "X_KEY", "https://example.invalid/v1"),
            max_output_tokens=100)
        compatible.generate(prompt, "m")
        self.assertEqual(captured["chat"]["messages"][0]["content"][1]["type"], "image_url")


@unittest.skipUnless(TESSERACT, "local Tesseract is not installed")
class ScannedFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "scan.pdf"
        make_scanned_pdf(self.path)

    def run_job(self, model, review="vision", jobs=None):
        jobs = jobs or DocumentJobs(self.root, adapter_factory=lambda role, request: model)
        settings = {"model": "configured", "budget_usd": 5.0, "model_config": CONFIG, "quality": "fast",
                    "automation": True, "language": "en", "ocr_review": review}
        started = jobs.start(self.path, settings, paid_confirm=True)
        return jobs, self.wait(jobs, started["job_id"])

    def wait(self, jobs, job_id):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            job = jobs.get(job_id)
            if job["status"] not in ("queued", "reading", "translating", "reviewing", "rebuilding") and not jobs.active:
                return job
            time.sleep(0.02)
        self.fail("job did not finish")

    def test_local_ocr_bundle_is_valid_evidence(self):
        document = pdf_extract.extract_pdf(self.path, "en")
        self.assertEqual(len(scanned_ocr.scanned_pages(document)), 1)
        bundle = scanned_ocr.run_local_ocr(self.path, document, self.root / "job")
        self.assertIn("theory of numbers", bundle["pages"][0]["transcription"])
        readings = build_readings(document, ocr_bundle=bundle)
        self.assertTrue(readings[0]["alternatives"][1]["usable"])

    def test_scanned_book_translates_with_vision_review(self):
        model = FakeModel()
        jobs, job = self.run_job(model)
        self.assertEqual(job["status"], "completed", job.get("error"))
        self.assertEqual(len(model.vision_calls), 1)
        self.assertGreater(model.translation_calls, 0)
        self.assertTrue(job["ocr_summary"]["vision_reviewed"])
        selected = job["structure"]["readings"][0]["selected"]
        self.assertEqual(selected["origin"], "ocr")
        source = " ".join(u["text"] for u in job["structure"]["units"])
        self.assertIn("⟦p + q⟧", source)
        journal = self.root / "documents" / job["job_id"] / "journal.sqlite3"
        connection = sqlite3.connect(journal)
        self.addCleanup(connection.close)   # Windows cannot delete an open database file
        stages = [r[0] for r in connection.execute("select stage from steps")]
        self.assertIn(scanned_ocr.VISION_STAGE, stages)
        self.assertEqual(job["settings"]["max_calls"], 1 * 24 + 64)

    def test_review_off_uses_tesseract_text_without_vision_calls(self):
        model = FakeModel()
        _, job = self.run_job(model, review="off")
        self.assertEqual(job["status"], "completed", job.get("error"))
        self.assertEqual(model.vision_calls, [])
        self.assertFalse(job["ocr_summary"]["vision_reviewed"])

    def test_failed_vision_offers_skip_and_resume_never_resends(self):
        model = FakeModel(fail_vision=True)
        with mock.patch.object(job_blocks, "AUTO_ACCEPT_BELOW_USD", 0.0):   # the user decides here
            jobs, job = self.run_job(model)
        self.assertEqual(job["status"], "failed")
        block = jobs.blocker(job["job_id"], job)
        self.assertIn("skip_ocr_review", [o["id"] for o in block["options"]])
        jobs.decide(job["job_id"], "skip_ocr_review")
        jobs.resume(job["job_id"])
        job = self.wait(jobs, job["job_id"])
        self.assertEqual(job["status"], "completed", job.get("error"))
        self.assertEqual(len(model.vision_calls), 1)
        self.assertEqual(job["settings"]["ocr_review"], "off")

    def test_scanned_preview_estimates_vision_review(self):
        jobs = DocumentJobs(self.root)
        preview = jobs.preview(self.path, {"model": "configured", "budget_usd": 5.0, "model_config": CONFIG,
                                           "automation": True, "language": "en"})
        self.assertTrue(preview["scanned"])
        self.assertEqual((preview["scanned_pages"], preview["chapter_count"]), (1, 0))
        self.assertTrue(preview["ocr_ready"])
        self.assertGreater(preview["conservative_total_ceiling_usd"], preview["expected_total_cost_usd"])
        self.assertGreater(preview["expected_total_cost_usd"], 0)


if __name__ == "__main__":
    unittest.main()
