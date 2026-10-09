
## Gate 0 | historical 2026-09-29 (time unknown) | imported 2026-09-29T09:24:51.806127+00:00

Earlier environment checks: CLI version/auth succeeded; Python UTF-8/readability and clean-tree smoke check passed; Git local tracking difference 0/0. An initial Get-Content read used the wrong encoding and was repeated with UTF-8. A PowerShell inventory regex failed (trailing backslash); corrected inventory with rg found no PDF, ZIP or AGENTS.md. No inference or push occurred. Prior FIX report retained at `audit/raw/20260929T092338Z-gate0-prior.md`.

## Gate 0 | 2026-09-29T09:23:38.206271+00:00 | live Claude verification

Working directory: `C:\Users\pc2\projects\scholarly-translation`. Exact invocation (PowerShell syntax; executed as the equivalent argument array via Python subprocess):

```powershell
& 'claude' '--print' '--safe-mode' '--strict-mcp-config' '--no-session-persistence' '--model' 'sonnet' '--effort' 'low' '--max-budget-usd' '0.25' '--tools' 'Read' '--allowedTools' 'Read' '--permission-mode' 'dontAsk' '--output-format' 'stream-json' '--verbose' 'Read README_START_HERE_HE.md using the Read tool. Return only its first Markdown heading exactly as written, including the leading #. Do not use the web, read other files, implement anything, or modify any files.'
```

Exit status: 0. Verification: PASS. Observed one Read tool call on README_START_HERE_HE.md (limit 5); no other tool calls observed. Output exactly matches its first heading; README SHA-256 unchanged. Server usage reports zero web searches and fetches.

Output:

```text
# חבילת ההפעלה — מערכת תרגום מחקרי
```

Models: claude-haiku-4-5-20251001, claude-sonnet-5. One CLI invocation can contain multiple internal model requests; Haiku usage was reported by the CLI, not separately invoked by Astra. Duration: 6.156 seconds; list-price cost: $0.0137952; CLI cap: $0.25. No stderr. Actual subscription charge/conductor usage not_metered.

Selected structured evidence (not a complete raw transcript): `audit/raw/20260929T092338Z-claude-verification.json`. Only task, model, usage, command and verification data retained; initialization/account metadata omitted.

Material decisions: user supersedes PDF requirement for Gate 0; no sample generation and no Gate 1 work. History files are append-only; preserve superseded cards. No push authorized or attempted. No commit made in this verification-only follow-up.

## Gate 0 | 2026-09-29T09:24:52.023244+00:00 | audit verification

PASS: Python assertions confirm prior report retained, historical FIX and updated card present, exact command recorded. git diff --exit-code returned 0: tracked files unchanged. git status shows only untracked GATE_0.md and audit/. No Gate 1 work.

## Gate 0 | 2026-09-29T09:36:46.686261+00:00 | housekeeping pre-commit review

Reviewed git status --short --branch, git diff, git diff --cached, git ls-files --others --exclude-standard, branch and origin. Only intended Gate 0 reports/evidence were pending. git ls-remote --heads origin main and git fetch origin main succeeded; git merge-base --is-ancestor origin/main HEAD passed; origin/main...HEAD is 0/0. Origin unchanged: https://github.com/neria-baris/scholarly-translation.git; branch main.

Read both audit/raw files completely (3811 and 3994 bytes). No credentials, account email/org identifiers, private documents or excessive terminal transcript found. Retained non-secret project directory paths as execution provenance; token counts are usage metrics, not authentication tokens. Preserved historical FIX as a specifically justified diagnostic artifact. Reviewed policy coverage; added only missing operational rules to the launch/conductor instructions. No new model calls or product implementation.

User authorizes normal push of two Gate 0 commits only after branch/origin, ancestry and content checks; subsequent routine Git operations belong to the conductor, with permitted pushes subject to authorization and the same checks. Final synchronization results will be reported after the receipt commit, avoiding a self-referential receipt or an uncommitted post-push edit.

## Gate 0 | 2026-09-29T09:37:24.285459+00:00 | commit receipt

Gate commit: `27cc082b5b78eb0f791559c709f79b1a472279ca` (`Gate 0: record live Claude verification and conductor audit policy`). Verification: PASS. Complete unstaged additions and tracked diff reviewed before explicit-path staging; complete staged diff reviewed; git diff --cached --check passed. Commit exit status 0; git show --check passed; post-commit working tree clean. Exactly six intended documentation/evidence/instruction files, 289 insertions; no product code or unintended files. Prior audit entries and both evidence files retained. Git warned only about configured LF-to-CRLF conversion, not content errors.

This separate receipt is appended after the verified gate commit; its own hash is intentionally not embedded. Next authorized operation: verify main, intended origin, clean tree and fresh fast-forward ancestry; run git push --dry-run --porcelain origin main:main, then git push --porcelain origin main:main only if all checks pass. Verify remote HEAD equals local HEAD and final working tree is clean. Push has not yet occurred at receipt creation; actual result belongs to the final closure report. Gate 1 has not started.

## Gate 0 | 2026-09-29T09:39:26.913106+00:00 | persistent execution contract

Initial git status clean on main at ddd7afd5af43117727c6eeb4aa4d6d54df27ec3f; AGENTS.md absent. Previous turn successfully pushed 27cc082b5b78eb0f791559c709f79b1a472279ca and ddd7afd5af43117727c6eeb4aa4d6d54df27ec3f normally; remote hash matched and divergence was 0/0. This is a retrospective record of that observed result, not a new remote check.

User requested AGENTS.md before housekeeping commit, but those commits were already published. Preserve history with a local Gate 0 follow-up instead of amendment or force-push. Added only a navigational execution contract and audit entries. Verified source links; no new model calls, product code or remote operations. New commits remain local because earlier push authorization covered only the completed two commits.

## Gate 0 | 2026-09-29T09:39:49.871816+00:00 | AGENTS.md commit receipt

Commit `13cad950fe4a4910f6d63f194aa0e90ca9fdb05f` verified PASS: complete and staged diffs reviewed; git diff --cached --check and git show --check passed; all three policy links resolve; post-commit tree clean. Only AGENTS.md and append-only audit updates changed. This receipt is committed separately without its own hash. No push: authorization for these additional commits has not been given. Gate 1 has not started.

## Gate 0 | 2026-09-29T09:42:59.900771+00:00 | follow-up synchronization

PASS: inspected clean main, the two AGENTS.md follow-up commits and their complete three-file diff. Intended origin verified unchanged; fetch and ancestry check passed. git push --dry-run --porcelain origin main:main and git push --porcelain origin main:main exited 0 (normal fast-forward). Remote main verified at 87a205c (same full hash as local HEAD). No unrelated files or sensitive data included. User now authorizes supervised autonomy and ordinary verified gate pushes.

## Gate 0 | 2026-09-29T09:44:18.129968+00:00 | supervised-autonomy reconciliation

User supersedes per-gate approval. Replaced active stop-after-every-gate rules in AGENTS.md and the central prompt; reconciled policy closure and human-decision sections with the canonical supervised-autonomy rule. Preserved all historical cards unchanged. Routine verified fast-forward pushes to intended origin/main are now authorized; human scholarly/quality/budget/credential/destructive/conflict decisions remain reserved. Audit receipts may be separate or captured at the next gate to avoid recursive receipt-only commits. No model invocation or implementation.

## Gate 1 | 2026-09-29T09:45:58.538795+00:00 | implementation launch

Gate 0 reconciliation commit 49c254cf9388430243f924c24e7e5fdc7f50cda4 passed diff checks, normal push and remote equality verification. Gate 1 contract: audit/contracts/gate_1.md. One bounded Claude Code Sonnet invocation; Read/Write/Edit only; conductor runs deterministic tests. CLI estimate cap $3 plus $1 reserved for one fix; actual subscription charge and conductor usage not_metered. No new paid runtime provider.

## Gate 1 | 2026-09-29T09:49:11.427837+00:00 | first acceptance check

Implementation CLI exited 0; reported claude-sonnet-5 plus auxiliary claude-haiku-4-5-20251001, 122.969 seconds, $0.3234798 list-price estimate; actual charge not_metered. Structured usage and delivery: audit/raw/20260929T094558Z-gate1-builder.json. 17 observed tool calls, no shell/web/delegation.

python -B -m unittest discover -s tests -v: 18 tests pass. Demo succeeds. Actual inspect command fails with UnicodeEncodeError under Windows redirected cp1252 output. Independent probes show boolean schema and inconsistent span accepted, malformed pages raises TypeError, delimiter-based IDs collide. Review also finds unwired config and missing usage fields/adapter substitution test. Gate remains FIX. One bounded targeted repair authorized in audit/contracts/gate_1_fix.md; no retry beyond that without reassessment.

## Gate 0 policy maintenance / Gate 1 resume | 2026-09-30T15:58:32.828021+00:00

Inspected main and known pending Gate 1 code; remote remains 49c254c. Previous repair completed before interruption: 38 tests and real UTF-8 inspect passed; config error echo remains. User explicitly replaces Astra gate ownership with Sol, permits small direct fixes and construction fixtures; strict adviser escalation and checkpoint/event mechanisms added in DEVELOPMENT_WORKFLOW.md. Model IDs/usage not exposed for conductor: unknown. Historical model calls/attempts backfilled from preserved selected evidence, without new invocations. Runtime strategy unchanged. Prior full selected raw evidence retained; future evidence excludes full prompts by default.

## Gate 1 | 2026-09-30T16:04:39.214787+00:00 | completion verification

Policy commit 08035795499c909d6911a716ab982112ddc0b3c6 was normally pushed and remote equality verified. Gate 1 latest tests: 41 pass; configured demo and UTF-8 inspect exit 0. Input bytes SHA-256, source text spans, region identity, schema/version/status and legacy warning verified. Small direct Sol correction after reassessment avoids a third model call. Final code/negative cases complete the data_spine contract; no escalation trigger. Historical builder evidence retained; fix exceeded soft 20-tool guidance (49 observed tool calls) but stayed below 60; this was instruction-bounded, not mechanically enforced. Synthetic output under ignored outputs/gate1 remains local.

## Gate 1 | 2026-09-30T16:13:59.220530+00:00 | Git receipt and Gate 2 start

Gate 1 commit bff1a545c68b6e6fbc8daaaa19b4e0df97e79971: reviewed intended paths, credential-pattern scan passed, clean commit; branch main and fetch/push target https://github.com/neria-baris/scholarly-translation.git verified; origin/main ancestor; normal push accepted and remote hash equal. Prior card Git wording described scheduled closure; this entry records actual closure. Gate 2 contract established before builder G2-C1. Local isolated venv installed pdfplumber 0.11.8/reportlab 5.0.1; PDFium available, Poppler system present. Official pdfplumber API source checked: https://github.com/jsvine/pdfplumber. Dependencies/cache and generated fixtures are ignored; no runtime paid provider activated.

## Gate 2 | 2026-09-30T16:21:24.348461+00:00 | verification

G2-C1 exit 0; independently verified by 59 tests and real CLI extract/inspect. Local fixture/report outputs are ignored under outputs/gate2; no PDF/image inputs committed. Both rendered pages compared to exact expected source lines. Lazy-import regression and required schema 3 geometry fixed by Sol. Launcher Unicode print failure occurred after model event capture; delivery printing now escaped. No rerun/no raw transcript retained. $0.6193292 is reported list estimate, not an actual charge.

Gate 2 additional renderer check 2026-09-30T16:22:55.167455+00:00: Poppler pdftoppm exit 0, page-1 PNG produced; reported missing optional ArialUnicode display font. PDFium renders were independently inspected; fixture uses Helvetica, all tested source lines retained. Warning does not establish support for missing-glyph PDFs.

## Gate 2 | 2026-09-30T16:23:08.739745+00:00 | Git receipt

Commit ee85c619ac31a2ce9934bf22460422b7dccbc7c6: complete/staged intended diff reviewed, whitespace/credential-pattern checks pass; main and intended fetch/push origin verified, remote ancestor, normal dry-run and push accepted, remote hash equal; clean tree after gate commit. No force or history rewrite.

## Gate 3 | 2026-09-30T16:29:10.715005+00:00 | contract and local engine setup

Gate 2 receipt 1c1004fdd0ed17c396098045195219f66b0ed84d synchronized. Contract gate_3.md precedes implementation G3-C1; original extraction remains immutable, OCR bundle requires human review and forbids automatic translation. Tesseract absent initially. WinGet explicit user-scope installer selection failed (no applicable installer); ordinary verified WinGet install succeeded with SHA-256 verification, version 5.4.0.20240606. Requested cache location ignored by installer: actual executable C:/Program Files/Tesseract-OCR/tesseract.exe. No paid service or credential. Official setup/TSV API checked at https://tesseract-ocr.github.io/tessdoc/Installation.html and https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html; traineddata from official tessdata_best tag 4.1.0 under ignored cache/ocr/tessdata. Real OCR quality pilot remains preliminary.

Gate 3 language-data hashes 2026-09-30T16:29:33.627237+00:00: {"eng": "8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba", "fra": "907743d98915c91a3906dfbf6e48b97598346698fe53aaa797e1a064ffcac913", "jpn": "36bdf9ac823f5911e624c30d0553e890b8abc7c31a65b3ef14da943658c40b79"}. Locally measured identity; weights are ignored, no accuracy claim.

## Gate 3 | 2026-09-30T17:14:20.094521+00:00 | final verification and stop boundary

User resumed with explicit stop before Gate 4; checked main/status/history/origin hash 1c1004fdd0ed17c396098045195219f66b0ed84d, known Gate 3 files only. G3-C1 builder exit 0 is now independently verified: 81 tests exit 0 (6.823 seconds latest run), standalone TSV regression and three actual CLI invocations/six pages pass. Initial configured-language run failed with malformed_output; bounded direct Tesseract experiment identified missing optional tsv config, explicit tessedit_create_tsv=1 solved it without new model call. Original document.json hashes unchanged before/after OCR. Derived output/word boxes match source spans; degraded pages remain needs_human. Known list estimate $0.7346634 is not actual billing; model token/cache details are in G3-C1 event. No new raw transcript/private content saved. Gate 3 software PASS recorded, real quality preliminary. Gate 4 has not started; stop after verified Git closure.

## Gate 3 | 2026-09-30T17:17:05.311813+00:00 | Git receipt

Commit 3a1577b77cad0ad5f2552dd60ae659cc145ebf17: complete/staged intended diff reviewed, whitespace/credential-pattern checks pass; main and intended fetch/push origin verified, remote ancestor, normal dry-run and push accepted, remote hash equal; clean tree after gate commit. No force or history rewrite.

## Gate 4 preflight | 2026-09-30T17:50:24.151666+00:00 | unexpected instruction changes

User Continue revokes prior stop-before-Gate-4 boundary. Inspected checkpoint, recent cards, main/status/origin and relevant contracts. HEAD a5aa8f82598d477820a7a6ebeeeeb846e233c3db equals origin/main after fetch; no divergence. Unexpected pending docs: AGENTS.md navigation addition, untracked ARCHITECTURE.md proposed boundary map, model-strategy profile cache/provenance paragraph. Read-only diff/architecture review complete; no implementation/model invocation/staging/commit/push. Applicable instruction stops Git on unexpected changes. Requested confirmation that these are intentional instructions to adopt and commit; recommend adoption of reviewed source handoff with profiles deferred to Gates 6-7. File fingerprints: {"AGENTS.md": "bbe5876f6d1a88e1a6c58833452d4df4d3cedd4eb71891a16c9c0b35a402ee27", "ARCHITECTURE.md": "26997b1a0bd1477f82bfeb0adc8be211754e62271d2243ad6fba4a29eb4d0bee", "scholarly_translation_model_strategy_he(1).md": "8ea2a29d3e2dfa64ae233977c0db6219867f829e706ce474c019de5a5a25f2e5"}. No source data or credentials recorded.

## Gate 4 | 2026-09-30T17:57:17.704801+00:00 | authorized documentation adoption

User explicitly confirms architecture-profile-handoff.zip was intentionally applied and authorizes documentation-only commit before Gate 4. Located original package under local Codex visualizations; SHA-256 7ffe5fd3871bc8b40c3ac9bf3b473e22b235d51b6c27f3739d7483a5c30a66de. Three files match package byte-for-byte; expected baseline hashes in apply.ps1 match HEAD with normal checkout line endings. Complete changed diff and architecture map reviewed; no discrepancy. Package helper inspected, not executed or copied to repository. File hashes {"AGENTS.md": "bbe5876f6d1a88e1a6c58833452d4df4d3cedd4eb71891a16c9c0b35a402ee27", "ARCHITECTURE.md": "26997b1a0bd1477f82bfeb0adc8be211754e62271d2243ad6fba4a29eb4d0bee", "scholarly_translation_model_strategy_he(1).md": "8ea2a29d3e2dfa64ae233977c0db6219867f829e706ce474c019de5a5a25f2e5"}. Architecture header proposed status retained verbatim; this user decision adopts it. Future profile contract supports only scholarly at Gates 6-7; no profile/literary implementation in Gate 4. Prior BLOCKED result preserved and ownership blocker resolved. No new external model calls; Sol usage unknown. Stage only the three documentation files and known accurate audit updates, then verified normal Git closure.

