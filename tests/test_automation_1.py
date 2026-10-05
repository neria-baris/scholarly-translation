"""Focused tests for the AUTOMATION-1 model-catalogue/token-counting slice.

Covers: deterministic mixed-script token sizing with no word-count claim of
conservatism, model-specific (not Luna-only) cost estimation including long
-context multipliers, custom pricing validation on ModelCapabilities,
Anthropic cache/thinking usage normalization, OpenAI/Anthropic/Chat
truncation detection, and PersistentBudget's call_output_cap.
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scholarly_translation import model_catalog, token_counting
from scholarly_translation.model_adapter import (
    AnthropicTextGenerationAdapter,
    OpenAICompatibleTextGenerationAdapter,
    OpenAITextGenerationAdapter,
    RequestValidationError,
    estimate_model_cost,
)
from scholarly_translation.model_config import ModelCapabilities, ModelConfigError
from scholarly_translation.runtime_controls import ControlStore, PersistentBudget, RuntimeControlsError


class TokenCountingTests(unittest.TestCase):
    def test_mixed_hebrew_japanese_latin_is_deterministic_and_bounded(self):
        text = "Hello עולם こんにちは world שלום"
        first = token_counting.count_tokens(text)
        second = token_counting.count_tokens(text)
        self.assertEqual(first, second)
        self.assertLessEqual(first["count"], first["upper_bound"])
        self.assertFalse(first["exact"])
        self.assertIn(first["method"], ("byte_upper_bound_estimate", "tiktoken_estimate_o200k_base"))

    def test_byte_upper_bound_never_claims_word_count_guarantee(self):
        # A pathological no-space string: a word-count heuristic would read
        # this as one "word" and drastically undercount; the byte bound must
        # still safely exceed its true token count.
        text = "א" * 500
        bound = token_counting.byte_upper_bound(text)
        self.assertGreater(bound, 500)

    def test_fits_within_uses_upper_bound_not_optimistic_count(self):
        text = "x" * 1000
        exact_bound = token_counting.count_tokens(text)["upper_bound"]
        self.assertTrue(token_counting.fits_within(text, exact_bound))
        self.assertFalse(token_counting.fits_within(text, exact_bound - 1))

    def test_rejects_non_string(self):
        with self.assertRaises(token_counting.TokenCountingError):
            token_counting.count_tokens(123)


class ModelCatalogTests(unittest.TestCase):
    def test_known_model_cost_is_not_luna_rate(self):
        usage = {"input": 1_000_000, "output": 1_000_000}
        luna = model_catalog.estimate_cost("openai", "gpt-6-luna", usage)
        sol = model_catalog.estimate_cost("openai", "gpt-6.1-sol", usage)
        self.assertNotEqual(luna["cost_usd"], sol["cost_usd"])
        self.assertEqual(luna["basis"], "catalog")
        self.assertEqual(sol["basis"], "catalog")

    def test_long_context_multiplier_applies_to_entire_request(self):
        small = model_catalog.estimate_cost("openai", "gpt-6.1-sol", {"input": 1000, "output": 100})
        big = model_catalog.estimate_cost(
            "openai", "gpt-6.1-sol", {"input": model_catalog.LONG_CONTEXT_INPUT_TOKENS + 1, "output": 100},
        )
        self.assertFalse(small["long_context_applied"])
        self.assertTrue(big["long_context_applied"])
        self.assertEqual(big["rates_per_million"]["input"], 2.0 * 2.0)
        self.assertEqual(big["rates_per_million"]["output"], 10.0 * 1.5)

    def test_unknown_model_is_labelled_conservative_not_luna(self):
        usage = {"input": 1000, "output": 1000}
        result = model_catalog.estimate_cost("openai", "some-future-model", usage)
        self.assertEqual(result["basis"], "unknown_conservative")
        luna = model_catalog.estimate_cost("openai", "gpt-6-luna", usage)
        self.assertGreater(result["cost_usd"], luna["cost_usd"])

    def test_custom_pricing_overrides_catalog(self):
        usage = {"input": 1000, "output": 1000}
        result = model_catalog.estimate_cost(
            "openai", "gpt-6-luna", usage, custom_rates={"input": 9.0, "output": 9.0},
        )
        self.assertEqual(result["basis"], "custom")
        self.assertGreater(result["cost_usd"], 0)

    def test_malformed_usage_returns_none_not_a_guess(self):
        self.assertIsNone(model_catalog.estimate_cost("openai", "gpt-6-luna", {"input": -1, "output": 1}))
        self.assertIsNone(model_catalog.estimate_cost("openai", "gpt-6-luna", "not a dict"))

    def test_validate_custom_pricing_rejects_non_finite_or_negative(self):
        with self.assertRaises(model_catalog.ModelCatalogError):
            model_catalog.validate_custom_pricing({"input": -1, "output": 1})
        with self.assertRaises(model_catalog.ModelCatalogError):
            model_catalog.validate_custom_pricing({"input": float("inf"), "output": 1})
        with self.assertRaises(model_catalog.ModelCatalogError):
            model_catalog.validate_custom_pricing({"output": 1})


class ModelConfigCustomPricingTests(unittest.TestCase):
    def test_capabilities_accept_valid_custom_pricing(self):
        caps = ModelCapabilities.from_dict({
            "context_window": 1000, "usable_context_tokens": 800,
            "custom_pricing": {"input": 1.0, "output": 2.0},
        })
        self.assertEqual(caps.custom_pricing["cached"], 1.0)
        self.assertEqual(caps.to_dict()["custom_pricing"]["output"], 2.0)

    def test_capabilities_reject_invalid_custom_pricing(self):
        with self.assertRaises(ModelConfigError):
            ModelCapabilities.from_dict({
                "context_window": 1000, "usable_context_tokens": 800,
                "custom_pricing": {"input": -1.0, "output": 2.0},
            })

    def test_capabilities_default_custom_pricing_is_none(self):
        caps = ModelCapabilities.from_dict({"context_window": 1000, "usable_context_tokens": 800})
        self.assertIsNone(caps.custom_pricing)


class EstimateModelCostTests(unittest.TestCase):
    def test_estimate_model_cost_widens_beyond_openai(self):
        usage = {"input": 1000, "output": 1000}
        result = estimate_model_cost("anthropic", "claude-sonnet-5-5", usage)
        self.assertNotEqual(result, "not_metered")
        unknown = estimate_model_cost("anthropic", "some-unlisted-model", usage)
        self.assertNotEqual(unknown, "not_metered")

    def test_estimate_model_cost_not_metered_on_malformed_usage(self):
        self.assertEqual(estimate_model_cost("openai", "gpt-6-luna", "not_metered"), "not_metered")


class AnthropicUsageNormalizationTests(unittest.TestCase):
    def test_cache_read_and_creation_included_in_input_once(self):
        response = SimpleNamespace(
            content=[SimpleNamespace(text="שלום")],
            model="claude-sonnet-5-5",
            stop_reason="end_turn",
            usage=SimpleNamespace(
                input_tokens=100, output_tokens=50,
                cache_read_input_tokens=20, cache_creation_input_tokens=30,
                cache_creation=SimpleNamespace(ephemeral_5m_input_tokens=10, ephemeral_1h_input_tokens=20),
            ),
        )
        client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: response))
        adapter = AnthropicTextGenerationAdapter(client=client)
        result = adapter.generate("prompt", "claude-sonnet-5-5")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.token_usage["input"], 100 + 20 + 30)
        self.assertEqual(result.token_usage["cached"], 20)
        self.assertEqual(result.token_usage["cache_write"], 10)
        self.assertEqual(result.token_usage["cache_write_1h"], 20)
        self.assertEqual(result.token_usage["output"], 50)

    def test_truncated_response_never_marked_completed(self):
        response = SimpleNamespace(
            content=[SimpleNamespace(text="partial")], model="claude-sonnet-5-5",
            stop_reason="max_tokens",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )
        client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: response))
        adapter = AnthropicTextGenerationAdapter(client=client)
        result = adapter.generate("prompt", "claude-sonnet-5-5")
        self.assertNotIn(result.status, ("completed", "mock_placeholder"))
        self.assertEqual(result.status, "failed_truncated")
        self.assertNotEqual(result.token_usage, "not_metered")

    def test_absent_stop_reason_is_legacy_compatible(self):
        response = SimpleNamespace(
            content=[SimpleNamespace(text="שלום")], model="claude-sonnet-5-5",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )
        client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: response))
        adapter = AnthropicTextGenerationAdapter(client=client)
        result = adapter.generate("prompt", "claude-sonnet-5-5")
        self.assertEqual(result.status, "completed")


class OpenAITruncationTests(unittest.TestCase):
    def test_incomplete_max_output_tokens_never_completed(self):
        response = SimpleNamespace(
            status="incomplete", output_text="partial", model="gpt-6.1-sol",
            incomplete_details=SimpleNamespace(reason="max_output_tokens"),
            usage=SimpleNamespace(input_tokens=10, output_tokens=5, input_tokens_details=None, output_tokens_details=None),
        )
        client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kw: response))
        adapter = OpenAITextGenerationAdapter(client=client)
        result = adapter.generate("prompt", "gpt-6.1-sol")
        self.assertEqual(result.status, "failed_truncated")
        self.assertNotEqual(result.token_usage, "not_metered")

    def test_reasoning_effort_rejected_when_unsupported(self):
        adapter = OpenAITextGenerationAdapter(client=SimpleNamespace(), reasoning="minimal")
        with self.assertRaises(RequestValidationError):
            adapter.generate("prompt", "gpt-6-luna")

    def test_luna_documented_high_effort_can_be_requested(self):
        payloads = []
        response = SimpleNamespace(status='completed', output_text='שלום', model='gpt-6-luna',
            usage=SimpleNamespace(input_tokens=100, output_tokens=20))
        def create(**payload):
            payloads.append(payload)
            return response
        client = SimpleNamespace(responses=SimpleNamespace(create=create))
        answer = OpenAITextGenerationAdapter(client=client, reasoning='high').generate('prompt', 'gpt-6-luna')
        self.assertEqual(answer.status, 'completed')
        self.assertEqual(payloads[0]['reasoning'], {'effort': 'high'})


class ChatTruncationTests(unittest.TestCase):
    def test_finish_reason_length_never_completed(self):
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="partial"), finish_reason="length")],
            model="deepseek-chat",
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )
        provider = SimpleNamespace(provider_id="deepseek", base_url="https://api.deepseek.com")
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: response)))
        adapter = OpenAICompatibleTextGenerationAdapter(client=client, provider_definition=provider)
        result = adapter.generate("prompt", "deepseek-chat")
        self.assertEqual(result.status, "failed_truncated")


class PersistentBudgetCallOutputCapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "controls.sqlite3"
        self.store = ControlStore(self.db_path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_call_output_cap_defaults_to_task_cap(self):
        budget = PersistentBudget(
            self.store, "task-1", max_calls=3, hard_list_usd=0.01, stage="translate",
            provider="openai", model="gpt-6-luna", output_cap=256,
        )
        self.assertEqual(budget.call_output_cap, 256)

    def test_call_output_cap_cannot_exceed_task_ceiling(self):
        with self.assertRaises(RuntimeControlsError):
            PersistentBudget(
                self.store, "task-1", max_calls=3, hard_list_usd=0.01, stage="translate",
                provider="openai", model="gpt-6-luna", output_cap=256, call_output_cap=257,
            )

    def test_different_models_price_differently_under_one_task(self):
        luna_budget = PersistentBudget(
            self.store, "task-1", max_calls=3, hard_list_usd=0.01, stage="translate",
            provider="openai", model="gpt-6-luna", output_cap=1000, call_output_cap=100,
        )
        sol_budget = PersistentBudget(
            self.store, "task-1", max_calls=3, hard_list_usd=0.01, stage="translate_other",
            provider="openai", model="gpt-6.1-sol", output_cap=1000, call_output_cap=100,
        )
        self.assertNotEqual(luna_budget.amount("short prompt"), sol_budget.amount("short prompt"))


if __name__ == "__main__":
    unittest.main()
