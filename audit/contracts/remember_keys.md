# REMEMBER-KEYS — opt-in local persistence of API keys, header key indicator

Authority: user request 2026-10-07 (Claude continuity, user-directed): keep the API key after the
program closes, and show an indicator (key-shaped) that an API key is present. This changes the
earlier "memory only, restart requires renewed credentials" UI design at the user's request; the
build prompt allows keys in a local secret manager ("מנהל סודות"), never in chat/files/commits/logs.

## Behaviour

- `key_store.py`: `WindowsCredentialStore` (ctypes, advapi32 CredWrite/CredEnumerate/CredDelete),
  generic credentials `ScholarlyTranslation/provider/<provider_id>`, persist = local machine for
  the current Windows user (encrypted by Windows). `default_key_store()` is None off Windows.
- `make_handler(..., key_store=None)`: None keeps the memory-only behaviour (all existing tests);
  `main()` passes `default_key_store()`. At start, valid stored keys (provider-id pattern, no
  newline) load into the session keys; a store read failure is ignored (memory-only).
- `/model-keys`: `remember: bool` (optional) saves updated keys in the store; a key updated
  without `remember` or cleared ("") also deletes any stored entry (no stale key resurrects at the
  next start); `forget_saved: true` deletes every stored key but keeps them for this run. Store
  errors return 400 before the session is changed. Response adds `saved` and `remember_supported`.
- `/document-config` adds `key_providers_saved`, `key_remember_supported`.
- UI: "remember on this computer" checkbox under the key fields (start + resume; shown only when
  supported; default checked when keys are already saved, else the last choice in localStorage
  `remember-keys` — a preference, never the key), "delete saved keys" button, labels show
  "(saved on this computer)"; header key icon: grey = no key, gold = a key is available (memory,
  store or environment), green dot = saved on this computer; tooltip/aria lists providers. Click opens a
  dedicated "API key" dialog (follow-up: the connection dialog's Auto text was irrelevant): per
  provider whether the key is saved on this computer, in memory only, or external (environment /
  server configuration; `key_providers_external` / `external` from the server), a hint to tick
  "remember", "enter or replace a key" (switches to my own model if needed, opens the options and
  focuses the key field or translator model) and "delete saved keys". Learning page key field gets the same checkbox.

## Invariants

- A key value never appears in any HTTP response, job/journal file, project file, log, browser
  storage or os.environ. No new dependency. No provider call.
