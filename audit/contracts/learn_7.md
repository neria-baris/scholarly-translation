# LEARN-7 — offline learning book export

User requests export for reading outside the website. Isolated feature checkout
only, no active translator/main/server/source credentials, merge or deploy.

Component: learning_export.py deterministic bytes builder. Input: validated
schema1 source, ordered plans, prepared chunks/recaps, pinned session/catalog
with effective vocabulary. Output: EPUB3 or standalone offline HTML bytes.
Public function export_learning_book(source, plans, prepared, session, catalog,
*, format='epub', include_meanings=True) -> bytes. No model/I/O/network/state.
Plans/chunks must cover each source unit exactly once, in source/chapter order;
all edits exact source slices through existing render_chunk context renderer.
Only complete ready/completed sessions export, never incomplete book. Preserve
every chapter/heading/paragraph and accepted substitution, no regeneration.
Chapter-end recap contains foreign labels, Hebrew meanings, actual grammar
explanations/examples/warnings from immutable prepared data. Escape all text;
reject XML-invalid control characters explicitly rather than silently drop.
Meanings optional: standard EPUB note-reference links on foreign words to
chapter-end notes; meanings never adjacent automatically. Reader support varies.
HTML uses the same links and chapter recap, script-free and self-contained.
Yiddish RTL and other foreign LTR; Hebrew book RTL. Format is a newly typeset
text export because learning source stores text rather than original ZIP/media.
Report this limitation visibly; no claim of original CSS/images preservation.
EPUB: first uncompressed mimetype, container.xml, OPF3 with identifier/title/he/
modified metadata, spine/toc/nav and local CSS, well-formed XHTML; safe generated
paths and no scripts/external assets. No silent length truncation or dependencies.
Errors: invalid_export_format, invalid_export_options, invalid_export_text,
invalid_export_coverage, book_not_ready, export_failed. Export neither marks
completion nor alters effort/history/cursor/grammar archive nor calls a model.

Ownership: scoped local export_builder agent owns ONLY learning_export.py and
tests/test_learning_export.py, shared frozen contract, no audit/Git/shared UI/
service edits or external model use. Sol owns service, guarded POST export,
download buttons/options in book list and reader, help/README/audit, integration.
Sol integrates sequentially and verifies; previous external Claude export-policy
rejection is not retried or worked around. Direct local implementation authorized.

Acceptance: EPUB ZIP/XML/spine/order/RTL, exact text incl long/Unicode/markup,
grammar/examples and optional note links, all five languages/dynamic definitions,
reject incomplete/missing/duplicated/reordered units/mismatched chunks and unsafe
controls/format/options; no state/model change. HTTP token/origin and binary
download/header, prepared integrity, legacy1/2. Browser actual EPUB download and
help/options, source preparation calls unchanged. Only affected export/service/
render/HTTP/library checks and JS syntax; no full-suite rerun or paid pilot.
No third-party linguistic critic. Reviewed clean isolated local commit/receipt,
feature push not attempted; main integration deferred during active translation.
