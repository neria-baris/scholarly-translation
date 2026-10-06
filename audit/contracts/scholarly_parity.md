# SCHOLARLY-PARITY — notebook, name table and cross-chapter QA for scholarly books

Date: 2026-10-06. Base: 8fc64a3. Claude continuity, user-directed. The user asked whether
the context work done for fiction (LIT-NOTEBOOK, REVIEW-EFFECT, NAMES-CROSSQA, SOURCE-PASS)
was carried over to scholarly books.

Finding (offline): the pipeline runs the notebook, name table and cross-chapter windows for
every automation job, scholarly included, but only the keeper prompt was profile-aware
(SCHOLARLY-MATH). The name-table prompt (09) asked only for persons, places, ranks and
invented terms; the cross-chapter prompt (10) checked forms of address between characters,
character gender and narrator voice; the keeper listed running jokes and character address
as rules for every book; prompts 04/06 described the notebook in literary terms only; the
scholarly style profile never told the translator to follow BOOK_NOTEBOOK.

Delivered (prompts and copy only; no new steps, no new calls, no deterministic checks):
- name_table: KINDS gains `person` and `work` (additive; old tables stay valid). The
  source-pass prompt gets `{{PROFILE_GUIDANCE}}`: literary keeps the old list line;
  scholarly lists cited authors/figures, cited works (established Hebrew title), schools,
  institutions, places, and the author's key technical terms (base form, inflects), skipping
  words capitalized only by language rules. Terms are translated, names transliterated.
  NAMES header: terms inflect as Hebrew grammar requires.
- cross_chapter_qa: `{{PROFILE_CHECKS}}`; literary keeps the old list; scholarly checks term
  and concept consistency (inflection is not an inconsistency), definitions, cross-references,
  cited authors/works and canonical translations, abbreviations and notation, cited-author
  gender, attribution and stance, argument contradictions, authorial voice.
- book_notebook/07: the address/gender and running-jokes rules move into the literary
  guidance (literary prompt content unchanged); scholarly guidance adds cited-author gender,
  authorial voice and hedging, cross-reference rendering, and name kinds person/work/term.
- 04/06: the notebook description also names terms, definitions, cited works, notation.
- translation_profiles: one short sentence, the scholarly translator follows BOOK_NOTEBOOK
  decisions (terms, names, notation); version scholarly-prompts-v2@3 (literary unchanged).
  Kept short: tight test fixtures sit at the context edge; the LONG-DOCS planner fixture
  'qa-groups' moves from qa_context 12000 to 13000 so it still yields several QA groups.
- ui.html/help.html: copy states what the table, notebook and summary hold in a scholarly book.

Not changed: job structure, budgets, windows, call counts, parsing. Existing scholarly jobs pick
up the new prompts on their next calls (cache keys change for scholarly translation calls).
