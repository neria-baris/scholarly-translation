# Claude Integration Conductor — Scholarly Translation Project

## Purpose

This file is the source of truth for the remaining implementation and integration work on the `scholarly-translation` project.

Claude should act primarily as the **integration conductor**:
- inspect existing work;
- validate completed branches/worktrees;
- merge safely;
- run tests;
- launch the remaining implementation stages;
- use sub-agents when parallel execution is useful;
- stop only for genuine product/architectural ambiguity.

Do **not** rerun completed stages unless their implementation is missing, broken, or unusable.

---

# Current status

The following stages have already been completed by separate agents:

- **A — Document Structure & Segmentation**
- **B — Scholarly & Literary Translation Profiles**
- **C — Independent Translation Review & Model Comparison**
- **E — Model / Provider Selection**

Treat A/B/C/E as **completed implementation work awaiting validation/integration**, not as tasks to reimplement.

Your first responsibility is to inspect their branches/worktrees/commits and determine:
- whether each is committed;
- whether tests pass;
- whether the implementation matches its intended scope;
- whether there are conflicts between them;
- whether any of them have already been merged.

Use Git/worktree state as the source of truth.

Useful first commands include:

```bash
git status
git branch -a
git worktree list
git log --oneline --graph --decorate --all
```

Do not assume stage completion merely from branch names. Verify the actual diff and tests.

---

# Parallelism policy

You may and should use **sub-agents** for independent work.

Parallel execution is encouraged when tasks do not depend on each other's output.

In particular:

- After A is integrated, **D and X should run in parallel**.
- Independent review/test work may be delegated to separate sub-agents.
- Merge-conflict inspection, export validation, and UI testing may be delegated when this avoids serial bottlenecks.
- Do not run two implementation sub-agents against the same working tree.
- Give each implementation sub-agent its own branch/worktree.
- Keep sub-agent scopes narrow and explicit.
- Do not let sub-agents redesign the architecture outside their assigned task.

Claude remains responsible for:
- deciding whether outputs are acceptable;
- integrating branches;
- resolving straightforward conflicts;
- escalating only genuine architectural/product decisions.

---

# Overall execution order

## Phase 1 — Validate and integrate completed work

A, B, C, E are already complete.

1. Inspect all A/B/C/E branches/worktrees.
2. Validate scope and tests.
3. Integrate **A first** because D and X depend on the document-structure schema.
4. Integrate B, C, E in a safe order based on actual overlap.
5. Resolve straightforward conflicts yourself.
6. Stop and ask only if a conflict reflects a real product/architecture choice.

## Phase 2 — Launch D and X in parallel

Once A is integrated:

- **D — Context Strategy**
- **X — PDF/EPUB Reconstruction and Export**

Create separate branches/worktrees and launch these in parallel, preferably via sub-agents.

## Phase 3 — Integrate backend

After D and X complete:

1. Inspect diffs.
2. Run relevant tests.
3. Integrate D and X with B/C/E.
4. Run the full relevant backend test suite.
5. Fix only concrete integration defects.

## Phase 4 — F UI integration

Only after A/B/C/D/E/X are integrated and stable:

- run **F — Simple UI Integration**

## Phase 5 — G final integration review

Only after F is integrated:

- run **G — Final Integration Review**

G is not a feature-development stage. It should detect and fix concrete integration defects only.

---

# Global operating rules

- Do not redesign the project.
- Do not introduce RAG, embeddings, vector databases, or a large Story Bible.
- Preserve provenance, caching, audit history, and versioning.
- Do not rewrite historical audit records.
- Use deterministic tests before expensive model calls.
- Avoid unnecessary paid API calls.
- Do not hard-code OpenAI/Luna assumptions.
- The model/provider layer must remain generic enough for OpenAI, Claude/Anthropic, DeepSeek, and other supported providers.
- Keep append-only integration notes where practical.
- Before every merge:
  - inspect the diff;
  - inspect tests;
  - understand overlap with already integrated changes.
- If a merge conflict is straightforward and the intended combined behavior is clear, resolve it yourself.
- Ask the user only if resolving it requires a real product or architecture decision.

---

# D — Context Strategy

You are working on the scholarly-translation project after the document-structure schema has been integrated.

Your task is to replace the current narrow translation-context strategy with a semantic-unit, chapter-aware strategy.

Do not redesign unrelated parts of the system.

## Core principle

**Translation unit != context window.**

