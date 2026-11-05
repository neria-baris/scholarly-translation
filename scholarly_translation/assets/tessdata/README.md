# Bundled Tesseract language models

`eng`, `fra` and `jpn` from tesseract-ocr/tessdata_fast (Apache-2.0, `LICENSE`), pinned in
`sources.json` with SHA-256 hashes. Used by `scanned_ocr.py` with the bundled engine
(`../tesseract/`), and with a system Tesseract installation whenever it lacks the
requested language. No download happens at runtime.
