"""Session D: semantic-unit, chapter-aware translation context strategy.

Covers the acceptance checks in audit/contracts/session_d_context_strategy.md:
whole-chapter-as-context vs bounded fallback, original source over any
summary, the three/five layered prompt sections, independent target-vs-
context recoverability, model-aware budgeting across two capability sizes,
the explicit whole-chapter *translation* comparison mode, a context
selection crossing a PDF page boundary inside one chapter, and cache/
provenance compatibility once `context_policy_version` exists.
"""
import tempfile
import unittest
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from scholarly_translation import context_strategy
from scholarly_translation.glossary import new_store as new_glossary_store
from scholarly_translation.model_config import ModelCapabilities
from scholarly_translation.pdf_extract import extract_pdf
from scholarly_translation.segmentation import build_structure
from scholarly_translation.source_reading import build_readings
from scholarly_translation.translation import (
    TranslationRequestError,
    build_context,
    build_translation_request,
    build_whole_chapter_translation_request,
    compute_cache_key,
    run_translation,
)


def _human_decision(candidate, reason="verified against page image") -> dict:
    return {
        "origin": candidate["origin"], "candidate_hash": candidate["candidate_hash"],
        "actor": "reviewer@example.org", "actor_kind": "human", "reason": reason,
    }


def _build_lines_pdf(path, lines) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    c.setFont("Helvetica", 12)
    y = height - 100
    for line in lines:
        c.drawString(72, y, line)
        y -= 20
    c.showPage()
    c.save()


def _build_pages_pdf(path, pages) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    c.setFont("Helvetica", 12)
    for lines in pages:
        y = height - 100
        for line in lines:
            c.drawString(72, y, line)
            y -= 20
        c.showPage()
    c.save()


def _single_page_structure(tmp_path, lines, unit_policy=None):
    pdf_path = tmp_path / "fixture.pdf"
    _build_lines_pdf(pdf_path, lines)
    document = extract_pdf(pdf_path, language="en")
    page = document.pages[0]
    reading = build_readings(document)[0]
    candidate = next(c for c in reading["alternatives"] if c["origin"] == "digital")
    decisions = {page.page_id: _human_decision(candidate)}
    return build_structure(document, decisions=decisions, unit_policy=unit_policy)


def _two_page_structure(tmp_path, pages, unit_policy=None):
    pdf_path = tmp_path / "fixture-two-pages.pdf"
    _build_pages_pdf(pdf_path, pages)
    document = extract_pdf(pdf_path, language="en")
    decisions = {}
    for page in document.pages:
        reading = next(r for r in build_readings(document) if r["page_id"] == page.page_id)
        candidate = next(c for c in reading["alternatives"] if c["origin"] == "digital")
        decisions[page.page_id] = _human_decision(candidate)
    return build_structure(document, decisions=decisions, unit_policy=unit_policy)


# One chapter heading plus five short single-sentence paragraphs. Pinning
# max_unit_words=1 keeps every line its own unit (no internal sentence
# boundary to split on), exactly as tests/test_translation.py already does,
# so unit boundaries are precisely predictable.
CHAPTER_LINES = [
    "Chapter One",
    "Alpha sentence introduces the topic.",
    "Beta sentence continues the discussion further.",
    "Gamma sentence is the target unit here today.",
    "Delta sentence adds another supporting point.",
    "Epsilon sentence concludes the chapter nicely.",
]


def _units_by_text_prefix(structure):
    return {u["text"].split()[0]: u for u in structure["units"]}