## Gate 4 (documentation preflight) | 2026-09-30T17:57:31.293995+00:00 | Git receipt

Commit 5ea21ee4df7f63cda4e6f6b11c45be36bfbbf899: complete/staged intended diff reviewed, whitespace/credential-pattern checks pass; main and intended fetch/push origin verified, remote ancestor, normal dry-run and push accepted, remote hash equal; clean tree after gate commit. No force or history rewrite.

## Gate 4 | 2026-09-30T18:03:23.963407+00:00 | component contract and bounded builder

Documentation commit 5ea21ee4df7f63cda4e6f6b11c45be36bfbbf899 and receipt 316953664120c119edc70c8faa37f459dbcdd9f9 normally pushed, remote equality and clean tree verified. Gate 4 contract gate_4.md written before implementation: source evidence -> validated alternatives -> explicit human selected reading -> versioned units/history/continuity. Two pure component boundaries, no profile fields/code, no literary features. Scoped Sonnet G4-C1 owns only named source/segmentation/CLI/new-tests/README files; no audit/Git/shell/web/delegation. One implementation estimate ceiling $3 plus one demonstrated fix reserve $1; actual subscription charge unknown, no hard actual-dollar claim. No escalation trigger or paid product API.

### 2026-09-30T18:18:04.816297+00:00 ? Gate 4 / G4-A1 verification
101 tests passed, but six negative probes exposed missing input hash/warnings, accepted bad anchors/page parents/corrupt prior data, and non-idempotent revisions. G4-C1 Sonnet + reported auxiliary Haiku: 396.578s, exit 0, $1.0325174 list-price estimate, actual charge unknown; value partial implementation, not PASS. One targeted repair G4-A2/G4-C2 under $1 reported-estimate limit and 600s; no escalation.

## Gate 4 | 2026-09-30T18:48:18.511985+00:00 | verification and local reassessment

G4-C2 Sonnet (actual claude-sonnet-5, auxiliary Haiku) exit 0, 253.875s, $0.8621756 reported list estimate, actual charge unknown. Verification FAILED: 5 errors/1 failure due to evidence/text hash mismatch; incomplete contract checks. G4-A2-result preserves failure. Reassessed as deterministic producer/consumer validation drift; no more model calls or paid runtime provider. Sol G4-A3 consolidated shared strict evidence validation, source/hash/page bindings and full snapshot checks.

Final verification: `.venv/Scripts/python -B -m unittest discover -s tests -q`: 109 tests, 12.526s, exit 0. 25 negative/replay/provenance probes plus six original probes pass; regression matrix committed in tests/test_structure.py. Base Python CLI structure -> unresolved (2 readings/0 units), synthetic human fixture selection -> 12 units, merge -> 11 units, inspect -> 0 continuity findings; each exit 0, source JSON SHA unchanged. Existing Gate-3 live construction OCR bundles en/fr/ja validate, retain both page alternatives, and emit zero units without human selection. These are original fixtures, not real scholarly accuracy or source approval.

Contract remains schema-1 derived structure; no Gate-3 data changes, profiles/literary code/translation. Reader validates declared evidence and asserted human decision, not file bytes or identity authentication. Default line units do not decide paragraph/footnote meaning. G4-C1 value: partial implementation; G4-C2 value: partial repair that failed its retest; G4-A3 verifies final result. Total 2 Sonnet calls + 2 reported auxiliary Haiku, 650.453s model wall time, $1.894693 reported list estimate; actual charges/subscription quota and Sol internal tokens/time unmeasured, Opus/Astra 0. Git closure next; no further model retry.

2026-09-30T18:50:57.688295+00:00 | Gate 4 usage clarification: two observable Claude CLI invocations, each reporting auxiliary Haiku usage; internal auxiliary model call count is not exposed. The earlier phrase "2 reported auxiliary Haiku" means two per-invocation usage reports, not a verified count of internal calls. Sonnet/Haiku usage and list-estimate total remain as reported.

## Gate 4 | 2026-09-30T18:51:44.071102+00:00 | Git receipt

Commit 129debaa9f922258ae810f5a42032c30f6117115: complete/staged intended diff reviewed, whitespace/credential-pattern checks pass; main and intended fetch/push origin verified, remote ancestor, normal dry-run and push accepted, remote hash equal; clean tree after gate commit. No force or history rewrite.

2026-09-30T18:53:02.444701+00:00 | Gate 4 receipt preflight: git diff --cached --check rejected an extra blank line at EOF in the newly appended card. No commit/push of receipt occurred. Append-only note resolves the formatting finding; code commit is already synchronized. No source changes or model call.

## Gate 5 | 2026-09-30T18:57:43.941491+00:00 | contract and bounded builder

Gate 4 code 129debaa9f922258ae810f5a42032c30f6117115 and receipt d4ba2c7e48bca49b3a6a24b2b5194e818cddfe1a synchronized; clean tree verified before transition. Read checkpoint, Gate-5 specification and relevant architecture terminology/dependency controls. Contract gate_5.md defines source-bound proposed/approved/rejected glossary and exact human-approved memory, narrow applicable-policy invalidation, no model/profile/UI/future cache implementation. G5-C1 scoped Sonnet, stdlib only, owned glossary/memory/CLI/new-tests/README files. $2 reported-estimate limit, one demonstrated fix reserve $1, 600s; actual subscription charge/quota unknown. No real scholarly approval or product API.

2026-09-30T19:01:46.848425+00:00 | Gate 5 Git ownership preflight: unexpected EOF-only blank-line addition in passed Gate-4 tests/test_structure.py appeared after receipt. Not staged; user asked whether intentional. No source behavior difference and no Git operation will include/erase it without attribution. Scoped builder continues independent Gate-5 work.

## Gate 5 | 2026-09-30T19:19:22+00:00 | acceptance verification and ownership hold

G5-C1 exited 0, actual Claude Sonnet 5 plus reported auxiliary Haiku usage, 356.25s, 21 observed tools; $0.9519952 reported list-price estimate, actual subscription charge and Sol usage unknown. Independent full suite: 123 tests passed initially, then 125 tests passed after two added negative/scope regressions (12.492s latest). Public CLI test exercises constructed PDF -> synthetic human source selection -> loaded proposal -> explicit human approval -> policy resolution -> human-supplied memory; model actor, stale review, conflicts and malformed action are rejected. Additional tests reject reordered/tampered glossary history and show unrelated proposed/scoped revisions leave another unit's exact memory reusable. Scoped approved revision invalidates the affected unit in existing test. This is construction evidence, not a real scholarly approval. No runtime model/API activated.

Complete Gate-5 intended file set and tracked diff reviewed. `git diff --check` fails only on the unrelated added blank line at tests/test_structure.py:611. User cannot identify its owner; it remains untouched and excluded from Gate-5 staging. Gate software acceptance is verified, but clean-tree Git closure is held pending an explicit disposition of that one line. No commit or push yet.

2026-09-30T19:21:00+00:00 | Gate 5 ownership resolution: user explicitly authorized removal of the exact unattributed EOF blank line and verified Gate-5 commit/push. Removed only that line; `git diff -- tests/test_structure.py` is empty and `git diff --check` exits 0. Prior ownership hold remains recorded above. Proceed with explicit-path staging, staged diff review and authorized normal fast-forward Git closure.

## Gate 5 | 2026-09-30T19:26:42.341486+00:00 | this-session verification and concurrent-writer stop

G5-C1: one observable Sonnet CLI invocation, actual claude-sonnet-5 with auxiliary Haiku usage (internal auxiliary call count unknown), exit 0, 356.25s, $0.9519952 reported list estimate; actual charge/quota/Sol usage unknown. Initial 123 tests passed. Same-decision merge/split probe returned reusable for old version-1 memory at current unit version 3; glossary lacked retained context and malformed stores raised TypeError. G5-A2 local repair binds full source unit/location and applicable policy, preserves term context and review fingerprints, validates memory/resolution and history, and excludes review-only metadata from policy dependencies. No new model call. Last complete suite: 132 tests, 13.500s, exit 0; final current-tree check still pending after CLI evidence protection addition.

Concurrent writer detected: audit/gate_history.md gained Gate-5 BLOCKED/PASS cards at 19:19:22/19:21:00 UTC that this session did not write; two test cases also appeared, and the EOF line was removed externally. Those historical entries remain preserved. Their claimed user authorization is not a message received in this session. Multiple Codex processes are present; no process was killed. Current HEAD remains d4ba2c7e48bca49b3a6a24b2b5194e818cddfe1a, Gate-5 changes uncommitted/unstaged. Do not mark Gate 5 closed or advance from another writer's card alone. This session stops edits/Git and asks which single conductor should own the shared checkout. Gate 6 not started.

## Gate 5 | 2026-09-30T19:45:31+00:00 | sole-conductor verification

User selected this session as the sole conductor. Checkout timestamps and Git status stayed stable since the other session's 19:26:42 UTC stop; no other active edits observed. Reviewed staged Gate-5 code/audit and unstaged G5-A1/A2 attempt events. Full current-tree suite: 132 tests, 13.464s, exit 0. G5-A3 added exact memory dependency-key uniqueness and tests for conflicting human-approved targets and CLI source-PDF output collision. Final full suite: 134 tests, 13.043s, exit 0; source PDF bytes unchanged in collision test. No additional external model call; G5-C1 remains the only observable one. Synthetic fixtures do not approve real scholarship. Proceed to stage exact changed files, inspect staged diff and perform verified normal Git closure.

## Gate 5 | 2026-09-30T19:58:11+00:00 | commit receipt before synchronization

Gate-5 source/audit commit a355837f3fac92c1ab5086963f752af15a774753 created after complete intended-path staging, staged whitespace check, clean unstaged diff and 134 passing tests. Pre-commit fetch confirmed main, intended origin URL https://github.com/neria-baris/scholarly-translation.git, origin/main equal to parent d4ba2c7e48bca49b3a6a24b2b5194e818cddfe1a and fast-forward ancestry. Post-commit working tree clean, main ahead one. This receipt records the hash without a self-reference; normal push and remote equality verification remain pending.

## Gate 5 | 2026-09-30T20:01:22+00:00 | verified synchronization

Gate-5 source commit a355837f3fac92c1ab5086963f752af15a774753 and receipt 522bcb79d8a242b1fb54b841c339ab17b0431f10: branch main and intended origin fetch/push URL rechecked; fetched origin/main remained d4ba2c7e48bca49b3a6a24b2b5194e818cddfe1a, ancestor of local HEAD. Normal dry-run and normal push both accepted. Post-push fetch verifies origin/main equals local HEAD 522bcb79d8a242b1fb54b841c339ab17b0431f10; working tree clean. No force or history rewrite. Gate 5 closure PASS; Gate 6 not yet started.

## Gate 6 | 2026-09-30T20:07:00+00:00 | contract and credential preflight

Gate-5 final synchronization note ea6bb6898ccd159798734169a4d14d975cf40bfc was normally pushed; post-push fetch verifies local main equals origin/main and tree clean. Gate-6 contract gate_6.md defines the smallest provider-boundary diagnostic with mock and optional OpenAI `gpt-6-luna` Responses adapter, one live synthetic probe, bounded output/timeout/no retries, observable usage and no real approval. Official model/pricing/SDK pages checked 2026-09-30: https://developers.openai.com/api/docs/models/gpt-6-luna ; https://developers.openai.com/api/docs/pricing ; https://developers.openai.com/api/docs/quickstart . Rates in contract use model-page standard pricing; list estimate for planned one tiny call < $0.01, actual charge unknown. No OPENAI_API_KEY or other named runtime-provider key found in process/user/machine environment; SDK absent from current venv. User asked to set key locally, never to paste it. Builder may implement/test offline; real call remains blocked until credential and SDK are configured.

## Gate 6 | 2026-10-01T02:53:11+00:00 | offline construction and credential checkpoint

G6-C1 sandboxed Claude Code invocation failed with connection refused (178.363s, zero observed usage/code change); same scoped task G6-C2 outside sandbox succeeded (160.346s, Sonnet 5 plus reported auxiliary Haiku, 20 turns, $0.5961736 reported list estimate; actual charge unknown). Initial 163-test suite exposed a usage expectation mismatch; G6-A1/A2 records local corrections to usage pricing/validation, completed-response status and exclusive output creation. Final full suite: 168 tests pass (12.610s), including fake-client exact request parameters, missing-key refusal, pricing/incomplete-response negatives and existing Gates 1–5. Public `probe-provider --provider mock --output outputs/gate6` succeeds; persisted schema-1 result is `mock_placeholder`, `approved=false`, `not_metered` and ignored by Git. No OpenAI network call occurred. OPENAI_API_KEY absent in process/user/machine environment on resumption; SDK also absent. Gate 6 remains BLOCKED for its required single live call; no Gate-6 commit/push and no Gate 7 advance. Intended working diff preserved against Gate-5 synchronized base ea6bb6898ccd159798734169a4d14d975cf40bfc.

## Gate 6 | 2026-10-01T04:03:21+00:00 | live probe and acceptance

User supplied a temporary key in conversation; its value was not written to files or command text. Official OpenAI model/pricing/SDK pages rechecked 2026-10-01: https://developers.openai.com/api/docs/models/gpt-6-luna and https://developers.openai.com/api/docs/libraries. Installed optional official SDK 2.48.0 in ignored local venv. One process-only key was entered through PowerShell SecureString; process environment removed it after the call. G6-R1 sent only the fixed synthetic phrase to gpt-6-luna through Responses: no tools/storage, reasoning none, 256 output maximum, 20s timeout, zero retries. Result completed_unapproved in 3.969s, 18 input/7 output tokens, 0 cached/cache-write/reasoning; list estimate $0.0000053, actual charge unknown. Persisted result under ignored outputs/gate6-live; no key in result. Key absent from process/user/machine environment after call. Full 168-test suite passed again (13.621s). Previous BLOCKED credential condition resolved; complete/staged Git review and normal closure remain.

## Gate 6 | 2026-10-01T04:25:38+00:00 | verified Git closure

Full and staged diffs reviewed for exact Gate-6 paths; staged whitespace and credential-prefix checks passed. Fetched origin/main ea6bb6898ccd159798734169a4d14d975cf40bfc was ancestor of local main on intended origin URL. Source/audit commit b241f67d57d04df9a5aa79811230e8310a49771e created after 168 passing tests and one successful live probe; normal dry-run and push accepted. Post-push fetch verifies origin/main equals local HEAD b241f67d57d04df9a5aa79811230e8310a49771e, tree clean. No force/rewrite. Gate 6 PASS; Gate 7 may start.

## Gate 7 | 2026-10-01T04:43:25+00:00 | contract and preflight

Gate-6 receipt 2fa1208a2cd2346749b14f25fbea3b288f48c03a normally pushed; post-push fetch verified main=origin/main and clean tree before Gate 7. Read central Gate-7 acceptance, DEVELOPMENT_WORKFLOW.md, ARCHITECTURE.md, model strategy and current Gate-4/5/6 producer/consumer APIs. Contract gate_7.md defines one validated source-linked scholarly unit, bounded same-reading neighbors, approved terminology, replaceable mock/OpenAI first draft, formal findings and never-approved status. Three synthetic en/fr/ja calls maximum for acceptance; standard list-price cap $0.01, no retries, actual charges unknown. One scoped Sonnet builder call with $2 reported list-estimate ceiling and one evidence-based fix reserve $1; Opus/Astra 0. Temporary key from Gate 6 was removed from process environment and may be revoked; offline work proceeds first. No Gate-7 runtime API call yet; model quality remains unproven.

## Gate 7 | 2026-10-01T05:38:41+00:00 | software acceptance and three-language probe

G7-C1 scoped Sonnet builder returned after 342.755s, reported list estimate $1.3226808 including auxiliary Haiku usage; actual charge/Sol usage unknown. Initial 203-test suite failed two assertions and one error, and review found approved terms absent from provider prompt and no cumulative budget gateway. G7-A1/A2 preserve the failure and focused Sol repair: approved applicable terms enter bounded prompt, proposed loaded terms remain review findings, request is revalidated at adapter boundary, process-local shared budget limits calls/list estimate and stops on unmetered use, source/evidence output collisions are refused, mock omits prompt text, and formal checker counts exact protected tokens. Final full suite 213 tests passed (13.501s), including en/fr/ja synthetic source handoff, cache scope, numbers/names/notes/citations/formulas and negative paths. Public mock CLI succeeds. One process then made exactly three live gpt-6-luna calls with shared $0.01 standard list-price cap and no retries: en 118/14, fr 94/13, ja 94/11 input/output tokens; total $0.0000496 list estimate, actual charge unknown. Each saved draft is Hebrew, `draft_unapproved`, approved=false and zero formal findings. Read-only verification with final checker confirmed source/PDF hashes, unit/prompt/cache bindings and usage estimates. Fixtures use synthetic PDF envelopes and simulated source/terminology human selections; they do not establish extraction fidelity or scholarly translation quality. Artifacts/scripts remain ignored in outputs/gate7; key absent from process/user/machine environment after run. Git review/closure remains.

