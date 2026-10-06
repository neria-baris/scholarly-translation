# Bundled Tesseract language models

`fra` and `jpn` from tesseract-ocr/tessdata_fast (Apache-2.0, `LICENSE`), pinned in
`sources.json` with SHA-256 hashes. Used by `scanned_ocr.py` only when the
system Tesseract installation lacks the requested language; English uses the
system `eng` model. No download happens at runtime.