class ChapterLookupTests(unittest.TestCase):
    """Pure context_strategy behavior, independent of translation.py."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.structure = _single_page_structure(
            Path(self.tmp.name), CHAPTER_LINES, unit_policy={"max_unit_words": 1},
        )
        self.units = _units_by_text_prefix(self.structure)

    def tearDown(self):
        self.tmp.cleanup()

    def test_enclosing_chapter_found_for_body_unit(self):
        target = self.units["Gamma"]
        chapter = context_strategy.find_enclosing_chapter_node(self.structure, target)
        self.assertIsNotNone(chapter)
        self.assertEqual(chapter["kind"], "chapter")
        self.assertEqual(chapter["text"], "Chapter One")

    def test_flat_document_without_chapter_node_degrades_gracefully(self):
        flat_structure = _single_page_structure(
            Path(self.tmp.name),
            ["A short sentence with no heading at all.", "Another plain sentence follows."],
            unit_policy={"max_unit_words": 1},
        )
        unit = flat_structure["units"][0]
        self.assertIsNone(context_strategy.find_enclosing_chapter_node(flat_structure, unit))
        decision, segments = context_strategy.plan_context(
            flat_structure, unit, ModelCapabilities(context_window=1000, usable_context_tokens=500),
        )
        self.assertEqual(decision["context_mode"], "bounded_fallback")
        self.assertIsNone(decision["chapter_node_id"])
        self.assertTrue(any(s["role"] == "target" for s in segments))

    def test_chapter_span_covers_every_body_node_until_document_end(self):
        target = self.units["Gamma"]
        chapter = context_strategy.find_enclosing_chapter_node(self.structure, target)
        span = context_strategy.chapter_node_span(self.structure, chapter)
        self.assertEqual([n["text"] for n in span], [line for line in CHAPTER_LINES])

    def test_estimate_tokens_is_conservative_word_based_not_a_real_tokenizer(self):
        text = "Gamma sentence is the target unit here today."
        self.assertEqual(context_strategy.estimate_tokens(text), 8 * context_strategy.WORDS_TO_TOKENS_RATIO)


class ModelAwareBudgetingTests(unittest.TestCase):
    """Two different ModelCapabilities sizes over the same structure/unit
    must produce a different context scope (contract acceptance check)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.structure = _single_page_structure(
            Path(self.tmp.name), CHAPTER_LINES, unit_policy={"max_unit_words": 1},
        )
        self.units = _units_by_text_prefix(self.structure)
        self.target = self.units["Gamma"]

    def tearDown(self):
        self.tmp.cleanup()

    def _capabilities(self, usable_context_tokens):
        return ModelCapabilities(context_window=1_000_000, usable_context_tokens=usable_context_tokens)

    def test_large_budget_uses_whole_chapter_small_budget_falls_back(self):
        # Whole-chapter word total is 33 words -> 66 estimated tokens exactly.
        large = self._capabilities(66)
        small = self._capabilities(16)

        large_decision, large_segments = context_strategy.plan_context(
            self.structure, self.target, large, headroom_fraction=0.0,
        )
        small_decision, small_segments = context_strategy.plan_context(
            self.structure, self.target, small, headroom_fraction=0.0,
        )

        self.assertEqual(large_decision["context_mode"], "whole_chapter")
        self.assertEqual(small_decision["context_mode"], "bounded_fallback")

        large_text = " ".join(s["text"] for s in large_segments)
        small_text = " ".join(s["text"] for s in small_segments)
        self.assertIn("Alpha", large_text)
        self.assertIn("Epsilon", large_text)
        self.assertNotIn("Alpha", small_text)
        self.assertNotIn("Epsilon", small_text)
        self.assertNotIn("Beta", small_text)
        self.assertNotIn("Delta", small_text)

    def test_bounded_fallback_expands_to_fit_available_budget(self):
        # Exactly enough budget for target + one neighbor on each side
        # (Beta + Gamma + Delta = 12+16+12 = 40 estimated tokens) but not
        # the whole chapter (64) or the next ring out (Alpha/Epsilon).
        capabilities = self._capabilities(40)
        decision, segments = context_strategy.plan_context(
            self.structure, self.target, capabilities, headroom_fraction=0.0,
        )
        self.assertEqual(decision["context_mode"], "bounded_fallback")
        roles = sorted(s["role"] for s in segments)
        self.assertEqual(roles, ["next", "previous", "target"])
        text = " ".join(s["text"] for s in segments)
        self.assertIn("Beta", text)
        self.assertIn("Delta", text)
        self.assertNotIn("Alpha", text)
        self.assertNotIn("Epsilon", text)
        self.assertNotIn("Chapter One", text)

    def test_no_capabilities_keeps_exact_legacy_one_neighbor_each_side(self):
        segments = build_context(self.structure, self.target)
        roles = [s["role"] for s in segments]
        self.assertEqual(roles, ["previous", "target", "next"])


class OriginalSourceOverSummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.structure = _single_page_structure(
            Path(self.tmp.name), CHAPTER_LINES, unit_policy={"max_unit_words": 1},
        )
        self.units = _units_by_text_prefix(self.structure)

    def tearDown(self):
        self.tmp.cleanup()

    def test_whole_chapter_context_is_literal_concatenated_node_text(self):
        target = self.units["Gamma"]
        capabilities = ModelCapabilities(context_window=1000, usable_context_tokens=66)
        decision, segments = context_strategy.plan_context(
            self.structure, target, capabilities, headroom_fraction=0.0,
        )
        self.assertEqual(decision["context_mode"], "whole_chapter")
        before = next(s for s in segments if s["role"] == "chapter_before")
        after = next(s for s in segments if s["role"] == "chapter_after")
        self.assertEqual(before["text"], "Chapter One\n\nAlpha sentence introduces the topic.\n\n"
                                          "Beta sentence continues the discussion further.")
        self.assertEqual(after["text"], "Delta sentence adds another supporting point.\n\n"
                                         "Epsilon sentence concludes the chapter nicely.")
        # Every word of actual source context text is literally present in
        # the original reading text -- nothing paraphrased or generated.
        # (The "target_marker" segment is a fixed instructional string, not
        # source content, so it is deliberately excluded from this check.)
        reading_text = self.structure["readings"][0]["text"]
        for segment in segments:
            if segment["role"] in ("target_marker",):
                continue
            for fragment in segment["text"].split("\n\n"):
                self.assertIn(fragment, reading_text)


