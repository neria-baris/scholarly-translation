# Current state
Updated: 2026-10-04T17:35:56.2045346Z

Gate 12 versioned translation profiles pass offline software acceptance and are committed on `agents/run-it-de649c23` as 64f7ca6f77677add0c6943d25eba871f4be5cf83. Contract: `audit/contracts/gate_12.md`. Changes add closed `scholarly`/`literary` prompts, explicit layered context inputs, profile/prompt/config/context cache and provenance identity, public literary CLI selection, and nullable `translation_note` while retaining additive schema-1 `translation-draft@1` and `approved=false`.

Evidence: final focused 57 tests passed in 1.130s; full 375 tests passed in 30.922s with one unrelated existing skip. Unknown profiles and malformed/oversized supplied context fail closed. No paid runtime translation call or real quality claim. G12-C1 was one Claude Code invocation using Sonnet plus auxiliary Haiku, 631.031s and $1.3716102 reported list estimate; actual charge unknown. Sol made one bounded correction after diff review; no second model call. The contract's one-turn wording mapped to one external invocation, while Claude reported 48 internal turns; preserved as a process-accounting deviation.

Git: eleven exact paths reviewed and committed; tree was clean before this short receipt. This isolated worktree branch has no configured upstream and was not pushed; `origin/main` remains the known base at 36fbbf0. Receipt's own hash is intentionally not embedded. Limits: context is supplied/selected elsewhere; review remains scholarly-oriented; provider/UI/chapter QA and real translation quality are out of scope.

Gate 10 remains BLOCKED human quality: expert source/Hebrew references, blind labels and representative comparison are still required. Prior Gate-11/UI-SIMPLE commits remain synchronized on main/origin; no earlier acceptance is superseded.
