"""Offline fixtures for learning_render; pure string transforms, no model calls."""
import unittest

from scholarly_translation.learning_contracts import LearningError
from scholarly_translation.learning_render import render_chunk, render_recap


def source_units():
    return [
        {"unit_id": "unit-one", "kind": "paragraph", "text": "הילד הביט בבית הגדול."},
        {"unit_id": "unit-heading", "kind": "heading", "text": "פרק ראשון"},
    ]


def generated_chunk(edits=None):
    return {
        "schema_version": 1, "plan_id": "plan-1", "response_version": 1, "provider": "openai",
        "model": "gpt-6-luna", "prompt_version": "learning-generation@1", "input_hash": "x" * 64,
        "edits": edits if edits is not None else [
            {"unit_id": "unit-one", "start": 10, "end": 14, "original": "בבית",
             "replacement": "maison", "item_ids": ["fr-maison"], "grammar_ids": [], "gloss_he": "בית"},
        ],
        "warnings": [], "coverage_item_ids": ["fr-maison"], "content_hash": "y" * 64,
    }


class RenderChunkTests(unittest.TestCase):
    def test_yiddish_direction_and_combining_marks_preserved(self):
        chunk = generated_chunk()
        chunk['language'] = 'yi'
        chunk['edits'][0]['replacement'] = 'גוטן טאָג'
        html_out = render_chunk(source_units(), chunk, 'click')
        self.assertIn('lang="yi" dir="rtl"', html_out)
        self.assertIn('גוטן טאָג', html_out)

    def test_source_mismatch_refused_even_at_renderer_boundary(self):
        chunk = generated_chunk()
        chunk['edits'][0]['original'] = 'טקסט שונה'
        with self.assertRaises(LearningError):
            render_chunk(source_units(), chunk, 'inline')
    def test_renders_escaped_fragment_with_occurrence_id(self):
        html_out = render_chunk(source_units(), generated_chunk(), "inline")
        self.assertIn('dir="rtl"', html_out)
        self.assertIn('data-occurrence-id="unit-one-0"', html_out)
        self.assertIn('lang="und" dir="ltr"', html_out)
        self.assertIn("maison", html_out)
        self.assertIn("הילד הביט ", html_out)

    def test_source_text_outside_edit_rendered_verbatim(self):
        html_out = render_chunk(source_units(), generated_chunk(), "inline")
        self.assertIn("הגדול.", html_out)

    def test_no_edits_renders_plain_escaped_units(self):
        html_out = render_chunk(source_units(), generated_chunk(edits=[]), "inline")
        self.assertIn("הילד הביט בבית הגדול.", html_out)
        self.assertNotIn("data-occurrence-id", html_out)

    def test_heading_unit_rendered_as_heading_tag(self):
        html_out = render_chunk(source_units(), generated_chunk(edits=[]), "inline")
        self.assertIn("<h3", html_out)

    def test_escapes_html_special_characters_in_source(self):
        units = [{"unit_id": "unit-one", "kind": "paragraph", "text": "<script>alert(1)</script> טקסט"}]
        html_out = render_chunk(units, generated_chunk(edits=[]), "inline")
        self.assertNotIn("<script>", html_out)
        self.assertIn("&lt;script&gt;", html_out)

    def test_escapes_malicious_gloss_and_replacement(self):
        edits = [{"unit_id": "unit-one", "start": 0, "end": 4, "original": "הילד",
                  "replacement": '"><img src=x onerror=alert(1)>',
                  "item_ids": ["fr-maison"], "grammar_ids": [], "gloss_he": '"><script>bad()</script>'}]
        html_out = render_chunk(source_units(), generated_chunk(edits=edits), "inline")
        self.assertNotIn("<img", html_out)
        self.assertNotIn("<script>bad()", html_out)

    def test_click_support_mode_marks_class_and_no_inline_gloss_span(self):
        html_out = render_chunk(source_units(), generated_chunk(), "click")
        self.assertIn("learning-foreign-click", html_out)
        self.assertNotIn("learning-gloss-inline", html_out)

    def test_invalid_support_mode_rejected(self):
        with self.assertRaises(LearningError):
            render_chunk(source_units(), generated_chunk(), "mastery")

    def test_edit_referencing_unknown_unit_rejected(self):
        edits = [{"unit_id": "ghost-unit", "start": 0, "end": 1, "original": "x",
                  "replacement": "y", "item_ids": [], "grammar_ids": [], "gloss_he": ""}]
        with self.assertRaises(LearningError):
            render_chunk(source_units(), generated_chunk(edits=edits), "inline")


class RenderRecapTests(unittest.TestCase):
    def test_empty_recap_renders_plain_hebrew_note(self):
        html_out = render_recap({"schema_version": 1, "chapter_id": "chapter-one", "chunk_hashes": [],
                                  "vocabulary": [], "grammar": [], "warnings": []})
        self.assertIn("לא נוספו", html_out)

    def test_populated_recap_renders_items(self):
        recap = {"schema_version": 1, "chapter_id": "chapter-one", "chunk_hashes": [],
                  "vocabulary": [{"item_id": "fr-maison", "gloss_he": "בית"}],
                  "grammar": [{"item_id": "fr-le", "explanation_he": "תווית יידוע",
                               "examples": [{"chunk_id": "plan-1", "edit_index": 0}]}],
                  "warnings": []}
        html_out = render_recap(recap)
        self.assertIn("בית", html_out)
        self.assertIn("תווית יידוע", html_out)

    def test_escapes_malicious_recap_content(self):
        recap = {"schema_version": 1, "chapter_id": "chapter-one", "chunk_hashes": [],
                  "vocabulary": [{"item_id": "fr-maison", "gloss_he": "<script>bad()</script>"}],
                  "grammar": [], "warnings": []}
        html_out = render_recap(recap)
        self.assertNotIn("<script>bad()", html_out)


if __name__ == "__main__":
    unittest.main()
