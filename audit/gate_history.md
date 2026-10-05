
## Gate 0 | historical 2026-09-29 (time unknown) | imported 2026-09-29T09:24:51.806127+00:00

**Gate 0 - environment and access: FIX (superseded)**

Historical card from the earlier session, 2026-09-29; original time-of-day unavailable.
- Prompt and both policy documents read; report and three-language synthetic text saved in GATE_0.md.
- Claude Code 2.1.268 executable; authentication reported loggedIn=true / Pro. Live inference, model availability and quota not verified.
- Python execution and UTF-8 document checks passed; Python 3.9.13 and Node 20.19.0 available; no product tests.
- Git main at caea85d; GitHub remote configured; initial tree clean; only GATE_0.md added; no commit or push; server state not checked.
- No ZIP or sample PDF; proposed ignored input paths inputs/fr/, inputs/en/, inputs/ja/.
- Zero additional model calls; conductor cost and total time not_metered.
- Proposed next step was bounded live Claude verification and PDF fixtures. Stopped without starting Gate 1.
The PDF condition is superseded by the user's explicit instruction: PDFs do not block Gate 0.

Full prior report preserved at `audit/raw/20260929T092338Z-gate0-prior.md`.

## Gate 0 | 2026-09-29T09:24:51.806127+00:00

**Gate 0 - environment and live Claude handoff: PASS WITH WARNINGS**

- Verified: Astra -> Claude Code CLI -> repository README -> independent Astra comparison. Claude used Read; returned the exact first heading; exit status 0.
- Models reported: claude-sonnet-5; CLI usage also includes claude-haiku-4-5-20251001.
- Usage: one live CLI invocation, 6.156 seconds, reported list-price cost $0.0137952 under a $0.25 CLI cap. Actual subscription charge and conductor usage: not_metered.
- Changes: updated GATE_0.md; added append-only audit histories and timestamped evidence. No product implementation, web use, or README modification.
- Git: main, baseline caea85dc16ab752658bcc5d20a4904825835bf27; no tracked source changes. Gate documentation remains uncommitted; no push. Remote freshness and ongoing push authorization remain unverified.
- Warnings: list-price usage is not proof of an actual subscription charge; the CLI reported auxiliary Haiku usage. Sample PDFs are a later-gate prerequisite, not a Gate 0 failure.
- Next step: stop for user review. Gate 1 has not started.

## Gate 0 | 2026-09-29T09:36:46.686261+00:00 | housekeeping

**Gate 0 housekeeping: PASS WITH WARNINGS**

- Live Claude verification remains PASS (exit 0, exact README heading, reported Sonnet plus auxiliary Haiku usage); no new model invocation.
- Reviewed the complete pending reports, audit evidence and instruction change; no unrelated files, credentials, private PDFs or excessive raw output found. Prior FIX is retained as a labeled diagnostic history, not a failed implementation.
- Added missing standing audit/Git rules to prompt_codex_cli_astra_conductor_translation_build_he.md; existing policy remains authoritative for existing usage fields and exclusions.
- Branch main and intended origin verified. git ls-remote and git fetch origin main succeeded; remote baseline caea85dc16ab752658bcc5d20a4904825835bf27 equals local HEAD; ancestry check passed. No remote configuration changed.
- Closure: create the Gate 0 commit, then a separate audit receipt with its hash; normal push of these two commits is user-authorized subject to final checks. Commit/push outcomes follow in the receipt and final response; this card does not claim a future push succeeded.
- Remaining warnings: reported model cost is a list-price estimate, not an actual-charge verification. Sample PDFs are a later-gate prerequisite and do not block Gate 0.
- Gate 1 has not started; stop after Git closure.

## Gate 0 | 2026-09-29T09:39:26.913106+00:00 | AGENTS.md follow-up

**Gate 0 instruction follow-up: PASS**

- Added concise root AGENTS.md: conductor/builder roles, source-of-truth links, explicit gate approval, append-only audit, conductor-owned Git, explicit remote/destructive authorization, scoped inexpensive execution, secret exclusions and conflict escalation.
- Verified all three linked policy/specification files exist. No implementation or model calls.
- Earlier housekeeping commits were already pushed before this request arrived; preserve published history. Create a separate local Gate 0 follow-up and audit receipt. Prior two-commit push authorization does not cover these new commits.
- Gate 1 has not started. Stop after local commits and clean-tree verification.

## Gate 0 | 2026-09-29T09:44:18.129968+00:00 | workflow reconciliation

**PASS (instruction review; Git closure follows).** Pending AGENTS follow-up pushed and verified at remote. Active instructions now use one canonical supervised-autonomy rule with navigational references; historical approval rules remain only as past audit evidence. Diff review and link/rule checks are required before commit. Model calls: 0; conductor usage not_metered. Next: synchronize instruction commit, then Gate 1.

## Gate 1 | 2026-09-29T09:49:11.427837+00:00 | first acceptance

**FIX.** Offline skeleton written; 18 unit tests pass, but real CLI inspect fails on Japanese output and validation/config/usage checks are incomplete. No PDF or translation-quality claim. One Sonnet invocation, reported $0.3234798 list-price estimate, actual charge not_metered. Next: one targeted fix and independent retest. No commit of failed implementation.

## Gate 1 | 2026-09-30T16:04:39.214787+00:00 | acceptance

**Gate 1 ? PASS (software acceptance; Git closure follows).**
Deliverable: runnable offline CLI, stable document/page/region/segment identity, source location/language, schema 2 stage/hash/status/warnings, explicit schema 1 reader, atomic JSON store, configurable mock provider and append-only usage.
Evidence: `python -B -m unittest discover -s tests -q` ? 41 pass; demo with config.example.json and inspect succeed including Japanese; producer/consumer source spans/hash and adapter substitution pass. No paid runtime API. Contracts: gate_1.md, data_spine.md.
Failures/fixes: G1-A1/A2 preserved; UTF-8/config/validation repairs completed, Sol corrected config echo and added current data spine (G1-A3). Synthetic fixture and mock are not scholarly/PDF quality evidence; JSON store is single-process.
Usage: Sonnet 2 observable CLI calls (G1-C1/G1-C2), 359.922 seconds, $1.0399862 total reported list-price estimate; actual subscription charge unknown. Sol usage/cumulative turns unknown; Opus/Astra 0. No additional model call for approval. CLI estimate limits do not prove a hard cap on subscription charges.
Git: intended Gate 1 files reviewed/committed/pushed through verified normal main workflow; final hash/sync is recorded at the next boundary. Next: Gate 2 digital PDF component on permissible fixture.

## Gate 2 | 2026-09-30T16:21:24.348461+00:00 | software acceptance

**PASS (construction fixture; Git closure follows).** Digital PDF CLI produces schema 3 source-linked text/bboxes/page renders and a side-by-side escaped HTML comparison; schemas 1/2 remain readable. Contract: contracts/gate_2.md. Evidence: 59 unit/negative/contract tests pass; actual two-page PDF CLI extract/inspect exit 0; both page PNGs visually checked against all expected lines, heading, footnote, citation, numbers and formulas. Stable IDs, relocated source bytes, changed versions/hash, blank/encrypted/corrupt PDF and geometry checks pass.
Fixes: G2-A1/A2; lazy dependency loading and required PDF geometry corrected directly by Sol. Limitations: basic reading order/layout_unverified; no multicolumn/Japanese vertical or real scholarly quality proof. No automatic semantic approval.
Models: Sonnet 1 call G2-C1, actual claude-sonnet-5 plus reported auxiliary Haiku, 245.828 s; $0.6193292 reported list-price estimate, actual charge unknown; Sol usage unknown, Opus/Astra 0. Builder exit 0; temporary launcher delivery printing failed cp1252 after audit capture, fixed locally (not a model failure). 25 tools exceeds soft 20 guidance, below instruction limit 60; no hard subscription cap claimed.
Git: intended diff reviewed; commit/synchronization receipt follows. Next: local OCR on image-only fixtures; real quality remains preliminary.

## Gate 3 | 2026-09-30T17:14:20.090688+00:00 | retrospective configured-engine finding

**FIX (superseded by acceptance below).** G3-C1 delivered OCR; 79 initial tests and then 80 boundary tests passed. Configured best-language directory CLI returned page-level malformed_output despite engine exit 0. A small deterministic reproduction showed plain text rather than TSV: standalone traineddata lacks configs/tsv. No Gate 3 PASS was granted on unit tests alone. Source images and needs_human guards remained intact. Next: explicit TSV renderer flag, real regression and retest (G3-A3); no extra model call.

## Gate 3 | 2026-09-30T17:14:20.094521+00:00 | construction acceptance

**PASS (software construction; Git closure follows).** Deliverable: public ocr-pdf CLI, local Tesseract fallback on selected pages, immutable base extraction plus OCR schema-1 bundle with PDF/image hashes, engine/language/model identity, image and PDF word boxes/spans, warnings and per-page errors. Contract: contracts/gate_3.md.
Evidence: 81 unit/contract/negative/integration tests exit 0, including installed real engine and standalone-weight regression; en/fr/ja CLI runs exit 0 (1.672/1.671/1.922 seconds) on six actual image-only PDF pages. Exact word span slices/PDF bounds/source preservation verified; clear sentinels recognized; degraded English/French empty and Japanese low_confidence. Rendered degraded French and clear Japanese images visually checked. Engine/timeouts/malformed/low-confidence outcomes retained for human review; digital pages skipped by default.
Fixes: G3-A1/A2/A3 preserved; finite timeout/geometry checks, explicit TSV renderer and accurate not_selected skip reason completed directly by Sol. No second model or debate.
Warnings: synthetic fixtures establish no real scholarly OCR accuracy; Japanese engine spacing is retained and no reconstruction is approved; all OCR pages needs_human and eligible_for_translation=false. Tesseract is locally installed in Program Files (requested location ignored); weights/inputs/cache/output remain uncommitted.
Models/cost: Sonnet 1 external call G3-C1, actual claude-sonnet-5 plus reported auxiliary Haiku, 264.5 seconds, exit 0, verified implementation value by tests/live CLI; $0.7346634 reported list-price estimate, actual subscription charge unknown. Sol cumulative usage/time/charge unknown; Opus/Astra 0. No paid runtime API. 22 tools exceeds soft 20 guidance, below instruction limit 60; no hard subscription-dollar cap claimed.
Git: reviewed intended diff only; verified gate commit/push and separate receipt follow. Next: STOP before Gate 4, as explicitly requested by user; no Gate 4 contract or implementation started.

