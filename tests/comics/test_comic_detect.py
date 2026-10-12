"""COMIC-A (audit/contracts/comic_translation.md): local text/balloon detection on synthetic
pages from ``comic_fixtures``. Offline, no model calls."""
import time
import unittest

from scholarly_translation.comics import detect as comic_detect
from scholarly_translation.comics import records as comic_records
from tests import comic_fixtures as fx

TOLERANCE = 2


def _scaled(box, scale):
    return [v * scale for v in box]


class ComicDetectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = fx.make_page(1.0)
        cls.found = comic_detect.detect_candidates(cls.page.image)
        cls.page2 = fx.make_page(2.0)
        started = time.time()
        cls.found2 = comic_detect.detect_candidates(cls.page2.image)
        cls.elapsed2 = time.time() - started

    def match(self, page, found, truth):
        hits = [c for c in found if fx.box_iou(c["bbox"], truth.text_bbox) >= 0.5]
        self.assertEqual(len(hits), 1, "%s: %d matches" % (truth.kind, len(hits)))
        return hits[0]

    def check_page(self, page, found):
        width, height = page.image.size
        self.assertEqual(len(found), len(page.truths), [c["bbox"] for c in found])
        for c in found:
            comic_records.validate_candidate(c, width=width, height=height)
        order = [(c["bbox"][1], c["bbox"][0]) for c in found]
        self.assertEqual(order, sorted(order))
        for c in found:
            for panel_art in [page.empty_art]:
                self.assertEqual(fx.box_iou(c["bbox"], panel_art), 0.0)
        for truth in page.truths:
            c = self.match(page, found, truth)
            if truth.container_bbox is None:
                self.assertFalse(c["plain_background"], truth.kind)
                self.assertIsNone(c["interior"], truth.kind)
                continue
            self.assertTrue(c["plain_background"], truth.kind)
            self.assertIsNotNone(c["interior"], truth.kind)
            self.assertTrue(all(abs(a - b) <= 12 for a, b in zip(c["background"], truth.background)),
                            (truth.kind, c["background"]))
            self.assertLess(abs(c["line_height"] - truth.line_height) / truth.line_height, 0.35,
                            (truth.kind, c["line_height"]))
            tx0, ty0, tx1, ty1 = truth.text_bbox
            rows = c["interior"]["rows"]
            step = c["interior"]["step"]
            for y, x0, x1 in rows:
                self.assertTrue(fx.inside_container(truth, x0 + TOLERANCE, y), (truth.kind, y, x0))
                self.assertTrue(fx.inside_container(truth, x1 - 1 - TOLERANCE, y), (truth.kind, y, x1))
                if ty0 <= y < ty1:
                    self.assertLessEqual(x0, tx0, (truth.kind, y))
                    self.assertGreaterEqual(x1, tx1, (truth.kind, y))
            inside = [y for y, _, _ in rows if ty0 <= y < ty1]
            self.assertTrue(inside)
            self.assertLessEqual(min(y for y, _, _ in rows), ty0 + step)
            self.assertGreaterEqual(max(y for y, _, _ in rows), ty1 - 1 - step)

    def test_page_candidates(self):
        self.check_page(self.page, self.found)

    def test_double_scale_page(self):
        self.check_page(self.page2, self.found2)
        self.assertLess(self.elapsed2, 5.0)

    def test_deterministic_and_input_untouched(self):
        before = self.page.image.tobytes()
        again = comic_detect.detect_candidates(self.page.image)
        self.assertEqual(again, self.found)
        self.assertEqual(self.page.image.tobytes(), before)
        self.assertEqual(comic_detect.DETECT_VERSION, "comic-detect@3")

    def test_blank_page_has_no_candidates(self):
        from PIL import Image
        self.assertEqual(comic_detect.detect_candidates(Image.new("RGB", (400, 600), (255, 255, 255))), [])


class SnapRegionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = fx.make_page(1.0)

    def test_loose_boxes_are_tightened(self):
        width, height = self.page.image.size
        for truth in self.page.truths:
            if truth.container_bbox is None:
                continue
            x0, y0, x1, y1 = truth.text_bbox
            dx, dy = (x1 - x0) * 0.075, (y1 - y0) * 0.075
            loose = [int(x0 - dx), int(y0 - dy), int(x1 + dx), int(y1 + dy)]
            c = comic_detect.snap_region(self.page.image, loose)
            comic_records.validate_candidate(c, width=width, height=height)
            self.assertGreaterEqual(fx.box_iou(c["bbox"], truth.text_bbox), 0.6, truth.kind)
            self.assertIsNotNone(c["interior"], truth.kind)
            self.assertTrue(c["plain_background"], truth.kind)
            for y, a, b in c["interior"]["rows"]:
                self.assertTrue(fx.inside_container(truth, a + TOLERANCE, y), truth.kind)
                self.assertTrue(fx.inside_container(truth, b - 1 - TOLERANCE, y), truth.kind)

    def test_art_text_has_no_interior(self):
        truth = self.page.truth("sign")[0]
        x0, y0, x1, y1 = truth.text_bbox
        c = comic_detect.snap_region(self.page.image, [x0 - 8, y0 - 8, x1 + 8, y1 + 8])
        comic_records.validate_candidate(c, width=self.page.image.width, height=self.page.image.height)
        self.assertIsNone(c["interior"])
        self.assertFalse(c["plain_background"])
        # lettering fused with hatching cannot be tightened: the given box is kept, never grown
        given = [x0 - 8, y0 - 8, x1 + 8, y1 + 8]
        self.assertTrue(given[0] <= c["bbox"][0] <= x0 and given[1] <= c["bbox"][1] <= y0)
        self.assertTrue(x1 <= c["bbox"][2] <= given[2] and y1 <= c["bbox"][3] <= given[3])

    def test_empty_art_and_clipping(self):
        width, height = self.page.image.size
        art = comic_detect.snap_region(self.page.image, self.page.empty_art)
        comic_records.validate_candidate(art, width=width, height=height)
        self.assertIsNone(art["interior"])
        self.assertEqual(art["bbox"], list(self.page.empty_art))
        self.assertFalse(art["plain_background"])
        clipped = comic_detect.snap_region(self.page.image, [-50, -40, 100, 90])
        comic_records.validate_candidate(clipped, width=width, height=height)
        self.assertEqual(clipped["bbox"], [0, 0, 100, 90])
        corner = comic_detect.snap_region(self.page.image, [width - 5, height - 5, width + 60, height + 60])
        comic_records.validate_candidate(corner, width=width, height=height)

    def test_deterministic_and_input_untouched(self):
        before = self.page.image.tobytes()
        box = self.page.truths[0].text_bbox
        a = comic_detect.snap_region(self.page.image, box)
        b = comic_detect.snap_region(self.page.image, box)
        self.assertEqual(a, b)
        self.assertEqual(self.page.image.tobytes(), before)


if __name__ == "__main__":
    unittest.main()
