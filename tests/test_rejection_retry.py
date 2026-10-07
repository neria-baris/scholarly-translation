"""Automatic resend only after an explicit unprocessed provider rejection (HTTP 429/5xx
before any output) or a connection that never opened. Ambiguous failures (dropped
connection, read timeout, mid-stream) are never resent."""
import unittest
from types import SimpleNamespace

from scholarly_translation.model_adapter import (
    AnthropicTextGenerationAdapter, OpenAITextGenerationAdapter, REJECTION_RETRY_DELAYS,
)


def not_connected(name="ConnectError"):
    """An SDK connection error caused by an httpx error that never opened a connection."""
    cause = type(name, (Exception,), {"__module__": "httpx"})("connect failed")
    error = type("APIConnectionError", (Exception,), {})("Connection error.")
    error.__cause__ = cause
    return error


class StatusError(Exception):
    def __init__(self, status_code, retry_after=None):
        super().__init__("status %d" % status_code)
        self.status_code = status_code
        self.response = SimpleNamespace(headers={"retry-after": retry_after} if retry_after else {})


def openai_response():
    return SimpleNamespace(status="completed", output_text="שלום", model="gpt-6-luna", usage=SimpleNamespace(
        input_tokens=10, output_tokens=5, input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0),
        output_tokens_details=SimpleNamespace(reasoning_tokens=0)))


class Scripted:
    """Raises/returns the scripted outcomes in order and counts sends."""
    def __init__(self, *outcomes):
        self.outcomes, self.sent = list(outcomes), 0

    def __call__(self, **payload):
        self.sent += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class RejectionRetryTests(unittest.TestCase):
    def adapter(self, *outcomes, max_output_tokens=1000):
        self.create = Scripted(*outcomes)
        adapter = OpenAITextGenerationAdapter(client=SimpleNamespace(responses=SimpleNamespace(create=self.create)),
                                              max_output_tokens=max_output_tokens)
        self.slept = []
        adapter._sleep = self.slept.append
        return adapter

    def test_rate_limit_and_overload_are_resent_with_backoff(self):
        result = self.adapter(StatusError(429), StatusError(503), openai_response()).generate("p", "gpt-6-luna")
        self.assertEqual(result.status, "completed")
        self.assertEqual(self.create.sent, 3)
        self.assertEqual(self.slept, list(REJECTION_RETRY_DELAYS[:2]))

    def test_retry_after_header_is_honoured_within_bound(self):
        self.adapter(StatusError(429, retry_after="30"), openai_response()).generate("p", "gpt-6-luna")
        self.assertEqual(self.slept, [30.0])
        self.adapter(StatusError(429, retry_after="9999"), openai_response()).generate("p", "gpt-6-luna")
        self.assertEqual(self.slept, [REJECTION_RETRY_DELAYS[0]])

    def test_gives_up_after_bounded_attempts(self):
        rejections = [StatusError(429) for _ in range(len(REJECTION_RETRY_DELAYS) + 1)]
        result = self.adapter(*rejections).generate("p", "gpt-6-luna")
        self.assertEqual(result.status, "failed_transport")
        self.assertEqual(self.create.sent, len(REJECTION_RETRY_DELAYS) + 1)

    def test_ambiguous_and_client_errors_are_never_resent(self):
        for error in (ConnectionError("reset"), TimeoutError("read"), StatusError(400), StatusError(401)):
            result = self.adapter(error, openai_response()).generate("p", "gpt-6-luna")
            self.assertEqual(result.status, "failed_transport")
            self.assertEqual(self.create.sent, 1, error)
            self.assertEqual(self.slept, [])

    def test_connection_that_never_opened_is_resent(self):
        for name in ("ConnectError", "ConnectTimeout"):
            result = self.adapter(not_connected(name), openai_response()).generate("p", "gpt-6-luna")
            self.assertEqual(result.status, "completed", name)
            self.assertEqual((self.create.sent, self.slept), (2, [REJECTION_RETRY_DELAYS[0]]))

    def test_dropped_connection_is_not_resent_and_names_the_error(self):
        result = self.adapter(not_connected("ReadError"), openai_response()).generate("p", "gpt-6-luna")
        self.assertEqual((result.status, self.create.sent), ("failed_transport", 1))
        self.assertIn("transport or timeout: APIConnectionError <- ReadError", result.error)

    def test_stream_failure_after_output_started_is_not_resent(self):
        sent = []

        class Stream:
            def __enter__(self):
                sent.append(1)
                return self

            def __exit__(self, *exc):
                return False

            def __iter__(self):
                yield "first event"
                raise StatusError(503)

        client = SimpleNamespace(responses=SimpleNamespace(stream=lambda **payload: Stream(), create=None))
        adapter = OpenAITextGenerationAdapter(client=client, max_output_tokens=16384)
        adapter._sleep = lambda delay: self.fail("must not wait to resend")
        self.assertEqual(adapter.generate("p", "gpt-6-luna").status, "failed_transport")
        self.assertEqual(len(sent), 1)

    def test_anthropic_overloaded_is_resent(self):
        create = Scripted(StatusError(529), SimpleNamespace(
            content=[SimpleNamespace(text="שלום")], model="claude-sonnet-5-5", stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0,
                                  cache_creation_input_tokens=0, cache_creation=None)))
        adapter = AnthropicTextGenerationAdapter(client=SimpleNamespace(messages=SimpleNamespace(create=create)),
                                                 max_output_tokens=1000)
        adapter._sleep = lambda delay: None
        self.assertEqual(adapter.generate("p", "claude-sonnet-5-5").status, "completed")
        self.assertEqual(create.sent, 2)


if __name__ == "__main__":
    unittest.main()
