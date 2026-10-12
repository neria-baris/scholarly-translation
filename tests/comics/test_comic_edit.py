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
    """``redraw_scene``: the re-lettering request ignores the mask and repaints everything; the
    cleaning request always respects it (paints the hole white)."""

    def __init__(self, fail=False, redraw_scene=False):
        self.calls, self.fail, self.redraw_scene = [], fail, redraw_scene

    def edit(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("provider down")
        width, height = (int(v) for v in kwargs["size"].split("x"))
        cleaning = "Remove the lettering" in kwargs["prompt"]
        if self.redraw_scene and not cleaning:
            result = Image.new("RGB", (width, height), (255, 0, 0))
        elif "mask" not in kwargs:                  # local regeneration: edges kept, the middle re-lettered
            result = Image.open(io.BytesIO(kwargs["image"][1])).convert("RGB")
            result.paste((255, 0, 0), (width // 4, height // 4, 3 * width // 4, 3 * height // 4))
        else:
            result = Image.open(io.BytesIO(kwargs["image"][1])).convert("RGB")
            hole = Image.open(io.BytesIO(kwargs["mask"][1])).split()[3].point(lambda v: 255 if v == 0 else 0)
            result.paste((255, 255, 255) if cleaning else (255, 0, 0), (0, 0), hole)
        buffer = io.BytesIO()
        result.save(buffer, format="PNG")
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
        self.assertEqual(editor.edit(image, self.region, "בר דנוור"), "local")
        self.assertNotIn("mask", client.images.calls[0])                   # no mask: a tight crop only
        self.assertEqual(image.getpixel((360, 220))[0], 255)                 # inside the sign: edited
        self.assertEqual(image.getpixel((100, 100)), (240, 240, 240))       # elsewhere untouched
        again = self.page()
        editor.edit(again, self.region, "בר דנוור")
        self.assertEqual(len(client.images.calls), 1)                       # cached
        ledger = [json.loads(l) for l in (Path(self.tmp.name) / "edits" / "edits.jsonl").read_text().splitlines()]
        self.assertAlmostEqual(ledger[0]["estimated_cost_usd"], (200 * 5 + 1000 * 8 + 3000 * 30) / 1e6)

    def test_scene_redraw_is_rejected_then_cleaned_and_lettered_locally(self):
        client = SimpleNamespace(images=FakeImages(redraw_scene=True))
        editor = edit.SignEditor(Path(self.tmp.name), client)
        image = self.page()
        from PIL import ImageDraw
        draw = ImageDraw.Draw(image)
        for i in range(6):                          # slanted "lettering": six blocks rising to the right
            x, y = 305 + i * 18, 228 - i * 4
            draw.rectangle([x, y, x + 10, y + 8], fill=(20, 20, 20))
        geometry = edit.lettering_geometry(image, self.region)
        self.assertLess(geometry["angle"], -5)       # rising to the right in image coordinates
        method = editor.edit(image, self.region, "בר דנוור")
        self.assertEqual(method, "local-clean+letter")                     # plain surface: cleaned locally
        self.assertEqual(len(client.images.calls), 2)                       # local and redraw rejected
        self.assertNotEqual(image.getpixel((100, 100))[0], 255)            # the red redraw never pasted
        dark = sum(1 for x in range(300, 420) for y in range(200, 240) if image.getpixel((x, y))[0] < 100)
        self.assertGreater(dark, 30)                                        # new lettering drawn locally

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


class LocatedSignTests(unittest.TestCase):
    def test_parse_quad(self):
        quad = edit.parse_quad('```json\n{"quad": [[100, 300], [900, 200], [900, 400], [100, 500]]}\n```')
        self.assertEqual(quad[1], [900.0, 200.0])
        for bad in ('{"quad": [[0, 0], [1, 1]]}', '{"quad": [[0, 0], [2000, 0], [0, 5], [5, 5]]}',
                    '{"quad": [[0, 0], [0, 0], [0, 0], [0, 0]]}', "no json"):
            with self.assertRaises(edit.SignEditError):
                edit.parse_quad(bad)

    def test_geometry_from_quad_angle_and_upright(self):
        g = edit.geometry_from_quad([[0, 100], [1000, 0], [1000, 200], [0, 300]], (0, 0, 1000, 1000))
        self.assertAlmostEqual(g["angle"], -5.71, places=1)                # rising to the right
        flipped = edit.geometry_from_quad([[1000, 0], [0, 100], [0, 300], [1000, 200]], (0, 0, 1000, 1000))
        self.assertAlmostEqual(flipped["angle"], g["angle"], places=1)     # corners end-first: still upright

    def test_located_sign_is_cleaned_locally_and_lettered(self):
        from PIL import ImageDraw
        image = Image.new("RGB", (800, 600), (245, 245, 245))
        draw = ImageDraw.Draw(image)
        for i in range(6):
            draw.rectangle([305 + i * 18, 214, 315 + i * 18, 226], fill=(20, 20, 20))
        client = SimpleNamespace(images=FakeImages(redraw_scene=True))
        with tempfile.TemporaryDirectory() as tmp:
            editor = edit.SignEditor(Path(tmp), client)
            region = {"region_id": "p001-r01", "bbox": [300, 200, 420, 240]}
            box = edit.edit_request(image, region, "x")[0]
            to_grid = lambda x, y: [(x - box[0]) * 1000 / (box[2] - box[0]), (y - box[1]) * 1000 / (box[3] - box[1])]
            quad = [to_grid(300, 210), to_grid(420, 210), to_grid(420, 230), to_grid(300, 230)]
            method = editor.edit(image, region, "בר דנוור", locate=lambda img, reg: quad)
        self.assertEqual(method, "local-clean+letter")
        self.assertEqual(len(client.images.calls), 2)                      # local and redraw rejected
        self.assertEqual(image.getpixel((100, 100)), (245, 245, 245))      # the picture elsewhere untouched


class ArtTextSelectionTests(unittest.TestCase):
    def test_everything_lettered_in_the_art_goes_to_the_editor(self):
        from scholarly_translation.comics import pipeline as cp
        edited = []

        class Editor:
            def edit(self, image, region, text, language_name, rtl, locate=None):
                edited.append(region["region_id"])
                return "local"

        def region(rid, kind, style, plain=True):
            return {"region_id": rid, "kind": kind, "bbox": [10, 10, 50, 30], "interior": None, "balloon": None,
                    "plain_background": plain, "background": [255, 255, 255], "warnings": [],
                    "translation": {"text": "טקסט", "status": "ok", "note": ""},
                    "layout": {"style": style, "lines": [], "overflow": False}}
        regions = [region("a", "speech", "bubble"), region("b", "sfx", "subtitle", False),
                   region("c", "speech", "box", False), region("d", "sign", "box", False)]
        stages = SimpleNamespace(render_page=lambda img, regs: img)
        cp._render(stages, Image.new("RGB", (100, 60), "white"), regions, False, Editor())
        self.assertEqual(edited, ["b", "c", "d"])
        self.assertTrue(all(r.get("edited") for r in regions[1:]))
        self.assertFalse(regions[0].get("edited"))
