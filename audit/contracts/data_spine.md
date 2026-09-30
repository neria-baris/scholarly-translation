# Gate 1 data spine — current contract

- component: immutable source-linked records and JSON store; owns: scholarly_translation/records.py, store.py, __main__.py; provider errors own provider.py.
- input: document JSON schema 1 or 2, UTF-8 original source, validated parent IDs and half-open character spans.
- output: schema 2 carries document/page/region/segment IDs, source URI/language, stage ID/version, exact input-file SHA-256, status and warnings. No model-derived fields until a real model gate needs them.
- invariants: preserve source text, IDs and source locations across store round trips; derived output does not overwrite source; IDs use unambiguous encoding. Synthetic region identity is derived from page and source span, not a fabricated PDF coordinate.
- errors: invalid shapes/types/parents/spans/schema/hash raise RecordValidationError; invalid provider config returns nonzero without echoing arbitrary values or creating output.
- side_effects: explicit JSON/source files and append-only mock usage only; no network. Demo is a synthetic fixture generator, not an input-document processor.
- compatibility: existing schema 1 remains readable with legacy stage/hash warning; never silently claim a legacy hash was measured. Current demo writes schema 2. No destructive migration.
- acceptance: schema 1 reading preserves IDs/text and marks missing provenance; schema 2 round trip preserves all metadata; missing required schema 2 fields rejected; actual CLI Unicode and hash/source-span verification; config errors redact values.
- out_of_scope: PDF/OCR/bbox, segmentation revision history, runtime API, real scholarly quality. Each is extended only at its gate.
- owner: Sol direct completion after two historical Sonnet invocations; no extra model approval call.