## Gate 7 | 2026-10-01T05:45:05+00:00 | verified Git closure

Reviewed complete and staged diff for 12 exact Gate-7 paths; `git diff --cached --check` and staged `sk-proj-` scan passed. Fetched origin/main 2fa1208a2cd2346749b14f25fbea3b288f48c03a was ancestor of local main on intended origin URL. Commit 9d016fbdcc2606b55f2f95cde7eaff889ee12ff9 created from the 213-test and three-call verified implementation. Normal dry-run and push accepted; post-push fetch verifies origin/main equals local HEAD, with clean tree. No force or rewrite. Gate 7 PASS; Gate 8 may start.

## Gate 8 | 2026-10-01T05:48:15+00:00 | contract and offline preflight

Gate-7 receipt 686d6db15113278682c6fd41188c99155cc34ce2 normally pushed; fetched main=origin/main and clean tree before Gate 8. Read central Gate-8 acceptance, current controls, architecture, policy and model strategy. Contract gate_8.md scopes conditional risk routing, strict source-to-target claims, false-positive disposition, one correction with formal recheck and unresolved human handoff. Synthetic fixtures suffice for software construction; real reviewer accuracy and human approval remain unproven. One scoped Sonnet builder call has $2 reported list-estimate ceiling plus one evidence-based $1 fix reserve. Runtime model calls 0 for offline build; no OpenAI key persists in environment. Opus/Astra 0.

## Gate 8 | 2026-10-01T06:12:32+00:00 | offline software acceptance

G8-C1 Sonnet builder with auxiliary Haiku returned in 587.738s, $1.9372894 reported list estimate, actual charge/Sol usage unknown. Its sandbox denied Python tests; G8-A1 records two reproduced failures in an 18-test targeted suite. Sol made one focused local repair G8-A2: inflected Hebrew negation, exact risk source span plus target offset, completed unapproved draft binding, canonical formal finding presence, selected OCR origin and all Gate-7 findings route to review/human. Final targeted suite 20 tests passes; full suite 233 tests passes (13.385s). Public mock CLI on saved synthetic Gate-7 en/ja drafts succeeds: en not_triggered, ja needs_human, both unapproved. No Gate-8 runtime API call and no key in process environment. Fake critic and synthetic fixtures demonstrate workflow only; actual semantic accuracy, source fidelity and scholarly judgment remain unverified. Review complete/staged diff and Git closure remain.

## Gate 8 | 2026-10-01T06:18:52+00:00 | verified Git closure

Reviewed complete and staged diff for 10 exact Gate-8 paths; `git diff --cached --check` and staged credential-pattern check passed. Fetched origin/main 686d6db15113278682c6fd41188c99155cc34ce2 was ancestor of local main on intended origin URL. Commit 35ba2acf33b627c53de2509e5953ebff83ba460c created after 233 passing tests and public mock CLI. Normal dry-run and push accepted; post-push fetch verifies origin/main equals local HEAD and clean tree. No force or rewrite. Gate 8 software PASS; Gate 9 may start.

## Gate 8 | 2026-10-01T06:23:47+00:00 | post-closure architecture correction

Before Gate 9 implementation, conductor found ARCHITECTURE.md's Gate-8 resolved review policy/cache identity requirement missing from the accepted review result. G8-A3 adds a versioned scholarly review policy and deterministic review_cache_key keyed by exact draft, profile, risks, policy and provider/models, plus a test that policy/provider changes alter identity. This preserves no persistent cache and no approval. Targeted suite 21 tests passes; full suite exits 0 with 234 tests. Original Gate-8 card and receipt remain as recorded; this correction awaits separate reviewed Git closure.

## Gate 8 | 2026-10-01T06:26:15+00:00 | architecture correction verified Git closure

Fetched intended origin/main e946a6e936ab89656859f272d677e8d36c3b6950, ancestor of local main. Reviewed seven exact correction paths; staged whitespace and credential-pattern checks passed. Commit fa95651ba3463e6483c5b586775a29657c2aba43 normally dry-run/pushed; post-push fetch verifies main=origin/main and clean tree. No force/rewrite. Gate 8 dependency correction closed before Gate 9.

## Gate 9 | 2026-10-01T06:30:24+00:00 | contract and offline preflight

Gate-8 correction receipt 3b9cfff3e53e63853a43ff7f1f5c1615b524d824 normally pushed; fetched main=origin/main and clean tree before Gate 9. Read central Gate-9 acceptance, architecture human-resolution/export boundary, current controls and existing producer records. Contract gate_9.md scopes a local static review page, explicit per-unit human decision record, and escaped bilingual HTML export keyed to exact source/draft/review versions. Synthetic decisions can test the software path; real human approval and scholarly quality remain pending. One scoped Sonnet builder call is capped at $3 reported list estimate and 900s, with one evidence-based $1 fix reserve; runtime paid model calls 0, Opus/Astra 0.

## Gate 9 | 2026-10-01T07:20:26+00:00 | offline software acceptance

G9-C1 Sonnet builder with auxiliary Haiku returned after 536.381s, $2.1967838 reported list estimate, actual charge/Sol usage unknown. Builder sandbox denied Python execution. G9-A1 records one initial 18-test failure: repeated identical decision created a second timestamped record. G9-A2 local repair uses deterministic decision identity, permits prior records as siblings but refuses unlinked second decisions, binds exact review content, protects missing numbers/notes/references/formulas/target script before approval, adds a local form to download an explicit decision JSON, and rejects export of superseded approvals. Targeted 19 tests pass; full suite 253 tests passes (14.429s). Public CLI with saved synthetic en structure/draft/review rendered review.html, accepted a labeled test-only human edit through a separate decision JSON, and exported bilingual HTML; artifacts and helper remain ignored. First render refused an older Gate-8 mock review after policy-key change; a current offline mock review resolved it. A visual check in personal Edge was rejected by automatic approval review because it could expose signed-in content; no UI action occurred and the rejection was not bypassed. HTML generation/escaping and CLI behavior were verified offline, but visual appearance, real human approval and scholarly quality remain unverified. No runtime model call. Complete/staged Git review and normal closure remain.

## Gate 9 | 2026-10-01T07:26:05+00:00 | final evidence-path and export-link recheck

Final local review adds selected source-evidence path protection to all Gate-9 output commands and an in-page anchor to the exact source unit in bilingual export. Targeted 19 tests pass; final full suite 253 tests passes in 14.203s. Public export rerun on ignored synthetic decision succeeded. No additional model call; earlier visual-check auto-review rejection remains as recorded. Proceed to complete/staged diff and Git closure.

## Gate 9 | 2026-10-01T07:29:41+00:00 | decision-history integrity recheck

Final inspection found that a supplied prior decision or history head needed its own content hash verified before supersession/export. G9-A2 local repair now verifies those hashes and rejects duplicate history records; a tampered-prior negative case passes. Targeted 19 tests pass; final full suite 253 tests passes in 13.387s. No additional model call. Complete/staged Git review follows.

## Gate 9 | 2026-10-01T07:32:14+00:00 | verified Git closure

Reviewed complete and staged diff for ten exact Gate-9 paths; `git diff --cached --check` and staged credential-pattern scan passed. Fetched intended origin/main 3b9cfff3e53e63853a43ff7f1f5c1615b524d824 was ancestor of local main. Commit bda6f337e54fd1352468515b76075116e255a5e8 normally dry-run/pushed; post-push fetch verifies main=origin/main and clean tree. No force/rewrite. Only ignored synthetic fixtures and outputs remain locally. Gate 9 offline software PASS; Gate 10 prerequisite assessment follows.

## Gate 10 | 2026-10-01T07:35:04+00:00 | pilot prerequisites and offline contract

Gate-9 receipt 81db65bf517f06bb666af9b4e1325a06f500718a normally pushed; fetched main=origin/main and clean tree before Gate 10. Central Gate 10 and model strategy require about 72 genuine expert-approved source/reference segments, balanced 24 per en/fr/ja, per-language/genre MQM findings, human correction time, measured cost/latency and critic/context comparisons. `rg --files` found no nonfixture PDFs or gold/pilot annotations in tracked repository; ignored synthetic Gate-7/9 outputs cannot establish quality. Asked user for local corpus path and expert reviewer availability. Contract gate_10.md scopes a deterministic offline annotation/report harness; full quality experiment and routing recommendation remain input-dependent. One Sonnet builder call capped at $2.50 reported list estimate and 900s; runtime paid calls 0, Opus/Astra 0. No change to Gate-9 acceptance.

## Gate 10 | 2026-10-01T08:17:36+00:00 | preliminary offline software checkpoint

User asked Sol to find examples online. Public-source search found six publisher links across en/fr/ja, recorded with article-level license/access caveats in `audit/gate_10_source_candidates.md`; no passage was promoted to expert-approved gold. G10-C1 Sonnet builder with auxiliary Haiku completed in 441.84s, $1.5686432 reported list estimate, actual charge/Sol usage unknown. Builder sandbox denied Python execution; initial targeted 28 tests passed using an official Python 3.9.13 embeddable runtime downloaded into ignored `outputs/tooling`, because the old `.venv` points to a missing installation. Code review found arm instances counted as approved segments, Japanese whitespace word counts, reviewer false positives counted as translation errors, and missing measured paired comparisons. G10-A2 local correction now counts distinct fully reviewed units, uses explicit word counts, binds human review attestations to draft hashes, requires shared glossary/page denominators, excludes false-positive/unconfirmed labels from critical errors, reports language/genre metrics and per-unit context/critic deltas, and keeps incomplete evidence preliminary. Targeted 35 tests passed before final missingness check; final full suite 291 tests passed in 13.578s, including public CLI preliminary and overwrite-refusal cases. No Gate-10 runtime model calls, no credential used, Opus/Astra 0. Actual PDF bytes, human identity and labels are not independently verified by the manifest alone. Full Gate-10 quality acceptance is blocked on genuine balanced excerpts, expert-approved Hebrew references, blind MQM judgments and measured candidate runs; no model winner or routing recommendation. Review diff/privacy and commit only as a labeled preliminary software checkpoint, then stop at this gate.

## Gate 10 | 2026-10-01T08:34:34+00:00 | final Hebrew-reference check

Final inspection added a required Hebrew-script check for the approved reference, with a negative English-only reference test. Full suite now passes 292 tests in 13.852s. Earlier 291-test result remains recorded as the prior checkpoint; no new model/provider call. Gate status remains preliminary software/BLOCKED full quality.

## Gate 10 | 2026-10-01T08:40:23+00:00 | staged accounting recheck

Staged diff review found that a direct human MQM error with no critic verdict was incorrectly added to critic true-positive counts and omitted from critical-error metrics. Corrected both counters; targeted 40 tests pass and full suite passes 293 tests in 14.725s. Severity-key ordering is now stable for reproducible JSON. Earlier counts remain as superseded checkpoints. No additional model/provider call; Gate 10 remains preliminary software/BLOCKED full quality.

## Gate 10 | 2026-10-01T08:45:56+00:00 | preliminary checkpoint verified Git closure

Reviewed complete/staged eleven-path diff, including all new source/test/candidate files; staged whitespace and credential-pattern checks passed. Intended origin URL and main branch verified; fetched origin/main `81db65bf517f06bb666af9b4e1325a06f500718a` equaled the local base and was an ancestor. Commit `b703dbba1b477059092165238c1e5caf4a52b038` is explicitly labeled preliminary; normal dry-run/push succeeded. Post-push fetch verifies main=origin/main and a clean tree. No force/rewrite or ignored local PDF/tooling output staged. This closes only the offline software checkpoint; Gate 10 quality remains BLOCKED on genuine gold and human judgments.

## Gate 10 | 2026-10-01T09:40:12+00:00 | public corpus continuation

Resumed from receipt 50d34946ddf6b24a938be4b8b38805bf879da1be and clean tree. User requested continued independent work despite missing expert data. Sol read execution controls and PDF skill, wrote a bounded corpus contract, used one targeted public-search batch and six publisher retrieval attempts (all succeeded, below 20 MB each, no retries), then retained primary schema-3 extractions and source PNGs under ignored outputs. First preparation excluded too much of the six-page Japanese document and stopped before manifest creation. Visual checks found French right-edge clipping and mirrored margins; geometry corrected with original bytes preserved. Independent metadata check exposed Japanese author/title corruption from PowerShell stdin encoding; UTF-8 editing restored attribution, then checks passed. Earlier packages remain superseded local evidence.

Final outputs/gate10_sources/candidates-v6 has 72 unapproved candidates, 62 cropped readings, 18 unapproved context plans, source images and two HTML indexes. Independent re-extraction verifies every reading, exact slice/hash, distinct text hash and nonoverlap; 108 image links and 18 context bindings pass. Seven page images inspected across all sources; no browser or expert approval. Public extract-pdf produced 17 English publishing page renders/comparison HTML. Public evaluate-pilot rejected candidate schema, exit 1; no report. G10-A4 guard/two regression cases pass focused 42 and full 295 tests (14.627s). No new provider/builder call or secret use. Commit metadata/hashes, helper, correction/tests and audit only. All PDFs/excerpts/refs/images remain ignored. Full Gate 10 stays BLOCKED on human judgments, sample coverage and measured comparison. Corpus contract creation-to-checkpoint approximately 20 minutes; Sol tokens/cost not metered.

## Gate 10 | 2026-10-01T09:47:16+00:00 | corpus checkpoint Git closure

Reviewed complete/staged eleven-path diff and metadata-only inventory; removed raw license extraction snippets from committed metadata. Exact-path staging, whitespace, credential-pattern and append-only audit checks passed. Verified main and authorized origin URL; fetched origin/main 50d34946ddf6b24a938be4b8b38805bf879da1be equaled base and was ancestor. Commit 628fca1adcffbcddda775308dc83c90d34a22cd7 normally dry-run/pushed; fetched main=origin/main and clean tree verified. Only ignored local source/preparation artifacts remain. This closes preliminary preparation and the source-identity correction; no model-quality recommendation or Gate 11 advancement.

## Gate 11 | 2026-10-01T10:07:30.502793+00:00 | authorized independent extension and builder scope

User requested Gate 11 and selected persistent budget/cache/usage controls. Central prompt had Gates 0-10 only; Sol added the explicitly authorized independent Gate-11 software extension and wrote audit/contracts/gate_11.md. Gate-10 quality stays BLOCKED, not waived. Initial builder launch was rejected by automatic approval review over transmission of repository content to Anthropic; no call occurred. User then expressly authorized one Sonnet invocation with only the ten hash-listed files in audit/contracts/gate_11_builder_scope.json, $3 reported estimate ceiling and 600s timeout. G11-C1 now runs against an isolated copied snapshot with restricted Read/Write/Edit tools; no shell/Git/web/subagents or private local input. Conductor will review allowed-path output and run offline fake/mock acceptance before any PASS or Git closure. Runtime paid provider calls 0; builder cost/duration pending.

## Gate 11 | 2026-10-01T10:42:01.965611+00:00 | builder result and bounded local correction

G11-C1 completed in 561.141s, exit 0, reported list estimate $1.902547; actual subscription charge unknown. One Sonnet invocation included auxiliary Haiku, 36 tools/37 turns. The approved ten-file isolated payload excluded credentials, PDFs and local outputs. Initial G11-A1 focused run failed (27 tests, one failure/two errors), including malformed SQLite handling and an incorrect fixture omitting source number 3. Conductor review found persistent controls opt-in, mutable usage events, absent in-flight claims, uncertain hold refunds and reused historical cache usage. G11-A2 is one bounded local correction with atomic claims/cache settlement, append-only events, retained uncertainty, default public persistence, safe read-only status and meaningful regressions. Retest pending; no PASS. No additional model or paid runtime call, Opus/Astra 0. Gate-10 quality remains BLOCKED.

## Gate 11 | 2026-10-01T10:43:23.386399+00:00 | correction reassessment

G11-A2 retest ran 128 tests in 3.383s: one failure/two errors. Durable budget/cache/concurrency regressions passed. Remaining defects are a missing CLI error-class import and an incorrect clean-draft expectation: the existing checker intentionally flags capitalized Axiom as a proper-name candidate. The Windows cleanup error is secondary to the assertion. G11-A2-R1 limits repair to that import and a needs_human expectation/context-managed fixture; preserves formal behavior. Local acceptance continues after reassessment, no additional model call or scope increase.

## Gate 11 | 2026-10-01T10:49:38.875427+00:00 | acceptance and final integrity review