class LayeredPromptTests(unittest.TestCase):
    """Style / glossary-decisions / local-state (plus target vs context)
    stay separable sections, never one free-form blob."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.structure = _single_page_structure(
            Path(self.tmp.name), CHAPTER_LINES, unit_policy={"max_unit_words": 1},
        )
        self.units = _units_by_text_prefix(self.structure)
        self.glossary = new_glossary_store()

    def tearDown(self):
        self.tmp.cleanup()

    def test_five_labelled_sections_present_and_ordered(self):
        target = self.units["Gamma"]
        request = build_translation_request(
            self.structure, self.glossary, target["unit_id"], "scholarly", "mock", "mock-translation-1",
            local_state="Speaker: narrator.",
            approved_decisions=["gamma -> גמא (approved)"],
        )
        text = request.prompt_text
        for marker in (
            "STYLE_PROFILE", "GLOSSARY_AND_APPROVED_DECISIONS:", "LOCAL_STATE:",
            "SOURCE_CONTEXT:", "<TARGET_UNIT>",
        ):
            self.assertIn(marker, text)
        self.assertLess(text.index("GLOSSARY_AND_APPROVED_DECISIONS:"), text.index("LOCAL_STATE:"))
        self.assertLess(text.index("LOCAL_STATE:"), text.index("SOURCE_CONTEXT:"))
        self.assertLess(text.index("SOURCE_CONTEXT:"), text.index("<TARGET_UNIT>"))

    def test_target_and_context_are_independently_recoverable(self):
        target = self.units["Gamma"]
        capabilities = ModelCapabilities(context_window=1000, usable_context_tokens=40)
        request = build_translation_request(
            self.structure, self.glossary, target["unit_id"], "scholarly", "mock", "mock-translation-1",
            capabilities=capabilities, context_headroom_fraction=0.0,
        )
        metadata = request.to_metadata_dict()

        # "What exact text was translated?" -- answerable from target_source
        # alone, independent of context_source.
        from scholarly_translation.source_reading import text_hash
        self.assertEqual(metadata["target_source"]["text_hash"], text_hash(target["text"]))
        self.assertEqual(metadata["target_source"]["unit_ids"], [target["unit_id"]])

        # "What context did the model see?" -- answerable from context_source
        # alone, and it excludes the target's own text.
        context_roles = {s["role"] for s in metadata["context_source"]["segments"]}
        self.assertEqual(context_roles, {"previous", "next"})
        context_only_text = "".join(
            s["text"] for s in request.context_segments if s["role"] != "target"
        )
        self.assertNotIn("Gamma", context_only_text)
        self.assertIn("Beta", context_only_text)
        self.assertIn("Delta", context_only_text)
        self.assertIn("Gamma", request.target_text)


class WholeChapterTranslationModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.structure = _single_page_structure(
            Path(self.tmp.name), CHAPTER_LINES, unit_policy={"max_unit_words": 1},
        )
        self.units = _units_by_text_prefix(self.structure)
        self.glossary = new_glossary_store()
        self.target = self.units["Gamma"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_whole_chapter_mode_is_distinct_from_default_semantic_unit_mode(self):
        capabilities = ModelCapabilities(context_window=1000, usable_context_tokens=66)
        default_request = build_translation_request(
            self.structure, self.glossary, self.target["unit_id"], "scholarly", "mock", "mock-translation-1",
            capabilities=capabilities, context_headroom_fraction=0.0,
        )
        chapter_request = build_whole_chapter_translation_request(
            self.structure, self.glossary, self.target["unit_id"], "scholarly", "mock", "mock-translation-1",
            capabilities=capabilities, context_headroom_fraction=0.0,
        )
        self.assertEqual(default_request.context_mode, "whole_chapter")
        self.assertEqual(chapter_request.context_mode, "whole_chapter_translation")
        self.assertEqual(default_request.target_text, self.target["text"])
        self.assertEqual(len(default_request.target_unit_ids), 1)
        self.assertEqual(len(chapter_request.target_unit_ids), len(self.structure["units"]))
        self.assertIn("Alpha", chapter_request.target_text)
        self.assertIn("Epsilon", chapter_request.target_text)
        self.assertNotEqual(default_request.cache_key, chapter_request.cache_key)

    def test_whole_chapter_mode_is_not_the_default(self):
        capabilities = ModelCapabilities(context_window=1000, usable_context_tokens=66)
        request = build_translation_request(
            self.structure, self.glossary, self.target["unit_id"], "scholarly", "mock", "mock-translation-1",
            capabilities=capabilities, context_headroom_fraction=0.0,
        )
        self.assertNotEqual(request.context_mode, "whole_chapter_translation")

    def test_whole_chapter_mode_requires_capabilities_and_a_chapter(self):
        with self.assertRaises(TranslationRequestError):
            build_whole_chapter_translation_request(
                self.structure, self.glossary, self.target["unit_id"], "scholarly", "mock", "mock-translation-1",
            )

    def test_whole_chapter_mode_refuses_a_chapter_too_large_for_the_budget(self):
        tiny = ModelCapabilities(context_window=1000, usable_context_tokens=10)
        with self.assertRaises(TranslationRequestError):
            build_whole_chapter_translation_request(
                self.structure, self.glossary, self.target["unit_id"], "scholarly", "mock", "mock-translation-1",
                capabilities=tiny, context_headroom_fraction=0.0,
            )

    def test_whole_chapter_mode_runs_through_run_translation(self):
        capabilities = ModelCapabilities(context_window=1000, usable_context_tokens=66)
        request = build_whole_chapter_translation_request(
            self.structure, self.glossary, self.target["unit_id"], "scholarly", "mock", "mock-translation-1",
            capabilities=capabilities, context_headroom_fraction=0.0,
        )
        draft = run_translation(request)
        self.assertFalse(draft["approved"])
        self.assertEqual(draft["context_mode"], "whole_chapter_translation")
        self.assertEqual(len(draft["target_source"]["unit_ids"]), len(self.structure["units"]))


class PageBoundaryContextTests(unittest.TestCase):
    def test_whole_chapter_context_crosses_a_pdf_page_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            structure = _two_page_structure(Path(tmp), [
                ["Chapter One", "Opening paragraph ends here cleanly."],
                ["Continuation paragraph follows on the next page."],
            ])
            page_ids = [p["page_id"] for p in structure["units"]]
            self.assertEqual(len(set(page_ids)), 2, "fixture must actually span two pages")
            target = next(u for u in structure["units"] if u["text"].startswith("Opening"))
            capabilities = ModelCapabilities(context_window=1000, usable_context_tokens=100)
            decision, segments = context_strategy.plan_context(
                structure, target, capabilities, headroom_fraction=0.0,
            )
            self.assertEqual(decision["context_mode"], "whole_chapter")
            self.assertTrue(decision["crosses_page_boundary"])
            after = next(s for s in segments if s["role"] == "chapter_after")
            self.assertIn("Continuation paragraph follows on the next page.", after["text"])

            glossary = new_glossary_store()
            request = build_translation_request(
                structure, glossary, target["unit_id"], "scholarly", "mock", "mock-translation-1",
                capabilities=capabilities, context_headroom_fraction=0.0,
            )
            self.assertTrue(request.crosses_page_boundary)
            self.assertTrue(request.to_metadata_dict()["crosses_page_boundary"])
            self.assertIn("Continuation paragraph", request.prompt_text)


class CacheProvenanceCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.structure = _single_page_structure(
            Path(self.tmp.name), CHAPTER_LINES, unit_policy={"max_unit_words": 1},
        )
        self.units = _units_by_text_prefix(self.structure)
        self.glossary = new_glossary_store()

    def tearDown(self):
        self.tmp.cleanup()

    def test_context_policy_version_and_mode_are_recorded_and_change_cache_key(self):
        target = self.units["Gamma"]
        no_caps = build_translation_request(
            self.structure, self.glossary, target["unit_id"], "scholarly", "mock", "mock-translation-1",
        )
        self.assertEqual(no_caps.context_policy_version, context_strategy.CONTEXT_POLICY_VERSION)
        self.assertEqual(no_caps.context_mode, "bounded_fallback")
        self.assertEqual(no_caps.to_metadata_dict()["context_policy_version"], context_strategy.CONTEXT_POLICY_VERSION)

        with_caps = build_translation_request(
            self.structure, self.glossary, target["unit_id"], "scholarly", "mock", "mock-translation-1",
            capabilities=ModelCapabilities(context_window=1000, usable_context_tokens=66),
            context_headroom_fraction=0.0,
        )
        self.assertEqual(with_caps.context_mode, "whole_chapter")
        self.assertNotEqual(no_caps.cache_key, with_caps.cache_key)

    def test_pre_session_d_compute_cache_key_callers_still_work(self):
        # Mirrors the exact kwargs shape used by tests/test_translation.py and
        # tests/test_model_config.py before context_policy_version/context_mode
        # existed; both are optional with defaults, so this keeps compiling
        # and the inequality behavior those tests rely on is unaffected.
        kwargs = dict(
            profile_id="scholarly", pdf_hash="a", source_uri="b", document_id="c",
            reading_id="d", reading_version=1, reading_text_hash="e", unit_id="f",
            unit_version=1, source_char_start=0, source_char_end=1, unit_text_hash="g",
            neighbor_fingerprint="h", policy_fingerprint="i", prompt_version="p",
            config_version="c", decoding_params={},
        )
        one = compute_cache_key(provider="openai", model="one", **kwargs)
        two = compute_cache_key(provider="openai", model="two", **kwargs)
        self.assertNotEqual(one, two)

    def test_unrelated_chapter_text_elsewhere_does_not_invalidate_cache(self):
        """Session D invalidation rule: a unit's cache key depends only on the
        text actually sent (target + the context actually included), never on
        unrelated text elsewhere in the chapter that was not part of that."""
        target = self.units["Gamma"]
        small_caps = ModelCapabilities(context_window=1000, usable_context_tokens=16)
        baseline = build_translation_request(
            self.structure, self.glossary, target["unit_id"], "scholarly", "mock", "mock-translation-1",
            capabilities=small_caps, context_headroom_fraction=0.0,
        )
        self.assertEqual(baseline.context_mode, "bounded_fallback")
        self.assertEqual(len(baseline.context_segments), 1)  # target only, per the tiny budget

        import copy
        mutated = copy.deepcopy(self.structure)
        epsilon = next(u for u in mutated["units"] if u["text"].startswith("Epsilon"))
        epsilon["warnings"] = list(epsilon["warnings"]) + ["unrelated_note_elsewhere_in_chapter"]
        again = build_translation_request(
            mutated, self.glossary, target["unit_id"], "scholarly", "mock", "mock-translation-1",
            capabilities=small_caps, context_headroom_fraction=0.0,
        )
        self.assertEqual(baseline.cache_key, again.cache_key)

    def test_whole_chapter_context_fingerprint_does_change_when_included_text_changes(self):
        """By contrast, once a node *is* actually sent as context
        (whole_chapter mode includes the whole chapter), a change to that
        node's text legitimately changes what was sent, so the context
        fingerprint feeding the cache key must change too. This is checked
        at the context_strategy level (a pure function of the structure
        dict's fields), since mutating real node text and re-validating the
        full persisted-structure schema is its own, unrelated concern."""
        import copy

        target = self.units["Gamma"]
        large_caps = ModelCapabilities(context_window=1000, usable_context_tokens=66)
        baseline_decision, baseline_segments = context_strategy.plan_context(
            self.structure, target, large_caps, headroom_fraction=0.0,
        )
        self.assertEqual(baseline_decision["context_mode"], "whole_chapter")

        mutated = copy.deepcopy(self.structure)
        for node in mutated["nodes"]:
            if node["text"].startswith("Epsilon"):
                node["text"] = "Epsilon sentence concludes the chapter differently."
        mutated_decision, mutated_segments = context_strategy.plan_context(
            mutated, target, large_caps, headroom_fraction=0.0,
        )
        self.assertEqual(mutated_decision["context_mode"], "whole_chapter")

        from scholarly_translation.source_reading import fingerprint
        self.assertNotEqual(fingerprint(baseline_segments), fingerprint(mutated_segments))

        base_key = compute_cache_key(
            profile_id="scholarly", pdf_hash="a", source_uri="b", document_id="c",
            reading_id="d", reading_version=1, reading_text_hash="e", unit_id=target["unit_id"],
            unit_version=1, source_char_start=0, source_char_end=1, unit_text_hash="g",
            neighbor_fingerprint=fingerprint(baseline_segments), policy_fingerprint="i",
            provider="mock", model="mock-translation-1", prompt_version="p", config_version="c",
            decoding_params={}, context_mode="whole_chapter",
        )
        changed_key = compute_cache_key(
            profile_id="scholarly", pdf_hash="a", source_uri="b", document_id="c",
            reading_id="d", reading_version=1, reading_text_hash="e", unit_id=target["unit_id"],
            unit_version=1, source_char_start=0, source_char_end=1, unit_text_hash="g",
            neighbor_fingerprint=fingerprint(mutated_segments), policy_fingerprint="i",
            provider="mock", model="mock-translation-1", prompt_version="p", config_version="c",
            decoding_params={}, context_mode="whole_chapter",
        )
        self.assertNotEqual(base_key, changed_key)


if __name__ == "__main__":
    unittest.main()
