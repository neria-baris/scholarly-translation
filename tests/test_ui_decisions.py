import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from scholarly_translation.glossary import new_store, propose_rule, review_rule
from scholarly_translation.pdf_extract import extract_pdf
from scholarly_translation.segmentation import build_structure
from scholarly_translation.ui_decisions import (
    UIDecisionError, glossary_action, glossary_options, source_decisions, source_options,
)
from scholarly_translation.web_ui import ROOT, make_handler


class LocalDecisionFormsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        pdf = Path(self.temp.name) / "fixture.pdf"
        page = canvas.Canvas(str(pdf), pagesize=LETTER)
        page.setFont("Helvetica", 14)
        page.drawString(72, 692, "The logos is central to the argument.")
        page.showPage()
        page.save()
        self.document = extract_pdf(pdf, language="en")
        self.unresolved = build_structure(self.document)
        self.option = source_options(self.unresolved)["readings"][0]
        self.candidate = next(item for item in self.option["alternatives"] if item["origin"] == "digital")

    def tearDown(self):
        self.temp.cleanup()

    def _source_request(self):
        return {"expected_revision": self.unresolved["revision"]["id"],
                "page_id": self.option["page_id"],
                "candidate_hash": self.candidate["candidate_hash"],
                "actor": "reviewer", "reason": "Compared with the page image"}

    def test_explicit_source_choice_creates_resolved_units(self):
        decisions = source_decisions(self.unresolved, self._source_request())
        resolved = build_structure(self.document, decisions=decisions, previous=self.unresolved)
        self.assertEqual(resolved["readings"][0]["status"], "resolved")
        self.assertTrue(resolved["units"])
        self.assertEqual(resolved["readings"][0]["decision"]["actor_kind"], "human")
        self.assertEqual(resolved["revision"]["parent_revision"], self.unresolved["revision"]["id"])

    def test_stale_or_anonymous_source_choice_is_rejected(self):
        request = self._source_request()
        request["candidate_hash"] = "stale"
        with self.assertRaises(UIDecisionError):
            source_decisions(self.unresolved, request)
        request = self._source_request()
        request["actor"] = ""
        with self.assertRaises(UIDecisionError):
            source_decisions(self.unresolved, request)

    def test_term_proposal_and_human_review_use_exact_binding(self):
        resolved = build_structure(self.document, decisions=source_decisions(self.unresolved, self._source_request()))
        unit = next(item for item in resolved["units"] if "logos" in item["text"])
        proposal = glossary_action(resolved, new_store(), {
            "kind": "propose", "unit_id": unit["unit_id"], "source_term": "logos",
            "target_term": "לוגוס", "occurrence": 1, "scope": "unit", "loaded": True,
        })
        self.assertEqual(proposal["source_char_start"], unit["source_char_start"] + unit["text"].index("logos"))
        store = propose_rule(new_store(), resolved, unit["unit_id"], unit["language"],
                             proposal["source_char_start"], proposal["source_char_end"],
                             proposal["target_term"], scope=proposal["scope"], loaded=True)
        latest = glossary_options(resolved, store)["rules"][0]
        request = {"kind": "review", "rule_id": latest["rule_id"], "expected_version": latest["version"],
                   "expected_fingerprint": latest["fingerprint"], "actor": "editor",
                   "reason": "Checked the source context", "status": "approved"}
        review = glossary_action(resolved, store, request)
        approved = review_rule(store, review["rule_id"], review["expected_version"],
                               review["expected_rule_fingerprint"], review["actor"],
                               review["actor_kind"], review["reason"], review["status"])
        self.assertEqual(approved["rules"][-1]["status"], "approved")
        request["expected_fingerprint"] = "stale"
        with self.assertRaises(UIDecisionError):
            glossary_action(resolved, store, request)

    def test_browser_endpoints_create_new_source_and_glossary_artifacts(self):
        (ROOT / "outputs").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp:
            folder = Path(temp)
            document_path = folder / "document.json"
            structure_path = folder / "structure.json"
            document_path.write_text(json.dumps(self.document.to_dict()), encoding="utf-8")
            structure_path.write_text(json.dumps(self.unresolved), encoding="utf-8")
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("decision-test-token"))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}"

            def post(route, data):
                request = Request(url + route, data=json.dumps(data).encode("utf-8"), method="POST",
                                  headers={"Content-Type": "application/json", "X-UI-Token": "decision-test-token",
                                           "Origin": url})
                with urlopen(request, timeout=30) as response:
                    return json.load(response)

            try:
                source = post("/source-decide", {"document_json": str(document_path),
                                                  "structure_json": str(structure_path), **self._source_request()})
                resolved = json.loads(Path(source["structure_json"]).read_text(encoding="utf-8"))
                self.assertEqual(resolved["readings"][0]["status"], "resolved")
                self.assertEqual(self.unresolved, json.loads(structure_path.read_text(encoding="utf-8")))
                unit = next(item for item in resolved["units"] if "logos" in item["text"])
                proposed = post("/glossary-action", {"kind": "propose", "structure_json": source["structure_json"],
                                                     "unit_id": unit["unit_id"], "source_term": "logos",
                                                     "target_term": "לוגוס", "occurrence": 1,
                                                     "scope": "unit", "loaded": True})
                proposal = json.loads(Path(proposed["glossary"]).read_text(encoding="utf-8"))
                self.assertEqual(proposal["rules"][-1]["status"], "proposed")
                rule = post("/glossary-options", {"structure_json": source["structure_json"],
                                                  "glossary": proposed["glossary"]})["rules"][0]
                approved = post("/glossary-action", {"kind": "review", "structure_json": source["structure_json"],
                                                     "glossary": proposed["glossary"], "rule_id": rule["rule_id"],
                                                     "expected_version": rule["version"],
                                                     "expected_fingerprint": rule["fingerprint"],
                                                     "actor": "editor", "reason": "Verified in context",
                                                     "status": "approved"})
                final = json.loads(Path(approved["glossary"]).read_text(encoding="utf-8"))
                self.assertEqual(final["rules"][-1]["status"], "approved")
                self.assertEqual(proposal, json.loads(Path(proposed["glossary"]).read_text(encoding="utf-8")))
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()
