# OPENAI-ACCOUNT: Sign in with ChatGPT, plan usage first, API key on exhaustion

Date: 2026-11-05. Base: e25ea47 (local main). Claude Code conductor, user-directed.
Branches: `feat/openai-account-backend` (builder A), `feat/openai-account-ui` (builder B),
integrated sequentially by the conductor.

User request: "add an option to connect with an OpenAI account, and when its budget runs out,
switch to the API key". The user rejected running through the Codex CLI. Use OpenAI's official
**Sign in with ChatGPT + plan usage** (DevDay 2026-09-29), which is documented for open-source
and personal locally run apps (this app qualifies). Docs: https://developers.openai.com/siwc
(token-sharing-open-source: sign-in, token-reference, models-and-inference, errors-and-recovery,
preview-limitations). Builders may fetch those pages to check details.

## Protocol facts (verified 2026-11-05)

- Discovery `https://auth.openai.com/.well-known/openid-configuration`: issuer
  `https://auth.openai.com`; authorize `https://auth.openai.com/api/accounts/authorize`;
  token `https://auth.openai.com/api/accounts/oauth/token`; revoke
  `https://auth.openai.com/api/accounts/oauth/revoke`; jwks `.../.well-known/jwks.json`;
  token auth method `none` (public client, no secret); PKCE `S256`; ID token RS256.
- Authorize query: `client_id` = `dynamic_agent_client` on first registration, else the saved
  issued id; `agent_name_hint=Scholarly Translation` (first registration only);
  `ext_agent_host_id` (required; `urn:uuid:<uuid4>` generated once per install, persisted, not
  personal); optional `id_token_hint`/`login_hint` on reauthorization; `response_type=code`;
  `redirect_uri=http://127.0.0.1:<port>/openai/callback` (127.0.0.1, never localhost; only the
  port may vary; the identical URI is used in the exchange); `scope=openid profile email
  offline_access resource.invoke chatgpt.tokens.use.direct`; `resource=https://api.openai.com/v1`;
  fresh `state`, `nonce`, `code_challenge` (b64url SHA-256, no padding), `code_challenge_method=S256`.
