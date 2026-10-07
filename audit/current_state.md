# Current state — REASONING-CAPS software accepted, Git receipt pending
Updated: 2026-10-07T16:08:21.329Z. Sol conductor, user-directed focused bug fix after Gate 12.

Latest known main before this change: ad35a80898c4059de2eaa8bde945369c848c3b24 (REASONING-CHOICE). Contract: audit/contracts/reasoning_caps.md.

Review caps now add experimental reasoning headroom to the existing answer allowance: none 0, low 8192, medium 16384, high 32768, xhigh 49152, max 65536. Existing catalogue defaults apply. Unit/chapter/focused recheck/cross QA use the same total in capacity checks, preview, reservations and dispatch; selected effort is preserved. Saved high-effort jobs refresh stale estimates on resume, preserving completed units, groups, contexts, charges and journal.

Verification: 8 new tests; 67 focused PASS; full offline 1334 PASS in 539.952s, diff check PASS. No runtime provider call or live server/job mutation. Sonnet CLI snapshot attempt had connection failures; network launch rejected by automatic approval review for source export. Sol performed the permitted small direct fix; Opus/Astra 0. Development billing unknown; no further model calls planned.

Open: restart UI server to load fix; then user can resume the saved high-effort job. Original dollar budget stays fixed; larger review reservations may require explicit budget renewal. Headroom is a local initial assumption, not a provider maximum or proof of output quality. Translation/keeper/name-prepass/learning caps remain existing behavior. Gate-10 real-source/human quality acceptance stays pending. Earlier target-language, durability, remembered-key and retry changes remain in main; historical details preserved in audit/run_history.md. LEARN-EN-BASE contract at 6f70896 is separate work, not implemented here.

Git: intended origin/main fetched and is an ancestor of base; 9 prior accepted main commits were awaiting sync. Preexisting Windows cache excluded locally, no deletion. Next: reviewed explicit-path staging, clean commit, verified ordinary push, separate audit receipt.
