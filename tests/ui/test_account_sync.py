"""One OpenAI account state across the app, project reasoning defaults, and the blinking key light
(user requests 2026-11-05)."""
import re
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[2] / "scholarly_translation" / "ui"


def _read(name):
    return (UI / name).read_text(encoding="utf-8")


class AccountStateIsSharedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui, cls.profile, cls.learning = _read("ui.js"), _read("profile.js"), _read("learning.js")

    def test_card_and_window_announce_changes_to_each_other(self):
        # Each side announces with its own source tag and ignores its own announcements.
        self.assertIn("new CustomEvent('openai-account',{detail:{state:openaiState,source:'ui'}})", self.ui)
        self.assertIn("new CustomEvent('openai-account',{detail:{state:openai,source:'profile'}})", self.profile)
        self.assertIn("d.source==='ui'", self.ui)
        self.assertIn("d.source==='profile'", self.profile)

    def test_card_takes_the_windows_state_and_rechecks_what_needs_a_key(self):
        listener = self.ui[self.ui.index("window.addEventListener('openai-account'"):]
        listener = listener[:listener.index("});") + 3]
        for call in ("renderOpenAI()", "renderKeyFields()", "updateSettings()"):
            self.assertIn(call, listener)

    def test_only_real_changes_are_announced(self):
        self.assertIn("if(sig===openaiSig)return false", self.ui)
        self.assertIn("const first=!openaiSig", self.ui)
        self.assertIn("if(first)return;", self.profile)

    def test_other_windows_and_returning_from_the_consent_page(self):
        self.assertIn("new BroadcastChannel('scholarly-openai-account')", self.profile)
        self.assertIn("channel.onmessage=function(){if(token)refreshOpenAI()}", self.profile)
        for source in (self.ui, self.profile):
            self.assertIn("addEventListener('focus'", source)
            self.assertIn("addEventListener('visibilitychange'", source)
        self.assertIn("window.addEventListener('openai-account',()=>{loadState().catch(()=>{})});", self.learning)

    def test_key_field_says_the_account_covers_openai(self):
        self.assertIn("openaiCoversProvider(pid)&&!keyProvidersAvailable[pid]", self.ui)
        self.assertIn("(optional: the connected OpenAI account is used; the key only when its budget runs out)", self.ui)


class ReasoningDefaultsTests(unittest.TestCase):
    def test_luna_low_and_sol_medium_by_default(self):
        from scholarly_translation.models import catalog
        self.assertEqual(catalog.default_reasoning(catalog.resolve("openai", "gpt-6-luna")), "low")
        self.assertEqual(catalog.default_reasoning(catalog.resolve("openai", "gpt-6.1-sol")), "medium")
        self.assertIsNone(catalog.default_reasoning(catalog.resolve("anthropic", "claude-sonnet-5-5")))

    def test_every_default_is_a_listed_value(self):
        from scholarly_translation.models import catalog
        for entry in catalog._CATALOG.values():
            if entry.default_reasoning is not None:
                self.assertIn(entry.default_reasoning, entry.reasoning_values)

    def test_no_caller_reads_the_first_listed_value_directly(self):
        root = UI.parent
        for path in root.rglob("*.py"):
            self.assertNotIn("reasoning_values[0]", path.read_text(encoding="utf-8").replace(
                "else entry.reasoning_values[0]", ""), str(path))


class KeyLightTests(unittest.TestCase):
    def test_any_key_makes_the_light_blink_green_unless_reduced_motion(self):
        theme = _read("ui-theme.css")
        rule = re.search(r"\.app-header \.key-indicator\.has-key \.key-badge\{([^}]*)\}", theme).group(1)
        self.assertIn("display:block", rule)
        self.assertIn("animation:key-blink", rule)
        self.assertRegex(rule, r"background:#5cbf6e")
        self.assertIn("@keyframes key-blink", theme)
        self.assertRegex(theme, r"prefers-reduced-motion:reduce\)\{\.app-header \.key-indicator\.has-key \.key-badge\{animation:none\}")


if __name__ == "__main__":
    unittest.main()