The model should translate a semantically complete unit while being allowed to see substantially more source context.

### 1. Translation units

Choose translation units according to meaning and document structure, not PDF lines or arbitrary fixed paragraph counts.

For scholarly text, prefer:
- a section;
- a subsection;
- a coherent argumentative move;
- or another semantically complete sequence.

For literary text, prefer:
- a scene;
- a coherent narrative block;
- a dialogue sequence;
- or another semantically complete unit.

Use approximately **1,000–2,000 source words** as the initial practical target size, but treat this only as a heuristic.

Do not split a coherent unit merely to hit the target size.
Do not combine unrelated material merely to reach it.

Translation units must remain bounded enough for:
- review;
- caching;
- selective retranslation;
- provenance;
- interruption/resume.

### 2. Broader context than output

The model should normally see more text than it is asked to translate.

If the enclosing source chapter fits comfortably within the selected model's usable context budget:

- provide the entire original source chapter;
- explicitly mark the exact translation target;
- instruct the model to translate only the target.

If the chapter is too large:

provide:
1. the complete current translation unit;
2. substantial original source text immediately before and after it;
3. relevant original passages elsewhere in the chapter when needed;
4. the structured context layers described below.

Prefer original source text over generated summaries whenever feasible.

Do not default to chapter summaries.

### 3. Maintain three distinct context layers

Keep these conceptually and technically separate:

#### A. Fixed style/profile instructions

Examples:
- scholarly translation rules;
- literary translation rules;
- target-language style requirements.

#### B. Glossary and approved translation decisions

Examples:
- established technical terminology;
- names;
- recurring expressions;
- approved renderings;
- explicit translation decisions.

#### C. Short local state

Examples:
- current speaker;
- viewpoint;
- relevant characters;
- referents of pronouns;
- previously introduced definitions;
- current argumentative position;
- current scene state;
- unresolved ambiguity.

Do not collapse these layers into one free-form prompt blob.

### 4. Source-backed memory

Context memory is an aid, not an authority.

Whenever a material context fact or translation decision is stored, preserve where practical a reference to the source passage or structural block supporting it.

Examples:
- a definition should reference where it was introduced;
- speaker identity should reference the relevant scene/dialogue evidence;
- an important terminology choice should reference its approved decision/source.

If something is uncertain, preserve the uncertainty.

Do not convert an inference or guess into a certain remembered fact.

When exact wording matters, provide the original source passage to the translator instead of relying only on a paraphrased memory.

### 5. Target/context separation

Every model request must clearly distinguish:

- SOURCE TO TRANSLATE
- SOURCE PROVIDED ONLY AS CONTEXT
- STYLE INSTRUCTIONS
- GLOSSARY / APPROVED DECISIONS
- LOCAL STATE

The model must be explicitly instructed:
- translate only the target;
- use context only for interpretation;
- do not insert information merely because it appears elsewhere in the chapter.

### 6. Model-aware context budgets

Do not hard-code one context-window size.

Use the provider/model metadata introduced by the model-selection layer.

Reserve reasonable headroom for:
- instructions;
- glossary;
- local state;
- output;
- review metadata.

The exact proportion should be configurable.

Do not assume that all OpenAI, Claude, DeepSeek, or future models have the same context characteristics.

### 7. Whole-chapter translation experiment

Support whole-chapter translation as an alternative strategy for chapters that fit comfortably.

Do not make it the universal default.

The system should make it possible to compare:

A. semantic-unit translation with chapter context

versus

B. whole-chapter translation in one request

on representative chapters.

Record enough metadata to compare:
- quality;
- completeness;
- runtime;
- model usage/cost where available.

Do not declare either strategy universally superior in code.

### 8. Provenance

For every translation output, separately record:

#### Target source
The exact spans/blocks actually translated.

#### Context source
The additional source spans/structural units shown to the model.

Also record:
- translation profile;
- context-policy version;
- model/provider;
- prompt version;
- glossary/decision version where applicable;
- local-state version where applicable.

It must be possible to answer:

"What exact text was translated?"

and independently:

"What source context and stored context did the model see?"

### 9. Cache and invalidation

Preserve selective caching and retranslation.

Do not naïvely invalidate every translation unit merely because any character elsewhere in the enclosing chapter changed.

Choose the simplest defensible dependency strategy.

A change to:
- target source;
- materially relevant approved terminology;
- translation profile;
- prompt version;
- model;
- material local state

should invalidate appropriately.

Document the chosen policy.

