"""User-decided blocks for automation jobs (contract: audit/contracts/user_decided_blocks.md).

``diagnose`` explains why a job cannot continue and which choices the user has;
``apply_decision`` records the user's explicit choice in the control store, the
work journal and the job settings. Neither ever sends a provider request: the
normal resume is the only sender, and automatic stops stay automatic.
"""
from __future__ import annotations

import json
import math
import time

from . import chapter_pipeline
from .chapter_pipeline import DEFAULT_STORY_WORDS, KEEPER_MAX_OUTPUT_TOKENS, keeper_output_cap, resolve_keeper_role
from .model_config import ModelConfiguration
from .runtime_controls import RuntimeControlsError

_BUDGET_PHRASES = ("list-price reservation limit", "more reserved funds", "exceed the document budget")
_NOTEBOOK_STAGE = "chapter-notebook"
_NAME_TABLE_STAGE = "name-table"
_CROSS_QA_STAGE = "cross-chapter-qa"
_VISION_STAGE = "ocr-vision"
_SKIP_VISION_LABEL = "להמשיך בלי בדיקת המודל (טקסט ה־OCR המקומי בלבד)"
SHORT_STORY_WORDS = 300
# User rule (2026-10-06): an unknown-outcome call whose whole held charge is below
# this is accepted and retried without asking; at or above it the user decides.
AUTO_ACCEPT_BELOW_USD = 1.0
# A call that keeps ending unknown stops for the user after this many automatic
# retries in a row (a row breaks once any other call is reserved in between).
AUTO_ACCEPT_MAX_STREAK = 3


class BlockDecisionError(ValueError):
    pass


def _option(option_id, label, value=None, input_kind=None):
    option = {"id": option_id, "label": label}
    if value is not None:
        option["value"] = value
    if input_kind is not None:
        option["input"] = input_kind
    return option


def _usd(value):
    return "$%.4f" % value


def _keeper_limit(job):
    configuration = ModelConfiguration.from_dict(job["settings"]["model_config"])
    selection, _ = configuration.resolve(resolve_keeper_role(configuration))
    return (keeper_output_cap(selection, job["settings"].get("keeper_output_cap")),
            keeper_output_cap(selection, 10 ** 9))


def _unresolved_anomaly(status):
    resumed = max([e["event_id"] for e in status["events"] if e["outcome"] == "user_resumed"] or [0])
    return any(e["outcome"] == "anomaly_over_cap" and e["event_id"] > resumed for e in status["events"])


def _budget_options(status):
    hard = status["hard_list_usd"]
    suggested = [round(hard * factor, 2) for factor in (1.25, 1.5, 2.0)]
    return ([_option("raise_budget", "העלאת התקציב ל־$%.2f" % value, value) for value in suggested]
            + [_option("raise_budget", "תקציב אחר (בדולרים)", input_kind="usd")])


