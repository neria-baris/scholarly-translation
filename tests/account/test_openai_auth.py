import base64
import hashlib
import json
import threading
import unittest
import urllib.parse

from scholarly_translation.account.openai_auth import (
    DYNAMIC_CLIENT_ID,
    OpenAIAccount,
    OpenAISignInError,
    OpenAISignedOut,
    PLAN_SCOPE,
    SCOPES,
    TOKEN_ENDPOINT,
    REVOKE_ENDPOINT,
)

REDIRECT = "http://127.0.0.1:8765/openai/callback"
SECRETS = ("ACCESS-SECRET-1", "REFRESH-SECRET-1", "ACCESS-SECRET-2", "REFRESH-SECRET-2")


class FakeStore:
    def __init__(self):
        self.record = {}
        self.host = "urn:uuid:11111111-1111-4111-8111-111111111111"
        self.saves = []

    def load(self):
        return json.loads(json.dumps(self.record))

    def save(self, record):
        self.record = json.loads(json.dumps(dict(record)))
        self.saves.append(self.record)

    def host_id(self):
        return self.host


def jwt(claims):
    def enc(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
    return enc({"alg": "RS256"}) + "." + enc(claims) + ".sig"


class Clock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.responses = []

    def __call__(self, method, url, form=None):
        self.calls.append((method, url, dict(form or {})))
        if self.responses:
            item = self.responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return 200, {}


def query_of(url):
    return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(url).query).items()}


