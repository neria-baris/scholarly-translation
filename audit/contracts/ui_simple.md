# Simple document translation — user-directed UX correction, 2026-10-04

Authority: user requested fixing the current UI and clarified the main product flow:
put a PDF/EPUB in, receive a translation, optionally review it; model, quality and
ordinary settings are secondary. This supersedes the command-form homepage. It
does not authorize fabricating human source/translation approvals or paid test calls.

Owner: Sol directly implements two bounded sequential components: UI-SIMPLE-ENGINE
(document draft/HTTP integration; at most 30 tool calls before reassessment) and
UI-SIMPLE-SHELL (HTML/CSS/JS and browser acceptance; at most 30 calls). Direct local
work avoids a new external repository transmission and preserves the already
verified, uncommitted Gate-11 controls. No Claude/Opus/Astra/runtime paid call.

## Input and ownership

- One uploaded PDF with embedded text or unencrypted EPUB, up to 25 MB, bounded
  pages/ZIP expansion/source characters. EPUB reads package spine order, never
  extracts archive paths or loads resources. Scanned/image-only content fails
  explicitly; no invented OCR or layout reconstruction feature.
- OpenAI model choice: GPT-6 Luna or GPT-6.1 Sol; quality controls actual supported
  reasoning effort and output budget, without a verified translation-quality claim.
  Source language auto/en/fr/ja; target Hebrew. Demo is explicitly not translation.
- API key is session memory or existing environment only. No secret in job files,
  client preferences, logs or Git. Provider transmission requires user action and
  confirmation showing destination and an enforced list-price reservation limit.

## Output and contracts

- New schema-1 `document-draft@1`, always approved=false/source_reviewed=false;
  bounded text chunks retain source file hash, location/span, raw source/target,
  model/settings, usage and formal findings. It is an explicitly automated draft,
  separate from canonical human-resolved Gate-7/9 schemas. Never fabricate human
  decisions to pass existing source validators.
- Persistent ignored job/result/revision files and durable SQLite reservations,
  append-only events and exact raw cache; cap/model/config/pricing/prompt identity
  bound. Conservative hold before dispatch, no retry, retained failed/unknown
  hold, anomalous usage stops. Existing Gate-11/CLI defaults and scholarly contracts
  remain intact. New job means a consciously started document task, not a cap reset.
- Plain-text and escaped HTML draft downloads available without mandatory review.
  Partial output is labeled incomplete and preserves untranslated positions.
  Optional human edits create a new draft revision, not research approval/export.
- Public local API returns actual processing/completed counts, never pretend
  progress; polling/resume works after page reload and completed jobs after restart.
  Downloads restricted to known job artifacts; CSRF/origin guard remains.

## UI-SIMPLE-SHELL

- Single uncluttered RTL page: clear heading, upload/drop area, translate button.
  File name/change control, model/quality/language chips; settings in a disclosure.
  No sidebar, fake completion tracker, generic CLI fields or raw log on main page.
- Settings show only implemented choices, key connection and per-document cap.
  Error/loading/result states are visible and actionable; keyboard/focus and
  narrow-screen layout supported. Demo is optional and conspicuously labeled.
- Result: download actions first, optional expandable source/target review and
  edit/save; no JSON manipulation or mandatory stage navigation.

## Acceptance and limits

Mechanical tests cover PDF/EPUB extraction/order/bounds, no paid calls in tests,
actual model/quality forwarding, cap/uncertain/incomplete behavior, source and
approval provenance, edited revisions, downloads and HTTP guards. Existing full
suite runs after focused acceptance. Browser verifies initial/upload or sample,
settings, genuine processing/result and optional review at desktop/narrow layout.
No new model winner, gold data, OCR service, authentication/account, remote host,
EPUB/PDF layout reproduction, approved scholarly output or Gate-10 quality pass.

Official docs checked 2026-10-04 (not account availability):
- https://developers.openai.com/api/docs/models/gpt-6-luna — Responses, none/low/medium effort; standard input/cache/write/output $0.10/$0.01/$0.125/$0.50 per million.
- https://developers.openai.com/api/docs/models/gpt-6.1-sol — Responses, low/medium/high effort; standard $2/$0.10/$2.50/$10 per million.
- https://developers.openai.com/api/docs/guides/reasoning — incomplete outputs must not be presented as complete; output allowance includes reasoning.
