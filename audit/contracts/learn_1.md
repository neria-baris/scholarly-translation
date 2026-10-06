# LEARN-1 parallel component contracts
Scope exception: user explicitly authorized >2 agents for LEARN; three writers.
Base: verified LEARN-0 commit (recorded in dispatch/audit). Three isolated worktrees,
same bootstrap; conductor integration order A -> B -> C, then service/UI sequential.
No recursive delegation. Claude Code Sonnet primary; Read/Write/Edit only, no paid
runtime calls. Initial invocations cap $2 each; shared measured list-price cap $10
including scoped fixes. Subscription actual charge unknown, bounded call count.

A owns learning_catalog.py, learning_planner.py, learning_state.py, learning_store.py,
learning_data/fr_common_v1.json, tests/test_learning_{state,planner,store}.py.
B owns learning_import.py, tests/test_learning_import.py.
C owns learning_generation.py, learning_render.py,
runtime_prompts/08_learning_generation.md, tests/test_learning_{generation,render}.py.
Each reads its numbered builder prompt; frozen learning_contracts.py read-only.
Conductor owns shared contracts, audit, integration, tests/test_learning_integration.py,
all Git and existing-file edits. Builders report mismatches; never silently modify API.

Frozen A API: load_catalog(language='fr'); plan_book(source,learner,catalog,policy_version=...);
replan_chunk(plan,projected_learner,catalog); apply_completion(learner,session,chunks,
recaps,completion_id,completed_at) as keyword completion metadata.
LearningStore(root) methods: save_source(source), get_source(book_id), get_learner(language='fr'),
save_learner(learner), create_session(source,learner) -> session,
get_session(session_id), list_sessions(language=None), save_prepared(session_id,chunks,recaps),
get_prepared(session_id)->{chunks,recaps}, complete_book(session_id,expected_prepared_hash,
completion_id)->receipt, save_cursor(session_id,cursor), update_session(session).
Store aggregates global learner/session/receipt atomically; no source/path credentials.
Import is separate from create_session: queued source imports don't claim active slot.
create_session acquires slot. Ready/preparing/paused/failed maintain it for safe resume.
Methods operate on defensive copies; source immutable. save_prepared sets chunk_ids,
prepared_hash and ready after full coverage/recaps check. Complete takes ready only.

B API: import_hebrew_epub(path_or_bytes,book_id=...,title=None),
import_translation_job(snapshot,book_id=...). Existing job has structure plus units
with unit_id/source_text/target_text/status and revision. Use current target_text,
reject missing targets. Reuse document_draft.extract_structure/chapter_groups.
Freeze maximum source unit size 2400: split long paragraphs deterministically on
whitespace with stable child unit IDs; headings stay intact. Preserve source links
in origin and immutable normalized text; no changes to existing extraction modules.

C API: build_request(plan,catalog,context='')->(prompt_string,input_hash);
parse_response(raw,plan,catalog,input_hash,provider='openai',model='gpt-6-luna')
->(GeneratedChunk,recap_proposals). raw is text; generated language explicit.
generate_chunk(plan,catalog,context='',controlled_generate=callable)->same pair;
callable(prompt,input_hash) returns TextGenerationResult or raw string, called once;
provider/model defaults Luna. Sol injects controlled dispatch/replay.
build_chapter_recap(chapter_id,accepted_chunks,proposed_entries)->ChapterRecap;
proposed_entries is a list of {chunk_id,recap:<model recap object>}.
render_chunk(source_units,generated_chunk,support_mode)->safe HTML string.
content_hash fingerprints edits/coverage; chapter hashes track generated content.
No direct provider, new cache, critic, keeper or extra recap call.

Acceptance per builder prompts with fakes/synthetic sources, plus end-to-end continuity
after integration. Invalid data -> LearningError code, never learner advancement.
Out of scope: main app deployment, paid pilot, language mastery/quality claim.
