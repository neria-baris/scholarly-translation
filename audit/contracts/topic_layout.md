# Contract: TOPIC-LAYOUT (package and tests by topic/role)

Requested by the user 2026-10-12 ("learning, translation, budget ... all in one place;
split into folders by topics and roles"). Supersedes the unmerged 2026-10-06
`chore/package-layout` attempt, whose base is now far behind main; its grouping is
reused and extended (budget, comics).

Owns: every module under `scholarly_translation/` (moves + import/path rewrites only),
`tests/` placement, root `runtime_prompts/` (moves to `scholarly_translation/learning/prompts/`),
entry points in `run-ui.ps1`/`install.ps1`, and references in README/docs.

Layout: `scholarly_translation/{core,sources,models,budget,translate,review,export,comics,learning,ui}`;
`__main__.py`, `assets/`, `runtime_prompts/` stay at the package root. Prefixes that repeat
the folder are dropped (`learning_store` -> `learning/store`, `export_pdf` -> `export/pdf`,
`comic_pipeline` -> `comics/pipeline`, `model_config` -> `models/config`;
`learning_import` -> `learning/importer`). Tests mirror the topics; shared fixtures stay in `tests/`.

Entry points: `python -m scholarly_translation` (unchanged), web UI
`-m scholarly_translation.ui.web_ui`, comics `-m scholarly_translation.comics.pipeline`.

Behaviour: no logic change. Exception: the validator code fingerprint
(`translate/chapter_pipeline.py`) now hashes the whole package recursively, so saved answers
rejected by the old code are offered for re-check once (expected after any code change).

Acceptance: complete offline suite has the same pass count as the baseline on the same base;
`node --check` on ui.js/learning.js; no `scholarly_translation.<old_module>` reference left
outside audit history; web UI starts and serves its pages from the new location.

Integration: merge into main only when no translation/comic job and no web UI process runs
from the main checkout (lazy imports would break mid-run), and after the other owner's staged
`chapter_pipeline.py`/test change is committed (it is carried across the rename). No provider calls.
