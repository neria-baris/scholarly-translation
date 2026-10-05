# AUTOMATION-3 — model/key settings and visible costs in the local UI

Authority: 2026-10-05 user addendum. Dependencies: accepted AUTOMATION-1/2.
Owner Sol; Claude Code Sonnet scoped builder. Budgets runtime API USD0;
one subscription invocation, CLI USD10 if enforcing, 20min/100tool soft.

Owns: existing loopback HTTP routes/HTML/JS/settings and user documentation.
Input: upload, profile, quality, per-role known/custom model choice, API keys,
budget. Output: secret-free config/catalogue and per-role token/cost preview,
document plan/progress/usage/exceptions, pause/resume/download/review.

Invariants: translator selectable from dated catalogue + Other; QA independently
selectable, ordinary default same selected model unless user chooses another.
Show provider ID, rates/version/source, estimated custom tariff clearly; allow
manual Other limits/rates and compatible endpoint. Keys accepted only by protected
POST, kept in server memory only, no global env mutation, logs, persisted config,
job, localStorage or response echo. Browser password field cleared after transfer.
Memory-only keys lost on restart; resume requests renewed keys without regenerating
saved work. Existing authenticated token and same-origin checks still apply.

Preview recomputes after file/model/QA/quality choice, including translation/QA/
bounded correction-recheck, expected vs conservative ceiling, counted vs estimated
tokens and cache-miss assumption. Unknown catalogue tariff is never official.
Runtime shows observed estimated spend separately from held/remaining planned
funds and role usage/cache reuse. Start explicitly consents to chosen providers;
demo remains conspicuously mock. Checked requires configured QA, defaults checked
for real translation; technical PASS never scholarly approval.

Acceptance: protected HTTP + injected-client tests for mixed model roles, custom
model estimates, malformed rates/URLs, missing QA/key preflight and no-secret
artifacts/responses; browser smoke of model selection, key session save, preview,
demo export, pause/resume; existing test suite and JS parse pass.

Errors: sanitized input/provider errors; no echoed arbitrary submitted secrets.
Side effects: existing local upload/jobs and bounded chosen provider use only.
Out of scope: hosting, shared multi-user credentials, live paid quality acceptance.