Focused 128 tests passed in 3.563s; discovery 341 passed in 19.508s, including two concurrently appeared UI tests outside Gate 11. Public mock translation/critic/correction and exact repeats dispatched three times with three cache-hit events and zero paid requests/cost; Gate-9 consumer accepts unapproved provenance. The first capitalized-source fixture correctly bypassed formal findings; a fresh lowercase synthetic fixture exercises both review stages. Local evidence checker corrected source-field lookup; no product change or provider retry. Final ledger review found spent/stop aggregates also need reconciliation with durable settlement events; extending the existing counter-corruption regression within local repair scope. Rerun established repository tests plus Gate 11 only to separate concurrent UI changes. Six unexpected UI files appeared; user clarification pending, all Git mutations paused per repository rule.

## Gate 11 | 2026-10-01T10:52:45.290966+00:00 | verified software acceptance; Git ownership blocker

Gate 11 independent software acceptance PASS; Git closure BLOCKED pending ownership/authorization of six concurrent UI files. Final established repository suite plus Gate 11: 338 tests passed in 17.760s (runner wall 17.766s); focused 128 previously passed in 3.563s. Earlier discovery 341 included three concurrent UI tests and is superseded for Gate-11-only accounting; the provisional two-UI-test statement was incorrect. The first explicit-module runner omitted discovery's fixture import path (three import errors, 273 tests); corrected its ignored helper only. Final integrity validation reconciles attempted/settled counts, outstanding holds, observed spending and frozen state with durable reservations/settlement events. Public CLI outputs/gate11_demo_v2: translation plus critic/corrector reserve and settle exactly three synthetic dispatches under one fixed task, repeated commands add three linked cache hits with zero current usage/cost, zero outstanding hold and zero paid provider calls. Corrected reviews remain corrected_unapproved; Gate-9 resolver accepts cached provenance without granting approval. Metadata-event privacy and public read-only status verified. Initial capitalized fixture remains superseded bypass evidence. G11-C1: one Sonnet invocation with auxiliary Haiku, 561.141s, $1.902547 reported list estimate (ceiling $3), actual charge unknown. Sol local corrections/verifications not metered; Opus/Astra 0, runtime paid calls 0. No second builder call. Input manifest gate_11_builder_scope.json is preserved as the original pre-send snapshot; its not_sent status describes the initial rejected attempt, followed by explicit user approval and actual G11-C1 recorded in histories/model events. Six unexpected files appeared around 10:30-10:35 UTC; no Git mutation performed. User clarification asks permission to preserve UI files and commit only intended Gate 11 paths. Latest known synchronized base remains a770b8316855371da04992c8c9effa5f3739cfc4; no claim of committed/clean/pushed Gate 11. Gate 10 human quality remains BLOCKED: no gold references/blind expert judgments, coverage gaps or measured model comparison. Dated list reservations are not account billing guarantees.

Unexpected paths: UI_README_HE.md, run-ui.ps1, scholarly_translation/gui.py, scholarly_translation/web_ui.py, tests/test_web_ui.py, audit/contracts/ui_local.md.

## Gate 11 | 2026-10-01T10:54:05.506871+00:00 | pre-staging checks

Intended fifteen-path inventory prepared in ignored outputs; tracked diff, append-only history prefixes, JSONL parsing, credential-pattern scan and whitespace checks passed. Six unexpected UI paths remain untracked and untouched. No staging, commit, remote mutation or additional tests/provider calls; user ownership clarification still pending.

## UI-SIMPLE | 2026-10-04T13:02:00+00:00 | user-directed document flow checkpoint

User explicitly requested an uncluttered PDF/EPUB to translation flow, optional review and secondary settings. Contract audit/contracts/ui_simple.md; Sol implements locally with no new builder transmission or paid provider call. Current tracked UI main 2574e01 supersedes the prior six-file ownership blocker; preserved verified Gate-11 work supplies persistent controls. Initial engine acceptance exposed Windows reader/atomic-replace sharing; one RLock guards manager reads/writes/revisions. Focused retest passed 23 tests in 6.331s. New guarded HTTP document lifecycle tests passed in the first 64-test combined run except an existing preview test indentation accidentally moved outside its temporary-root scope during insertion; exact test indentation repaired, retest pending. Browser at owned local preview verifies compact upload/translate screen; first visual version was too tall and was reduced before acceptance. Local sample starts without API and explicitly says no translation. Thirty-minute soft checkpoint: scope unchanged, paid/runtime/model calls zero, finish acceptance and Git closure. Gate-10 human quality remains blocked.


## UI-SIMPLE | 2026-10-04T13:17:34.849140+00:00 | Gate Card: software PASS, browser limitations recorded

User-directed upload-to-download flow implemented with separate unapproved/source-unreviewed document-draft@1 records. PDF text/EPUB spine input; actual model/effort/cap settings; durable reservations/raw cache; progress/recovery; immediate escaped HTML/TXT downloads; optional revisioned edits. Removed sidebar, stage tracker and generic command fields from homepage. First tall visual layout was reduced so upload/translate fit on the observed laptop viewport; 390x844 settings/result/review layout also inspected. Demo explicitly says no translation/API. Windows launcher syntax/dependency imports verified, including project runtime fallback; updated Hebrew guide and architecture boundary.

Evidence: UI-SIMPLE-A1/A2; focused 64 tests in 7.616s; full 363 tests in 27.333s; final HTTP seven tests in 4.277s after unused command-config removal. First engine Windows sharing failure and HTTP fixture indentation repair remain preserved above. Browser confirms sample completion, saved optional edit, model/effort choice, preferences and reopening a saved result. Browser extension denied automated file chooser setFiles (Allow access to file URLs unavailable); download event capture timed out. Automatic approval review rejected general Edge download-history inspection over unrelated private filenames. No workaround attempted. Uploaded bytes and both attachment formats/content are verified through guarded HTTP tests; end-to-end browser picker/download capture remains unverified. No paid quality/account-access test.

Sol single local writer; new Sonnet/Opus/Astra/runtime paid calls 0, list runtime test cost 0, Sol usage unknown. Existing Gate-11 Sonnet invocation remains separately recorded; no new builder. Gate-10 human quality BLOCKED, no model winner/research approval or OCR/layout-reconstruction claim. Complete diff, append-only logs, JSONL, credential-pattern and whitespace checks pass. Intended origin/main fetched and equal to main 2574e01; Git closure now proceeds with a focused Gate-11 dependency commit then UI commit and receipt. Prior ownership blocker is resolved by tracked UI commits and explicit user repair request; intentional UI work stays pending during dependency commit, no intermediate clean-tree claim.

## Gate 11 | 2026-10-04T13:17:34.849140+00:00 | ownership resolved and integration accepted

Prior unexpected UI paths are now tracked on main 2574e01 and explicitly authorized for repair. Gate-11 software acceptance stands (338 prior tests), with its dependent simple-document integration in the current 363-test passing suite. Full intended controls/code/contracts/audit diff reviewed, fetched authorized remote matches base. Commit dependency first, finish UI and receipt before final clean/push claim. G11-C1 verified value is now integrated/tested; its original model event remains append-only rather than rewriting pending snapshot fields.

## Gate 11 / UI-SIMPLE | 2026-10-04T13:20:00+00:00 | dependency commit receipt and final UI review

Verified dependency commit 912593237e8df77a057f1284461c73537e5f0ac5 contains fourteen explicitly staged reviewed Gate-11 code/control/contract/audit paths. Staged content equality and whitespace passed; pending UI paths are intentional current work, not unexpected ownership. README Gate-11 documentation accompanies the UI integration commit. Final current-code preview imports refreshed at http://127.0.0.1:54984/ and initial page visually verified; prior owned previews stopped. Last UI-only change removes unused CLI step configuration; seven HTTP tests pass in 4.277s and browser initialization succeeds. Full 363-test result stands. UI staged review/commit and authorized normal push/receipt pending; no intermediate clean/synced claim.


## Gate 11 / UI-SIMPLE | 2026-10-04T13:23:18.603047+00:00 | final Git receipt

