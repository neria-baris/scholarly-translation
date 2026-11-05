# PROFILE-EVERYWHERE: a drawn profile picture and a sign-in window on every screen

Date: 2026-11-05. Base: 66b7d2d (main = origin/main). Claude Code conductor, user-directed.
Branch `feat/profile-everywhere` (builder), integrated by the conductor.

User request: "I want a sign-in window and a profile drawing to appear on every screen."

## Behavior

- Every page served by the local app shows the same profile button at the end of its header
  (`.app-header`): `ui.html` (all routes: library, new, job, result), `learning.html`,
  `help.html`, `learning_help.html`, `keys_guide.html`. Exactly one profile button per header.
- The button is a **drawing** (inline SVG, no image files, no network): a reader in the library
  look — matte and flat, warm palette and dark outline like the cat logo (`#e3893a`, `#2a1a10`,
  cream `#fffbea`); no gloss, gradients or 3D. A small status badge: none when signed out; green
  when an OpenAI plan is ready; amber when the plan is exhausted / switched to the key; the first
  letter of the connected email may be shown on the badge or in the window, never in place of
  the drawing.
- Clicking opens the **sign-in window** (a `<dialog>`, keyboard accessible, Esc closes, focus
  returns to the button, RTL Hebrew / LTR English following the page language):
  1. **OpenAI account (ChatGPT Plus/Pro)** — the same data and actions as the card in the model
     settings, through the existing routes `POST /openai-account`, `/openai-account/sign-in`,
     `/openai-account/sign-out`, `/openai-account/settings`: connected email, whether plan usage
     was granted (if not: explain and offer reconnect), the auto-fallback checkbox, state line
     (ready / exhausted since, next try / switched to the API key N times), link to ChatGPT
     settings → Usage. After "connect" the window keeps polling until signed in or closed.
  2. **Google account (library in Drive)** — status and sign in / sign out through the existing
     `/account` routes. If Google is unavailable in this build, say so in one quiet line.
  3. A short line linking to the help section `/help#openai-account`.
- The existing Google button in the `ui.html` header (`#account-area`, `#account-button`,
  `#sign-in-button`) must not produce a second avatar: fold its entry point into the profile
  window; keep every Drive feature reachable (sync, remote library, restore — e.g. a button in
  the window that opens the existing account menu or the same actions). No feature lost.
- The card in the model settings stays; both read the same routes and stay consistent.
- Pages that today have no token (`help.html`, `learning_help.html`, `keys_guide.html`) get
  `window.UI_CONFIG = {token}` injected by `web_ui.py` the same way as `ui.html`/`learning.html`,
  so the window can call the POST routes. Tokens/keys never reach the page beyond that UI token.
- The cat must not sit on the profile button (it avoids buttons already; keep it that way).

## Owned files

- new `scholarly_translation/ui/profile.js`, new `scholarly_translation/ui/profile.css`
- `scholarly_translation/ui/web_ui.py` (serving the two new static files and injecting the
  config into the three help pages only)
- `ui.html`, `learning.html`, `help.html`, `learning_help.html`, `keys_guide.html` (header
  mount point + script/style tags), `ui.js` and `ui.css` only for folding the old Google header
  button, EN strings if the UI's EN tables require them
- tests under `tests/ui/` (new `test_profile_everywhere.py`; revise contradicted assertions)

Not owned: `cat.js`, `cat.css` (the conductor is changing the cat in parallel).

## Acceptance

- Each of the five pages, served by `make_handler`, contains the profile mount and loads
  `profile.js`/`profile.css`; the three help pages contain the injected token config.
- The window's actions call only the existing routes; no token text in any page.
- Existing UI tests pass (revise those that asserted the old Google header button).
