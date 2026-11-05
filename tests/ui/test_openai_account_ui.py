"""OPENAI-ACCOUNT builder B: server routes, credential acceptance and adapter wrapping.

Offline: a fake OpenAI account, a fake plan state and fake chatgpt_plan classes
(injected into sys.modules, so the tests do not depend on the backend module)
replace OpenAI. The handler runs on 127.0.0.1:0 in a thread; no network call.
"""
import json
import sys
import tempfile
import threading
import types
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scholarly_translation.ui import web_ui
from scholarly_translation.ui.web_ui import make_handler

ROOT = Path(__file__).resolve().parents[2]
UI_DIR = ROOT / "scholarly_translation" / "ui"
TOKEN = "openai-token"
PLAN_MODULE = "scholarly_translation.models.chatgpt_plan"
SECRET_ACCESS = "access-token-SECRET-123"


class OpenAISignInError(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class FakeOpenAIAccount:
    def __init__(self, signed_in=False, plan_usage=True, email="reader@example.com"):
        self.signed_in, self.plan_usage, self.email = signed_in, plan_usage, email
        self.redirect_uri = None
        self.completed = []
        self.signed_out = 0
        self.fail_with = None

    def status(self):
        return {"available": True, "signed_in": self.signed_in,
                "email": self.email if self.signed_in else None,
                "plan_usage": bool(self.signed_in and self.plan_usage), "access_token": SECRET_ACCESS}

    def begin_sign_in(self, redirect_uri):
        self.redirect_uri = redirect_uri
        return "https://auth.example.test/authorize?state=oa-state", {"state": "oa-state"}

    def complete_sign_in(self, pending, query):
        if self.fail_with:
            raise OpenAISignInError(self.fail_with)
        if query.get("state") != pending["state"]:
            raise OpenAISignInError("state_mismatch")
        self.completed.append(dict(query))
        self.signed_in = True
        return {"email": self.email, "plan_usage": self.plan_usage}

    def sign_out(self):
        self.signed_in = False
        self.signed_out += 1


class FakePlanState:
    def __init__(self):
        self.resets = 0
        self.data = {"state": "ready", "since": None, "retry_at": None, "fallback_calls": 0, "last_fallback_at": None}

    def snapshot(self):
        return dict(self.data)

    def reset(self):
        self.resets += 1


class FakePlanAdapter:
    def __init__(self, account, reasoning=None, **kwargs):
        self.account, self.reasoning = account, reasoning


class FakePlanFirst:
    def __init__(self, plan_adapter, plan_state, fallback_adapter=None, auto_fallback=True):
        self.plan_adapter, self.plan_state = plan_adapter, plan_state
        self.fallback_adapter, self.auto_fallback = fallback_adapter, auto_fallback


def fake_plan_module():
    module = types.ModuleType("scholarly_translation.models.chatgpt_plan")
    module.PlanState = FakePlanState
    module.ChatGPTPlanAdapter = FakePlanAdapter
    module.PlanFirstAdapter = FakePlanFirst
    return module


class _plan_module_missing:
    """Context manager: the plan module cannot be imported (touches only its own sys.modules key)."""

    def __enter__(self):
        self.saved = sys.modules.get(PLAN_MODULE)
        sys.modules[PLAN_MODULE] = None

    def __exit__(self, *exc):
        sys.modules[PLAN_MODULE] = self.saved


class _fake_plan_module_patch:
    def __enter__(self):
        self.saved = sys.modules.get(PLAN_MODULE)
        sys.modules[PLAN_MODULE] = fake_plan_module()

    def __exit__(self, *exc):
        if self.saved is None:
            sys.modules.pop(PLAN_MODULE, None)
        else:
            sys.modules[PLAN_MODULE] = self.saved


class ServerCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for patcher in (
            patch.object(web_ui, "OUTPUT_ROOT", Path(self.temp.name)),
            _fake_plan_module_patch(),
            patch.dict("os.environ", {"OPENAI_API_KEY": ""}),
        ):
            if hasattr(patcher, "start"):
                patcher.start()
                self.addCleanup(patcher.stop)
            else:
                patcher.__enter__()
                self.addCleanup(patcher.__exit__)
        self.account = FakeOpenAIAccount()
        self.plan = FakePlanState()

    def start(self, account_factory="default", plan_state="default"):
        factory = (lambda: self.account) if account_factory == "default" else account_factory
        plan = self.plan if plan_state == "default" else plan_state
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(
            TOKEN, openai_account_factory=factory, plan_state=plan, account_factory=lambda: None))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def post(self, route, payload=None, token=TOKEN):
        headers = {"Content-Type": "application/json", "X-UI-Token": token, "Origin": self.url}
        request = Request(self.url + route, data=json.dumps(payload or {}).encode("utf-8"), headers=headers, method="POST")
        try:
            with urlopen(request, timeout=15) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def get(self, path):
        try:
            with urlopen(self.url + path, timeout=15) as response:
                return response.status, response.read().decode("utf-8")
        except HTTPError as error:
            return error.code, error.read().decode("utf-8")


