# LIBRARY-HTML-INSTALLER contract

Base: a83f845 (main == origin/main). User request 2026-10-05: a library of all
translated, available files; PDF items allow choosing a font for download and also
downloading an HTML version; installer must install Python 3.10+ itself when
missing and be brought up to date. The user explicitly authorized more than two
parallel builders for this gate (overrides the default two-writer limit for this
gate only). Three writers, disjoint ownership, sequential integration B1 -> B2 -> B3.

## B1 backend (owns: scholarly_translation/export_html.py (new),
## scholarly_translation/document_draft.py render_download only,
## scholarly_translation/web_ui.py, tests/test_library_html.py (new))

- `export_html.export_html(structure, translations, title, font_id=None) -> bytes`:
  self-contained UTF-8 HTML5, `<html lang="he" dir="rtl">`, every text value escaped,
  no `<script>`, no external URLs/resources. Same unit order/kinds (headings vs
  paragraphs) and translations mapping as the PDF export. Untranslated units fall
  back exactly as PDF export does. When `font_id` names an available bundled PDF
  font, embed that font file as a base64 `@font-face` and use it; unknown/unavailable
  font_id -> ExportError (no silent substitution). None -> system font stack.
- `render_download(job, kind, source_path=None, font_id=None)` accepts `kind="html"`
  for any completed job (pdf or epub source); other kinds keep the existing check.
- `POST /document-library` body `{}` -> `{"documents": [...]}` newest first, max 200,
  completed jobs only, each:
  `{"job_id", "filename", "source_kind": "pdf"|"epub", "completed_at": <unix float>,
    "unit_count": int, "font_id": str|null, "formats": ["pdf","html"]|["epub","html"]}`.
  Corrupt/unreadable job folders are skipped, never fatal. No source text or
  local paths in the response.
- `POST /document-download` gains optional `"format"`: absent or equal to the
  source kind -> unchanged behavior; `"html"` -> `text/html; charset=utf-8`,
  attachment filename `<stem>.he.html`, `font_id` optional and validated against
  available fonts; any other value -> 400. Same token/origin checks as today.
- Offline tests only, no provider calls.

## B2 library UI (owns: scholarly_translation/ui.html, ui.js, ui.css,
## tests/test_library_ui.py (new))

- Header button "הספרייה" and a start-panel text button open `#library-panel`
  (added to the show() panel set). Panel lists /document-library entries: file name,
  kind badge, date; empty state text; back button to the start panel.
- Clicking an entry expands it. PDF: font `<select>` (available fonts, default the
  job's font_id), "הורדת PDF" (format pdf + font_id), "הורדת HTML" (format html +
  same font_id). EPUB: "הורדת EPUB", "הורדת HTML". Optional "פתיחה" re-opens the
  job in the existing result panel via poll(job_id).
- Download filenames `<stem>.he.pdf|epub|html`. Errors shown inline. RTL, keyboard
  accessible, matches the gold/parchment theme, no new external resources.
- Existing translate/result/review flows unchanged.

## B3 installer (owns: install.ps1, Install.bat, run-ui.ps1, INSTALL_HE.md,
## tests/test_installer_scripts.py (new))

- If no Python >= 3.10 is found: install it per-user without admin — winget
  (`Python.Python.3.12` or 3.10+) when available, else download the official
  python.org amd64 installer over HTTPS and run it quietly with
  `InstallAllUsers=0 PrependPath=1 Include_launcher=1`; refresh PATH in-process
  and re-detect (also probe the standard per-user install dirs). Show progress in
  the window; clear failure message + Retry otherwise.
- Find-Python probes `py -3.13/-3.12/-3.11/-3.10` explicitly before bare `py`/`python`
  (a default `python` may be 3.9), and returns a full invocation that works.
- Bring the rest up to date: verify list matches requirements.txt imports, upgrade
  pip in the venv, run-ui.ps1 candidates must not prefer a Python < 3.10 path,
  INSTALL_HE.md describes the automatic Python step. No admin rights, no secrets.
- Tests are static/offline (script text checks); never actually install anything.
