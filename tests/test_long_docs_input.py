"""LONG-DOCS layers 1, 2, 4 (plumbing) and 5: EPUB diagnosis/fallbacks,
structural chapter groups, unit_policy pass-through and size limits."""
from __future__ import annotations

import io
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from scholarly_translation import context_strategy
from scholarly_translation import document_draft as dd
from scholarly_translation.epub_extract import EpubExtractionError, extract_epub

XHTML = '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><body>%s</body></html>'
OPF_NS = 'xmlns="http://www.idpf.org/2007/opf"'


def para_chapter(title, count):
    body = "<h1>%s</h1>" % title
    for i in range(count):
        body += "<p>%s sentence number %d of the chapter, with some filler words to give it length.</p>" % (title, i)
    return XHTML % body


def build_epub(chapters, spine=True, extra_manifest="", ncx=None, nav=None, encryption=None):
    """chapters: list of (name, xhtml str). Returns bytes of a synthetic EPUB."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml",
                   '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                   '<rootfile full-path="OEBPS/package.opf"/></rootfiles></container>')
        manifest = "".join('<item id="i%d" href="%s" media-type="application/xhtml+xml"/>' % (i, n)
                           for i, (n, _) in enumerate(chapters))
        if ncx is not None:
            manifest += '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
            z.writestr("OEBPS/toc.ncx", ncx)
        if nav is not None:
            manifest += '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
            z.writestr("OEBPS/nav.xhtml", nav)
        itemrefs = "".join('<itemref idref="i%d"/>' % i for i in range(len(chapters))) if spine else ""
        z.writestr("OEBPS/package.opf", '<package %s><metadata/><manifest>%s%s</manifest><spine>%s</spine></package>'
                   % (OPF_NS, manifest, extra_manifest, itemrefs))
        for n, content in chapters:
            z.writestr("OEBPS/" + n, content)
        if encryption:
            z.writestr("META-INF/encryption.xml", encryption)
    return buf.getvalue()


def three_chapters():
    return [("a.xhtml", XHTML % "<h1>Alpha</h1><p>alpha text</p>"),
            ("b.xhtml", XHTML % "<h1>Beta</h1><p>beta text</p>"),
            ("c.xhtml", XHTML % "<h1>Gamma</h1><p>gamma text</p>")]


def texts(document):
    return [p.source_text.split("\n")[0] for p in document.pages]


class EpubDiagnosisTests(unittest.TestCase):
    def test_ncx_fallback_order_and_warning(self):
        ncx = ('<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap>'
               '<navPoint playOrder="2"><content src="c.xhtml"/></navPoint>'
               '<navPoint playOrder="1"><content src="a.xhtml#x"/></navPoint>'
               '<navPoint playOrder="3"><content src="a.xhtml"/></navPoint>'
               '</navMap></ncx>')
        doc = extract_epub(build_epub(three_chapters(), spine=False, ncx=ncx), "en")
        self.assertEqual(texts(doc), ["Alpha", "Gamma", "Beta"])  # ncx order, dedup, rest appended
        self.assertTrue(any("ncx" in w for w in doc.warnings))

    def test_nav_fallback(self):
        nav = ('<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>'
               '<nav epub:type="toc"><ol><li><a href="b.xhtml">B</a></li><li><a href="a.xhtml">A</a></li>'
               '</ol></nav></body></html>')
        doc = extract_epub(build_epub(three_chapters(), spine=False, nav=nav), "en")
        self.assertEqual(texts(doc), ["Beta", "Alpha", "Gamma"])
        self.assertTrue(any("nav" in w for w in doc.warnings))

    def test_manifest_fallback(self):
        doc = extract_epub(build_epub(three_chapters(), spine=False), "en")
        self.assertEqual(texts(doc), ["Alpha", "Beta", "Gamma"])
        self.assertTrue(any("manifest" in w for w in doc.warnings))

    def test_normal_spine_has_no_warning(self):
        self.assertEqual(extract_epub(build_epub(three_chapters()), "en").warnings, [])

    def test_empty_spine_no_content(self):
        with self.assertRaises(EpubExtractionError) as ctx:
            extract_epub(build_epub([], spine=False), "en")
        self.assertEqual(ctx.exception.code, "empty_spine")

    def test_all_empty_chapter_files(self):
        data = build_epub([("a.xhtml", ""), ("b.xhtml", "")], spine=False)
        with self.assertRaises(EpubExtractionError) as ctx:
            extract_epub(data, "en")
        self.assertEqual(ctx.exception.code, "empty_chapters")
        self.assertIn("empty", str(ctx.exception))

    def test_all_empty_chapter_files_hebrew_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.epub"
            path.write_bytes(build_epub([("a.xhtml", "")], spine=True))
            with self.assertRaises(dd.DocumentDraftError) as ctx:
                dd.extract_structure(path)
        self.assertIn("קובצי הפרקים בתוכו ריקים", str(ctx.exception))

    def test_some_empty_chapters_are_skipped(self):
        chapters = [("a.xhtml", ""), ("b.xhtml", XHTML % "<p>real</p>")]
        doc = extract_epub(build_epub(chapters), "en")
        self.assertEqual(len(doc.pages), 2)
        self.assertEqual(doc.pages[0].segments, [])

    def test_image_only_is_no_text(self):
        with self.assertRaises(EpubExtractionError) as ctx:
            extract_epub(build_epub([("a.xhtml", XHTML % '<img src="x.png"/>')]), "en")
        self.assertEqual(ctx.exception.code, "no_text")

    def test_drm_still_rejected(self):
        enc = ('<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><EncryptedData>'
               '<CipherData><CipherReference URI="OEBPS/a.xhtml"/></CipherData></EncryptedData></encryption>')
        with self.assertRaises(EpubExtractionError) as ctx:
            extract_epub(build_epub(three_chapters(), encryption=enc), "en")
        self.assertEqual(ctx.exception.code, "drm")
        with self.assertRaises(EpubExtractionError) as ctx:
            extract_epub(build_epub(three_chapters(), spine=False, encryption=enc), "en")
        self.assertEqual(ctx.exception.code, "drm")

    def test_bad_spine_item_code(self):
        data = build_epub(three_chapters(), extra_manifest='<item id="x" href="x.png" media-type="image/png"/>')
        src = zipfile.ZipFile(io.BytesIO(data))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for n in src.namelist():
                content = src.read(n)
                if n.endswith(".opf"):
                    content = content.replace(b'<itemref idref="i0"/>', b'<itemref idref="x"/>')
                z.writestr(n, content)
        with self.assertRaises(EpubExtractionError) as ctx:
            extract_epub(buf.getvalue(), "en")
        self.assertEqual(ctx.exception.code, "bad_spine_item")


def structure_for(chapters):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "b.epub"
        path.write_bytes(build_epub(chapters))
        return dd.extract_structure(path)


def big(title, n=30):
    return (title + ".xhtml", para_chapter(title, n))


class ChapterGroupTests(unittest.TestCase):
    def check_partition(self, structure, groups):
        flat = [u["unit_id"] for g in groups for u in g]
        self.assertEqual(flat, [u["unit_id"] for u in structure["units"]])
        self.assertTrue(all(groups))

    def test_one_group_per_spine_document(self):
        structure = structure_for([big("one"), big("two"), big("three")])
        groups = dd.chapter_groups(structure, structure["units"])
        self.check_partition(structure, groups)
        self.assertEqual(len(groups), 3)
        for g in groups:
            self.assertEqual(len({u["page_id"] for u in g}), 1)

    def test_tiny_documents_merge_forward_and_backward(self):
        def tiny(t):
            return (t + ".xhtml", XHTML % ("<h1>%s</h1><p>short</p>" % t))
        structure = structure_for([tiny("t1"), big("big1"), tiny("t2"), big("big2"), tiny("t3")])
        groups = dd.chapter_groups(structure, structure["units"])
        self.check_partition(structure, groups)
        self.assertEqual([len({u["page_id"] for u in g}) for g in groups], [2, 3])

    def test_deterministic_and_method_delegates(self):
        structure = structure_for([big("one"), big("two")])
        units = structure["units"]
        self.assertEqual(dd.chapter_groups(structure, units), dd.chapter_groups(structure, units))
        self.assertEqual(dd.DocumentJobs._chapter_groups(None, structure, units),
                         dd.chapter_groups(structure, units))

    def test_all_tiny_single_group(self):
        structure = structure_for([("a.xhtml", XHTML % "<p>x</p>"), ("b.xhtml", XHTML % "<p>y</p>")])
        self.assertEqual(len(dd.chapter_groups(structure, structure["units"])), 1)

    def test_pdf_like_flat_structure_single_group(self):
        structure = structure_for([big("one"), big("two"), big("three")])
        pdf_like = dict(structure)
        pdf_like["readings"] = [
            dict(r, selected={"origin": "digital", "candidate_hash": "x"},
                 alternatives=[dict(a, origin="digital") for a in r["alternatives"]])
            for r in structure["readings"]]
        groups = dd.chapter_groups(pdf_like, pdf_like["units"])
        self.assertEqual(len(groups), 1)
        self.check_partition(structure, groups)

    def test_chapter_nodes_keep_existing_grouping(self):
        structure = structure_for([big("one"), big("two")])
        units = structure["units"]
        calls = []
        real = context_strategy.find_enclosing_chapter_node

        def fake(struct, unit):
            calls.append(unit["unit_id"])
            return {"node_id": "A" if len(calls) <= 2 else "B"}
        context_strategy.find_enclosing_chapter_node = fake
        try:
            groups = dd.chapter_groups(structure, units)
        finally:
            context_strategy.find_enclosing_chapter_node = real
        self.assertEqual([len(g) for g in groups], [2, len(units) - 2])


class LongBookTests(unittest.TestCase):
    def test_800k_chars_50_documents(self):
        chapters = [("c%02d.xhtml" % i, para_chapter("c%02d" % i, 180)) for i in range(50)]
        self.assertGreater(sum(len(c) for _, c in chapters), 700_000)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "long.epub"
            path.write_bytes(build_epub(chapters))
            start = time.time()
            structure = dd.extract_structure(path)
            elapsed = time.time() - start
            groups = dd.chapter_groups(structure, structure["units"])
        print("800k extract_structure seconds: %.2f" % elapsed)
        self.assertLess(elapsed, 30)
        self.assertEqual(len(groups), 50)

    def test_unit_policy_none_identical_and_narrow_smaller(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.epub"
            path.write_bytes(build_epub([big("one", 60)]))
            default = dd.extract_structure(path)
            explicit = dd.extract_structure(path, unit_policy=None)
            narrow = dd.extract_structure(path, unit_policy={"max_unit_words": 100})
        self.assertEqual(default, explicit)
        self.assertGreater(len(narrow["units"]), len(default["units"]))
        self.assertLess(max(len(u["text"]) for u in narrow["units"]),
                        max(len(u["text"]) for u in default["units"]))


class LimitTests(unittest.TestCase):
    def test_constants_and_budget(self):
        self.assertEqual((dd.MAX_SOURCE_CHARS, dd.MAX_PAGES, dd.MAX_BUDGET_USD), (3_000_000, 2_000, 30))
        self.assertEqual(dd.validate_settings({"budget_usd": 30})["budget_usd"], 30.0)
        with self.assertRaises(dd.DocumentDraftError) as ctx:
            dd.validate_settings({"budget_usd": 31})
        self.assertIn("$30", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
