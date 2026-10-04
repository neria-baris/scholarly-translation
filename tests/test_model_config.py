import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scholarly_translation.model_adapter import (
    AnthropicTextGenerationAdapter,
    OpenAICompatibleTextGenerationAdapter,
    OpenAIConfigurationError,
    OpenAITextGenerationAdapter,
    TextGenerationResult,
    build_translation_adapter,
)
from scholarly_translation.runtime_controls import ControlStore, PersistentBudget, RuntimeCache
from scholarly_translation.review_qa import (
    build_candidate_comparison_request_for_role,
    build_chapter_qa_request_for_role,
    build_unit_review_request_for_role,
    run_candidate_comparison,
    run_chapter_qa,
    run_unit_review,
)
from scholarly_translation.model_config import (
    ModelConfigError,
    ModelConfiguration,
    ProviderDefinition,
    load_model_configuration,
)
from scholarly_translation.translation import compute_cache_key


def capabilities(context=1000, usable=800, output=200):
    return {"context_window": context, "usable_context_tokens": usable,
            "max_output_tokens": output, "structured_output": True}


def configuration():
    return ModelConfiguration.from_dict({
        "schema_version": 1,
        "providers": {
            "oa": {"type": "openai", "credential_env": "OPENAI_API_KEY"},
            "claude": {"type": "anthropic", "credential_env": "ANTHROPIC_API_KEY"},
            "ds": {"type": "deepseek", "credential_env": "DEEPSEEK_API_KEY",
                   "base_url": "https://api.deepseek.com"},
            "lab": {"type": "openai_compatible", "credential_env": "LAB_API_KEY",
                    "base_url": "https://models.example.test/v1"},
        },
        "models": {
            "translator": {"provider": "claude", "model": "translator-user-id",
                           "capabilities": capabilities()},
            "semantic_reviewer": {"provider": "oa", "model": "reviewer-user-id",
                                  "capabilities": capabilities(2000, 1600, 300)},
            "chapter_qa": {"provider": "ds", "model": "qa-user-id",
                           "capabilities": capabilities()},
            "candidate_evaluator": {"provider": "lab", "model": "eval-user-id",
                                    "capabilities": capabilities()},
            "context_state_builder": {"provider": "oa", "model": "reviewer-user-id",
                                      "capabilities": capabilities()},
        },
    })


class ConfigTests(unittest.TestCase):
    def test_roles_resolve_independently_and_may_share_model(self):
        config = configuration()
        translator, provider = config.resolve("translator")
        self.assertEqual((translator.provider, translator.model, provider.provider_type),
                         ("claude", "translator-user-id", "anthropic"))
        reviewer, _ = config.resolve("semantic_reviewer")
        context, _ = config.resolve("context_state_builder")
        self.assertEqual((reviewer.provider, reviewer.model), (context.provider, context.model))

    def test_capabilities_are_configurable_not_universal(self):
        config = configuration()
        self.assertEqual(config.resolve("translator")[0].capabilities.usable_context_tokens, 800)
        self.assertEqual(config.resolve("semantic_reviewer")[0].capabilities.context_window, 2000)

    def test_missing_role_has_no_fallback(self):
        data = configuration().to_dict()
        del data["models"]["chapter_qa"]
        with self.assertRaisesRegex(ModelConfigError, "no provider/model configured"):
            ModelConfiguration.from_dict(data).resolve("chapter_qa")

    def test_missing_credential_names_provider_and_env_not_secret(self):
        provider = configuration().resolve("translator")[1]
        with self.assertRaisesRegex(ModelConfigError, "ANTHROPIC_API_KEY") as caught:
            provider.require_credential({})
        self.assertNotIn("secret-value", str(caught.exception))

    def test_json_loader_and_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "models.json"
            path.write_text(__import__("json").dumps(configuration().to_dict()), encoding="utf-8")
            loaded = load_model_configuration(path)
        self.assertEqual(loaded.to_dict(), configuration().to_dict())

    def test_repository_example_is_valid(self):
        path = Path(__file__).resolve().parents[1] / "model_config.example.json"
        loaded = load_model_configuration(path)
        self.assertEqual(set(loaded.models), {
            "translator", "semantic_reviewer", "chapter_qa",
            "candidate_evaluator", "context_state_builder",
        })

    def test_compatible_endpoint_rejects_embedded_credentials(self):
        with self.assertRaises(ModelConfigError):
            ProviderDefinition.from_dict("bad", {"type": "openai_compatible",
                "credential_env": "BAD_KEY", "base_url": "https://user:pass@example.test/v1"})


