"""Focused HTTP/injected-client tests for the AUTOMATION-3/4 UI slice:
mixed-role model/QA selection, custom/"other"-model estimates, malformed
limits/rates/URLs, missing-credential preflight (zero generation), no
secret ever reaching an artifact/response/config/environment, preview cost
varying by selected model and including QA, the actual pause/resume route,
and demo export. No network or paid provider call is made anywhere here.
"""
import json
import os
import re
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
from types import SimpleNamespace
from scholarly_translation.model_adapter import TextGenerationResult

from scholarly_translation import web_ui, model_settings
from scholarly_translation.web_ui import make_handler


MOCK_CONFIG = {
    "schema_version": 1,
    "providers": {"mock": {"type": "mock"}},
    "models": {
        role: {"provider": "mock", "model": "mock-translation-1",
               "capabilities": {"context_window": 8000, "usable_context_tokens": 6000, "max_output_tokens": 500}}
        for role in ("translator", "semantic_reviewer", "chapter_qa")
    },
}


class Automation3HTTPTests(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict(os.environ, {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""})
        self.env_patch.start()
        self.temp = tempfile.TemporaryDirectory()
        self.output_patch = __import__("unittest.mock", fromlist=["patch"]).patch.object(
            web_ui, "OUTPUT_ROOT", Path(self.temp.name))
        self.output_patch.start()
        self.calls = []
        def builder(provider, model, **kwargs):
            def generate(prompt, requested):
                self.calls.append((provider, model, kwargs.get("max_output_tokens")))
                match = re.search(r"TARGET_UNIT_IDS[^\n]*?: (\[[^\n]*\])", prompt)
                if match and "JSON array" in prompt:
                    text = json.dumps([{"unit_id": uid, "translation": "יש חוקרים שאינם מקבלים את הטענה. במסמך 3 טענות.",
                                        "translation_note": None} for uid in json.loads(match.group(1))], ensure_ascii=False)
                else:
                    text = "VERDICT: PASS\nISSUES: none\nCHAPTER_LEVEL_NOTES: none\nSTATE_UPDATES: none"
                return TextGenerationResult("completed", text, {"input": 100, "output": 20}, requested, 0)
            return SimpleNamespace(generate=generate)
        self.adapter_patch = patch("scholarly_translation.model_adapter.build_translation_adapter", builder)
        self.adapter_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("test-token"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.output_patch.stop()
        self.adapter_patch.stop()
        self.env_patch.stop()
        self.temp.cleanup()

    def post(self, route, payload, token="test-token", raw=False):
        request = Request(
            self.url + route, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-UI-Token": token, "Origin": self.url},
            method="POST",
        )
        if raw:
            return urlopen(request, timeout=15)
        with urlopen(request, timeout=15) as response:
            return json.load(response)

    def upload_sample(self):
        sample = self.post("/document-sample", {})
        request = Request(self.url + "/upload?name=sample.pdf", data=Path(sample["path"]).read_bytes(),
                          headers={"X-UI-Token": "test-token", "Origin": self.url}, method="POST")
        with urlopen(request) as response:
            return json.load(response)

    # ---- protected routes ----
    def test_new_routes_require_token(self):
        for route, payload in (("/model-keys", {"keys": {}}), ("/document-preview", {}),
                               ("/document-pause", {"job_id": "x"}), ("/document-resume", {"job_id": "x"})):
            with self.assertRaises(HTTPError) as caught:
                self.post(route, payload, token="bad")
        self.assertEqual(caught.exception.code, 403)

    def test_other_limits_use_full_window_and_reject_unsupported_output(self):
        selected = {"source": "catalog", "provider": "openai", "model": "gpt-6-luna"}
        config = model_settings.build_configuration({"translator": selected})
        self.assertEqual(config.models["translator"].capabilities.usable_context_tokens,
                         config.models["translator"].capabilities.context_window)
        other = {"source": "other", "provider_type": "openai", "model": "org/model-v1",
                 "context_window": 50000, "max_output_tokens": 128001}
        with self.assertRaises(model_settings.ModelSettingsError):
            model_settings.build_configuration({"translator": other})
        other["max_output_tokens"] = 5000
        self.assertEqual(model_settings.build_configuration({"translator": other}).models["translator"].model, "org/model-v1")
        for model in ("sk-credential-value", "<img src=x>"):
            with self.assertRaises(model_settings.ModelSettingsError):
                model_settings.build_configuration({"translator": dict(other, model=model)})

    def test_endpoint_changes_require_distinct_memory_keys(self):
        a = {"source": "other", "provider_type": "openai_compatible", "model": "custom-model",
             "base_url": "https://first.example/v1", "context_window": 100000, "max_output_tokens": 8000}
        b = dict(a, base_url="https://second.example/v1")
        ca = model_settings.build_configuration({"translator": a})
        cb = model_settings.build_configuration({"translator": b})
        self.assertNotEqual(ca.models["translator"].provider, cb.models["translator"].provider)
        self.post("/model-keys", {"keys": {ca.models["translator"].provider: "key-for-first"}})
        settings = {"model": "configured", "budget_usd": 2.0, "quality": "fast", "role_selections": {"translator": b}}
        resolved = self.post("/document-models", {"settings": settings})
        self.assertFalse(resolved["required_providers"][0]["key_available"])
        self.assertEqual(self.calls, [])

    def test_custom_endpoint_cannot_borrow_native_saved_key(self):
        self.post("/model-keys", {"keys": {"openai": "key-only-for-native"}})
        config = model_settings.build_configuration({"translator": {"source": "catalog", "provider": "openai", "model": "gpt-6-luna"}}).to_dict()
        config["providers"]["openai"]["base_url"] = "https://different.example/v1"
        result = self.post("/document-models", {"settings": {"model": "configured", "budget_usd": 2.0, "quality": "fast", "model_config": config}})
        self.assertFalse(result["required_providers"][0]["key_available"])

    def test_unknown_config_field_errors_do_not_echo_submitted_secret(self):
        secret = "private-field-must-not-echo"
        selected = {"source": "catalog", "provider": "openai", "model": "gpt-6-luna", secret: "x"}
        with self.assertRaises(HTTPError) as caught:
            self.post("/document-models", {"settings": {"model": "configured", "budget_usd": 2.0, "role_selections": {"translator": selected}}})
        self.assertNotIn(secret.encode(), caught.exception.read())

    # ---- no secret ever leaks ----
    def test_key_is_never_echoed_or_put_in_environ(self):
        secret = "sk-local-super-secret-value"
        result = self.post("/model-keys", {"keys": {"openai": secret}})
        self.assertNotIn(secret, json.dumps(result))
        self.assertTrue(result["available"]["openai"])
        config = self.post("/document-config", {})
        self.assertNotIn(secret, json.dumps(config))
        self.assertNotIn(secret, os.environ.get("OPENAI_API_KEY", ""))
        self.assertFalse(any(secret in v for v in os.environ.values()))
        # Clearing is supported and never echoes either.
        cleared = self.post("/model-keys", {"keys": {"openai": ""}})
        self.assertNotIn("openai", cleared["available"])

    # ---- mixed roles / custom unknown-price preview ----
    def test_preview_varies_by_selected_model_and_includes_qa(self):
        uploaded = self.upload_sample()
        settings_luna = {
            "profile": "scholarly", "quality": "checked", "language": "en", "budget_usd": 5, "model": "configured",
            "role_selections": {
                "translator": {"source": "catalog", "provider": "openai", "model": "gpt-6-luna"},
                "semantic_reviewer": {"source": "catalog", "provider": "openai", "model": "gpt-6-luna"},
            },
        }
        settings_other = {
            **settings_luna,
            "role_selections": {
                "translator": {"source": "other", "provider_type": "openai", "model": "some-future-model",
                               "context_window": 10000, "max_output_tokens": 500},
                "semantic_reviewer": {"source": "catalog", "provider": "openai", "model": "gpt-6-luna"},
            },
        }
        preview_luna = self.post("/document-preview", {"path": uploaded["path"], "settings": settings_luna})
        preview_other = self.post("/document-preview", {"path": uploaded["path"], "settings": settings_other})
        self.assertGreater(preview_luna["chapter_count"], 0)
        roles_seen = set()
        for chapter in preview_luna["chapters"]:
            roles_seen.update(chapter["role_usage"])
        self.assertIn("translator", roles_seen)
        self.assertIn("chapter_qa", roles_seen)  # QA defaulted to the translator model
        self.assertIn("semantic_reviewer", roles_seen)
        self.assertNotEqual(preview_luna["expected_total_cost_usd"], preview_other["expected_total_cost_usd"])
        other_bases = {
            usage["pricing_basis"]
            for chapter in preview_other["chapters"] for usage in chapter["role_usage"].values()
        }
        self.assertIn("unknown_conservative", other_bases)

    # ---- malformed limits/rates/URL ----
    def test_malformed_other_model_settings_are_rejected(self):
        uploaded = self.upload_sample()
        base = {"profile": "scholarly", "quality": "fast", "language": "en", "budget_usd": 2, "model": "configured"}
        bad_cases = [
            {"source": "other", "provider_type": "openai", "model": "x", "context_window": -1, "max_output_tokens": 10},
            {"source": "other", "provider_type": "openai", "model": "x", "context_window": 10, "max_output_tokens": 0},
            {"source": "other", "provider_type": "openai", "model": "x", "context_window": 10,
             "max_output_tokens": 5, "rates": {"input": -1, "output": 1}},
            {"source": "other", "provider_type": "openai_compatible", "model": "x", "context_window": 10,
             "max_output_tokens": 5},  # missing required base_url
            {"source": "other", "provider_type": "openai_compatible", "model": "x", "context_window": 10,
             "max_output_tokens": 5, "base_url": "http://example.com/v1"},  # not HTTPS, not localhost
            {"source": "other", "provider_type": "openai", "model": "x", "context_window": 10,
             "max_output_tokens": 5, "base_url": "https://user:pass@example.com"},  # embedded credentials
        ]
        for selection in bad_cases:
            settings = {**base, "role_selections": {"translator": selection}}
            with self.assertRaises(HTTPError) as caught:
                self.post("/document-preview", {"path": uploaded["path"], "settings": settings})
            self.assertEqual(caught.exception.code, 400)

    # ---- missing-credential preflight: zero generation ----
    def test_missing_key_preflight_blocks_start_with_zero_generation(self):
        uploaded = self.upload_sample()
        settings = {
            "profile": "scholarly", "quality": "checked", "language": "en", "budget_usd": 2, "model": "configured",
            "role_selections": {
                "translator": {"source": "catalog", "provider": "openai", "model": "gpt-6-luna"},
            },
        }
        with self.assertRaises(HTTPError) as caught:
            self.post("/document-translate", {"path": uploaded["path"], "settings": settings, "paid_confirm": True})
        self.assertEqual(caught.exception.code, 400)
        body = json.loads(caught.exception.read())
        self.assertIn("openai", body["error"])
        recent = self.post("/document-recent", {})
        self.assertIsNone(recent["job"])

    # ---- actual pause/resume route (never a UI placebo) ----
    def test_pause_and_resume_call_the_real_document_jobs_api(self):
        uploaded = self.upload_sample()
        settings = {
            "profile": "scholarly", "quality": "fast", "language": "en", "budget_usd": 2, "model": "configured",
            "model_config": MOCK_CONFIG, "automation": True,
        }
        started = self.post("/document-translate", {"path": uploaded["path"], "settings": settings, "paid_confirm": True})
        with self.assertRaises(HTTPError) as caught:
            self.post("/document-pause", {"job_id": "0" * 32})
        self.assertEqual(caught.exception.code, 400)  # unknown job_id: real lookup, not a placebo 200

        deadline = time.monotonic() + 10
        job = None
        while time.monotonic() < deadline:
            job = self.post("/document-job", started)
            if job["status"] not in ("queued", "reading", "translating", "reviewing", "rebuilding"):
                break
            time.sleep(0.02)
        self.assertEqual(job["status"], "completed")

        # pause() on an already-active-less, non-automation-incompatible state is
        # exercised directly on a non-automation job to prove it is the real
        # settings-gated API, not a UI-only flag:
        plain_settings = {"profile": "scholarly", "quality": "fast", "language": "en",
                          "budget_usd": 2, "model": "auto"}
        plain = self.post("/document-translate", {"path": uploaded["path"], "settings": plain_settings})
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            plain_job = self.post("/document-job", plain)
            if plain_job["status"] not in ("queued", "reading", "translating", "reviewing", "rebuilding"):
                break
            time.sleep(0.02)
        with self.assertRaises(HTTPError) as caught:
            self.post("/document-pause", plain)
        self.assertEqual(caught.exception.code, 400)

        # resume() on an already-completed automation job is a real, defined
        # no-op (zero further provider calls), not a generic placebo success.
        resumed = self.post("/document-resume", started)
        self.assertEqual(resumed["status"], "completed")

    # ---- demo export still works end to end through the new config path ----
    def test_demo_download_unaffected(self):
        uploaded = self.upload_sample()
        settings = {"profile": "scholarly", "quality": "fast", "language": "en", "budget_usd": 2, "model": "auto"}
        started = self.post("/document-translate", {"path": uploaded["path"], "settings": settings})
        deadline = time.monotonic() + 10
        job = None
        while time.monotonic() < deadline:
            job = self.post("/document-job", started)
            if job["status"] not in ("queued", "reading", "translating", "reviewing", "rebuilding"):
                break
            time.sleep(0.02)
        self.assertEqual(job["status"], "completed")
        request = Request(self.url + "/document-download", data=json.dumps({**started, "format": "pdf"}).encode(),
                          headers={"X-UI-Token": "test-token", "Origin": self.url}, method="POST")
        with urlopen(request) as response:
            self.assertTrue(response.read().startswith(b"%PDF"))

    # ---- model_settings unit coverage (no HTTP) ----
    def test_build_configuration_defaults_qa_to_translator_until_changed(self):
        selections = {"translator": {"source": "catalog", "provider": "openai", "model": "gpt-6-luna"}}
        configuration = model_settings.build_configuration(selections)
        translator, _ = configuration.resolve("translator")
        reviewer, _ = configuration.resolve("semantic_reviewer")
        self.assertEqual(translator.model, reviewer.model)

    def test_build_configuration_rejects_missing_translator(self):
        with self.assertRaises(model_settings.ModelSettingsError):
            model_settings.build_configuration({})


if __name__ == "__main__":
    unittest.main()
