"""COMIC-B acceptance tests (audit/contracts/comic_translation.md), offline."""
import unittest
from unittest import mock

from PIL import Image, ImageChops

from scholarly_translation.comics import records as cr
from scholarly_translation.comics import typeset as ts
from tests.comic_fixtures import inside_ellipse, make_page

HEBREW = "איפה היית אתמול בלילה?"
STEP = 4


def _interior(truth, inset=6):
    """Interior rows from the fixture's balloon geometry (detection is another task)."""
    x0, y0, x1, y1 = truth.container_bbox
    rows = []
    for y in range(y0 + inset, y1 - inset, STEP):
        if truth.shape == "ellipse":
            rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
            k = max(0.0, 1 - ((y - y0 - ry) / ry) ** 2) ** 0.5
            a, b = int(x0 + rx - rx * k + inset), int(x0 + rx + rx * k - inset)
        else:
            a, b = x0 + inset, x1 - inset
        if b - a > 4:
            rows.append([y, a, b])
    return {"step": STEP, "rows": rows}


def _region(truth, number=1, interior=True, text=None):
    candidate = {"bbox": list(truth.text_bbox), "interior": _interior(truth) if interior and truth.container_bbox
                 else None, "background": list(truth.background), "plain_background": truth.plain_background,
                 "line_height": truth.line_height, "confidence": 0.9}
    region = cr.new_region(candidate, 1, number, kind=truth.kind, source_text=truth.text)
    return region


class TypesetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = make_page(1.0)
        cls.image = cls.page.image
        cls.w, cls.h = cls.image.size
        cls.latin = ts.font_for("en")
        cls.hebrew = ts.font_for("he")
        cls.balloon = cls.page.truths[0]

    def assert_in_spans(self, region, layout):
        area = ts._Area(region)
        for line in layout["lines"]:
            y0, y1 = line["y"], line["y"] + layout["line_height"]
            span = area.span(y0, y1)
            self.assertIsNotNone(span, line)
            self.assertGreaterEqual(line["x"], span[0])
            self.assertLessEqual(line["x"] + line["width"], span[1])

    def test_fonts_and_min_size(self):
        self.assertEqual(ts.font_for("he").name, "HadasimCLM-Bold.ttf")
        self.assertEqual(ts.font_for("en").name, "NotoSans-Regular.ttf")
        self.assertGreaterEqual(ts.min_font_px(300), 10)
        self.assertEqual(ts.min_font_px(1500), 16)

    def test_bubble_lines_inside_ellipse_and_spans(self):
        region = _region(self.balloon)
        layout = ts.fit(region, "Where were you last night, honestly?", self.latin, False, self.h)
        self.assertEqual(layout["style"], "bubble")
        self.assertFalse(layout["overflow"])
        self.assert_in_spans(region, layout)
        for line in layout["lines"]:
            for x in (line["x"], line["x"] + line["width"]):
                for y in (line["y"], line["y"] + layout["line_height"]):
                    self.assertTrue(inside_ellipse(self.balloon.container_bbox, x, y))

    def test_short_text_larger_than_long_and_size_cap(self):
        region = _region(self.balloon)
        short = ts.fit(region, "Hi!", self.latin, False, self.h)
        long = ts.fit(region, "Where were you last night? I waited for hours and hours, and nobody told me "
                      "anything at all, not even your sister, who always knows everything.", self.latin, False, self.h)
        self.assertFalse(long["overflow"])
        self.assertGreater(short["font_size"], long["font_size"])
        # the drawn line pitch never exceeds the source line pitch by more than ~5%
        cap = 1.05 * region["line_height"] + 1
        self.assertLessEqual(short["line_height"], cap)
        self.assertLessEqual(long["line_height"], cap)

    def test_overflow_reported_at_min_size(self):
        region = _region(self.balloon)
        layout = ts.fit(region, "blah " * 200, self.latin, False, self.h)
        self.assertTrue(layout["overflow"])
        self.assertEqual(layout["font_size"], ts.min_font_px(self.h))
        self.assertTrue(layout["lines"])
        cr.validate_region(dict(region, layout=layout))

    def test_long_word_is_split_only_when_needed(self):
        region = _region(self.balloon)
        word = "Supercalifragilisticexpialidocious" * 2
        layout = ts.fit(region, word, self.latin, False, self.h)
        self.assertGreater(len(layout["lines"]), 1)
        self.assertEqual("".join(l["text"] for l in layout["lines"]), word)
        normal = ts.fit(region, "Where were you", self.latin, False, self.h)
        self.assertEqual(" ".join(l["text"] for l in normal["lines"]), "Where were you")

    def test_hebrew_uses_visual_order(self):
        region = _region(self.balloon)
        with mock.patch.object(ts, "reorder_bidi_line", wraps=ts.reorder_bidi_line) as spy:
            layout = ts.fit(region, HEBREW, self.hebrew, True, self.h)
        self.assertTrue(spy.called)
        self.assertTrue(layout["rtl"])
        self.assert_in_spans(region, layout)
        self.assertEqual(" ".join(l["text"] for l in layout["lines"]), HEBREW)
        page = dict(region, layout=layout, translation={"text": HEBREW, "status": "ok", "note": ""})
        with mock.patch.object(ts, "reorder_bidi_line", wraps=ts.reorder_bidi_line) as spy:
            out = ts.render_page(self.image, [page])
        self.assertTrue(spy.called)
        # drawing the logical (unreordered) text instead gives a different picture
        with mock.patch.object(ts, "reorder_bidi_line", side_effect=lambda t, rtl_paragraph=False: t):
            plain = ts.render_page(self.image, [page])
        self.assertIsNotNone(ImageChops.difference(out, plain).getbbox())

    def test_render_erases_source_and_keeps_outside(self):
        region = _region(self.balloon)
        text = "Where were you last night?"
        layout = ts.fit(region, text, self.latin, False, self.h)
        item = dict(region, layout=layout, translation={"text": text, "status": "ok", "note": ""})
        before = self.image.tobytes()
        out = ts.render_page(self.image, [item])
        self.assertEqual(self.image.tobytes(), before)
        self.assertIsNot(out, self.image)
        # outside of the dilated bbox and the text lines nothing changes
        allowed = Image.new("L", out.size, 0)
        from PIL import ImageDraw
        draw = ImageDraw.Draw(allowed)
        x0, y0, x1, y1 = region["bbox"]
        draw.rectangle([x0 - 4, y0 - 4, x1 + 4, y1 + 4], fill=255)
        for line in layout["lines"]:
            draw.rectangle([line["x"] - 2, line["y"] - 2, line["x"] + line["width"] + 2,
                            line["y"] + layout["line_height"] + 2], fill=255)
        diff = ImageChops.difference(out, self.image).convert("L").point(lambda v: 255 if v else 0)
        outside = ImageChops.multiply(diff, ImageChops.invert(allowed))
        self.assertIsNone(outside.getbbox())
        # the source glyphs are gone: render a blank-text version and compare the bbox area
        blank = dict(item, layout=dict(layout, lines=[]))
        erased = ts.render_page(self.image, [blank]).crop(tuple(region["bbox"]))
        self.assertEqual(erased.convert("L").getextrema()[0], 255)

    def test_balloon_outline_untouched(self):
        region = _region(self.balloon)
        layout = ts.fit(region, "Hello", self.latin, False, self.h)
        item = dict(region, layout=layout, translation={"text": "Hello", "status": "ok", "note": ""})
        out = ts.render_page(self.image, [item])
        x0, y0, x1, y1 = self.balloon.container_bbox
        mid = (y0 + y1) // 2
        for x in (x0 + 1, x0 + 2, x1 - 3, x1 - 2):
            self.assertEqual(out.getpixel((x, mid)), self.image.getpixel((x, mid)))

    def test_skipped_and_missing_untouched(self):
        region = _region(self.balloon)
        layout = ts.fit(region, "Hi", self.latin, False, self.h)
        skipped = dict(region, layout=layout, translation={"text": "Hi", "status": "skipped", "note": ""})
        nolayout = dict(region, layout=None, translation={"text": "Hi", "status": "ok", "note": ""})
        out = ts.render_page(self.image, [skipped, nolayout])
        self.assertEqual(out.tobytes(), self.image.tobytes())

    def test_box_style_on_art(self):
        sign = self.page.truth("sign")[0]
        region = _region(sign)
        layout = ts.fit(region, "Closed for today", self.latin, False, self.h, self.w)
        self.assertEqual(layout["style"], "box")
        bx0, by0, bx1, by1 = layout["box"]
        self.assertTrue(0 <= bx0 and by0 >= 0 and bx1 <= self.w and by1 <= self.h)
        sx0, sy0, sx1, sy1 = region["bbox"]
        self.assertTrue(bx0 <= sx0 and by0 <= sy0 and bx1 >= sx1 and by1 >= sy1)
        for line in layout["lines"]:
            self.assertTrue(bx0 <= line["x"] and line["x"] + line["width"] <= bx1)
            self.assertTrue(by0 <= line["y"] and line["y"] + layout["line_height"] <= by1)
        item = dict(region, layout=layout, translation={"text": "x", "status": "ok", "note": ""})
        out = ts.render_page(self.image, [item])
        self.assertEqual(out.getpixel((bx0 + 1, by0 + layout["line_height"] // 2)), tuple(region["background"]))
        cr.validate_region(item, width=self.w, height=self.h)

    def test_subtitle_keeps_art(self):
        sfx = self.page.truth("sfx")[0]
        region = _region(sfx)
        layout = ts.fit(region, "BOOM", self.latin, False, self.h, self.w)
        self.assertEqual(layout["style"], "subtitle")
        x0, y0, x1, y1 = layout["box"]
        self.assertTrue(0 <= x0 and 0 <= y0 and x1 <= self.w and y1 <= self.h)
        self.assertGreaterEqual(layout["lines"][0]["y"], region["bbox"][3])
        item = dict(region, layout=layout, translation={"text": "BOOM", "status": "ok", "note": ""})
        out = ts.render_page(self.image, [item])
        sx0, sy0, sx1, sy1 = region["bbox"]
        self.assertEqual(out.crop((sx0, sy0, sx1, sy1)).tobytes(), self.image.crop((sx0, sy0, sx1, sy1)).tobytes())
        self.assertIsNotNone(ImageChops.difference(out, self.image).getbbox())

    def test_caption_without_interior(self):
        cap = self.page.truth("narration")[0]
        region = _region(cap, interior=False)
        layout = ts.fit(region, "Meanwhile, elsewhere", self.latin, False, self.h)
        self.assertEqual(layout["style"], "bubble")
        self.assert_in_spans(region, layout)

    def test_capacity_grows_with_balloon(self):
        small = _region(self.page.truths[2])  # "Liar..." balloon
        big = _region(self.page.truths[1])
        self.assertGreater(ts.capacity(big, self.latin, False, self.h), ts.capacity(small, self.latin, False, self.h))
        self.assertGreater(ts.capacity(small, self.hebrew, True, self.h), 0)

    def test_deterministic_and_valid(self):
        items = []
        for number, truth in enumerate(self.page.truths, 1):
            region = _region(truth, number)
            layout = ts.fit(region, HEBREW, self.hebrew, True, self.h, self.w)
            item = dict(region, layout=layout, translation={"text": HEBREW, "status": "ok", "note": ""})
            cr.validate_region(item, width=self.w, height=self.h)
            items.append(item)
        a, b = ts.render_page(self.image, items), ts.render_page(self.image, items)
        self.assertEqual(a.tobytes(), b.tobytes())
        self.assertEqual(ts.fit(items[0], HEBREW, self.hebrew, True, self.h), items[0]["layout"])


if __name__ == "__main__":
    unittest.main()
