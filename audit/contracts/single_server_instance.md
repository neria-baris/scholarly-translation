# SINGLE-INSTANCE — one local server per data folder

User-directed, 2026-10-09. Evidence: a learning book showed "נעצר" with "המשך הכנה", and
the resume answered `already_running` ("ההכנה כבר רצה"). Two `scholarly_translation.web_ui`
processes were live (started 15:49 and 16:02, ports 54376 and 50756; random port per launch),
both on `outputs/learning`. Each kept its own in-memory `_running` set and auto-retry timers
while reading and overwriting the same `service.json`/session files, so the browser saw one
process's saved status and reached the other process's running worker.

- component: `web_ui.main`; new `claim_single_instance(folder)`, `running_instance_url(folder)`.
- owns: startup only. No change to learning, translation, budgets or provider calls.
- behaviour: the server takes an exclusive non-blocking OS lock on `outputs/web_ui.lock`
  (msvcrt on Windows, flock elsewhere) for its lifetime and records its address in
  `outputs/web_ui.url`. A second launch that cannot take the lock prints a console notice,
  opens the recorded address (only `http://127.0.0.1:<port>/` is accepted) and exits 0
  without binding a port or touching job state.
- invariants: the OS releases the lock when the process dies (no stale lock after a crash);
  the access token is never written to disk (it is served in the page, not in the URL).
- tests: `tests/test_single_instance.py` (second process refused while held, accepted after
  release; URL validation).
- not covered: servers already running before this change carry no lock; they must be closed
  by hand once.
