# SCANNED-OCR — scanned PDFs in the simple flow, with model vision review

Date: 2026-10-06. Base: 367d07f. User request: translate scanned books; use the
translator model (Luna, confirmed by the user to read images) as an external
reviewer of OCR, including mathematics.

Before: the simple flow rejected PDFs without embedded text ("נדרש OCR"); local
Tesseract OCR existed only as a separate CLI stage; Tesseract had only `eng`.

Owns:
1. `scanned_ocr.py`: find pages without usable digital text; run local Tesseract
   on them (parallel, per-page cache in the job folder, bundled pinned `fra`/`jpn`
   tessdata_fast models used when the system lacks the language); assemble a
   standard OCR bundle.
2. Vision review (setting `ocr_review`: "vision" default for configured models,
   or "off"): per OCR page, one controlled call (journal + budget, translator
   role) with the page image and the Tesseract text; the model returns the exact
   page text, formulas in Unicode linear form inside ⟦ ⟧. Validation: non-empty,
   not Hebrew (no translation), fences stripped. The corrected text is aligned
   to Tesseract words: matching words keep their boxes/confidence, changed words
   get the page box with confidence 0. Pages whose texts disagree strongly get
   warning `ocr_vision_disagreement` and a job exception. Bundle stage becomes
   `local-ocr+vision@1` with provenance `vision_model` (validators extended).
3. Model adapters accept an `ImagePrompt` (text + one PNG): OpenAI Responses
   `input_image`, Anthropic `image` block, OpenAI-compatible `image_url`.
   Reservations add a conservative per-image token allowance.
4. Job flow: scanned pages are OCRed (and reviewed) in the "reading" stage before
   planning; OCR jobs fix `max_calls` from the page count before the first call;
   resume of a job interrupted before its structure existed reruns the reading
   stage (cached OCR, journaled vision answers: no resend).
5. Preview of a scanned PDF: page count, OCR note and vision-review estimate;
   translation cost is planned after OCR (over-budget -> existing decision box).
6. Decision option `skip_ocr_review` (continue with Tesseract text only) when a
   vision call fails.
7. UI setting and help text.

Invariants: OCR text stays source evidence (never translated by the reviewer);
no silent loss (disagreement is surfaced); completed vision answers are never
resent; digital pages are untouched; EPUB unaffected.
Out of scope: layout analysis beyond Tesseract, handwriting, image/figure OCR,
LaTeX output, scanned EPUB.
Acceptance: offline tests with a generated scanned PDF (real Tesseract when
installed), fake vision adapter, alignment/validator tests, resume without
resend, preview, decision option; relevant suites green.
