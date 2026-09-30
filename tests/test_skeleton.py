import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from scholarly_translation.__main__ import cmd_demo, cmd_inspect, _build_document
from scholarly_translation.provider import (
    ConfigValidationError,
    MockTranslationAdapter,
    ProviderConfig,
    TranslationAdapter,
    UnsupportedProviderError,
    build_adapter,
)
from scholarly_translation.records import (
    Document,
    Page,
    RecordValidationError,
    Segment,
)
from scholarly_translation.store import (
    deterministic_id,
    load_document,
    save_document,
)


class RecordValidationTests(unittest.TestCase):
    def test_segment_rejects_empty_id(self):
        with self.assertRaises(RecordValidationError):
            Segment(
                segment_id="",
                page_id="p1",
                order=1,
                text="x",
                source_char_start=0,
                source_char_end=1,
            )

    def test_segment_rejects_negative_span(self):
        with self.assertRaises(RecordValidationError):
            Segment(
                segment_id="s1",
                page_id="p1",
                order=1,
                text="x",
                source_char_start=5,
                source_char_end=2,
            )

    def test_page_rejects_mismatched_parent(self):
        segment = Segment(
            segment_id="s1",
            page_id="other-page",
            order=1,
            text="x",
            source_char_start=0,
            source_char_end=1,
        )
        with self.assertRaises(RecordValidationError):
            Page(page_id="p1", document_id="d1", page_number=1, segments=[segment])

    def test_document_rejects_nonpositive_version(self):
        with self.assertRaises(RecordValidationError):
            Document(
                schema_version=1,
                document_id="d1",
                document_version=0,
                language="he",
                source_kind="synthetic",
                source_uri="x",
                pages=[],
            )

    def test_document_rejects_unsupported_schema_version(self):
        with self.assertRaises(RecordValidationError):
            Document(
                schema_version=99,
                document_id="d1",
                document_version=1,
                language="he",
                source_kind="synthetic",
                source_uri="x",
                pages=[],
            )

    def test_document_rejects_bool_schema_version(self):
        with self.assertRaises(RecordValidationError):
            Document.from_dict(
                {
                    "schema_version": True,
                    "document_id": "d1",
                    "document_version": 1,
                    "language": "he",
                    "source_kind": "synthetic",
                    "source_uri": "x",
                    "pages": [],
                }
            )

    def test_segment_rejects_span_length_mismatch(self):
        with self.assertRaises(RecordValidationError):
            Segment(
                segment_id="s1",
                page_id="p1",
                order=1,
                text="hello",
                source_char_start=0,
                source_char_end=999999,
            )

    def test_document_from_dict_rejects_none_page(self):
        with self.assertRaises(RecordValidationError):
            Document.from_dict(
                {
                    "schema_version": 1,
                    "document_id": "d1",
                    "document_version": 1,
                    "language": "he",
                    "source_kind": "synthetic",
                    "source_uri": "x",
                    "pages": [None],
                }
            )

    def test_page_rejects_duplicate_segment_ids(self):
        segment_a = Segment(
            segment_id="s1", page_id="p1", order=1, text="a",
            source_char_start=0, source_char_end=1,
        )
        segment_b = Segment(
            segment_id="s1", page_id="p1", order=2, text="b",
            source_char_start=1, source_char_end=2,
        )
        with self.assertRaises(RecordValidationError):
            Page(page_id="p1", document_id="d1", page_number=1, segments=[segment_a, segment_b])

    def test_document_rejects_duplicate_page_numbers(self):
        page_a = Page(page_id="p1", document_id="d1", page_number=1, segments=[])
        page_b = Page(page_id="p2", document_id="d1", page_number=1, segments=[])
        with self.assertRaises(RecordValidationError):
            Document(
                schema_version=1,
                document_id="d1",
                document_version=1,
                language="he",
                source_kind="synthetic",
                source_uri="x",
                pages=[page_a, page_b],
            )


class DeterministicIdTests(unittest.TestCase):
    def test_same_inputs_same_id(self):
        self.assertEqual(deterministic_id("a", "1", "2"), deterministic_id("a", "1", "2"))

    def test_different_inputs_different_id(self):
        self.assertNotEqual(deterministic_id("a", "1"), deterministic_id("a", "2"))

    def test_no_boundary_ambiguity_across_parts(self):
        self.assertNotEqual(
            deterministic_id("a|b", "c"), deterministic_id("a", "b|c")
        )


