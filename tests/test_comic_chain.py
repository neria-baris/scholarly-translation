"""COMIC integration: local detection feeds typesetting and rendering
(audit/contracts/comic_translation.md, conductor acceptance)."""
import unittest

from scholarly_translation import comic_detect, comic_records as cr, comic_typeset
from tests import comic_fixtures

HEBREW = {"speech": ["איפה היית אתמול בלילה?", "כבר אמרתי לך. בספרייה!"], "thought": ["שקרן..."],
          "narration": ["בינתיים, בצד השני של העיר..."], "sign": ["סגור"], "sfx": ["בום!"]}


def _typeset_page(scale):
    page = comic_fixtures.make_page(scale)
    width, height = page.image.size
    font = comic_typeset.font_for("he")
    texts = {kind: list(values) for kind, values in HEBREW.items()}
    pairs = []
    for number, candidate in enumerate(comic_detect.detect_candidates(page.image), 1):
        truth = max(page.truths, key=lambda t: comic_fixtures.box_iou(candidate["bbox"], t.text_bbox))
        region = cr.new_region(candidate, 1, number, kind=truth.kind, source_text=truth.text)
        text = texts[truth.kind].pop(0)
        region["translation"] = {"text": text, "status": "ok", "note": ""}
        region["layout"] = comic_typeset.fit(region, text, font, True, height, width)
        cr.validate_region(region, width=width, height=height)
        pairs.append((truth, region))
    return page, pairs


class ChainTests(unittest.TestCase):
    def test_detected_regions_take_the_translation_inside_the_balloon(self):
        for scale in (1.0, 1.4):
            page, pairs = _typeset_page(scale)
            self.assertEqual(sorted(t.kind for t, _ in pairs), sorted(t.kind for t in page.truths))
            for truth, region in pairs:
                layout = region["layout"]
                self.assertFalse(layout["overflow"], truth.text)
                self.assertEqual(layout["style"], {"sfx": "subtitle", "sign": "box"}.get(truth.kind, "bubble"))
                if layout["style"] != "bubble":
                    continue
                # every corner of every line lies inside the drawn balloon/caption shape
                for line in layout["lines"]:
                    for x in (line["x"], line["x"] + line["width"] - 1):
                        for y in (line["y"] + 2, line["y"] + layout["line_height"] - 2):
                            self.assertTrue(comic_fixtures.inside_container(truth, x, y), (scale, truth.text, line))
                # the translation is not set larger than the source lettering
                self.assertLessEqual(layout["line_height"], 1.05 * region["line_height"] + 1)

    def test_render_replaces_the_source_lettering(self):
        page, pairs = _typeset_page(1.0)
        before = page.image.tobytes()
        out = comic_typeset.render_page(page.image, [region for _, region in pairs])
        self.assertEqual(page.image.tobytes(), before)
        for truth, region in pairs:
            if region["layout"]["style"] != "bubble":
                continue
            drawn = region["layout"]["box"]
            x0, y0, x1, y1 = truth.text_bbox
            # source ink outside the new text block is gone
            for y in range(y0, y1, 2):
                for x in range(x0, x1, 2):
                    if drawn[0] - 2 <= x < drawn[2] + 2 and drawn[1] - 2 <= y < drawn[3] + 2:
                        continue
                    self.assertGreater(sum(out.getpixel((x, y))) / 3, 200, (truth.text, x, y))


if __name__ == "__main__":
    unittest.main()