## Gate 3 | 2026-09-30T17:17:05.311813+00:00 | verified Git closure

**PASS (software construction).** Acceptance evidence above: 81 tests and live en/fr/ja OCR fixtures; source preservation and human-review guards pass. Gate commit 3a1577b77cad0ad5f2552dd60ae659cc145ebf17 normally pushed and remote equality verified; intended diff/credential-pattern checks passed, tree clean. One Sonnet call, reported list estimate $0.7346634, actual charge/Sol usage unknown, Opus/Astra 0. No real scholarly accuracy claim. Next: STOP before Gate 4 as requested; Gate 4 not started.

## Gate 4 | 2026-09-30T17:50:24.151666+00:00 | preflight checkpoint

**BLOCKED (instruction ownership / Git preflight, not a software failure).** Gates 1-3 remain passed; main synchronized at a5aa8f82598d477820a7a6ebeeeeb846e233c3db. Three unexpected instruction changes reviewed (AGENTS.md, ARCHITECTURE.md, model strategy); user confirmation pending. Gate 4 contract/implementation not started; no new tests or external model calls, Sol usage unknown. Git operations stopped under repository rule; files preserved untouched. Next: clarify intentional adoption, then verified instruction commit and Gate 4 source/segmentation contract.

## Gate 4 | 2026-09-30T17:57:17.704801+00:00 | documentation preflight resolved

**PASS for documentation verification only; Gate 4 software not yet implemented.** User confirmed intended package. Exact package/baseline hashes and full proposed documentation diff checked, no discrepancies. Source handoff map adopted; profiles deferred to Gates 6-7, scholarly only. Previous preflight BLOCKED preserved. Model calls 0; Sol usage unknown. Intended documentation/audit commit and normal synchronization follow; next define smallest Gate 4 source-resolution/segmentation contract.

## Gate 4 | 2026-09-30T18:51:44.071102+00:00 | PASS (software construction)

- Deliverable: validated digital/OCR source alternatives, explicit human-selected readings, exact source-linked line/merge/split units and complete revision history. Contracts: contracts/gate_4.md, gate_4_fix.md; immutable Document schema 3/OCR schema 1 -> derived structure schema 1. No profile/literary/translation implementation.
- Evidence: 109 tests pass (12.526s); six original and 25 focused provenance/replay probes pass. Public CLI unresolved 2 pages/0 units -> synthetic human decisions 12 units -> merge 11 units -> persisted inspect with zero findings; source bytes unchanged. Gate-3 live construction bundles en/fr/ja validate and remain unresolved without human choice. Producer/consumer/current/history negatives reject bad hashes, page bindings, anchors, stale decisions, omissions/duplicates and model actors.
- Failures/fixes: G4-A1/G4-C1 passing basic suite exposed six contract gaps; G4-A2/G4-C2 repair failed (5 errors/1 failure). Reassessed locally; Sol G4-A3 shared validation and independent evidence/text hashes pass. No repeated model retry/escalation.
- Usage: Sol conductor internal model/tokens/time unknown; Sonnet 2 scoped calls (actual claude-sonnet-5) with auxiliary Haiku usage reported in both CLI invocations (internal auxiliary call count unknown), 650.453s model wall time. Observed Gate 4 work window: 49.7 minutes. Opus 0, Astra 0. Reported list-price estimate $1.894693; actual charges/quota unknown, no hard actual-charge cap claimed. IDs/usage: model_calls.jsonl and attempts.jsonl.
- Warnings: construction fixtures do not prove scholarly OCR/translation accuracy. Human fixture decisions are simulated. Pure consumer checks declared evidence/internal consistency, not image bytes or actor authentication. Default source lines do not resolve scholarly paragraph order/footnote association; real ambiguity stays human-owned.
- Git: 129debaa9f922258ae810f5a42032c30f6117115 reviewed/committed and normally pushed to the verified intended origin/main; remote hash equality and clean tree verified. Separate receipt preserves this hash without self-reference.
- Next: Gate 5 small terminology/approved-memory contract under supervised autonomy; no human decision needed for routine transition.

Receipt preflight 2026-09-30T18:53:02.444701+00:00: trailing blank-line check corrected by this append-only note; gate acceptance and synchronized code commit unchanged.

## Gate 5 | 2026-09-30T19:19:22+00:00 | software verified, Git ownership hold

**BLOCKED for gate closure (unexpected unrelated edit).** Versioned source-bound glossary, explicit human reviews, scoped applicable-policy fingerprint and exact human-approved memory are implemented behind pure functions and the terminology CLI. Contract: contracts/gate_5.md. 125 tests pass (12.492s latest), including constructed PDF/structure/CLI round trip, negative history and actor cases, affected-rule invalidation and unrelated-unit reuse. Synthetic decisions are not real scholarly approval. One Sonnet CLI invocation with reported auxiliary Haiku usage, 356.25s and $0.9519952 list estimate; actual charge/Sol usage unknown, Opus/Astra 0. Intended Gate-5 diff reviewed; no gate commit/push yet because tests/test_structure.py contains an unattributed EOF blank line outside Gate-5 ownership. That line remains untouched. Next: obtain exact disposition of the unrelated line, then staged review and verified Git closure; advance only after clean tree.

## Gate 5 | 2026-09-30T19:21:00+00:00 | ownership resolved, construction acceptance

**PASS for software construction; Git closure follows.** User authorized exact removal of the unrelated EOF blank line; tests/test_structure.py matches HEAD, and complete unstaged diff passes whitespace check. The preceding BLOCKED card is superseded only for this ownership issue. Acceptance remains 125 passing tests and scoped memory invalidation; real glossary/translation judgments remain human-owned. One Sonnet invocation as recorded above, actual charge unknown; no additional model call. Stage only Gate-5 code, tests, contract, documentation and audit, then verified commit and normal push before Gate 6.

## Gate 5 | 2026-09-30T19:26:42.341486+00:00 | BLOCKED (concurrent writer / integration and Git closure)

This-session checkpoint supersedes no historical evidence silently. Glossary/approved-memory working implementation exists under contracts/gate_5.md; G5-A1 defects and G5-A2 local repair recorded. Last suite: 132 tests passed in 13.500s; final tree verification pending after latest CLI guard. One Sonnet CLI call, auxiliary Haiku reported, 356.25s, $0.9519952 list estimate; actual charge/Sol usage unknown, Opus/Astra 0. Another writer changed shared tests and append-only audit and claimed approval absent from this conversation. Gate-5 code/audit remain uncommitted; no PASS for gate closure, no Gate 6. Next: user assigns one active conductor, then inspect exact current diff, rerun relevant checks and perform normal verified Git closure. Real scholarly judgments remain unapproved.

## Gate 5 | 2026-09-30T19:45:31+00:00 | construction acceptance after sole-conductor verification

**PASS for software construction; Git closure follows.** User chose this session as sole conductor. The preceding concurrent-writer BLOCKED card is resolved, and both sessions' G5-A1/A2 evidence remains preserved. Complete current-tree suite passes 134 tests (13.043s), including exact source/unit/version/policy memory binding, scoped invalidation, history corruption, conflicting memory targets, and CLI protection of source PDF bytes. Public CLI uses synthetic human selections and approvals; no real scholarly quality claim. One Sonnet CLI invocation with reported auxiliary Haiku usage, 356.25s, $0.9519952 list estimate, actual charge/Sol usage unknown; Opus/Astra 0. Intended paths and staged diff require final Git review, commit and normal verified push before Gate 6.

## Gate 5 | 2026-09-30T20:01:22+00:00 | verified Git closure

**PASS (software construction).** Acceptance: 134 tests pass, source-linked versioned terminology and exact approved memory meet Gate-5 contract on synthetic fixtures. Real scholarly approvals remain human-owned. Source commit a355837f3fac92c1ab5086963f752af15a774753 and audit receipt 522bcb79d8a242b1fb54b841c339ab17b0431f10 normally pushed to verified intended origin/main; post-push remote equality and clean tree confirmed. One Sonnet CLI invocation with reported auxiliary Haiku usage, $0.9519952 list estimate; actual charge/Sol usage unknown, Opus/Astra 0. Next: Gate 6 first-translation contract; no paid runtime provider enabled.

## Gate 6 | 2026-10-01T02:53:11+00:00 | BLOCKED (required runtime credential)

**BLOCKED for Gate-6 acceptance.** Diagnostic request/result schema, mock adapter, optional `gpt-6-luna` Responses adapter and public CLI are implemented under contracts/gate_6.md. Full suite: 168 tests pass (12.610s); public mock probe succeeds with unapproved, non-billed placeholder. G6-A1/A2 preserve initial defect and local repair evidence. No real OpenAI call occurred: OPENAI_API_KEY is absent in process/user/machine environment and optional SDK is not installed. One small synthetic live call remains mandatory for PASS. One successful Sonnet builder invocation with auxiliary Haiku reported, $0.5961736 list estimate and actual charge unknown; one sandbox connection failure had no observed model use. Sol internal usage unknown; Opus/Astra 0. Intended diff remains uncommitted and unpushed under the central prompt's BLOCKED rule; Gate 5 main/origin synchronization is unchanged. Next: when key is locally available, install optional SDK, verify live-call preflight, run exactly one bounded probe, record usage, rerun acceptance and perform reviewed normal Git closure. Gate 7 has not started.

