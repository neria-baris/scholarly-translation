# Provider and model selection contract

Status: authorized independent product slice from Session E; does not alter or
resolve Gate 10 human-quality acceptance.

## Component

Role-based provider/model configuration, provider-neutral text-generation
dispatch, capability metadata, provenance/cache identity, and minimal existing
settings-surface exposure.

## Owns

- Explicit model assignments for `translator`, `semantic_reviewer`,
  `chapter_qa`, `candidate_evaluator`, and optional `context_state_builder`.
- Provider definitions for `mock`, `openai`, `anthropic`, `deepseek`, and a
  named OpenAI-compatible endpoint, with credentials referenced only by
  environment-variable name.
- Provider adapters that convert the shared text-generation request/result
  boundary to provider SDK/HTTP shapes and sanitize provider failures.
- Configurable context/output/structured-output/endpoint capability metadata.
- Provider/model identity in applicable runtime provenance, audit events, and
  cache identity.

## Input

- Versioned JSON configuration following existing repository conventions.
- A resolved role, provider ID, user-supplied model ID, prompt, and optional
  injected mock client for tests.
- Credentials and optional base URLs from environment variables at dispatch
  time; never credential values in persisted configuration.

## Output

- Validated immutable configuration records and role selections.
- The existing provider-neutral `TextGenerationResult` contract, extended only
  where required for provider identity/usage metadata.
- Existing translation/review records with exact configured provider/model
  provenance and cache identity.
- Minimal secondary settings controls; no main-flow redesign.

## Invariants

- Core translation/review code does not import provider SDKs or encode request
  schemas.
- Model IDs are nonempty configuration values, not a hard-coded marketing-name
  allowlist. The same selection may be assigned to multiple roles.
- No implicit provider/model fallback. Missing selection, credential, SDK, or
  endpoint fails clearly before a paid call where practical.
- Secrets never enter prompts, logs, fixtures, source-controlled config, cache
  keys, errors, or provenance.
- Context limits are per configured model and user-overridable; no universal
  limit is assumed.
- Existing persisted schemas remain readable or receive explicit versioned
  compatibility behavior.
- Mock tests perform no network calls and establish no quality claim.

## Errors

- Reject malformed/unknown config fields, roles, providers, capability values,
  credential-variable names, and missing required compatible-provider base URL.
- Surface actionable sanitized configuration/transport/empty-response errors.
- Treat provider-returned model identity mismatch as observable provenance, not
  permission to substitute another configured selection.

## Side effects

- Reads named environment variables only when building a live adapter.
- Normal live adapters may make one explicitly requested provider call; tests
  inject mocked clients/transports.
- Settings persistence may write only non-secret provider/model/capability
  choices through the repository's existing preferences mechanism.

## Acceptance

- Mocked tests cover distinct selections by role; OpenAI, Anthropic, DeepSeek,
  and generic compatible dispatch; missing credentials; configurable capability
  overrides; exact provenance; cache invalidation on relevant provider/model
  change; and absence of silent fallback.
- Existing translation, semantic-review, runtime-control, CLI, and web-UI tests
  remain green; full suite passes.
- Documentation explains JSON configuration, credential/base-URL environment
  mapping, previous versus new behavior, and limitations.
- Sol reviews the complete diff, records append-only audit evidence, commits the
  intended paths, and verifies push status under repository rules.

## Out of scope

- Prompt, segmentation, QA-policy, context-assembly, routing, retry, budget, or
  translation-quality redesign.
- Choosing recommended production models, enabling paid calls, provider
  failover, OAuth/account setup, or claiming Gate 10/release acceptance.
- OCR, source-reading, glossary, export, or main translation-screen redesign.
