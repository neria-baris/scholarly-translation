import hashlib
import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

from scholarly_translation.__main__ import cmd_probe_provider
from scholarly_translation.model_adapter import (
    DiagnosticRequest,
    OpenAIConfigurationError,
    OpenAIDiagnosticAdapter,
    MockDiagnosticAdapter,
    RequestValidationError,
    SYNTHETIC_MARKER,
    build_adapter,
    compute_estimate,
)

SOURCE_TEXT = "Fixed synthetic diagnostic phrase."
SOURCE_HASH = hashlib.sha256(SOURCE_TEXT.encode("utf-8")).hexdigest()


def make_request(**overrides):
    fields = dict(
        request_id="req-1",
        profile_id="scholarly",
        marker=SYNTHETIC_MARKER,
        source_language="en",
        target_language="he",
        source_text=SOURCE_TEXT,
        source_sha256=SOURCE_HASH,
        prompt_version="gate6-v1",
        config_version="gate6-v1",
        provider="mock",
        model="mock-diagnostic-1",
    )
    fields.update(overrides)
    return DiagnosticRequest(**fields)


class DiagnosticRequestTests(unittest.TestCase):
    def test_valid_request_constructs(self):
        request = make_request()
        self.assertEqual(request.profile_id, "scholarly")

    def test_wrong_profile_rejected(self):
        with self.assertRaises(RequestValidationError):
            make_request(profile_id="other")

    def test_wrong_marker_rejected(self):
        with self.assertRaises(RequestValidationError):
            make_request(marker="not-the-marker")

    def test_wrong_target_language_rejected(self):
        with self.assertRaises(RequestValidationError):
            make_request(target_language="en")

    def test_mismatched_hash_rejected(self):
        with self.assertRaises(RequestValidationError):
            make_request(source_sha256="0" * 64)

    def test_oversized_text_rejected(self):
        with self.assertRaises(RequestValidationError):
            long_text = "a" * 2001
            make_request(source_text=long_text, source_sha256=hashlib.sha256(long_text.encode()).hexdigest())

    def test_unsupported_provider_rejected(self):
        with self.assertRaises(RequestValidationError):
            make_request(provider="anthropic", model="mock-diagnostic-1")

    def test_unsupported_model_rejected(self):
        with self.assertRaises(RequestValidationError):
            make_request(provider="mock", model="not-a-model")

    def test_empty_request_id_rejected(self):
        with self.assertRaises(RequestValidationError):
            make_request(request_id="")

    def test_error_message_excludes_source_text(self):
        try:
            make_request(profile_id="other")
        except RequestValidationError as exc:
            self.assertNotIn(SOURCE_TEXT, str(exc))


class MockAdapterTests(unittest.TestCase):
    def test_mock_is_deterministic_placeholder_and_unbilled(self):
        request = make_request()
        result = MockDiagnosticAdapter().run(request)
        self.assertEqual(result.status, "mock_placeholder")
        self.assertIn("[GATE6-MOCK-PLACEHOLDER]", result.response_text)
        self.assertIn(SOURCE_TEXT, result.response_text)
        self.assertEqual(result.token_usage, "not_metered")
        self.assertEqual(result.actual_charge, "not_metered")
        self.assertFalse(result.approved)

    def test_build_adapter_mock(self):
        adapter = build_adapter("mock", "mock-diagnostic-1")
        self.assertIsInstance(adapter, MockDiagnosticAdapter)

    def test_build_adapter_rejects_unsupported(self):
        with self.assertRaises(RequestValidationError):
            build_adapter("anthropic", "claude")


class PricingEstimateTests(unittest.TestCase):
    def test_missing_usage_not_metered(self):
        self.assertEqual(compute_estimate("not_metered"), "not_metered")

    def test_empty_dict_not_metered(self):
        self.assertEqual(compute_estimate({}), "not_metered")

    def test_negative_field_not_metered(self):
        self.assertEqual(compute_estimate({"input": -1}), "not_metered")

    def test_non_numeric_field_not_metered(self):
        self.assertEqual(compute_estimate({"input": "lots"}), "not_metered")

    def test_bool_field_not_metered(self):
        self.assertEqual(compute_estimate({"input": True}), "not_metered")

    def test_valid_usage_computes_expected_cost(self):
        usage = {"input": 3_000_000, "output": 1_000_000, "cached": 1_000_000, "cache_write": 1_000_000}
        # Input total includes both cached and cache-write tokens.
        self.assertAlmostEqual(compute_estimate(usage), 0.735)

    def test_cached_tokens_are_not_charged_twice(self):
        self.assertAlmostEqual(compute_estimate({"input": 1_000_000, "output": 0, "cached": 1_000_000}), 0.01)

    def test_missing_required_usage_is_not_metered(self):
        self.assertEqual(compute_estimate({"input": 10}), "not_metered")

    def test_subtoken_count_exceeding_input_is_not_metered(self):
        self.assertEqual(compute_estimate({"input": 10, "output": 1, "cached": 11}), "not_metered")

    def test_wrong_pricing_version_not_metered(self):
        self.assertEqual(compute_estimate({"input": 1}, pricing_version="1999-01-01"), "not_metered")