## Gate 6 | 2026-10-01T04:03:21+00:00 | PASS for software acceptance, Git closure follows

The preceding credential BLOCKED card is superseded for acceptance. G6-R1 completed exactly one real synthetic gpt-6-luna Responses probe: status completed_unapproved, 3.969s, 18 input/7 output tokens, $0.0000053 standard list estimate, actual charge unknown. The result is unapproved and proves provider access/usage plumbing only, not scholarly translation quality. Full suite 168 tests pass (13.621s); public mock and live CLIs both worked. G6-C1/C2 and G6-A1/A2/A3 retain builder failure, builder cost, local repair and live evidence. Developer reported list estimate $0.5961736 from one successful Sonnet invocation with auxiliary Haiku; Sol usage/actual charge unknown, Opus/Astra 0. Git diff review, commit and verified normal push remain before Gate 7.

## Gate 6 | 2026-10-01T04:25:38+00:00 | verified Git closure

**PASS.** Full and staged diff checks passed; 168 tests and the one G6-R1 live diagnostic meet the written software acceptance. Commit b241f67d57d04df9a5aa79811230e8310a49771e was normally pushed to verified intended origin/main; post-push fetch confirms hash equality and a clean tree. Only synthetic provider access was demonstrated; scholarly quality remains unapproved. Gate 7 may start under supervised autonomy.

## Gate 7 | 2026-10-01T05:38:41+00:00 | PASS for software acceptance, Git closure follows

Source-bound scholarly first-draft job, bounded same-reading context, applicable approved glossary prompt, mock/OpenAI text boundary, exact policy/cache identity, conservative shared runtime budget and deterministic formal findings work through a public CLI. Full suite: 213 tests pass (13.501s); public mock CLI succeeds. G7-C1 builder cost $1.3226808 reported list estimate, actual charge unknown, with auxiliary Haiku; G7-A1/A2 retain initial 203-test failure (2 failures/1 error) and focused local repair. Three real synthetic gpt-6-luna calls G7-R1/R2/R3 produced Hebrew `draft_unapproved` results for en/fr/ja, zero formal findings and no human approval; 306 input/38 output tokens total, $0.0000496 standard list estimate under $0.01, actual charge unknown. No retries; key removed after process run. These source records use synthetic PDF envelopes and simulated source/glossary decisions, so they demonstrate software construction, not real PDF extraction or scholarly meaning. Sol internal usage unknown, Opus/Astra 0. Review complete/staged diff and normally commit/push before Gate 8.

## Gate 7 | 2026-10-01T05:45:05+00:00 | verified Git closure

**PASS.** Complete and staged Gate-7 paths reviewed; whitespace and credential-prefix checks passed. The 213-test suite and three bounded synthetic language probes meet the written software acceptance. Commit 9d016fbdcc2606b55f2f95cde7eaff889ee12ff9 was normally pushed to the verified intended origin/main. Post-push fetch confirms local/remote hash equality and a clean tree. Translation meaning and human approval remain unverified. Gate 8 may start under supervised autonomy.

## Gate 8 | 2026-10-01T06:12:32+00:00 | PASS for software acceptance, Git closure follows

Conditional risk routing, canonical Gate-7 draft binding, exact source-to-target critic claims, false-positive display, one correction with formal recheck, and unresolved human handoff work through the public mock CLI. Full suite 233 tests passes (13.385s); saved synthetic en/ja drafts remain unapproved. G8-C1 builder used $1.9372894 reported list estimate, actual charge unknown, including auxiliary Haiku; G8-A1/A2 preserve the initial two failures and focused repair. Runtime provider calls 0, Opus/Astra 0, Sol usage unknown. Software construction is accepted; fake lexical review is not evidence of real semantic accuracy. Complete Git review and normal commit/push before Gate 9.

## Gate 8 | 2026-10-01T06:18:52+00:00 | verified Git closure

**PASS for software construction.** Full and staged diffs reviewed; whitespace and staged credential-pattern checks passed. Final 233-test suite and public mock CLI meet the written offline acceptance. Commit 35ba2acf33b627c53de2509e5953ebff83ba460c was normally pushed to verified intended origin/main. Post-push fetch confirms local/remote hash equality and a clean tree. Real semantic accuracy and human approval remain unverified. Gate 9 may start under supervised autonomy.

## Gate 8 | 2026-10-01T06:23:47+00:00 | architecture correction before Gate 9

The preceding PASS lacked the versioned review-policy/cache identity required by ARCHITECTURE.md. G8-A3 adds it without changing draft/source or granting approval. Targeted 21-test and full 234-test suites pass; reviewed Git closure follows. The earlier receipt remains a valid record of its then-observed checks, not evidence this dependency was already implemented.

## Gate 8 | 2026-10-01T06:26:15+00:00 | architecture correction verified Git closure

**PASS with G8-A3 correction.** Reviewed complete/staged seven-path diff, passed whitespace and credential-pattern checks, then normally pushed commit fa95651ba3463e6483c5b586775a29657c2aba43 to intended origin/main. Post-push fetch verifies hash equality and clean tree. The versioned review policy/cache identity is now in request, result and test. Gate 9 may start.

## Gate 9 | 2026-10-01T07:20:26+00:00 | PASS for offline software construction, Git closure follows

Local review page, explicit per-unit human decision with source/draft/review hashes, and escaped bilingual HTML export work through three public CLI commands. The page shows source PDF/OCR evidence, Hebrew, flags, glossary and correction history; it can download a decision JSON but cannot approve by itself. Targeted 19 and full 253 tests pass (14.429s). One ignored synthetic test-only decision was accepted and exported; no real person approved a translation. G9-C1 Sonnet builder with auxiliary Haiku reported $2.1967838 list estimate, actual charge unknown; G9-A1/A2 preserve initial duplicate-decision failure and focused repair. Runtime calls 0, Opus/Astra 0, Sol usage unknown. Browser visual inspection was blocked by automatic approval review of a personal Edge window; generated HTML and public CLI were checked offline. Real scholarly quality and human review remain pending. Review full/staged diff and normally commit/push before Gate 10.

## Gate 9 | 2026-10-01T07:26:05+00:00 | final offline recheck, Git closure follows

After adding source-evidence output protection and a source-unit anchor in export, the full 253-test suite passed again (14.203s) and the public synthetic export succeeded. The earlier software acceptance remains preliminary for real visual appearance and human judgment. Review complete/staged diff and normally commit/push.

## Gate 9 | 2026-10-01T07:29:41+00:00 | final decision-history recheck, Git closure follows

Prior and latest decision records now verify their own content hashes before supersession/export. The full 253-test suite passes again (13.387s), including tampered-history rejection. Software construction remains unapproved for real scholarly quality and visual browser appearance. Reviewed Git closure follows.

## Gate 9 | 2026-10-01T07:32:14+00:00 | verified Git closure

**PASS for offline software construction.** Complete and staged ten-path diffs reviewed; whitespace and credential-pattern checks passed. The final 253-test suite and public synthetic render/decision/export CLI meet the software acceptance. Commit bda6f337e54fd1352468515b76075116e255a5e8 was normally pushed to intended origin/main; post-push fetch confirms local/remote hash equality and a clean tree. Actual human approval, visual browser appearance and scholarly quality are not established. Gate 10 may assess real pilot prerequisites.

## Gate 10 | 2026-10-01T08:17:36+00:00 | PRELIMINARY software checkpoint; full quality gate BLOCKED

The deterministic `evaluate-pilot` CLI validates a human-labeled manifest and computes per-language/genre error, correction-time, cost and latency metrics with per-unit context/critic comparisons. Distinct fully reviewed source segments determine the 72/24 thresholds; the report never selects a model or routing policy. G10-C1 and G10-A1/A2 record the builder and focused conductor verification repair. Final full suite: 291 tests passed in 13.578s; tests use synthetic annotations and demonstrate software arithmetic only. Six licensed public source candidates are indexed, with retrieval/genre caveats. No actual source spans or Hebrew references have expert approval, and no blinded MQM labels, correction times or bounded real model comparison exist. Thus the requested Gate-10 per-language quality recommendation and transition criterion are **not met**. Sonnet builder reported $1.5686432 list estimate (actual charge unknown); runtime calls 0, Opus/Astra 0, Sol usage unknown. Commit the reviewed harness as explicitly preliminary, then pause at Gate 10 pending genuine gold evidence and human evaluation.

## Gate 10 | 2026-10-01T08:34:34+00:00 | final offline recheck; status unchanged

An approved Hebrew reference must contain Hebrew script. The added negative test passes; final full suite is 292 tests in 13.852s. This supersedes the earlier test count, not the preliminary/BLOCKED quality decision. No new paid call. Reviewed preliminary Git checkpoint follows.

## Gate 10 | 2026-10-01T08:40:23+00:00 | accounting correction; status unchanged

Staged review separated direct expert MQM findings from critic true positives and counted those findings in the critical-error metric. Targeted 40 and full 293 tests pass (14.725s); severity key order is deterministic. Prior 291/292-test results remain historical checkpoints. No real gold set or model comparison; full Gate 10 stays BLOCKED.

## Gate 10 | 2026-10-01T08:45:56+00:00 | preliminary checkpoint Git receipt