class ProviderTests(unittest.TestCase):
    def test_default_config_is_mock_targeting_he(self):
        config = ProviderConfig()
        self.assertEqual(config.provider, "mock")
        self.assertEqual(config.target_language, "he")

    def test_unknown_provider_rejected(self):
        with self.assertRaises(UnsupportedProviderError):
            ProviderConfig(provider="paid-provider-x")

    def test_build_adapter_returns_mock_for_mock_config(self):
        adapter = build_adapter(ProviderConfig())
        self.assertIsInstance(adapter, MockTranslationAdapter)

    def test_mock_output_is_marked_placeholder(self):
        adapter = MockTranslationAdapter()
        result = adapter.translate("hello", "he")
        self.assertIn("MOCK-PLACEHOLDER", result)

    def test_unknown_model_rejected(self):
        with self.assertRaises(UnsupportedProviderError):
            ProviderConfig(model="paid-real-model")

    def test_alternate_adapter_stub_satisfies_interface(self):
        class StubAdapter(TranslationAdapter):
            def translate(self, text: str, target_language: str) -> str:
                return f"[STUB:{target_language}] {text}"

        adapter = StubAdapter()
        self.assertIsInstance(adapter, TranslationAdapter)
        self.assertEqual(adapter.translate("hi", "he"), "[STUB:he] hi")

    def test_config_from_dict_rejects_non_object(self):
        with self.assertRaises(ConfigValidationError):
            ProviderConfig.from_dict(["not", "an", "object"])

    def test_config_from_dict_rejects_unknown_field_without_leaking_value(self):
        with self.assertRaisesRegex(ConfigValidationError, "unknown config fields"):
            ProviderConfig.from_dict({"api_key": "super-secret-value"})

    def test_config_from_dict_rejects_unsupported_provider(self):
        with self.assertRaises(UnsupportedProviderError):
            ProviderConfig.from_dict({"provider": "paid-provider-x"})

    def test_config_from_dict_rejects_unsupported_model(self):
        with self.assertRaises(UnsupportedProviderError):
            ProviderConfig.from_dict({"model": "paid-real-model"})

    def test_config_from_dict_rejects_bad_field_type(self):
        with self.assertRaises(ConfigValidationError):
            ProviderConfig.from_dict({"target_language": 5})

    def test_config_from_dict_valid_config_affects_target_language(self):
        config = ProviderConfig.from_dict({"target_language": "fr"})
        self.assertEqual(config.target_language, "fr")
        self.assertEqual(config.provider, "mock")


class StoreRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def test_save_and_load_preserves_unicode_text(self):
        text = "これは日本語のテストです。"
        segment = Segment(
            segment_id="s1",
            page_id="p1",
            order=1,
            text=text,
            source_char_start=0,
            source_char_end=len(text),
        )
        page = Page(page_id="p1", document_id="d1", page_number=1, segments=[segment])
        document = Document(
            schema_version=1,
            document_id="d1",
            document_version=1,
            language="mixed",
            source_kind="synthetic",
            source_uri="file:///x",
            pages=[page],
        )
        path = self.tmpdir / "doc.json"
        save_document(document, path)
        loaded = load_document(path)
        self.assertEqual(loaded.pages[0].segments[0].text, segment.text)
        self.assertEqual(loaded.document_id, "d1")

    def test_load_invalid_json_fails_clearly(self):
        path = self.tmpdir / "bad.json"
        path.write_text("not json", encoding="utf-8")
        with self.assertRaises(RecordValidationError):
            load_document(path)

    def test_load_rejects_unsupported_schema_version(self):
        path = self.tmpdir / "bad_schema.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 99,
                    "document_id": "d1",
                    "document_version": 1,
                    "language": "he",
                    "source_kind": "synthetic",
                    "source_uri": "x",
                    "pages": [],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(RecordValidationError):
            load_document(path)


class CliDemoInspectTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def test_demo_persists_source_and_document(self):
        output_dir = self.tmpdir / "outputs" / "gate1"
        result = cmd_demo(str(output_dir))
        self.assertEqual(result, 0)
        self.assertTrue((output_dir / "document.json").exists())
        self.assertTrue((output_dir / "source.txt").exists())
        self.assertTrue((output_dir / "usage.jsonl").exists())

    def test_rerunning_demo_preserves_ids_and_appends_usage(self):
        output_dir = self.tmpdir / "outputs" / "gate1"
        cmd_demo(str(output_dir))
        doc1 = load_document(output_dir / "document.json")
        cmd_demo(str(output_dir))
        doc2 = load_document(output_dir / "document.json")
        self.assertEqual(doc1.document_id, doc2.document_id)
        self.assertEqual(
            doc1.pages[0].segments[0].segment_id,
            doc2.pages[0].segments[0].segment_id,
        )
        usage_lines = (output_dir / "usage.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(usage_lines), 2)

    def test_inspect_round_trips_exact_text(self):
        output_dir = self.tmpdir / "outputs" / "gate1"
        cmd_demo(str(output_dir))
        document = _build_document(source_uri=str(output_dir / "source.txt"))
        loaded = load_document(output_dir / "document.json")
        self.assertEqual(loaded.document_id, document.document_id)
        for page_a, page_b in zip(document.pages, loaded.pages):
            for seg_a, seg_b in zip(page_a.segments, page_b.segments):
                self.assertEqual(seg_a.text, seg_b.text)

    def test_inspect_cli_returns_nonzero_on_missing_file(self):
        result = cmd_inspect(str(self.tmpdir / "does_not_exist.json"))
        self.assertEqual(result, 1)

    def test_demo_source_uri_is_absolute_file_uri(self):
        output_dir = self.tmpdir / "outputs" / "gate1"
        cmd_demo(str(output_dir))
        document = load_document(output_dir / "document.json")
        self.assertTrue(document.source_uri.startswith("file:///"))

    def test_demo_with_valid_config_affects_target_language(self):
        output_dir = self.tmpdir / "outputs" / "gate1"
        config_path = self.tmpdir / "config.json"
        config_path.write_text(json.dumps({"target_language": "fr"}), encoding="utf-8")
        result = cmd_demo(str(output_dir), str(config_path))
        self.assertEqual(result, 0)
        usage_lines = (output_dir / "usage.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(usage_lines[-1])["provider"], "mock")

    def test_demo_with_invalid_config_rejects_and_writes_nothing(self):
        output_dir = self.tmpdir / "outputs" / "gate1"
        config_path = self.tmpdir / "config.json"
        config_path.write_text(
            json.dumps({"provider": "paid-provider-x"}), encoding="utf-8"
        )
        result = cmd_demo(str(output_dir), str(config_path))
        self.assertEqual(result, 1)
        self.assertFalse(output_dir.exists())

    def test_demo_with_invalid_model_config_rejects_and_writes_nothing(self):
        output_dir = self.tmpdir / "outputs" / "gate1"
        config_path = self.tmpdir / "config.json"
        config_path.write_text(json.dumps({"model": "paid-real-model"}), encoding="utf-8")
        result = cmd_demo(str(output_dir), str(config_path))
        self.assertEqual(result, 1)
        self.assertFalse(output_dir.exists())

    def test_usage_log_has_explicit_cost_fields_and_no_source_text(self):
        output_dir = self.tmpdir / "outputs" / "gate1"
        cmd_demo(str(output_dir))
        usage_line = (output_dir / "usage.jsonl").read_text(encoding="utf-8").splitlines()[0]
        record = json.loads(usage_line)
        self.assertIn("token_usage", record)
        self.assertIn("actual_charge", record)
        self.assertIn("estimated_cost_usd", record)
        self.assertNotEqual(record["actual_charge"], "0")
        for japanese_fragment in ("これは", "合成"):
            self.assertNotIn(japanese_fragment, usage_line)


class CliUtf8OutputTests(unittest.TestCase):
    def test_inspect_output_is_utf8_regardless_of_console_encoding(self):
        tmpdir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        output_dir = tmpdir / "outputs" / "gate1"
        cmd_demo(str(output_dir))

        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "cp1252"
        result = subprocess.run(
            [sys.executable, "-B", "-m", "scholarly_translation", "inspect",
             str(output_dir / "document.json")],
            capture_output=True,
            env=env,
            cwd=str(PROJECT_ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        decoded = result.stdout.decode("utf-8")
        self.assertIn("これは合成のオフラインテスト文です。", decoded)


if __name__ == "__main__":
    unittest.main()