def diagnose(job, store, journal):
    """Return None when nothing blocks the job, else a dict with ``kind``,
    Hebrew ``message``, ``options`` and ``details``."""
    if not job.get("settings", {}).get("automation") or job.get("status") == "completed":
        return None
    job_id = job["job_id"]
    error = job.get("error") or ""
    try:
        status = store.status(job_id)
    except RuntimeControlsError:
        # No call was reserved yet (e.g. the plan exceeded the budget before sending).
        if any(phrase in error for phrase in _BUDGET_PHRASES):
            budget = job["settings"]["budget_usd"]
            return {"kind": "budget_limit", "details": {"spent_usd": 0.0, "budget_usd": budget},
                    "message": "התקציב שהוגדר (%s) אינו מספיק לתכנון העבודה." % _usd(budget),
                    "options": _budget_options({"hard_list_usd": budget})}
        return None
    steps = journal.job_steps(job_id)
    stuck = [s for s in steps if s["status"] in ("failed", "unknown", "dispatched")]
    # A failed keeper step never blocks the job (the keeper degrades to "no update").
    blocking = [s for s in stuck if not (s["status"] == "failed" and (
        s["stage"] == _NOTEBOOK_STAGE
        or s["stage"] == _VISION_STAGE and job["settings"].get("ocr_review") == "off"))]
    details = {"spent_usd": status["list_estimated_spent_usd"], "budget_usd": status["hard_list_usd"],
               "calls": status["attempted_calls"], "max_calls": status["max_calls"]}
    uncertain = store.uncertain_calls(job_id)
    if uncertain:
        call = uncertain[0]
        details["call"] = call
        notebook = call["stage"] == _NOTEBOOK_STAGE
        vision = [_option("skip_ocr_review", _SKIP_VISION_LABEL)] if call["stage"] == _VISION_STAGE else []
        if call["known_usd"] is None:
            return {"kind": "unknown_outcome", "details": details,
                    "message": "קריאה לספק הסתיימה בלי מידע ודאי על השימוש (למשל ניתוק). ייתכן שהספק חייב עליה. "
                               "אפשר לרשום את מלוא הסכום השמור (%s) ולנסות שוב; ייתכן חיוב כפול." % _usd(call["held_usd"]),
                    "options": [_option("accept_worst_case_and_retry", "לרשום %s ולנסות שוב" % _usd(call["held_usd"]))]
                               + ([_option("skip_notebook_chapter", "לרשום ולדלג על עדכון המחברת בפרק זה")] if notebook else [])
                               + vision}
        if notebook and call["provider_outcome"] == "failed_truncated":
            current, maximum = _keeper_limit(job)
            step = next((s for s in stuck if s["stage"] == _NOTEBOOK_STAGE), None)
            used = step["call_output_cap"] if step else current
            raised = min(maximum, max(used * 2, KEEPER_MAX_OUTPUT_TOKENS))
            options = []
            if raised > used:
                options.append(_option("raise_notebook_cap", "להגדיל את חלון הפלט של המחברת ל־%d טוקנים" % raised, raised))
            words = job["settings"].get("notebook_story_words") or DEFAULT_STORY_WORDS
            if words is None or words > SHORT_STORY_WORDS:
                options.append(_option("shorten_notebook", "לקצר את סיכום הספר ל־%d מילים לכל היותר" % SHORT_STORY_WORDS,
                                       SHORT_STORY_WORDS))
            options.append(_option("skip_notebook_chapter", "לדלג על עדכון המחברת בפרק זה"))
            return {"kind": "notebook_truncated", "details": dict(details, output_cap=used),
                    "message": "מחברת הספר הגיעה לגודל המרבי: תשובת המודל נקטעה אחרי %d טוקנים. "
                               "הקריאה עלתה %s לפי המחירון. בחרו איך להמשיך." % (used, _usd(call["known_usd"])),
                    "options": options}
        return {"kind": "failed_call", "details": details,
                "message": "תשובת הספק נכשלה או נקטעה (%s). השימוש ידוע: %s לפי המחירון. "
                           "אפשר לרשום את העלות ולנסות שוב את אותו שלב." % (call["provider_outcome"], _usd(call["known_usd"])),
                "options": [_option("accept_and_retry", "לרשום %s ולנסות שוב" % _usd(call["known_usd"]))]
                           + ([_option("skip_notebook_chapter", "לרשום ולדלג על עדכון המחברת בפרק זה")] if notebook else [])
                           + vision}
    if _unresolved_anomaly(status):
        return {"kind": "over_cap_anomaly", "details": details,
                "message": "עלות קריאה חרגה מהסכום שנשמר לה או מהתקציב. בדקו את ההוצאה לפני שממשיכים.",
                "options": [_option("acknowledge", "ראיתי, להמשיך")] + _budget_options(status)}
    if status["stopped"]:
        return {"kind": "stopped", "details": details, "message": "העבודה נעצרה לבטיחות התקציב.",
                "options": [_option("acknowledge", "להמשיך")]}
    if status["attempted_calls"] >= status["max_calls"]:
        raised = max(status["max_calls"] + 1, math.ceil(status["max_calls"] * 1.5))
        return {"kind": "call_limit", "details": details,
                "message": "הגעתם למספר הקריאות המרבי לעבודה זו (%d)." % status["max_calls"],
                "options": [_option("raise_calls", "להעלות ל־%d קריאות" % raised, raised)]}
    if any(phrase in error for phrase in _BUDGET_PHRASES):
        return {"kind": "budget_limit", "details": details,
                "message": "התקציב שהוגדר (%s) אינו מספיק להמשך. הוצאה עד כה: %s."
                           % (_usd(status["hard_list_usd"]), _usd(status["list_estimated_spent_usd"])),
                "options": _budget_options(status)}
    if blocking and error:
        # The step that stopped the job is the one failed (or re-checked) last; an older
        # failure later in the book must not stand in for it.
        step = max(blocking, key=lambda s: (s["updated_at"], s["created_at"]))
        saved = json.loads(step["raw_json"]) if step["status"] == "failed" and step["raw_json"] else None
        options = [_option("accept_and_retry", "לשלוח את השלב מחדש (קריאה חדשה לספק)")]
        message = "שלב %s נכשל (%s). ניסיון חוזר ישלח קריאה חדשה לספק." % (step["stage"], step["error"] or step["status"])
        if saved and saved.get("status") in ("completed", "mock_placeholder"):
            if journal.rejection_code(step["identity"]) != chapter_pipeline.VALIDATOR_CODE:
                # The code changed since this answer was rejected: resuming re-checks it
                # first (it is the step the run stopped at), never resends.
                options.insert(0, _option("reuse_saved_response", "להמשיך עם התשובה השמורה (בלי קריאה חדשה)"))
                message = ("שלב %s נכשל בבדיקת התשובה (%s). התשובה של הספק נשמרה והקוד עודכן מאז: אפשר לבדוק "
                           "אותה שוב בלי קריאה חדשה, או לשלוח את השלב מחדש." % (step["stage"], step["error"]))
            else:
                message = ("שלב %s נכשל בבדיקת התשובה (%s). התשובה השמורה כבר נבדקה בקוד הנוכחי ונדחתה; "
                           "ניסיון חוזר ישלח קריאה חדשה לספק." % (step["stage"], step["error"]))
        if step["stage"] == _VISION_STAGE:
            options.append(_option("skip_ocr_review", _SKIP_VISION_LABEL))
        return {"kind": "failed_call", "details": dict(details, stage=step["stage"], identity=step["identity"]),
                "message": message, "options": options}
    return None


