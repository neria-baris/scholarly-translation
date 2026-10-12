"""COMIC-0 data spine and fixture (audit/contracts/comic_translation.md)."""
import json
import unittest

from scholarly_translation.comics import records as cr
from tests import comic_fixtures


def candidate(**overrides):
    value = {"bbox": [10, 10, 60, 40], "interior": {"step": 2, "rows": [[8, 5, 70], [10, 4, 72]]},
             "background": [255, 255, 255], "plain_background": True, "line_height": 12.0, "confidence": 0.9}
    value.update(overrides)
    return value


class RecordTests(unittest.TestCase):
    def test_ids(self):
        self.assertEqual(cr.page_id(3), "p003")
        self.assertEqual(cr.region_id(3, 7), "p003-r07")

    def test_candidate_validation(self):
        cr.validate_candidate(candidate(), width=100, height=100)
        cr.validate_candidate(candidate(interior=None))
        for bad in (candidate(bbox=[10, 10, 10, 40]), candidate(bbox=[0, 0, 200, 20]),
                    candidate(interior={"step": 2, "rows": [[10, 5, 70], [8, 4, 72]]}),
                    candidate(interior={"step": 0, "rows": [[1, 1, 2]]}),
                    candidate(background=[0, 0, 300]), candidate(plain_background=1),
                    candidate(confidence=1.5), candidate(line_height=0)):
            with self.assertRaises(cr.ComicRecordError):
                cr.validate_candidate(bad, width=100, height=100)

    def test_region_page_comic_roundtrip(self):
        comic = cr.new_comic("c1", "en", "he")
        page = cr.new_page(1, "001.png", b"png-bytes", 100, 100)
        region = cr.new_region(candidate(), 1, 1, kind="thought", source_text="Hi", speaker="Ann",
                               speaker_gender="female")
        region["translation"] = {"text": "היי", "status": "ok", "note": ""}
        page["regions"].append(region)
        comic["pages"].append(page)
        comic["notebook"]["characters"].append({"name": "Ann", "target_name": "אן", "gender": "female", "note": ""})
        restored = json.loads(json.dumps(comic, ensure_ascii=False))
        self.assertEqual(cr.validate_comic(restored), comic)

    def test_region_errors(self):
        with self.assertRaises(cr.ComicRecordError):
            cr.new_region(candidate(), 1, 1, colour="red")
        page = cr.new_page(1, "a.png", b"x", 100, 100)
        page["regions"] = [cr.new_region(candidate(), 1, 1), cr.new_region(candidate(), 1, 1)]
        with self.assertRaisesRegex(cr.ComicRecordError, "duplicate"):
            cr.validate_page(page)
        page["regions"] = [cr.new_region(candidate(), 1, 1, kind="shout")]
        with self.assertRaisesRegex(cr.ComicRecordError, "kind"):
            cr.validate_page(page)
        page["regions"] = [cr.new_region(candidate(), 2, 1)]
        with self.assertRaisesRegex(cr.ComicRecordError, "another page"):
            cr.validate_page(page)


class FixtureTests(unittest.TestCase):
    def test_fixture_page_is_deterministic_and_scaled(self):
        a, b = comic_fixtures.make_page(), comic_fixtures.make_page()
        self.assertEqual(a.image.tobytes(), b.image.tobytes())
        self.assertEqual(a.image.size, (1000, 1500))
        self.assertEqual(comic_fixtures.make_page(2.0).image.size, (2000, 3000))
        kinds = sorted(t.kind for t in a.truths)
        self.assertEqual(kinds, ["narration", "sfx", "sign", "speech", "speech", "thought"])

    def test_text_sits_inside_its_container(self):
        page = comic_fixtures.make_page()
        for truth in page.truths:
            if truth.container_bbox is None:
                continue
            x0, y0, x1, y1 = truth.text_bbox
            for x, y in ((x0, y0), (x1 - 1, y0), (x0, y1 - 1), (x1 - 1, y1 - 1)):
                self.assertTrue(comic_fixtures.inside_container(truth, x, y), (truth.text, x, y))


if __name__ == "__main__":
    unittest.main()
