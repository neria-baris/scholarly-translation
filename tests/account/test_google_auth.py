"""Offline tests for Google sign-in (injected transport, store and clock)."""
import base64
import hashlib
import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from scholarly_translation.account.google_auth import (
    Account, AccountConfigError, GOOGLE_TARGET_PREFIX, GoogleAccount, GoogleClientConfig,
    REVOKE_ENDPOINT, SCOPES, SignInError, SignedOut, TOKEN_ENDPOINT,
)

CLIENT_ID = "client-123.apps.googleusercontent.com"
SECRET = "SECRET-VALUE-XYZ"
REFRESH = "REFRESH-TOKEN-ABC"
ACCESS = "ACCESS-TOKEN-DEF"
NOW = 1_000_000.0


def jwt(**overrides):
    claims = {"iss": "https://accounts.google.com", "aud": CLIENT_ID, "exp": NOW + 3600,
              "email_verified": True, "sub": "sub-1", "email": "a@example.com", "name": "Ann"}
    claims.update(overrides)
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"h.{body}.s"


class FakeStore:
    def __init__(self):
        self.data = {}
        self.deleted = []

    def load_all(self):
        return dict(self.data)

    def save(self, key, value):
        self.data[key] = value

    def delete(self, key):
        self.deleted.append(key)
        self.data.pop(key, None)


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, form=None):
        self.calls.append((method, url, dict(form or {})))
        return self.responses.pop(0)


def ok_exchange(**claim_overrides):
    return (200, {"access_token": ACCESS, "expires_in": 3600, "refresh_token": REFRESH,
                  "id_token": jwt(**claim_overrides)})


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now


def make(*responses, store=None):
    clock = Clock()
    transport = FakeTransport(*responses)
    store = store if store is not None else FakeStore()
    auth = GoogleAccount(GoogleClientConfig(CLIENT_ID, SECRET), store, transport, clock)
    return auth, transport, store, clock


def callback(pending, **extra):
    query = {"state": pending.state, "code": "auth-code"}
    query.update(extra)
    return query


