# Gate 10 public corpus preparation — 2026-10-01

**Preparation complete; quality acceptance remains BLOCKED.** Six publisher PDFs supplied 72 distinct unapproved source candidates (24 each in English, French and Japanese) and 18 unapproved two-page context plans (six per language). Each source contributes 12 candidates. Metadata/hashes and observed checks are in `gate_10_corpus_summary.json`. Passage text, PDF bytes, page images, human references and judgments remain ignored.

The final local package is `outputs/gate10_sources/candidates-v6/review.html`, with `context_review.html`, `source_candidates.json`, `readings.json`, `context_plans.json`, and source PNGs. Original PDFs and primary schema-3 `document.json` files remain in the parent directory. Candidates use separate, unapproved cropped readings with exact text, offsets, hashes and geometry. They do not replace primary extraction or constitute resolved product source readings. Approval, approved word count, Hebrew reference and MQM fields are empty. The public evaluator rejects this preparation schema.

## Verification

- Six PDF signatures/parser opens and SHA-256 identities verified; article-level CC license evidence observed, including both French PDFs previously inaccessible. French philosophy license applies to text only; images remain local evidence. Japanese epistemology attribution retains the original authors and CC BY-SA condition.
- 62 cropped readings independently re-extracted from original bytes; 72 spans match exact slices/hashes, have distinct text hashes and do not overlap within a reading.
- 18 context plans match primary PDF/page IDs/text hashes, adjacent page numbers and available images; 108 image links resolve. Context windows overlap and are not extra independent source segments. No context experiment has run.
- Source visual checks: page 2 of both English PDFs and both Japanese PDFs; page 3 of French mathematics education; pages 3 and 4 of French philosophy. Mirrored French margins required wider geometry. These spot checks do not approve all passages or establish complete fidelity.
- Public `extract-pdf` produced the full 17-page English publishing document, PNGs and comparison HTML. Public `evaluate-pilot` refused the candidate schema with exit 1 and no report.
- The evaluator now rejects renamed duplicate PDF/reading/version/span identities while accepting adjacent boundaries. Focused 42 and full 295 tests pass; full suite 14.627 seconds. Test annotations remain synthetic.

## Reproduction

1. Retrieve the summary's public source URLs into an ignored local directory using the recorded local filenames. Verify each SHA-256 before use. Changed publisher bytes require a new acquisition record. Bound downloads to 20 MB, 30 seconds and no automatic retries.
2. Serialize the summary's `sources` array as local `source_metadata.json`. This inventory supplies attribution/license metadata, language, genre and PDF identities.
3. For each source run `python -B -m scholarly_translation extract-pdf LOCAL_PDF --language LANGUAGE --output ROOT/SOURCE_ID`. Preserve existing outputs or use a new directory.
4. With `pdfplumber==0.11.8`, run `python -B audit/support/prepare_gate10_candidates.py --root ROOT --output-name candidates`. No network/provider calls; output-directory creation is exclusive. The script verifies source hashes, counts, exact slices and nonoverlap. Use a new child output name for another attempt. This workspace uses ignored `outputs/tooling/python39/python.exe` because the old virtual environment's base is missing.
5. Compare retained reading hashes/source spans and open review indexes alongside original PDFs. Whole candidate-manifest hashes include acquisition metadata; reproducing from the summarized inventory can change those metadata fields. Source PDF and reading identities must match.

## Human review and remaining scope

An expert must confirm order, glyphs, notes, formulas, passage boundaries, source language and linguistic word counts, then produce approved Hebrew references. Japanese character and whitespace counts are not word counts. English/French whitespace counts are provisional. Blind translation judgments, correction times, the required second-reviewer subset, critic error examples/injections and a separately bounded real comparison remain.

The pool is not representative: all PDFs are digital; no genuine poor OCR or history-of-mathematics sample exists. Mathematics education does not establish technical mathematics coverage. Quoted English within Japanese prose, page-break fragments, hyphenation, note markers, tables and glyph/case mappings may need reconstruction decisions. Source approval must precede dependent decisions. No model winner, routing change, scholarly-quality pass or release acceptance is claimed.

Preparation used six of twelve retrieval attempts and one of four search batches. New paid/provider/Sonnet/Opus/Astra calls: zero; Sol usage not metered. Partial local packages remain superseded evidence; only `candidates-v6` is final.
