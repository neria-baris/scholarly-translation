import copy
import hashlib
import json
import tempfile
import unittest
import unittest.mock
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from scholarly_translation.__main__ import cmd_translate_unit
from scholarly_translation.formal_checks import run_formal_checks
from scholarly_translation.glossary import (
    new_store as new_glossary_store, propose_rule, review_rule, validate_glossary,
)
from scholarly_translation.model_adapter import (
    MockTextGenerationAdapter,
    OpenAIConfigurationError,
    OpenAITextGenerationAdapter,
    RequestValidationError,
    build_translation_adapter,
)
from scholarly_translation.pdf_extract import extract_pdf
from scholarly_translation.records import Document, Page, Segment
from scholarly_translation.segmentation import build_structure
from scholarly_translation.source_reading import build_readings, fingerprint, text_hash
from scholarly_translation.store import deterministic_id
from scholarly_translation.translation import (
    TranslationBudget,
    TranslationBudgetError,
    TranslationRequestError,
    build_context,
    build_translation_request,
    compute_cache_key,
    run_translation,
)


def _human_decision(candidate, reason="verified against page image") -> dict:
    return {
        "origin": candidate["origin"], "candidate_hash": candidate["candidate_hash"],
        "actor": "reviewer@example.org", "actor_kind": "human", "reason": reason,
    }


def _build_structure_for_lines(tmp_path, lines, language):
    pdf_path = tmp_path / "fixture.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=LETTER)
    width, height = LETTER
    c.setFont("Helvetica", 14)
    for i, line in enumerate(lines):
        c.drawString(72, height - 100 - i * 30, line)
    c.showPage()
    c.save()

    document = extract_pdf(pdf_path, language=language)
    page = document.pages[0]
    reading = build_readings(document)[0]
    candidate = next(cand for cand in reading["alternatives"] if cand["origin"] == "digital")
    decisions = {page.page_id: _human_decision(candidate)}
    return build_structure(document, decisions=decisions)


def _synthetic_source_structure(tmp_path, language, text):
    """A declared synthetic PDF envelope; source text is fixture data."""
    source_path = tmp_path / f"source-{language}.pdf"
    c = canvas.Canvas(str(source_path), pagesize=LETTER)
    c.drawString(72, 700, "Synthetic fixture envelope")
    c.showPage()
    c.save()
    document_id = deterministic_id("gate7-synthetic", language)
    page_id = deterministic_id(document_id, "page", "1")
    source_text = text + "\n"
    segment = Segment(
        segment_id=deterministic_id(page_id, "line", "1"), page_id=page_id,
        order=1, text=text, source_char_start=0, source_char_end=len(text),
        bbox=(10, 10, 500, 30),
    )
    page = Page(
        page_id=page_id, document_id=document_id, page_number=1, segments=[segment],
        width=600, height=800, source_text=source_text,
    )
    document = Document(
        schema_version=3, document_id=document_id, document_version=1,
        language=language, source_kind="pdf", source_uri=source_path.resolve().as_uri(),
        pages=[page], stage_id="digital-pdf", stage_version=1,
        input_hash=hashlib.sha256(source_path.read_bytes()).hexdigest(),
        status="synthetic", warnings=["synthetic_not_quality_evidence"],
    )
    candidate = build_readings(document)[0]["alternatives"][0]
    return build_structure(document, decisions={page_id: _human_decision(candidate, "simulated fixture selection")})


def _approved_glossary(structure, unit, term, target_term, loaded=False, store=None):
    store = new_glossary_store() if store is None else store
    start = unit["text"].index(term) + unit["source_char_start"]
    end = start + len(term)
    store = propose_rule(store, structure, unit["unit_id"], "en", start, end, target_term, loaded=loaded)
    rule = store["rules"][-1]
    return review_rule(
        store, rule["rule_id"], rule["version"], fingerprint(rule),
        "editor@example.org", "human", "approved for gate 7 fixture", "approved",
    )


class ContextAndCacheKeyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.structure = _build_structure_for_lines(
            Path(self.tmp.name),
            ["The logos is central to the argument.", "Later the logos returns once more."],
            "en",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_source_bound_requests_for_each_available_language(self):
        samples = {"en": "Axiom 3 remains true.", "fr": "Le théorème 3 reste valide.", "ja": "定理3は成り立つ。"}
        for language, text in samples.items():
            with self.subTest(language=language):
                structure = _synthetic_source_structure(Path(self.tmp.name), language, text)
                unit = structure["units"][0]
                request = build_translation_request(
                    structure, new_glossary_store(), unit["unit_id"],
                    "scholarly", "mock", "mock-translation-1",
                )
                self.assertEqual(request.source_language, language)
                self.assertEqual(request.to_metadata_dict()["source_text_hash"], text_hash(text))
                self.assertFalse(run_translation(request)["approved"])

    def test_context_includes_only_same_reading_neighbors(self):
        units = sorted(self.structure["units"], key=lambda u: u["source_char_start"])
        self.assertEqual(len(units), 2)
        segments = build_context(self.structure, units[0])
        roles = [s["role"] for s in segments]
        self.assertEqual(roles, ["target", "next"])
        segments = build_context(self.structure, units[1])
        roles = [s["role"] for s in segments]
        self.assertEqual(roles, ["previous", "target"])

    def test_cache_key_changes_on_source_boundary(self):
        unit = self.structure["units"][0]
        base_kwargs = dict(
            profile_id="scholarly", pdf_hash=self.structure["pdf_hash"], source_uri=self.structure["source_uri"],
            document_id=unit["document_id"], reading_id=unit["reading_id"], reading_version=unit["reading_version"],
            reading_text_hash=unit["reading_text_hash"], unit_id=unit["unit_id"], unit_version=unit["unit_version"],
            source_char_start=unit["source_char_start"], source_char_end=unit["source_char_end"],
            unit_text_hash="a" * 64, neighbor_fingerprint="b" * 64, policy_fingerprint="c" * 64,
            provider="mock", model="mock-translation-1", prompt_version="scholarly-first-draft@1",
            config_version="scholarly-first-draft@1", decoding_params={"max_output_tokens": 256, "temperature": 0},
        )
        key1 = compute_cache_key(**base_kwargs)
        changed = dict(base_kwargs, unit_text_hash="d" * 64)
        key2 = compute_cache_key(**changed)
        self.assertNotEqual(key1, key2)

    def test_cache_key_changes_on_policy_and_provider_and_model(self):
        unit = self.structure["units"][0]
        base_kwargs = dict(
            profile_id="scholarly", pdf_hash=self.structure["pdf_hash"], source_uri=self.structure["source_uri"],
            document_id=unit["document_id"], reading_id=unit["reading_id"], reading_version=unit["reading_version"],
            reading_text_hash=unit["reading_text_hash"], unit_id=unit["unit_id"], unit_version=unit["unit_version"],
            source_char_start=unit["source_char_start"], source_char_end=unit["source_char_end"],
            unit_text_hash="a" * 64, neighbor_fingerprint="b" * 64, policy_fingerprint="c" * 64,
            provider="mock", model="mock-translation-1", prompt_version="scholarly-first-draft@1",
            config_version="scholarly-first-draft@1", decoding_params={"max_output_tokens": 256, "temperature": 0},
        )
        key1 = compute_cache_key(**base_kwargs)
        self.assertNotEqual(key1, compute_cache_key(**dict(base_kwargs, policy_fingerprint="e" * 64)))
        self.assertNotEqual(key1, compute_cache_key(**dict(base_kwargs, provider="openai", model="gpt-6-luna")))
        self.assertNotEqual(key1, compute_cache_key(**dict(base_kwargs, neighbor_fingerprint="f" * 64)))


class BuildTranslationRequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.structure = _build_structure_for_lines(
            Path(self.tmp.name),
            ["The logos is central to the argument.", "Later the logos returns once more."],
            "en",
        )
        self.unit = sorted(self.structure["units"], key=lambda u: u["source_char_start"])[0]
        self.glossary = new_glossary_store()

    def tearDown(self):
        self.tmp.cleanup()

    def test_unsupported_profile_rejected(self):
        with self.assertRaises(TranslationRequestError):
            build_translation_request(
                self.structure, self.glossary, self.unit["unit_id"], "generic", "mock", "mock-translation-1",
            )

    def test_unknown_unit_rejected(self):
        with self.assertRaises(TranslationRequestError):
            build_translation_request(
                self.structure, self.glossary, "no-such-unit", "scholarly", "mock", "mock-translation-1",
            )

    def test_continuity_findings_block_request(self):
        bad_structure = copy.deepcopy(self.structure)
        bad_structure["continuity"] = [{"type": "overlap"}]
        with self.assertRaises(TranslationRequestError):
            build_translation_request(
                bad_structure, self.glossary, self.unit["unit_id"], "scholarly", "mock", "mock-translation-1",
            )

    def test_conflicting_glossary_resolution_blocks_request(self):
        units = sorted(self.structure["units"], key=lambda u: u["source_char_start"])
        store = _approved_glossary(self.structure, units[0], "logos", "לוגוס-א")
        store = _approved_glossary(self.structure, units[1], "logos", "לוגוס-ב", store=store)
        with self.assertRaises(TranslationRequestError):
            build_translation_request(
                self.structure, store, units[0]["unit_id"], "scholarly", "mock", "mock-translation-1",
            )

    def test_malformed_structure_rejected(self):
        with self.assertRaises(Exception):
            build_translation_request(
                {"not": "a structure"}, self.glossary, self.unit["unit_id"], "scholarly", "mock", "mock-translation-1",
            )

    def test_oversized_prompt_rejected(self):
        huge_structure = copy.deepcopy(self.structure)
        for unit in huge_structure["units"]:
            unit["text"] = unit["text"]
        with unittest.mock.patch("scholarly_translation.translation.MAX_PROMPT_BYTES", 10):
            with self.assertRaises(TranslationRequestError):
                build_translation_request(
                    self.structure, self.glossary, self.unit["unit_id"], "scholarly", "mock", "mock-translation-1",
                )

    def test_dependency_unaffected_by_unrelated_structure_change(self):
        request1 = build_translation_request(
            self.structure, self.glossary, self.unit["unit_id"], "scholarly", "mock", "mock-translation-1",
        )
        unrelated = copy.deepcopy(self.structure)
        other_unit = next(u for u in unrelated["units"] if u["unit_id"] != self.unit["unit_id"])
        other_unit["warnings"] = list(other_unit["warnings"]) + ["unrelated_ui_note"]
        request2 = build_translation_request(
            unrelated, self.glossary, self.unit["unit_id"], "scholarly", "mock", "mock-translation-1",
        )
        self.assertEqual(request1.cache_key, request2.cache_key)

    def test_applicable_approved_glossary_reaches_provider_prompt(self):
        baseline = build_translation_request(
            self.structure, new_glossary_store(), self.unit["unit_id"],
            "scholarly", "mock", "mock-translation-1",
        )
        store = _approved_glossary(self.structure, self.unit, "logos", "לוגוס")
        request = build_translation_request(
            self.structure, store, self.unit["unit_id"], "scholarly", "mock", "mock-translation-1",
        )
        self.assertEqual(len(request.applicable_rules), 1)
        self.assertIn('"source_term": "logos"', request.prompt_text)
        self.assertIn('"target_term": "לוגוס"', request.prompt_text)
        self.assertEqual(request.to_metadata_dict()["prompt_hash"], text_hash(request.prompt_text))
        self.assertNotEqual(request.cache_key, baseline.cache_key)

    def test_unrelated_glossary_scope_does_not_change_cache_key(self):
        baseline = build_translation_request(
            self.structure, new_glossary_store(), self.unit["unit_id"],
            "scholarly", "mock", "mock-translation-1",
        )
        other_unit = next(u for u in self.structure["units"] if u["unit_id"] != self.unit["unit_id"])
        start = other_unit["text"].index("logos") + other_unit["source_char_start"]
        store = propose_rule(
            new_glossary_store(), self.structure, other_unit["unit_id"], "en",
            start, start + len("logos"), "לוגוס",
            scope={"document_ids": [], "unit_ids": [other_unit["unit_id"]]},
        )
        rule = store["rules"][-1]
        store = review_rule(
            store, rule["rule_id"], rule["version"], fingerprint(rule),
            "fixture-editor", "human", "simulated test approval", "approved",
        )
        request = build_translation_request(
            self.structure, store, self.unit["unit_id"],
            "scholarly", "mock", "mock-translation-1",
        )
        self.assertEqual(request.cache_key, baseline.cache_key)

    def test_proposed_loaded_term_is_not_sent_as_an_instruction(self):
        start = self.unit["text"].index("logos") + self.unit["source_char_start"]
        store = propose_rule(
            new_glossary_store(), self.structure, self.unit["unit_id"], "en",
            start, start + len("logos"), "מונח מוצע", loaded=True,
        )
        request = build_translation_request(
            self.structure, store, self.unit["unit_id"], "scholarly", "mock", "mock-translation-1",
        )
        self.assertNotIn("מונח מוצע", request.prompt_text)
        draft = run_translation(request)
        self.assertTrue(any(f["type"] == "unapproved_loaded_term" for f in draft["findings"]))


class RunTranslationMockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.structure = _build_structure_for_lines(
            Path(self.tmp.name), ["The logos is central to the argument."], "en",
        )
        self.unit = self.structure["units"][0]
        self.glossary = new_glossary_store()

    def tearDown(self):
        self.tmp.cleanup()

    def test_mock_result_is_non_hebrew_placeholder_never_approved(self):
        request = build_translation_request(
            self.structure, self.glossary, self.unit["unit_id"], "scholarly", "mock", "mock-translation-1",
        )
        draft = run_translation(request)
        self.assertEqual(draft["status"], "mock_placeholder")
        self.assertIn("GATE7-MOCK-PLACEHOLDER-NON-HEBREW", draft["draft_text"])
        self.assertNotIn(self.unit["text"], draft["draft_text"])
        self.assertFalse(draft["approved"])
        self.assertEqual(draft["token_usage"], "not_metered")


class TranslationBudgetTests(unittest.TestCase):
    def test_conservative_preflight_refuses_too_small_cap(self):
        budget = TranslationBudget(max_calls=3, hard_list_usd=0.000001)
        with self.assertRaises(TranslationBudgetError):
            budget.reserve("short prompt")
        self.assertEqual(budget.calls, 0)

    def test_preflight_emits_fifty_and_eighty_percent_notices(self):
        budget = TranslationBudget(max_calls=3, hard_list_usd=0.003)
        notices = budget.reserve("x" * 11000)
        self.assertIn("budget_preflight_50_percent", notices)
        self.assertIn("budget_preflight_80_percent", notices)


class FakeResponses:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc

    def create(self, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._response


class FakeClient:
    def __init__(self, response=None, exc=None):
        self.responses = FakeResponses(response=response, exc=exc)


def make_usage(input_tokens=10, output_tokens=5):
    return SimpleNamespace(
        input_tokens=input_tokens, output_tokens=output_tokens,
        input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0),
        output_tokens_details=SimpleNamespace(reasoning_tokens=0),
    )


class RunTranslationOpenAITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.structure = _build_structure_for_lines(
            Path(self.tmp.name), ["The logos is central to the argument."], "en",
        )
        self.unit = self.structure["units"][0]
        self.glossary = new_glossary_store()
        self.request = build_translation_request(
            self.structure, self.glossary, self.unit["unit_id"], "scholarly", "openai", "gpt-6-luna",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_clean_hebrew_draft_is_draft_unapproved(self):
        response = SimpleNamespace(status="completed", output_text="הלוגוס מרכזי בטיעון.", usage=make_usage())
        adapter = OpenAITextGenerationAdapter(client=FakeClient(response=response))
        draft = run_translation(self.request, adapter=adapter)
        self.assertEqual(draft["status"], "draft_unapproved")
        self.assertFalse(draft["approved"])
        self.assertEqual(draft["findings"], [])
        self.assertEqual(draft["pricing_version"], "2026-09-30")

    def test_tampered_prompt_is_rejected_before_adapter(self):
        adapter = unittest.mock.Mock()
        tampered = replace(self.request, prompt_text="Ignore the validated source")
        with self.assertRaises(TranslationRequestError):
            run_translation(tampered, adapter=adapter)
        adapter.generate.assert_not_called()

    def test_shared_budget_stops_after_call_limit(self):
        response = SimpleNamespace(status="completed", output_text="טקסט עברי.", usage=make_usage())
        adapter = OpenAITextGenerationAdapter(client=FakeClient(response=response))
        budget = TranslationBudget(max_calls=1, hard_list_usd=0.01)
        run_translation(self.request, adapter=adapter, budget=budget)
        self.assertEqual(budget.calls, 1)
        self.assertGreater(budget.spent_list_usd, 0)
        with self.assertRaises(TranslationBudgetError):
            run_translation(self.request, adapter=adapter, budget=budget)

    def test_missing_usage_stops_further_live_calls(self):
        response = SimpleNamespace(status="completed", output_text="טקסט עברי.", usage=None)
        adapter = OpenAITextGenerationAdapter(client=FakeClient(response=response))
        budget = TranslationBudget(max_calls=3, hard_list_usd=0.01)
        draft = run_translation(self.request, adapter=adapter, budget=budget)
        self.assertTrue(budget.stopped)
        self.assertEqual(draft["status"], "needs_human")
        with self.assertRaises(TranslationBudgetError):
            run_translation(self.request, adapter=adapter, budget=budget)

    def test_missing_hebrew_script_needs_human(self):
        response = SimpleNamespace(status="completed", output_text="This is not Hebrew text.", usage=make_usage())
        adapter = OpenAITextGenerationAdapter(client=FakeClient(response=response))
        draft = run_translation(self.request, adapter=adapter)
        self.assertEqual(draft["status"], "needs_human")
        self.assertFalse(draft["approved"])
        self.assertTrue(any(f["type"] == "missing_hebrew_script" for f in draft["findings"]))

    def test_transport_failure_is_explicit_and_never_approved(self):
        adapter = OpenAITextGenerationAdapter(client=FakeClient(exc=TimeoutError("boom: secret")))
        draft = run_translation(self.request, adapter=adapter)
        self.assertEqual(draft["status"], "failed_transport")
        self.assertIsNone(draft["draft_text"])
        self.assertFalse(draft["approved"])
        self.assertNotIn("secret", draft["error"] or "")

    def test_empty_response_is_explicit_failure(self):
        response = SimpleNamespace(status="completed", output_text="", usage=make_usage())
        adapter = OpenAITextGenerationAdapter(client=FakeClient(response=response))
        draft = run_translation(self.request, adapter=adapter)
        self.assertEqual(draft["status"], "failed_empty_response")
        self.assertFalse(draft["approved"])

    def test_missing_key_raises_before_network(self):
        with unittest.mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(OpenAIConfigurationError):
                run_translation(self.request, adapter=OpenAITextGenerationAdapter(client=None))

    def test_exact_request_params(self):
        captured = {}
        orig_create = FakeResponses.create

        class CapturingResponses(FakeResponses):
            def create(self, **kwargs):
                captured.update(kwargs)
                return orig_create(self, **kwargs)

        client = FakeClient()
        client.responses = CapturingResponses(
            response=SimpleNamespace(status="completed", output_text="הלוגוס", usage=make_usage()),
        )
        adapter = OpenAITextGenerationAdapter(client=client)
        run_translation(self.request, adapter=adapter)
        self.assertEqual(captured["model"], "gpt-6-luna")
        self.assertEqual(captured["store"], False)
        self.assertEqual(captured["tools"], [])
        self.assertEqual(captured["reasoning"], {"effort": "none"})
        self.assertEqual(captured["max_output_tokens"], 256)


class FormalChecksTests(unittest.TestCase):
    def test_missing_number_flagged(self):
        findings = run_formal_checks("There are 42 cases.", "אין מספרים כאן.", "en")
        self.assertTrue(any(f["type"] == "missing_number" for f in findings))

    def test_number_present_not_flagged(self):
        findings = run_formal_checks("There are 42 cases.", "יש 42 מקרים.", "en")
        self.assertFalse(any(f["type"] == "missing_number" for f in findings))

    def test_number_substring_and_duplicate_do_not_count_as_preserved(self):
        findings = run_formal_checks("3 and 3", "יש 13 וגם 3", "en")
        self.assertEqual(sum(f["type"] == "missing_number" for f in findings), 1)

    def test_missing_footnote_and_formula_tokens_are_reported(self):
        findings = run_formal_checks("Note†: E=mc^2.", "הערה: נוסחה.", "en")
        types = {f["type"] for f in findings}
        self.assertIn("missing_footnote_marker", types)
        self.assertIn("missing_formula_token", types)

    def test_citation_missing_flagged(self):
        findings = run_formal_checks("As shown (Smith, 2020).", "כפי שהוצג.", "en")
        self.assertTrue(any(f["type"] == "missing_citation_reference" for f in findings))

    def test_proper_name_always_surfaced_not_asserted_wrong(self):
        findings = run_formal_checks("Plato wrote this.", "אפלטון כתב את זה.", "en")
        name_findings = [f for f in findings if f["type"] == "proper_name_candidate"]
        self.assertEqual(len(name_findings), 1)
        self.assertEqual(name_findings[0]["target_evidence"], "uncertain_transliteration_not_asserted")

    def test_missing_hebrew_script_flagged(self):
        findings = run_formal_checks("Plain text.", "Plain text in Latin only.", "en")
        self.assertTrue(any(f["type"] == "missing_hebrew_script" for f in findings))

    def test_clean_draft_no_findings_besides_names(self):
        findings = run_formal_checks("hello world", "שלום עולם", "en")
        self.assertEqual(findings, [])

    def test_none_target_never_crashes(self):
        findings = run_formal_checks("There are 42 cases (Smith, 2020).", None, "en")
        self.assertTrue(len(findings) >= 2)


class TranslationAdapterBuilderTests(unittest.TestCase):
    def test_build_mock_adapter(self):
        self.assertIsInstance(build_translation_adapter("mock", "mock-translation-1"), MockTextGenerationAdapter)

    def test_build_supports_anthropic_provider(self):
        from scholarly_translation.model_adapter import AnthropicTextGenerationAdapter
        self.assertIsInstance(
            build_translation_adapter("anthropic", "configured-claude-model"),
            AnthropicTextGenerationAdapter,
        )

    def test_build_rejects_unsupported_model(self):
        with self.assertRaises(RequestValidationError):
            build_translation_adapter("mock", "not-a-model")


class TranslateUnitCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp.name)
        self.structure = _build_structure_for_lines(
            tmp_path, ["The logos is central to the argument."], "en",
        )
        self.unit = self.structure["units"][0]
        self.structure_path = tmp_path / "structure.json"
        self.structure_path.write_text(json.dumps(self.structure, ensure_ascii=False), encoding="utf-8")
        self.glossary_path = tmp_path / "glossary.json"
        self.glossary_path.write_text(json.dumps(new_glossary_store(), ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_mock_round_trip(self):
        out_dir = Path(self.tmp.name) / "out"
        rc = cmd_translate_unit(
            str(self.structure_path), str(self.glossary_path), self.unit["unit_id"],
            "scholarly", "mock", str(out_dir),
        )
        self.assertEqual(rc, 0)
        draft_path = out_dir / "translation_draft.json"
        self.assertTrue(draft_path.exists())
        data = json.loads(draft_path.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "mock_placeholder")
        self.assertFalse(data["approved"])

    def test_refuses_to_overwrite_existing_draft(self):
        out_dir = Path(self.tmp.name) / "out"
        self.assertEqual(cmd_translate_unit(
            str(self.structure_path), str(self.glossary_path), self.unit["unit_id"],
            "scholarly", "mock", str(out_dir),
        ), 0)
        rc = cmd_translate_unit(
            str(self.structure_path), str(self.glossary_path), self.unit["unit_id"],
            "scholarly", "mock", str(out_dir),
        )
        self.assertEqual(rc, 1)

    def test_refuses_output_colliding_with_structure(self):
        rc = cmd_translate_unit(
            str(self.structure_path), str(self.glossary_path), self.unit["unit_id"],
            "scholarly", "mock", str(self.structure_path.parent),
        )
        self.assertEqual(rc, 1)
        self.assertFalse((self.structure_path.parent / "translation_draft.json").exists())

    def test_unsafe_output_path_rejected(self):
        package_dir = Path(__file__).resolve().parents[1] / "scholarly_translation"
        rc = cmd_translate_unit(
            str(self.structure_path), str(self.glossary_path), self.unit["unit_id"],
            "scholarly", "mock", str(package_dir),
        )
        self.assertEqual(rc, 1)

    def test_openai_without_key_produces_no_call_or_output(self):
        out_dir = Path(self.tmp.name) / "out-openai"
        with unittest.mock.patch.dict("os.environ", {}, clear=True):
            rc = cmd_translate_unit(
                str(self.structure_path), str(self.glossary_path), self.unit["unit_id"],
                "scholarly", "openai", str(out_dir),
            )
        self.assertEqual(rc, 1)
        self.assertFalse((out_dir / "translation_draft.json").exists())

    def test_unknown_unit_id_returns_nonzero_without_traceback(self):
        out_dir = Path(self.tmp.name) / "out-bad-unit"
        rc = cmd_translate_unit(
            str(self.structure_path), str(self.glossary_path), "not-a-real-unit",
            "scholarly", "mock", str(out_dir),
        )
        self.assertEqual(rc, 1)

    def test_malformed_structure_json_returns_nonzero(self):
        bad_path = Path(self.tmp.name) / "bad_structure.json"
        bad_path.write_text('{"a": 1, "a": 2}', encoding="utf-8")
        out_dir = Path(self.tmp.name) / "out-bad-structure"
        rc = cmd_translate_unit(
            str(bad_path), str(self.glossary_path), self.unit["unit_id"], "scholarly", "mock", str(out_dir),
        )
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
