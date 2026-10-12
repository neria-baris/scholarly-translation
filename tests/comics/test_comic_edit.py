"""COMIC sign editing (audit/contracts/comic_sign_edit.md): offline, fake image client."""
import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from scholarly_translation.comics import edit


class FakeImages:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def edit(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("provider down")
        width, height = (int(v) for v in kwargs["size"].split("x"))
        buffer = io.BytesIO()
        Image.new("RGB", (width, height), (255, 0, 0)).save(buffer, format="PNG")   # everything red
        usage = SimpleNamespace(input_tokens=1200, output_tokens=3000,
                                input_tokens_details=SimpleNamespace(text_tokens=200, image_tokens=1000))
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(buffer.getvalue()).decode())],
                               usage=usage)


class SignEditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.region = {"region_id": "p001-r01", "bbox": [300, 200, 420, 240]}

    def page(self):
        return Image.new("RGB", (800, 600), (240, 240, 240))

    def test_request_mask_and_prompt(self):
        box, crop, mask, prompt, size = edit.edit_request(self.page(), self.region, "בר דנוור")
        self.assertEqual(size, "1536x1024")
        self.assertIn("«בר דנוור»", prompt)
        self.assertIn("right-to-left", prompt)
        alpha = Image.open(io.BytesIO(mask)).split()[3]
        self.assertEqual(alpha.getpixel((5, 5)), 255)                       # outside: keep
        self.assertEqual(alpha.getpixel((alpha.width // 2, alpha.height // 2)), 0)   # the lettering: edit

    def test_only_the_sign_changes_and_cache_prevents_a_second_call(self):
        client = SimpleNamespace(images=FakeImages())
        editor = edit.SignEditor(Path(self.tmp.name), client)
        image = self.page()
        self.assertTrue(editor.edit(image, self.region, "בר דנוור"))
        self.assertEqual(image.getpixel((360, 220))[0], 255)                 # inside the sign: edited
        self.assertEqual(image.getpixel((100, 100)), (240, 240, 240))       # elsewhere untouched
        again = self.page()
        editor.edit(again, self.region, "בר דנוור")
        self.assertEqual(len(client.images.calls), 1)                       # cached
        ledger = [json.loads(l) for l in (Path(self.tmp.name) / "edits" / "edits.jsonl").read_text().splitlines()]
        self.assertAlmostEqual(ledger[0]["estimated_cost_usd"], (200 * 5 + 1000 * 8 + 3000 * 30) / 1e6)

    def test_budget_and_failure(self):
        editor = edit.SignEditor(Path(self.tmp.name), SimpleNamespace(images=FakeImages()), budget_usd=0.0)
        with self.assertRaises(edit.SignEditError):
            editor.edit(self.page(), self.region, "x")
        failing = edit.SignEditor(Path(self.tmp.name) / "b", SimpleNamespace(images=FakeImages(fail=True)))
        image = self.page()
        with self.assertRaises(edit.SignEditError):
            failing.edit(image, self.region, "x")
        self.assertEqual(image.getpixel((360, 220)), (240, 240, 240))


if __name__ == "__main__":
    unittest.main()