class _ResponsesClient:
    def __init__(self):
        self.responses = self
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        usage = SimpleNamespace(input_tokens=2, output_tokens=1,
                                input_tokens_details=None, output_tokens_details=None)
        return SimpleNamespace(status="completed", output_text="ok", model=kwargs["model"], usage=usage)


class _AnthropicClient:
    def __init__(self):
        self.messages = self
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(content=[SimpleNamespace(text="ok")], model=kwargs["model"],
                               usage=SimpleNamespace(input_tokens=2, output_tokens=1))


class _ChatClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=self)
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                               model=kwargs["model"],
                               usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1))


class AdapterDispatchTests(unittest.TestCase):
    def test_openai_dispatch_uses_configured_model(self):
        client = _ResponsesClient()
        adapter = build_translation_adapter("openai", "arbitrary-model", client=client)
        self.assertIsInstance(adapter, OpenAITextGenerationAdapter)
        result = adapter.generate("prompt", "arbitrary-model")
        self.assertEqual((client.kwargs["model"], result.observed_provider),
                         ("arbitrary-model", "openai"))

    def test_anthropic_dispatch_uses_messages_shape(self):
        client = _AnthropicClient()
        adapter = build_translation_adapter("anthropic", "arbitrary-claude", client=client)
        self.assertIsInstance(adapter, AnthropicTextGenerationAdapter)
        result = adapter.generate("prompt", "arbitrary-claude")
        self.assertEqual(client.kwargs["messages"][0]["content"], "prompt")
        self.assertEqual(result.observed_provider, "anthropic")

    def test_deepseek_dispatch_uses_compatible_chat_shape(self):
        client = _ChatClient()
        adapter = build_translation_adapter("deepseek", "arbitrary-deepseek", client=client)
        self.assertIsInstance(adapter, OpenAICompatibleTextGenerationAdapter)
        result = adapter.generate("prompt", "arbitrary-deepseek")
        self.assertEqual(client.kwargs["messages"][0]["content"], "prompt")
        self.assertEqual(result.observed_provider, "deepseek")

    def test_named_compatible_provider_dispatch(self):
        definition = configuration().providers["lab"]
        client = _ChatClient()
        adapter = build_translation_adapter("lab", "private-model", client=client,
                                            provider_definition=definition)
        result = adapter.generate("prompt", "private-model")
        self.assertEqual(result.observed_provider, "lab")

    def test_missing_credential_fails_without_fallback(self):
        adapter = build_translation_adapter("anthropic", "configured-model")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(OpenAIConfigurationError, "ANTHROPIC_API_KEY"):
                adapter.generate("prompt", "configured-model")

    def test_provider_and_model_change_cache_identity(self):
        kwargs = dict(profile_id="scholarly", pdf_hash="a", source_uri="b", document_id="c",
                      reading_id="d", reading_version=1, reading_text_hash="e", unit_id="f",
                      unit_version=1, source_char_start=0, source_char_end=1, unit_text_hash="g",
                      neighbor_fingerprint="h", policy_fingerprint="i", prompt_version="p",
                      config_version="c", decoding_params={})
        one = compute_cache_key(provider="openai", model="one", **kwargs)
        self.assertNotEqual(one, compute_cache_key(provider="openai", model="two", **kwargs))
        self.assertNotEqual(one, compute_cache_key(provider="anthropic", model="one", **kwargs))

    def test_unpriced_provider_records_usage_but_does_not_cache_or_continue(self):
        with tempfile.TemporaryDirectory() as tmp, ControlStore(Path(tmp) / "controls.sqlite3") as store:
            budget = PersistentBudget(store, "doc", max_calls=2, hard_list_usd=0.01,
                                      stage="translate", provider="claude", model="m")
            cache = RuntimeCache(store, stage="translate", provider="claude", model="m")
            result, hit, notices = cache.execute(
                "identity", "prompt", "m",
                lambda *_: TextGenerationResult("completed", "ok", {"input": 2, "output": 1}, "m", 0),
                stage="translate",
                metadata={"document_id": "doc", "unit_id": "unit", "provider_type": "anthropic"},
                budget=budget,
            )
            self.assertFalse(hit)
            self.assertEqual(result.text, "ok")
            self.assertIn("usage_not_metered_stop", notices)
            self.assertTrue(store.status("doc")["stopped"])
            self.assertEqual(store._conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0], 0)

    def test_named_openai_provider_can_cache_with_requested_identity(self):
        with tempfile.TemporaryDirectory() as tmp, ControlStore(Path(tmp) / "controls.sqlite3") as store:
            budget = PersistentBudget(store, "doc", max_calls=2, hard_list_usd=0.01,
                                      stage="translate", provider="corporate_openai", model="m")
            cache = RuntimeCache(store, stage="translate", provider="corporate_openai", model="m")
            kwargs = dict(stage="translate",
                          metadata={"document_id": "doc", "unit_id": "unit", "provider_type": "openai"},
                          budget=budget)
            call = lambda *_: TextGenerationResult("completed", "ok", {"input": 2, "output": 1}, "m", 0)
            self.assertFalse(cache.execute("identity", "prompt", "m", call, **kwargs)[1])
            self.assertTrue(cache.execute("identity", "prompt", "m", lambda *_: self.fail("cache miss"), **kwargs)[1])


