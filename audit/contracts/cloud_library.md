# CLOUD-LIBRARY contract — Google sign-in, Drive library, bring-your-own-key guide

Base: 4b59367 (main). User decisions 2026-10-15 (Claude Code conductor session):
the app becomes available online with Google (Gmail) sign-in and keeps each user's
translated books; the owner pays as little as possible for servers; users pay for
models with their own API keys (no OpenRouter, no reseller billing, no
Sign-in-with-ChatGPT); each provider gets a link to create a key and add credits,
and gpt-6-luna is the recommended model.

Architecture (decided): no hosted processing server. Translation, OCR and export
keep running in the existing local app (127.0.0.1 server). The local app signs in
with Google (installed-app OAuth, loopback redirect + PKCE) and keeps the user's
library in the user's own Google Drive. A static public site (no backend) offers
the download, the key guide and the privacy policy. Owner running cost: a domain
at most. Windows only, as today.

Human prerequisites (blocking only real-account use, not construction):
Google Cloud project, OAuth consent screen (External; scopes `openid email profile`
and `https://www.googleapis.com/auth/drive.file`), a Desktop-app OAuth client ID,
a privacy-policy URL, and a site host. The conductor re-verifies before release
that drive.file is still classified non-sensitive and every provider URL below.

## C1 Google sign-in (owns: scholarly_translation/account/ (new: __init__.py,
## google_auth.py), tests/account/test_google_auth.py (new))

- Component: installed-app OAuth 2.0 for Google. Stdlib only (urllib, hashlib,
  secrets, base64, json); no new dependency.
- Input: `GoogleClientConfig(client_id, client_secret|None)` read from
  `SCHOLARLY_GOOGLE_CLIENT_ID` / `SCHOLARLY_GOOGLE_CLIENT_SECRET` or a
  secret-free `account_config.json` (client_id only; a desktop client secret is
  not confidential per Google, but it is still never logged or returned to the UI).
- `begin_sign_in(redirect_uri) -> (authorization_url, PendingSignIn)`: S256 PKCE,
  random `state`, scopes exactly as above, `access_type=offline`, `prompt=consent`
  only when no refresh token is stored.
- `complete_sign_in(pending, query) -> Account`: rejects missing/mismatched state,
  `error=` responses and absent code (`SignInError`, explicit reason). Exchanges the
  code at the token endpoint; validates the ID token's `iss`, `aud`, `exp` and
  `email_verified` from the token-endpoint response (TLS-authenticated, so no JWKS).
  `Account(sub, email, name)`; identity key is `sub`, never the email.
- Token storage: the refresh token goes into the existing Windows Credential
  Manager under `ScholarlyTranslation/google/<sub>` (same mechanism as
  models/key_store.py; reuse, do not duplicate the ctypes layer — add a small
  public helper there only if needed and say so). Access tokens memory only.
  `sign_out()` revokes (best effort) and deletes the stored entry.
- `access_token() -> str` refreshes when expired; refresh failure (`invalid_grant`)
  -> `SignedOut` state, never a crash or silent retry loop.
- Tests: offline, injected HTTP transport fakes; state mismatch, error callback,
  bad aud/iss/expired token, refresh, revoked refresh token, sign-out deletes entry.

## C2 Drive library sync (owns: scholarly_translation/account/drive_library.py
## (new), tests/account/test_drive_library.py (new))

- Consumes C1 only through `access_token()` (injected callable) and an injected
  transport; Drive REST v3 over urllib, stdlib only.
- Folder: one app folder "Scholarly Translation" in the user's Drive (created by the
  app, found via `appProperties.scholarly_library=1`, so drive.file suffices); one
  subfolder per completed job, `appProperties.job_id=<job_id>`.
- Uploaded per completed job: `job.json` (unchanged schema) plus the job's
  translated outputs and source file, using multipart/resumable upload for files
  over 5 MB. Uploads are idempotent per (job_id, file name, sha256): unchanged
  files are skipped; changed files replace the Drive copy. Never deletes a Drive
  file the user did not ask to delete.
- `list_remote() -> [RemoteBook(job_id, filename, completed_at, files)]`;
  `download(job_id, dest)` restores a job folder into the local job root only if
  no local job with that id exists (no silent overwrite; conflict -> explicit
  `SyncConflict`).