Do not create a complex dependency graph unless existing architecture requires it.

### 10. Chapter-level assembly support

After separately translated units are assembled into a chapter, the pipeline must expose the assembled chapter to the existing chapter-level QA/review layer.

Do not implement a second QA system here.

Ensure enough provenance remains to trace any chapter-level issue back to its component translation unit.

### 11. Tests

Add/update tests covering at least:

- semantic translation-unit construction;
- approximately 1,000–2,000-word heuristic without treating it as a rigid boundary;
- full chapter supplied as context when it fits;
- fallback for oversized chapters;
- original source preferred over generated summary;
- separate style / glossary-decisions / local-state layers;
- source-backed state references;
- uncertainty preserved as uncertainty;
- target source distinguished from context source;
- model-aware context limits;
- whole-chapter mode available for comparison;
- context crossing PDF page boundaries;
- compatibility with existing provenance/cache/review behavior.

### Explicitly out of scope

Do NOT add:
- vector search;
- embeddings;
- general-purpose RAG;
- a large Story Bible;
- new autonomous agent orchestration;
- UI work;
- export/rebuild work;
- unrelated model-routing complexity.

Use the simplest direct-source-context solution possible.

### Completion

When finished:

1. summarize old context behavior;
2. summarize new semantic-unit behavior;
3. explain the chapter-context fallback;
4. explain the three context layers;
5. explain source-backed memory;
6. explain cache/invalidation behavior;
7. describe whole-chapter comparison mode;
8. list files changed;
9. list tests added/changed;
10. note remaining limitations;
11. commit completed work to this branch.

Do not merge other branches.

---

# X — PDF/EPUB Reconstruction and Export

You are working on the scholarly-translation project after the document-structure layer has been integrated.

Your task is to implement format-preserving translated-document export.

The desired product behavior is:

**PDF input -> translated PDF output**

**EPUB input -> translated EPUB output**

Preserve the original document's logical structure and visual character as far as reasonably possible.

Do not redesign translation, context, review, or model-selection logic.

## 1. General principle

The translated output should feel like the translated version of the source document, not like a generic newly generated report.

Preserve wherever possible:

- document hierarchy;
- chapters;
- headings/subheadings;
- paragraph boundaries;
- lists;
- block quotations;
- footnotes/endnotes;
- captions;
- images;
- tables;
- formulas;
- emphasis;
- links;
- page/section ordering.

Translation text may occupy different physical space from source text, especially when translating into RTL Hebrew.

Do not promise pixel-identical layout when this is not technically possible.

## 2. EPUB

For EPUB input, preserve the existing EPUB structure whenever feasible rather than converting it into another format and rebuilding from scratch.

Preserve, where supported:

- package metadata;
- spine/order;
- table of contents;
- chapter files;
- HTML hierarchy;
- CSS;
- images;
- internal links;
- external links;
- notes;
- emphasis;
- semantic block structure.

Replace translatable textual content using the translated structural blocks.

Add correct Hebrew/RTL document semantics where needed without unnecessarily destroying the original styling.

The generated EPUB must pass a reasonable structural/validity check.

Do not flatten EPUB into plain text.

## 3. PDF

For PDF input, reconstruct a translated PDF using the detected logical structure and retained layout/style metadata.

Preserve as far as reasonably possible:

- page size;
- margins;
- hierarchy;
- heading styles;
- paragraph styling;
- images;
- tables;
- captions;
- formulas;
- footnotes;
- visual separators.

Do not force Hebrew translated text into original fixed bounding boxes when this creates unreadable layout.

Allow reflow where necessary.

The objective is:
- same document identity and visual style;
- not exact pixel reproduction.

Support RTL Hebrew correctly.

Avoid mirrored punctuation, broken numbered lists, or incorrect bidirectional text behavior.

## 4. Style mapping

Use retained source metadata to derive a reusable style mapping.

Where exact fonts cannot be reused or lack Hebrew glyphs:
- select an appropriate Hebrew-capable fallback;
- preserve relative hierarchy such as title > heading > body > note;
- preserve bold/italic distinctions where meaningful.

Do not ship or expose proprietary font files.

## 5. Source structural linkage

Export must operate on the canonical document-structure representation produced by the structure stage.

Do not build a second independent interpretation of chapters/headings/paragraphs.

Each translated output block should remain traceable to:
- its translation unit;
- its source structural block(s).

## 6. Bilingual/debug outputs

