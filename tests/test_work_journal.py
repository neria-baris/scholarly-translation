import tempfile
import unittest
from pathlib import Path

from scholarly_translation.work_journal import (
    StepCorruptionError, WorkJournal, WorkJournalError, step_identity,
)

RAW_OK = {"status": "completed", "text": "hello", "token_usage": {"input": 1, "output": 1},
          "observed_model": "m1", "error": None}


class WorkJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "journal.sqlite3"

    def _identity(self, prompt_text="prompt", deps=("u1",)):
        return step_identity(job_id="job1", role="translator", stage="chapter-translate",
                             model="m1", call_output_cap=100, prompt_text=prompt_text, dependencies=list(deps))

    def test_plan_step_is_idempotent(self):
        with WorkJournal(self.path) as journal:
            identity = self._identity()
            row1 = journal.plan_step(identity, job_id="job1", role="translator", stage="chapter-translate",
                                     model="m1", call_output_cap=100, prompt_text="prompt", dependencies=["u1"])
            journal.mark_dispatched(identity)
            row2 = journal.plan_step(identity, job_id="job1", role="translator", stage="chapter-translate",
                                     model="m1", call_output_cap=100, prompt_text="prompt", dependencies=["u1"])
            self.assertEqual(row1["status"], "planned")
            self.assertEqual(row2["status"], "dispatched")  # unchanged by re-planning, not reset

    def test_full_transition_sequence(self):
        with WorkJournal(self.path) as journal:
            identity = self._identity()
            journal.plan_step(identity, job_id="job1", role="translator", stage="chapter-translate",
                              model="m1", call_output_cap=100, prompt_text="prompt", dependencies=["u1"])
            self.assertEqual(journal.status_of(identity), "planned")
            journal.mark_dispatched(identity)
            self.assertEqual(journal.status_of(identity), "dispatched")
            journal.mark_received(identity, RAW_OK)
            self.assertEqual(journal.status_of(identity), "received")
            self.assertEqual(journal.read_raw(identity), RAW_OK)
            journal.mark_validated(identity, {"u1": "parsed"})
            self.assertEqual(journal.read_validated(identity), {"u1": "parsed"})
            journal.mark_completed(identity)
            self.assertEqual(journal.status_of(identity), "completed")

    def test_cannot_receive_before_dispatch(self):
        with WorkJournal(self.path) as journal:
            identity = self._identity()
            journal.plan_step(identity, job_id="job1", role="translator", stage="chapter-translate",
                              model="m1", call_output_cap=100, prompt_text="prompt", dependencies=["u1"])
            with self.assertRaises(WorkJournalError):
                journal.mark_received(identity, RAW_OK)

    def test_unknown_outcome_blocks_further_transitions(self):
        with WorkJournal(self.path) as journal:
            identity = self._identity()
            journal.plan_step(identity, job_id="job1", role="translator", stage="chapter-translate",
                              model="m1", call_output_cap=100, prompt_text="prompt", dependencies=["u1"])
            journal.mark_dispatched(identity)
            journal.mark_unknown(identity)
            self.assertEqual(journal.status_of(identity), "unknown")
            # An unknown dispatch may still later receive a (late/duplicate)
            # response, but the identity never silently resets to re-dispatch.
            with self.assertRaises(WorkJournalError):
                journal.mark_dispatched(identity)

    def test_resume_reparses_received_raw_with_zero_additional_provider_calls(self):
        identity = self._identity()
        with WorkJournal(self.path) as journal:
            journal.plan_step(identity, job_id="job1", role="translator", stage="chapter-translate",
                              model="m1", call_output_cap=100, prompt_text="prompt", dependencies=["u1"])
            journal.mark_dispatched(identity)
            journal.mark_received(identity, RAW_OK)
        # Simulate a process restart: a fresh WorkJournal instance over the
        # same durable file finds the already-received raw response.
        with WorkJournal(self.path) as journal:
            raw = journal.read_raw(identity)
            self.assertEqual(raw, RAW_OK)
            journal.mark_validated(identity, {"u1": "parsed-on-resume"})
            journal.mark_completed(identity)
            self.assertEqual(journal.status_of(identity), "completed")

    def test_distinct_dependencies_are_distinct_identities(self):
        id_a = self._identity(deps=("u1",))
        id_b = self._identity(deps=("u1", "u2"))
        self.assertNotEqual(id_a, id_b)

    def test_pause_resume_flags(self):
        with WorkJournal(self.path) as journal:
            self.assertFalse(journal.is_paused("job1"))
            journal.pause("job1")
            self.assertTrue(journal.is_paused("job1"))
            journal.resume("job1")
            self.assertFalse(journal.is_paused("job1"))

    def test_opening_empty_file_is_corruption(self):
        self.path.write_bytes(b"")
        with self.assertRaises(StepCorruptionError):
            WorkJournal(self.path)

    def test_invalid_raw_shape_rejected(self):
        with WorkJournal(self.path) as journal:
            identity = self._identity()
            journal.plan_step(identity, job_id="job1", role="translator", stage="chapter-translate",
                              model="m1", call_output_cap=100, prompt_text="prompt", dependencies=["u1"])
            journal.mark_dispatched(identity)
            with self.assertRaises(WorkJournalError):
                journal.mark_received(identity, {"status": "completed"})


if __name__ == "__main__":
    unittest.main()