class FakeResponses:
    def __init__(self, response=None, exc=None, captured=None):
        self._response = response
        self._exc = exc
        self._captured = captured

    def create(self, **kwargs):
        if self._captured is not None:
            self._captured.update(kwargs)
        if self._exc is not None:
            raise self._exc
        return self._response


class FakeClient:
    def __init__(self, response=None, exc=None, captured=None):
        self.responses = FakeResponses(response=response, exc=exc, captured=captured)


def make_usage(input_tokens=10, output_tokens=5, cached=0, reasoning=0, cache_write=0):
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_tokens_details=SimpleNamespace(cached_tokens=cached, cache_write_tokens=cache_write),
        output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
    )


class OpenAIAdapterFakeClientTests(unittest.TestCase):
    def test_successful_call_shape_and_exact_request_params(self):
        captured = {}
        response = SimpleNamespace(status="completed", output_text="hello world", usage=make_usage())
        client = FakeClient(response=response, captured=captured)
        request = make_request(provider="openai", model="gpt-6-luna")
        adapter = OpenAIDiagnosticAdapter(client=client)

        result = adapter.run(request)

        self.assertEqual(result.status, "completed_unapproved")
        self.assertEqual(result.response_text, "hello world")
        self.assertEqual(result.token_usage, {"input": 10, "output": 5, "cached": 0, "cache_write": 0, "reasoning": 0})
        self.assertFalse(result.approved)
        self.assertEqual(result.actual_charge, "unknown")

        self.assertEqual(captured["model"], "gpt-6-luna")
        self.assertEqual(captured["store"], False)
        self.assertEqual(captured["tools"], [])
        self.assertEqual(captured["reasoning"], {"effort": "none"})
        self.assertEqual(captured["max_output_tokens"], 256)

    def test_empty_response_text_is_explicit_failure(self):
        response = SimpleNamespace(status="completed", output_text="", usage=make_usage())
        client = FakeClient(response=response)
        request = make_request(provider="openai", model="gpt-6-luna")
        result = OpenAIDiagnosticAdapter(client=client).run(request)
        self.assertEqual(result.status, "failed_empty_response")
        self.assertFalse(result.approved)
        self.assertIsNone(result.response_text)

    def test_incomplete_response_with_text_is_failure(self):
        response = SimpleNamespace(status="incomplete", output_text="partial", usage=make_usage())
        request = make_request(provider="openai", model="gpt-6-luna")
        result = OpenAIDiagnosticAdapter(client=FakeClient(response=response)).run(request)
        self.assertEqual(result.status, "failed_empty_response")
        self.assertIsNone(result.response_text)

    def test_transport_exception_is_sanitized_failure(self):
        client = FakeClient(exc=TimeoutError("boom: secret-detail"))
        request = make_request(provider="openai", model="gpt-6-luna")
        result = OpenAIDiagnosticAdapter(client=client).run(request)
        self.assertEqual(result.status, "failed_transport")
        self.assertFalse(result.approved)
        self.assertNotIn("secret-detail", result.error or "")

    def test_missing_usage_is_not_metered(self):
        response = SimpleNamespace(status="completed", output_text="hi", usage=None)
        client = FakeClient(response=response)
        request = make_request(provider="openai", model="gpt-6-luna")
        result = OpenAIDiagnosticAdapter(client=client).run(request)
        self.assertEqual(result.token_usage, "not_metered")
        self.assertEqual(result.estimated_cost_usd, "not_metered")

    def test_no_key_no_sdk_no_network_attempt(self):
        adapter = OpenAIDiagnosticAdapter(client=None)
        request = make_request(provider="openai", model="gpt-6-luna")
        with unittest.mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(OpenAIConfigurationError):
                adapter.run(request)


class ProbeProviderCLITests(unittest.TestCase):
    def test_mock_round_trip_writes_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "probe"
            rc = cmd_probe_provider("mock", str(out_dir))
            self.assertEqual(rc, 0)
            result_path = out_dir / "probe_result.json"
            self.assertTrue(result_path.exists())
            data = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "mock_placeholder")
            self.assertFalse(data["approved"])
            self.assertNotIn("OPENAI_API_KEY", json.dumps(data))

    def test_refuses_to_overwrite_existing_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "probe"
            self.assertEqual(cmd_probe_provider("mock", str(out_dir)), 0)
            rc = cmd_probe_provider("mock", str(out_dir))
            self.assertEqual(rc, 1)

    def test_unwritable_output_shape_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "file-instead-of-directory"
            out_path.write_text("evidence", encoding="utf-8")
            self.assertEqual(cmd_probe_provider("mock", str(out_path)), 1)
            self.assertEqual(out_path.read_text(encoding="utf-8"), "evidence")

    def test_openai_refuses_without_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "probe"
            with unittest.mock.patch.dict("os.environ", {}, clear=True):
                rc = cmd_probe_provider("openai", str(out_dir))
            self.assertEqual(rc, 1)
            self.assertFalse((out_dir / "probe_result.json").exists())

    def test_unsafe_output_path_rejected(self):
        package_dir = Path(__file__).resolve().parents[1] / "scholarly_translation"
        rc = cmd_probe_provider("mock", str(package_dir))
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