If existing bilingual HTML/debug exports are useful, preserve them as secondary outputs.

Do not make them the primary product output.

Primary output:
- PDF for PDF input
- EPUB for EPUB input

## 7. Graceful degradation

Some PDFs may be too complex for high-fidelity layout reconstruction.

When preservation is incomplete:
- generate a readable, structurally faithful translated document;
- record what could not be preserved;
- do not silently claim exact layout preservation.

Examples:
- complex floating figures;
- highly irregular magazine layouts;
- scanned pages with no recoverable structure.

## 8. Tests

Add representative tests for:

### EPUB
- chapter structure;
- TOC;
- CSS retention;
- images;
- links;
- Hebrew RTL output;
- valid package reconstruction.

### PDF
- heading hierarchy;
- paragraphs;
- footnotes;
- images;
- simple tables/formulas where supported;
- Hebrew RTL;
- page generation;
- readable reflow.

Also test:
- input format determines default output format;
- source/translation structural linkage survives export;
- export failure is reported clearly;
- existing HTML/debug exports continue to work where intended.

Use small deterministic fixtures.

## 9. Scope

Do NOT:
- alter translation prompts;
- change context policy;
- redesign semantic review;
- introduce a new UI;
- build a desktop publishing suite;
- attempt arbitrary pixel-perfect PDF editing.

Implement the smallest robust exporter that makes the translated document usable and preserves its structure/style well.

## Completion

When finished:

1. state what EPUB preservation supports;
2. state what PDF preservation supports;
3. clearly state limitations;
4. list files changed;
5. list dependencies added;
6. list tests added/changed;
7. provide one small end-to-end example for each supported format if fixtures allow;
8. commit completed work to this branch.

Do not merge other branches.

---

# F — Simple UI Integration

Run this only after A/B/C/D/E/X are integrated and stable.

Your task is to update the user interface so the application exposes the new capabilities through a simple translation workflow.

This is a UI integration task, not a backend redesign.

## Product principle

The application should feel like:

**put a PDF or EPUB in -> choose a few meaningful options -> translate -> download the translated document**

Do NOT expose the internal pipeline, Gates, provenance machinery, segmentation internals, cache system, or implementation details on the primary screen.

The backend may be complex. The user interface should not be.

## Primary workflow

The main screen should support:

1. Upload/select a source document:
   - PDF
   - EPUB

2. Choose translation profile:
   - Academic
   - Literary

3. Choose translation model:
   - Auto
   - or any configured available model/provider

4. Choose quality/review mode:
   - Fast
   - Checked
   - Thorough

5. Start translation.

6. Show understandable progress.

7. When complete, allow the user to download the translated document.

The output format should follow the input format where supported:

- PDF input -> PDF output
- EPUB input -> EPUB output

If a format-preserving exporter is not yet implemented, expose the best currently supported output clearly without pretending preservation exists.

## Model selection

Use the integrated provider/model configuration layer.

The user must be able to select any configured model, including models from different providers such as:
- OpenAI
- Anthropic / Claude
- DeepSeek
- other supported providers

Do not hard-code model names into the UI.

Populate choices from the backend/provider registry.

### Default/simple mode

The main screen should expose only one simple model selector:

`Model: Auto | <available models>`

When `Auto` is selected, use backend defaults.

### Advanced settings

Add an unobtrusive Advanced section or dialog where the user may independently choose, where supported:
- Translator model
- Reviewer model
- Chapter QA model
- Candidate evaluator model
- Context/state model

Do not require these selections for normal use.

If no reviewer is used under the selected quality mode, do not force the user to choose a reviewer model.

## Quality modes

Map the UI modes cleanly onto backend behavior.

### Fast
Translation only.

No routine semantic review unless required by a hard failure or existing safety/integrity rule.

### Checked
Default recommended mode.

Translate normally and invoke semantic review only when the pipeline flags meaningful uncertainty/risk or when configured policy requires it.

Run chapter-level consistency/continuity checks after units are assembled where supported.

### Thorough
Run semantic review for every translation unit plus chapter-level QA.

Do not implement new review architecture here. Use the existing integrated backend capabilities.

Clearly communicate that these modes trade speed/cost for additional checking.

## Academic vs Literary

### Academic
Use the scholarly translation profile and its existing rules for:
- semantic fidelity
- terminology
- logical structure
- citations
- formulas
- ambiguity

### Literary
Use the literary profile and its existing rules for:
- voice
- register
- dialogue
- viewpoint
- character continuity
- recurring phrases
- ambiguity