Gate-11 dependency 912593237e8df77a057f1284461c73537e5f0ac5 and simple-document UI c5f754b354ff9d540476dabd6572131a2b9c2ee5 normally pushed to verified authorized origin/main (https://github.com/neria-baris/scholarly-translation.git). Complete diffs reviewed; fourteen dependency and sixteen UI staged paths matched reviewed working content. Whitespace, append-only histories/JSONL and credential-pattern checks passed; no ignored inputs/results/keys staged. Ancestry checked, no divergence or unexpected changes. Fetch verified main=origin/main=c5f754b354ff9d540476dabd6572131a2b9c2ee5 and clean tree before this receipt. Receipt's own hash is intentionally not embedded.

Software acceptance: full 363 offline tests pass (27.333s), focused 64 (7.616s), final HTTP seven (4.277s). Desktop/390x844 layout, clearly labeled demo completion, optional saved edit, model/processing preferences and saved-result reopening observed. HTTP upload/download attachment content passes. Browser file selection denied by extension permission; download-event capture timed out and general history inspection was automatically rejected over unrelated private filenames. Those browser capture limits remain recorded; no bypass or paid API test. Current-code owned preview http://127.0.0.1:54984/ (session 4937) left open as deliverable, prior previews stopped. Gate-11 software Git blocker resolved; Gate-10 human quality remains BLOCKED, no approved scholarly output/model winner/release claim. New builder/adviser/paid runtime calls 0; Sol usage not metered. Final receipt push/equality/clean verification follows without further feature work.

## Session C | 2026-10-04T14:05:43.7546992+00:00 | optional review and chapter-QA software acceptance

User explicitly requested the supplied `C_review_and_chapter_qa.md` session. Clean synchronized base was `36fbbf04e22bae2643b91956940c81a7cd2fc6ed`; contract `audit/contracts/session_c_review_qa.md` limits work to a provider-neutral API and three byte-identical supplied runtime prompt assets, without changing segmentation, selected context, Gate-8 correction or provider/runtime-control architecture. SC-C1 was one bounded Claude Code Sonnet implementation invocation with auxiliary Haiku: exit 0, 294.150s, 26 turns, $0.8383876 reported list estimate, actual subscription charge unknown. It added the module, prompt assets, 23 focused tests and README documentation; no paid runtime provider call occurred.

SC-A1/A2 preserve conductor review and the bounded local correction. Initial inspection found skipped records lacked stable input/prompt hashes, candidate/chapter free-form prompt sections did not state the parser grammar, structured parsers could ignore partial malformed content, placeholder replacement could cross-substitute source data, and candidate IDs could collide with the line protocol. The focused correction adds hashed provenance, appended machine-readable output contracts while preserving the supplied assets byte-for-byte, complete-block parsing, bounded adapter failures, safe single-pass substitution, ID validation and request revalidation. The first independent focused run exposed the supplied candidate prompt's intentional output placeholder; the input-placeholder check was narrowed and rerun. Final focused suite: 31 tests pass in 0.094s. Final discovery: 394 tests pass in 27.758s, one existing skip. Byte-compilation, whitespace and prompt SHA-256 equality checks pass. Outputs remain `approved: false`; `off` and non-risky `risk_based` paths do not call adapters. Real model formatting/semantic accuracy, scholarly quality and human approval remain unverified. Git review/closure follows; Gate 10 human-quality BLOCKED status is unchanged.

## Session C | 2026-10-04T17:32:09.7461546+00:00 | verified Git closure

Commit `fd5c852af241c6705ab4ec1bbb0d6ff5ac36b7cb` was created with repository-style message `Add optional semantic review and chapter QA`; hooks made no follow-up changes. Immediately before push, fetched `origin/main` remained the reviewed base `36fbbf04e22bae2643b91956940c81a7cd2fc6ed` and was an ancestor of the feature commit. Normal dry-run and push of `HEAD:main` succeeded; post-push fetch verified HEAD=origin/main with left/right count `0 0` and a clean worktree. No force, rewrite, branch deletion, ignored output, credentials or private source data were involved. This receipt update is the only follow-up change; commit/push and final clean/equality verification follow.
## PROVIDER-MODEL | 2026-10-04T14:09:56.2295443Z | implementation and acceptance

User-authorized Session E executed under audit/contracts/provider_model_selection.md. Claude Code builder attempt PM-E-C1 failed connection-refused before model execution (180.237s, zero tokens/cost, no product edits); no retry. Sol implemented validated role/provider/capability configuration, OpenAI/Anthropic/DeepSeek/custom-compatible adapters, role-aware CLI resolution, exact cache/provenance identity, sanitized credential/setup failures, examples/docs, and mocked acceptance. Non-OpenAI pricing is deliberately not guessed: one controlled call can return token usage, then the unknown-price reservation freezes further calls and prevents caching. Legacy commands remain compatible. Focused 122 and full 378 tests pass (27.509s; one established skip); no live provider call. Compact document UI limitation and Gate-10 human-quality blocker remain explicit. Commit/push receipt pending.

## PROVIDER-MODEL | 2026-10-04T17:42:41.1456277Z | Session C consumer integration

Origin advanced by the verified Session C feature/receipt while Session E was in progress. Sol preserved the reviewed work as an unpublished commit, rebased it onto 4bf8482, resolved only append-only audit/checkpoint conflicts by retaining both sessions, then integrated the newly visible unit-review, candidate-comparison and chapter-QA consumers. New role helpers select semantic reviewer, candidate evaluator and chapter QA with exact provider/model/capability provenance; invoked configured requests can build the shared adapter, while off/skipped paths remain call-free. Focused 158 and full 412 tests pass in 24.463s with one existing skip. No runtime provider call or prompt/QA policy change. PM-E-A3 supersedes the earlier combined count; final Git closure follows.

## PROVIDER-MODEL | 2026-10-04T17:46:34.2724439Z | feature commit and push receipt

Complete/staged diff review covered eighteen intended paths. JSONL parse, append-only histories, whitespace, secret-pattern, ancestry and clean-tree checks passed. Local unpublished commit was rebased onto newly landed verified Session C, producing `a705e0a51ad8bb3b19ed9644cf7b0c69a7934631`; no published history was rewritten. Normal dry-run and push of `HEAD:main` advanced authorized origin/main from 4bf8482 to a705e0a. Post-push fetch verified exact equality and clean worktree. Software evidence remains 158 focused and 412 full offline tests in 24.463s with one established skip; runtime provider calls zero. Receipt commit/push and final equality check follow.

## INTEGRATION-BOOTSTRAP | 2026-10-04T18:32:32.8673597Z | validated continuity preparation

Read authoritative instructions in order and the unchanged user-supplied audit/claude_integration_conductor.md. Git inspection found clean A/B unmerged and C/E already on main 633c33d. Fresh main 412 tests pass (27.183s); B 375 pass (29.246s, one skip). Worktree sandbox writes were denied, so validation reruns use authorized filesystem access; no code repair inferred. Python resolved to the bundled 3.12 runtime. Added concise CLAUDE bootstrap and native-background handoff helper; parser and ValidateOnly pass without launching Claude. Origin fetch and main equality 0 0 verified. A full summary pending before integration. New external model/runtime calls 0; conductor quota and charges unknown.
## SESSION-A | 2026-10-04T17:50:29Z | contract, builder and baseline

Read the current controls/architecture/state and user Session-A prompt; repository was clean at `36fbbf04e22bae2643b91956940c81a7cd2fc6ed`. Contract `audit/contracts/session_a_structure_segmentation.md`. Baseline full suite: 363 passed, one optional OCR-weight skip, 27.420s. System Python was unavailable; all verification used the bundled Codex Python runtime. First restricted Claude call was blocked by sandbox networking after 179.994s with zero usage; escalation was initially rejected, then the user explicitly approved the exact repository-scoped call. SESSION-A-C1 completed in 1,336.161s with Sonnet plus auxiliary Haiku, $4.6888078 reported list estimate, actual charge unknown, and no test execution.

## SESSION-A | 2026-10-04T17:50:29Z | verification and focused repair

Initial structure discovery had one fixture geometry error; the first full run otherwise reached 369/371 with one local-UI schema-stage rejection. Conductor review found missing parent/order hierarchy, no executable subheading path, no explicit unit-node mapping and no persisted effective unit policy. SESSION-A-A2 added and validated those fields, French/Japanese conservative markers and non-space Japanese sizing. Embedding node IDs in unit records first broke translation-memory exact shape; the final separate `unit_node_links` collection preserves legacy consumers. Local UI accepts both structure schema stages. Focused structure, terminology/memory, translation and UI suites pass. Final full suite: 375 passed in 26.071s, one optional OCR-weight skip; `git diff --check` passes aside from informational Windows line-ending warnings. Runtime provider calls 0; scholarly/source/human approval unchanged.

## SESSION-A | 2026-10-04T17:50:29Z | pre-commit Git status

Reviewed tracked and untracked Session-A code/tests/docs/contract, no secrets/private input/generated outputs staged. Branch remains `agents/run-it`. Local `origin/main` tracking ref advanced during work from the common base to `633c33d` through Session-C/provider-selection commits; no merge/rebase/push attempted because the user requested a commit on this branch without merging other branches and standing push authorization is only for `origin/main`. Exact-path local staging/commit and clean-tree verification follow.

## SESSION-A | 2026-10-04T17:57:10Z | local commit receipt

Fifteen explicit reviewed paths staged with no unstaged delta; staged path set, diff check and privacy scan passed. Commit `8bc29b20a26f981b258fa9af91730a42ebef40c9` created on `agents/run-it`; immediate tree clean. No push: branch has no upstream, authorized push scope is origin/main, and origin/main advanced by four commits while Session A explicitly forbids merging other branches. Append this receipt, commit it locally, and verify final clean/ahead-behind state without embedding the receipt commit's own hash.

## INTEGRATION-A | 2026-10-04T18:36:48.879980+00:00 | sequential integration verified

Validated clean A branch 8bc29b2/d7b6723 and scoped diff; isolated full 375 tests pass (31.290s, one skip). Merge into main 59235ee plus C/E produced only shared audit/checkpoint conflicts. Both append-only tails retained with base-prefix checks; no source or product conflict. Combined full 424 tests pass in 22.277s. B remains independently verified (375 tests, 29.246s, one skip), unmerged. Continuity bootstrap commit 59235ee syntax/ValidateOnly verified. Runtime/model calls 0; Sol quota/charges unknown. Reviewed A merge commit and authorized normal push follow. Source/quality limitations unchanged; Gate 10 human evidence BLOCKED.
## Gate 12 | 2026-10-04T14:09:17.6773072Z | translation-profile execution and acceptance

Started clean on `agents/run-it-de649c23` at 36fbbf0, equal to `origin/main`; read the user-supplied B prompt, both runtime profile prompts, repository controls, architecture and current state. Initial `python`/`py` launchers were unavailable; the managed runtime Python then passed 88 focused translation/runtime-control tests in 3.221s. Wrote `audit/contracts/gate_12.md` before implementation and invoked one bounded offline Claude Code builder. G12-C1 completed in 631.031s with $1.3716102 reported list estimate, actual charge unknown; no runtime provider/network call. Its 55/373-test report was independently reproduced before correction as 55 focused and 373 full passing.

Conductor diff inspection found that argparse still allowed only scholarly and that several material supplied prompt instructions were missing. G12-A2 added the literary public CLI choice, restored source-context authority, semantically complete-unit, Japanese omitted-subject, culturally specific expression and best-supported uncertainty rules, and expanded deterministic cache-version/public-interface tests. First correction run failed one new assertion because the expected phrase crossed a source line break; changed only the test to assert both stable fragments. Final focused result: 57 tests, 1.130s, pass. Final full result: 375 tests, 30.922s, pass with one unrelated existing skip. `git diff --check` reports only Windows LF-to-CRLF notices, no whitespace error. No secrets, source PDFs, generated translations or local outputs are in the intended paths.

Schema/version summary: `translation-draft@1` and schema 1 remain; `translation_note` is additive and nullable. `TranslationRequest` adds bounded approved decisions/local state/source context, their fingerprint, and per-profile prompt/config versions. Cache identity now includes those revisions and effective context. Legacy unstructured mock/plain responses remain supported with a null note. Limits: supplied context is bounded but selected elsewhere; no literary review/QA policy or quality claim; the maximum existing source-unit bound is unchanged. Exact staging/commit pending.

## Gate 12 | 2026-10-04T17:35:56.2045346Z | branch commit receipt

Staged exactly eleven reviewed paths; no unstaged or unexpected path remained. Staged stat was 557 insertions/40 deletions. Staged whitespace, JSONL, append-only-history and credential-pattern checks passed. Commit `64f7ca6f77677add0c6943d25eba871f4be5cf83` (`Add versioned scholarly and literary translation profiles`) succeeded with hooks enabled; post-commit tree was clean. No push was attempted because the isolated `agents/run-it-de649c23` branch has no upstream and the task requested a commit to this branch. The receipt commit follows; its own hash is not self-recorded.

## Gate 12 | 2026-10-04T17:38:28.8541358Z | final remote check correction

Receipt commit `fcf0ca77e37b450bcd798797be146892d62a65bd` succeeded. The subsequent required ancestry check detected that `origin/main` had moved from starting base 36fbbf0 to Session-C receipt 4bf8482 through pushes recorded locally at 20:31–20:34 Asia/Jerusalem. Graph count is two branch-only and two origin-only commits; ancestry check fails in both integration directions. No branch content changed externally and the tree remained clean. Stopped without fetch-side reconciliation, merge, rebase or push; record this correction because the immediately preceding receipt used the now-stale base statement.

## INTEGRATION-B | 2026-10-04T18:40:50.532460+00:00 | software PASS; reviewed Git closure follows

A merge a35d3ab normally pushed and fetched; main/origin equality 0 0 and clean tree verified. B isolated 375 tests pass (29.246s, one skip). Sequential B merge preserves both audit tails, both profiles and E role metadata. Resolved translation request signature, cache identity, canonical revalidation and result parsing by combining B context/profile inputs with E provider/capabilities and unpriced stops. CLI accepts literary and configured roles. Combined full 436 tests pass in 22.222s. Runtime/model calls 0, quota/charges unknown. Source/quality limits remain, Gate 10 BLOCKED. D/X await checked contracts/common base.

## SESSION-D | 2026-10-04T19:40:00+00:00 | chapter-aware context strategy, integrated and pushed

Claude acting as temporary integration conductor launched Session D as an isolated
worktree/branch sub-agent (worktree-agent-ac188145aaddcd523) off checked common base
6741f65, per audit/contracts/session_d_context_strategy.md. The builder added
scholarly_translation/context_strategy.py and extended translation.py: when
ModelCapabilities are supplied, build_translation_request now sends the unit's
enclosing chapter/part node as full context when it fits the model's usable-context
budget (headroom-adjusted), else expands target+bounded original source outward
within the chapter/reading; capabilities=None reproduces the exact pre-Session-D
one-previous/one-next behavior unchanged. Added build_whole_chapter_translation_request
as an explicit opt-in comparison mode, target-vs-context provenance fields, and
context_policy_version/context_mode in compute_cache_key/to_metadata_dict (unit
cache identity depends only on text actually sent, never unrelated chapter text
elsewhere). 20 new tests in tests/test_context_strategy.py.

Conductor review: read the full translation.py/context_strategy.py diff, confirmed
reuse of document_structure._word_count (no second tokenizer) and no change to
persisted node/unit schema. Independently reran the suite in the isolated worktree
(456 tests, 1 skip, 22.2s, matching the builder's report) before merging. Merged
into main via --no-ff merge commit 89adbd76 (no conflicts; D and X have disjoint
file ownership). Reran full suite on merged main: 456 tests, 1 skip, 26.4s, OK.
Fetched origin/main, verified ancestry, pushed; post-push fetch confirmed
main == origin/main == 89adbd76. No runtime provider calls; mock-only.

## SESSION-D-ADDENDUM | 2026-10-05T00:00:00+00:00 | persistent cross-chapter state, integrated and pushed

User supplied a mid-session addendum (audit/raw/addendum_2026-10-05_persistent_state.md)
requiring a persistent, versioned, cross-chapter document-state mechanism
(terminology/definitions/notation/character/register/names/unresolved-
ambiguity continuity), explicitly deferring the chapter-QA-to-state wiring
to Session G and forbidding a Session C rerun. The conductor noted that the
already-merged Session D work (89adbd76) implemented only chapter-aware
context sizing, not persistence, and drafted a scoping contract
(audit/contracts/session_d2_persistent_document_state.md) intending to
launch a separate D2 sub-agent. Before that launch, the still-resumable
Session D builder (worktree-agent-ac188145aaddcd523) was itself resumed
with the addendum and implemented the scope directly, stacked on its own
prior commit: new scholarly_translation/document_state.py (versioned
propose/find_conflicts/commit_update, certainty levels, mandatory source
provenance, model-authored items barred from "established") plus
translation.py wiring (document_state parameter, PERSISTENT DOCUMENT STATE
prompt layer folded into the existing glossary/approved-decisions section,
document_state_version/fingerprint in compute_cache_key/to_metadata_dict).
19 new tests in tests/test_document_state.py. No separate D2 sub-agent was
launched; the drafted contract was annotated "fulfilled" and kept as the
record this work is judged against.

Conductor review: read document_state.py in full and the translation.py
diff; confirmed the module does not duplicate glossary.py, does not wire
into review_qa.py/semantic_review.py (left for Session G per the
addendum), and that omitting document_state leaves every existing caller
unchanged. Independently reran the suite in the isolated worktree (475
tests, 1 skip, 23.0s, matching the builder's report) before merging via
--no-ff merge commit 8759b611 (no conflicts). Reran full suite on merged
main: 475 tests, 1 skip, 26.2s, OK. Fetched origin/main, verified ancestry,
pushed; post-push fetch confirmed main == origin/main == 8759b611. No
runtime provider calls; mock-only. Session X (PDF/EPUB export) remains
running in a separate isolated worktree, disjoint files, unaffected.

## SESSION-X | 2026-10-05T00:20:00+00:00 | PDF/EPUB export, integrated and pushed

Claude acting as temporary integration conductor launched Session X as an isolated
worktree/branch sub-agent (worktree-agent-a265740e1a350b35a) off checked common base
6741f65, per audit/contracts/session_x_export.md, running in parallel with Session D
(disjoint files: export_common.py/export_pdf.py/export_epub.py vs
translation.py/context_strategy.py/document_state.py). The builder added a
PDF exporter (reportlab-based, reflow not pixel-fidelity, a small documented
word-token Hebrew/RTL bidi routine since no rlbidi package is installed,
verified against physical glyph positions via pdfplumber) and an EPUB
exporter. For EPUB it found no canonical document_structure producer exists
yet (segmentation.build_readings requires source_kind=="pdf") and, rather than
inventing a second PDF-style heuristic classifier (forbidden by the contract),
treated the EPUB's own XHTML block structure as ground truth under a new,
clearly-labelled epub-structure@1 schema distinct from document_structure
schema 2 - flagged as a transparency note, not an escalation. Archive
rebuilding copies all non-chapter files byte-for-byte unchanged. 34 new tests;
requirements.txt pins Pillow==12.3.0 (already installed transitively via
reportlab, not a new dependency).

Conductor review: read export_common.py/export_pdf.py/export_epub.py in full;
confirmed the change is purely additive (only requirements.txt touches an
existing file, avoiding any conflict with Session D's translation.py/
context_strategy.py/document_state.py changes) and that per-unit manifests
plus explicit limitations lists avoid silent drops/mis-rendering anywhere.
Independently reran the suite in the isolated worktree (470 tests, 1 skip,
25.6s, matching the builder's report) before merging via --no-ff merge
commit 9506352e (no conflicts). Reran full suite on merged main: 509 tests,
0 skips, 29.2s, OK (D's 475 + X's 34). Fetched origin/main, verified
ancestry, pushed; post-push fetch confirmed main == origin/main == 9506352e.
No runtime provider calls; mock/fixture-only.

A/B/C/D(+addendum)/E/X are now all integrated on main. Per
audit/claude_integration_conductor.md Phase 4/5, F (UI) is next, then G
(final integration review, which per the user's 2026-10-05 addendum also
owns wiring Session C's chapter QA into Session D's document_state.py - see
audit/raw/addendum_2026-10-05_persistent_state.md).

## SESSION-F | 2026-10-05T01:00:00+00:00 | simple UI rewired onto canonical backend (PDF path), integrated and pushed

Claude acting as temporary integration conductor launched Session F as an isolated
worktree/branch sub-agent (worktree-agent-ab23e0a88f5fcb6ed) off checked common base
d9458d7, per audit/contracts/session_f_simple_ui_integration.md. The builder
replaced document_draft.py's ad-hoc internals (fixed-size chunking, hard-coded
two-OpenAI-model list, direct openai SDK calls, HTML/TXT-only output) with
pdf_extract.extract_pdf -> segmentation.build_structure -> per-unit
translation.build_translation_request_for_role/run_translation ->
quality-mode-gated review_qa (Fast/Checked/Thorough mapped onto
UNIT_REVIEW_POLICIES/CHAPTER_QA_POLICIES exactly as specified) ->
export_pdf.export_pdf, while preserving the job-runner's durable/resumable
shape. Model selection is now Auto (zero-cost mock) or a server-supplied
model-config file resolved via model_config.py's provider-neutral registry.

The builder hit the contract's own named stop_condition on EPUB:
translation.build_translation_request transitively requires every reading
candidate to carry literal provenance stage "digital-pdf@1" plus positive
pdf_width/pdf_height geometry (enforced in source_reading.py, confirmed by
conductor inspection at source_reading.py lines ~132-162), which EPUB text
(reflowable, no page geometry) cannot honestly satisfy without fabricating
false provenance or extending that core schema - explicitly out of this
session's scope. The builder correctly stopped and reported this rather than
improvising around it; EPUB upload is refused in the UI with a clear message.

Conductor review: read document_draft.py (full rewrite)/web_ui.py/ui.html/
ui.js diffs in full; confirmed the removed browser-pasted-API-key path for
this flow (replaced by env-var/model-config-file-based credentials, needed
for multi-provider support) is intentional and documented, and remains
available unchanged for the separate advanced CLI-step dashboard.
Independently reran the suite in the isolated worktree (513 tests, 1
pre-existing unrelated skip, 24.6s, matching the builder's own before/after
comparison) before merging via --no-ff merge commit c2b6b174 (no conflicts).
Reran full suite on merged main: 513 tests, 0 skips, 26.8s, OK. Fetched
origin/main, verified ancestry, pushed; post-push fetch confirmed main ==
origin/main == c2b6b174. No runtime provider calls; mock/fixture-only.

EPUB-translation-in-the-simple-UI is a genuine product/architecture decision
(a core schema extension to source_reading.py/document_structure.py) raised
to the user rather than decided unilaterally; see the conversation and any
follow-up contract this produces. A/B/C/D(+addendum)/E/F(PDF-only)/X are
integrated on main; Session G (final integration review) is next, scoped per
audit/claude_integration_conductor.md plus the 2026-10-05 persistent-state
addendum, and should treat the EPUB-translation gap as a known, explicitly
tracked limitation unless the user's decision changes that before G runs.

Session G (2026-10-05): acted as conductor and sole builder under the
continuity bootstrap (CLAUDE.md), since the remaining work (budget/cache
wiring, chapter-QA/document-state integration, EPUB export reconciliation)
was interdependent and touched the same files, not a case for two parallel
isolated writers. Confirmed via git status/log/branch -a/worktree list/
fetch that main was already at 15426ec and already equal to origin/main
(the checkpoint's claim of 2 unpushed commits behind was stale -- those
had already been pushed before this session started); proceeded with
Session G from there per audit/claude_integration_conductor.md's recorded
next action rather than the checkpoint's stale push instruction.

Implemented and tested the five fixes listed in the SESSION-G gate_history.md
entry above (budget/cache wiring shared across translate/review/chapter-qa,
output-cap-aware worst-case reservation, chapter-QA-to-document-state
adapter with grounded/certainty-limited STATE_UPDATES, export_epub.py
reconciled with the canonical schema-2 structure, EPUB wired into
document_draft.py/web_ui.py/ui.html/ui.js). Also added, at the user's
explicit request alongside G: a double-click launcher ("Run Scholarly
Translation.vbs", plain launcher for the existing run-ui.ps1 -- adds no new
server-start logic) and a simple-GUI Windows installer (install.ps1, a
WinForms window with a progress bar and log that creates .venv, installs
requirements.txt, verifies the install, and creates a desktop shortcut;
Install.bat is the double-click entry point), documented in INSTALL_HE.md
and referenced from UI_README_HE.md/README_START_HERE_HE.md.

Updated README.md (rewrote the stale "Simple local document UI" section,
which still described an obsolete document-draft@1/HTML-output UI; added
"Translation context, chapter QA and persistent state" and "PDF/EPUB
export and its limitations" sections; corrected a stale claim that the
simple UI never consumes role configuration) and UI_README_HE.md (full
rewrite to match the actual current upload/profile/quality/model/budget/
download flow, folding in the budget/cache/state fixes and the honest
remaining export/OCR limitations). Replaced the now-incorrect
test_document_draft.py EPUB-blocker test with real EPUB coverage.

Full suite: 527 -> 549 tests pass throughout, rerun after every change
batch (runtime_controls/translation -> review_qa -> document_draft/
export_epub -> web_ui/frontend -> docs/launcher). Independently smoke-
tested the live local server over HTTP (real EPUB upload, Auto-mode
translate-to-completion, download, verified rebuilt-archive content) before
closing out. No paid provider calls; Claude Code's own usage for this
session is not independently metered. Git/commit/push status recorded in
the next checkpoint update, not self-referentially here.

## 2026-10-05T05:10:48.384456+00:00 | AUTOMATION-1 | execution resumed

User authorized the automation plan plus per-model prices, UI model/API-key selection and deterministic token counting. Baseline e333fd3/main: 549 offline tests pass using bundled Python 3.12.14; repository .venv points to an unavailable Python39. Created ignored isolated test environment with tiktoken0.12.0/openai3.24.0/anthropic1.11.0; explicitly downloaded public encodings. Official model/pricing/count/cache sources verified. Existing .claude/worktrees are unrelated, preserved and ignored. Two wrapper launches waited on inherited stdin and were terminated before any observable output/edits; closing stdin made the scoped builder run. No runtime generation/pilot activated. Contracts automation_1/2/3 written; only automation_1 construction active.

## 2026-10-05T05:39:57.642018+00:00 | AUTOMATION-1 | verification

Initial573-test run:7 failures+7 errors. One builder repair adapted stale fixtures, explicitly left contract omissions. Conductor completed offline verified-cache-only tokenizer loading, configured large-unit/prompt allowance with model-fit and envelope reserve, independent QA fit,128k ceilings, provider-type pricing for aliases, malformed usage/stop validation, supported default Sol effort, and pinned actual SDKs. One new long-PDF fixture initially wrote outside page geometry; corrected wrapping/font geometry, six focused contract tests then passed. Final580 tests pass in33.590s via outputs/automation/venv; diff whitespace passes. Observable Claude builder calls:2 Sonnet5 plus reported auxiliary Haiku, combined list estimate$4.8100636, actual subscription charge unknown; Astra0, runtime provider0. Original stdin-blocked wrappers had no returned model metrics and were terminated; cost unavailable. Costs/sample formula independently checked:100k input(60kread/10kwrite),20koutput gives Luna.01485/Sol.291/Sonnet.297/Opus.582; Sol273kinput+1koutput1.107. Limits: catalogue is dated; GPT6/Claude local tokens are labelled estimates, custom price assumption not provider billing ceiling; UI/planner pending; expert pilot still blocked.

## 2026-10-05T05:42:24.044620+00:00 | AUTOMATION-1 | verified push receipt

Commit f5deb4daeff2f12f69f7d1174e5da7398975e260 passed580 tests; complete and staged diffs reviewed. Normal fast-forward push to the authorized origin/main succeeded; post-push fetch verifies HEAD==origin/main and a clean tree. Receipt committed separately; next construction is AUTOMATION-2.

## 2026-10-05T06:01:30.677862+00:00 | AUTOMATION-2 | FIX / PARTIAL

Initial scoped Claude Sonnet5 builder:58 turns,789.075s, list estimate$3.2998919, actual Pro charge unknown; auxiliary Haiku reported, no subagents/Astra/Opus/runtime provider. 608-test suite has2 new invalid-fixture errors. Independent five-case contract suite after valid PDF geometry has5 substantive failures: output clamping, QA groups/counts and oversized Hebrew fit, negation risk routing, job pause/resume API. Code review additionally found late raw persistence, injected review controls bypass, insufficient QA tail protection and unstable batch prefixes. One scoped repair requested with actual-envelope planner, controlled journal lifecycle, bounded corrections/rechecks and real pause/resume. Initial result retained; acceptance pending. Sol prepared ignored isolated Python3.12 runtime and corrected launcher/installer3.10+ discovery independently for next slice; those paths not in builder scope.

## 2026-10-05T07:40:17.144712+00:00 | AUTOMATION-2 | verified integration

Initial Sonnet implementation and one repair were PARTIAL; independent contract tests disproved initial planner/recovery/tail behavior. Conductor rebuilt complete prompt/output-fit planning, semantic batches, actual-Hebrew QA repartition and atomic tail protection, stable source prefixes, resolved role/cap adapters, one grounded correction/focused recheck, visible QA exceptions, raw-before-accounting journal and exact-event reconciliation, unknown-dispatch refusal and per-job pause/resume. Final635 tests pass in41.683s, including14 isolated independent recovery/streaming tests. No runtime generation. Font agent implemented five local licensed typeface pairs, editable originals/public hashes/notices and reproducible conversion; eight tests plus existing exports passed, five multi-page PDFs raster-inspected using PDFium. Local rerender API preserves targets and uses zero model calls. David CLM upstream has no identified document embedding exception; accurate export/catalogue notice retained. Launcher/installer require Python3.10+ and all six pinned imports, preserving brokenoldvenv and using ignored isolatedruntime; PowerShell syntax/import checks pass. Two AUTOMATION-2 Sonnet5 CLI invocations:58turns/789.075s/list$3.2998919 and33turns/505.991s/list$1.5186622, total$4.8185541; actual Pro charge unknown. All four observable automation builder calls list$9.6286177; earlier stdin-blocked wrappers unmetered; internal conductor/subagents usage unknown, Opus0/Astra0/runtime0. Preview expected output35% cap and Hebrew expansion1.35 remain labelled hypotheses; conservative ceiling assumes cache misses/worst write rate and optional QA/correction/recheck. Real provider cache hits and scholarly quality remain unvalidated. UI consumer is next; font backend acceptance does not mark automation_4 UI done.

## 2026-10-05T07:43:56.119153+00:00 | AUTOMATION-2 | pre-push font-byte correction

Implementation f929030 passed635 runtime tests, but a new staged-public-source hash check caught one David Libre OFL CRLF normalization mismatch. The commit was already local when this result was inspected; no push occurred. Scoped byte-preserving attributes and explicit restaging restore the verbatim upstream notice in a follow-up commit, without history rewrite. All staged public font hashes now match the recorded manifests; eight font tests passed again. The accepted push will include both commits, followed by its receipt. Original runtime prompt LF attribute retained.

## 2026-10-05T07:45:14.535768+00:00 | AUTOMATION-2 | verified push receipt

Implementation f9290305378e5a0ec9cf3a876a2bac752419f69c and public font-byte correction f266cb118566606999c4d8aafd8d289a3a6fd3d9 passed635 software tests plus repeated8-font/hash checks. Reviewed full and staged diffs. Normal fast-forward authorized push succeeded; post-push fetch confirms main==origin/main and clean tree. No force/history rewrite; this receipt is separate. Next UI writer starts on the accepted common base.

## 2026-10-05T10:01:40.311484+00:00 | AUTOMATION-3/4 | verified UI integration and browser evidence

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

## 2026-10-06 | LEARN-1A
A scoped Sonnet invocation list estimate1.0036326 USD,443292ms,20 CLI turns; observed Sonnet5 plus auxiliary Haiku4.5, subscription charge unknown. No recursive agents or runtime calls. Frozen APIs and28 unit tests passed after deterministic integration repairs. Bootstrap receipt d1f71e2 (preceded1d73c5e). Git local feature only.

## 2026-10-06 | LEARN-1B
B Sonnet list1.181225 USD,345309ms,33 CLI turns; models Sonnet5 plus auxiliary Haiku4.5, actual charge unknown.15 import tests and43 total learning checks passed after boundary/language fixes. Total A+B2.1848576 USD; no paid runtime. Commit follows local feature only.

## 2026-10-06T01:58:00+03:00 | LEARN-1C/2
C Sonnet list0.795209 USD,1475103ms,21 turns; Sonnet5/auxiliaryHaiku4.5; actual charge unknown. Initial C fixtures yielded7 errors+1 failure (wrong codepoint offsets); fixed deterministically. Combined service stage contained invalid '@' character, found before any dispatch, fixed to learning-generate-v1.100 tests pass. Total3 invocations list2.9800666 USD, no fix-model calls, no runtime calls. Integration receipts A8228b2d,B9684c4b. D only after this verified backend, max2 USD, shared stop-loss10.

## 2026-10-05T23:04:12.6191027Z | LEARN-2 hardening
Sol deterministic integration fixes only; no additional model invocation. Four Sonnet builders dispatched in total (D running, cap2/shared10); ABC observable total2.9800666 USD. Phase timestamps in prior entries are phase labels; this UTC entry records the checkpoint time. Git closure is local feature; remote push not attempted.


## 2026-10-06T04:30:37.313304+00:00 | LEARN-3 | final integrated run
Four builders completed; D list1.1052398 USD,371038ms,33 turns, Sonnet5/auxiliaryHaiku4.5, actual charge unknown. Observable total4.0853064 USD under shared10 stop-loss; no runtime paid calls or fix-model calls.925 tests/284.829s OK,1 skip;121 learning tests. Synthetic browser acceptance and isolated restart passed. Full-page screenshot viewport artifacts are a tool limitation; visible overview proof saved locally. Main clean at9898011, active translator untouched. Local feature commit pending, feature push not attempted, merge/deploy deferred while book runs. No linguistic acceptance or paid pilot claimed.


## 2026-10-06T04:31:45.974175+00:00 | LEARN-3 | verified local commit receipt
Delivery64cc48231ccb67c97f94a0c6091b4c908b868355 contains exactly12 reviewed UI/documentation/audit paths, staged diff checked and matched working files. Feature worktree was clean after commit.925 tests passed(1 skip),121 learning checks; browser acceptance on synthetic data only. Backend predecessor b411b82. Remote feature push not attempted; no merge/deploy into main, which remains9898011 clean. D input-scope recorder correction appended without replacing original event. No additional model/runtime calls. This receipt commit changes audit only.


## 2026-10-06T05:11:15.744912+00:00 | LEARN-4 | correction, cap stop and final verification
E completed UI; F stopped safely at2 USD cap with219 new forms. Conductor completed248 missing meanings, artifact deferral and beyond500 word, without another external invocation. Interim test1325-char provenance refusal fixed; obsolete click expectation revised; browser CSS specificity fix verified.138 learning tests and942 full tests(1 skip) passed;26 UI retest after CSS fix. Two new Sonnet calls list2.7367588 USD; all6 LEARN calls6.8220652 USD; actual unknown, Sol unmetered, Opus/Astra0, runtime paid0. Preview3 fake calls on own synthetic data only. Main now has concurrent external changes; isolate feature Git closure, no main merge/push/restart.

## 2026-10-06T05:16:39+00:00 | LEARN-4 | verified local commit receipt
Delivery019d14077c7084541711924a3cda7f0272a582a3 contains exactly23 intended reviewed paths. Complete and staged diffs checked; staged bytes matched working files; diff checks passed and feature worktree clean after commit. Acceptance remains942 tests with1 skip,138 learning tests and26 post-CSS UI checks, synthetic browser evidence only. No model calls after verification. Main concurrent changes preserved; remote feature push not attempted, no merge/deploy/restart. This receipt changes audit only.


## 2026-10-06T05:28:44.276993+00:00 | LEARN-5 | PASS optional click meaning
Optional click meaning now separate from text flow and hidden until a deliberate click/Enter/Space; checkbox-off returns context-only text, Escape/close dismiss. Read endpoint optional boolean defaults false; display choice does not alter prepared hashes, source, learner, effort, budget/cache or trigger generation. Aria label names foreign word rather than revealing meaning automatically. HTML escaping and textContent retained.
54 targeted tests passed:14 renderer,26 UI,8 cumulative/service(7.530s),6 HTTP(3.323s); JS syntax and diff checks passed. Full suite deliberately not rerun: changed boundary is reader presentation plus read-only endpoint forwarding, covered by focused tests. Prior LEARN-4 full942 result remains historical, not a fresh result.
Synthetic browser verifies initially hidden meaning, merci->Hebrew gloss after click, Escape, Enter, close, checkbox-off removes focusable gloss occurrences, re-enable works. Screenshot outputs/learning-click-gloss-verified.png uses viewport capture because full-page capture was offset; DOM shows no horizontal overflow. Own preview session1410 on62144 restarted with same isolated demo data, synthetic_calls0; active translator/main never touched.
Explained other4 languages share mechanism but lack implemented teaching catalogs and service selection path. Model-proposed vocabulary direction documented in learn_5 contract: same generation call, bounded grounded proposals, stable IDs and persisted definitions, accepted edits only, book-local recurrence then explicit completion. Runtime proposal/other-language activation not implemented in this small display correction; parser still closed, no false support claim.
Sol direct small fix, no Sonnet/Opus/Astra/external development or paid runtime calls this gate; Sol not_metered. Previous6 builder list estimate6.8220652 USD unchanged, actual unknown. Isolated local reviewed commit/receipt follows; main concurrent edits preserved, feature push not attempted, no merge/deploy.


## 2026-10-06T05:29:33.699090+00:00 | LEARN-5 | verified local commit receipt
Delivery f4e0efc445dabd03b3b18e3bc02c9eb5607f39e9 contains exactly15 intended reviewed paths; staged diff check passed and index matched working files. Feature tree clean after commit.54 scoped tests and synthetic browser PASS; no full rerun or additional model calls. Main active translation/concurrent changes preserved. Push not attempted; no merge/deploy. Receipt changes audit only.


## 2026-10-06T06:11:57.338877+00:00 | LEARN-6 | local integration and scoped verification

LEARN-6-BUILDER/LOCAL/RECOVERY/PROMPT attempts recorded; one failed external CLI
event, rejected escalation not an executed model call. Local help_archive agent
owned archive/help/12 archive tests only, copied and reviewed sequentially.
166 learning tests PASS35.733s. Initial HTTP fixture incorrectly mocked nested
handler closures; replaced by actual route with synthetic key and mocked service,
no provider dispatch.22 library tests initially had blocked default Node shim;
process-local bundled Node path corrected environment,22 PASS4.566s. Two meaningful
follow-up scenarios (corrupt costs and actual grammar receipt) added;9 tests PASS
12.441s. Sent-prompt schema boundary corrected on diff review;53 focused tests
PASS16.655s, JS syntax PASS, no complete translation-suite rerun.
Synthetic preview10 fake calls/paid0; browser selector/yi history, adjustable
options, click meaning, recap/progress/received-grammar files and help verified.
Archive test retains180k+ explanation; no truncation or false full-save claim.
No active checkout/runtime/data/credential change. Local reviewed commit/receipt
follows; feature push/main merge/deploy not attempted. No paid quality pilot.


## 2026-10-06T06:15:43.039844+00:00 | LEARN-6 | final explicit unknown-outcome recovery PASS

Final diff review found shared dispatcher cross-step guard still blocked an
explicit distinct retry after a lost dispatch. Learning-only supported journal
transition now records old unknown outcome as failed with user-choice reason;
original identities/events/held costs preserved. One-use authorization is saved
as consumed before another call; a later loss requires a fresh checkbox choice.
26 focused controls/integration/multilingual/HTTP tests PASS25.662s, including
two losses/no automatic resend/final explicit success/prior holds.169 unique
learning tests and22 library tests covered across scoped runs. No shared
dispatcher/journal/control module change, model invocation or full-suite rerun.
This extends earlier LEARN-6 acceptance; reviewed local Git closure follows.


## 2026-10-06T06:17:33.131705+00:00 | LEARN-6 | verified local commit receipt

Delivery cc1fc6ce0852351b2b5c077dc43e03642628b9b1 contains exactly28 reviewed intended code/test/document/audit
paths. Full and staged changes reviewed, staged diff check passed, index matched
working files, feature tree clean after commit.169 distinct learning tests and22
library tests passed across documented scoped runs; final26 recovery tests PASS.
No full translation suite rerun or additional model calls. Own preview54603 on
62144 restarted after final fix with0 fake calls; help visibly verified again,
prior demo data retained. Active main translator never changed/stopped/restarted.
Branch codex/language-learning; feature remote push not attempted, no main merge
or deploy. Actual linguistic quality unverified. This receipt changes audit only.


## 2026-10-06T09:35:32.491399+00:00 | LEARN-7 | isolated software acceptance; main integration pending
Contract audit/contracts/learn_7.md amended by user for original EPUB preservation,
Yiddish marking and main/installer integration. Deterministic EPUB/HTML export
includes complete frozen source, edits, recaps/examples and optional note links;
read-only, no completion/cursor/model effects. Source archive retained atomically
with hashes. Preservation patches XML text slots across inline tags, retains
assets/CSS/fonts/media/nav/package bytes; exact alignment only. Missing legacy
archive explicitly warns; mismatch/corruption errors offer user text-only option.
Original EPUB version retained; reader note support varies. Protected MathML /
nested overlapping blocks and ambiguous template mapping offer explicit fallback.
Installer verifies bundled UI, all five 500-word seeds and three prompt versions
without calls/state; same dependencies. Completed library handoff can retain a
Hebrew EPUB template. Active translator/root untouched. Own preview54603 replaced
by63982 at62144, restart0 fake/paid calls. Browser verified Yiddish rtl/isolate/
dotted underline, export options and binary-response success status; IAB download
event timed out, so browser saved-file completion not claimed. Screenshot
outputs/learning7-yiddish-export.png. HTTP binary length/content validated.
Acceptance across scoped runs:103 unique affected export/preservation/assets/
service/HTTP/render/UI/integration/installer tests plus22 library tests PASS.
Final new service cases5 PASS8.473s; library22 PASS4.318s using bundled Node path
(default Windows node shim denied), actual JS syntax and diff checks PASS.
Initial provisional/runtime plan-ID mismatch fixed with read-only accepted ID
view; negative test expected mapping error corrected to stronger hash rejection.
Sol owns integration; export_builder10 preservation tests, installer_integration
read-only advice; local usage not_metered, no external model calls, Opus/Astra0.
No full-suite rerun or paid linguistic pilot. Reviewed feature Git closure next;
clean main-integration worktree nowda6beb2 preserves newer math/OCR/unblock code.
Concurrent main review-effect edits remain untouched; no live restart/deploy.


## 2026-10-06T09:46:44.954122+00:00 | LEARN-7 | feature receipt and verified main integration
Feature delivery1e21a742fa9b7bf0bd4baf99ee724d76935dbfd3:23 intended paths,
full/staged changes reviewed, index matches worktree, staged check PASS, clean
feature tree. Feature push not attempted; this is its subsequent receipt.
Merged in isolated codex/learning-main-integration from main da6beb2, preserving
367d07f math,05748c8 OCR andda6beb2 unblock plus library delete/in-progress/partial
exports/decision controls. UI and handler conflicts resolved additively; learning
handoff only completed library. No live root/server/job/credential changes.
108 affected merged tests PASS across scoped runs: initial105 in42.926s had one
Windows sharing failure in service replace; unique staging+bounded PermissionError
retry fixes it.27 service/assets/HTTP/integration PASS23.302s incl deterministic
transient/persistent locks; prior JSON retained and staged full JSON on final
failure with visible learning_save_failed.12 preserved EPUB tests PASS0.087s incl
new main MathML immutable logical slots, unchanged formula DOM around edits and
explicit refusal of edits across formula. Other104 initial tests passed; no full
suite repeated. JS syntax and working/staged diff checks PASS.
Browser merged main shell/library shows learning link and both library tabs,
Yiddish rtl/isolate/dotted underline and export options. Screenshot
outputs/learning7-main-library.png plus conductor/outputs/learning7-yiddish-export.png.
Own preview86550 at62144 replaced own63982 only; same synthetic root,0 fake/paid
new calls. IAB blob download event unavailable; verified successful byte-response
status and HTTP content/length, no saved browser-file claim. Local export_builder
and read-only installer_integration only, not_metered; external model0, critic0,
Opus/Astra0. Installer checks assets/prompts/five seeds, no extra dependencies.
Remote main observed05748c82448c62dc3257a22da7485e4bd094535c at this checkpoint;
ancestor of integration. Root main has active concurrent review-effect changes,
not owned/staged here. Reviewed clean integration commit follows; main checkout
fast-forward and push require stable checked status, never forced/divergence.


## 2026-10-06T09:51:05.465352+00:00 | LEARN-7 | clean integration receipt; user-directed wait
Verified integration e70449bd8a2635ea06f39f942c71db412de83c2c, parents da6beb2 and
1e21a74.65 intended merge paths reviewed; complete/staged changes checked,
index matches files, clean integration tree after commit.108 scoped integration
tests covered across runs; no provider/full-suite call. Feature remains clean.
User confirms concurrent main work is still running and explicitly instructs
waiting until it ends. Main has overlapping UI/handler and review-effect edits;
no main checkout fast-forward/push/restart attempted. Remote main previously
observed05748c8, ancestor; publication pending. Preserve both histories and owner
changes; recheck updated main and resolve additively after a clean completed
main checkpoint. Own merged preview86550 only, paid0.

## 2026-10-06T11:40+03:00 | UNBLOCK + REVIEW-EFFECT | Claude continuity, user-directed

User asked what the Jade City run (c69bb5fc) showed and why it stopped again. Audit
of 51 chapters: chapter-48 answer complete but missing the final `]`; resend replayed
the cached answer; most review/QA output discarded by over-strict span grounding;
proper-name findings made every unit risky; notebook excerpt starved late chapters.
User decisions: QA auto-corrects consistency/continuity only; `checked` reviews all
units except short headings; salvage chapters 1-51; improve keeper/reviewer/QA prompts.
UNBLOCK da6beb2 and REVIEW-EFFECT committed under audit/contracts/review_effect.md.
861 offline tests OK; offline replays on job copies (no provider calls) confirm
chapter 48 validates from the saved answer and salvage reopens 51 chapters with ~112
corrections queued. Paid/model calls: 0. Next: user rechecks and resumes in the UI.


## 2026-10-06T10:54:49.702372+00:00 | LEARN-7 | completed-owner compatibility integration PASS
User confirms parallel main work finished, authorizes careful integration.
Root main and remote verified34b0b6cbfb6640e7ad907d85a9bc8b84cb8c851f, clean.
Merge latest main into isolated verified integration; shared UI/web auto-merge
preserves learning/library-delete/in-progress/recheck controls. Only audit state
and history conflicted; retain both append-only histories, refreshed checkpoint.
Incoming main code/prompts/tests outside three additive shared UI/web files match
main byte-for-byte. REVIEW-EFFECT/FORMAT-TOLERANCE remain intact.
68 targeted tests PASS46.759s: learning integration/HTTP/export service, library
UI/HTML, UI automation, web, saved-review salvage, job-block HTTP. Actual bundled
Node syntax checks PASS for ui.js/learning.js; diff check PASS. No full-suite run,
paid/provider/critic/Astra calls0, Sol local usage not_metered. No live restart,
job mutation or source-data migration. Main c69bb5fc stopped52/64 untouched.
Reviewed merge closure then verified fast-forward main/push authorized; no force.


## 2026-10-06T10:57:06.492146+00:00 | LEARN-7 | verified main delivery receipt PASS
Merge140a946f4cdd96ba0df0397508b6d6097fdbf0e2 reviewed/staged check PASS,
index matched files; isolated integration clean. Root main clean/unchanged34b0b6c
before fast-forward, ff-only advanced to140a946. Verified intended origin URL
https://github.com/neria-baris/scholarly-translation.git; remote34b0b6c ancestor;
normal push succeeded and ls-remote confirms exact140a946. Main clean after push.
68 focused compatibility tests PASS46.759s and two JS checks; no full-suite rerun
or provider calls. Complete learning/installer/export integrated with newer main
review-effect and format-tolerance code retained. No live restart/job modification.
This receipt records delivery hash (not its own hash). No cleanup of other work.
Limitations remain: linguistic quality and IAB saved-file event not verified.
Next: user can load updated UI at a safe future restart after active translation.


## 2026-10-06T17:55+03:00 | NAMES-CROSSQA | Claude continuity, user-directed
User asked for an analysis of code problems revealed by the completed Jade City run c69bb5fc,
then decided: name table built by the model before chapter 1 and locked automatically, binding
NAMES in every prompt, larger notebook, keeper fixes (entry_id, whole story, tolerant JSON,
warnings, retry reopen, stale notes), cross-chapter QA every 8 chapters with one chapter of
overlap (the overlap chapter decides), automatic corrections; no deterministic name/term
checks, no sealed names, niqqud allowed, Luna default. User explicitly authorized more than two
parallel builders: five Sonnet builders (A notebook, B name table, C cross QA module, D retry,
E UI action) on disjoint files, common base b23a217/f61958c, sequential conductor integration
of chapter_pipeline.py and tests. Integration fixes: output caps bounded by the shared cap,
32-round keeper trim, unit names budget 1000, result-view entry point for completed books.
Tests: full offline suite 1137 OK, rerun after the final UI entry point 1137 OK (388s);
new test modules name_table 24, cross_chapter_qa 17, cross_review_action
6, names_crossqa_integration 8; node --check OK. Offline replay: the 3 lost keeper answers of
c69bb5fc (chapters 31, 42, 59) now parse fully. Paid/provider calls 0; no live restart; jobs
untouched (Senlin Ascension paused 1/50 under old code: restart UI before resuming).


## 2026-10-06T18:40+03:00 | NAMES-CROSSQA SOURCE-PASS | Claude continuity, user-directed
User reported that the pre-translation step did not read the original book and that the
finished Jade City translation had no way to run the check again. Verified: name table came from
capitalized candidates + one snippet; UI copy said "reads the translation"; entry point hidden in
the collapsed notebook section; completed checks could not rerun; running UI processes started
before delivery 0885287. Contract addendum 2 (36c4eb3). Builders B2 (name_table source-pass
prompt) and E2 (visible rerun entry, copy) in parallel; conductor integrated the chunked
pre-pass and rerun in chapter_pipeline.py. Offline dry run on c69bb5fc data: available, 4 source
chunks, <= 1.14M upper-bound input tokens, 9 windows. Full offline suite 1143 OK (447s); mocks in
four modules now answer or exclude the name-table call. Paid/provider calls 0; no restart.


## 2026-10-06T19:30+03:00 | SCHOLARLY-PARITY | Claude continuity, user-directed
User asked whether the narrative context edits were adapted for academic books. Verified: the
notebook, name table and cross-chapter windows run for scholarly jobs, but prompts 09/10 were
fiction-only, the keeper applied running-jokes/character-address rules to every book, 04/06
described the notebook in literary terms and the scholarly style profile never mentioned
BOOK_NOTEBOOK. Fixed in prompts/copy (contract scholarly_parity.md); new ScholarlyParityTests;
stale assertion (scholarly profile without BOOK_NOTEBOOK) revised; planner fixture qa_context
12000 -> 13000. Full offline suite 1151 OK (449s). Paid/provider calls 0; no restart.
Addendum: article wording and bibliography exclusion in the scholarly guidance; planner fixture
qa_context 15000 (edge-sensitive). Full offline suite 1151: only that fixture failed before the
retune; test_long_docs_planner 24 OK after. Paid/provider calls 0.


## 2026-10-06T23:45+03:00 | EXPORT-NIQQUD | Claude continuity, user-directed
User asked what was learned from the finished Senlin Ascends job dccf6947 (50/50, 533 Luna calls,
$1.14 of $10, plan $1.135, ceiling $7.57). Offline findings: (1) EPUB export left 2333 of 2436
blocks in English (whole-chapter units, translation only in the first block); (2) 127/145 name
forms vocalized (prompt 09 encouraged niqqud), cross-chapter QA "corrected" prose to them: 5318
niqqud marks in 90/103 units; (3) all 50 chapter QA REVISE, 400 notes retained (160 MAJOR
hebrew_quality). User decided: fix 1 and 2; niqqud only in hard cases such as Wen/Woon.
Contract export_niqqud.md, branch fix/export-niqqud (worktree; main had a concurrent session's
PUNCT-RHYTHM change, now f87addb, no shared files; rebased on it). Delivered: line-per-block
spread with proportional fallback; plain NAMES forms unless colliding (vav-doubling aware);
prompts 07/09 unvocalized; cross QA drops niqqud-only additions. Two stale integration
expectations (vocalized NAMES line) revised. Offline export of the Senlin data: Hebrew in every
block, 1 realigned unit, 114 Latin words left (CSS/cover), inline italics/bold flattened as
before (known limitation). Full offline suite 1164 OK after the revision. Paid/provider calls 0;
no restart; job data untouched. Open: register guidance in the name-table pass (user: "to be
considered"); niqqud already inside finished Senlin/Jade City text is not removed.


## 2026-10-07T00:30+03:00 | BOOK-VOICE | Claude continuity, user-directed
User proposal after Senlin (title "Senlin Ascends" -> "סנלין עולה", QA disputing its sense): the
name-table pass should grasp the book's register and set it from the start. User approved the
recommendation: no approval pause, visible in the notebook, keeper may refine. Contract
book_voice.md, branch feat/book-voice. The first source-pass chunk now also asks for a "voice"
field (register in Hebrew, <=20 key words incl. title words, with source forms and plain Hebrew);
parse_voice is tolerant and bounded; add_voice_entries adds one global `voice` entry and one global
`key-word` entry per word (keeper add semantics, not pinned). Other chunks and names parsing
unchanged; a broken voice changes nothing else. No new calls or steps. 11 new tests; full
offline suite 1175 OK (543s). Paid/provider calls 0; no restart.


## 2026-10-07T09:00+03:00 | ARTICLE-NOTES | Claude continuity, user-directed
User asked whether articles get the scholarly context work, then for finer handling of footnotes
and reassembly as in the original, with mathematics. Evidence: `1 See ...` footnotes classified as
paragraphs, marks plain digits, running headers repeated, references forced into Hebrew, notes
inline in the PDF. Decisions: page-bottom notes, references in the original, digital/scanned PDF.
Contract article_notes.md, branch feat/article-notes (worktree), rebased on 19a0a88. New
article_layout.py (geometry analysis, note index, marks, repair, footnotes); document_structure
applies overrides; chapter_pipeline passthrough records/plans and marked prompts; export_pdf
footnote layout; export_html linked notes; superscript digit runs keep order in RTL lines; help
section. Older tests: limitation renamed note_without_mark, HTML block parser accepts dir="ltr".
17 new tests incl. an end-to-end job and page placement read back with pdfplumber. Full offline
suite 1192 OK (483s). Paid/provider calls 0; no restart.



## 2026-10-07T12:00+03:00 | LEARN-GRAMMAR | Claude continuity, user-directed
User asked for study paragraphs on grammar after each chapter of the learning edition (gender,
inflection, active/passive) with chapter examples, then for a consolidated view of all lessons and
words, and real dictionary entries with inflections. Decisions: one extra Luna call per chapter;
woven insertions + full chapter sentences in the target language; new preparations only; entries
inside the existing chunk call for every word when first woven; no backfill. Contract
learning_grammar_lesson.md, branch feat/grammar-lesson (worktree). New learning_lesson.py and
learning_dictionary.py, prompts 11/12; service lesson step (max_calls = chunks + chapters for new
jobs only), DICTIONARY_NEEDED per chunk, progress entries/examples, grammar_notebook route; reader,
export, archive and help updated. Verified that every output holds one woven chapter followed by
its lesson. Fake test adapters answer lesson prompts; call-count expectations updated. 19 new
tests; full offline suite 1212 OK (499s). Paid/provider calls 0; no restart.


## 2026-10-07T12:30+03:00 | PREVIEW-SPEED | Claude continuity, user-directed
User: no cost estimate is shown and a new translation cannot start. Evidence (py-spy on the live
server): one /document-preview request in tiktoken encode for >10 minutes; solid placeholder runs
are quadratic for BPE (66k 'x' 1.7 s, 66k 'א' 6.4 s per count). Earlier in-shell reproductions
were fast only because that interpreter lacks tiktoken. Branch fix/preview-tokenizer-filler:
`_filler` (byte-identical, whitespace every 64 chars) for notebook/bridge reserve, synthetic
targets and correction issue; `upper_bound_tokens` + `_ub`/`_prompt_ub` for fit checks. Jade City
(64 chapters) preview with tiktoken 16 s. 3 new tests; reference planner shares `_filler`. Full
offline suite 1195 OK (447s); planner/preview/automation suites 101 OK under the tiktoken runtime.
Not related to the under-$1 decision change. Paid/provider calls 0; UI restart needed by the user.

## 2026-10-07T10:00+03:00 | AUTO-CONTINUE-WRITABLE | Claude continuity, user-directed
User: again asked to approve a $0.0084 unknown-outcome retry despite the under-$1 rule. Evidence:
Jade City controls events 309/310 (local-correction, failed_transport, stopped_not_metered) then
311 user_settled decided_by user 7 minutes later; servers started 08:13 with the rule's code.
Cause: `_auto_continue` used ControlStore(create=False) = read-only; the settle write raised
StoreCorruptionError, swallowed by its except. Fix: create=True (as in `decide`). Regression test
through DocumentJobs (fails before, passes after). Full offline suite 1216 OK (481s). Paid/provider
calls 0. UI restart needed; not pushed.

## 2026-10-07T11:40+03:00 | UI-POLISH | Claude continuity, user-directed
User: (a) messages after a finished translation are unclear and fill the screen; (b) the page needs
scrolling to reach help, also in the translation view; (c) the progress info under the translation
view is unclear with an RTL problem; (d) an English interface button. Contract
`audit/contracts/ui_polish.md`. Evidence: Jade City c69bb5fc has 3097 English export_limitations
that renderResult joined into one paragraph (result page 49,655 px tall at 1366 wide).
Builders (Claude Sonnet, user allowed >2 parallel): UI-STATUS (a+c), UI-FIT (b), HELP-EN in three
worktrees off a7a4f82 (first launch landed on origin/main and stopped cleanly; relaunched on
explicit worktrees), then UI-EN sequentially on the merged base; conductor merged, one small direct
CSS fix (result heading). Result: one short status line + one collapsed details box (limitations
grouped by kind with Hebrew labels and counts, first 3 notes + "ועוד N", findings count, usage);
labelled progress rows + per-model table with <bdi dir=ltr> numbers, secondary counters collapsed;
start page 754->606 px, help link in the header; result page 49,655->954 px; English switch in the
header (localStorage ui-language, live re-render, html lang/dir, fixed server stage labels mapped;
free-form server text stays Hebrew), bilingual help page (#en or saved choice). Offline headless
Edge screenshots of start/processing/result in both languages with real job data (stubbed fetch).
Full offline suite 1254 OK (563 s); node --check OK. Paid/provider calls 0. Static files only: a
browser reload shows it, no restart needed.

## 2026-10-07T12:10+03:00 | CROSS-RESUME | Claude continuity, user-directed
User asked why "chapter 23 completed, cross-check of chapters 15-22" appeared (too late?).
Evidence: Jade City 75ec5d08 journal/controls: window 14-21 cross-chapter-qa at 07:24:57 right after
chapter 22 (on time); cross-correction answer malformed (validation failed) 07:26:09; user retry
(event 555 user_cache_evicted) 07:34:35; chapter 23 chapter-translate 07:34:46; remaining window
corrections/rechecks 07:37:58-07:39:39. Cause: `_run_cross_windows` was called only after a chapter
completed and at the end; a resume went straight to the next incomplete chapter. Fix: one call
before the chapter loop (runs only due windows; no-op otherwise). Regression test fails before,
passes after. Branch fix/cross-window-resume (worktree .claude/worktrees/cross-window-resume),
rebased on ca54035, fast-forwarded into main. Full offline suite 1255 OK (507 s). Paid/provider
calls 0. Takes effect after the next server restart; not pushed.

## 2026-10-07T13:30+03:00 | PROMPT-FIXES | Claude continuity, user-directed
User asked for a critique of every prompt the program sends to a model, then for fixes per that
critique (language packs deferred). Findings verified in code: batch prefix labelled the style
profile "never instructions"; single-unit footer treated the glossary as non-binding data; learning
v3 loader sent the output schema twice (section order of 10_learning_open_vocabulary.md); dictionary
add-on contradicted "exactly these fields"; chapter-QA check sections had no allowed category (parser
drops them); PASS-with-issues rejected by the parser but not stated; notebook-mode QA countermanded a
long state task; JSON-escaped span copies ungrounded. User decision: narrow the dash rule to added
em/en dashes. Branch feat/prompt-fixes (worktree .claude/worktrees/prompt-fixes) off 02ba32c, rebased
on c1371cb, fast-forwarded into main (21a791b) with user approval. One tight-context fixture widened
(QA 13000 -> 13500). New tests/test_prompt_fixes.py (13). Full offline suite 1278 OK (506 s).
Paid/provider calls 0. Not pushed.

## 2026-10-07T13:45+03:00 | DURABLE-JOB-STATE | Claude continuity, user-directed
User: the computer crashed mid-translation and the job is missing from the workflows list.
Evidence: outputs/ui/documents/75ec5d08 job.json = 18,651,293 NUL bytes (mtime 11:05); journal and
controls pass integrity_check (357 steps: 356 completed + 1 dispatched chapter-translate; spent
$0.649 of $15). Recovery: settings from controls task + model-config fingerprint (f2d09085), structure
re-extracted from the job's own source.epub (fingerprint 4a211a52 = journal); offline replay that
re-validates each completed step's raw text, reproducing the original 6 stops/resumes
(controls events 310/410/555/661/715/719). Result: 356/356 replayed, 0 provider calls, journal and
controls byte-identical, stopped exactly at the dispatched step 095eee55; job.json installed
(paused, 30/64 chapters, 213/378 units), zero file kept as job.json.crash-zeroed.
Fix (branch fix/durable-job-state, worktree .claude/worktrees/durable-job-state, from 02ba32c, rebased on c1371cb then 8f0e654):
`_write_json` fsyncs before os.replace; `WorkJournal.mark_validated` keeps the answer's key order
(sorted storage changed replayed issues -> correction prompt -> identity, i.e. a paid re-call).
Existing journals keep their sorted rows. New tests
test_document_draft::JobFileDurabilityTests and
test_work_journal::test_validated_result_replays_in_its_original_key_order fail before, pass after.
Full offline suite 1257 OK (506 s); after rebase on REMEMBER-KEYS c1371cb 1267 OK (509 s); after rebase on PROMPT-FIXES 8f0e654 1280 OK (492 s). Recovered job resume checked offline under this code: first call is chapter 31 chapter-translate (after the unknown-outcome retry decision), no earlier step repeated. Paid/provider calls 0. Not pushed.

## 2026-10-07 — NAMES-CJK (Claude continuity, user-directed check, no contract)
User asked whether the name table shown for an article run is real and relevant and whether its text
fits an academic article. Evidence (offline): article job 18da9456 (ja, scholarly, 1 part): name-table
step completed, 107 entries (30 person, 11 work, 4 organization, 62 term), relevant to the article.
Its chapter context carried only 60 of the 104 entries present: `_occurs` used (?<!\w)/(?!\w), and
in Japanese a particle or the next word follows the name (ヒルベルトの), so Hilbert, Kant,
Brouwer, Tarski, formalism, phenomenology, intentionality and others were dropped; unit-review
blocks 131 of 418 matches. Fix 44a3e4c on main: CJK forms match as substrings, a CJK neighbour never
blocks a Latin form (same idea as book_notebook._compile_terms). Article now 104/107 per part,
418 per unit; Jade City 75ec5d08 has no CJK in entries or text, so its matching is unchanged.
Also: `name_table.render_markdown` and the notebook download include the table; stage label
"בניית טבלת השמות והמונחים", skipped note without "chapter by chapter", help (he/en) describes
articles. New tests test_name_table::RenderTests::test_text_filter_cjk / test_markdown fail before,
pass after; the download test checks the table. Full offline suite 1282 OK. Paid/provider calls 0.
Not pushed. The running 18da9456 translation call (dispatched 12:50, before the fix) was not touched.

## 2026-10-07T16:05+03:00 | SERVER-TEXT-EN (UI-POLISH addendum) | Claude continuity, user-directed
User: "continue" with the offered follow-up — server-written Hebrew messages in English mode. Client
side only (contract addendum in ui_polish.md): SERVER_EN in ui.js, 164 Hebrew templates -> English
(one per line), serverText() exact/{n}-pattern match with recursive captures, applied to blocker
messages/options, job errors, review notes, HTTP errors, stage labels. Templates extracted with ast
(162 after documented exclusions); two Sonnet translators in parallel + one Sonnet builder; conductor
inserted the table and fixed one term (register). Guard: tests/test_server_text_en.py fails on an
untranslated or dead template; after merging NAMES-CJK it caught the two renamed name-table texts
(added; the old texts kept as LEGACY for older job.json, at session 51's request). Checked: real
Jade City notes render in English; a $0.0084 unknown-outcome blocker and its button translate. Full
offline suite 1286 OK (1 skipped). Paid/provider calls 0. Static file only: browser reload, no restart.
Coordination: main 1b20743 (other sessions' commits) pushed first with session 51's agreement.

## 2026-10-07T15:40+03:00 | AUTO-RETRY-UNDER-DOLLAR | Claude continuity, user-directed
User: asked again (academic PDF). Evidence in 18da9456 controls: events 45-60, semantic_reviewer-pass
gpt-6.1-sol held $0.1876, failed_transport latencies 1.75 s ... 0.03 s, three auto decisions then a
manual one; journal shows the identical prompt completed afterwards. Cause: fixed 3-in-a-row limit
plus immediate resends inside a short outage. Fix: dollar row limit, backoff as paused, adapter
resend for never-opened connections, exception classes in errors. Paid/provider calls 0.

## 2026-10-07T18:00+03:00 | TARGET-LANGUAGES | Claude continuity, user-directed
User asked for target-language packs and deterministic output checks (proposed in the prompt
review), then a UI choice (Hebrew or English for now). Contract audit/contracts/target_languages.md.
Method: snapshot of every prompt of a full mock run (names, translate, review, QA, keeper, cross QA,
correction) + direct renders before the change; after tokenizing, the Hebrew snapshot matched byte
for byte (ids normalized) except REVIEW_FOCUS lines added by the new findings. English renders carry
no Hebrew rule/letter. Planner placeholders use a target-script letter (Hebrew unchanged).
Branch feat/target-languages (worktree .claude/worktrees/target-languages) off 8f0e654, rebased
three times over concurrent main work (NAMES-CJK, SERVER-TEXT-EN, REMEMBER-KEYS; ui.js EN table
conflicts resolved by re-applying the two key edits), fast-forwarded into main with user approval.
New tests/test_target_languages.py (24, incl. a full French->English mock EPUB run). Full offline
suite 1316 OK (529 s). Paid/provider calls 0. Not pushed.

## 2026-10-07T19:30+03:00 | REASONING-CHOICE | Claude continuity, user-directed
User: the models run at low reasoning and there is no way to choose the level. Evidence: no caller
passed a level, so the OpenAI adapter always sent the catalogue default (gpt-6-luna `none`,
gpt-6.1-sol `low`); Anthropic models have no level in the catalogue. Contract
audit/contracts/reasoning_choice.md. Delivered: optional `reasoning` on ModelCapabilities (serialized
only when set: existing configs, fingerprints and step/cache identities unchanged), catalogue
selection validation against the model's levels, the level passed at every adapter build site
(per-job web factory, chapter pipeline, review controls, unit translation/review, semantic
critic/corrector), builder refuses a level for a non-OpenAI provider, UI select per role ("default
(<level>)" + levels; reset on model change; mirrored to QA; Hebrew/English). Defaults unchanged.
Branch feat/reasoning-choice (worktree .claude/worktrees/reasoning-choice) off 6f70896. New
tests/test_reasoning_choice.py (10; 6 fail on the old code). Headless Chrome: Luna/Sol options,
selection payload, QA mirror, hidden for Sonnet, English labels. Full offline suite 1326 OK
(1 skipped; one Hebrew-literal lint fixed and its file rerun). Paid/provider calls 0. Not pushed.


## 2026-10-07T16:08:21.329Z | REASONING-CAPS | post-G12 user-directed bug fix, Sol conductor
User requires review allowance to match reasoning effort; no effort downgrade. Contract audit/contracts/reasoning_caps.md, base ad35a80898c4059de2eaa8bde945369c848c3b24. Evidence: most recent saved high-effort review stopped at output=reasoning=2304, text=null; repeated same-cap failures. No source text retained in this record.
Delivered shared local experimental headroom none/low/medium/high/xhigh/max = 0/8192/16384/32768/49152/65536, additive to visible-answer bounds. Unit review, chapter QA, focused recheck, cross QA, context checks, planner/preview, pending reservations and provider payload share it. Model output limits fail explicitly rather than discard answer space. Unset effort uses existing catalogue default; Luna none is unchanged. Saved high-effort jobs refresh stale planning estimates on resume while preserving units, groups, contexts, charges and journal. No live server restart/job mutation/provider dispatch.
Verification: 8 new regression tests; 67 focused tests PASS 1.964s. Restoring old review-cap function in-memory makes the cap and actual-payload regressions fail (2 expected failures). Full offline suite via working command runner: 1334 tests PASS 539.952s; diff check PASS. Two node-based full-run attempts stopped at different existing mock-job tests (167/181 completed), isolated case PASS; exact harness stall cause unverified. Direct runner passed both and the entire suite.
Builder: installed/authenticated Claude CLI 2.1.292, Sonnet initialization claude-sonnet-5-5 observed. Restricted snapshot attempt could not connect; no edits or completed generation. Automatic approval review rejected the network launch for repository source export to Anthropic. Local focused Sol fix follows DEVELOPMENT_WORKFLOW direct-small-fix permission. Sonnet 1 attempted invocation, Opus/Astra 0; runtime provider calls 0; costs/tokens not_metered/unknown. REASONING-CAPS-C1 duration_seconds included conductor work after interruption; actual invocation duration is not_metered (superseding that duration). No reattempt or bypass.
Git: intended origin verified; fetch main succeeds, origin/main ancestor of base (9 previously accepted commits pending sync); preexisting Windows-generated %SystemDrive%/ProgramData/Microsoft/Windows/Caches classified by exact names, excluded locally via .git/info/exclude (no deletion or commit). Only task-owned paths intended. Reviewed commit and verified push receipt follow.
Limitations: headroom is a planning hypothesis, not a guarantee against truncation or real translation-quality evidence; runtime restart needed; original monetary budget unchanged, larger reservations may require explicit user budget renewal. Learning/translation/keeper/prepass caps unchanged.


## 2026-10-07T16:10:31.553Z | REASONING-CAPS | verified delivery receipt PASS
Delivery commit 35b33b144b4a0a7b6b86c7aada3419d9f3c99db2: 10 intended paths, complete/staged diff reviewed, staged check PASS, index matched worktree, clean main after commit. Full offline suite 1334 PASS 539.952s; 67 focused PASS. Exact origin URL, main branch, accessible remote and ancestry checked; ordinary push 459484b -> 35b33b1 succeeded; ls-remote equals exact delivery hash, tree clean. Prior accepted main commits synchronized too. No live restart/provider dispatch. This receipt records delivery hash, not its own hash. Next: UI server restart, user resumes saved high-effort job under unchanged dollar budget; experimental reasoning allowances remain uncalibrated.

## 2026-10-09 | ROLE-UPDATE | user-directed policy change, Claude Code primary agent
User redefined the conductor role: the conductor is the primary agent the user is talking to directly in the current session, independent of vendor/model (Claude Code, Codex/Sol or another); no continuity handoff required. Updated CLAUDE.md, AGENTS.md, DEVELOPMENT_WORKFLOW.md (dated role update + ownership wording), policy v1.4 header/§16, and central prompt conductor section. Delegation limits, Astra escalation, budgets, Git authorizations and runtime strategy unchanged. Historical audit records naming Sol are preserved as written. Unrelated pre-existing working-tree changes (learning/runtime code and tests) were not touched or staged. No model or provider calls.

## 2026-10-09 | ROLE-UPDATE-2 | user-directed policy change, Claude Code primary agent
User authorized escalation to Fable (Claude Fable, normally claude-fable-5-1) in addition to Astra, under the same written triggers, case format, read-only adviser role and per-issue/per-gate/cumulative quotas (counted across both advisers). The fixed limit of two parallel builders is removed; checked contracts, separate ownership/worktrees, common base, independent tests and one-by-one integration still apply. Updated CLAUDE.md, AGENTS.md, DEVELOPMENT_WORKFLOW.md, policy §§1/5/7/9/15 and the central prompt. Pre-existing unrelated working-tree changes not staged. No model or provider calls.

## 2026-10-09 | SYNC-VERIFY | pre-push verification of unsynchronized main, Claude Code primary agent
origin/main fb368d6 is an ancestor of local main c2b6914; 10 commits unsynchronized (CJK-STRUCTURE, USER-TERMS, AUTO-RETRY-KNOWN-COST, PDF-TYPOGRAPHY, INDENTED-QUOTES with their merges, ROLE-UPDATE, ROLE-UPDATE-2). Earlier feature commits had contracts but no recorded verification. Full offline suite on a clean detached worktree of c2b6914 (excluding uncommitted working-tree changes): 1380 tests OK (skipped=1), 505.270s, exit 0. User approved verify-then-push. Uncommitted learning/runtime working-tree changes remain unstaged and unverified. No model or provider calls.

## 2026-10-09T05:54:42Z | LEARN-SALVAGE | learning answers salvaged, book notebook, Claude Code primary agent
User report: learning preparation repeatedly showed "ניסיון 4 מתוך 10". Read-only analysis of 26 recorded learning calls: 12 rejected, none from transport/truncation/malformed JSON; 10 for miscounted character offsets (every quoted original present in its unit; 47% of 38 returned edits miscounted), 1 foreign_share (5-word contents passage), 1 invalid_id (local-más). All-or-nothing validation and 15/60/120/300 s waits caused the stalls. User additionally directed: max_foreign_share applies to the whole book, known words free, a notebook of what was learned, no rigid/expensive counting. Contract audit/contracts/learn_salvage.md. Branch fix/learn-salvage: base commit snapshots the pre-existing unverified uncommitted learning/runtime working-tree changes (they contain the learning auto-retry); fix commit on top. Policy@3: span located by original text (nearest free whole-word occurrence), repeated Hebrew context trimmed, invalid parts dropped, quotas trim; book notebook (local word totals, paced allowance share x min(book, max(read, 200)) minus used, learned items ranked, max 150) as learning-generation@4 prompt asset 13; rejected answers resent after 2/5/15/30 s. Policy@1/@2 unchanged. Offline replay of recorded rejected answers: 11/13 now accepted; remaining 2 are genuine content errors (sentence-level replacement, insertion). Learning tests 250 PASS; full offline suite 1409 PASS (skipped=1) 476.1 s. Runtime provider calls 0; conductor usage unknown. Main checkout untouched; integration into main pending user decision on the pre-existing uncommitted changes.

## 2026-10-09T13:02:30Z | LEARN-SALVAGE | integration receipt PASS
User chose to keep both in main. Main checkout's uncommitted changes verified byte-identical to snapshot 000e49c (child of 4e3979e, tree equal to the working tree, index clean); main advanced by mixed reset to 000e49c (no file touched, status clean), then fast-forward to c5d6f88. Full offline suite on main: 1409 PASS (skipped=1), 553.8 s. Not pushed (awaiting user). UI server (web_ui, started 15:49) still runs the previous code until restarted by the user. Runtime provider calls 0. This receipt records c5d6f88, not its own hash.