def auto_decision(job, store, journal):
    """The option to apply without asking, or None when the user must decide.
    Only an unknown-outcome block whose total held charge is below
    ``AUTO_ACCEPT_BELOW_USD`` qualifies, at most ``AUTO_ACCEPT_MAX_STREAK``
    times in a row."""
    block = diagnose(job, store, journal)
    if block is None or block["kind"] != "unknown_outcome":
        return None
    if sum(c["held_usd"] for c in store.uncertain_calls(job["job_id"])) >= AUTO_ACCEPT_BELOW_USD:
        return None
    calls, streak = store.status(job["job_id"])["attempted_calls"], 0
    for decision in reversed(job.get("decisions", [])):
        if not decision.get("auto") or calls - decision.get("calls", 0) > 1:
            break
        streak, calls = streak + 1, decision.get("calls", 0)
    return None if streak >= AUTO_ACCEPT_MAX_STREAK else "accept_worst_case_and_retry"


def _reset_stuck(job, journal, stage=None, store=None, identity=None):
    for step in journal.job_steps(job["job_id"]):
        if step["status"] in ("failed", "unknown", "dispatched") and (stage is None or step["stage"] == stage) \
                and (identity is None or step["identity"] == identity):
            saved = json.loads(step["raw_json"]) if step["raw_json"] else None
            if store is not None and step["status"] == "failed" and saved and saved.get("status") in ("completed", "mock_placeholder"):
                # The provider answered but the answer failed validation: a resend must
                # not replay the same cached answer.
                store.user_evict_cache(job["job_id"], stage=step["stage"], prompt_hash=step["prompt_hash"])
            prior = journal.reset_for_retry(step["identity"])
            job.setdefault("retry_history", []).append({
                "identity": prior["identity"], "stage": prior["stage"], "status": prior["status"],
                "error": prior["error"], "raw_json": prior["raw_json"], "reset_at": time.time()})


def _reopen_skipped(job, journal, stage=None, identity=None):
    """Undo the "keeper skipped" bookkeeping for exactly the steps ``_reset_stuck``
    will reset, so the reset step really runs again (chapter notebook, name table,
    cross-chapter QA window)."""
    for step in journal.job_steps(job["job_id"]):
        if step["status"] not in ("failed", "unknown", "dispatched") or (stage is not None and step["stage"] != stage) \
                or (identity is not None and step["identity"] != identity):
            continue
        inputs = json.loads(step["dependencies_json"] or "{}").get("inputs", {})
        if step["stage"] == _NOTEBOOK_STAGE:
            chapter = inputs.get("chapter")
            key = str(chapter)
            if chapter is not None and not job.get("chapter_completion", {}).get(key):
                job.get("notebook_applied", {}).pop(key, None)
                job.get("qa_notebooks", {}).pop(key, None)
        elif step["stage"] == _NAME_TABLE_STAGE:
            if job.get("name_table", {}).get("status") == "skipped":
                job["name_table"]["status"] = "pending"
        elif step["stage"] == _CROSS_QA_STAGE:
            windows = job.get("cross_qa", {}).get("windows", {})
            if windows.get(inputs.get("window"), {}).get("status") == "skipped":
                windows.pop(inputs.get("window"), None)


