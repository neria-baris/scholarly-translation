# LEARN-3 UI builder contract
Owns only scholarly_translation/learning.html, learning.css, learning.js,
small additions to ui.html/ui.js/ui.css (learning-window link and library handoff),
tests/test_learning_ui.py. Existing translator flow/polling/panels stay unchanged.
Read numbered05 prompt and this concrete contract, not obsolete field guesses.
No server/schema/audit/Git edits, no provider/network calls, no delegation.
Use unittest, not pytest; no new dependencies/framework/remote assets.

Separate RTL page /learning, __CONFIG__ token injection exactly like ui.html.
Header link opens new tab target=_blank rel=noopener; library completed book
action opens /learning?job_id=ENCODED; learning page explicitly imports server-side
snapshot via /learning/import-translation once and removes query with history API.
Do not import snapshot data/path supplied by browser. Existing book flow unchanged.

All POST JSON with X-UI-Token. Error maps bounded response.code to Hebrew message.
API:
- /learning/state {} -> books[{book_id,title,origin}], sessions (schema learn_1),
  learner (schema), jobs{session_id:{accepted_chunks,total_chunks,error_code,status}},
  languages[{id,available}], levels (numeric limits), model=gpt-6-luna.
- /learning/upload-epub?name=ENCODED raw file bytes <=25MB -> book summary;
  Hebrew EPUB only. Selection/drop accessible, input accept .epub.
- /learning/import-translation {job_id} -> book summary.
- /learning/effort {level_id:'1'/'2'/'3'} -> learner; disabled while active_book_id.
- /model-keys {keys:{openai:VALUE}} -> existing memory-only save response;
  clear input afterwards, never browser storage or URL. Learning key is optional
  UI section, labeled stays in memory until this server closes.
- /learning/prepare {book_id,budget_usd:positive finite<=100} -> session, async;
  explicit action only. Cap must be entered, no auto-paid action on upload/visit.
- /learning/pause {session_id}; stops before next chunk, current call may finish.
- /learning/resume {session_id,budget_usd} -> session; re-supply key after restart,
  budget used only in pre-dispatch orphan recovery; ordinary cap stays unchanged.
- /learning/abandon {session_id} -> session; stopped (paused/failed/imported) only,
  releases active slot without completion/exposures. jobs.status='abandoned',
  failed session old revision cannot resume. UI explains before this action.
- /learning/read {session_id,chapter_index:0-based} -> session,title,chapter_title,
  chapter_index,chapter_count,html (safe server fragment),recap,items{id:{lemma,sense_he}}.
  Recap vocabulary[{item_id,gloss_he}], grammar[{item_id,explanation_he,examples}],
  warnings list. Display all through textContent/escaping; only html is trusted
  server renderer. Fragment foreign occurrences are accessible for gloss clicks.
- /learning/cursor {session_id,chapter_index}; persist chapter position, no progress.
- /learning/complete {session_id,prepared_hash:from reader.session,completion_id:
  one stable client ID per confirmation attempt} -> receipt; explicit 'קראתי'.
  Refresh on completion; show accumulated introduced items count, never mastery.
- GET /learning/wordlist?language=fr/de/es/yi/it ->500-form list; links in new tab.

First working curriculum French small starter; other four lists available but
their learning languages disabled with clear note. Levels1:10%+inline gloss,
2:20%+click,3:30%+short phrases. Show maxima, not promises. Whole-sentence/paragraph
levels unavailable. Book status/progress, read cursor, previous/next chapter,
end-of-chapter grammar+vocabulary recap, sparse coverage note when empty. Source
and learner history separate. Mobile readable typography, keyboard/labels/live
status, right-to-left book with target language bidi isolation. Minimal UI.

Acceptance: static wiring/accessibility/token/key nonstorage tests, syntax Node
by conductor, existing library tests, isolated browser import/read/complete flow.
No paid pilot, critic, implementation jargon in product, active main edits/deploy.