- Errors: 401 -> one refresh then `SignedOut`; 403 quota/storage -> `DriveQuotaError`
  shown to the user; network -> retry later, job stays local. A sync failure never
  fails or alters a translation job.
- Tests: offline fake Drive; first sync, unchanged re-sync, changed file, restore,
  conflict, 401/403/network, folder rediscovery.

## C3 web_ui wiring + account UI (owns: scholarly_translation/ui/web_ui.py,
## ui.html, ui.js, ui.css, tests/ui/test_account_ui.py (new)) — after C1, C2

- Routes (same token/origin checks): `POST /account` -> `{signed_in, email, name,
  sync: {state, last_sync_at, pending}}`; `POST /account/sign-in` -> authorization
  URL (opened with webbrowser); `GET /oauth/callback` completes sign-in (state
  checked), then shows a small "you can close this tab" page; `POST
  /account/sign-out`; `POST /account/sync`; `POST /account/remote-library`;
  `POST /account/restore {job_id}`.
- Completed jobs are queued for upload automatically when signed in; sync runs in a
  background thread, one at a time.
- UI: header "Sign in with Google" / avatar initial + email menu (sync status,
  sync now, sign out). Library panel marks each book local / in Drive / both and
  offers "restore to this computer" for Drive-only books. Hebrew + English strings.
- The app keeps working fully when signed out (current behaviour unchanged).

## C4 bring-your-own-key guide (owns: scholarly_translation/ui/keys_guide.html
## (new), ui.js key-dialog section only, tests/ui/test_keys_guide.py (new)) —
## independent of C1-C3; if run in parallel with C3, ui.js is integrated after C3

- A guide reachable from the key dialog ("How do I get a key?") and the start
  panel, Hebrew and English, per provider the app supports: what an API key is,
  that a ChatGPT/Claude subscription does not include API credit, steps to create a
  key, add prepaid credit (minimum, auto-recharge off by default recommendation,
  set a monthly limit), and paste it with "remember on this computer".
- Recommendation box: OpenAI `gpt-6-luna` for translator and QA (cheapest
  measured option; cite the catalogue's list rate and the app's own estimate),
  with an example cost per typical book derived from models/catalog.py, not a
  hard-coded promise.
- Links (verified by the conductor before release; builder copies them as given):
  OpenAI keys https://platform.openai.com/api-keys, billing
  https://platform.openai.com/settings/organization/billing/overview;
  Anthropic keys https://platform.claude.com/settings/keys, billing
  https://platform.claude.com/settings/billing; DeepSeek keys
  https://platform.deepseek.com/api_keys, top-up https://platform.deepseek.com/top_up.
  Links open in the system browser; no key, email or usage data is sent anywhere.
- Static, no script requirement beyond the existing i18n; no external resources.

## C5 public static site (owns: site/ (new: index.html, keys.html, privacy.html,
## site.css), tests/site/test_site_static.py (new)) — independent

- Hebrew-first RTL pages with English versions: what the app does, download/install
  (links to the release asset), the key guide (same content and links as C4),
  privacy policy (data stays on the user's computer and the user's own Drive; Google
  data used only for sign-in and the app's own Drive folder; no server collects
  anything; contact address is a placeholder the owner fills).
- Pure static files, no analytics, no external scripts or fonts, served by GitHub
  Pages of the public distribution repo (see Distribution). The download button
  points to `https://github.com/<DIST_REPO>/releases/latest/download/ScholarlyTranslation-Setup.zip`
  with `<DIST_REPO>` as a literal placeholder the release script fills.
  Tests: links well-formed, no external script/style, every page has lang/dir and a title.

## Distribution (user decision 2026-10-15)

The development repo stays private. A separate public repo (`<DIST_REPO>`, created
by the owner; name not yet chosen) holds only runtime files, one tag per version
(`v<version>`), the static site on GitHub Pages, and per-release assets:
`ScholarlyTranslation-Setup.zip` (first install), `manifest.json`, `manifest.json.sig`.
Nothing from audit/, docs/, tests/, outputs/, .claude/ or Git history of the private
repo is published. Creating the repo and each publish are owner-approved actions.

