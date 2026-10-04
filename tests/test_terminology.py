import copy
import json
import copy
import tempfile
import unittest
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from scholarly_translation import __main__ as cli
from scholarly_translation.glossary import (
    GlossaryError, new_store as new_glossary_store, propose_rule, resolve_applicable,
    review_rule, validate_glossary,
)
from scholarly_translation.pdf_extract import extract_pdf
from scholarly_translation.segmentation import build_structure
from scholarly_translation.source_reading import build_readings
from scholarly_translation.source_reading import fingerprint
from scholarly_translation.translation_memory import (
    MemoryError, lookup, new_store as new_memory_store, remember, validate_memory,
)


def _build_fixture_pdf(path) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    c.setFont("Helvetica", 14)
    c.drawString(72, height - 100, "The logos is central to the argument.")
    c.drawString(72, height - 130, "Later the logos returns once more.")
    c.showPage()
    c.save()


def _human_decision(candidate, reason="verified against page image") -> dict:
    return {
        "origin": candidate["origin"], "candidate_hash": candidate["candidate_hash"],
        "actor": "reviewer@example.org", "actor_kind": "human", "reason": reason,
    }


def _build_structure(tmp_path):
    pdf_path = tmp_path / "fixture.pdf"
    _build_fixture_pdf(pdf_path)
    document = extract_pdf(pdf_path, language="en")
    page = document.pages[0]
    from scholarly_translation.source_reading import build_readings
    reading = build_readings(document)[0]
    candidate = next(c for c in reading["alternatives"] if c["origin"] == "digital")
    decisions = {page.page_id: _human_decision(candidate)}
    # Pin a small word-count ceiling so the two short fixture sentences stay
    # separate units under the default logical-structure grouping policy
    # (the policy's merge-toward-target behavior is covered separately in
    # tests/test_structure_v2.py).
    return build_structure(document, decisions=decisions, unit_policy={"max_unit_words": 1})


class GlossaryProposalAndReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.structure = _build_structure(Path(self.tmp.name))
        self.unit = self.structure["units"][0]
        self.term_start = self.unit["text"].index("logos") + self.unit["source_char_start"]
        self.term_end = self.term_start + len("logos")

    def tearDown(self):
        self.tmp.cleanup()

    def test_propose_is_not_effective_until_approved(self):
        store = propose_rule(
            new_glossary_store(), self.structure, self.unit["unit_id"], "en",
            self.term_start, self.term_end, "לוגוס", loaded=True,
        )
        rule = store["rules"][0]
        self.assertEqual(rule["status"], "proposed")
        self.assertEqual(rule["source_term"], "logos")
        self.assertTrue(rule["loaded"])
        validate_glossary(store)

        resolution = resolve_applicable(store, self.structure, self.unit["unit_id"])
        self.assertEqual(resolution["approved_rules"], [])
        self.assertEqual(len(resolution["proposed_rules"]), 1)
        self.assertEqual(resolution["status"], "ready")

    def test_human_approval_makes_rule_applicable_and_effective(self):
        store = propose_rule(
            new_glossary_store(), self.structure, self.unit["unit_id"], "en",
            self.term_start, self.term_end, "לוגוס", loaded=True,
        )
        rule = store["rules"][0]
        store = review_rule(
            store, rule["rule_id"], rule["version"], fingerprint(rule),
            "editor@example.org", "human", "approved after cross-check", "approved",
        )
        approved = store["rules"][-1]
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["version"], 2)

        resolution = resolve_applicable(store, self.structure, self.unit["unit_id"])
        self.assertEqual(resolution["status"], "ready")
        self.assertEqual(len(resolution["approved_rules"]), 1)
        self.assertEqual(resolution["approved_rules"][0]["target_term"], "לוגוס")
        return store, resolution

    def test_model_actor_cannot_approve(self):
        store = propose_rule(
            new_glossary_store(), self.structure, self.unit["unit_id"], "en",
            self.term_start, self.term_end, "לוגוס",
        )
        rule = store["rules"][0]
        with self.assertRaises(GlossaryError):
            review_rule(
                store, rule["rule_id"], rule["version"], fingerprint(rule),
                "model-agent", "model", "auto-approved", "approved",
            )

    def test_stale_expected_fingerprint_rejected(self):
        store = propose_rule(
            new_glossary_store(), self.structure, self.unit["unit_id"], "en",
            self.term_start, self.term_end, "לוגוס",
        )
        rule = store["rules"][0]
        store = review_rule(
            store, rule["rule_id"], rule["version"], fingerprint(rule),
            "editor@example.org", "human", "approved", "approved",
        )
        with self.assertRaises(GlossaryError):
            review_rule(
                store, rule["rule_id"], rule["version"], fingerprint(rule),
                "editor@example.org", "human", "revise again", "approved", target_term="other",
            )

    def test_persisted_review_history_rejects_reordering_and_tampering(self):
        store = propose_rule(
            new_glossary_store(), self.structure, self.unit["unit_id"], "en",
            self.term_start, self.term_end, "לוגוס",
        )
        proposal = store["rules"][0]
        store = review_rule(
            store, proposal["rule_id"], proposal["version"], fingerprint(proposal),
            "editor@example.org", "human", "approved", "approved",
        )

        reordered = copy.deepcopy(store)
        reordered["rules"].reverse()
        with self.assertRaises(GlossaryError):
            validate_glossary(reordered)

        tampered = copy.deepcopy(store)
        tampered["rules"][0]["target_term"] = "שונה"
        with self.assertRaises(GlossaryError):
            validate_glossary(tampered)

    def test_conflicting_approved_targets_need_human(self):
        second_unit = self.structure["units"][1]
        second_start = second_unit["text"].index("logos") + second_unit["source_char_start"]
        second_end = second_start + len("logos")

        store = new_glossary_store()
        store = propose_rule(store, self.structure, self.unit["unit_id"], "en",
                              self.term_start, self.term_end, "לוגוס")
        rule_a = store["rules"][0]
        store = review_rule(store, rule_a["rule_id"], rule_a["version"], fingerprint(rule_a),
                             "editor@example.org", "human", "approve a", "approved")

        store = propose_rule(store, self.structure, second_unit["unit_id"], "en",
                              second_start, second_end, "מילה")
        rule_b = store["rules"][-1]
        store = review_rule(store, rule_b["rule_id"], rule_b["version"], fingerprint(rule_b),
                             "editor@example.org", "human", "approve b", "approved")

        resolution = resolve_applicable(store, self.structure, self.unit["unit_id"])
        self.assertEqual(resolution["status"], "needs_human")
        self.assertEqual(resolution["approved_rules"], [])
        self.assertIn("conflicting_approved_target:logos", resolution["warnings"])

    def test_invalid_span_rejected(self):
        with self.assertRaises(GlossaryError):
            propose_rule(new_glossary_store(), self.structure, self.unit["unit_id"], "en",
                         self.unit["source_char_start"] - 1, self.term_end, "x")

    def test_unresolved_unit_rejected(self):
        with self.assertRaises(GlossaryError):
            propose_rule(new_glossary_store(), self.structure, "unknown-unit", "en", 0, 1, "x")


class TranslationMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.structure = _build_structure(Path(self.tmp.name))
        self.unit = self.structure["units"][0]
        self.term_start = self.unit["text"].index("logos") + self.unit["source_char_start"]
        self.term_end = self.term_start + len("logos")
        store = propose_rule(new_glossary_store(), self.structure, self.unit["unit_id"], "en",
                              self.term_start, self.term_end, "לוגוס", loaded=True)
        rule = store["rules"][0]
        self.glossary = review_rule(store, rule["rule_id"], rule["version"], fingerprint(rule),
                                    "editor@example.org", "human", "approved", "approved")
        self.resolution = resolve_applicable(self.glossary, self.structure, self.unit["unit_id"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_exact_reuse_after_human_approved_memory(self):
        memory = remember(new_memory_store(), self.structure, self.unit["unit_id"], self.resolution,
                          "הלוגוס הוא מרכזי לטיעון.", "translator@example.org", "human", "approved fixture memory")
        validate_memory(memory)
        outcome = lookup(memory, self.structure, self.unit["unit_id"], self.resolution)
        self.assertEqual(outcome["outcome"], "reusable")
        self.assertEqual(outcome["target_text"], "הלוגוס הוא מרכזי לטיעון.")

    def test_same_source_and_policy_cannot_hold_conflicting_approved_targets(self):
        memory = remember(new_memory_store(), self.structure, self.unit["unit_id"], self.resolution,
                          "תרגום ראשון.", "translator@example.org", "human", "approved fixture memory")
        with self.assertRaises(MemoryError):
            remember(memory, self.structure, self.unit["unit_id"], self.resolution,
                     "תרגום שונה.", "translator@example.org", "human", "conflicting fixture memory")

    def test_miss_without_prior_entry(self):
        outcome = lookup(new_memory_store(), self.structure, self.unit["unit_id"], self.resolution)
        self.assertEqual(outcome["outcome"], "miss")

    def test_revised_approved_rule_makes_reuse_stale(self):
        memory = remember(new_memory_store(), self.structure, self.unit["unit_id"], self.resolution,
                          "הלוגוס הוא מרכזי לטיעון.", "translator@example.org", "human", "approved fixture memory")
        approved_rule = self.glossary["rules"][-1]
        revised_glossary = review_rule(
            self.glossary, approved_rule["rule_id"], approved_rule["version"], fingerprint(approved_rule),
            "editor@example.org", "human", "revised target term", "approved", target_term="לוגוס (מונח מהותי)",
        )
        new_resolution = resolve_applicable(revised_glossary, self.structure, self.unit["unit_id"])
        outcome = lookup(memory, self.structure, self.unit["unit_id"], new_resolution)
        self.assertEqual(outcome["outcome"], "stale_dependencies")

    def test_unrelated_proposal_and_scoped_rule_revision_preserve_other_unit(self):
        other = self.structure["units"][1]
        other_resolution = resolve_applicable(new_glossary_store(), self.structure, other["unit_id"])
        memory = remember(
            new_memory_store(), self.structure, other["unit_id"], other_resolution,
            "תרגום דוגמה.", "translator@example.org", "human", "approved fixture memory",
        )

        proposed = propose_rule(
            new_glossary_store(), self.structure, self.unit["unit_id"], "en",
            self.term_start, self.term_end, "לוגוס",
            scope={"document_ids": [], "unit_ids": [self.unit["unit_id"]]},
        )
        proposal = proposed["rules"][0]
        approved = review_rule(
            proposed, proposal["rule_id"], proposal["version"], fingerprint(proposal),
            "editor@example.org", "human", "approved", "approved",
        )
        rule = approved["rules"][-1]
        revised = review_rule(
            approved, rule["rule_id"], rule["version"], fingerprint(rule),
            "editor@example.org", "human", "revised terminology", "approved",
            target_term="מונח מתוקן",
        )
        for glossary in (proposed, approved, revised):
            resolution = resolve_applicable(glossary, self.structure, other["unit_id"])
            self.assertEqual(resolution["policy_fingerprint"], other_resolution["policy_fingerprint"])
            self.assertEqual(lookup(memory, self.structure, other["unit_id"], resolution)["outcome"], "reusable")

    def test_model_actor_cannot_remember(self):
        with self.assertRaises(MemoryError):
            remember(new_memory_store(), self.structure, self.unit["unit_id"], self.resolution,
                    "target", "model-agent", "model", "auto")

    def test_needs_human_resolution_cannot_be_remembered(self):
        second_unit = self.structure["units"][1]
        second_start = second_unit["text"].index("logos") + second_unit["source_char_start"]
        second_end = second_start + len("logos")
        conflicted = propose_rule(self.glossary, self.structure, second_unit["unit_id"], "en",
                                  second_start, second_end, "מילה")
        rule = conflicted["rules"][-1]
        conflicted = review_rule(conflicted, rule["rule_id"], rule["version"], fingerprint(rule),
                                 "editor@example.org", "human", "approve b", "approved")

        needs_human_resolution = resolve_applicable(conflicted, self.structure, self.unit["unit_id"])
        self.assertEqual(needs_human_resolution["status"], "needs_human")
        with self.assertRaises(MemoryError):
            remember(new_memory_store(), self.structure, self.unit["unit_id"], needs_human_resolution,
                    "target", "translator@example.org", "human", "reason")


class TerminologyCliTests(unittest.TestCase):
    def test_cli_refuses_to_overwrite_source_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "glossary.json"
            _build_fixture_pdf(source)
            document = extract_pdf(source, language="en")
            from scholarly_translation.source_reading import build_readings
            reading = build_readings(document)[0]
            candidate = next(c for c in reading["alternatives"] if c["origin"] == "digital")
            structure = build_structure(document, decisions={document.pages[0].page_id: _human_decision(candidate)})
            structure_path = root / "structure.json"
            structure_path.write_text(json.dumps(structure, ensure_ascii=False), encoding="utf-8")
            original = source.read_bytes()

            rc = cli.main(["terminology", str(structure_path), "--glossary", str(root / "new-store.json"),
                           "--output", str(root)])
            self.assertEqual(rc, 1)
            self.assertEqual(source.read_bytes(), original)

    def test_cli_propose_review_remember_resolve_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            structure = _build_structure(tmp_path)
            structure_path = tmp_path / "structure.json"
            with open(structure_path, "w", encoding="utf-8") as handle:
                json.dump(structure, handle, ensure_ascii=False)

            unit = structure["units"][0]
            term_start = unit["text"].index("logos") + unit["source_char_start"]
            term_end = term_start + len("logos")

            glossary_path = tmp_path / "glossary.json"
            out_dir = tmp_path / "out1"
            propose_action = tmp_path / "propose.json"
            propose_action.write_text(json.dumps({
                "action": "propose", "unit_id": unit["unit_id"], "source_language": "en",
                "source_char_start": term_start, "source_char_end": term_end,
                "target_term": "לוגוס", "loaded": True,
            }), encoding="utf-8")

            rc = cli.main([
                "terminology", str(structure_path), "--glossary", str(glossary_path),
                "--action", str(propose_action), "--output", str(out_dir),
            ])
            self.assertEqual(rc, 0)
            glossary = json.loads((out_dir / "glossary.json").read_text(encoding="utf-8"))
            rule = glossary["rules"][0]
            self.assertEqual(rule["status"], "proposed")

            review_action = tmp_path / "review.json"
            review_action.write_text(json.dumps({
                "action": "review", "rule_id": rule["rule_id"], "expected_version": rule["version"],
                "expected_rule_fingerprint": fingerprint(rule), "actor": "editor@example.org",
                "actor_kind": "human", "reason": "approved", "status": "approved",
            }), encoding="utf-8")
            out_dir2 = tmp_path / "out2"
            rc = cli.main([
                "terminology", str(structure_path), "--glossary", str(out_dir / "glossary.json"),
                "--action", str(review_action), "--output", str(out_dir2),
            ])
            self.assertEqual(rc, 0)

            resolve_action = tmp_path / "resolve.json"
            resolve_action.write_text(json.dumps({"action": "resolve", "unit_id": unit["unit_id"]}), encoding="utf-8")
            out_dir3 = tmp_path / "out3"
            rc = cli.main([
                "terminology", str(structure_path), "--glossary", str(out_dir2 / "glossary.json"),
                "--action", str(resolve_action), "--output", str(out_dir3),
            ])
            self.assertEqual(rc, 0)
            resolution = json.loads((out_dir3 / "resolution.json").read_text(encoding="utf-8"))
            self.assertEqual(resolution["status"], "ready")
            self.assertEqual(len(resolution["approved_rules"]), 1)

            remember_action = tmp_path / "remember.json"
            remember_action.write_text(json.dumps({
                "action": "remember", "unit_id": unit["unit_id"],
                "target_text": "הלוגוס הוא מרכזי לטיעון.", "actor": "translator@example.org",
                "actor_kind": "human", "reason": "approved fixture memory",
            }), encoding="utf-8")
            out_dir4 = tmp_path / "out4"
            rc = cli.main([
                "terminology", str(structure_path), "--glossary", str(out_dir2 / "glossary.json"),
                "--memory", str(tmp_path / "missing_memory.json"),
                "--action", str(remember_action), "--output", str(out_dir4),
            ])
            self.assertEqual(rc, 0)
            memory = json.loads((out_dir4 / "memory.json").read_text(encoding="utf-8"))
            self.assertEqual(len(memory["entries"]), 1)
            self.assertEqual(memory["entries"][0]["target_text"], "הלוגוס הוא מרכזי לטיעון.")

    def test_cli_rejects_invalid_action_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            structure = _build_structure(tmp_path)
            structure_path = tmp_path / "structure.json"
            with open(structure_path, "w", encoding="utf-8") as handle:
                json.dump(structure, handle, ensure_ascii=False)

            action_path = tmp_path / "bad_action.json"
            action_path.write_text(json.dumps({"action": "propose"}), encoding="utf-8")

            rc = cli.main([
                "terminology", str(structure_path), "--glossary", str(tmp_path / "glossary.json"),
                "--action", str(action_path), "--output", str(tmp_path / "out"),
            ])
            self.assertEqual(rc, 1)
            self.assertFalse((tmp_path / "out" / "glossary.json").exists())


class TerminologyContractRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.structure = _build_structure(self.folder)
        self.unit = self.structure["units"][0]
        self.uid = self.unit["unit_id"]
        start = self.unit["text"].index("logos") + self.unit["source_char_start"]
        self.proposal = propose_rule(new_glossary_store(),self.structure,self.uid,"en",start,start+5,
                                     "fixture target",loaded=True,
                                     scope={"document_ids":[],"unit_ids":[self.uid]})
        rule = self.proposal["rules"][0]
        self.glossary = review_rule(self.proposal,rule["rule_id"],1,fingerprint(rule),
                                    "fixture-human","human","construction simulation","approved")

    def _remember(self, structure, uid, glossary):
        return remember(new_memory_store(),structure,uid,resolve_applicable(glossary,structure,uid),
                        "תרגום בדיקה בלבד", "fixture-human","human","construction simulation")

    def test_source_context_history_and_aliasing(self):
        old = copy.deepcopy(self.proposal)
        context = self.proposal["rules"][0]["source_context"]
        self.assertEqual(context["text"],self.unit["text"])
        self.assertEqual(context["source_uri"],self.structure["source_uri"])
        reviewed = copy.deepcopy(self.glossary)
        reviewed["rules"][0]["source_context"]["text"] = "wrong"
        self.assertEqual(self.proposal,old)
        with self.assertRaises(GlossaryError):
            validate_glossary(reviewed)
        bad = copy.deepcopy(self.glossary)
        bad["rules"].reverse()
        with self.assertRaises(GlossaryError):
            validate_glossary(bad)
        bad = copy.deepcopy(self.glossary)
        bad["rules"][-1]["review"]["expected_rule_fingerprint"] = "0"*64
        with self.assertRaises(GlossaryError):
            validate_glossary(bad)
        resolution = resolve_applicable(self.glossary,self.structure,self.uid)
        resolution["approved_rules"][0]["target_term"] = "mutated copy"
        self.assertEqual(self.glossary["rules"][-1]["target_term"],"fixture target")

    def test_malformed_stores_and_invalid_proposal_rejected(self):
        for field,value in (("rules",None),("schema_version",True)):
            bad = copy.deepcopy(self.glossary);bad[field] = value
            with self.subTest(field=field),self.assertRaises(GlossaryError):
                validate_glossary(bad)
        for field,value in (("entries",None),("schema_version",True)):
            bad = new_memory_store();bad[field] = value
            with self.subTest(field=field),self.assertRaises(MemoryError):
                validate_memory(bad)
        start = self.unit["source_char_start"]
        for kw in ({"scope":{}},{"source_language":"fr"}):
            args = dict(store=new_glossary_store(),structure=self.structure,unit_id=self.uid,
                        source_language="en",source_char_start=start,source_char_end=start+3,target_term="fixture")
            args.update(kw)
            with self.assertRaises(GlossaryError):
                propose_rule(**args)

    def test_scope_change_stales_only_dependent_memory(self):
        other = self.structure["units"][1]["unit_id"]
        memory = self._remember(self.structure,self.uid,self.glossary)
        other_memory = self._remember(self.structure,other,self.glossary)
        r = self.glossary["rules"][-1]
        updated = review_rule(self.glossary,r["rule_id"],r["version"],fingerprint(r),
                              "fixture-human","human","simulated revised terminology","approved",target_term="new fixture target")
        self.assertEqual(lookup(memory,self.structure,self.uid,
                               resolve_applicable(updated,self.structure,self.uid))["outcome"],"stale_dependencies")
        self.assertEqual(lookup(other_memory,self.structure,other,
                               resolve_applicable(updated,self.structure,other))["outcome"],"reusable")
        self.assertEqual(len(memory["entries"]),1)
        self.assertEqual(self.glossary["rules"][-1]["target_term"],"fixture target")

    def test_review_metadata_and_external_view_change_do_not_invalidate(self):
        memory = self._remember(self.structure,self.uid,self.glossary)
        r = self.glossary["rules"][-1]
        updated = review_rule(self.glossary,r["rule_id"],r["version"],fingerprint(r),
                              "another-fixture-human","human","same policy checked again","approved")
        self.assertEqual(resolve_applicable(self.glossary,self.structure,self.uid)["policy_fingerprint"],
                         resolve_applicable(updated,self.structure,self.uid)["policy_fingerprint"])
        # View state has no place in source or effective-policy dependency identity.
        view_state = {"font_size":12,"direction":"rtl"}
        before = lookup(memory,self.structure,self.uid,resolve_applicable(updated,self.structure,self.uid))
        view_state.update(font_size=20)
        after = lookup(memory,self.structure,self.uid,resolve_applicable(updated,self.structure,self.uid))
        self.assertEqual(before,after)
        self.assertEqual(after["outcome"],"reusable")

    def test_boundary_round_trip_invalidates_old_unit_version_approval(self):
        glossary = new_glossary_store()
        memory = self._remember(self.structure,self.uid,glossary)
        document = extract_pdf(self.folder/"fixture.pdf",language="en")
        decisions = {r["page_id"]:_human_decision(r["alternatives"][0]) for r in build_readings(document)}
        merged = build_structure(document,decisions=decisions,previous=self.structure,
                                 boundaries={document.pages[0].page_id:[[0,len(document.pages[0].source_text)]]})
        restored = build_structure(document,decisions=decisions,previous=merged,
                                   unit_policy={"max_unit_words": 1})
        self.assertEqual(restored["units"][0]["unit_id"],self.uid)
        self.assertEqual(restored["units"][0]["unit_version"],3)
        result = lookup(memory,restored,self.uid,resolve_applicable(glossary,restored,self.uid))
        self.assertEqual(result["outcome"],"stale_dependencies")
        self.assertEqual(memory["entries"][0]["unit_version"],1)

    def test_malformed_policy_and_memory_source_binding_rejected(self):
        resolution = resolve_applicable(self.glossary,self.structure,self.uid)
        memory = self._remember(self.structure,self.uid,self.glossary)
        for field,value in (("status", "invalid"),("policy_fingerprint", "0"*64),("unit_hash","0"*64)):
            bad = copy.deepcopy(resolution);bad[field] = value
            with self.subTest(field=field),self.assertRaises(MemoryError):
                lookup(memory,self.structure,self.uid,bad)
        for mutate in (lambda x:x["entries"][0].update(page_id="wrong"),
                       lambda x:x["entries"][0].update(status="draft"),
                       lambda x:x["entries"][0]["source_unit"].update(unit_version=99),
                       lambda x:x["entries"][0]["policy_dependencies"][0].update(target_term="wrong")):
            bad = copy.deepcopy(memory);mutate(bad)
            with self.assertRaises(MemoryError):
                validate_memory(bad)

    def test_other_language_and_document_policy_does_not_invalidate(self):
        memory = self._remember(self.structure,self.uid,self.glossary)
        pdf = self.folder/"fr.pdf"
        c = canvas.Canvas(str(pdf),pagesize=LETTER)
        c.drawString(72,700,"Le logos est un terme dans cette phrase.")
        c.save()
        doc = extract_pdf(pdf,language="fr")
        decisions = {r["page_id"]:_human_decision(r["alternatives"][0]) for r in build_readings(doc)}
        structure = build_structure(doc,decisions=decisions)
        unit = structure["units"][0]
        start = unit["source_char_start"] + unit["text"].index("logos")
        extra = propose_rule(self.glossary,structure,unit["unit_id"],"fr",start,start+5,"fixture fr")
        rule = extra["rules"][-1]
        extra = review_rule(extra,rule["rule_id"],1,fingerprint(rule),"fixture-human","human","simulation","approved")
        self.assertEqual(lookup(memory,self.structure,self.uid,
                               resolve_applicable(extra,self.structure,self.uid))["outcome"],"reusable")


if __name__ == "__main__":
    unittest.main()
