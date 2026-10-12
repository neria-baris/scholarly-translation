# COMIC-REVIEW — the literary engine's review mechanism for comics

Date: 2026-10-12. User request: take the review mechanism of the literary translation engine
(independent review, issue taxonomy, application rule) instead of the ad-hoc comic reviewer, add a
"questionable source reading" finding, keep the review-unit size open to change and compare sizes,
and check text pages too. Supersedes the comic-review@1 rewrite pass (e77cf0c).

Component: `scholarly_translation/comics/review.py`, prompts `runtime_prompts/17_comic_review.md`
(critic, adapted from 04 independent semantic review + 06 chapter QA literary/Hebrew-quality
sections), `18_comic_correction.md`, `19_comic_reread.md`; wiring in `comics/pipeline.py`.

Flow per review unit (`--review-unit panel|page|pages:N`, default page): critic call (role
semantic_reviewer, falls back to translator) returns PASS or issues with category, severity
CRITICAL/MAJOR/MINOR, smallest source/translation spans, problem and suggested correction.
Categories: fidelity (omission, addition, mistranslation, negation, quantifier_scope, modality,
condition_causality, referent_speaker, notebook_departure, names_numbers, disambiguation,
lost_ambiguity, over_literal, humor_wordplay, voice_register), hebrew_quality, consistency,
continuity, completeness, and comic-only source_reading.
Application (review-suggestions rule): fidelity and hebrew_quality always; consistency/continuity
only MAJOR/CRITICAL; completeness note only. A translation span found exactly once is replaced
locally (no call); others go to one correction call per unit (role translator). source_reading:
one re-reading call on enlarged crops, regions whose reading changed are retranslated (earlier
transcription kept in `source_reread`). Corrected regions get one focused recheck (`--recheck
on|off`); its findings are recorded, never applied (each finding sent once). All calls journaled
and replayed on rerun; a failed review keeps the translation with warning `review_failed`.

Records: `translation.review` = {issues, applied (with method span|correction|reread), notes,
previous, recheck}; `region.source_reread`; `page.reviewed`. Pages flow: prepare (recognition,
translation) -> review per unit (units may span N pages) -> finish (fit, shorten, render).

Acceptance: offline tests for parsing/rule/spans/units/prompts and pipeline paths (span, correction,
reread+retranslate, rule notes, unit sizes, replay). Live comparison of unit sizes on the same
translations (text pages included) is evidence only, not a quality claim.