The reviewed offline harness and source-candidate index were committed as `b703dbba1b477059092165238c1e5caf4a52b038`, normally pushed to authorized origin/main, fetched, and verified equal with a clean tree before this receipt. Final full suite: 293 tests. **Gate 10 remains BLOCKED for quality acceptance**; no genuine 72-segment gold set, expert MQM evaluation, measured model comparison or routing recommendation exists. The commit is an unapproved software checkpoint, not a quality-pass version.

## Gate 10 | 2026-10-01T09:40:12+00:00 | corpus preparation complete; quality BLOCKED

Under the user request to continue, G10-A3 acquired six publisher PDFs and prepared 72 distinct local candidates (24 per language) and 18 two-page context plans. Independent checks pass for six PDF hashes, 62 re-extracted readings, 72 exact nonoverlapping spans, 18 page-bound contexts and 108 image links. Seven source-page visual spot checks informed crop geometry; all source/reference/word-count/MQM approvals remain empty. Technical mathematics, history-of-mathematics and poor-OCR coverage is absent. G10-A4 closes renamed duplicate-source-span inflation; focused 42 and full 295 tests pass (14.627s). Public real-PDF extraction succeeds; public evaluator rejects the candidate schema. Contract audit/contracts/gate_10_corpus.md; evidence audit/gate_10_corpus_preparation.md. New paid/model calls 0; Sol usage not metered. Preparation acceptance met; full Gate 10 BLOCKED on human evidence and measured comparison. Review and commit only preliminary metadata/helper/correction; no Gate 11 transition.

## Gate 10 | 2026-10-01T09:47:16+00:00 | preliminary corpus checkpoint Git receipt

Complete/staged eleven-path diffs, exact staging, whitespace, credential-pattern and append-only-history checks passed. Commit `628fca1adcffbcddda775308dc83c90d34a22cd7` was normally pushed to checked intended origin/main; fetched remote equality and a clean tree verified. No PDF, excerpt, page image, gold reference or label was staged. Full 295-test software result and independent corpus checks stand; Gate 10 quality remains BLOCKED. Next required evidence is expert-approved sources/Hebrew references, representative sampling and blind measured comparison. This receipt records preparation closure, not quality acceptance.

## Gate 11 | 2026-10-01T10:52:45.290966+00:00 | Gate Card: software PASS, Git closure BLOCKED

Gate 11 independent software acceptance PASS; Git closure BLOCKED pending ownership/authorization of six concurrent UI files. Final established repository suite plus Gate 11: 338 tests passed in 17.760s (runner wall 17.766s); focused 128 previously passed in 3.563s. Earlier discovery 341 included three concurrent UI tests and is superseded for Gate-11-only accounting; the provisional two-UI-test statement was incorrect. The first explicit-module runner omitted discovery's fixture import path (three import errors, 273 tests); corrected its ignored helper only. Final integrity validation reconciles attempted/settled counts, outstanding holds, observed spending and frozen state with durable reservations/settlement events. Public CLI outputs/gate11_demo_v2: translation plus critic/corrector reserve and settle exactly three synthetic dispatches under one fixed task, repeated commands add three linked cache hits with zero current usage/cost, zero outstanding hold and zero paid provider calls. Corrected reviews remain corrected_unapproved; Gate-9 resolver accepts cached provenance without granting approval. Metadata-event privacy and public read-only status verified. Initial capitalized fixture remains superseded bypass evidence. G11-C1: one Sonnet invocation with auxiliary Haiku, 561.141s, $1.902547 reported list estimate (ceiling $3), actual charge unknown. Sol local corrections/verifications not metered; Opus/Astra 0, runtime paid calls 0. No second builder call. Input manifest gate_11_builder_scope.json is preserved as the original pre-send snapshot; its not_sent status describes the initial rejected attempt, followed by explicit user approval and actual G11-C1 recorded in histories/model events. Six unexpected files appeared around 10:30-10:35 UTC; no Git mutation performed. User clarification asks permission to preserve UI files and commit only intended Gate 11 paths. Latest known synchronized base remains a770b8316855371da04992c8c9effa5f3739cfc4; no claim of committed/clean/pushed Gate 11. Gate 10 human quality remains BLOCKED: no gold references/blind expert judgments, coverage gaps or measured model comparison. Dated list reservations are not account billing guarantees.

Unexpected paths: UI_README_HE.md, run-ui.ps1, scholarly_translation/gui.py, scholarly_translation/web_ui.py, tests/test_web_ui.py, audit/contracts/ui_local.md.


## UI-SIMPLE | 2026-10-04T13:17:34.849140+00:00 | Gate Card: software PASS, browser limitations recorded

User-directed upload-to-download flow implemented with separate unapproved/source-unreviewed document-draft@1 records. PDF text/EPUB spine input; actual model/effort/cap settings; durable reservations/raw cache; progress/recovery; immediate escaped HTML/TXT downloads; optional revisioned edits. Removed sidebar, stage tracker and generic command fields from homepage. First tall visual layout was reduced so upload/translate fit on the observed laptop viewport; 390x844 settings/result/review layout also inspected. Demo explicitly says no translation/API. Windows launcher syntax/dependency imports verified, including project runtime fallback; updated Hebrew guide and architecture boundary.

Evidence: UI-SIMPLE-A1/A2; focused 64 tests in 7.616s; full 363 tests in 27.333s; final HTTP seven tests in 4.277s after unused command-config removal. First engine Windows sharing failure and HTTP fixture indentation repair remain preserved above. Browser confirms sample completion, saved optional edit, model/effort choice, preferences and reopening a saved result. Browser extension denied automated file chooser setFiles (Allow access to file URLs unavailable); download event capture timed out. Automatic approval review rejected general Edge download-history inspection over unrelated private filenames. No workaround attempted. Uploaded bytes and both attachment formats/content are verified through guarded HTTP tests; end-to-end browser picker/download capture remains unverified. No paid quality/account-access test.

Sol single local writer; new Sonnet/Opus/Astra/runtime paid calls 0, list runtime test cost 0, Sol usage unknown. Existing Gate-11 Sonnet invocation remains separately recorded; no new builder. Gate-10 human quality BLOCKED, no model winner/research approval or OCR/layout-reconstruction claim. Complete diff, append-only logs, JSONL, credential-pattern and whitespace checks pass. Intended origin/main fetched and equal to main 2574e01; Git closure now proceeds with a focused Gate-11 dependency commit then UI commit and receipt. Prior ownership blocker is resolved by tracked UI commits and explicit user repair request; intentional UI work stays pending during dependency commit, no intermediate clean-tree claim.

## Gate 11 | 2026-10-04T13:20:00+00:00 | dependency commit receipt

Commit 912593237e8df77a057f1284461c73537e5f0ac5 records the reviewed/passing persistent controls and historical audits. Fourteen explicit staged paths matched reviewed working content; whitespace/privacy and fetched-base checks passed. Prior ownership blocker resolved; remaining UI paths are authorized intentional integration. UI documentation/commit and ordinary push follow before final clean-tree receipt. No paid runtime request or additional builder invocation.


## Gate 11 / UI-SIMPLE | 2026-10-04T13:23:18.603047+00:00 | final Git receipt

