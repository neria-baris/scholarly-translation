"""Sign in with ChatGPT (OpenAI public client, loopback redirect, S256 PKCE), stdlib only.

The app is registered dynamically (``dynamic_agent_client``) on the first
sign-in; the issued client id is kept for later reauthorization. The refresh
token (which rotates on every refresh) lives in one record protected with
Windows DPAPI for the current user; access tokens stay in memory. Tokens are
never logged, put in exception messages, reprs, job files or ``os.environ``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional

ISSUER = "https://auth.openai.com"
AUTH_ENDPOINT = "https://auth.openai.com/api/accounts/authorize"
TOKEN_ENDPOINT = "https://auth.openai.com/api/accounts/oauth/token"
REVOKE_ENDPOINT = "https://auth.openai.com/api/accounts/oauth/revoke"
DYNAMIC_CLIENT_ID = "dynamic_agent_client"
AGENT_NAME_HINT = "Scholarly Translation"
RESOURCE = "https://api.openai.com/v1"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
SCOPES = "openid profile email offline_access resource.invoke " + PLAN_SCOPE
TERMINAL_REFRESH_ERRORS = frozenset({
    "invalid_grant", "invalid_refresh_token", "token_expired",
    "refresh_token_expired", "refresh_token_invalidated", "refresh_token_reused",
})
_EXPIRY_SKEW = 60  # refresh this many seconds before the access token expires

# transport(method, url, form_fields) -> (http_status, parsed_json_body)
Transport = Callable[[str, str, Optional[Mapping[str, str]]], "tuple[int, dict]"]


class OpenAISignInError(Exception):
    """Sign-in or refresh failed. ``reason`` is a short machine-readable code."""

    def __init__(self, reason: str, message: str = ""):
        super().__init__(f"{reason}: {message}" if message else reason)
        self.reason = reason


class OpenAISignedOut(Exception):
    """No usable credentials (never signed in, signed out, or refresh rejected)."""


@dataclass(frozen=True)
class PendingOpenAISignIn:
    state: str
    code_verifier: str
    nonce: str
    redirect_uri: str
    client_id: str

    def __repr__(self) -> str:
        return "PendingOpenAISignIn(...)"


def urllib_transport(method: str, url: str, form: Optional[Mapping[str, str]] = None) -> "tuple[int, dict]":
    data = urllib.parse.urlencode(form).encode("ascii") if form is not None else None
    request = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        raise OpenAISignInError("network", "could not reach OpenAI") from None
    try:
        body = json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError:
        body = {}
    return status, body if isinstance(body, dict) else {}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _jwt_claims(id_token: object) -> dict:
    try:
        payload = str(id_token).split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except (IndexError, ValueError, UnicodeError):
        raise OpenAISignInError("bad_id_token", "ID token is not a readable JWT") from None
    if not isinstance(claims, dict):
        raise OpenAISignInError("bad_id_token", "ID token payload is not an object")
    return claims


def _error_code(body: Mapping) -> str:
    error = body.get("error")
    if isinstance(error, dict):
        error = error.get("code") or error.get("type")
    return str(error)[:80] if error else ""


def _scope_set(scope: object) -> set:
    return set(str(scope or "").split())


def _expires_in(body: Mapping) -> float:
    try:
        return max(0.0, float(body.get("expires_in") or 0))
    except (TypeError, ValueError):
        return 0.0


# -- storage ---------------------------------------------------------------
class DpapiAccountStore:
    """One DPAPI-protected record (current user) plus a non-secret host id file."""

    RECORD_NAME = "openai_account.bin"
    HOST_ID_NAME = "openai_host_id.txt"

    def __init__(self, directory):
        self._dir = Path(directory)

    @staticmethod
    def _blob_api():
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        pblob = ctypes.POINTER(DATA_BLOB)
        crypt32.CryptProtectData.restype = wintypes.BOOL
        crypt32.CryptProtectData.argtypes = [pblob, wintypes.LPCWSTR, pblob, ctypes.c_void_p,
                                             ctypes.c_void_p, wintypes.DWORD, pblob]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        crypt32.CryptUnprotectData.argtypes = [pblob, ctypes.c_void_p, pblob, ctypes.c_void_p,
                                               ctypes.c_void_p, wintypes.DWORD, pblob]

        def run(call, data: bytes) -> bytes:
            buffer = (ctypes.c_ubyte * max(1, len(data))).from_buffer_copy(data or b"\0")
            source = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
            out = DATA_BLOB()
            if not call(ctypes.byref(source), ctypes.byref(out)):
                raise OSError("Windows data protection failed")
            try:
                return ctypes.string_at(out.pbData, out.cbData)
            finally:
                kernel32.LocalFree(out.pbData)

        def protect(data: bytes) -> bytes:
            return run(lambda s, o: crypt32.CryptProtectData(
                s, "Scholarly Translation", None, None, None, 0, o), data)

        def unprotect(data: bytes) -> bytes:
            return run(lambda s, o: crypt32.CryptUnprotectData(s, None, None, None, None, 0, o), data)

        return protect, unprotect

    def load(self) -> dict:
        try:
            blob = (self._dir / self.RECORD_NAME).read_bytes()
        except OSError:
            return {}
        try:
            _, unprotect = self._blob_api()
            record = json.loads(unprotect(blob).decode("utf-8"))
        except (OSError, ValueError, UnicodeError):
            return {}
        return record if isinstance(record, dict) else {}

    def save(self, record: Mapping) -> None:
        protect, _ = self._blob_api()
        blob = protect(json.dumps(dict(record)).encode("utf-8"))
        self._write_atomic(self.RECORD_NAME, blob)

    def host_id(self) -> str:
        try:
            value = (self._dir / self.HOST_ID_NAME).read_text(encoding="ascii").strip()
            if value.startswith("urn:uuid:"):
                return value
        except (OSError, UnicodeError):
            pass
        value = "urn:uuid:" + str(uuid.uuid4())
        self._write_atomic(self.HOST_ID_NAME, value.encode("ascii"))
        return value

    def _write_atomic(self, name: str, data: bytes) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self._dir), prefix="." + name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self._dir / name)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


# -- account ---------------------------------------------------------------
class OpenAIAccount:
    def __init__(self, store, transport: Transport = urllib_transport,
                 clock: Callable[[], float] = time.time):
        """``store`` needs load() -> dict, save(dict) and host_id() -> str,
        e.g. ``DpapiAccountStore``."""
        self._store = store
        self._transport = transport
        self._clock = clock
        self._lock = threading.RLock()
        self._access_token: Optional[str] = None
        self._expires_at = 0.0

    def __repr__(self) -> str:
        return "OpenAIAccount(...)"

    def _record(self) -> dict:
        try:
            record = self._store.load()
        except OSError:
            return {}
        return record if isinstance(record, dict) else {}

    def _keep_identity_only(self, record: Mapping) -> None:
        """Drop all tokens but keep the issued client id (host id lives apart)."""
        kept = {"client_id": record["client_id"]} if record.get("client_id") else {}
        self._access_token, self._expires_at = None, 0.0
        try:
            self._store.save(kept)
        except OSError:
            pass

    # -- state ---------------------------------------------------------
    def status(self) -> dict:
        with self._lock:
            record = self._record()
            signed_in = bool(record.get("refresh_token"))
            return {
                "available": True,
                "signed_in": signed_in,
                "email": str(record["email"]) if signed_in and record.get("email") else None,
                "plan_usage": signed_in and PLAN_SCOPE in _scope_set(record.get("scope")),
            }

    # -- sign in -------------------------------------------------------
    def begin_sign_in(self, redirect_uri: str) -> "tuple[str, PendingOpenAISignIn]":
        with self._lock:
            saved = str(self._record().get("client_id") or "")
            host_id = self._store.host_id()
        verifier = _b64url(secrets.token_bytes(64))
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        state = _b64url(secrets.token_bytes(24))
        nonce = _b64url(secrets.token_bytes(24))
        client_id = saved or DYNAMIC_CLIENT_ID
        params = {"client_id": client_id}
        if not saved:
            params["agent_name_hint"] = AGENT_NAME_HINT
        params.update({
            "ext_agent_host_id": host_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": SCOPES,
            "resource": RESOURCE,
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
        url = AUTH_ENDPOINT + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        return url, PendingOpenAISignIn(state, verifier, nonce, redirect_uri, client_id)

    def complete_sign_in(self, pending: PendingOpenAISignIn, query: "Mapping[str, str] | str") -> dict:
        if isinstance(query, str):
            query = {k: v[0] for k, v in urllib.parse.parse_qs(query.lstrip("?")).items()}
        got_state = query.get("state")
        if not got_state or not secrets.compare_digest(str(got_state), pending.state):
            raise OpenAISignInError("state_mismatch", "missing or mismatched state")
        error = query.get("error")
        if error:
            code = str(error)[:60]
            raise OpenAISignInError("access_denied" if code == "access_denied" else "provider_error",
                                    f"OpenAI returned error {code}")
        code = query.get("code")
        if not code:
            raise OpenAISignInError("missing_code", "no authorization code in the callback")
        returned = str(query.get("client_id") or "")
        if pending.client_id == DYNAMIC_CLIENT_ID:
            if not returned or returned == DYNAMIC_CLIENT_ID:
                raise OpenAISignInError("missing_client_id", "no issued client id in the callback")
            client_id = returned
        else:
            if returned and returned != pending.client_id:
                raise OpenAISignInError("client_id_mismatch", "callback client id differs from the request")
            client_id = pending.client_id
        form = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": str(code),
            "code_verifier": pending.code_verifier,
            "redirect_uri": pending.redirect_uri,
            "resource": RESOURCE,
        }
        status, body = self._transport("POST", TOKEN_ENDPOINT, form)
        if status != 200 or not body.get("access_token"):
            raise OpenAISignInError(
                "invalid_grant" if _error_code(body) == "invalid_grant" else "token_exchange_failed",
                f"token endpoint status {status}")
        claims = self._validate_claims(_jwt_claims(body.get("id_token")), client_id, pending.nonce)
        refresh = body.get("refresh_token")
        if not refresh:
            raise OpenAISignInError("no_refresh_token", "OpenAI did not issue a refresh token")
        scope = str(body.get("scope") or query.get("scope") or "")
        email = str(claims.get("email") or "")
        with self._lock:
            self._store.save({
                "client_id": client_id, "sub": str(claims["sub"]), "email": email,
                "refresh_token": str(refresh), "scope": scope,
            })
            self._access_token = str(body["access_token"])
            self._expires_at = self._clock() + _expires_in(body)
        return {"email": email, "plan_usage": PLAN_SCOPE in _scope_set(scope)}

    def _validate_claims(self, claims: dict, client_id: str, nonce: str) -> dict:
        if claims.get("iss") != ISSUER:
            raise OpenAISignInError("bad_issuer", "ID token issuer is not OpenAI")
        aud = claims.get("aud")
        audiences = aud if isinstance(aud, list) else [aud]
        if client_id not in audiences:
            raise OpenAISignInError("bad_audience", "ID token audience does not match this app")
        try:
            exp = float(claims.get("exp"))
        except (TypeError, ValueError):
            raise OpenAISignInError("bad_expiry", "ID token has no valid expiry") from None
        if exp <= self._clock():
            raise OpenAISignInError("expired_id_token", "ID token has expired")
        got_nonce = claims.get("nonce")
        if not got_nonce or not secrets.compare_digest(str(got_nonce), nonce):
            raise OpenAISignInError("bad_nonce", "ID token nonce does not match")
        if not claims.get("sub"):
            raise OpenAISignInError("bad_id_token", "ID token has no subject")
        return claims

    # -- tokens --------------------------------------------------------
    def access_token(self) -> str:
        with self._lock:
            if self._access_token and self._clock() < self._expires_at - _EXPIRY_SKEW:
                return self._access_token
            record = self._record()
            refresh = record.get("refresh_token")
            client_id = record.get("client_id")
            if not refresh or not client_id:
                self._access_token, self._expires_at = None, 0.0
                raise OpenAISignedOut("not signed in")
            form = {"grant_type": "refresh_token", "client_id": str(client_id),
                    "refresh_token": str(refresh), "resource": RESOURCE}
            status, body = self._transport("POST", TOKEN_ENDPOINT, form)
            if status != 200 and _error_code(body) in TERMINAL_REFRESH_ERRORS:
                self._keep_identity_only(record)
                raise OpenAISignedOut("refresh token was rejected")
            if status != 200 or not body.get("access_token"):
                # Temporary failure: credentials stay, the caller may retry later.
                raise OpenAISignInError("refresh_failed", f"token endpoint status {status}")
            updated = dict(record)
            if body.get("refresh_token"):
                updated["refresh_token"] = str(body["refresh_token"])
            if body.get("scope"):
                updated["scope"] = str(body["scope"])
            self._store.save(updated)  # persist the rotated token before anything else
            self._access_token = str(body["access_token"])
            self._expires_at = self._clock() + _expires_in(body)
            return self._access_token

    def invalidate_access_token(self) -> None:
        with self._lock:
            self._access_token, self._expires_at = None, 0.0

    def sign_out(self) -> None:
        with self._lock:
            record = self._record()
            token = record.get("refresh_token")
            if token and record.get("client_id"):
                try:
                    self._transport("POST", REVOKE_ENDPOINT, {
                        "token": str(token), "token_type_hint": "refresh_token",
                        "client_id": str(record["client_id"])})
                except Exception:  # best effort only
                    pass
            self._keep_identity_only(record)


def default_openai_account() -> Optional[OpenAIAccount]:
    """The Windows-protected account, or None where the feature is unsupported."""
    if sys.platform != "win32":
        return None
    try:
        from scholarly_translation.app_paths import data_root
        store = DpapiAccountStore(data_root() / "account")
        store._blob_api()  # fail early if DPAPI is not reachable
    except (OSError, AttributeError, ImportError):
        return None
    return OpenAIAccount(store)
