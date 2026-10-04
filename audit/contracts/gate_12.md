# Gate 12 contract — versioned translation profiles

```yaml
task_id: "G12-C1"
milestone: "Gate 12 — scholarly and literary translation profiles"
objective: "Expose explicit, versioned scholarly and literary prompt profiles through the existing provider-independent translation request, with layered context, cache/provenance identity, and a minimal uncertainty note."
in_scope:
  - "Implement the substantive runtime instructions from scholarly_translation_prompts_v2/runtime/01_scholarly_translation.md and 02_literary_translation.md."
  - "Support profile_id scholarly and literary without provider-specific branching."
  - "Keep stable style/profile instructions, glossary plus approved decisions, short local state, broader original source context, and TARGET UNIT visibly separate."
  - "Preserve source-bound semantically complete units supplied by the existing segmentation contract; make no line/paragraph assumption."
  - "Make profile/prompt/config revisions and all effective supplied context affect provenance and cache identity."
  - "Add a minimal nullable translation_note for material ambiguity, conflict, wordplay, or uncertainty."
  - "Update the earlier one-profile statement in ARCHITECTURE.md only as needed to remove the now-superseded contradiction."
out_of_scope:
  - "Structure detection, segmentation algorithms, context selection, provider/model infrastructure, UI, semantic review policy, chapter QA, export, and human approval."
  - "A plugin/registry framework, provider-specific prompt branches, paid/live model calls, or translation-quality claims."
relevant_paths:
  - "audit/contracts/gate_12.md"
  - "ARCHITECTURE.md"
  - "scholarly_translation/translation.py"
  - "scholarly_translation/translation_profiles.py (new if useful)"
  - "tests/test_translation.py"
inputs_and_fixtures:
  - "C:/Users/pc2/projects/scholarly_translation_prompts_v2/vscode_agents/B_translation_profiles.md"
  - "C:/Users/pc2/projects/scholarly_translation_prompts_v2/runtime/01_scholarly_translation.md"
  - "C:/Users/pc2/projects/scholarly_translation_prompts_v2/runtime/02_literary_translation.md"
  - "Existing synthetic Gate-7 structure and glossary fixtures only"
interface_contract: "build_translation_request remains source-bound and backward compatible for existing callers, accepts an explicit supported profile and optional caller-supplied approved decisions/local state/source context without selecting that context itself; TranslationRequest and translation-draft metadata expose effective profile/prompt/config identity; run_translation returns approved=false and a nullable translation_note. Unsupported profiles and malformed/oversized context fail closed without fallback or network activity."
acceptance_checks:
  - "Both supported profiles build deterministically distinct prompts containing their required fidelity rules and exact layered section markers."
  - "Prompt wording instructs translation of TARGET UNIT only and distinguishes broader SOURCE_CONTEXT."
  - "Approved glossary rules and supplied approved decisions appear only in the glossary/decision layer and remain source data, not instructions."
  - "Changing profile, prompt/profile version, approved decisions, local state, or source context changes cache/provenance identity; identical inputs remain stable."
  - "A completed structured result exposes translation text and null or one brief translation_note; legacy mock/offline behavior remains deterministic and unapproved."
  - "Focused translation tests and the full offline suite pass with zero paid runtime calls."
known_risks:
  - "The committed architecture previously deferred literary support; this user-directed gate supersedes only that profile-count decision."
  - "Existing tests and adapters return some unstructured mock/plain text, so compatibility must not fabricate semantic certainty."
  - "Context size remains bounded; this gate defines an input interface, not a selector or whole-chapter strategy."
source_provenance_required: true
builder_model: "Claude Sonnet (actual model reported by Claude Code)"
reason_for_model: "A bounded but cross-cutting prompt/schema/cache change fits the repository's designated primary builder and settled contract."
budgets:
  api_usd_hard: 2
  model_turns_hard: 1
  tool_calls_soft: 20
  wall_minutes_soft: 30
review_trigger: "Use no independent model review unless deterministic acceptance fails or a serious cache/provenance defect survives the single builder result."
stop_condition: "Stop after one implementation/delivery package, no paid runtime call, no audit/Git mutation, and no work in excluded components."
```

## Schema and compatibility decisions

- Keep the persisted stage name `translation-draft@1` and schema version 1 if the
  additive nullable note and metadata fields are accepted by existing readers;
  otherwise document and test an explicit migration. Never reinterpret an old
  field.
- Profile IDs are exact closed values `scholarly` and `literary`. Unknown values
  fail; there is no implicit default/fallback inside the request builder.
- Stable profile text is application-owned, versioned data. Caller-supplied
  decisions/state/context are bounded data and participate in fingerprinting.
- A translation note is not human approval, a source correction, or a semantic
  review finding.
