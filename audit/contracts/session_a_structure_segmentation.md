# Session A contract — logical structure and semantic segmentation

- task_id: `SESSION-A-STRUCTURE-1`
- milestone: replace default visual-line units with conservative logical document
  structure and bounded semantic translation units.
- owner: Sol conducts and verifies; Claude Code Sonnet is the single scoped
  builder. Base commit: `36fbbf04e22bae2643b91956940c81a7cd2fc6ed`.

## Scope

- In scope: the structure/segmentation implementation, its direct schema
  documentation and compatibility helpers, focused fixtures/tests, and only
  the smallest direct-consumer adaptations required to keep existing public
  workflows valid.
- Out of scope: translation/review prompt wording, quality policy, provider or
  model routing, UI redesign, budget infrastructure, OCR engine behavior,
  automatic scholarly/source approval, and literary profile implementation.
- Historical source evidence and committed structure artifacts remain
  inspectable. Derived structure never overwrites extraction or OCR evidence.

## Inputs and outputs

- Input remains validated schema-3 `Document`, optional validated OCR bundle,
  explicit human source decisions, optional explicit boundary overrides, and
  an optional prior structure artifact.
- The current page readings and exact evidence anchors remain authoritative.
- New output documents a minimal versioned representation for hierarchical
  nodes and semantic translation units. It represents, at minimum, part or
  chapter, section or subsection, heading or subheading, paragraph, scene
  break, quotation, list, note, caption, formula, bibliography entry and page
  furniture. Unsupported/uncertain classification remains explicit rather
  than guessed.
- Every logical node and unit carries stable identity, ordered source links,
  exact half-open source spans, selected-reading identity/version/hash, and
  the intersecting PDF/OCR anchors. Reconstructed paragraph grouping must not
  erase or silently rewrite source characters.
- Existing structure schema-1 artifacts remain readable and validated. New
  schema revisions must not be silently interpreted as the old line model.

## Segmentation policy

- Default segmentation is based on logical blocks, not one visual line and not
  a fixed one-paragraph rule.
- Scholarly units group semantically coherent adjacent body blocks and prefer
  structural boundaries. A target of roughly 1,000–2,000 source words is a
  heuristic only; strongest internal boundaries split oversized groups.
- The implementation stays bounded and deterministic. It may expose a narrow
  mode/policy parameter if needed for scholarly versus literary boundary
  behavior, but it must not add profile routing or literary translation code.
- Page furniture remains source-linked and distinguishable from body content.
  Notes, captions, formulas, bibliography entries, quotations, lists and scene
  breaks remain explicit; they are never silently dropped.
- Manual boundaries remain validated, exact and non-overlapping. Invalid plans
  fail instead of being repaired.

## Acceptance checks

1. Focused tests prove reconstruction/grouping of PDF visual lines into a
   paragraph while retaining exact source spans and anchors.
2. Tests cover chapter/section/heading levels, notes, page furniture,
   quotations/lists/captions/formulas/bibliography/scene breaks, deterministic
   reading order, and no source-span loss or overlap.
3. Tests prove semantic boundaries prefer headings/scene boundaries over the
   1,000–2,000-word heuristic and split oversized content at the strongest
   available internal boundary.
4. Stable IDs/version/predecessor behavior and complete historical snapshots
   survive a boundary or classification change; legacy schema-1 artifacts are
   still accepted without fabricating new provenance.
5. Digital and OCR-backed resolved readings work; unresolved readings still
   emit no translatable units. Existing source-decision safeguards remain.
6. Direct consumers and the full existing test suite pass without prompt,
   routing, UI, budget or approval-policy changes.
7. Schema and old/new behavior, conservative heuristics and known limitations
   are documented in repository-facing Markdown.

## Errors, side effects and stop condition

- Malformed or stale structure/provenance raises a sanitized `StructureError`;
  source text is not echoed in errors. No network or runtime model call is
  introduced.
- Builder budget: one Sonnet subscription invocation, at most 60 tool calls and
  45 wall minutes; usage/list estimate recorded if observable, actual charge
  otherwise `not_metered`. One focused fix is reserved after conductor review.
- Stop after implementation and tests are authored, returning changed files,
  tests run or not run, deviations and open risks. The builder does not edit
  audit histories, current state, Git metadata or commits.