## C6 silent updates (owns: scholarly_translation/update/ (new: __init__.py,
## manifest.py, updater.py), scholarly_translation/app_paths.py (new),
## run-ui.ps1, install.ps1, Install.bat, scripts/release/ (new: build_release.py,
## sign_manifest.py), tests/update/ (new)) — user decision 2026-10-15: users get
## updates without consciously re-downloading the project

- Install layout: `%LOCALAPPDATA%\ScholarlyTranslation\app\<version>\` (runtime
  files only: scholarly_translation/, requirements.txt, launcher scripts; never
  audit/, docs/, tests/, outputs/) and `...\app\current.txt` naming the active
  version. User data moves to `%LOCALAPPDATA%\ScholarlyTranslation\data\`
  (`app_paths.data_root()`; env `SCHOLARLY_DATA_ROOT` overrides; a development
  checkout keeps `<repo>/outputs` when no install marker exists). First run after
  the move copies an existing `<install>/outputs` into data/ once, never deletes it.
  web_ui.OUTPUT_ROOT derives from data_root() — that one line is integrated after C3.
- Release channel (GitHub, no server): the manifest and signature are fetched from
  `https://github.com/<DIST_REPO>/releases/latest/download/manifest.json(.sig)`;
  each changed file from `https://raw.githubusercontent.com/<DIST_REPO>/v<version>/<path>`.
  `<DIST_REPO>` is one constant in update/manifest.py. Manifest: `{schema 1, version,
  tag, min_launcher, requirements_sha256, files: {relative_path: {sha256, size}},
  notes_he, notes_en}` plus detached Ed25519 signature `manifest.json.sig`. Redirects
  only to github.com / *.githubusercontent.com hosts; anything else is rejected. The public key is embedded in
  the app; the private key stays with the owner, offline, never in the repo or audit.
- Updater: at app start, in a background thread, fetch the manifest (HTTPS, short
  timeout); verify the signature (dependency: `cryptography`, pinned in
  requirements.txt); reject any version not greater than current (no downgrade) and
  any path outside the app tree (no `..`, absolute or drive paths). Build the new
  version folder by hard-copying unchanged files from the current version and
  downloading only files whose sha256 differs; verify each file's hash and size;
  write `current.txt` atomically only after the whole folder verifies. If
  `requirements_sha256` changed, the launcher runs `pip install -r` into the
  existing venv before switching; on failure it stays on the old version.
- Applied at the next launch, never mid-run. The UI shows a quiet notice "updated to
  X" with the notes, and an "update ready, restart" hint if one is staged. Keep the
  previous version folder for rollback: if the new version fails to start (no
  heartbeat within 60 s), the launcher switches back and records why. Remove older
  folders beyond two.
- Setting "automatic updates" (default on) in the existing options; off = check
  and show only. No telemetry: the only request is the anonymous manifest/file GET.
- Jobs, keys, terms and Drive state written by an older version stay readable
  (existing explicit legacy-reading rule); an update never touches data/.
- `scripts/release/build_release.py` (dry-run by default) exports the runtime file
  allow-list from a clean commit of the private repo into a local checkout of the
  distribution repo, writes the manifest and the Setup zip, and prints the exact `git`
  and `gh release create` commands for the owner to run; it never pushes by itself.
  `sign_manifest.py` signs with a key path the owner supplies at run time and also
  offers `--generate-key` writing the private key outside the repo.
- Tests offline: tampered manifest/file/signature, downgrade, path traversal,
  partial download, unchanged-file reuse, requirements change, rollback, data-root
  migration, update disabled.

## Invariants

- No hosted backend, database or job server is introduced. No paid provider call,
  no real Google/Drive call in tests. Keys and tokens never appear in HTTP
  responses, files, logs, browser storage, Drive or os.environ.
- Each user's library lives only on their computer and in their own Drive.
- Signed-out behaviour is byte-for-byte the current app flow.

## Integration order

C1, C4, C5 and C6 in parallel (disjoint paths) -> C2 -> C3 -> C6's OUTPUT_ROOT
line -> conductor end-to-end check with a real test Google account once the owner
supplies the OAuth client, and an update round-trip on a clean Windows user
profile once the owner generates the signing key (human prerequisites).

## Out of scope

Mac/Linux packaging, Windows Authenticode signing of the installer, hosted processing, payments to the owner,
OpenRouter or Sign-in-with-ChatGPT, sharing books between users, deleting Drive
copies, multi-device conflict merging beyond the explicit SyncConflict.