class Base(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.transport = FakeTransport()
        self.clock = Clock()
        self.account = OpenAIAccount(self.store, self.transport, self.clock)

    def token_response(self, pending, scope=SCOPES, client_id="oaiapp_issued", access="ACCESS-SECRET-1",
                       refresh="REFRESH-SECRET-1", **claim_overrides):
        claims = {"iss": "https://auth.openai.com", "aud": client_id, "exp": self.clock.now + 600,
                  "nonce": pending.nonce, "sub": "user-1", "email": "a@example.org"}
        claims.update(claim_overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        return 200, {"access_token": access, "refresh_token": refresh, "id_token": jwt(claims),
                     "token_type": "Bearer", "expires_in": 3600, "scope": scope}

    def sign_in(self, **kw):
        url, pending = self.account.begin_sign_in(REDIRECT)
        self.transport.responses.append(self.token_response(pending, **kw))
        info = self.account.complete_sign_in(
            pending, {"code": "CODE", "state": pending.state, "client_id": "oaiapp_issued"})
        return url, pending, info


class AuthorizeUrlTests(Base):
    def test_first_authorize_url_uses_dynamic_client(self):
        url, pending = self.account.begin_sign_in(REDIRECT)
        self.assertTrue(url.startswith("https://auth.openai.com/api/accounts/authorize?"))
        q = query_of(url)
        self.assertEqual(q["client_id"], DYNAMIC_CLIENT_ID)
        self.assertEqual(q["agent_name_hint"], "Scholarly Translation")
        self.assertEqual(q["ext_agent_host_id"], self.store.host)
        self.assertEqual(q["response_type"], "code")
        self.assertEqual(q["redirect_uri"], REDIRECT)
        self.assertTrue(q["redirect_uri"].startswith("http://127.0.0.1:"))
        self.assertEqual(q["scope"], SCOPES)
        self.assertIn(PLAN_SCOPE, q["scope"].split())
        self.assertEqual(q["resource"], "https://api.openai.com/v1")
        self.assertEqual(q["code_challenge_method"], "S256")
        digest = hashlib.sha256(pending.code_verifier.encode()).digest()
        self.assertEqual(q["code_challenge"], base64.urlsafe_b64encode(digest).rstrip(b"=").decode())
        self.assertEqual(q["state"], pending.state)
        self.assertEqual(q["nonce"], pending.nonce)

    def test_saved_client_id_used_later_without_name_hint(self):
        self.sign_in()
        url, _ = self.account.begin_sign_in(REDIRECT)
        q = query_of(url)
        self.assertEqual(q["client_id"], "oaiapp_issued")
        self.assertNotIn("agent_name_hint", q)
        self.assertEqual(q["ext_agent_host_id"], self.store.host)

    def test_state_and_nonce_are_fresh(self):
        _, a = self.account.begin_sign_in(REDIRECT)
        _, b = self.account.begin_sign_in(REDIRECT)
        self.assertNotEqual(a.state, b.state)
        self.assertNotEqual(a.nonce, b.nonce)
        self.assertNotEqual(a.code_verifier, b.code_verifier)

    def test_host_id_is_reused(self):
        u1, _ = self.account.begin_sign_in(REDIRECT)
        u2, _ = self.account.begin_sign_in(REDIRECT)
        self.assertEqual(query_of(u1)["ext_agent_host_id"], query_of(u2)["ext_agent_host_id"])

    def test_dpapi_host_id_persisted(self):
        import tempfile
        from pathlib import Path
        from scholarly_translation.account.openai_auth import DpapiAccountStore
        with tempfile.TemporaryDirectory() as tmp:
            first = DpapiAccountStore(Path(tmp)).host_id()
            self.assertTrue(first.startswith("urn:uuid:"))
            self.assertEqual(DpapiAccountStore(Path(tmp)).host_id(), first)


class CallbackTests(Base):
    def test_state_mismatch_rejected_without_exchange(self):
        _, pending = self.account.begin_sign_in(REDIRECT)
        with self.assertRaises(OpenAISignInError) as ctx:
            self.account.complete_sign_in(pending, {"code": "C", "state": "other"})
        self.assertEqual(ctx.exception.reason, "state_mismatch")
        self.assertEqual(self.transport.calls, [])
        with self.assertRaises(OpenAISignInError):
            self.account.complete_sign_in(pending, {"code": "C"})

    def test_access_denied_stops(self):
        _, pending = self.account.begin_sign_in(REDIRECT)
        with self.assertRaises(OpenAISignInError) as ctx:
            self.account.complete_sign_in(pending, {"error": "access_denied", "state": pending.state})
        self.assertEqual(ctx.exception.reason, "access_denied")
        self.assertEqual(self.transport.calls, [])
        self.assertFalse(self.account.status()["signed_in"])

    def test_state_checked_before_error(self):
        _, pending = self.account.begin_sign_in(REDIRECT)
        with self.assertRaises(OpenAISignInError) as ctx:
            self.account.complete_sign_in(pending, {"error": "access_denied", "state": "forged"})
        self.assertEqual(ctx.exception.reason, "state_mismatch")

    def test_missing_code(self):
        _, pending = self.account.begin_sign_in(REDIRECT)
        with self.assertRaises(OpenAISignInError) as ctx:
            self.account.complete_sign_in(pending, {"state": pending.state, "client_id": "oaiapp_x"})
        self.assertEqual(ctx.exception.reason, "missing_code")

    def test_different_client_id_rejected_on_reauthorization(self):
        self.sign_in()
        _, pending = self.account.begin_sign_in(REDIRECT)
        with self.assertRaises(OpenAISignInError) as ctx:
            self.account.complete_sign_in(pending, {"code": "C", "state": pending.state, "client_id": "oaiapp_other"})
        self.assertEqual(ctx.exception.reason, "client_id_mismatch")
        self.assertEqual(len(self.transport.calls), 1)  # only the first sign-in's exchange

    def test_client_id_may_be_omitted_on_reauthorization(self):
        self.sign_in()
        url, pending = self.account.begin_sign_in(REDIRECT)
        self.transport.responses.append(self.token_response(pending))
        info = self.account.complete_sign_in(pending, {"code": "C", "state": pending.state})
        self.assertTrue(info["plan_usage"])

    def test_first_sign_in_requires_issued_client_id(self):
        _, pending = self.account.begin_sign_in(REDIRECT)
        with self.assertRaises(OpenAISignInError) as ctx:
            self.account.complete_sign_in(pending, {"code": "C", "state": pending.state})
        self.assertEqual(ctx.exception.reason, "missing_client_id")

    def test_query_string_accepted(self):
        _, pending = self.account.begin_sign_in(REDIRECT)
        self.transport.responses.append(self.token_response(pending))
        info = self.account.complete_sign_in(
            pending, "?code=C&state=%s&client_id=oaiapp_issued" % pending.state)
        self.assertEqual(info["email"], "a@example.org")


class ExchangeTests(Base):
    def test_exchange_form_and_status(self):
        _, pending, info = self.sign_in()
        method, url, form = self.transport.calls[0]
        self.assertEqual((method, url), ("POST", TOKEN_ENDPOINT))
        self.assertEqual(form["grant_type"], "authorization_code")
        self.assertEqual(form["client_id"], "oaiapp_issued")
        self.assertEqual(form["code"], "CODE")
        self.assertEqual(form["code_verifier"], pending.code_verifier)
        self.assertEqual(form["redirect_uri"], REDIRECT)
        self.assertEqual(form["resource"], "https://api.openai.com/v1")
        self.assertEqual(info, {"email": "a@example.org", "plan_usage": True})
        self.assertEqual(self.account.status(),
                         {"available": True, "signed_in": True, "email": "a@example.org", "plan_usage": True})
        self.assertEqual(self.store.record["client_id"], "oaiapp_issued")
        self.assertEqual(self.store.record["sub"], "user-1")

    def test_plan_usage_false_without_direct_scope(self):
        _, _, info = self.sign_in(scope="openid profile email offline_access resource.invoke")
        self.assertFalse(info["plan_usage"])
        self.assertTrue(self.account.status()["signed_in"])
        self.assertFalse(self.account.status()["plan_usage"])

    def test_claim_validation(self):
        cases = {
            "bad_issuer": {"iss": "https://evil.example"},
            "bad_audience": {"aud": "oaiapp_someone_else"},
            "expired_id_token": {"exp": 1.0},
            "bad_expiry": {"exp": "soon"},
            "bad_nonce": {"nonce": "wrong"},
        }
        for reason, override in cases.items():
            with self.subTest(reason):
                account = OpenAIAccount(FakeStore(), self.transport, self.clock)
                _, pending = account.begin_sign_in(REDIRECT)
                self.transport.responses.append(self.token_response(pending, **override))
                with self.assertRaises(OpenAISignInError) as ctx:
                    account.complete_sign_in(pending, {"code": "C", "state": pending.state, "client_id": "oaiapp_issued"})
                self.assertEqual(ctx.exception.reason, reason)
                self.assertFalse(account.status()["signed_in"])

    def test_missing_nonce_rejected(self):
        _, pending = self.account.begin_sign_in(REDIRECT)
        self.transport.responses.append(self.token_response(pending, nonce=None))
        with self.assertRaises(OpenAISignInError) as ctx:
            self.account.complete_sign_in(pending, {"code": "C", "state": pending.state, "client_id": "oaiapp_issued"})
        self.assertEqual(ctx.exception.reason, "bad_nonce")

    def test_invalid_grant_on_exchange(self):
        _, pending = self.account.begin_sign_in(REDIRECT)
        self.transport.responses.append((400, {"error": "invalid_grant"}))
        with self.assertRaises(OpenAISignInError) as ctx:
            self.account.complete_sign_in(pending, {"code": "C", "state": pending.state, "client_id": "oaiapp_issued"})
        self.assertEqual(ctx.exception.reason, "invalid_grant")
        self.assertFalse(self.account.status()["signed_in"])
        self.assertEqual(self.store.record, {})


class RefreshTests(Base):
    def refresh_ok(self, access="ACCESS-SECRET-2", refresh="REFRESH-SECRET-2", **extra):
        body = {"access_token": access, "refresh_token": refresh, "expires_in": 3600}
        body.update(extra)
        return 200, body

    def test_cached_access_token_used_until_expiry(self):
        self.sign_in()
        self.assertEqual(self.account.access_token(), "ACCESS-SECRET-1")
        self.assertEqual(len(self.transport.calls), 1)
        self.clock.now += 3600 - 30  # inside the skew window
        self.transport.responses.append(self.refresh_ok())
        self.assertEqual(self.account.access_token(), "ACCESS-SECRET-2")

    def test_refresh_rotation_persisted_immediately(self):
        self.sign_in()
        self.account.invalidate_access_token()
        self.transport.responses.append(self.refresh_ok())
        self.assertEqual(self.account.access_token(), "ACCESS-SECRET-2")
        _, url, form = self.transport.calls[-1]
        self.assertEqual(url, TOKEN_ENDPOINT)
        self.assertEqual(form["grant_type"], "refresh_token")
        self.assertEqual(form["refresh_token"], "REFRESH-SECRET-1")
        self.assertEqual(form["client_id"], "oaiapp_issued")
        self.assertEqual(self.store.record["refresh_token"], "REFRESH-SECRET-2")
        self.assertEqual(self.store.record["client_id"], "oaiapp_issued")
        # the next refresh uses the rotated token
        self.account.invalidate_access_token()
        self.transport.responses.append(self.refresh_ok(access="A3", refresh="R3"))
        self.account.access_token()
        self.assertEqual(self.transport.calls[-1][2]["refresh_token"], "REFRESH-SECRET-2")

    def test_refresh_updates_scope(self):
        self.sign_in()
        self.account.invalidate_access_token()
        self.transport.responses.append(self.refresh_ok(scope="openid offline_access"))
        self.account.access_token()
        self.assertFalse(self.account.status()["plan_usage"])

    def test_terminal_refresh_errors_sign_out_but_keep_client_id(self):
        for code in ("invalid_grant", "invalid_refresh_token", "token_expired", "refresh_token_expired",
                     "refresh_token_invalidated", "refresh_token_reused"):
            with self.subTest(code):
                self.store.record = {}
                self.sign_in()
                self.account.invalidate_access_token()
                self.transport.responses.append((400, {"error": code}))
                with self.assertRaises(OpenAISignedOut):
                    self.account.access_token()
                self.assertFalse(self.account.status()["signed_in"])
                self.assertEqual(self.store.record, {"client_id": "oaiapp_issued"})
                self.assertEqual(self.store.host, self.store.host_id())
                with self.assertRaises(OpenAISignedOut):
                    self.account.access_token()

    def test_nested_error_object_is_understood(self):
        self.sign_in()
        self.account.invalidate_access_token()
        self.transport.responses.append((400, {"error": {"code": "refresh_token_reused"}}))
        with self.assertRaises(OpenAISignedOut):
            self.account.access_token()

    def test_temporary_failures_keep_credentials(self):
        self.sign_in()
        for outcome in ((503, {}), (500, {"error": "server_error"}), OpenAISignInError("network")):
            self.account.invalidate_access_token()
            self.transport.responses.append(outcome)
            with self.assertRaises(OpenAISignInError):
                self.account.access_token()
            self.assertTrue(self.account.status()["signed_in"])
            self.assertEqual(self.store.record["refresh_token"], "REFRESH-SECRET-1")

    def test_signed_out_raises(self):
        with self.assertRaises(OpenAISignedOut):
            self.account.access_token()

    def test_concurrent_refresh_is_serialized(self):
        self.sign_in()
        self.account.invalidate_access_token()
        gate = threading.Event()
        original = self.transport.__call__

        calls = []

        def slow(method, url, form=None):
            calls.append(form)
            gate.wait(0.2)
            return 200, {"access_token": "ACCESS-SECRET-2", "refresh_token": "REFRESH-SECRET-2", "expires_in": 3600}

        account = OpenAIAccount(self.store, slow, self.clock)
        results = []
        threads = [threading.Thread(target=lambda: results.append(account.access_token())) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(calls), 1)
        self.assertEqual(results, ["ACCESS-SECRET-2"] * 4)


class SignOutTests(Base):
    def test_sign_out_revokes_and_keeps_host_and_client_id(self):
        self.sign_in()
        host_before = self.store.host_id()
        self.transport.responses.append((200, {}))
        self.account.sign_out()
        method, url, form = self.transport.calls[-1]
        self.assertEqual(url, REVOKE_ENDPOINT)
        self.assertEqual(form, {"token": "REFRESH-SECRET-1", "token_type_hint": "refresh_token",
                                "client_id": "oaiapp_issued"})
        self.assertEqual(self.store.record, {"client_id": "oaiapp_issued"})
        self.assertEqual(self.store.host_id(), host_before)
        self.assertFalse(self.account.status()["signed_in"])
        with self.assertRaises(OpenAISignedOut):
            self.account.access_token()
        url2, _ = self.account.begin_sign_in(REDIRECT)
        self.assertEqual(query_of(url2)["client_id"], "oaiapp_issued")

    def test_sign_out_survives_revoke_failure(self):
        self.sign_in()
        self.transport.responses.append(OpenAISignInError("network"))
        self.account.sign_out()
        self.assertFalse(self.account.status()["signed_in"])

    def test_sign_out_when_signed_out_is_harmless(self):
        self.account.sign_out()
        self.assertEqual(self.transport.calls, [])


class NoLeakTests(Base):
    def assertClean(self, text):
        for secret in SECRETS + ("CODE",):
            self.assertNotIn(secret, text)

    def test_reprs_and_errors_do_not_contain_tokens(self):
        _, pending, _ = self.sign_in()
        self.assertClean(repr(self.account))
        self.assertClean(repr(pending))
        self.assertNotIn(pending.code_verifier, repr(pending))
        self.assertNotIn(pending.state, repr(pending))
        errors = []
        self.account.invalidate_access_token()
        self.transport.responses.append((400, {"error": "refresh_token_reused", "refresh_token": "REFRESH-SECRET-1"}))
        try:
            self.account.access_token()
        except OpenAISignedOut as exc:
            errors.append(exc)
        self.sign_in()
        self.account.invalidate_access_token()
        self.transport.responses.append((500, {"error": "boom", "access_token": "ACCESS-SECRET-2"}))
        try:
            self.account.access_token()
        except OpenAISignInError as exc:
            errors.append(exc)
        _, pending2 = self.account.begin_sign_in(REDIRECT)
        self.transport.responses.append((400, {"error": "invalid_grant", "error_description": "CODE REFRESH-SECRET-1"}))
        try:
            self.account.complete_sign_in(pending2, {"code": "CODE", "state": pending2.state, "client_id": "oaiapp_issued"})
        except OpenAISignInError as exc:
            errors.append(exc)
        try:
            self.account.complete_sign_in(pending2, {"code": "CODE", "state": "bad"})
        except OpenAISignInError as exc:
            errors.append(exc)
        self.assertEqual(len(errors), 4)
        for exc in errors:
            self.assertClean(str(exc))
            self.assertClean(repr(exc))


class DefaultAccountTests(unittest.TestCase):
    def test_default_account_is_none_off_windows(self):
        import sys
        from unittest import mock
        from scholarly_translation.account import openai_auth
        with mock.patch.object(sys, "platform", "linux"):
            self.assertIsNone(openai_auth.default_openai_account())


if __name__ == "__main__":
    unittest.main()
