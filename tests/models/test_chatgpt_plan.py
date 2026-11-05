import unittest
from types import SimpleNamespace

from scholarly_translation.account.openai_auth import OpenAISignedOut, OpenAISignInError
from scholarly_translation.models.adapter import (
    CacheablePrompt,
    ImagePrompt,
    OpenAIConfigurationError,
    RequestValidationError,
    TextGenerationAdapter,
    TextGenerationResult,
)
from scholarly_translation.models.chatgpt_plan import (
    ChatGPTPlanAdapter,
    PLAN_PROVIDER_ID,
    PLAN_RETRY_SECONDS,
    PlanFirstAdapter,
    PlanState,
    PlanUnavailableError,
)


def usage(i=10, o=5):
    return SimpleNamespace(
        input_tokens=i, output_tokens=o,
        input_tokens_details=SimpleNamespace(cached_tokens=0),
        output_tokens_details=SimpleNamespace(reasoning_tokens=0))


def completed_event(text="שלום", status="completed", **extra):
    response = SimpleNamespace(status=status, output_text=text, usage=usage(), model="gpt-6-luna",
                               incomplete_details=None, **extra)
    return SimpleNamespace(type="response.completed" if status == "completed" else "response.incomplete",
                           response=response)


def failed_event(code):
    return SimpleNamespace(type="response.failed",
                           response=SimpleNamespace(error=SimpleNamespace(code=code, message="x")))


class FakeStatusError(Exception):
    def __init__(self, status, code=None, via="body"):
        super().__init__("status error")
        self.status_code = status
        self.body = None
        self.response = None
        if code and via == "body":
            self.body = {"error": {"code": code, "message": "m"}}
        elif code and via == "flat":
            self.body = {"code": code}
        elif code and via == "response":
            self.response = SimpleNamespace(json=lambda: {"error": {"code": code}})


class FakeResponses:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return iter(item)


class FakeClient:
    def __init__(self, script):
        self.responses = FakeResponses(script)


class FakeAccount:
    def __init__(self, tokens=("tok-1", "tok-2", "tok-3")):
        self.tokens = list(tokens)
        self.invalidated = 0
        self.issued = []
        self.error = None

    def access_token(self):
        if self.error:
            raise self.error
        token = self.tokens[min(self.invalidated, len(self.tokens) - 1)]
        self.issued.append(token)
        return token

    def invalidate_access_token(self):
        self.invalidated += 1


def make(script, account=None, **kw):
    account = account or FakeAccount()
    client = FakeClient(script)
    seen = []

    def factory(token):
        seen.append(token)
        return client

    return ChatGPTPlanAdapter(account, client_factory=factory, **kw), client, account, seen


