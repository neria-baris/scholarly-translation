"""Google installed-app OAuth 2.0 (loopback redirect, S256 PKCE), stdlib only.

Identity key is the ID token ``sub``. The refresh token lives in the Windows
Credential Manager under ``ScholarlyTranslation/google/<sub>``; access tokens
stay in memory. Tokens and secrets are never logged, put in exception
messages, written to files or placed in ``os.environ``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"
SCOPES = "openid email profile https://www.googleapis.com/auth/drive.file"
GOOGLE_TARGET_PREFIX = "ScholarlyTranslation/google/"
ISSUERS = ("accounts.google.com", "https://accounts.google.com")
ENV_CLIENT_ID = "SCHOLARLY_GOOGLE_CLIENT_ID"
ENV_CLIENT_SECRET = "SCHOLARLY_GOOGLE_CLIENT_SECRET"
_EXPIRY_SKEW = 60  # refresh this many seconds before the access token expires

# transport(method, url, form_fields) -> (http_status, parsed_json_body)
Transport = Callable[[str, str, Optional[Mapping[str, str]]], "tuple[int, dict]"]


class SignInError(Exception):
    """Sign-in failed. ``reason`` is a short machine-readable code."""

    def __init__(self, reason: str, message: str = ""):
        super().__init__(f"{reason}: {message}" if message else reason)
        self.reason = reason


class SignedOut(Exception):
    """No usable credentials (never signed in, signed out, or refresh revoked)."""


class AccountConfigError(Exception):
    pass


@dataclass(frozen=True)
class GoogleClientConfig:
    client_id: str
    client_secret: Optional[str] = None

    def __repr__(self) -> str:  # never expose the secret
        return f"GoogleClientConfig(client_id={self.client_id!r}, client_secret={'***' if self.client_secret else None})"

    @classmethod
    def load(cls, config_path: "str | Path | None" = None, environ: Optional[Mapping[str, str]] = None):
        env = os.environ if environ is None else environ
        client_id = (env.get(ENV_CLIENT_ID) or "").strip()
        secret = (env.get(ENV_CLIENT_SECRET) or "").strip() or None
        if not client_id and config_path and Path(config_path).is_file():
            try:
                data = json.loads(Path(config_path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise AccountConfigError("account_config.json is unreadable") from None
            if isinstance(data, dict):
                client_id = str(data.get("client_id") or "").strip()
                # A Desktop-app client secret is not confidential (Google's
                # installed-app model), but the token endpoint still requires it.
                secret = secret or (str(data.get("client_secret") or "").strip() or None)
        if not client_id:
            raise AccountConfigError("Google client_id is not configured")
        return cls(client_id, secret)


@dataclass(frozen=True)
class Account:
    sub: str
    email: str
    name: str


@dataclass(frozen=True)
class PendingSignIn:
    state: str
    code_verifier: str
    redirect_uri: str

    def __repr__(self) -> str:
        return "PendingSignIn(...)"


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
        raise SignInError("network", "could not reach Google") from None
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
        raise SignInError("bad_id_token", "ID token is not a readable JWT") from None
    if not isinstance(claims, dict):
        raise SignInError("bad_id_token", "ID token payload is not an object")
    return claims


class GoogleAccount:
    def __init__(self, config: GoogleClientConfig, store, transport: Transport = urllib_transport,
                 clock: Callable[[], float] = time.time):
        """``store`` needs load_all()/save(key, value)/delete(key), e.g.
        ``WindowsCredentialStore(prefix=GOOGLE_TARGET_PREFIX)``."""
        self._config = config
        self._store = store
        self._transport = transport
        self._clock = clock
        self._account: Optional[Account] = None
        self._access_token: Optional[str] = None
        self._expires_at = 0.0

    # -- state ---------------------------------------------------------
    @property
    def account(self) -> Optional[Account]:
        return self._account

    @property
    def signed_in(self) -> bool:
        return self._account is not None

    def _stored(self) -> dict:
        try:
            return self._store.load_all()
        except OSError:
            return {}

    @staticmethod
    def _parse_entry(raw: str) -> Optional[dict]:
        try:
            entry = json.loads(raw)
        except (ValueError, TypeError):
            return None
        if isinstance(entry, dict) and entry.get("refresh_token"):
            return entry
        return None

    def restore(self) -> Optional[Account]:
        """Re-adopt a stored account without network access (access token is fetched lazily)."""
        for sub, raw in self._stored().items():
            entry = self._parse_entry(raw)
            if entry:
                self._account = Account(sub, str(entry.get("email", "")), str(entry.get("name", "")))
                self._access_token, self._expires_at = None, 0.0
                return self._account
        return None

    # -- sign in -------------------------------------------------------
    def begin_sign_in(self, redirect_uri: str) -> "tuple[str, PendingSignIn]":
        verifier = _b64url(secrets.token_bytes(64))
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        state = _b64url(secrets.token_bytes(24))
        params = {
            "client_id": self._config.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
        }
        if not any(self._parse_entry(raw) for raw in self._stored().values()):
            params["prompt"] = "consent"
        url = AUTH_ENDPOINT + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        return url, PendingSignIn(state, verifier, redirect_uri)

    def complete_sign_in(self, pending: PendingSignIn, query: "Mapping[str, str] | str") -> Account:
        if isinstance(query, str):
            query = {k: v[0] for k, v in urllib.parse.parse_qs(query.lstrip("?")).items()}
        got_state = query.get("state")
        if not got_state or not secrets.compare_digest(str(got_state), pending.state):
            raise SignInError("state_mismatch", "missing or mismatched state")
        if query.get("error"):
            raise SignInError("provider_error", f"Google returned error {str(query['error'])[:60]}")
        code = query.get("code")
        if not code:
            raise SignInError("missing_code", "no authorization code in the callback")
        form = {
            "grant_type": "authorization_code",
            "code": str(code),
            "client_id": self._config.client_id,
            "redirect_uri": pending.redirect_uri,
            "code_verifier": pending.code_verifier,
        }
        if self._config.client_secret:
            form["client_secret"] = self._config.client_secret
        status, body = self._transport("POST", TOKEN_ENDPOINT, form)
        if status != 200 or not body.get("access_token"):
            raise SignInError("token_exchange_failed", f"token endpoint status {status}")
        claims = self._validate_claims(_jwt_claims(body.get("id_token")))
        sub = str(claims["sub"])
        refresh = body.get("refresh_token")
        if not refresh:
            existing = self._parse_entry(self._stored().get(sub, ""))
            refresh = existing["refresh_token"] if existing else None
        if not refresh:
            raise SignInError("no_refresh_token", "Google did not issue a refresh token")
        account = Account(sub, str(claims.get("email", "")), str(claims.get("name", "")))
        self._store.save(sub, json.dumps(
            {"refresh_token": refresh, "email": account.email, "name": account.name}))
        self._account = account
        self._access_token = str(body["access_token"])
        self._expires_at = self._clock() + float(body.get("expires_in") or 0)
        return account

    def _validate_claims(self, claims: dict) -> dict:
        if claims.get("iss") not in ISSUERS:
            raise SignInError("bad_issuer", "ID token issuer is not Google")
        aud = claims.get("aud")
        audiences = aud if isinstance(aud, list) else [aud]
        if self._config.client_id not in audiences:
            raise SignInError("bad_audience", "ID token audience does not match this app")
        try:
            exp = float(claims.get("exp"))
        except (TypeError, ValueError):
            raise SignInError("bad_expiry", "ID token has no valid expiry") from None
        if exp <= self._clock():
            raise SignInError("expired_id_token", "ID token has expired")
        if claims.get("email_verified") not in (True, "true"):
            raise SignInError("email_unverified", "Google account email is not verified")
        if not claims.get("sub"):
            raise SignInError("bad_id_token", "ID token has no subject")
        return claims

    # -- tokens --------------------------------------------------------
    def access_token(self) -> str:
        if self._account is None:
            raise SignedOut("not signed in")
        if self._access_token and self._clock() < self._expires_at - _EXPIRY_SKEW:
            return self._access_token
        sub = self._account.sub
        entry = self._parse_entry(self._stored().get(sub, ""))
        if not entry:
            self._drop_local()
            raise SignedOut("no stored credentials")
        form = {
            "grant_type": "refresh_token",
            "refresh_token": entry["refresh_token"],
            "client_id": self._config.client_id,
        }
        if self._config.client_secret:
            form["client_secret"] = self._config.client_secret
        status, body = self._transport("POST", TOKEN_ENDPOINT, form)
        if status == 400 and body.get("error") == "invalid_grant":
            self._forget(sub)
            raise SignedOut("refresh token was revoked or expired")
        if status != 200 or not body.get("access_token"):
            # Transient failure: stay signed in, do not retry here.
            raise SignInError("refresh_failed", f"token endpoint status {status}")
        self._access_token = str(body["access_token"])
        self._expires_at = self._clock() + float(body.get("expires_in") or 0)
        return self._access_token

    def invalidate_access_token(self) -> None:
        """Forget the cached access token (an API answered 401); the next
        access_token() call refreshes it with the stored refresh token."""
        self._access_token, self._expires_at = None, 0.0

    def sign_out(self) -> None:
        if self._account is None:
            return
        sub = self._account.sub
        entry = self._parse_entry(self._stored().get(sub, ""))
        token = (entry or {}).get("refresh_token") or self._access_token
        if token:
            try:
                self._transport("POST", REVOKE_ENDPOINT, {"token": token})
            except Exception:  # best effort only
                pass
        self._forget(sub)

    def _drop_local(self) -> None:
        self._account, self._access_token, self._expires_at = None, None, 0.0

    def _forget(self, sub: str) -> None:
        self._drop_local()
        try:
            self._store.delete(sub)
        except OSError:
            pass


def default_google_store():
    """Windows Credential Manager store for Google tokens, or None elsewhere."""
    if sys.platform != "win32":
        return None
    from scholarly_translation.models.key_store import WindowsCredentialStore
    try:
        return WindowsCredentialStore(prefix=GOOGLE_TARGET_PREFIX)
    except (OSError, AttributeError):
        return None
