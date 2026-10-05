"""Public export contract: selecting/rerendering fonts never translates text."""
import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pdfplumber
from pdfminer.pdftypes import resolve1

from scholarly_translation import export_common
from scholarly_translation.export_common import ExportError, list_pdf_fonts, resolve_hebrew_font
from scholarly_translation.export_pdf import export_pdf
from test_export_pdf import _build_structure_from_lines


class PdfFontSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.structure = _build_structure_from_lines(Path(self.tmp.name)/'source.pdf',
                                                    ['Chapter One', 'An original sentence.'])
        self.translations = {u['unit_id']: {'text': ('שלום עולם - (Smith, 2026) 12345. ' * 180),
                                           'approved':False, 'status':'unreviewed'}
                             for u in self.structure['units']}

    def test_all_five_faces_available_with_honest_license_metadata(self):
        choices = list_pdf_fonts()
        self.assertEqual([c['name'] for c in choices],
                         ['David Libre','Hadasim CLM','Noto Serif Hebrew','Frank Ruhl Libre','David CLM'])
        self.assertTrue(all(c['available'] for c in choices))
        david = next(c for c in choices if c['id']=='david-clm')
        self.assertIn('no identified', david['embedding_note'])
        self.assertNotIn('OFL', david['license'])

    def test_each_font_embeds_its_regular_bold_faces_across_pages(self):
        before = copy.deepcopy(self.translations)
        all_signatures = []
        for choice in list_pdf_fonts():
            with self.subTest(font=choice['id']):
                result = export_pdf(self.structure,self.translations,title='כותרת הספר Book 2026',font_id=choice['id'])
                self.assertEqual(result.font_id, choice['id'])
                self.assertGreater(result.page_count, 1)
                with pdfplumber.open(io.BytesIO(result.content)) as pdf:
                    embedded = []
                    for resource in resolve1(pdf.pages[0].page_obj.resources['Font']).values():
                        font = resolve1(resource)
                        descriptor = resolve1(font.get('FontDescriptor'))
                        if descriptor and descriptor.get('FontFile2'):
                            embedded.append(resolve1(descriptor['FontFile2']).get_data())
                    self.assertEqual(len(embedded),2)
                    self.assertTrue(all(len(font)>1000 for font in embedded))
                    chars = [char for page in pdf.pages for char in page.chars]
                    self.assertTrue(any(ch['text']=='ש' for ch in chars))
                    extracted = ''.join(ch['text'] for ch in chars)
                    self.assertIn('Smith', extracted)
                    self.assertIn('12345', extracted)
                    self.assertTrue(all(ch['x0'] >= 53 and ch['x1'] <= 542 for ch in chars))
                    self.assertTrue(all(not entry['approved'] for entry in result.manifest))
                    all_signatures.append(tuple(hashlib.sha256(font).hexdigest() for font in embedded))
        self.assertEqual(len(set(all_signatures)),5)
        self.assertEqual(self.translations,before)

    def test_unknown_or_path_selection_fails_closed(self):
        for value in ['unknown','../../fonts.ttf','',True,{},42]:
            with self.subTest(value=value), self.assertRaises(ExportError):
                export_pdf(self.structure,self.translations,font_id=value)

    def test_missing_explicit_assets_never_substitute_host_fonts(self):
        with patch.object(export_common,'_BUNDLED_FONT_ROOT',Path(self.tmp.name)):
            self.assertTrue(all(not f['available'] for f in list_pdf_fonts()))
            with self.assertRaisesRegex(ExportError,'unavailable'):
                resolve_hebrew_font('david-libre')

    def test_reexport_preserves_text_and_manifest_without_model_requests(self):
        with patch('scholarly_translation.model_adapter.build_translation_adapter',side_effect=AssertionError('model call')):
            first=export_pdf(self.structure,self.translations,font_id='david-libre')
            second=export_pdf(self.structure,self.translations,font_id='noto-serif-hebrew')
        self.assertEqual(first.manifest,second.manifest)
        self.assertNotEqual(first.content,second.content)

    def test_long_body_starts_below_title_instead_of_leaving_empty_title_page(self):
        translations = copy.deepcopy(self.translations)
        translations[self.structure['units'][0]['unit_id']]['text'] = 'פרק ראשון'
        result=export_pdf(self.structure,translations,title='כותרת הספר',font_id='david-libre')
        with pdfplumber.open(io.BytesIO(result.content)) as pdf:
            self.assertIn('Smith',''.join(ch['text'] for ch in pdf.pages[0].chars))
            self.assertGreater(len(pdf.pages),1)

    def test_david_license_distinction_is_recorded_only_for_david(self):
        for font in list_pdf_fonts():
            result=export_pdf(self.structure,self.translations,font_id=font['id'])
            notices=[lim for lim in result.limitations if lim['kind']=='font_license_notice']
            self.assertEqual(len(notices),int(font['id']=='david-clm'))

    def test_bundled_source_and_built_hashes_match(self):
        root=export_common._BUNDLED_FONT_ROOT
        for manifest in ['sources.json','built_fonts.json']:
            for item in json.loads((root/manifest).read_text())['files']:
                self.assertEqual(hashlib.sha256((root/item['path']).read_bytes()).hexdigest(),item['sha256'])


if __name__ == '__main__': unittest.main()
