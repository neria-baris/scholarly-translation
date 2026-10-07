"""Opt-in persistent API keys ("remember on this computer").

HTTP tests use an in-memory store; the Windows Credential Manager round trip
uses a unique test-only target prefix and removes what it writes. No network
or provider call is made here.
"""
import json
import os
import secrets
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scholarly_translation import web_ui
from scholarly_translation.key_store import WindowsCredentialStore


class MemoryStore:
    def __init__(self, initial=None):
        self.keys = dict(initial or {})

    def load_all(self):
        return dict(self.keys)

    def save(self, provider_id, key):
        self.keys[provider_id] = key

    def delete(self, provider_id):
        self.keys.pop(provider_id, None)


class FailingStore(MemoryStore):
    def load_all(self):
        raise OSError("unavailable")

    def save(self, provider_id, key):
        raise OSError("מנהל האישורים של Windows: שמירה נכשלה (קוד 5).")


class RememberKeysHTTPTests(unittest.TestCase):
    def start(self, store):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), web_ui.make_handler("test-token", key_store=store))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self.thread.join)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def setUp(self):
        env = patch.dict(os.environ, {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""})
        env.start()
        self.addCleanup(env.stop)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        output = patch.object(web_ui, "OUTPUT_ROOT", Path(temp.name))
        output.start()
        self.addCleanup(output.stop)

    def post(self, route, payload):
        request = Request(self.url + route, data=json.dumps(payload).encode("utf-8"), method="POST",
                          headers={"Content-Type": "application/json", "X-UI-Token": "test-token", "Origin": self.url})
        with urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
        return json.loads(body), body

    def test_saved_key_is_available_after_restart_and_never_echoed(self):
        secret = "sk-remembered-" + secrets.token_hex(8)
        self.start(MemoryStore({"openai": secret}))
        config, body = self.post("/document-config", {})
        self.assertNotIn(secret, body)
        self.assertTrue(config["key_providers_available"]["openai"])
        self.assertEqual(config["key_providers_saved"], {"openai": True})
        self.assertTrue(config["key_remember_supported"])
        self.assertFalse(any(secret in value for value in os.environ.values()))

    def test_remember_saves_and_plain_save_does_not(self):
        store = MemoryStore()
        self.start(store)
        secret = "sk-new-" + secrets.token_hex(8)
        result, body = self.post("/model-keys", {"keys": {"openai": secret}, "remember": True})
        self.assertNotIn(secret, body)
        self.assertEqual(store.keys, {"openai": secret})
        self.assertEqual(result["saved"], {"openai": True})
        self.assertTrue(result["remember_supported"])
        result, _ = self.post("/model-keys", {"keys": {"anthropic": "sk-ant-session"}, "remember": False})
        self.assertNotIn("anthropic", store.keys)
        self.assertTrue(result["available"]["anthropic"])
        self.assertNotIn("anthropic", result["saved"])

    def test_replacing_without_remember_removes_the_stale_saved_key(self):
        store = MemoryStore({"openai": "sk-old"})
        self.start(store)
        result, _ = self.post("/model-keys", {"keys": {"openai": "sk-replacement"}})
        self.assertEqual(store.keys, {})
        self.assertEqual(result["saved"], {})
        self.assertTrue(result["available"]["openai"])

    def test_clearing_a_key_deletes_it_from_the_store(self):
        store = MemoryStore({"openai": "sk-old"})
        self.start(store)
        result, _ = self.post("/model-keys", {"keys": {"openai": ""}})
        self.assertEqual(store.keys, {})
        self.assertNotIn("openai", result["available"])

    def test_forget_saved_keeps_the_key_for_this_run(self):
        store = MemoryStore({"openai": "sk-old", "anthropic": "sk-ant-old"})
        self.start(store)
        result, _ = self.post("/model-keys", {"forget_saved": True})
        self.assertEqual(store.keys, {})
        self.assertEqual(result["saved"], {})
        self.assertTrue(result["available"]["openai"])
        self.assertTrue(result["available"]["anthropic"])

    def test_without_a_store_remember_is_unsupported_and_memory_only(self):
        self.start(None)
        result, _ = self.post("/model-keys", {"keys": {"openai": "sk-x"}, "remember": True})
        self.assertFalse(result["remember_supported"])
        self.assertEqual(result["saved"], {})
        self.assertTrue(result["available"]["openai"])
        config, _ = self.post("/document-config", {})
        self.assertFalse(config["key_remember_supported"])

    def test_invalid_remember_value_is_rejected(self):
        store = MemoryStore()
        self.start(store)
        with self.assertRaises(HTTPError) as caught:
            self.post("/model-keys", {"keys": {"openai": "sk-x"}, "remember": "yes"})
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(store.keys, {})

    def test_store_failures_do_not_break_the_server_or_keep_a_half_saved_key(self):
        self.start(FailingStore())
        with self.assertRaises(HTTPError) as caught:
            self.post("/model-keys", {"keys": {"openai": "sk-secret-value"}, "remember": True})
        self.assertEqual(caught.exception.code, 400)
        body = caught.exception.read().decode("utf-8")
        self.assertIn("מנהל האישורים", body)
        self.assertNotIn("sk-secret-value", body)
        result, _ = self.post("/model-keys", {})
        self.assertNotIn("openai", result["available"])

    def test_keys_from_the_environment_are_reported_as_external(self):
        self.start(MemoryStore({"anthropic": "sk-ant-saved"}))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env-value"}):
            config, body = self.post("/document-config", {})
            result, _ = self.post("/model-keys", {})
        self.assertNotIn("sk-env-value", body)
        self.assertEqual(config["key_providers_external"], {"openai": True})
        self.assertEqual(result["external"], {"openai": True})
        self.assertEqual(result["saved"], {"anthropic": True})
        result, _ = self.post("/model-keys", {"keys": {"openai": "sk-typed"}})
        self.assertEqual(result["external"], {})

    def test_invalid_stored_entries_are_ignored(self):
        self.start(MemoryStore({"Bad ID": "sk-a", "openai": "sk-a\nb", "anthropic": "  "}))
        result, _ = self.post("/model-keys", {})
        self.assertEqual(result["available"], {})
        self.assertEqual(result["saved"], {})


@unittest.skipUnless(sys.platform == "win32", "Windows Credential Manager only")
class WindowsCredentialStoreTests(unittest.TestCase):
    def test_round_trip_with_a_test_only_prefix(self):
        store = WindowsCredentialStore(prefix=f"ScholarlyTranslationTest/{secrets.token_hex(6)}/")
        self.addCleanup(lambda: [store.delete(pid) for pid in list(store.load_all())])
        self.assertEqual(store.load_all(), {})
        store.save("openai", "sk-test-שלום")
        store.save("anthropic", "sk-ant-test")
        self.assertEqual(store.load_all(), {"openai": "sk-test-שלום", "anthropic": "sk-ant-test"})
        store.save("openai", "sk-test-2")
        self.assertEqual(store.load_all()["openai"], "sk-test-2")
        store.delete("openai")
        store.delete("openai")  # deleting a missing entry is not an error
        self.assertEqual(store.load_all(), {"anthropic": "sk-ant-test"})


if __name__ == "__main__":
    unittest.main()
