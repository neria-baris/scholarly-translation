import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from scholarly_translation.export_common import ExportError
from scholarly_translation.export_epub import export_epub, extract_epub_structure


def make_epub(path, extra_files=None):
    """A small, deterministic EPUB fixture mirroring the real structure
    this exporter must handle: two spine chapters, a stylesheet, an image,
    a heading/paragraph/list/blockquote mix, an internal cross-chapter
    link, an external link, and a figure with an untranslatable image."""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/package.opf"/></rootfiles></container>',
        )
        archive.writestr(
            "OEBPS/package.opf",
            '<package xmlns="http://www.idpf.org/2007/opf">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<dc:title>Original Title</dc:title><dc:language>en</dc:language>"
            "</metadata>"
            '<manifest>'
            '<item id="c0" href="chapter0.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="css" href="style.css" media-type="text/css"/>'
            '<item id="img1" href="image1.png" media-type="image/png"/>'
            "</manifest>"
            '<spine><itemref idref="c0"/><itemref idref="c1"/></spine>'
            "</package>",
        )
        archive.writestr("OEBPS/style.css", "p { color: navy; }")
        archive.writestr("OEBPS/image1.png", b"\x89PNG\r\n\x1a\nFAKE_IMAGE_BYTES")
        archive.writestr(
            "OEBPS/chapter0.xhtml",
            '<?xml version="1.0"?>'
            '<html xmlns="http://www.w3.org/1999/xhtml"><head>'
            '<link rel="stylesheet" href="style.css"/></head><body>'
            '<h1 id="ch0">Chapter Zero</h1>'
            "<p>A plain paragraph with no inline markup.</p>"
            '<p>A paragraph with <a href="chapter1.xhtml#note1">an internal link</a> '
            "inside it.</p>"
            '<p>See <a href="https://example.org">this external site</a> for more.</p>'
            '<div class="figure"><img src="image1.png"/>'
            "<p>Figure caption text.</p></div>"
            "</body></html>",
        )
        archive.writestr(
            "OEBPS/chapter1.xhtml",
            '<?xml version="1.0"?>'
            '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
            "<h2>Chapter One</h2>"
            '<p id="note1">Target paragraph for the internal link.</p>'
            "<ul><li>First item</li><li>Second item</li></ul>"
            "<blockquote>A quoted passage.</blockquote>"
            "</body></html>",
        )
        for name, content in (extra_files or {}).items():
            archive.writestr(name, content)


def _translations_for(structure, prefix="טקסט מתורגם"):
    return {u["unit_id"]: {"text": f"{prefix} {i}", "approved": True}
            for i, u in enumerate(structure["units"])}


class EpubStructureExtractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "book.epub"
        make_epub(self.path)

    def test_chapter_structure_and_heading_kinds_are_discovered_in_spine_order(self):
        structure = extract_epub_structure(self.path)
        chapters = [n["chapter_path"] for n in structure["nodes"]]
        self.assertEqual(chapters, sorted(chapters, key=lambda p: structure["spine"].index(p)))
        kinds = {n["kind"] for n in structure["nodes"]}
        self.assertEqual(kinds, {"heading", "paragraph", "list", "quotation"})
        self.assertEqual(structure["spine"], ["OEBPS/chapter0.xhtml", "OEBPS/chapter1.xhtml"])

    def test_unit_node_links_are_one_to_one_and_traceable(self):
        structure = extract_epub_structure(self.path)
        node_ids = {n["node_id"] for n in structure["nodes"]}
        unit_ids = {u["unit_id"] for u in structure["units"]}
        self.assertEqual(len(structure["unit_node_links"]), len(unit_ids))
        for link in structure["unit_node_links"]:
            self.assertEqual(len(link["node_ids"]), 1)
            self.assertIn(link["node_ids"][0], node_ids)
            self.assertIn(link["unit_id"], unit_ids)


class EpubExportPreservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "book.epub"
        make_epub(self.path)
        self.structure = extract_epub_structure(self.path)

    def _rebuild(self, translations=None):
        translations = translations if translations is not None else _translations_for(self.structure)
        result = export_epub(self.path, self.structure, translations)
        return result, zipfile.ZipFile(io.BytesIO(result.content))

    def test_package_is_a_valid_zip_with_resolvable_spine_and_manifest(self):
        result, archive = self._rebuild()
        names = set(archive.namelist())
        self.assertIn("OEBPS/package.opf", names)
        package = ET.fromstring(archive.read("OEBPS/package.opf"))
        href_by_id = {e.get("id"): e.get("href") for e in package.iter()
                      if e.tag.endswith("}item")}
        spine_ids = [e.get("idref") for e in package.iter() if e.tag.endswith("}itemref")]
        for item_id in spine_ids:
            href = href_by_id[item_id]
            self.assertIn(f"OEBPS/{href}", names)

    def test_css_is_retained_byte_identical_and_still_linked(self):
        result, archive = self._rebuild()
        self.assertEqual(archive.read("OEBPS/style.css"), b"p { color: navy; }")
        chapter0 = archive.read("OEBPS/chapter0.xhtml").decode("utf-8")
        self.assertIn('href="style.css"', chapter0)

    def test_image_bytes_are_retained_byte_identical(self):
        result, archive = self._rebuild()
        self.assertEqual(archive.read("OEBPS/image1.png"), b"\x89PNG\r\n\x1a\nFAKE_IMAGE_BYTES")

    def test_internal_link_target_and_id_survive_translation(self):
        result, archive = self._rebuild()
        chapter0 = archive.read("OEBPS/chapter0.xhtml").decode("utf-8")
        chapter1 = archive.read("OEBPS/chapter1.xhtml").decode("utf-8")
        self.assertIn('href="chapter1.xhtml#note1"', chapter0)
        self.assertIn('id="note1"', chapter1)

    def test_external_link_href_survives_inline_flattening(self):
        result, archive = self._rebuild()
        chapter0 = archive.read("OEBPS/chapter0.xhtml").decode("utf-8")
        self.assertIn('href="https://example.org"', chapter0)
        kinds = [lim["kind"] for lim in result.limitations]
        self.assertIn("inline_markup_flattened", kinds)

    def test_hebrew_rtl_semantics_are_added_to_translated_chapters(self):
        result, archive = self._rebuild()
        chapter0 = archive.read("OEBPS/chapter0.xhtml").decode("utf-8")
        self.assertIn('dir="rtl"', chapter0)
        self.assertIn('lang="he"', chapter0)
        package = archive.read("OEBPS/package.opf").decode("utf-8")
        self.assertIn("<dc:language>he</dc:language>", package)
        self.assertIn("Original Title", package)  # other metadata preserved

    def test_translated_text_is_substituted_into_existing_block_elements(self):
        translations = _translations_for(self.structure, prefix="תרגום בדיקה")
        result, archive = self._rebuild(translations)
        chapter1 = archive.read("OEBPS/chapter1.xhtml").decode("utf-8")
        self.assertIn("תרגום בדיקה", chapter1)
        self.assertNotIn("Chapter One", chapter1)

    def test_manifest_traces_every_rendered_unit_to_its_node(self):
        result, _archive = self._rebuild()
        node_ids = {n["node_id"] for n in self.structure["nodes"]}
        unit_ids = {u["unit_id"] for u in self.structure["units"]}
        for entry in result.manifest:
            self.assertIn(entry["unit_id"], unit_ids)
            for node_id in entry["node_ids"]:
                self.assertIn(node_id, node_ids)


class EpubGracefulDegradationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "book.epub"
        make_epub(self.path)
        self.structure = extract_epub_structure(self.path)

    def test_block_with_embedded_image_is_left_untranslated_not_dropped(self):
        # An *irregular floating figure*: an <img> nested directly inside a
        # translatable paragraph (not as its own sibling block), which this
        # exporter cannot safely substitute translated text into without
        # risking the image. It must degrade gracefully: keep the original
        # paragraph (with its image) untouched, record a limitation, and
        # never crash the whole export.
        path = Path(self.tmp.name) / "inline.epub"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "META-INF/container.xml",
                '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                '<rootfiles><rootfile full-path="OEBPS/package.opf"/></rootfiles></container>',
            )
            archive.writestr(
                "OEBPS/package.opf",
                '<package xmlns="http://www.idpf.org/2007/opf">'
                '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                "<dc:language>en</dc:language></metadata>"
                '<manifest><item id="c0" href="chapter0.xhtml" media-type="application/xhtml+xml"/>'
                '<item id="img1" href="image1.png" media-type="image/png"/></manifest>'
                '<spine><itemref idref="c0"/></spine></package>',
            )
            archive.writestr("OEBPS/image1.png", b"\x89PNG\r\n\x1a\nFAKE_IMAGE_BYTES")
            archive.writestr(
                "OEBPS/chapter0.xhtml",
                '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><body>'
                '<p>Text with an inline figure <img src="image1.png"/> right inside it.</p>'
                "</body></html>",
            )

        structure = extract_epub_structure(path)
        translations = _translations_for(structure, prefix="לא אמור להופיע")
        result = export_epub(path, structure, translations)
        self.assertTrue(any(lim["kind"] == "media_block_not_translated" for lim in result.limitations))
        with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
            rewritten = archive.read("OEBPS/chapter0.xhtml").decode("utf-8")
            self.assertEqual(archive.read("OEBPS/image1.png"), b"\x89PNG\r\n\x1a\nFAKE_IMAGE_BYTES")
        self.assertIn("inline figure", rewritten)
        self.assertNotIn("לא אמור להופיע", rewritten)

    def test_missing_translation_keeps_original_text_and_records_limitation(self):
        translations = _translations_for(self.structure)
        dropped_unit = self.structure["units"][0]["unit_id"]
        del translations[dropped_unit]
        result = export_epub(self.path, self.structure, translations)
        kinds = [lim["kind"] for lim in result.limitations]
        self.assertIn("missing_translation", kinds)


class EpubErrorHandlingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_not_a_zip_file_raises_specific_clean_exception(self):
        path = Path(self.tmp.name) / "broken.epub"
        path.write_bytes(b"this is not a zip archive")
        with self.assertRaises(ExportError) as ctx:
            extract_epub_structure(path)
        self.assertNotIn("Traceback", str(ctx.exception))

    def test_doctype_declaration_is_rejected(self):
        path = Path(self.tmp.name) / "doctype.epub"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "META-INF/container.xml",
                "<!DOCTYPE foo><container><rootfiles/></container>",
            )
        with self.assertRaises(ExportError):
            extract_epub_structure(path)

    def test_encrypted_chapter_is_rejected(self):
        path = Path(self.tmp.name) / "drm.epub"
        make_epub(path, extra_files={
            "META-INF/encryption.xml":
                '<encryption xmlns="urn:test">'
                '<CipherReference URI="OEBPS/chapter0.xhtml"/></encryption>',
        })
        with self.assertRaises(ExportError):
            extract_epub_structure(path)

    def test_export_requires_structure_from_extract_epub_structure(self):
        path = Path(self.tmp.name) / "book.epub"
        make_epub(path)
        with self.assertRaises(ExportError):
            export_epub(path, {"nodes": [], "units": []}, {})

    def test_malformed_translations_mapping_is_rejected(self):
        path = Path(self.tmp.name) / "book.epub"
        make_epub(path)
        structure = extract_epub_structure(path)
        with self.assertRaises(ExportError):
            export_epub(path, structure, {"x": "not-a-dict"})


class InputFormatDeterminesEpubOutputFormatTests(unittest.TestCase):
    def test_epub_input_produces_a_valid_zip_epub_by_default(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            path = Path(tmp.name) / "book.epub"
            make_epub(path)
            structure = extract_epub_structure(path)
            translations = _translations_for(structure)
            result = export_epub(path, structure, translations)
            with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
                self.assertIn("mimetype", archive.namelist())
                self.assertIn("META-INF/container.xml", archive.namelist())
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
