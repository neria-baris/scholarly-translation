"""REVIEW-EFFECT salvage (contract: audit/contracts/review_effect.md).

Re-read the preserved provider answers of unit reviews and chapter QA that an older
parser rejected, with the current parser. No provider call happens here. A chapter
whose results change is reopened, so the normal resume recomputes its exceptions and
runs bounded corrections and focused rechecks for material issues (those are new
provider calls, started by the user's resume).
"""
from __future__ import annotations

import json
import time

from . import chapter_pipeline as cp
from . import review_qa as rq
from .model_adapter import TextGenerationResult
from .model_config import ModelConfiguration
from .source_reading import fingerprint

RECHECKABLE = ("needs_human", "failed")
_REVIEW_STAGE, _QA_STAGE = "semantic_reviewer-pass", "chapter_qa-pass"
_CHAPTER_EXCEPTIONS = {"qa_result_needs_human", "qa_note_retained", "ambiguous_qa_location"}
_PARSE_CAP = 4096   # the parser never looks at the call cap


def _text_at_review(record):
    """Hebrew as it was when reviewed (reviews and QA run before any correction)."""
    versions = record.get("target_versions") or []
    return versions[0]["text"] if versions else record["target_text"]


def _frozen(records):
    return [dict(r, target_text=_text_at_review(r)) for r in records]


def candidates(job):
    """Saved results that an older parser left for a human: (unit reviews, chapter QA)."""
    units = sum((r.get("review") or {}).get("status") in RECHECKABLE for r in job.get("units", []))
    qa = sum(item.get("status") in RECHECKABLE for item in job.get("chapter_qa_results", []))
    return units, qa


def recheck_saved_reviews(job, journal):
    """Mutates and returns a report; the caller persists ``job``."""
    configuration = ModelConfiguration.from_dict(job["settings"]["model_config"])
    profile = job["settings"]["profile"]
    by_id = {r["unit_id"]: r for r in job["units"]}
    chapter_of = {uid: index for index, ids in enumerate(job.get("chapter_groups") or []) for uid in ids}
    saved = {}
    for step in journal.job_steps(job["job_id"]):
        if step["stage"] in (_REVIEW_STAGE, _QA_STAGE) and step["raw_json"]:
            inputs = json.loads(step["dependencies_json"]).get("inputs", {})
            saved[(step["stage"], tuple(inputs.get("ids") or ()), inputs.get("targets"))] = step["identity"]

    def answer(stage, records):
        identity = saved.get((stage, tuple(r["unit_id"] for r in records),
                              fingerprint([r["target_text"] for r in records])))
        raw = journal.read_raw(identity) if identity else None
        if not raw or raw["status"] not in ("completed", "mock_placeholder"):
            return None
        return TextGenerationResult(**raw, duration_seconds=0)

    report = {"unit_reviews_recovered": 0, "chapter_qa_recovered": 0, "still_needs_human": 0,
              "no_saved_answer": 0, "dropped_issues": 0, "reopened_chapters": [], "units_to_correct": 0}
    changed = set()

    for record in job["units"]:
        if (record.get("review") or {}).get("status") not in RECHECKABLE:
            continue
        frozen = _frozen([record])
        result = answer(_REVIEW_STAGE, frozen)
        if result is None:
            report["no_saved_answer"] += 1
            continue
        request = cp._review_request("semantic_reviewer", frozen, configuration, profile, _PARSE_CAP, "all")
        new = rq.run_unit_review(request, generate=lambda *_, r=result: r)
        if new["status"] != "completed":
            report["still_needs_human"] += 1
            continue
        record["review"] = dict(new, rechecked_from_saved_answer=True)
        report["unit_reviews_recovered"] += 1
        report["dropped_issues"] += new.get("dropped_issues", 0)
        changed.add(chapter_of.get(record["unit_id"]))

    automation_qa = job.get("automation_qa", {})
    for item in job.get("chapter_qa_results", []):
        if item.get("status") not in RECHECKABLE or not item.get("unit_ids"):
            continue
        frozen = _frozen([by_id[uid] for uid in item["unit_ids"] if uid in by_id])
        result = answer(_QA_STAGE, frozen) if len(frozen) == len(item["unit_ids"]) else None
        if result is None:
            report["no_saved_answer"] += 1
            continue
        chapter = chapter_of.get(item["unit_ids"][0])
        request = cp._review_request("chapter_qa", frozen, configuration, profile, _PARSE_CAP,
                                     book_notebook=job.get("qa_notebooks", {}).get(str(chapter), ""))
        new = rq.run_chapter_qa(request, generate=lambda *_, r=result: r)
        if new["status"] != "completed":
            report["still_needs_human"] += 1
            continue
        new = dict(new, rechecked_from_saved_answer=True)
        for key, entry in list(automation_qa.items()):
            if key.startswith("%s:" % chapter) and entry.get("input_hash") == item.get("input_hash") \
                    and entry.get("status") in RECHECKABLE:
                automation_qa[key] = new
        unit_ids = item["unit_ids"]
        item.clear()
        item.update(new, unit_ids=unit_ids)
        report["chapter_qa_recovered"] += 1
        report["dropped_issues"] += new.get("dropped_issues", 0)
        changed.add(chapter)

    changed.discard(None)
    completion = job.setdefault("chapter_completion", {})
    for chapter in sorted(changed):
        number = chapter + 1
        job["exceptions"] = [e for e in job.get("exceptions", [])
                             if not (e.get("chapter") == number and e.get("type") in _CHAPTER_EXCEPTIONS)]
        if completion.get(str(chapter)):
            completion[str(chapter)] = False
            report["reopened_chapters"].append(number)
        records = [by_id[uid] for uid in job["chapter_groups"][chapter] if uid in by_id]
        results = [r.get("review") or {} for r in records] + [
            e for k, e in automation_qa.items() if k.startswith("%s:" % chapter)]
        to_correct = set()
        for result in results:
            for issue in result.get("issues", []):
                affected = cp._corrects_automatically(issue) and cp._issue_unit(issue, records)
                if affected and not affected.get("correction_done"):
                    to_correct.add(affected["unit_id"])
        report["units_to_correct"] += len(to_correct)
    if report["reopened_chapters"] and job.get("status") == "completed":
        job["status"], job["stage_label"] = "paused", "הופסק"
    job.setdefault("review_salvage", []).append(dict(report, at=time.time()))
    return report