Do not duplicate prompt logic in the UI layer.

The UI should select the profile; backend prompt construction remains authoritative.

## Context behavior

Do not expose token windows, paragraph counts, chapter IDs, RAG controls, or raw context configuration on the normal screen.

The backend determines context using semantic translation units and chapter-aware context.

The UI may display short human-readable statuses such as:
- "Translating Chapter 3"
- "Checking terminology"
- "Reviewing chapter consistency"

but not internal prompt/context details.

## Progress UX

Progress should represent meaningful user-level work, not internal Gate names.

Prefer stages such as:
- Reading document
- Detecting structure
- Translating
- Reviewing
- Rebuilding document
- Complete

Where possible, show useful progress such as:
`Chapter 4 of 12`

Do not display raw logs on the main screen.

## Output and format preservation

The primary output must use the integrated format-preserving export layer.

Default behavior:

- PDF input -> translated PDF
- EPUB input -> translated EPUB

The primary completion action should therefore be:

- Download translated PDF

or

- Download translated EPUB

as appropriate.

Do not implement document reconstruction inside the UI.

Use the integrated exporter.

Where the exporter reports preservation limitations, expose a concise user-readable warning rather than pretending the original layout was perfectly preserved.

Secondary outputs may include, if already supported:
- bilingual HTML
- QA/review report
- debug/provenance report

Keep all secondary outputs visually subordinate to the translated document.

## Error handling

Convert backend errors into understandable messages.

Examples:
- unsupported PDF structure;
- OCR required/failed;
- provider authentication missing;
- selected model unavailable;
- translation interrupted;
- export failed.

Do not surface raw Python exceptions or internal schema errors as the primary user message.

Where possible, offer an actionable next step.

## Visual design

Preserve the existing simple visual direction of the project.

Do not turn the interface back into a pipeline dashboard.

Keep the main screen visually restrained and uncluttered.

Maintain the existing project visual identity rather than replacing it with a generic admin UI.

Do not introduce unnecessary sidebars, dense cards, developer controls, or workflow-step navigation.

Advanced controls should remain visually secondary.

## State and resumability

If the backend supports resumable work, reflect this simply.

Examples:
- Resume translation
- Translation interrupted
- Continue from Chapter 7

Do not expose internal cache keys, hashes, checkpoints, or provenance IDs.

## Compatibility

Do not duplicate business logic in frontend code.

Use existing backend APIs/services for:
- structure;
- translation;
- context;
- review;
- model/provider selection;
- export.

If an API boundary is missing, add only the smallest adapter needed.

Do not redesign the backend.

## Tests

Add/update tests covering at least:
- PDF and EPUB input selection;
- Academic/Literary profile selection;
- model list populated dynamically from available providers;
- Auto model behavior;
- Fast / Checked / Thorough mapping;
- advanced independent model selectors where applicable;
- translation start;
- progress-state rendering;
- error rendering;
- completion/download state;
- absence of internal pipeline controls from the primary workflow;
- compatibility with the integrated backend.

If end-to-end UI tests already exist, extend them rather than introducing a second testing framework.

## Explicitly out of scope

Do NOT:
- redesign translation architecture;
- add RAG or embeddings;
- alter context policy;
- rewrite translation prompts;
- invent a new review system;
- redesign provenance;
- add a large project-management dashboard;
- expose all backend settings to users;
- rebuild the application using a new frontend framework unless absolutely necessary.

Use the current frontend stack.

## Completion

When finished:

1. summarize the old UI workflow;
2. summarize the new user workflow;
3. explain how model/provider selection is exposed;
4. explain Fast / Checked / Thorough behavior;
5. state which output formats actually work end-to-end;
6. list files changed;
7. list tests added/changed;
8. identify backend capabilities that are still missing rather than faking them in the UI;
9. commit completed work to this branch.

Do not merge other branches.

---

# G — Final Integration Review

Run only after F is integrated.

Perform a final integration and end-to-end review of the scholarly-translation project.

All recent implementation work has now been integrated.

The project should support:

- logical PDF/EPUB document structure;
- semantic translation units;
- scholarly and literary translation profiles;
- configurable model/provider selection;
- OpenAI, Anthropic/Claude, DeepSeek, and other supported providers without hard-coded provider assumptions;
- broad chapter-aware source context;
- separate style, glossary/approved decisions, and local-state context layers;
- source-backed context memory;
- optional semantic review;
- chapter-level QA;
- candidate translation comparison;
- PDF -> translated PDF;
- EPUB -> translated EPUB;
- simple UI exposing the above without exposing internal pipeline complexity.