class RouteTests(ServerCase):
    def test_routes_require_the_ui_token(self):
        self.start()
        for route in ("/openai-account", "/openai-account/sign-in", "/openai-account/sign-out", "/openai-account/settings"):
            self.assertEqual(self.post(route, {}, token="wrong")[0], 403, route)

    def test_status_shape_and_no_token_leak(self):
        self.start()
        status, body = self.post("/openai-account")
        self.assertEqual(status, 200)
        self.assertEqual(set(body), {"account", "plan", "auto_fallback", "key_available"})
        self.assertEqual(body["account"], {"available": True, "signed_in": False, "email": None, "plan_usage": False})
        self.assertIs(body["auto_fallback"], True)
        self.assertIs(body["key_available"], False)
        self.account.signed_in = True
        text = json.dumps(self.post("/openai-account")[1])
        self.assertNotIn(SECRET_ACCESS, text)
        self.assertIn("reader@example.com", text)

    def test_unavailable_without_account_or_module(self):
        self.start(account_factory=lambda: None)
        status, body = self.post("/openai-account")
        self.assertEqual((status, body["account"]), (200, {"available": False}))
        self.assertEqual(self.post("/openai-account/sign-in")[0], 404)

    def test_unavailable_when_plan_module_missing(self):
        with _plan_module_missing():
            self.start()
        self.assertEqual(self.post("/openai-account")[1]["account"], {"available": False})

    def test_factory_exception_degrades(self):
        def boom():
            raise RuntimeError("no store")
        self.start(account_factory=boom)
        self.assertEqual(self.post("/openai-account")[1]["account"], {"available": False})

    def test_sign_in_flow_uses_127_redirect_and_resets_plan_state(self):
        self.start()
        with patch.object(web_ui.webbrowser, "open") as opened:
            status, body = self.post("/openai-account/sign-in")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"url": "https://auth.example.test/authorize?state=oa-state"})
        opened.assert_called_once_with(body["url"])
        self.assertEqual(self.account.redirect_uri, f"{self.url}/openai/callback")
        stray, page = self.get("/openai/callback?state=attacker&code=abc")
        self.assertIn("ההתחברות לא הושלמה", page)
        self.assertEqual(self.account.completed, [])
        good, page = self.get("/openai/callback?state=oa-state&code=zq9code")
        self.assertEqual(good, 200)
        self.assertIn("ההתחברות הושלמה", page)
        self.assertIn("reader@example.com", page)
        self.assertNotIn("zq9code", page)
        self.assertEqual(self.plan.resets, 1)
        self.assertTrue(self.post("/openai-account")[1]["account"]["signed_in"])
        again, page = self.get("/openai/callback?state=oa-state&code=zq9code")
        self.assertIn("ההתחברות לא הושלמה", page)  # the pending sign-in is single use

    def test_callback_without_pending_and_failure_page(self):
        self.start()
        self.assertIn("ההתחברות לא הושלמה", self.get("/openai/callback?state=x&code=y")[1])
        with patch.object(web_ui.webbrowser, "open"):
            self.post("/openai-account/sign-in")
        self.account.fail_with = "access_denied"
        page = self.get("/openai/callback?error=access_denied&state=oa-state")[1]
        self.assertIn("ההתחברות לא הושלמה", page)
        self.assertEqual(self.plan.resets, 0)

    def test_pending_sign_in_expires(self):
        self.start()
        with patch.object(web_ui.webbrowser, "open"):
            self.post("/openai-account/sign-in")
        with patch.object(web_ui, "PENDING_SIGN_IN_SECONDS", -1):
            self.assertIn("ההתחברות לא הושלמה", self.get("/openai/callback?state=oa-state&code=c")[1])
        self.assertEqual(self.account.completed, [])

    def test_callback_does_not_need_token_but_routes_do(self):
        self.start()
        self.assertEqual(self.get("/openai/callback?state=x")[0], 200)

    def test_sign_out_resets(self):
        self.account.signed_in = True
        self.start()
        self.assertEqual(self.post("/openai-account/sign-out"), (200, {"ok": True}))
        self.assertEqual((self.account.signed_out, self.plan.resets), (1, 1))

    def test_settings_persist_in_non_secret_json(self):
        self.start()
        self.assertEqual(self.post("/openai-account/settings", {"auto_fallback": "yes"})[0], 400)
        status, body = self.post("/openai-account/settings", {"auto_fallback": False})
        self.assertEqual((status, body["auto_fallback"]), (200, False))
        saved = json.loads((Path(self.temp.name) / "openai_account.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, {"auto_fallback": False})
        self.stop()
        self.start()  # a new server process keeps the choice
        self.assertIs(self.post("/openai-account")[1]["auto_fallback"], False)

    def test_key_available_reflects_entered_key(self):
        self.start()
        self.post("/model-keys", {"keys": {"openai": "sk-test-key"}})
        self.assertIs(self.post("/openai-account")[1]["key_available"], True)


class CredentialAndAdapterTests(ServerCase):
    SETTINGS = {"model": "configured", "quality": "fast", "language": "en", "budget_usd": 2,
                "role_selections": {"translator": {"source": "catalog", "provider": "openai", "model": "gpt-6-luna"}}}

    def setUp(self):
        super().setUp()
        self.captured = {}
        for patcher in (
            patch("scholarly_translation.translate.document_draft.DocumentJobs.start", new=self._start),
            patch("scholarly_translation.models.adapter.build_translation_adapter", side_effect=self._build),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.built = []

    def _start(self, source, settings, paid_confirm=None, adapter_factory=None):
        self.captured["factory"] = adapter_factory
        return {"job_id": "job-1"}

    def _build(self, provider, model, **kwargs):
        adapter = types.SimpleNamespace(provider=provider, model=model, api_key=kwargs.get("api_key"), kwargs=kwargs)
        self.built.append(adapter)
        return adapter

    def upload(self):
        folder = Path(self.temp.name) / "uploads" / "abc"
        folder.mkdir(parents=True)
        path = folder / "book.pdf"
        path.write_bytes(b"%PDF-1.4 test")
        return str(path)

    def translate(self):
        return self.post("/document-translate", {"path": self.upload(), "settings": self.SETTINGS})

    def factory_adapter(self):
        return self.captured["factory"]("translator", types.SimpleNamespace(max_output_tokens=None))

    def test_no_account_and_no_key_still_demands_key(self):
        self.start(account_factory=lambda: None)
        status, body = self.translate()
        self.assertEqual(status, 400)
        self.assertIn("יש לשמור מפתח API עבור", body["error"])

    def test_signed_in_without_plan_usage_still_demands_key(self):
        self.account.signed_in, self.account.plan_usage = True, False
        self.start()
        self.assertEqual(self.translate()[0], 400)

    def test_plan_granted_replaces_key_requirement_and_wraps_without_key(self):
        self.account.signed_in = True
        self.start()
        status, body = self.translate()
        self.assertEqual((status, body), (200, {"job_id": "job-1"}))
        adapter = self.factory_adapter()
        self.assertIsInstance(adapter, FakePlanFirst)
        self.assertIsInstance(adapter.plan_adapter, FakePlanAdapter)
        self.assertIs(adapter.plan_adapter.account, self.account)
        self.assertIs(adapter.plan_state, self.plan)
        self.assertIsNone(adapter.fallback_adapter)  # no key: nothing to fall back to
        self.assertIs(adapter.auto_fallback(), True)  # a callable: read on every call

    def test_plan_with_key_falls_back_to_the_key_adapter_and_honours_setting(self):
        self.account.signed_in = True
        self.start()
        self.post("/model-keys", {"keys": {"openai": "sk-test-key"}})
        self.post("/openai-account/settings", {"auto_fallback": False})
        self.translate()
        adapter = self.factory_adapter()
        self.assertEqual(adapter.fallback_adapter.api_key, "sk-test-key")
        self.assertIs(adapter.auto_fallback(), False)
        self.post("/openai-account/settings", {"auto_fallback": True})
        self.assertIs(adapter.auto_fallback(), True)  # a change mid-job applies to the next call

    def test_not_signed_in_uses_plain_key_adapter(self):
        self.start()
        self.post("/model-keys", {"keys": {"openai": "sk-test-key"}})
        self.translate()
        adapter = self.factory_adapter()
        self.assertEqual(adapter.api_key, "sk-test-key")
        self.assertNotIsInstance(adapter, FakePlanFirst)

    def test_requirements_and_document_config_report_plan(self):
        self.account.signed_in = True
        self.start()
        config = self.post("/document-config")[1]
        self.assertIs(config["openai_plan_granted"], True)
        self.assertEqual(config["key_providers_available"], {})  # the plan never counts as a key
        models = self.post("/document-models", {"settings": self.SETTINGS})[1]["required_providers"]
        self.assertEqual([(p["key_available"], p["plan_available"]) for p in models], [(False, True)])

    def test_custom_endpoint_is_never_covered_by_the_plan(self):
        self.account.signed_in = True
        self.start()
        settings = dict(self.SETTINGS, role_selections={"translator": {
            "source": "other", "provider_type": "openai", "base_url": "https://llm.example.test/v1",
            "model": "m", "context_window": 8000, "usable_context_tokens": 6000, "max_output_tokens": 1000,
            "rates": {"input": 1, "output": 1}}})
        status, body = self.post("/document-translate", {"path": self.upload(), "settings": settings})
        self.assertEqual(status, 400)
        self.assertIn("יש לשמור מפתח API עבור", body["error"])


class StaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (UI_DIR / "ui.html").read_text(encoding="utf-8")
        cls.js = (UI_DIR / "ui.js").read_text(encoding="utf-8")
        cls.guide = (UI_DIR / "keys_guide.html").read_text(encoding="utf-8")

    def test_card_elements(self):
        for element in ('id="openai-card"', 'id="oa-connect"', 'id="oa-disconnect"', 'id="oa-fallback"',
                        'id="oa-state"', 'id="oa-job-notice"', 'href="https://chatgpt.com/#settings"'):
            self.assertIn(element, self.html)
        self.assertIn("חשבון OpenAI (ChatGPT Plus/Pro)", self.html)
        self.assertIn("כשתקציב החשבון נגמר — להמשיך אוטומטית עם מפתח ה־API", self.html)
        self.assertRegex(self.html, r'id="oa-fallback" type="checkbox" checked')

    def test_js_wiring_uses_routes_and_never_tokens(self):
        for route in ("/openai-account", "/openai-account/sign-in", "/openai-account/sign-out", "/openai-account/settings"):
            self.assertIn("'%s'" % route, self.js)
        self.assertIn("pollOpenAIDuringJob()", self.js)
        self.assertNotIn("access_token", self.js)

    def test_guide_mentions_account_and_fallback(self):
        self.assertIn("Sign in with ChatGPT", self.guide)
        self.assertIn("חשבון OpenAI", self.guide)


if __name__ == "__main__":
    unittest.main()
