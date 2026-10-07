# Contract: learning grammar lesson (per chapter)

User request 2026-10-07: after each chapter, a few teaching paragraphs on grammar (gender,
inflection, active/passive, etc.) with examples from the chapter. User decisions: one extra
model call per chapter; examples = woven insertions + full chapter sentences rendered in the
target language; new preparations only (no backfill button).

- component: `scholarly_translation/learning_lesson.py`, prompt `runtime_prompts/11_learning_grammar_lesson.md`
  (`learning-lesson@1`, stage `learning-lesson-v1`), service step `LearningService._prepare_lessons`.
- owns: lesson request building, deterministic validation, storage shape (`recap.lesson`).
- input: accepted chunks + plan units of one chapter, effective catalog items, session language/level,
  topics of earlier lessons in the same book (<=30). Units capped at 40000 chars, insertions at 120
  (grammar-bearing edits first).
- output: `recap.lesson` = `{schema_version 1, status ready|unavailable, prompt_version, input_hash,
  provider, model, topics, paragraphs[{heading_he, text_he, examples[]}], dropped_examples}` or
  `{status unavailable, reason}`. Example kinds: `insertion` (chunk_id/edit_index; foreign/hebrew
  copied from the accepted edit) and `sentence` (unit_id; hebrew = exact whitespace-normalized
  quote of that unit; foreign = model translation, no Hebrew letters except Yiddish).
- invariants: lesson calls only for jobs started with `lessons` (new preparations); max_calls =
  chunks + chapters for those jobs, unchanged for older jobs; calls go through `_controlled`
  (budget, journal, cache, replay, explicit retry); a resumed job only calls for missing chapters;
  reader/export/archive never make a call.
- errors: malformed/structurally invalid answer -> `unavailable` record, book still ready;
  ungrounded examples dropped and counted; provider/budget failures follow the chunk-call path.
- side_effects: one paid Luna call per chapter (~$0.002-0.005 list estimate), inside the job budget.
- acceptance: `tests/test_learning_lesson.py`, updated learning service tests, full offline suite.
- out_of_scope: backfilling lessons for already prepared books; linguistic correctness review
  (model-written, disclosed in UI/help/export).

## Addendum: dictionary entries and grammar notebook (same day)

User decisions: entries "from now on" inside the existing chunk call (no extra call, no backfill),
for every lexical item when first woven (catalog words too, not only model-proposed ones);
a consolidated grammar notebook.

- component: `scholarly_translation/learning_dictionary.py`, prompt `runtime_prompts/12_learning_dictionary_entries.md`
  (`learning-dictionary@1`, appended to the chunk prompt; chunk prompt_version gets `+learning-dictionary@1`),
  `LearningService.grammar_notebook`, route `/learning/grammar-notebook`.
- input: `DICTIONARY_NEEDED` = selected lexical IDs without an entry in this job or in completed books of the language.
- output: optional `chunk.dictionary_entries[{item_id, part_of_speech, gender, senses_he[1-4], forms[<=16
  {label_he, form}], notes_he}]`, only for lexical items used by accepted edits and not already known.
  Covered by prepared_hash, not by content_hash (export hash checks unchanged).
- invariants: only jobs started with `dictionary` (new preparations); invalid entries are dropped and never
  reject the chunk; first entry per item wins; book examples come from accepted edits (woven sentence),
  never from the model; progress rows carry `entry`/`examples` (grammar rows `explanation_he`);
  dictionary.json/md include them; notebook and progress make no model call.
- out_of_scope: entries for words learned before this change; linguistic review of entries.