Your task is NOT to add features or redesign architecture.

Your task is to find and fix concrete integration defects.

## 1. Run the complete relevant test suite

Run all project tests relevant to the integrated pipeline.

Do not stop after the first passing subsystem.

Report:
- passed tests;
- failures found;
- fixes made;
- tests still failing.

## 2. Check cross-component assumptions

Look specifically for mismatches between:
- document structure and translation units;
- translation units and context selection;
- context selection and prompt construction;
- profiles and prompt versions;
- model/provider configuration and actual model calls;
- translator and reviewer model configuration;
- semantic review and quality-mode selection;
- translated blocks and chapter assembly;
- chapter assembly and chapter QA;
- document structure and PDF/EPUB export;
- exporter and UI download behavior;
- cache keys and new context/profile/model semantics;
- provenance and new target-vs-context distinction.

## 3. Remove obsolete assumptions

Find concrete remaining assumptions such as:
- one extracted line == one translation unit;
- previous/next unit is the only translation context;
- OpenAI/Luna is hard-coded;
- only scholarly profile exists;
- every translation requires semantic review;
- HTML is the only meaningful output;
- headings are ordinary body text;
- PDF and EPUB are treated as plain text containers.

Fix these only where they conflict with the integrated intended behavior.

## 4. Quality-mode behavior

Verify end-to-end:

### Fast
Translation without routine semantic review.

### Checked
Translation with risk/uncertainty-triggered review plus chapter-level consistency checks where supported.

### Thorough
Semantic review of all translation units plus chapter-level QA.

Ensure the UI and backend agree exactly on these semantics.

## 5. Provider/model behavior

Verify that:
- available models are discovered/configured through the provider layer;
- the user can choose a translation model;
- advanced independent models can be selected for translator/reviewer/chapter QA/evaluation where supported;
- Auto uses backend defaults;
- no UI component contains a hard-coded list that can drift from the provider registry;
- provider credentials/errors are handled cleanly.

Do not make live paid API calls unnecessarily.

Use mocks/fixtures where appropriate.

## 6. End-to-end fixtures

Where practical, run at least:

### Academic fixture
source -> structure -> semantic units -> context -> translation mock -> optional review -> chapter assembly -> export.

### Literary fixture
source -> scene/narrative unit -> literary context -> translation mock -> chapter assembly -> export.

### EPUB fixture
EPUB -> translated EPUB.

### PDF fixture
PDF -> translated PDF.

Use deterministic/mock translation outputs unless a tiny live call is already part of established project testing.

## 7. UI

Check that the primary UI remains simple.

A normal user should primarily see:
- source document;
- Academic / Literary;
- model / Auto;
- Fast / Checked / Thorough;
- Translate;
- understandable progress;
- Download translated PDF/EPUB.

Internal pipeline concepts must not dominate the primary interface.

## 8. No scope creep

Do NOT introduce:
- RAG;
- embeddings;
- large Story Bible systems;
- a new frontend framework;
- new orchestration systems;
- speculative abstractions;
- unrelated refactors.

Only fix demonstrated integration problems.

## 9. Documentation

Update concise project documentation so the implemented architecture is described accurately.

Document:
- translation unit strategy;
- context policy;
- profiles;
- quality modes;
- provider/model configuration;
- export formats and limitations;
- how to run the application;
- how to run tests.

Remove or clearly mark documentation that describes obsolete behavior.

## Completion

Return a concise integration report:

1. test results;
2. integration defects found;
3. fixes made;
4. remaining known limitations;
5. supported end-to-end workflows;
6. exact commands for running the app;
7. exact commands for running the test suite.

Commit only concrete integration fixes and required documentation updates.

Do not redesign the system.

---

# Suggested conductor behavior after reading this file

Start by inspecting the repository.

Then report briefly:

1. which A/B/C/E worktrees/branches exist;
2. which are clean/dirty/committed;
3. which are already merged;
4. which are ready to integrate;
5. whether A can be integrated immediately.

After that, proceed autonomously wherever the next action is unambiguous.

When A is integrated, launch **D and X in parallel using separate sub-agents/worktrees**.

After backend integration, launch F.

After F integration, launch G.

Keep the user informed only at meaningful milestones or blockers.
