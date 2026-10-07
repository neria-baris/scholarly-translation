"""REASONING-CHOICE: a per-role reasoning effort chosen in the UI reaches the
provider request; an unset level leaves configurations and identities as before."""
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scholarly_translation import model_settings, review_qa
from scholarly_translation.model_adapter import (
    OpenAITextGenerationAdapter,
    RequestValidationError,
    TextGenerationResult,
    build_translation_adapter,
)
from scholarly_translation.model_config import ModelCapabilities, ModelConfigError, ProviderDefinition
from scholarly_translation.model_settings import ModelSettingsError
from scholarly_translation.work_journal import fingerprint

PACKAGE = Path(__file__).resolve().parents[1] / "scholarly_translation"
LUNA = {"source": "catalog", "provider": "openai", "model": "gpt-6-luna"}
SOL = {"source": "catalog", "provider": "openai", "model": "gpt-6.1-sol"}
SONNET = {"source": "catalog", "provider": "anthropic", "model": "claude-sonnet-5-5"}


class CapabilitiesTests(unittest.TestCase):
    def test_reasoning_round_trips_and_is_omitted_when_unset(self):
        base = {"context_window": 1000, "usable_context_tokens": 1000, "max_output_tokens": 100}
        legacy = ModelCapabilities.from_dict(base)
        self.assertIsNone(legacy.reasoning)
        self.assertNotIn("reasoning", legacy.to_dict())
        chosen = ModelCapabilities.from_dict(dict(base, reasoning="high"))
        self.assertEqual(chosen.reasoning, "high")
        self.assertEqual(ModelCapabilities.from_dict(chosen.to_dict()), chosen)

    def test_malformed_reasoning_is_rejected(self):
        base = {"context_window": 1000, "usable_context_tokens": 1000}
        for bad in ("", "High", "high effort", 3, True, "x" * 33):
            with self.assertRaises(ModelConfigError):
                ModelCapabilities.from_dict(dict(base, reasoning=bad))


class SelectionTests(unittest.TestCase):
    def test_unset_level_keeps_the_configuration_fingerprint(self):
        config = model_settings.build_configuration({"translator": LUNA}).to_dict()
        self.assertNotIn("reasoning", repr(config))
        again = model_settings.build_configuration({"translator": dict(LUNA)}).to_dict()
        self.assertEqual(fingerprint(config), fingerprint(again))

    def test_chosen_level_is_stored_mirrored_and_changes_the_fingerprint(self):
        plain = model_settings.build_configuration({"translator": LUNA})
        chosen = model_settings.build_configuration({"translator": dict(LUNA, reasoning="high")})
        for role in model_settings.ROLE_NAMES:
            self.assertEqual(chosen.models[role].capabilities.reasoning, "high")
        self.assertNotEqual(fingerprint(plain.to_dict()), fingerprint(chosen.to_dict()))
        split = model_settings.build_configuration({
            "translator": dict(SOL, reasoning="xhigh"), "semantic_reviewer": LUNA})
        self.assertEqual(split.models["translator"].capabilities.reasoning, "xhigh")
        self.assertIsNone(split.models["semantic_reviewer"].capabilities.reasoning)

    def test_unsupported_levels_are_rejected(self):
        for selection in (dict(SOL, reasoning="none"), dict(LUNA, reasoning="minimal"),
                          dict(SONNET, reasoning="high")):
            with self.assertRaises(ModelSettingsError):
                model_settings.build_configuration({"translator": selection})

    def test_catalogue_lists_levels_and_default(self):
        entries = {(e["provider"], e["model"]): e for e in model_settings.catalogue()}
        luna = entries[("openai", "gpt-6-luna")]
        self.assertEqual(luna["default_reasoning"], "none")
        self.assertIn("high", luna["reasoning_values"])
        self.assertEqual(entries[("openai", "gpt-6.1-sol")]["default_reasoning"], "low")
        self.assertEqual(entries[("anthropic", "claude-sonnet-5-5")]["reasoning_values"], [])
        self.assertIsNone(entries[("anthropic", "claude-sonnet-5-5")]["default_reasoning"])


class AdapterTests(unittest.TestCase):
    def test_builder_passes_the_level_to_the_openai_request(self):
        payloads = []
        response = SimpleNamespace(status="completed", output_text="שלום", model="gpt-6.1-sol",
                                   usage=SimpleNamespace(input_tokens=10, output_tokens=5))

        def create(**payload):
            payloads.append(payload)
            return response

        definition = ProviderDefinition("openai", "openai", "OPENAI_API_KEY")
        client = SimpleNamespace(responses=SimpleNamespace(create=create))
        adapter = build_translation_adapter("openai", "gpt-6.1-sol", client=client,
                                            provider_definition=definition, reasoning="high")
        self.assertIsInstance(adapter, OpenAITextGenerationAdapter)
        self.assertEqual(adapter.generate("prompt", "gpt-6.1-sol").status, "completed")
        self.assertEqual(payloads[0]["reasoning"], {"effort": "high"})

    def test_builder_refuses_a_level_for_a_provider_without_one(self):
        definition = ProviderDefinition("anthropic", "anthropic", "ANTHROPIC_API_KEY")
        with self.assertRaises(RequestValidationError):
            build_translation_adapter("anthropic", "claude-sonnet-5-5",
                                      provider_definition=definition, reasoning="high")

    def test_unit_review_builds_its_adapter_with_the_role_level(self):
        configuration = model_settings.build_configuration({
            "translator": LUNA, "semantic_reviewer": dict(SOL, reasoning="medium")})
        request = review_qa.build_unit_review_request_for_role(
            "The source sentence.", "משפט התרגום.", configuration, policy="all")
        captured = {}

        def fake_builder(*args, **kwargs):
            captured.update(kwargs)
            failed = TextGenerationResult(status="failed", text=None, token_usage="not_metered",
                                          observed_model="gpt-6.1-sol", duration_seconds=0.0, error="x")
            return SimpleNamespace(generate=lambda prompt, model: failed)

        with patch.object(review_qa, "build_translation_adapter", fake_builder):
            review_qa.run_unit_review(request)
        self.assertEqual(captured["reasoning"], "medium")

    def test_every_runtime_adapter_build_passes_a_reasoning_level(self):
        for path in PACKAGE.glob("*.py"):
            if path.name == "model_adapter.py":
                continue
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"build_translation_adapter\(", text):
                call = text[match.end():text.find("\n\n", match.end())]
                close = call.find(")\n")
                self.assertIn("reasoning=", call[:close if close >= 0 else None],
                              f"{path.name}: adapter built without the role's reasoning level")


if __name__ == "__main__":
    unittest.main()
