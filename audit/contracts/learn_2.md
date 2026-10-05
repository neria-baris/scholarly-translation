# LEARN-2 orchestration and HTTP contract
Owns learning_service.py, new HTTP routes and integration tests. No changes to
translation processing. Lazy service uses outputs/learning; isolated preview has
its own checkout/root/port. Source records contain Hebrew only and remain immutable.

Input: validated LEARN-1 source/catalog/state, memory-only OpenAI credential,
explicit positive finite USD cap for preparation. French catalog initially only.
Output: queued sources, learner/session summaries, chapter safe HTML and recap,
explicit completion receipt. Error response uses bounded stable LearningError code.
Credentials never persist or appear in responses. One active book per language.

Reuse existing ControlStore, WorkJournal and chapter_pipeline._controlled as a
single translator dispatch primitive, without invoking translation orchestration,
keeper, review or QA. Frozen source/plan/config determine replay identity. Validate
with C before journal completion; persist current plan before dispatch. Persist
accepted chunks/proposals between calls; restart becomes paused, explicit resume.
Unknown dispatch cannot automatically resend. Pause takes effect before next call.
Completion checks prepared hash and commits learner state atomically through A.

HTTP uses existing token/origin guard. Upload raw EPUB separately; library handoff
gets a coherent read-only DocumentJobs snapshot. Never import a client filesystem
path or a client supplied translation snapshot. Learning routes return no keys.
Reader cursor is persisted independently of learner advancement. State changes
only through explicit complete. Prepared book uses the same support/effort in all
chunks; next book inherits committed state. In-book accepted coverage projects
selection only, never commits mastery. No automatic provider calls on app start.

Acceptance: synthetic end-to-end import/prepare/read/complete/next-book,
idempotency, resume with zero extra calls, capped single-role generation, HTML
escaping, HTTP token refusal and legacy routes. Out of scope: paid pilot, language
quality acceptance, main merge/deploy while active translation runs.
