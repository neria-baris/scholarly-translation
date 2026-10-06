# EXPORT-NIQQUD — merged EPUB blocks and niqqud leaking into the prose

Date: 2026-10-06. Base: ea5cbeb. Claude continuity, user-directed. Branch `fix/export-niqqud`.
Cause: completed Senlin Ascends job dccf6947 (50/50, $1.14), inspected offline.

Findings:
1. EPUB export: 103 units span 2436 EPUB blocks (whole-chapter units). The whole translation of a
   unit went into its first block; the other 2333 blocks kept their English text
   (`units_merged_multiple_blocks` + `missing_translation`). In 102/103 units the translation has
   exactly one line per source block.
2. Niqqud: prompt 09 encouraged niqqud; 127/145 name-table forms and 131/207 notebook entries are
   vocalized; NAMES says "use exactly these forms", so cross-chapter QA "corrected" plain prose to
   vocalized forms (5318 niqqud marks in 90/103 units).

User decision (2026-10-06): fix both; niqqud only in hard cases such as Wen/Woon (Jade City).

Component / owns:
- `export_epub.py`: a merged unit's translation is split into lines and placed one line per EPUB
  block when the counts match; otherwise lines are aligned proportionally to the source block
  lengths (several lines joined with a space, a block left without lines is emptied). No original
  -language text stays in a merged unit's blocks. Limitation `units_merged_multiple_blocks` is
  recorded only for the realigned (count mismatch) case, with kind detail. Single-block units
  unchanged.
- `name_table.py`: `plain_form` strips niqqud/cantillation; rendered NAMES lines show the plain
  form unless two entries' plain forms coincide (then the stored vocalized forms are kept). Stored
  table unchanged (old tables keep working; Senlin/Jade City get plain forms on the next call).
- prompts 09/07: Hebrew forms are written without niqqud, as in the running text; minimal niqqud
  only when two names would otherwise be written alike.
- `cross_chapter_qa.py`: an issue whose correction equals its span after stripping niqqud and adds
  niqqud is dropped (counted in dropped_issues); one that removes niqqud is kept. Output contract
  states that Hebrew prose is unvocalized and a niqqud-only difference is not an inconsistency.

Invariants: no new steps, calls, budgets or schema changes; prompt 10 file untouched (another
session edits it). Errors: none new. Side effects: cache keys of name-bearing prompts change.
Acceptance: unit tests for each point; full offline suite green; offline check on the Senlin job
data (export: no English left in merged blocks; NAMES render without niqqud).
Out of scope: removing niqqud already in finished translations (needs a user decision), register
guidance in the name-table pass (proposal pending), PDF export (already line-aware).