class PlanAdapterTests(unittest.TestCase):
    def test_success_sets_observed_provider_and_payload(self):
        adapter, client, _, seen = make([[SimpleNamespace(type="response.created"), completed_event()]])
        result = adapter.generate("translate this", "gpt-6-luna")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.text, "שלום")
        self.assertEqual(result.observed_provider, PLAN_PROVIDER_ID)
        self.assertEqual(result.observed_model, "gpt-6-luna")
        self.assertEqual(result.token_usage, {"input": 10, "output": 5, "cached": 0, "reasoning": 0})
        self.assertEqual(seen, ["tok-1"])
        call = client.responses.calls[0]
        self.assertIs(call["store"], False)
        self.assertIs(call["stream"], True)
        self.assertEqual(call["input"], "translate this")
        for omitted in ("max_output_tokens", "temperature", "top_p", "metadata", "prompt_cache_options",
                        "prompt_cache_retention", "previous_response_id", "user", "truncation", "tools"):
            self.assertNotIn(omitted, call)

    def test_cacheable_prompt_sent_as_plain_text(self):
        adapter, client, _, _ = make([[completed_event()]])
        adapter.generate(CacheablePrompt("STABLE ", "dynamic"), "gpt-6-luna")
        call = client.responses.calls[0]
        self.assertEqual(call["input"], "STABLE dynamic")
        self.assertNotIn("prompt_cache_options", call)

    def test_image_prompt_sent_as_input_image(self):
        adapter, client, _, _ = make([[completed_event()]])
        adapter.generate(ImagePrompt("read it", b"\x89PNG-bytes"), "gpt-6-luna")
        content = client.responses.calls[0]["input"][0]["content"]
        self.assertEqual(content[0], {"type": "input_text", "text": "read it"})
        self.assertEqual(content[1]["type"], "input_image")
        self.assertTrue(content[1]["image_url"].startswith("data:image/png;base64,"))

    def test_reasoning_from_catalog_or_explicit(self):
        adapter, client, _, _ = make([[completed_event()]])
        adapter.generate("x", "gpt-6-luna")
        self.assertEqual(client.responses.calls[0]["reasoning"], {"effort": "low"})  # Luna's default
        adapter2, client2, _, _ = make([[completed_event()]], reasoning="medium")
        adapter2.generate("x", "gpt-6-luna")
        self.assertEqual(client2.responses.calls[0]["reasoning"], {"effort": "medium"})
        adapter3, _, _, _ = make([], reasoning="bogus")
        with self.assertRaises(RequestValidationError):
            adapter3.generate("x", "gpt-6-luna")

    def test_streamed_deltas_used_when_output_text_missing(self):
        deltas = [SimpleNamespace(type="response.output_text.delta", delta="ab"),
                  SimpleNamespace(type="response.output_text.delta", delta="cd")]
        adapter, _, _, _ = make([deltas + [completed_event(text="")]])
        result = adapter.generate("x", "gpt-6-luna")
        self.assertEqual((result.status, result.text), ("completed", "abcd"))

    def test_truncated_and_empty_results(self):
        incomplete = completed_event("part", status="incomplete")
        incomplete.response.incomplete_details = SimpleNamespace(reason="max_output_tokens")
        adapter, _, _, _ = make([[incomplete]])
        result = adapter.generate("x", "gpt-6-luna")
        self.assertEqual((result.status, result.text), ("failed_truncated", "part"))
        self.assertEqual(result.observed_provider, PLAN_PROVIDER_ID)
        adapter, _, _, _ = make([[completed_event(text="")]])
        self.assertEqual(adapter.generate("x", "gpt-6-luna").status, "failed_empty_response")
        adapter, _, _, _ = make([[completed_event("t", status="incomplete")]])
        self.assertEqual(adapter.generate("x", "gpt-6-luna").status, "failed_empty_response")

    def test_http_error_codes_map_to_reasons(self):
        table = [
            (429, "subscription_sharing_usage_limit_exceeded", "exhausted"),
            (403, "subscription_sharing_user_not_eligible", "not_eligible"),
            (403, "chatpass_v2_scope_not_authorized", "not_eligible"),
            (403, "chatpass_v2_invalid_authorization_context", "not_eligible"),
            (400, "subscription_sharing_unsupported_capability", "unsupported"),
            (503, "subscription_sharing_usage_unavailable", "unavailable"),
            (503, "subscription_sharing_user_unavailable", "unavailable"),
            (503, None, "unavailable"),
        ]
        for status, code, reason in table:
            for via in ("body", "flat", "response"):
                if code is None and via != "body":
                    continue
                with self.subTest(status=status, code=code, via=via):
                    adapter, _, _, _ = make([FakeStatusError(status, code, via)])
                    with self.assertRaises(PlanUnavailableError) as ctx:
                        adapter.generate("x", "gpt-6-luna")
                    self.assertEqual(ctx.exception.reason, reason)
                    self.assertIsInstance(ctx.exception, OpenAIConfigurationError)

    def test_failed_event_codes_map_to_reasons(self):
        for code, reason in (("subscription_sharing_usage_limit_exceeded", "exhausted"),
                             ("subscription_sharing_user_not_eligible", "not_eligible"),
                             ("subscription_sharing_unsupported_capability", "unsupported"),
                             ("subscription_sharing_usage_unavailable", "unavailable")):
            with self.subTest(code):
                adapter, _, _, _ = make([[failed_event(code)]])
                with self.assertRaises(PlanUnavailableError) as ctx:
                    adapter.generate("x", "gpt-6-luna")
                self.assertEqual(ctx.exception.reason, reason)

    def test_mid_stream_failure_after_deltas(self):
        events = [SimpleNamespace(type="response.output_text.delta", delta="par"),
                  failed_event("subscription_sharing_usage_limit_exceeded")]
        adapter, _, _, _ = make([events])
        with self.assertRaises(PlanUnavailableError) as ctx:
            adapter.generate("x", "gpt-6-luna")
        self.assertEqual(ctx.exception.reason, "exhausted")

    def test_unknown_failed_event_is_transport_failure(self):
        adapter, _, _, _ = make([[failed_event("server_error")]])
        result = adapter.generate("x", "gpt-6-luna")
        self.assertEqual(result.status, "failed_transport")
        self.assertEqual(result.observed_provider, PLAN_PROVIDER_ID)

    def test_ordinary_failures_are_failed_transport_without_message_leak(self):
        adapter, _, _, _ = make([RuntimeError("secret prompt text tok-1")])
        result = adapter.generate("x", "gpt-6-luna")
        self.assertEqual(result.status, "failed_transport")
        self.assertNotIn("tok-1", result.error)
        self.assertNotIn("secret", result.error)
        adapter, _, _, _ = make([[SimpleNamespace(type="response.created")]])  # stream ends early
        self.assertEqual(adapter.generate("x", "gpt-6-luna").status, "failed_transport")
        adapter, _, _, _ = make([FakeStatusError(500)])
        self.assertEqual(adapter.generate("x", "gpt-6-luna").status, "failed_transport")

    def test_401_invalidates_refreshes_and_retries_once(self):
        adapter, client, account, seen = make([FakeStatusError(401), [completed_event()]])
        result = adapter.generate("x", "gpt-6-luna")
        self.assertEqual(result.status, "completed")
        self.assertEqual(account.invalidated, 1)
        self.assertEqual(seen, ["tok-1", "tok-2"])
        self.assertEqual(len(client.responses.calls), 2)

    def test_second_401_is_temporary_unavailable(self):
        adapter, client, account, _ = make([FakeStatusError(401), FakeStatusError(401)])
        with self.assertRaises(PlanUnavailableError) as ctx:
            adapter.generate("x", "gpt-6-luna")
        self.assertEqual(ctx.exception.reason, "unavailable")
        self.assertEqual(len(client.responses.calls), 2)

    def test_invalid_user_code_triggers_refresh(self):
        adapter, _, account, _ = make([FakeStatusError(403, "subscription_sharing_invalid_user"),
                                       [completed_event()]])
        self.assertEqual(adapter.generate("x", "gpt-6-luna").status, "completed")
        self.assertEqual(account.invalidated, 1)

    def test_signed_out_and_refresh_failure(self):
        account = FakeAccount()
        account.error = OpenAISignedOut("gone")
        adapter, client, _, _ = make([], account=account)
        with self.assertRaises(PlanUnavailableError) as ctx:
            adapter.generate("x", "gpt-6-luna")
        self.assertEqual(ctx.exception.reason, "signed_out")
        self.assertEqual(client.responses.calls, [])
        account.error = OpenAISignInError("refresh_failed")
        with self.assertRaises(PlanUnavailableError) as ctx:
            adapter.generate("x", "gpt-6-luna")
        self.assertEqual(ctx.exception.reason, "unavailable")

    def test_error_messages_are_hebrew_and_token_free(self):
        for reason in ("exhausted", "not_eligible", "signed_out", "unsupported", "unavailable"):
            text = str(PlanUnavailableError(reason))
            self.assertTrue(any("א" <= ch <= "ת" for ch in text), reason)
            self.assertNotIn("tok", text)

    def test_default_client_built_lazily_with_sdk_settings(self):
        import sys
        from unittest import mock
        built = {}

        class FakeOpenAI:
            def __init__(self, **kwargs):
                built.update(kwargs)
                self.responses = FakeResponses([[completed_event()]])

        with mock.patch.dict(sys.modules, {"openai": SimpleNamespace(OpenAI=FakeOpenAI)}):
            adapter = ChatGPTPlanAdapter(FakeAccount())
            self.assertEqual(adapter.generate("x", "gpt-6-luna").status, "completed")
        self.assertEqual(built["api_key"], "tok-1")
        self.assertEqual(built["base_url"], "https://api.openai.com/v1")
        self.assertEqual(built["max_retries"], 0)
        self.assertIn("timeout", built)