Gate-11 dependency 912593237e8df77a057f1284461c73537e5f0ac5 and simple-document UI c5f754b354ff9d540476dabd6572131a2b9c2ee5 normally pushed to verified authorized origin/main (https://github.com/neria-baris/scholarly-translation.git). Complete diffs reviewed; fourteen dependency and sixteen UI staged paths matched reviewed working content. Whitespace, append-only histories/JSONL and credential-pattern checks passed; no ignored inputs/results/keys staged. Ancestry checked, no divergence or unexpected changes. Fetch verified main=origin/main=c5f754b354ff9d540476dabd6572131a2b9c2ee5 and clean tree before this receipt. Receipt's own hash is intentionally not embedded.

Software acceptance: full 363 offline tests pass (27.333s), focused 64 (7.616s), final HTTP seven (4.277s). Desktop/390x844 layout, clearly labeled demo completion, optional saved edit, model/processing preferences and saved-result reopening observed. HTTP upload/download attachment content passes. Browser file selection denied by extension permission; download-event capture timed out and general history inspection was automatically rejected over unrelated private filenames. Those browser capture limits remain recorded; no bypass or paid API test. Current-code owned preview http://127.0.0.1:54984/ (session 4937) left open as deliverable, prior previews stopped. Gate-11 software Git blocker resolved; Gate-10 human quality remains BLOCKED, no approved scholarly output/model winner/release claim. New builder/adviser/paid runtime calls 0; Sol usage not metered. Final receipt push/equality/clean verification follows without further feature work.

## Session C | 2026-10-04T14:05:43.7546992+00:00 | software PASS, Git closure follows

**PASS for offline software construction.** Optional unit review supports explicit `off`, `risk_based` and `all` modes; candidate experiments accept two or three anonymous translations and preserve `NO_CLEAR_WINNER`; chapter QA is explicitly `off`/`on` and returns only grounded local issues/corrections. Three supplied runtime prompts are versioned byte-identical assets with hashed identity; free-form sections receive appended parse contracts. Records are unapproved, input/policy/prompt/provider/model provenance is explicit, malformed or ungrounded model output fails closed, and skipped paths make no adapter call. Focused 31 tests pass in 0.094s; full 394 pass in 27.758s with one existing skip; compile, whitespace and asset-hash checks pass. SC-C1 Sonnet plus auxiliary Haiku took 294.150s and reported $0.8383876 list estimate; actual charge unknown. Runtime paid calls 0; Sol usage not metered; Opus/Astra 0. Real reviewer compliance/accuracy, scholarly quality and human approval remain unverified. Review exact/staged paths, commit and normally push before the receipt; Gate 10 remains BLOCKED on genuine expert evidence.

## Session C | 2026-10-04T17:32:09.7461546+00:00 | verified Git closure

**PASS for offline software construction.** Reviewed feature commit `fd5c852af241c6705ab4ec1bbb0d6ff5ac36b7cb` was normally fast-forward pushed to the authorized `origin/main`; a post-push fetch verified exact local/remote equality and a clean worktree. Thirteen explicitly staged paths contained only the Session C contract, module, three LF-pinned supplied prompt assets, 31-test suite, README and append-only audit/checkpoint records. Staged whitespace, JSONL, secret-pattern, prompt-hash and ancestry checks passed. Final acceptance remains 31 focused and 394 full offline tests with one existing skip. No paid runtime call, model choice, human approval or scholarly-quality claim was made. Gate 10 remains BLOCKED on genuine expert evidence. The receipt commit's own hash is verified after creation rather than embedded here.
## PROVIDER-MODEL | 2026-10-04T14:09:56.2295443Z | Gate Card: software PASS, Git closure pending

Session E contract implemented as an independent product slice. Versioned JSON assigns arbitrary model IDs and per-model capability metadata to translator, semantic reviewer, chapter QA, candidate evaluator and optional context-state roles. OpenAI Responses, Anthropic Messages, DeepSeek chat-compatible and named OpenAI-compatible adapters share one result boundary; credentials remain named environment references, custom URLs reject embedded credentials, and missing setup has no fallback. Translation and semantic-review CLI resolve role configuration, preserve legacy mock/OpenAI commands, bind provider/model/capabilities into cache identity and record requested/observed provenance. Existing prompt, segmentation, QA and context logic are unchanged.

Evidence PM-E-A1/A2: builder connection refused before execution (PM-E-C1: zero tokens/cost/value); Sol local implementation. New mocked tests cover role independence/reuse, capability override, four adapter dispatch paths, missing credentials, no fallback, cache identity and priced/unpriced durable behavior. Focused 122 pass; full 378 pass in 27.509s, one established skip; whitespace check passes. No live runtime provider call. Non-OpenAI price tables are not invented: token usage is retained, pricing is `not_metered`, the reservation remains/further calls stop, and the response is not cached. Compact whole-document browser flow remains explicitly OpenAI-only; multi-provider role configuration is exposed through JSON and scholarly CLI, without low-level API settings on the upload screen. Gate 10 quality remains BLOCKED; no model winner or release-quality claim. Reviewed commit/push receipt pending.

## PROVIDER-MODEL | 2026-10-04T17:42:41.1456277Z | upstream integration PASS

The unpublished Session E commit was rebased onto verified Session C receipt 4bf8482 after origin advanced. Both append-only histories and model/attempt events were preserved. Session C's actual optional unit review, candidate comparison and chapter QA now resolve `semantic_reviewer`, `candidate_evaluator` and `chapter_qa` through the shared configuration, can build the configured adapter only on invoked paths, and record requested/observed provider/model plus capability provenance. Prompt assets, routing, strict parsing and unapproved status are unchanged; skipped policies still make no call. PM-E-A3 focused 158 and full 412 tests pass in 24.463s with one established skip. No live runtime call. Prior 378-test Session E result is superseded for final combined acceptance. Integration commit and ordinary push remain pending.

## PROVIDER-MODEL | 2026-10-04T17:46:34.2724439Z | verified Git closure

Feature commit `a705e0a51ad8bb3b19ed9644cf7b0c69a7934631` contains the reviewed Session E contract, role configuration/example, provider adapters, translation/review/Session-C consumer integration, tests, documentation and append-only audit evidence. Eighteen paths were reviewed; staged whitespace, JSONL, append-only-prefix, credential-pattern, full-diff and ancestry checks passed. The commit was rebased only while unpublished onto verified Session C receipt `4bf8482`, then normally fast-forward pushed to authorized `origin/main`. Post-push fetch verified exact HEAD=origin/main equality `0 0` and a clean tree. Final acceptance is 158 focused and 412 full offline tests (24.463s; one established skip), zero live runtime calls, and no quality/model-winner claim. This receipt's own commit/hash is intentionally recorded by the following equality check rather than self-embedded.

## INTEGRATION-BOOTSTRAP | 2026-10-04T18:32:32.8673597Z | continuity software PASS

Minimal CLAUDE.md points to existing policy/checkpoint and the authoritative D/X/F/G file; handoff helper resolves the repository from its own path, validates required files/Claude, supports non-launching ValidateOnly and starts a separate native Claude background session only on actual handoff. Syntax and ValidateOnly pass. Existing main baseline 412 tests pass. No model call or competing audit/workflow introduced. Git closure follows; next action is sequential A integration after fresh verification, then B and independent D/X under existing limits.
## SESSION-A | 2026-10-04T17:50:29Z | Gate Card: software PASS, local Git closure follows

Default structure output is now versioned `structure@2`: conservative logical nodes for part/chapter/section/subsection/heading/subheading/paragraph/scene break/quotation/list/note/caption/formula/bibliography/page furniture, exact page-reading spans and PDF/OCR anchors, document order and parent hierarchy, explicit unit-to-node links, persisted semantic-unit policy, and source-exact paragraph reconstruction. Semantic units group adjacent paragraphs toward a 2,000-word heuristic, prefer structural boundaries and split oversized text at sentence boundaries. French/Japanese markers and non-space Japanese sizing are bounded heuristics, not semantic claims. Schema-1 artifacts remain validated and can start a fresh schema-2 lineage with a legacy fingerprint; existing unit shape and downstream terminology/memory/translation/review flows remain compatible.

Evidence: SESSION-A-A1/A2; focused structure 39 tests and final full 375 tests passed in 26.071s, with one optional OCR-weight test skipped. Negative tests reject hierarchy/order/policy/unit-node-link tampering; digital/OCR/unresolved, revision history, source continuity and local UI source/glossary paths pass. First oversized fixture exceeded page geometry and was corrected; first conductor mapping embedded node IDs in units and broke exact translation-memory shape, so links moved to a separate collection. One UI structure-stage allowlist was extended from schema 1 to schemas 1/2. No runtime provider call or scholarly quality claim.

Development calls: initial sandboxed Claude attempt failed after 179.994s with connection refused and zero tokens/cost. User then explicitly approved one restricted Claude Code invocation: Sonnet plus auxiliary Haiku, 1,336.161s, $4.6888078 reported list estimate, actual subscription charge unknown. Builder authored the first implementation without tests; Sol performed the focused repair and all verification, usage not metered. Opus/Astra 0.

Git: branch `agents/run-it`, base `36fbbf04e22bae2643b91956940c81a7cd2fc6ed`; complete diff/privacy/whitespace review passed. During the run `origin/main` advanced by four commits to `633c33d`; Session A did not merge/rebase other branches and is intentionally not pushed under the authorization limited to `origin/main`. Local focused commit and clean-tree verification follow. Gate 10 human quality remains BLOCKED and unaffected.

## SESSION-A | 2026-10-04T17:57:10Z | local Git receipt

Reviewed implementation/audit commit `8bc29b20a26f981b258fa9af91730a42ebef40c9` records the exact 15-path Session-A set after the passing 375-test suite, JSONL parsing, credential-pattern scan, staged-path equality and whitespace checks. The worktree was clean immediately after that commit. Branch `agents/run-it` is one local commit ahead and four commits behind current `origin/main=633c33d`; it has no upstream and was not pushed. No merge/rebase/force operation occurred. This short receipt's own hash is intentionally recorded only by final Git verification.

## INTEGRATION-A | 2026-10-04T18:36:48.879980+00:00 | software PASS

Validated clean A branch 8bc29b2/d7b6723 and scoped diff; isolated full 375 tests pass (31.290s, one skip). Merge into main 59235ee plus C/E produced only shared audit/checkpoint conflicts. Both append-only tails retained with base-prefix checks; no source or product conflict. Combined full 424 tests pass in 22.277s. B remains independently verified (375 tests, 29.246s, one skip), unmerged. Continuity bootstrap commit 59235ee syntax/ValidateOnly verified. Runtime/model calls 0; Sol quota/charges unknown. Reviewed A merge commit and authorized normal push follow. Source/quality limitations unchanged; Gate 10 human evidence BLOCKED.
## Gate 12 | 2026-10-04T14:09:17.6773072Z | Gate Card: software PASS, Git closure follows

**Gate and goal:** versioned `scholarly` and `literary` translation profiles from the supplied runtime prompt pack. **Built:** closed profile IDs and stable style prompts; explicit glossary/approved-decision, local-state, broader-source-context and TARGET UNIT layers; profile/context/prompt/config cache and provenance identity; structured `TRANSLATION` plus nullable `translation_note`; public CLI literary selection. Existing `translation-draft@1`/schema 1 stays compatible through additive fields, and all drafts remain unapproved. Architecture's earlier one-profile deferral is explicitly superseded only for this user-directed profile gate.

**Tests and evidence:** G12-A1/A2; baseline 88 focused tests; final 57 translation tests pass in 1.130s and full 375 tests pass in 30.922s with one unrelated existing skip. Negative coverage rejects unknown profiles and malformed/oversized supplied context; deterministic tests prove target-only instructions, glossary integration, structured uncertainty output, and cache changes for profile/prompt/config/context revisions. Runtime paid calls 0. G12-C1 was one Claude Code invocation: Sonnet with auxiliary Haiku, 631.031s, $1.3716102 reported list estimate below the $2 cap, actual charge unknown; Sol usage not metered, Opus/Astra 0. Contract wording `model_turns_hard: 1` meant one external builder invocation, but the CLI reported 48 internal turns; this accounting ambiguity is preserved as a deviation and no second call occurred.

**Limits/Git/decision:** No context selector, provider redesign, literary semantic-review policy, UI, chapter QA, real translation-quality test or human approval. Review components remain historically scholarly-oriented and are deliberately unchanged under this task's boundary. Complete six-path implementation/contract diff and added CLI correction reviewed; whitespace has only Git line-ending notices. **Decision: PASS for offline software construction;** exact staging and branch commit remain before closure. Gate 10 human quality remains BLOCKED independently.

## Gate 12 | 2026-10-04T17:35:56.2045346Z | verified branch-commit receipt

**PASS for offline software construction and requested branch closure.** Eleven explicit implementation, test, contract and audit paths were staged after complete and staged diff review; JSONL parsing, append-only-history prefixes, credential-pattern scan and whitespace checks passed. Commit `64f7ca6f77677add0c6943d25eba871f4be5cf83` records the versioned scholarly/literary profile gate on `agents/run-it-de649c23`; the worktree was clean immediately after that commit. Final evidence remains 57 focused and 375 full offline tests passing (one unrelated existing skip), with zero paid runtime provider calls. This isolated branch has no configured upstream and was not pushed; `origin/main` remains the known base at 36fbbf0. Receipt commit hash is intentionally not embedded in itself. Gate 10 human-quality BLOCKED status is unchanged.

## Gate 12 | 2026-10-04T17:38:28.8541358Z | upstream-status correction; integration stopped

The preceding receipt's `origin/main` statement was stale and is superseded only for remote status. Final verification found that another authorized session had pushed Session C commits `fd5c852`/`4bf8482` at 20:31–20:34 Asia/Jerusalem while this branch was closing. `agents/run-it-de649c23` is now two commits ahead and two behind `origin/main`; neither is an ancestor of the other. Gate-12 implementation and receipt commits remain intact and the worktree is clean, but no push, merge, rebase or guessed reconciliation was attempted. Software PASS stands; integration is stopped on the documented unexpected divergence for the later coordinated merge order.

## INTEGRATION-B | 2026-10-04T18:40:50.532460+00:00 | software PASS; reviewed Git closure follows

A merge a35d3ab normally pushed and fetched; main/origin equality 0 0 and clean tree verified. B isolated 375 tests pass (29.246s, one skip). Sequential B merge preserves both audit tails, both profiles and E role metadata. Resolved translation request signature, cache identity, canonical revalidation and result parsing by combining B context/profile inputs with E provider/capabilities and unpriced stops. CLI accepts literary and configured roles. Combined full 436 tests pass in 22.222s. Runtime/model calls 0, quota/charges unknown. Source/quality limits remain, Gate 10 BLOCKED. D/X await checked contracts/common base.

## SESSION-G | 2026-10-05T04:48:02Z | software PASS, local Git closure follows

**Scope:** final integration/repair per audit/claude_integration_conductor.md plus the 2026-10-05 persistent-state addendum; no redesign. **Fixed concrete integration defects, not features:** (1) `document_draft.py`'s per-document budget (`TranslationBudget`) covered translation only; `review_qa.py` unit-review/chapter-QA calls bypassed it entirely (unmetered, uncapped real spend) and never touched the existing persistent `runtime_controls.ControlStore`/cache at all. Replaced with one shared `ControlStore` task per document covering translate+unit-review+chapter-qa; `job["estimated_cost_usd"]` now updates from that store after every stage instead of staying frozen at `0.0`. (2) The worst-case budget reservation and `RuntimeCache`'s cache-key both hard-coded the single global `OPENAI_MAX_OUTPUT_TOKENS` constant regardless of a resolved role's own configured `capabilities.max_output_tokens` (`model_config.py`); `PersistentBudget`/`TranslationBudget.reserve()` now accept the real per-task/per-call output cap (`runtime_controls.py`, `translation.py`). (3) Wired Session C's chapter QA into Session D's `document_state.py`: extended `06_chapter_level_qa.md`/`review_qa.py` with a grounded, certainty-limited `STATE_UPDATES` structured-output section (never `established` from a model); `document_draft.py` now translates chapter-by-chapter, commits non-conflicting proposals via `document_state.find_conflicts`/`commit_update` between chapters, and threads the resulting state into the next chapter's translation requests. (4) Reconciled `export_epub.py`'s disconnected bespoke `epub-structure@1` path with the canonical schema-2 `document_structure` (new `export_epub_from_document_structure`, positional node matching, `units_merged_multiple_blocks` limitation) and wired `epub_extract.py` into `document_draft.py`/`web_ui.py`/`ui.html`/`ui.js`, so EPUB upload -> translate -> same-format download now works end-to-end (previously refused).

**Tests/evidence:** full suite 527 -> 549 tests pass (`python -B -m unittest discover -s tests`, `.venv` runtime with pdfplumber/reportlab/Pillow); new `tests.test_document_draft.ChapterQAPersistentStateTests` (10 tests, one per addendum scenario), two new budget/cache-wiring integration tests, two new real EPUB end-to-end tests (Auto and configured/thorough), five new `review_qa.py` STATE_UPDATES tests, five new `export_epub_from_document_structure` tests (translated text, multi-block merge limitation, 1:1 heading/list/quotation mapping, structure/archive-mismatch fail-closed, schema-version guard). Independently smoke-tested the live server (`scholarly_translation.web_ui`) end-to-end over HTTP: uploaded a real EPUB fixture, ran an Auto-mode job to completion, downloaded it, and confirmed the rebuilt archive is a valid zip with RTL attributes and the translated text correctly substituted into both a heading and a paragraph.

**Limits/decision:** did not build real per-model/per-provider pricing (only OpenAI is priced at all; this was already true before G and remains a documented limitation, see README.md's new "Translation context, chapter QA and persistent state" and "PDF/EPUB export and its limitations" sections); did not visually validate either exporter against real complex documents (footnotes, tables, formulas, mixed Hebrew-Latin) -- documented as an open limitation, not fixed. No redesign, no RAG/embeddings/Story Bible, no new orchestration. Runtime/model calls: 0 paid provider calls (mock/fixture-only plus the live local-server smoke test above); Claude Code usage not independently metered. **Decision: PASS for offline software construction;** staging/branch-commit and push follow. Gate 10 human quality remains BLOCKED and unaffected.

## SESSION-G | 2026-10-05T04:55:00Z | verified push receipt

Commit `55ae999c9c65a8954dd388879d6ca6a4e26db22c` records the Session-G integration set (22 paths) on `main`, built on `15426ec` (verified `origin/main` immediately before commit, no divergence). Pushed as a normal fast-forward; post-push fetch confirms `main == origin/main == 55ae999`. Working tree clean except two items intentionally left untouched and unstaged: `.claude/` (harness-managed) and `AUTOMATION_WORK_PLAN_HE.md` (a different, not-yet-owned future-phase plan that explicitly defers to this session; not authored or claimed by this session).

## 2026-10-05T05:39:57.642018+00:00 | AUTOMATION-1 | PASS (supersedes initial FIX)

- Contract: `audit/contracts/automation_1.md`; plan authorized plus model/key/cost addendum.
- Built: model catalogue/custom assumptions, offline tiktoken sizing, model-aware runtime costs, independent translation/QA fit, per-call caps, usage/truncation/credential-injection boundary.
- Verification:580 tests,33.590s, no paid runtime calls; complete diff/privacy/whitespace review. `AUTO1-SOL-VERIFY`; `AUTO-1-C1`/`AUTO-1fix-C1`.
- Cost:two observable Sonnet CLI invocations/list$4.8100636, actual subscription billing unknown; conductor not_metered; Opus0/Astra0.
- Git:main from e333fd3; intended verified origin, normal commit/push pending receipt.
- Limits: software acceptance only. UI/automation slices remain; real expert Gate10 pilot blocked. Next:commit/push receipt, then AUTOMATION-2.

## 2026-10-05T05:42:24.044620+00:00 | AUTOMATION-1 | verified push receipt

Commit f5deb4daeff2f12f69f7d1174e5da7398975e260 passed580 tests; complete and staged diffs reviewed. Normal fast-forward push to the authorized origin/main succeeded; post-push fetch verifies HEAD==origin/main and a clean tree. Receipt committed separately; next construction is AUTOMATION-2.

## 2026-10-05T06:01:30.677862+00:00 | AUTOMATION-2 | FIX / PARTIAL

Initial scoped Claude Sonnet5 builder:58 turns,789.075s, list estimate$3.2998919, actual Pro charge unknown; auxiliary Haiku reported, no subagents/Astra/Opus/runtime provider. 608-test suite has2 new invalid-fixture errors. Independent five-case contract suite after valid PDF geometry has5 substantive failures: output clamping, QA groups/counts and oversized Hebrew fit, negation risk routing, job pause/resume API. Code review additionally found late raw persistence, injected review controls bypass, insufficient QA tail protection and unstable batch prefixes. One scoped repair requested with actual-envelope planner, controlled journal lifecycle, bounded corrections/rechecks and real pause/resume. Initial result retained; acceptance pending. Sol prepared ignored isolated Python3.12 runtime and corrected launcher/installer3.10+ discovery independently for next slice; those paths not in builder scope.

## 2026-10-05T07:40:17.144712+00:00 | AUTOMATION-2 | PASS (supersedes PARTIAL/FIX)

- Contract: `audit/contracts/automation_2.md`; independent font producer part of automation_4.md.
- Delivered: full chapter/batch/QA plan, protected QA funds, local reuse/provider cache boundaries, finite correction/recheck, durable raw recovery, pause/resume, actual stage progress and observed usage.
- Acceptance:635 offline tests41.683s; independent14 recovery/streaming tests; five-font raster inspection; reviewed complete diff/privacy/whitespace. AUTO2-SOL-INTEGRATE.
- Agents:font writer then recovery-test writer isolated; UI read-only until this base accepted; no recursive agents. Sol integration sequential.
- Cost:two external Sonnet CLI calls/list$4.8185541, actual subscription billing unknown. Four automation builder calls cumulative$9.6286177; internal usage unknown. Runtime0/Astra0/Opus0.
- Git:main from5c185fc, intended remote fetched unchanged; normal commit/push pending receipt.
- Limits:software only, Gate10 representative source/credentials/expert judgment still BLOCKED. Next:verified push and UI automation_3/4.

## 2026-10-05T07:43:56.119153+00:00 | AUTOMATION-2 | pre-push font-byte correction

Implementation f929030 passed635 runtime tests, but a new staged-public-source hash check caught one David Libre OFL CRLF normalization mismatch. The commit was already local when this result was inspected; no push occurred. Scoped byte-preserving attributes and explicit restaging restore the verbatim upstream notice in a follow-up commit, without history rewrite. All staged public font hashes now match the recorded manifests; eight font tests passed again. The accepted push will include both commits, followed by its receipt. Original runtime prompt LF attribute retained.

## 2026-10-05T07:45:14.535768+00:00 | AUTOMATION-2 | verified push receipt

Implementation f9290305378e5a0ec9cf3a876a2bac752419f69c and public font-byte correction f266cb118566606999c4d8aafd8d289a3a6fd3d9 passed635 software tests plus repeated8-font/hash checks. Reviewed full and staged diffs. Normal fast-forward authorized push succeeded; post-push fetch confirms main==origin/main and clean tree. No force/history rewrite; this receipt is separate. Next UI writer starts on the accepted common base.

## 2026-10-05T10:01:40.311484+00:00 | AUTOMATION-3/4 | PASS scoped software (supersedes builder PARTIAL)

- Contracts: `audit/contracts/automation_3.md`, `automation_4.md`; accepted producer base `91f3dac4c7c1e037406553f884429d94762dd50c`.
- Delivered: selectable translation/QA/Other models, endpoint-bound memory-only keys, per-role token/cost preflight and observed usage; actual pause/resume; styled HTML help with dated prices and honest quality notes; original book logo; side-profile pixel book and real percent; all five PDF fonts before/after translation without generation. Manual edits preserve revision and explicitly stale prior QA.
- Evidence: `AUTO3-SOL-REVIEW`, `AUTO3-SOL-WINDOWS403`, `AUTO3-SOL-BROWSER`, `AUTO3-SOL-VERIFY`; final659 offline tests60.956s,9 independent HTTP-worker tests,13 focused UI tests. Real Edge upload, consent cancel/approve, model preview, pause/restart/key renewal without translator resend, completed font selection; mobile help verified. Actual public launcher and protected PDF download verified. Browser saved-file event/path not observable; no browser-policy bypass.
- Models/cost: this slice two observable Claude Code Sonnet5 calls (auxiliary Haiku reported),981.220s+230.627s=1211.847s, list estimate$4.6565572. Six automation builder calls cumulative$14.2851749. Actual subscription charge unknown; Sol/conductor and internal agents not_metered; Opus0/Astra0/paid runtime0. Builder initial and one repair were PARTIAL; local deterministic closure supersedes acceptance, not historical invocation records.
- Git: complete diff/privacy review; main and intended origin verified; explicit staging, staged review and normal authorized push follow with separate receipt. No secrets, source uploads, output evidence/caches or unrelated worktrees included.
- Limits: scoped software acceptance, not full quality/release approval. Gate10 requires approved representative inputs/references, paid runtime authorization/credentials and expert judgments. Real cache hits, Hebrew expansion and expected-output assumptions remain uncalibrated. Partial-draft export, automatic paid QA after human edit and automatic dispatch on server startup are not implemented; restart supports explicit safe resume with renewed keys. Next: commit/push receipt and genuine pilot only when prerequisites exist.

## 2026-10-05T10:04:37.062280+00:00 | AUTOMATION-3/4 | verified push receipt

Implementation `59a06d6d06320ca600b42dc38da6c099b18be3bb` passed659 offline tests60.956s and browser/HTTP acceptance recorded above. Full working and staged diffs,25 explicit paths, exact staged bytes, audit append-only prefixes, JSONL validity, privacy and whitespace reviewed. Origin URL/branch/base checked; normal fast-forward push succeeded. Post-push fetch confirms main==origin/main and a clean tree. No force/history rewrite, private source uploads, credentials, output screenshots/caches or unrelated worktrees. This separate receipt records the implementation hash without self-reference. Scoped software accepted; genuine Gate10 pilot and the plan's listed remaining gaps are unchanged.

## 2026-10-05T10:17:47.361949+00:00 | BOOK-REFERENCE | PASS visual software

- Contract: `audit/contracts/book_reference_animation.md`; base `200ec773ef63a72e46546befd16df4d2c656fc13`. Recreated gold-cover/cream-page pixel book from the user-visible reference as a deterministic local SVG strip,40 frames32x40. Not the original image bytes. Opening0-7,24-frame page loop8-31, mirrored closing32-39; actual job percent and existing phases unchanged.
- Acceptance: `BOOK-REFERENCE-SOL-VERIFY`; exact regeneration/XML/geometry/endpoints and served SVG MIME/bytes;22 existing focused HTTP tests(9 in7.667s,13 in8.440s). Edge page-turn position changes, pause/error static CSS, opposite closed endpoints, reduced-motion static demonstration and375px no overflow. Actual Auto completed page renders the new book at100%, console errors0. Prior659-test acceptance remains; no translator/QA/budget changes or new implementation-mirroring tests.
- Cost/calls: Sol internal not_metered; external Sonnet0/Opus0/Astra0/runtime0, added billed API cost0. Verification tests16.107s; conductor/browser wall time not_metered. Small deterministic correction needs no delegated builder. Prior cumulative builder estimate$14.2851749 unchanged, actual subscription charge unknown.
- Git: complete diff/asset/source/privacy/whitespace review; explicit stage and normal authorized commit/push follow; separate receipt records known sync. Screenshots and local fixture server stay ignored. No key, source document or unrelated worktree staged.
- Limits/next: visual update only, not scholarly acceptance; Gate10 and previously documented plan gaps unchanged. Existing job results rerender without paid work. Finish verified Git receipt.

## 2026-10-05T10:20:42.387338+00:00 | BOOK-REFERENCE | verified push receipt

Implementation `d695978e93e853b464cec691ebcc32e988463aaf` passed22 focused HTTP tests, reproducible40-frame XML/pixel bounds/mirrored endpoints and served asset checks, plus documented Edge visual acceptance. Reviewed complete and staged diffs, ten intended paths and exact staged bytes; no source documents, secrets, output screenshots or local fixture server committed. Normal authorized fast-forward push succeeded; post-push fetch confirms main==origin/main and clean tree. This separate receipt records the verified implementation hash; quality/pilot status unchanged.

## 2026-10-05T11:41:40+00:00 | BOOK-REFERENCE-2 | PASS visual software

- Trigger: user feedback that the closed book did not look like a book; same reference sheet. Contract `audit/contracts/book_reference_animation.md` (amended frame layout). Base `9753e61`.
- Change: `tools/build_book_sprite.py` rebuilt from the reference's palette and sequence; 48 frames 32x40: closed front cover with spine, label, page edges and back board (0); hinge cover swing with perspective lift (1-6); page block flips onto inside cover (7-11); two page turns per loop with cast shadow (12-35); mirrored reversed opening ending on back cover (36-47). `ui.css` offsets/timing updated (opening/closing 1.1s, loop 2.4s). Phases, percentage and processing unchanged.
- Acceptance: `BOOK-REFERENCE-2-VERIFY`; deterministic regeneration, XML 48 frames, Edge render and animation-time probe of every phase; full 659 offline tests 59.422s OK. Ignored preview `outputs/automation/book-reference-v2-frames.png`.
- Cost/calls: internal not_metered; external/runtime calls 0, billed cost 0. No delegated builder (small deterministic change).
- Git: explicit-path local commit; push awaits user confirmation. Gate10 and documented gaps unchanged.

## 2026-10-05T11:58:00+00:00 | GOLD-THEME | PASS visual software

- Trigger: user accepted BOOK-REFERENCE-2 and asked to adjust the website colour and push to main.
- Change: `scholarly_translation/ui.css` palette only: teal/green hues mapped to the book gold (42deg, lightness kept), parchment page background, gold-brown accent `#644d16`, warm ink/muted text; error colours unchanged.
- Acceptance: `GOLD-THEME-VERIFY`; contrast >= 5.2:1 for text, Edge home/processing render (ignored `outputs/automation/gold-theme-preview.png`), 659 offline tests OK. External/runtime calls 0, billed cost 0.
- Git: explicit-path commit; normal push of main with BOOK-REFERENCE-2 per user authorization; separate receipt follows.

## 2026-10-05T12:00:00+00:00 | BOOK-REFERENCE-2 + GOLD-THEME | verified push receipt

Implementations `3b4cdaa` (BOOK-REFERENCE-2) and `0445bde` (GOLD-THEME) passed 659 offline tests and the browser checks recorded above. Explicit-path staging, diff check and JSONL validity reviewed. Normal fast-forward push 9753e61..0445bde to origin/main per user authorization; post-push fetch confirms main==origin/main and a clean tree. No force, secrets, source documents or ignored screenshots committed. Gate10 status unchanged.

## 2026-10-05T14:20:00+00:00 | LONG-DOCS | PASS scoped software

- Contract `audit/contracts/long_documents_chapters.md` (afc6b2d). Builders A `044e473`, B `4973809`->`01e7042`; conductor integration follows.
- Diagnosis: failing EPUB is a damaged third-party file (empty spine, 0-byte chapters; no text). Valid 730k-char novel was one chapter group (EPUB never produced chapter nodes); units up to 11.7k chars; preview >10 min; 150k/200-page caps arbitrary.
- Change: EPUB error codes + Hebrew messages, NCX/nav/manifest fallback; spine-document chapters (tiny merged); size fitting (60k chars / role context) at unit boundaries; unit policy only when actual units exceed translator output; caps 3M chars / 2000 pages; planner validates structure once per plan; groups persisted, legacy plans never regrouped.
- Acceptance: LONG-DOCS-INTEGRATE; 709 offline tests OK 276.7 s; real novel 38 chapters, preview 7-25 s per mode.
- Cost (no calls): LONG-DOCS-COST. Sol 6.1 checked reserve $71.63 > MAX_BUDGET_USD $30: user decision pending. Builder usage subscription not_metered; external API calls 0.
- Next: user budget ceiling; literary continuity/quality design (separate contract) awaiting approval.

## 2026-10-05T16:10:00+00:00 | LIT-NOTEBOOK | PASS scoped software

- Contract `audit/contracts/literary_notebook.md` (e4d2166). Builders: C `fdb41c4`, D `0d6c2b0`->`1e1c366`, E `f504304` (ff). LONG-DOCS `9cc42e4` was pushed (receipt here).
- User decisions: no code budget ceiling but a required user budget for paid runs/previews; adaptive model-kept notebook with free tags and per-chapter plot summaries; human review optional only.
- Behaviour: new automation jobs keep `book_notebook` (keeper call after each chapter in all modes; relevant excerpt + previous-passage bridge in translation; notebook in chapter QA; literary risk triggers; downloadable Markdown and summaries in results). Legacy jobs stay on document_state. Nothing waits for a human.
- Acceptance: LIT-NOTEBOOK-BUILD; 760 offline tests OK 290.3 s. Cost: LIT-NOTEBOOK-COST. External API calls 0; builder usage not_metered.
- Limits: no quality claim (Gate10 still needs real judgments); unknown-outcome keeper dispatch blocks further calls like any step; keeper model follows chapter_qa unless context_state_builder configured.

## 2026-10-06T00:07:04.3531617+03:00 | LEARN-PROMPTS | PASS documentation package

- User scope: separate learning window, library translation-copy bridge, direct Hebrew EPUB upload, common vocabulary/grammar, deterministic learner/language continuity committed by explicit "קראתי", one Luna role and no linguistic critic. User authorizes >2 agents for this work; package permits three disjoint builders after frozen bootstrap, sequential A -> B -> C integration and later UI D.
- Contract: audit/contracts/language_learning_prompt_package.md. Artifacts: LANGUAGE_LEARNING_PROMPTS_HE.md and seven prompts/language_learning/*.md files (conductor, shared contract, A/B/C/D, runtime generation).
- Acceptance: LEARN-PROMPTS-CHECK passed nine UTF-8 document checks, seven local Markdown links, runtime JSON example parsing, continuity/error handoff requirements and three pairwise-disjoint parallel write sets. Manual review: source copy/EPUB paths, exactly-once completion, within-book replan, projected vs committed state, no automatic mastery/level promotion, single-model recap, ownership and merge boundaries.
- Limits: documentation acceptance only; no learning code implemented, workers dispatched or runtime/provider calls. English pilot is an explicit replaceable assumption; curated common seed is not verified frequency ranking. No linguistic/pedagogical quality claim; existing Gate10 remains blocked. No product tests rerun for documentation-only changes.
- Git: inspected clean main at 3c698126f24ca037f7c24a2d99e120e19ec620e2; fresh origin fetch confirmed zero ahead/behind. This reconciles the earlier checkpoint's pending prior push description; prior implementation test evidence remains historical, not rerun. Explicit-path reviewed documentation/audit commit and permitted push follow; separate receipt will record hash/status.
- Calls/cost: Sol internal not_metered; Sonnet/Opus/Astra/builders 0; paid runtime/provider calls 0. No imported book, source text, key, output or unrelated worktree added.
- Next: user may execute 00_conductor.md; creating prompts did not start product implementation.
## 2026-10-06T00:07:32+03:00 | LEARN-PROMPTS | Git closure stopped; documents ready

Supersedes only the planned Git closure in the preceding documentation card.
The initial tree was clean, but final inspection detected unexpected concurrent
modifications in scholarly_translation/chapter_pipeline.py,
scholarly_translation/work_journal.py, tests/test_chapter_pipeline.py and
tests/test_pipeline_recovery_contract.py. This task did not edit those files.
Per AGENTS.md stop-on-unexpected-changes, no staging, commit or push was performed.
Document checks remain passed; full gate acceptance/clean Git closure is deferred.
Prompt files are saved and delivered; product execution/worker dispatch did not start.
No product test or quality claim is attached to the concurrent changes.

## 2026-10-06T00:17:51.2437685+03:00 | LEARN-PROMPTS + WORDLISTS | verified delivery; Git reconciliation

- User selected fr/de/es/yi/it. Added 500 unique lexical surface forms per language (2500), five readable Markdown lists, one provenance-bearing JSON, attribution README and standard-library-only offline reproduction helper under prompts/language_learning/wordlists/. No Hebrew glosses/lemma senses/grammar catalog claimed; frequency is a candidate-selection proxy, not universal usefulness or CEFR. First proposed working slice changed from English to French; runtime support remains unimplemented.
- Sources: Hermit Dave FrequencyWords/OpenSubtitles2018 pinned commit 525f9b560de45753a5ea01069454e72e9aa541c6 (fr/de/es/it), Wiktionary Yiddish Newspaper top 600 oldid 71268025 (yi; 2006-2008 newspapers). CC-BY-SA-4.0 attribution/source/history/license and change notices included; raw snapshots stay ignored under outputs/. Letter/mark-safe NFC filtering and casefold dedup; surface inflections/function words retained; corpus bias/names/slang limitations documented.
- LEARN-WORDLISTS-CHECK: 5 x 500 unique forms, ranks 1..500, descending counts, original source ranks and hashes, 15 UTF-8 documents and 15 local links, Unicode Yiddish marks, and byte-identical offline regeneration all passed. No product tests or linguistic critic; no runtime/model calls or workers dispatched.
- Git-stop reconciliation: concurrent owner committed the four unrelated code/test paths plus checkpoint as b56df6b (untranslatable-unit fix). This task did not edit those paths. Fresh fetch succeeded; only this task's documentation/data/audit changes remain. Safe explicit-path documentation closure resumes; preserved prior fix and its checkpoint next action. Earlier stop receipt remains history.
- Network fetch needed sandbox escalation and was approved. One download succeeded with only a console Unicode-print error; local inspection corrected output encoding without re-fetching or changing data. Paid/model cost 0 observable external provider calls; Sol internal usage not_metered.
- Next: reviewed documentation/data/audit commit and authorized normal push, then separate receipt. Product execution starts only on user instruction.

## 2026-10-06T00:23:03.3639273+03:00 | LEARN-PROMPTS + WORDLISTS | verified push receipt

Delivery f675162c4a29a80d8ddcc6681ae31d8f81d0d02a contains exactly 20 reviewed
prompt/data/audit paths. Staged bytes matched local files; five requested languages
have 500 unique forms each; source/license metadata, links and offline reproducibility
passed. Normal authorized push b56df6b..f675162 succeeded; post-push fetch verified
main == origin/main and clean tree. Prior product fix preserved. Workers/runtime calls
0; documentation/data acceptance only. This separate receipt records that known hash.
Next: deliver links; later execution requires the user's instruction to start building.


## 2026-10-06T01:25:07.7972847+03:00 | LEARN-0 | PASS isolated bootstrap

- User authorized execution and warned about an active translation. Isolated conductor worktree/branch codex/language-learning from 9898011; active root checkout/server/data/credentials untouched. No merge/deployment while book runs.
- Contract audit/contracts/learn_0.md and learn_1.md; executable schema1/source/hash/learner/catalog/plan/generated/recap validation, numeric effort policy and Unicode fixture. Four bootstrap tests OK; 22 existing library tests OK (correct discovery; initial module invocation lacked tests path and sandbox prevented node, corrected locally).
- No model/provider calls yet; conductor usage unknown. Three Claude Code Sonnet builders will own disjoint paths in isolated common-base worktrees. Measured invocation caps 2 USD each, shared list cap10; subscription charge unknown. No runtime pilot authorized.
- Git: verified local bootstrap commit follows; push intentionally not attempted outside standing origin/main authorization, and main remains untouched. Full integration accepted only after tests and separate UI preview.

## 2026-10-06 | LEARN-1A | PASS local component
Builder A integrated first from d1f71e2.28 tests pass, including continuity, deterministic plans, stale state and receipt scope. Conductor adapted pytest-style tests to repository unittest without dependencies, repaired fixture hashes, added atomic slot acquisition and source opportunity ranking. Small French35-item starter; four other catalogs unavailable. No runtime calls; no quality claim. Commit follows, feature push not attempted; main remains untouched.

## 2026-10-06 | LEARN-1B | PASS local component
B integrated after A receipt8228b2d.43 learning tests pass. Reused safe EPUB reader and chapter grouping; conductor preserves explicit short chapters, checks Hebrew targets. Immutable source snapshots, damaged/wrong-language/unfinished input refusals, stable splits and headings. No live app changes; shared integration remains in progress, not a deploy gate.
