import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scholarly_translation.__main__ import cmd_demo
from scholarly_translation.records import Document, RecordValidationError
from scholarly_translation.store import load_document, save_document


class DataSpineTests(unittest.TestCase):
    def test_producer_consumer_source_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.assertEqual(cmd_demo(tmp), 0)
            doc = load_document(folder / "document.json")
            source = (folder / "source.txt").read_text(encoding="utf-8")
            self.assertEqual(doc.input_hash, hashlib.sha256((folder / "source.txt").read_bytes()).hexdigest())
            for page in doc.pages:
                for seg in page.segments:
                    self.assertEqual(source[seg.source_char_start:seg.source_char_end], seg.text)
                    self.assertTrue(seg.region_id)
            save_document(doc, folder / "roundtrip.json")
            self.assertEqual(load_document(folder / "roundtrip.json").to_dict(), doc.to_dict())
            self.assertEqual(doc.status, "synthetic")

    def test_legacy_reading_never_invents_input_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            cmd_demo(tmp)
            data = json.loads((Path(tmp) / "document.json").read_text(encoding="utf-8"))
            data["schema_version"] = 1
            for field in ("stage_id", "stage_version", "input_hash", "status", "warnings"):
                data.pop(field)
            old_id = data["document_id"]
            doc = Document.from_dict(data)
            self.assertEqual(doc.document_id, old_id)
            self.assertEqual(doc.input_hash, "unknown")
            self.assertIn("legacy_input_hash_unavailable", doc.warnings)
            current = copy.deepcopy(data)
            current["schema_version"] = 2
            with self.assertRaises(RecordValidationError):
                Document.from_dict(current)

    def test_cli_errors_do_not_echo_provider_or_model_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for field in ("provider", "model"):
                config = folder / "config.json"
                config.write_text(json.dumps({field: "PRIVATE_SENTINEL_VALUE"}), encoding="utf-8")
                result = subprocess.run(
                    [sys.executable, "-B", "-m", "scholarly_translation", "demo",
                     "--output", str(folder / "out"), "--config", str(config)],
                    capture_output=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(b"PRIVATE_SENTINEL_VALUE", result.stdout + result.stderr)
                self.assertFalse((folder / "out").exists())
