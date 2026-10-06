# LEARN-4 user correction: cumulative reading and visible vocabulary

User explicitly rejects automatic beside-word glosses. Foreign words are understood
from context or chapter learning. New books default to support_mode=context; old
stored modes remain readable but server reader renders context only. Glosses are
available in chapter recaps and vocabulary lists, not appended to reading text.
All effort levels retain numerical share maxima, independent of gloss mode.

Conductor owns contracts/schema/service/store/planner/generation/render/Git/audit.
Two scoped isolated Claude Sonnet builders, cap2 USD each; cumulative shared LEARN
cap10 USD (prior4.0853064). Read/Write/Edit only, no paid runtime, Bash/network,
delegation or Git. Integrate catalog F then UI E after conductor backend checks.

F owns only learning_data/fr_common_v2.json and tests/test_learning_catalog_v2.py.
Catalog version fr-common@2, same schema1. Preserve every v1 item and ID verbatim
(levels may change support_mode to context). Extend to include every French form
in existing european_500.json with original Hebrew meaning labels and exact allowed
forms; use stable fr-freq-NNN IDs for new forms, priority_tier=source rank. Do not
duplicate an existing approved form; keep existing IDs/senses. No universal usefulness
or expert-curation claim. Provenance distinguishes frequency forms from authored,
model-assisted Hebrew labels; CC-BY-SA4 attribution retained. No fixed500 catalog
ceiling.500 is initial milestone, not lifelong limit. Other4 catalogs unchanged.

E owns only learning.html/.js/.css and tests/test_learning_ui.py. No old translation
UI edits necessary. Remove inline gloss labeling and interactions from reading UI;
all effort levels are context-based. Add usable progress/vocabulary panel (filter by
foreign or Hebrew text) with completed-book items and separately current-read items.
Never label prepared-but-unread material learned or mastery. Existing imports,
budget, polling, reader navigation/completion/token/key controls preserved.

Additive /learning/state progress contract, all values server generated:
progress={initial_word_goal:500,catalog_word_count:int,completed_word_count:int,
 completed_structure_count:int,completed_items:[{item_id,kind,foreign,hebrew,encounters,
 last_book_title}],active_book:null|{book_id,title,chapter_index:null|int,
 chapter_count:int,read_items:[same fields],prepared_chunks:int,total_chunks:int}}.
active_book.read_items includes accepted occurrences in chapters visited through
furthest recorded cursor, counts are encounters in this book only. Rows in both
sections may overlap; one is saved cross-book history, other is current-book reading.
No new endpoint or client-side source splicing. Full catalog/500 raw lists remain
separate from learned list. Display500 as first milestone, progress continues after.

Planner: include ALL relevant already-exposed items, independent of new-item quota,
alongside bounded new items; no arbitrary review cap. Persist projected accepted
exposures per actual edit. Known repeated meanings receive increasing replacement
targets (most suitable occurrences), within effort caps and semantic ambiguity.
No deterministic blanket replacement of homonyms. Plan optional review_targets
metadata and prompt version2 express this; source/dispatch hashes include changes.
Effort-policy2 share and grammar quotas apply to NEW material only; known words
do not spend these quotas. Total foreign density may grow across chapters/books.
Policy1 remains total-share limited for already-pinned legacy preparations.

Versioning: keep v1 catalog available for pinned old sessions and completion;
upgrade inactive learner to latest catalog preserving IDs/history/level. Catalog
extensions require retained IDs and meanings; no500 validation cap. Do not mutate
active main app, outputs/keys, server or in-flight books. Conductor preview restart
may affect only conductor-owned synthetic preview. No linguistic review model.

Acceptance: new/legacy state compatibility; all relevant known words in later plans
even when review set exceeds new quota; increasing recurrence targets;500 French
forms present; >500 catalog fixture accepted/planned/history retained; current-read
versus durable list and cursor accuracy; no inline gloss in reader; browser filtering
and continued explicit completion; appropriate learning tests plus legacy regression.
