# SCHOLARLY-MATH — profile-aware notebook, academic triggers, mathematics

Date: 2026-10-06. Base: d475a2b. User request: carry the literary notebook work
over to the scholarly profile, add academic risk triggers, support mathematics in
PDF export and, where feasible, in reading.

Findings that motivate it:
- The book notebook already runs for every automation job, but its keeper prompt
  and suggested tags are literary (plot, subplot, secret, wordplay, character).
- Unit-review risk triggers are only negation/quantifier/modality (en/fr) plus
  literary ones; they decide whether a unit is reviewed in "checked" mode but are
  not shown to the reviewer.
- Bundled Hebrew PDF fonts lack 29-43 of 43 common math/Greek glyphs, so exported
  formulas show empty boxes.
- EPUB MathML (<math>) is flattened on reading and deleted on export.
- A formula-only unit (e.g. "E = mc²") would be rejected as "not Hebrew".

Owns:
1. Keeper prompt and suggested tags depend on profile. Scholarly: story_so_far is
   the "argument so far" (thesis, argument steps, defined concepts and usage,
   distinctions, interlocutors' positions, open questions) and terminology rules
   (one rendering per term, original term in parentheses, established Hebrew
   translations of quoted canonical works, transliteration of names/titles,
   fixed interpretation of ambiguous terms). JSON schema unchanged.
2. Academic risk triggers (scholarly profile; en/fr word lists plus
   language-independent patterns): citation, number_unit, formula_math,
   definition, contrast_concession, conditional_causal, hedge,
   comparative_degree, original_term, footnote_marker. The unit reviewer prompt
   receives the triggered types as focus hints.
3. Mathematics:
   - has_translatable_words treats math tokens (operators, Greek, single
     letters, sub/superscripts) as non-lexical, so formula-only units pass
     through and skip review.
   - Formula node detection accepts Unicode math, Greek and sub/superscripts.
   - PDF export: per-character font fallback Hebrew font -> Noto Sans Math ->
     Noto Sans (both SIL OFL 1.1, pinned Google Fonts commit, hashes recorded).
     Formula nodes are drawn left-to-right.
   - HTML export: formula blocks LTR; math font stack.
   - EPUB: each inline <math> becomes a protected placeholder in the source
     text; the translator must keep placeholders; export re-inserts the original
     MathML elements in order. Missing/duplicated placeholders fail validation
     (no silent loss).
   - Reading math from PDFs stays text-based (no image/LaTeX OCR); documented.
4. Glossary vs notebook: the simple UI has no glossary editor, so every job's
   approved glossary is empty and the notebook is the only terminology memory.
   The BOOK_NOTEBOOK header (sent only when a notebook is present, both
   profiles) now says: follow unless the source contradicts, note departures,
   approved terminology overrides. Style profiles are unchanged (adding the rule
   there pushed tight-context planner fixtures over their limits).

Invariants: no provider calls in tests; completed steps never resent; prompts
change only for not-yet-run steps; literary behaviour unchanged except shared
fixes; font licences bundled with provenance.
Out of scope: OCR of formula images, LaTeX conversion, MathML rendering inside
PDF (MathML in PDF export falls back to its text alternative), Gate10 quality
claims.
Acceptance: targeted tests per item; glyph coverage test; EPUB MathML round
trip test; relevant suites green.
