# REASONING-CHOICE — per-role reasoning effort selectable in the UI

Authority: user request 2026-10-07 (Claude continuity, user-directed): the models run at a low
reasoning effort (catalogue default: gpt-6-luna `none`, gpt-6.1-sol `low`) and the UI offers no way
to choose the level. Make it selectable. The project defaults are unchanged.

## Behaviour

- `model_config.ModelCapabilities.reasoning: str | None` (default None). `from_dict` accepts an
  optional `reasoning` (lowercase word, at most 32 characters) or null; `to_dict` emits the key only
  when it is set, so every existing configuration, its fingerprint and all cache/step identities
  built from it are byte-identical.
- `model_settings`: a catalogue selection may carry `reasoning`; it must be one of that model's
  catalogue `reasoning_values` (a model with none rejects any value). It is stored in the role's
  capabilities. `catalogue()` lists `reasoning_values` and `default_reasoning` (first value or null).
  "Other" selections stay without reasoning.
- Every runtime adapter build that has the role's capabilities passes
  `reasoning=capabilities.reasoning` (web UI per-job factory, chapter pipeline, review controls,
  unit translation, unit review, semantic critic/corrector). The OpenAI adapter already validates it
  against the catalogue and sends `reasoning.effort`; None keeps the catalogue default.
  `build_translation_adapter` refuses a reasoning value for a provider type that does not take one.
- UI: next to each catalogue model with reasoning values, a "reasoning level" select: "default
  (<value>)" plus the listed values; changing the model resets it to default. QA mirroring copies it
  with the model. Hebrew and English labels.

## Invariants

- No default changes; an unset level sends exactly what was sent before.
- A set level is part of the configuration fingerprint (chapter steps) and the unit cache key, so a
  result made at another level is never reused as if it matched.
- No provider call; no new dependency; learning keeps its fixed Luna configuration.

## Errors

Unsupported level for the model, or a level for a model without levels: `ModelSettingsError`
(Hebrew, with an English entry in SERVER_EN).

## Acceptance

Unit tests: capabilities round trip and legacy fingerprint unchanged; selection validation; adapter
receives the level; catalogue fields. Full offline suite passes.

## Out of scope

Anthropic thinking/effort control, "other" model reasoning, the learning page, the cost preview
(an estimate from output caps; a higher level spends more output tokens within the same caps).