class BeginTests(unittest.TestCase):
    def test_url_has_pkce_state_scopes_and_consent(self):
        auth, _, _, _ = make()
        url, pending = auth.begin_sign_in("http://127.0.0.1:8765/oauth/callback")
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(q["code_challenge_method"], ["S256"])
        self.assertEqual(q["scope"], [SCOPES])
        self.assertEqual(q["state"], [pending.state])
        self.assertEqual(q["access_type"], ["offline"])
        self.assertEqual(q["prompt"], ["consent"])
        self.assertEqual(q["client_id"], [CLIENT_ID])
        self.assertNotIn(SECRET, url)
        self.assertNotIn(pending.code_verifier, url)
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(pending.code_verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(q["code_challenge"], [expected])

    def test_no_consent_prompt_when_refresh_token_stored(self):
        store = FakeStore()
        store.data["sub-1"] = json.dumps({"refresh_token": REFRESH})
        auth, _, _, _ = make(store=store)
        url, _ = auth.begin_sign_in("http://127.0.0.1/cb")
        self.assertNotIn("prompt", urllib.parse.parse_qs(urllib.parse.urlparse(url).query))

    def test_state_is_random(self):
        auth, _, _, _ = make()
        self.assertNotEqual(auth.begin_sign_in("http://x/cb")[1].state,
                            auth.begin_sign_in("http://x/cb")[1].state)


class CompleteTests(unittest.TestCase):
    def fail_reason(self, auth, pending, query):
        with self.assertRaises(SignInError) as ctx:
            auth.complete_sign_in(pending, query)
        for secret in (SECRET, REFRESH, ACCESS, pending.code_verifier):
            self.assertNotIn(secret, str(ctx.exception))
        return ctx.exception.reason

    def test_state_mismatch_and_missing(self):
        auth, transport, _, _ = make()
        _, pending = auth.begin_sign_in("http://x/cb")
        self.assertEqual(self.fail_reason(auth, pending, {"state": "nope", "code": "c"}), "state_mismatch")
        self.assertEqual(self.fail_reason(auth, pending, {"code": "c"}), "state_mismatch")
        self.assertEqual(transport.calls, [])

    def test_error_callback(self):
        auth, _, _, _ = make()
        _, pending = auth.begin_sign_in("http://x/cb")
        self.assertEqual(self.fail_reason(auth, pending, callback(pending, error="access_denied")),
                         "provider_error")

    def test_missing_code(self):
        auth, _, _, _ = make()
        _, pending = auth.begin_sign_in("http://x/cb")
        self.assertEqual(self.fail_reason(auth, pending, {"state": pending.state}), "missing_code")

    def test_bad_claims(self):
        cases = [({"aud": "other"}, "bad_audience"), ({"iss": "https://evil.example"}, "bad_issuer"),
                 ({"exp": NOW - 1}, "expired_id_token"), ({"email_verified": False}, "email_unverified")]
        for overrides, reason in cases:
            auth, _, store, _ = make(ok_exchange(**overrides))
            _, pending = auth.begin_sign_in("http://x/cb")
            self.assertEqual(self.fail_reason(auth, pending, callback(pending)), reason)
            self.assertEqual(store.data, {})
            self.assertFalse(auth.signed_in)

    def test_alternate_issuer_accepted(self):
        auth, _, _, _ = make(ok_exchange(iss="accounts.google.com"))
        _, pending = auth.begin_sign_in("http://x/cb")
        self.assertEqual(auth.complete_sign_in(pending, callback(pending)).sub, "sub-1")

    def test_token_endpoint_failure_does_not_leak(self):
        auth, _, _, _ = make((400, {"error": "invalid_grant", "error_description": SECRET}))
        _, pending = auth.begin_sign_in("http://x/cb")
        self.assertEqual(self.fail_reason(auth, pending, callback(pending)), "token_exchange_failed")

    def test_success_stores_refresh_under_sub(self):
        auth, transport, store, _ = make(ok_exchange())
        _, pending = auth.begin_sign_in("http://x/cb")
        account = auth.complete_sign_in(pending, callback(pending))
        self.assertEqual(account, Account("sub-1", "a@example.com", "Ann"))
        self.assertEqual(json.loads(store.data["sub-1"])["refresh_token"], REFRESH)
        method, url, form = transport.calls[0]
        self.assertEqual((method, url), ("POST", TOKEN_ENDPOINT))
        self.assertEqual(form["code_verifier"], pending.code_verifier)
        self.assertEqual(auth.access_token(), ACCESS)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(GOOGLE_TARGET_PREFIX, "ScholarlyTranslation/google/")

    def test_query_string_accepted(self):
        auth, _, _, _ = make(ok_exchange())
        _, pending = auth.begin_sign_in("http://x/cb")
        self.assertTrue(auth.complete_sign_in(pending, f"?state={pending.state}&code=abc").sub)


class TokenTests(unittest.TestCase):
    def signed_in(self, *more):
        auth, transport, store, clock = make(ok_exchange(), *more)
        _, pending = auth.begin_sign_in("http://x/cb")
        auth.complete_sign_in(pending, callback(pending))
        return auth, transport, store, clock

    def test_refresh_when_expired(self):
        auth, transport, _, clock = self.signed_in((200, {"access_token": "NEW", "expires_in": 3600}))
        clock.now += 3600
        self.assertEqual(auth.access_token(), "NEW")
        form = transport.calls[1][2]
        self.assertEqual((form["grant_type"], form["refresh_token"]), ("refresh_token", REFRESH))
        self.assertEqual(auth.access_token(), "NEW")
        self.assertEqual(len(transport.calls), 2)

    def test_invalid_grant_signs_out_once(self):
        auth, transport, store, clock = self.signed_in((400, {"error": "invalid_grant"}))
        clock.now += 3600
        with self.assertRaises(SignedOut):
            auth.access_token()
        self.assertFalse(auth.signed_in)
        self.assertEqual(store.data, {})
        self.assertEqual(store.deleted, ["sub-1"])
        with self.assertRaises(SignedOut):
            auth.access_token()
        self.assertEqual(len(transport.calls), 2)  # no retry loop

    def test_transient_failure_keeps_session(self):
        auth, _, store, clock = self.signed_in((503, {}))
        clock.now += 3600
        with self.assertRaises(SignInError) as ctx:
            auth.access_token()
        self.assertNotIn(REFRESH, str(ctx.exception))
        self.assertTrue(auth.signed_in)
        self.assertIn("sub-1", store.data)

    def test_signed_out_state(self):
        auth, _, _, _ = make()
        with self.assertRaises(SignedOut):
            auth.access_token()

    def test_restore_from_store(self):
        _, _, store, clock = self.signed_in()
        fresh = GoogleAccount(GoogleClientConfig(CLIENT_ID), store,
                              FakeTransport((200, {"access_token": "R", "expires_in": 100})), clock)
        self.assertEqual(fresh.restore(), Account("sub-1", "a@example.com", "Ann"))
        self.assertEqual(fresh.access_token(), "R")

    def test_sign_out_revokes_and_deletes(self):
        auth, transport, store, _ = self.signed_in((200, {}))
        auth.sign_out()
        self.assertEqual(transport.calls[1], ("POST", REVOKE_ENDPOINT, {"token": REFRESH}))
        self.assertEqual(store.data, {})
        self.assertFalse(auth.signed_in)

    def test_sign_out_survives_revoke_failure(self):
        def boom(*args, **kwargs):
            raise SignInError("network")
        auth, _, store, _ = self.signed_in()
        auth._transport = boom
        auth.sign_out()
        self.assertEqual(store.data, {})


class ConfigTests(unittest.TestCase):
    def test_env_and_repr(self):
        cfg = GoogleClientConfig.load(environ={"SCHOLARLY_GOOGLE_CLIENT_ID": "id",
                                               "SCHOLARLY_GOOGLE_CLIENT_SECRET": SECRET})
        self.assertEqual(cfg.client_id, "id")
        self.assertNotIn(SECRET, repr(cfg))

    def test_missing_config(self):
        with self.assertRaises(AccountConfigError):
            GoogleClientConfig.load(environ={})

    def test_json_config_reads_desktop_client_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "account_config.json"
            path.write_text(json.dumps({"client_id": "from-file", "client_secret": "desktop-secret"}))
            cfg = GoogleClientConfig.load(path, environ={})
            only_id = Path(tmp) / "only_id.json"
            only_id.write_text(json.dumps({"client_id": "from-file"}))
            cfg_no_secret = GoogleClientConfig.load(only_id, environ={})
        self.assertEqual((cfg.client_id, cfg.client_secret), ("from-file", "desktop-secret"))
        self.assertNotIn("desktop-secret", repr(cfg))
        self.assertIsNone(cfg_no_secret.client_secret)


if __name__ == "__main__":
    unittest.main()