class SessionCRoleIntegrationTests(unittest.TestCase):
    def test_unit_review_resolves_semantic_reviewer_and_records_capabilities(self):
        request = build_unit_review_request_for_role(
            "Source sentence.", "משפט מתורגם.", configuration(), policy="off",
        )
        record = run_unit_review(request)
        self.assertEqual((record["provider"], record["model"]), ("oa", "reviewer-user-id"))
        self.assertEqual(record["provider_type"], "openai")
        self.assertEqual(record["model_capabilities"]["context_window"], 2000)

    def test_candidate_comparison_resolves_candidate_evaluator_provenance(self):
        request = build_candidate_comparison_request_for_role(
            "Source sentence.", {"A": "תרגום א.", "B": "תרגום ב."}, configuration(),
        )
        response = (
            "MATERIAL_DIFFERENCES:\nnone\n"
            "CANDIDATE_ASSESSMENTS:\nA: supported\nB: supported\n"
            "BEST_SUPPORTED_TRANSLATION:\nNO_CLEAR_WINNER\n"
            "REASON:\nequivalent\nUNCERTAINTIES:\nnone\n"
        )
        record = run_candidate_comparison(
            request, lambda *_: TextGenerationResult(
                "completed", response, {"input": 2, "output": 1}, "eval-user-id", 0,
                observed_provider="lab",
            ),
        )
        self.assertEqual((record["provider"], record["model"]), ("lab", "eval-user-id"))
        self.assertEqual(record["call"]["observed_provider"], "lab")
        self.assertEqual(record["call"]["estimated_cost_usd"], "not_metered")

    def test_chapter_qa_resolves_chapter_role_without_call_when_off(self):
        request = build_chapter_qa_request_for_role(
            "Chapter source.", "טקסט פרק.", configuration(), policy="off",
        )
        record = run_chapter_qa(request)
        self.assertEqual((record["provider"], record["model"]), ("ds", "qa-user-id"))
        self.assertEqual(record["provider_type"], "deepseek")
        self.assertEqual(record["status"], "skipped")
