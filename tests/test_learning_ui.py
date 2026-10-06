"""LEARN builder D: offline static contract checks for the learning UI.

No browser/JS runtime is exercised here (Bash/Node unavailable); these are
syntax/wiring/accessibility/token/key-nonstorage checks on the shipped text,
plus the existing-flow files that must stay untouched by this builder.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / 'scholarly_translation'


class LearningHtmlTests(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / 'learning.html').read_text(encoding='utf-8')

    def test_rtl_hebrew_page(self):
        self.assertIn('lang="he"', self.html)
        self.assertIn('dir="rtl"', self.html)

    def test_config_token_injection_like_ui_html(self):
        self.assertIn('window.UI_CONFIG = __CONFIG__', self.html)
        self.assertIn('/learning.js', self.html)
        self.assertIn('/learning.css', self.html)

    def test_upload_input_accepts_epub_only(self):
        self.assertIn('accept=".epub,application/epub+zip"', self.html)

    def test_no_source_text_or_path_literals(self):
        # The page must not carry any book text/path baked in; it only ever
        # receives a job_id via the query string, imported server-side.
        self.assertNotIn('source_text', self.html)
        self.assertNotIn('.pdf', self.html)


class LearningJsTests(unittest.TestCase):
    def setUp(self):
        self.js = (ROOT / 'learning.js').read_text(encoding='utf-8')

    def test_uses_ui_token_header(self):
        self.assertIn("'X-UI-Token':token", self.js)

    def test_never_stores_api_key(self):
        # The key input value must never be persisted to storage/log/URL.
        self.assertNotIn("setItem('learning-key", self.js)
        self.assertNotIn('console.log', self.js)
        self.assertIn("$('learning-key').value=''", self.js)

    def test_completion_id_is_stable_per_session_not_a_secret(self):
        self.assertIn('completionIdFor', self.js)
        self.assertIn('localStorage', self.js)
        self.assertIn('completion_id', self.js)

    def test_imports_query_job_id_once_and_strips_it(self):
        self.assertIn("params.get('job_id')", self.js)
        self.assertIn('history.replaceState', self.js)
        self.assertIn('/learning/import-translation', self.js)

    def test_gloss_toggle_handlers_present(self):
        self.assertIn('learning-foreign-click', self.js)
        self.assertIn("event.key==='Enter'", self.js)
        self.assertIn("event.key===' '", self.js)

    def test_recap_rendered_through_textcontent_only(self):
        # Only the trusted server 'html' field may use innerHTML; the recap
        # object (vocabulary/grammar/warnings) must be escaped via textContent.
        self.assertIn("result.html;", self.js)  # reader fragment, server-trusted
        recap_section = self.js[self.js.index('function renderRecap'):]
        self.assertNotIn('innerHTML', recap_section[:recap_section.index('function toggleGloss')])

    def test_explicit_completion_action(self):
        self.assertIn('/learning/complete', self.js)
        self.assertIn("button.disabled=true", self.js)

    def test_routes_present(self):
        for route in ('/learning/state', '/learning/upload-epub', '/learning/effort',
                       '/learning/prepare', '/learning/resume', '/learning/pause',
                       '/learning/abandon', '/learning/read', '/learning/cursor',
                       '/learning/complete', '/learning/wordlist', '/model-keys'):
            self.assertIn(route, self.js)


class LearningCssTests(unittest.TestCase):
    def test_file_exists_and_non_empty(self):
        css = (ROOT / 'learning.css').read_text(encoding='utf-8')
        self.assertTrue(css.strip())
        self.assertIn('.learning-foreign-click', css)


class UiHtmlLearningLinkTests(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / 'ui.html').read_text(encoding='utf-8')

    def test_separate_window_link_present(self):
        self.assertIn('href="/learning"', self.html)
        self.assertIn('target="scholarly-learning"', self.html)
        self.assertIn('rel="noopener"', self.html)

    def test_existing_panels_preserved(self):
        for marker in ('id="start-panel"', 'id="processing-panel"', 'id="result-panel"',
                       'id="library-panel"', 'id="translation-form"', 'id="review-panel"'):
            self.assertIn(marker, self.html)


class UiJsLibraryHandoffTests(unittest.TestCase):
    def setUp(self):
        self.js = (ROOT / 'ui.js').read_text(encoding='utf-8')

    def test_transfer_action_wired_without_source_text_in_url(self):
        self.assertIn('openLearningWindow', self.js)
        self.assertIn("'/learning?job_id='+encodeURIComponent(doc.job_id)", self.js)
        self.assertIn("window.open(target,'scholarly-learning')", self.js)

    def test_fallback_link_when_popup_blocked(self):
        start = self.js.index('function openLearningWindow')
        end = self.js.index('function libraryOpen')
        body = self.js[start:end]
        self.assertIn('if(!win)', body)
        self.assertIn("link.target='scholarly-learning'", body)
        self.assertIn("link.rel='noopener'", body)

    def test_existing_handlers_preserved(self):
        for marker in ('function renderLibrary', 'function loadLibrary', 'function libraryDownload',
                       'function libraryOpen', 'function translate', 'async function sample'):
            self.assertIn(marker, self.js)


class WordlistConstraintTests(unittest.TestCase):
    def test_wordlist_links_cover_all_five_languages(self):
        js = (ROOT / 'learning.js').read_text(encoding='utf-8')
        self.assertIn('LANGUAGE_NAMES', js)
        for code in ('fr', 'de', 'es', 'yi', 'it'):
            self.assertIn(f"{code}:", js)


if __name__ == '__main__':
    unittest.main()