class FakeClock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


class StubAdapter(TextGenerationAdapter):
    def __init__(self, outcomes, provider="openai"):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.provider = provider

    def generate(self, prompt_text, model):
        self.calls += 1
        item = self.outcomes.pop(0) if self.outcomes else "ok"
        if isinstance(item, Exception):
            raise item
        return TextGenerationResult("completed", item, {"input": 1, "output": 1}, model, 0.0,
                                    observed_provider=self.provider)


class PlanFirstTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.state = PlanState(clock=self.clock)

    def build(self, plan_outcomes, key_outcomes=(), fallback=True, auto=True):
        self.plan = StubAdapter(plan_outcomes, provider=PLAN_PROVIDER_ID)
        self.key = StubAdapter(key_outcomes) if fallback else None
        return PlanFirstAdapter(self.plan, self.state, fallback_adapter=self.key, auto_fallback=auto)

    def test_ready_uses_plan(self):
        adapter = self.build(["plan text"])
        result = adapter.generate("p", "m")
        self.assertEqual((result.text, result.observed_provider), ("plan text", PLAN_PROVIDER_ID))
        self.assertEqual(self.key.calls, 0)
        snap = self.state.snapshot()
        self.assertEqual((snap["state"], snap["fallback_calls"]), ("ready", 0))

    def test_exhausted_falls_back_counts_pauses_and_retries(self):
        adapter = self.build([PlanUnavailableError("exhausted"), "plan again"], ["key 1", "key 2"])
        first = adapter.generate("p", "m")
        self.assertEqual((first.text, first.observed_provider), ("key 1", "openai"))
        snap = self.state.snapshot()
        self.assertEqual((snap["state"], snap["fallback_calls"]), ("exhausted", 1))
        self.assertIsNotNone(snap["since"])
        self.assertIsNotNone(snap["retry_at"])
        self.assertIsNotNone(snap["last_fallback_at"])
        # inside the pause the plan is not tried
        self.clock.now += PLAN_RETRY_SECONDS - 1
        self.assertEqual(adapter.generate("p", "m").text, "key 2")
        self.assertEqual(self.plan.calls, 1)
        self.assertEqual(self.state.snapshot()["fallback_calls"], 2)
        # after the pause the plan is tried again and success returns to ready
        self.clock.now += 2
        again = adapter.generate("p", "m")
        self.assertEqual(again.observed_provider, PLAN_PROVIDER_ID)
        self.assertEqual(self.plan.calls, 2)
        snap = self.state.snapshot()
        self.assertEqual((snap["state"], snap["retry_at"]), ("ready", None))
        self.assertEqual(snap["fallback_calls"], 2)

    def test_retry_that_is_still_exhausted_pauses_again(self):
        adapter = self.build([PlanUnavailableError("exhausted"), PlanUnavailableError("exhausted")],
                             ["k1", "k2", "k3"])
        adapter.generate("p", "m")
        self.clock.now += PLAN_RETRY_SECONDS + 1
        adapter.generate("p", "m")
        self.assertEqual(self.plan.calls, 2)
        adapter.generate("p", "m")
        self.assertEqual(self.plan.calls, 2)

    def test_auto_fallback_off_raises(self):
        adapter = self.build([PlanUnavailableError("exhausted")], auto=False)
        with self.assertRaises(PlanUnavailableError) as ctx:
            adapter.generate("p", "m")
        self.assertEqual(ctx.exception.reason, "exhausted")
        self.assertEqual(self.key.calls, 0)
        self.assertEqual(self.state.snapshot()["state"], "exhausted")
        self.assertEqual(self.state.snapshot()["fallback_calls"], 0)
        # while paused, still raises a clear plan error without calling the plan
        with self.assertRaises(PlanUnavailableError) as ctx:
            adapter.generate("p", "m")
        self.assertEqual(ctx.exception.reason, "exhausted")
        self.assertEqual(self.plan.calls, 1)

    def test_no_fallback_adapter_raises(self):
        adapter = self.build([PlanUnavailableError("exhausted")], fallback=False)
        with self.assertRaises(PlanUnavailableError):
            adapter.generate("p", "m")

    def test_callable_auto_fallback_setting_is_read_each_call(self):
        flag = {"on": False}
        plan = StubAdapter([PlanUnavailableError("unsupported"), PlanUnavailableError("unsupported")],
                           provider=PLAN_PROVIDER_ID)
        key = StubAdapter(["k"])
        adapter = PlanFirstAdapter(plan, self.state, fallback_adapter=key, auto_fallback=lambda: flag["on"])
        with self.assertRaises(PlanUnavailableError):
            adapter.generate("p", "m")
        flag["on"] = True
        self.assertEqual(adapter.generate("p", "m").text, "k")

    def test_unsupported_falls_back_for_that_call_only(self):
        adapter = self.build([PlanUnavailableError("unsupported"), "plan ok"], ["key"])
        self.assertEqual(adapter.generate("p", "m").text, "key")
        self.assertEqual(self.state.snapshot()["state"], "ready")
        self.assertEqual(adapter.generate("p", "m").observed_provider, PLAN_PROVIDER_ID)
        self.assertEqual(self.state.snapshot()["fallback_calls"], 1)

    def test_unavailable_and_signed_out_fall_back_without_pausing(self):
        adapter = self.build([PlanUnavailableError("unavailable"), PlanUnavailableError("signed_out"), "ok"],
                             ["k1", "k2"])
        adapter.generate("p", "m")
        adapter.generate("p", "m")
        self.assertEqual(self.state.snapshot()["state"], "ready")
        self.assertEqual(adapter.generate("p", "m").observed_provider, PLAN_PROVIDER_ID)

    def test_not_eligible_pauses_until_reset(self):
        adapter = self.build([PlanUnavailableError("not_eligible"), "plan"], ["k1", "k2", "k3"])
        adapter.generate("p", "m")
        self.assertEqual(self.state.snapshot()["state"], "not_eligible")
        self.assertIsNone(self.state.snapshot()["retry_at"])
        self.clock.now += 10 * PLAN_RETRY_SECONDS
        adapter.generate("p", "m")
        self.assertEqual(self.plan.calls, 1)
        self.state.reset()
        self.assertEqual(self.state.snapshot()["state"], "ready")
        self.assertEqual(adapter.generate("p", "m").observed_provider, PLAN_PROVIDER_ID)

    def test_not_eligible_without_fallback_raises_not_eligible(self):
        adapter = self.build([PlanUnavailableError("not_eligible")], fallback=False)
        for _ in range(2):
            with self.assertRaises(PlanUnavailableError) as ctx:
                adapter.generate("p", "m")
            self.assertEqual(ctx.exception.reason, "not_eligible")
        self.assertEqual(self.plan.calls, 1)

    def test_failed_plan_result_is_returned_unchanged_and_state_kept(self):
        class Failing(TextGenerationAdapter):
            def generate(self, prompt_text, model):
                return TextGenerationResult("failed_transport", None, "not_metered", None, 0.0, error="e",
                                            observed_provider=PLAN_PROVIDER_ID)
        self.state.mark_exhausted()
        self.clock.now += PLAN_RETRY_SECONDS + 1
        adapter = PlanFirstAdapter(Failing(), self.state, fallback_adapter=StubAdapter([]))
        self.assertEqual(adapter.generate("p", "m").status, "failed_transport")
        self.assertEqual(self.state.snapshot()["state"], "exhausted")

    def test_fallback_result_returned_unchanged(self):
        adapter = self.build([PlanUnavailableError("exhausted")], ["key text"])
        result = adapter.generate("p", "m")
        self.assertEqual(result.observed_provider, "openai")
        self.assertEqual(result.status, "completed")

    def test_plan_state_reset_clears_pause_but_not_counter(self):
        self.state.mark_exhausted()
        self.state.note_fallback()
        self.state.reset()
        snap = self.state.snapshot()
        self.assertEqual((snap["state"], snap["since"], snap["retry_at"], snap["fallback_calls"]),
                         ("ready", None, None, 1))


if __name__ == "__main__":
    unittest.main()