def _reopen_failed_keeper(job, journal):
    """Let the keeper run again (under the new setting) for a chapter whose keeper
    call failed or ended with an unknown outcome, if the chapter is not completed."""
    _reopen_skipped(job, journal, _NOTEBOOK_STAGE)


def store_has_task(store, job_id):
    try:
        store.status(job_id)
        return True
    except RuntimeControlsError:
        return False


def apply_decision(job, store, journal, option_id, value=None, auto=False):
    """Apply one offered option. Mutates and returns ``job`` (caller persists).
    ``auto`` marks a decision taken by the user's standing rule (``auto_decision``)."""
    block = diagnose(job, store, journal)
    if block is None:
        raise BlockDecisionError("אין חסימה שדורשת החלטה בעבודה זו.")
    offered = {o["id"]: o for o in block["options"]}
    if option_id not in offered:
        raise BlockDecisionError("האפשרות שנבחרה אינה זמינה עבור החסימה הנוכחית.")
    job_id, settings = job["job_id"], job["settings"]
    try:
        uncertain = store.uncertain_calls(job_id)
    except RuntimeControlsError:
        uncertain = []   # no control-store task yet
    accepted = [store.user_settle(job_id, call["event_id"]) for call in uncertain]
    if option_id == "raise_notebook_cap":
        settings["keeper_output_cap"] = int(offered[option_id]["value"])
        _reopen_failed_keeper(job, journal)
    elif option_id == "shorten_notebook":
        settings["notebook_story_words"] = int(offered[option_id]["value"])
        _reopen_failed_keeper(job, journal)
    elif option_id == "skip_ocr_review":
        settings["ocr_review"] = "off"
        for step in journal.job_steps(job_id):
            if step["stage"] == _VISION_STAGE and step["status"] in ("unknown", "dispatched"):
                journal.mark_failed(step["identity"], "vision review skipped by user decision")
    elif option_id == "skip_notebook_chapter":
        for step in journal.job_steps(job_id):
            if step["stage"] == _NOTEBOOK_STAGE and step["status"] in ("unknown", "dispatched"):
                journal.mark_failed(step["identity"], "notebook update skipped by user decision")
    elif option_id in ("accept_and_retry", "accept_worst_case_and_retry"):
        # A failed call resets only the step shown; other saved answers stay for their re-check.
        retry_stage = block["details"].get("call", {}).get("stage") or block["details"].get("stage")
        retry_identity = block["details"].get("identity") if block["kind"] == "failed_call" else None
        _reopen_skipped(job, journal, retry_stage, retry_identity)
        _reset_stuck(job, journal, retry_stage, store, retry_identity)
    elif option_id == "raise_calls":
        settings["max_calls"] = store.user_raise_limits(job_id, max_calls=int(offered[option_id]["value"]))["max_calls"]
    elif option_id == "raise_budget":
        amount = value if offered[option_id].get("input") else offered[option_id]["value"]
        if type(amount) not in (int, float) or isinstance(amount, bool) or not math.isfinite(amount) \
                or amount <= block["details"]["budget_usd"]:
            raise BlockDecisionError("יש להזין תקציב גבוה מהתקציב הנוכחי.")
        amount = round(float(amount), 2)
        try:
            settings["budget_usd"] = store.user_raise_limits(job_id, hard_list_usd=amount)["hard_list_usd"]
        except RuntimeControlsError:
            if uncertain or store_has_task(store, job_id):
                raise
            settings["budget_usd"] = amount   # nothing reserved yet: the job setting is the whole policy
    if store_has_task(store, job_id) and store.status(job_id)["stopped"]:
        store.user_resume(job_id)
    decision = {"at": time.time(), "kind": block["kind"], "option": option_id,
                "value": settings.get("budget_usd") if option_id == "raise_budget" else offered[option_id].get("value"),
                "accepted_charges": accepted}
    if auto:
        decision.update(auto=True, calls=block["details"]["calls"])
    job.setdefault("decisions", []).append(decision)
    job["error"] = None
    return job