- Callback: `code`, `state`, `client_id` (issued, e.g. `oaiapp_...`; may be omitted on
  reauthorization; a different one than the pending request's is rejected), `scope`.
  `error=access_denied` → validate state, stop, no exchange.
- Exchange (form POST to token endpoint): `grant_type=authorization_code`, `client_id` (issued),
  `code`, `code_verifier`, `redirect_uri`, `resource`. Response: `access_token` (1 h),
  `refresh_token` (30 days, rotates on every refresh), `id_token`, `token_type`, `expires_in`,
  `scope`, `earliest_refresh_at`. `invalid_grant` on exchange → discard the code.
- Validate ID token claims `iss`, `aud` == issued client id, `exp`, `nonce` (claims read as in
  `google_auth._jwt_claims`; token received directly from the token endpoint over TLS).
  Identity = `sub` (+ email for display) stored together with the client id.
- **Plan usage is granted only if the granted `scope` contains `chatgpt.tokens.use.direct`.**
  Identity sign-in alone does not grant it.
- Refresh: form POST `grant_type=refresh_token`, `client_id`, `refresh_token` (+ `resource`).
  Replace access token, expiry, scopes and the rotating refresh token together and persist
  immediately. Refresh is serialized by a lock (concurrent refresh → `refresh_token_reused`).
  Terminal refresh errors (`invalid_grant`, `invalid_refresh_token`, `token_expired`,
  `refresh_token_expired`, `refresh_token_invalidated`, `refresh_token_reused`) → drop tokens,
  keep client id + host id, state signed out. Temporary failures never erase credentials.
- Sign out: best-effort revoke (`token`, `token_type_hint=refresh_token`, `client_id`), drop
  tokens; keep the host id and issued client id for later reauthorization.
- Inference: `POST https://api.openai.com/v1/responses` with `Authorization: Bearer <access>`
  (openai SDK: `api_key=<access>`, `base_url="https://api.openai.com/v1"`, `max_retries=0`).
  Required: `store=false`, `stream=true`; success only after `response.completed`.
  Omit: `max_output_tokens`, `temperature`, `top_p`, `metadata`, `prompt_cache_retention`,
  `previous_response_id`, `user`, `truncation`, explicit system-role items. Send the prompt as
  plain text (a `CacheablePrompt` is sent as its full text, no cache hints). Images
  (`ImagePrompt`) are allowed when the model accepts them. `reasoning` may be sent.
- Errors (`error.code` in an HTTP error body or a `response.failed` event, possibly mid-stream):
  `subscription_sharing_usage_limit_exceeded` (429) → plan exhausted;
  `subscription_sharing_user_not_eligible` (403), `chatpass_v2_scope_not_authorized`,
  `chatpass_v2_invalid_authorization_context` (403) → plan not usable;
  `subscription_sharing_unsupported_capability` (400) → plan cannot serve this request;
  `subscription_sharing_usage_unavailable`, `subscription_sharing_user_unavailable` (503) and
  admission 503 → temporary; 401 / `subscription_sharing_invalid_user` → refresh once, then
  temporary. Do not infer a reset time from the exhaustion code.

## Behavior

- Sign-in is an explicit user action in the UI. An existing Codex/ChatGPT login is never read
  or reused (no `~/.codex`), and no plan call happens without this app's own sign-in.
- For every model role whose provider is the native OpenAI endpoint (`provider_type == "openai"`
  and no `base_url`), when the account is signed in with plan usage granted, calls go to the
  plan first. Other providers are unchanged.
- **Fallback (the user's choice, shown in the UI, on by default):** "when the account's budget
  runs out, continue automatically with my OpenAI API key". OpenAI does not switch billing paths
  itself; this setting is the user's explicit advance choice. When the plan is exhausted /
  not usable / cannot serve the request and the setting is on and a key is available, the same
  call is made with the key and the UI shows that it switched. With the setting off or no key,
  the call raises `PlanUnavailableError` (an `OpenAIConfigurationError`, so the reservation is
  released and nothing is recorded as spent) with a clear Hebrew message.
- After exhaustion, plan calls pause for `PLAN_RETRY_SECONDS = 1800`; then the next call tries the
  plan again (a successful plan call returns the state to ready). Not eligible pauses until the
  next sign-in. Unsupported capability falls back for that call only.
- Plan-served results are free at the margin: `observed_provider == PLAN_PROVIDER_ID`
  (`"openai-chatgpt-plan"`) settles with estimate `0.0` and `actual_charge="chatgpt_plan"`;
  token usage is still recorded. Fallback results are normal API-key calls.
- Job start (paid confirmation, preflight): the native OpenAI provider counts as having a
  credential when either a key or a plan-granted sign-in exists. The cost estimate stays the
  API-key worst case (what the job can cost if everything falls back).
- Tokens never appear in logs, exception messages, HTTP responses, job files, `os.environ` or the
  browser. Storage: Windows only (same rule as `key_store.default_key_store`): one record under
  the app's user-data area protected with Windows DPAPI (`CryptProtectData`, current user) or the
  Credential Manager if the blob fits; written atomically. Non-Windows → feature unavailable.

## Builder A — backend (owns exactly)

- new `scholarly_translation/account/openai_auth.py`
- new `scholarly_translation/models/chatgpt_plan.py`
- `scholarly_translation/budget/runtime_controls.py` (only the plan zero-estimate settle rule)
- new `tests/account/test_openai_auth.py`, new `tests/models/test_chatgpt_plan.py`, plus a test
  for the settle rule in the existing runtime-controls test file.

Public interface (builder B codes against this, do not change names):

```python
# scholarly_translation/account/openai_auth.py  (stdlib only, injectable transport like google_auth)
class OpenAISignInError(Exception): reason: str           # machine code, no secrets
class OpenAISignedOut(Exception): ...
class OpenAIAccount:
    def __init__(self, store, transport=urllib_transport, clock=time.time): ...
    def begin_sign_in(self, redirect_uri: str) -> tuple[str, object]   # (authorize URL, pending)
    def complete_sign_in(self, pending, query: Mapping[str, str] | str) -> dict  # {"email", "plan_usage"}
    def status(self) -> dict      # {"available": True, "signed_in": bool, "email": str|None, "plan_usage": bool}
    def access_token(self) -> str # refreshes when needed (lock); raises OpenAISignedOut
    def invalidate_access_token(self) -> None
    def sign_out(self) -> None
def default_openai_account() -> OpenAIAccount | None   # None where unsupported

# scholarly_translation/models/chatgpt_plan.py
PLAN_PROVIDER_ID = "openai-chatgpt-plan"
PLAN_RETRY_SECONDS = 1800
class PlanUnavailableError(OpenAIConfigurationError): reason: str  # "exhausted"|"not_eligible"|"signed_out"|"unsupported"|"unavailable"
class PlanState:   # thread-safe, one per server process; injectable clock
    def snapshot(self) -> dict  # {"state": "ready"|"exhausted"|"not_eligible", "since": iso|None,
                                #  "retry_at": iso|None, "fallback_calls": int, "last_fallback_at": iso|None}
    def reset(self) -> None     # on sign-in / sign-out
class ChatGPTPlanAdapter(TextGenerationAdapter):
    def __init__(self, account, reasoning=None, timeout=None, client_factory=None, max_wall_seconds=3600)
    # generate() -> TextGenerationResult(observed_provider=PLAN_PROVIDER_ID) on success;
    # raises PlanUnavailableError(reason) for plan-specific refusals; ordinary transport
    # failures return failed_transport like OpenAITextGenerationAdapter.
class PlanFirstAdapter(TextGenerationAdapter):
    def __init__(self, plan_adapter, plan_state, fallback_adapter=None, auto_fallback=True)
```

`PlanFirstAdapter.generate` uses the plan when `plan_state` is ready, records state changes,
falls back per the Behavior rules, counts `fallback_calls`, and returns the fallback adapter's
result unchanged. Tests use fake transports/clients only. No network, no real sign-in.

## Builder B — UI and server wiring (owns exactly)

- `scholarly_translation/ui/web_ui.py`, `scholarly_translation/ui/ui.html`, `ui.js`, `ui.css`
  (and `ui-theme.css` only if needed), `scholarly_translation/ui/keys_guide.html` (short
  section), server text in English if the UI has an EN string table that must stay in sync
  (check `tests/ui/test_server_text_en.py`, `test_ui_language.py`)
- tests under `tests/ui/` (new `test_openai_account_ui.py`; revise existing assertions rather
  than leaving contradictions).

Work:
- `make_handler(..., openai_account_factory=None, plan_state=None)`; production
  `default_openai_account()`. Routes (token-protected like `/account/*`):
  `POST /openai-account` → `{account: status(), plan: plan_state.snapshot(), auto_fallback,
  key_available}`; `/openai-account/sign-in` → opens the browser with the authorize URL
  (pending expires like Google's); `/openai-account/sign-out`; `/openai-account/settings`
  `{auto_fallback: bool}` persisted in a small non-secret JSON under `OUTPUT_ROOT / "ui"`.
  `GET /openai/callback` completes sign-in (exempt from the token like `/oauth/callback`,
  state-checked), then `plan_state.reset()`; a reply page in the same style as `_sign_in_page`.
- `_adapter_factory_for`: for native OpenAI definitions with a plan-granted sign-in, wrap in
  `PlanFirstAdapter(ChatGPTPlanAdapter(account, reasoning=...), plan_state, fallback_adapter=
  <existing key adapter or None>, auto_fallback=<setting>)`. `_preflight_credentials`,
  `_missing_credential_providers`, `_requirements`, `_learning_adapter` and `/document-config`
  key availability accept the plan for the native OpenAI provider.
- UI, in the existing key section (library look, matte; Hebrew primary, EN table if present):
  card "חשבון OpenAI (ChatGPT Plus/Pro)": connect / disconnect, connected email, whether plan
  usage was granted (if not: explain that it must be allowed on the consent screen),
  checkbox "כשתקציב החשבון נגמר — להמשיך אוטומטית עם מפתח ה־API" (default on), state line
  (ready / exhausted since HH:MM, next try HH:MM / switched to API key N times), link to
  ChatGPT Settings → Usage. Poll the state while a job runs and show a notice when calls switched
  to the key.

## Invariants and acceptance

- No paid or plan call in tests; no real network. Existing API-key-only behavior is unchanged
  when not signed in. Run: `python -B -m unittest discover -s tests` (conductor).
- The conductor does one live manual check only with the user's sign-in and consent.
