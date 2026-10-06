"""ARTICLE-NOTES: footnotes, note marks, page furniture, reference lists and mathematics in
PDF articles (audit/contracts/article_notes.md). Offline only: fake adapters, no network."""
import json
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _article_pdf
from scholarly_translation import article_layout as al
from scholarly_translation import chapter_pipeline as pipeline
from scholarly_translation.document_draft import DocumentJobs, _auto_accept_decisions
from scholarly_translation.export_common import reorder_bidi_line
from scholarly_translation.export_html import export_html
from scholarly_translation.export_pdf import export_pdf
from scholarly_translation.glossary import new_store
from scholarly_translation.model_adapter import TextGenerationResult
from scholarly_translation.model_config import ModelConfiguration
from scholarly_translation.pdf_extract import extract_pdf

from test_document_draft import MOCK_MODEL_CONFIG


def _kinds(structure):
    return [(n["kind"], n["text"]) for n in sorted(structure["nodes"], key=lambda n: n["order"])]


class _Article(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.pdf = _article_pdf.build(Path(cls.tmp.name) / "article.pdf")
        cls.structure = _auto_accept_decisions(extract_pdf(cls.pdf, "en"))
        cls.index = al.note_index(cls.structure)
        cls.units = {u["unit_id"]: u for u in cls.structure["units"]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def unit_with(self, needle):
        return next(u for u in self.structure["units"] if needle in u["text"])


class LayoutTests(_Article):
    def test_furniture_notes_references_heading_and_formula(self):
        kinds = _kinds(self.structure)
        self.assertEqual([t for k, t in kinds if k == "page_furniture"],
                         [_article_pdf.HEADER, "101", _article_pdf.HEADER, "102", _article_pdf.HEADER, "103"])
        self.assertIn(("heading", "Justice and the Measure of Things"), kinds)
        self.assertIn(("heading", "References"), kinds)
        self.assertIn(("formula", "E = mc2 (3)"), kinds)
        notes = [t for k, t in kinds if k == "note"]
        self.assertEqual(len(notes), 4)
        self.assertTrue(notes[1].startswith("2 Rawls") and notes[1].endswith("political"))   # 2 lines, one node
        self.assertTrue(notes[2].startswith("liberalism"))                                  # continues on page 2
        entries = [t for k, t in kinds if k == "bibliography_entry"]
        self.assertEqual(len(entries), 3)
        self.assertIn("\n287-337.", entries[0])                                            # wrapped entry joined

    def test_note_index_labels_continuation_and_passthrough(self):
        notes = list(self.index["notes"].values())
        self.assertEqual([n["label"] for n in notes], ["1", "2", None, "3"])
        second = next(uid for uid, n in self.index["notes"].items() if n["label"] == "2")
        self.assertEqual(notes[2]["continues"], second)
        reasons = sorted(set(self.index["passthrough"].values()))
        self.assertEqual(reasons, ["bibliography_entry", "formula", "page_furniture"])
        self.assertNotIn(self.unit_with("References")["unit_id"], self.index["passthrough"])

    def test_marks_skip_mathematics(self):
        body = self.unit_with("as argued earlier")
        marked = al.marked_text(self.structure, body)
        self.assertIn("several authors.[^1] The relation", marked)
        self.assertIn("similar view,[^2]", marked)
        self.assertIn("the measure x2 of", marked)              # a power, not note 2
        self.assertNotIn("x[^2]", marked)
        self.assertIn("assumptions;[^3]", al.marked_text(self.structure, self.unit_with("A second claim")))

    def test_two_page_documents_and_chapter_headings_are_not_furniture(self):
        readings = [_reading("p%d" % i, ["Chapter %d" % i, "Body text of this page goes on here for a while.",
                                          "More body text that keeps going for the test."]) for i in range(1, 5)]
        for over in al.analyze_readings(readings).values():
            self.assertNotIn("page_furniture", {v[0] for v in over.values()})


class MarkTests(unittest.TestCase):
    def test_find_marks_math_and_order(self):
        text = "as shown.1 Then x2 and α3 and a^4 and f(x)=y2 and sin(3) but claim5 holds; also (6)."
        self.assertEqual([m[2] for m in al.find_marks(text, ["1", "2", "3", "4", "5", "6"])], ["1", "5"])
        self.assertEqual(al.find_marks("first.2 then.1", ["1", "2"]), [(13, 14, "1")])   # label order
        self.assertEqual(al.find_marks("in 1990s and page 12 of it", ["12"]), [])

    def test_note_label(self):
        for text, label in (("1 See Smith.", "1"), ("12. Ibid.", "12"), ("* Corresponding author", "*"),
                            ("¹ See", "1"), ("1990 was a year", None), ("2,5 million", None), ("12", None)):
            self.assertEqual(al.note_label(text), label, text)

    def test_repair_marks(self):
        self.assertEqual(al.repair_marks("a[^1] b[^2]", "א[^1] ב"), ("א[^1] ב[^2]", True))
        self.assertEqual(al.repair_marks("a[^1]", "א[^1] ב[^1] ג[^7]"), ("א[^1] ב ג", True))
        self.assertEqual(al.repair_marks("a[^1]", "א[^1]"), ("א[^1]", False))
        self.assertEqual(al.repair_marks("plain", "פשוט"), ("פשוט", False))

    def test_superscript_marks_keep_digit_order_in_rtl(self):
        visual = reorder_bidi_line("מילה¹² נוספת.")
        self.assertIn("¹²", visual)
        self.assertNotIn("²¹", visual)


def _reading(page_id, lines, heights=None, origin="ocr"):
    """A resolved OCR-shaped reading: one word anchor per line, pdf_bbox geometry."""
    text = "\n".join(lines)
    anchors, pos, top = [], 0, 60.0
    for i, line in enumerate(lines):
        h = (heights or {}).get(i, 11.0)
        anchors.append({"kind": "word", "text": line, "source_char_start": pos, "source_char_end": pos + len(line),
                        "pdf_bbox": [72.0, top, 400.0, top + h]})
        pos += len(line) + 1
        top += h + 4.0
    return {"page_id": page_id, "status": "resolved", "text": text,
            "selected": {"origin": origin, "candidate_hash": "h"},
            "alternatives": [{"origin": origin, "candidate_hash": "h", "anchors": anchors}]}


class OcrShapeTests(unittest.TestCase):
    def test_note_zone_from_ocr_word_geometry(self):
        lines = ["The body of the scanned article runs on here.", "It mentions a source here.4 And more text follows.",
                 "4 A small note at the bottom of the page.", "which goes on to a second note line."]
        readings = [_reading("p1", lines, {2: 8.0, 3: 8.0})]
        over = al.analyze_readings(readings)["p1"]
        starts = [0, len(lines[0]) + 1, len(lines[0]) + len(lines[1]) + 2]
        self.assertNotIn(starts[1], over)
        self.assertEqual(over[starts[2]][0], "note")
        self.assertEqual(len({v[2] for v in over.values() if v[0] == "note"}), 1)   # one note, two lines

    def test_small_lines_without_label_are_body(self):
        readings = [_reading("p1", ["Normal body text line of the page here.", "Another normal body line here.",
                                     "a small caption line without a number"], {2: 8.0})]
        self.assertEqual(al.analyze_readings(readings), {})


class PipelineTests(_Article):
    def configuration(self):
        return ModelConfiguration.from_dict(MOCK_MODEL_CONFIG)

    def test_plan_leaves_passthrough_units_out(self):
        ids = [u["unit_id"] for u in self.structure["units"]]
        plan = pipeline.plan_chapter(self.structure, new_store(), ids, self.configuration(), "fast", "scholarly")
        planned = {uid for batch in plan["batches"] for uid in batch["unit_ids"]}
        self.assertFalse(planned & set(self.index["passthrough"]))
        self.assertEqual(plan["unit_count"], len(ids) - len(self.index["passthrough"]))
        refs = [uid for uid, reason in self.index["passthrough"].items() if reason == "bibliography_entry"]
        only = pipeline.plan_chapter(self.structure, new_store(), refs, self.configuration(), "checked", "scholarly")
        self.assertTrue(only["passthrough_only"])
        self.assertEqual((only["batches"], only["conservative_total_ceiling_usd"]), ([], 0.0))

    def test_prompt_shows_marks_and_rules(self):
        body, note = self.unit_with("as argued earlier"), self.unit_with("1 See Smith")
        prompt = pipeline.build_batch_translation_prompt(self.structure, new_store(), [body["unit_id"], note["unit_id"]],
                                                         "scholarly")
        self.assertIn("several authors.[^1] The relation", prompt.stable_prefix)
        self.assertIn("[^n] is a footnote mark", prompt.suffix)
        self.assertIn("keep that number first", prompt.suffix)

    def test_parse_repairs_marks(self):
        source = "Claim.[^1] Second[^2] end."
        raw = json.dumps([{"unit_id": "u", "translation": "טענה.[^1] שנייה [^9] סוף.", "translation_note": None}],
                         ensure_ascii=False)
        repaired = []
        out = pipeline.parse_batch_translation_response(raw, ["u"], {"u": source}, lambda: repaired.append(1))
        self.assertEqual(out["u"]["translation"], "טענה.[^1] שנייה  סוף.[^2]")
        self.assertTrue(out["u"]["note_marks_relocated"])
        self.assertEqual(repaired, [1])


class _MarkingTranslator:
    """Translates each unit to Hebrew keeping its [^n] marks; drops mark 2 once to exercise repair."""
    def __init__(self):
        self.prompts = []

    def generate(self, prompt_text, model):
        self.prompts.append(prompt_text)
        suffix = prompt_text.suffix
        marker = "TARGET_UNIT_IDS (translate exactly these ids, in exactly this order, each exactly once): "
        start = suffix.index(marker) + len(marker)
        ids = json.loads(suffix[start:suffix.index("\n", start)])
        sources = {}
        for line in prompt_text.stable_prefix.splitlines():
            if line.startswith('{"unit_id"'):
                row = json.loads(line)
                sources[row["unit_id"]] = row["source_text"]
        payload = []
        for uid in ids:
            marks = al.MARK_TOKEN_RE.findall(sources[uid])
            label = al.note_label(sources[uid])
            text = (label + " " if label and not marks else "") + "תרגום " + " ".join(
                "מילה[^%s]" % m for m in marks if m != "2") + " סוף."
            payload.append({"unit_id": uid, "translation": text, "translation_note": None})
        return TextGenerationResult(status="completed", text=json.dumps(payload, ensure_ascii=False),
                                    token_usage={"input": 10, "output": 10}, observed_model=model,
                                    duration_seconds=0.0, observed_provider="fake")


class _Keeper:
    def generate(self, prompt_text, model):
        text = '{"names": []}' if "NAME TABLE of a book" in str(prompt_text) else '{"ops": []}'
        return TextGenerationResult(status="completed", text=text, token_usage={"input": 10, "output": 5},
                                    observed_model=model, duration_seconds=0.0, observed_provider="fake")


class JobTests(unittest.TestCase):
    def test_article_job_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _article_pdf.build(root / "article.pdf")
            translator = _MarkingTranslator()
            fakes = {"translator": translator, "chapter_qa": _Keeper(), "semantic_reviewer": None}
            config = json.loads(json.dumps(MOCK_MODEL_CONFIG))
            for role in config["models"].values():
                role["capabilities"] = {"context_window": 64000, "usable_context_tokens": 60000}
            jobs = DocumentJobs(root, adapter_factory=lambda role, request: fakes[role])
            started = jobs.start(path, {"model": "configured", "budget_usd": 2.0, "model_config": config,
                                        "quality": "fast", "automation": True}, paid_confirm=True)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                job = jobs.get(started["job_id"])
                if job["status"] not in ("queued", "reading", "translating", "reviewing", "rebuilding"):
                    break
                time.sleep(0.02)
            while jobs.active and time.monotonic() < deadline:
                time.sleep(0.02)
            job = jobs.get(started["job_id"])
            self.assertEqual(job["status"], "completed", job.get("error"))
            structure = job["structure"]
            passthrough = al.note_index(structure)["passthrough"]
            records = {r["unit_id"]: r for r in job["units"]}
            units = {u["unit_id"]: u for u in structure["units"]}
            self.assertEqual(set(records), set(units))
            self.assertEqual([r["unit_id"] for r in job["units"]],
                             [u["unit_id"] for u in sorted(structure["units"], key=lambda u: records[u["unit_id"]]["order"])])
            for uid in passthrough:
                self.assertEqual(records[uid]["target_text"], units[uid]["text"])
                self.assertEqual(records[uid]["review"]["skip_reason"], "passthrough_" + passthrough[uid])
            sent = " ".join(p.suffix for p in translator.prompts)
            self.assertFalse(any(uid in sent for uid in passthrough))
            self.assertFalse(any("Clarendon" in p.stable_prefix for p in translator.prompts))
            body = next(r for r in job["units"] if "[^1]" in r["source_text"])
            self.assertTrue(body["target_text"].endswith("[^2]"))           # dropped mark restored
            self.assertIn("note_mark_relocated", {f["type"] for f in body["findings"]})
            translations = {r["unit_id"]: {"text": r["target_text"]} for r in job["units"]}
            result = export_pdf(structure, translations)
            self.assertEqual(sum(m.get("placement") == "footnote" for m in result.manifest), 4)


class ExportTests(_Article):
    def translations(self, body_words=12, note_words=8, note_tail=""):
        out = {}
        for uid, unit in self.units.items():
            if uid in self.index["passthrough"]:
                out[uid] = {"text": unit["text"]}
                continue
            info = self.index["notes"].get(uid)
            if info is not None:
                label = info["label"]
                out[uid] = {"text": (label + " " if label else "") + "NOTE%s " % (label or "C")
                            + "הערה " * note_words + note_tail}
                continue
            marks = al.MARK_TOKEN_RE.findall(al.marked_text(self.structure, unit))
            out[uid] = {"text": "פסקה " * body_words + " ".join("מילה[^%s]" % m for m in marks) + " סוף."}
        return out

    def pages(self, content):
        path = Path(self.tmp.name) / "out.pdf"
        path.write_bytes(content)
        with pdfplumber.open(path) as pdf:
            return [page.extract_text() or "" for page in pdf.pages]

    def test_each_note_on_the_page_of_its_mark(self):
        result = export_pdf(self.structure, self.translations(body_words=900))
        pages = self.pages(result.content)
        self.assertGreater(len(pages), 2)
        for label, sup in (("1", "¹"), ("2", "²"), ("3", "³")):
            note_page = next(i for i, text in enumerate(pages) if "NOTE" + label in text)
            mark_page = next(i for i, text in enumerate(pages) if sup in text)
            self.assertEqual(note_page, mark_page, label)
        self.assertEqual(sum("NOTEC" in text for text in pages), 1)      # continuation joined to note 2
        self.assertNotIn("Journal of Test Studies", "".join(pages))
        self.assertIn("Smith, A. (2019). Relations and Measures.", "".join(pages))
        self.assertIn("Ethics 109, 287-337.", "".join(pages))
        self.assertFalse(any(lim["kind"] == "note_without_mark" for lim in result.limitations))

    def test_long_note_continues_on_next_page(self):
        result = export_pdf(self.structure, self.translations(note_words=900, note_tail="TAILEND"))
        pages = self.pages(result.content)
        start = next(i for i, text in enumerate(pages) if "NOTE1" in text)
        tail = next(i for i, text in enumerate(pages) if "TAILEND" in text)
        self.assertGreater(tail, start)

    def test_html_links_marks_and_notes(self):
        page = export_html(self.structure, self.translations(), "t").decode("utf-8")
        self.assertEqual(len(re.findall(r'<sup id="fnref-\d"><a href="#fn-\d">\d</a></sup>', page)), 3)
        self.assertEqual(page.count('<li id="fn-'), 3)
        self.assertIn('class="bib" dir="ltr">Anderson, E. (1999). What is the point of equality? Ethics 109, 287-337.',
                      page)
        self.assertNotIn("Journal of Test Studies", page)


if __name__ == "__main__":
    unittest.main()
