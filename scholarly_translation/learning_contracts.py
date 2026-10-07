"""LEARN schema 1: pure contracts shared by independent learning components."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re

SCHEMA_VERSION = 1
POLICY_VERSION = "learning-policy@3"
SUPPORTED_LANGUAGE_CODES = ("fr", "de", "es", "yi", "it")
MAX_CHUNK_CHARS = 2400
DEFAULT_LEVELS = [
    {"level_id": "1", "new_items_per_chunk": 3, "max_foreign_share": .10,
     "max_grammar_per_chunk": 1, "max_foreign_words_per_edit": 1, "support_mode": "context"},
    {"level_id": "2", "new_items_per_chunk": 3, "max_foreign_share": .20,
     "max_grammar_per_chunk": 1, "max_foreign_words_per_edit": 2, "support_mode": "context"},
    {"level_id": "3", "new_items_per_chunk": 4, "max_foreign_share": .30,
     "max_grammar_per_chunk": 1, "max_foreign_words_per_edit": 5, "support_mode": "context"},
]


class LearningError(ValueError):
    def __init__(self, code, message=None):
        self.code = code
        super().__init__(message or code)


def require(condition, code="invalid_record", message=None):
    if not condition:
        raise LearningError(code, message)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_id(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}", value),
            "invalid_id")
    return value


def require_fields(row, fields, optional=(), code="invalid_record"):
    require(isinstance(row, dict) and set(fields) <= set(row)
            and not set(row) - set(fields) - set(optional), code)


def _version(row):
    require(type(row.get("schema_version")) is int and row["schema_version"] == 1, "schema_version")


def _integer(value, minimum=0):
    require(type(value) is int and value >= minimum)


def _text(value, limit=2000000, empty=False):
    require(isinstance(value, str) and len(value) <= limit and (empty or bool(value.strip())))


def _ids(rows, key):
    require(isinstance(rows, list))
    values = [check_id(row[key]) for row in rows]
    require(len(values) == len(set(values)), "duplicate_id")


def source_hash(source):
    return fingerprint(source["chapters"])


def validate_source(source):
    require_fields(source, ("schema_version", "book_id", "revision", "title", "source_hash", "origin", "chapters"))
    _version(source)
    check_id(source["book_id"])
    _integer(source["revision"], 1)
    _text(source["title"], 500)
    origin = source["origin"]
    require_fields(origin, ("kind", "original_hash", "source_job_id", "source_revision"))
    require(origin["kind"] in ("hebrew_epub", "translation_library"))
    require(re.fullmatch(r"[a-f0-9]{64}", origin["original_hash"]) is not None)
    if origin["source_job_id"] is not None:
        check_id(origin["source_job_id"])
    if origin["source_revision"] is not None:
        _integer(origin["source_revision"])
    require(bool(source["chapters"]), "no_hebrew_text")
    _ids(source["chapters"], "chapter_id")
    all_ids = []
    for chapter in source["chapters"]:
        require_fields(chapter, ("chapter_id", "title", "units"))
        _text(chapter["title"], 500)
        require(bool(chapter["units"]), "no_hebrew_text")
        for unit in chapter["units"]:
            require_fields(unit, ("unit_id", "text", "kind"))
            all_ids.append(check_id(unit["unit_id"]))
            _text(unit["text"])
            require(unit["kind"] in ("heading", "paragraph"))
    require(len(all_ids) == len(set(all_ids)), "duplicate_id")
    require(source["source_hash"] == source_hash(source), "source_hash_mismatch")
    return source


def validate_catalog(catalog):
    require_fields(catalog, ("schema_version", "language", "version", "provenance", "items", "levels"), ('frequency_seed',))
    _version(catalog)
    require(catalog["language"] in SUPPORTED_LANGUAGE_CODES, "unsupported_language")
    _text(catalog["version"], 128)
    require_fields(catalog["provenance"], ("basis", "source", "license"))
    for value in catalog["provenance"].values():
        _text(value, 1000)
    _ids(catalog["items"], "item_id")
    if 'frequency_seed' in catalog:
        require(isinstance(catalog['frequency_seed'], list))
        for row in catalog['frequency_seed']:
            require_fields(row, ('rank', 'word'))
            _integer(row['rank'], 1)
            _text(row['word'], 300)
    keys = {i["item_id"] for i in catalog["items"]}
    for item in catalog["items"]:
        require_fields(item, ("item_id", "kind", "lemma", "sense_he", "forms", "priority_tier",
                             "prerequisite_ids", "explanation_he", "min_level"))
        require(item["kind"] in ("word", "phrase", "grammar"))
        _text(item["lemma"], 300)
        _text(item["sense_he"], 300)
        _text(item["explanation_he"], 1000, empty=True)
        _integer(item["priority_tier"], 1)
        _integer(item["min_level"], 1)
        require(isinstance(item["forms"], list) and bool(item["forms"]))
        for surface in item["forms"]:
            _text(surface, 300)
        require(isinstance(item["prerequisite_ids"], list)
                and set(item["prerequisite_ids"]) <= keys and item["item_id"] not in item["prerequisite_ids"])
    visiting, visited = set(), set()
    by_id = {i["item_id"]: i for i in catalog["items"]}
    def visit(key):
        require(key not in visiting, "prerequisite_cycle")
        if key in visited:
            return
        visiting.add(key)
        for dependency in by_id[key]["prerequisite_ids"]:
            visit(dependency)
        visiting.remove(key)
        visited.add(key)
    for key in keys:
        visit(key)
    require(bool(catalog["levels"]))
    _ids(catalog["levels"], "level_id")
    for level in catalog["levels"]:
        require_fields(level, DEFAULT_LEVELS[0].keys())
        for key in ("new_items_per_chunk", "max_grammar_per_chunk", "max_foreign_words_per_edit"):
            _integer(level[key], 1)
        require(type(level["max_foreign_share"]) in (int, float)
                and math.isfinite(level["max_foreign_share"]) and 0 < level["max_foreign_share"] <= 1)
        require(level["support_mode"] in ("context", "inline", "click"))
    return catalog


def new_learner(language="fr", learner_id="local", catalog_version=None):
    catalog_version = catalog_version or ('fr-common@2' if language == 'fr' else language + '-seed@1')
    result = {"schema_version": 1, "learner_id": learner_id, "language": language,
              "revision": 0, "catalog_version": catalog_version, "level_id": "1",
              "support_mode": "context", "items": [], "completed_books": [], "active_book_id": None}
    return validate_learner(result)


def validate_learner(learner):
    require_fields(learner, ("schema_version", "learner_id", "language", "revision", "catalog_version",
                             "level_id", "support_mode", "items", "completed_books", "active_book_id"), ('vocabulary',))
    _version(learner)
    check_id(learner["learner_id"])
    require(learner["language"] in SUPPORTED_LANGUAGE_CODES, "unsupported_language")
    if 'vocabulary' in learner:
        from .learning_vocabulary import validate_vocabulary
        validate_vocabulary(learner['vocabulary'], learner['language'])
    _integer(learner["revision"])
    check_id(learner["level_id"])
    _text(learner["catalog_version"], 128)
    require(learner["support_mode"] in ("context", "inline", "click"))
    _ids(learner["items"], "item_id")
    for row in learner["items"]:
        require_fields(row, ("item_id", "introduced_count", "last_completed_book_id"))
        _integer(row["introduced_count"], 1)
        check_id(row["last_completed_book_id"])
    _ids(learner["completed_books"], "completion_id")
    for row in learner["completed_books"]:
        require_fields(row, ("book_id", "prepared_hash", "completion_id"))
        check_id(row["book_id"])
        _text(row["prepared_hash"], 64)
    if learner["active_book_id"] is not None:
        check_id(learner["active_book_id"])
    return learner


def validate_session(session):
    require_fields(session, ("schema_version", "session_id", "learner_id", "language", "book_id", "source_hash",
                             "base_learner_revision", "policy_version", "catalog_version", "level_id",
                             "support_mode", "status", "prepared_hash", "chunk_ids", "read_cursor"), ('vocabulary',))
    _version(session)
    for key in ("session_id", "learner_id", "book_id", "level_id"):
        check_id(session[key])
    _integer(session["base_learner_revision"])
    require(session["language"] in SUPPORTED_LANGUAGE_CODES, "unsupported_language")
    if 'vocabulary' in session:
        from .learning_vocabulary import validate_vocabulary
        validate_vocabulary(session['vocabulary'], session['language'])
    require(session["status"] in ("imported", "preparing", "ready", "completed", "paused", "failed"))
    require(session["support_mode"] in ("context", "inline", "click"))
    require(isinstance(session["chunk_ids"], list) and len(set(session["chunk_ids"])) == len(session["chunk_ids"]))
    for cid in session["chunk_ids"]:
        check_id(cid)
    for key in ("policy_version", "catalog_version", "source_hash"):
        _text(session[key], 128)
    if session["prepared_hash"] is not None:
        _text(session["prepared_hash"], 64)
    require(session["read_cursor"] is None or isinstance(session["read_cursor"], dict))
    return session


def validate_plan(plan):
    require_fields(plan, ("schema_version", "plan_id", "book_id", "chapter_id", "chunk_id", "source_hash", "units",
                          "base_learner_revision", "catalog_version", "policy_version", "level_id", "support_mode",
                          "selected_item_ids", "new_item_ids", "review_item_ids", "limits"), ("language", "review_targets"))
    _version(plan)
    for key in ("plan_id", "book_id", "chapter_id", "chunk_id", "level_id"):
        check_id(plan[key])
    _integer(plan["base_learner_revision"])
    require(bool(plan["units"]), "invalid_plan")
    _ids(plan["units"], "unit_id")
    for unit in plan["units"]:
        require_fields(unit, ("unit_id", "text", "kind"))
        _text(unit["text"])
        require(unit["kind"] in ("heading", "paragraph"))
    for key in ("selected_item_ids", "new_item_ids", "review_item_ids"):
        require(isinstance(plan[key], list) and len(plan[key]) == len(set(plan[key])), "invalid_plan")
        for item in plan[key]:
            check_id(item)
    require(set(plan["new_item_ids"]) <= set(plan["selected_item_ids"]) and
            set(plan["review_item_ids"]) <= set(plan["selected_item_ids"]), "invalid_plan")
    if plan['policy_version'] != 'learning-policy@1':
        require(not set(plan['new_item_ids']) & set(plan['review_item_ids']) and
                set(plan['selected_item_ids']) == set(plan['new_item_ids']) | set(plan['review_item_ids']), 'invalid_plan')
    require_fields(plan["limits"], DEFAULT_LEVELS[0].keys())
    require(len(plan["new_item_ids"]) <= plan["limits"]["new_items_per_chunk"], "invalid_plan")
    require(plan["limits"]["level_id"] == plan["level_id"], "invalid_plan")
    require(plan['support_mode'] in ('context', 'inline', 'click'), 'invalid_plan')
    if 'review_targets' in plan:
        require(isinstance(plan['review_targets'], dict) and
                set(plan['review_targets']) == set(plan['review_item_ids']), 'invalid_plan')
        for target in plan['review_targets'].values():
            require_fields(target, ('seen_count', 'target_share'), code='invalid_plan')
            _integer(target['seen_count'], 1)
            require(type(target['target_share']) in (int, float) and
                    math.isfinite(target['target_share']) and .5 < target['target_share'] <= 1, 'invalid_plan')
    return plan


def validate_generated(chunk):
    require_fields(chunk, ("schema_version", "plan_id", "response_version", "provider", "model", "prompt_version",
                           "input_hash", "edits", "warnings", "coverage_item_ids", "content_hash"),
                   ("language", 'introduced_items', 'dictionary_entries'))
    _version(chunk)
    check_id(chunk["plan_id"])
    require(chunk["response_version"] == 1 and isinstance(chunk["edits"], list), "invalid_generation")
    for edit in chunk["edits"]:
        require_fields(edit, ("unit_id", "start", "end", "original", "replacement", "item_ids", "grammar_ids", "gloss_he"))
        check_id(edit["unit_id"])
        _integer(edit["start"])
        _integer(edit["end"], edit["start"] + 1)
        for key in ("original", "replacement", "gloss_he"):
            _text(edit[key], 2000000 if key == "original" else 1000)
        require(isinstance(edit["item_ids"], list) and isinstance(edit["grammar_ids"], list))
    require(isinstance(chunk["warnings"], list) and isinstance(chunk["coverage_item_ids"], list))
    if 'introduced_items' in chunk:
        from .learning_vocabulary import validate_vocabulary
        validate_vocabulary([{'item': item, 'origin': {key: chunk[key] for key in
                            ('provider', 'model', 'prompt_version', 'input_hash')}}
                             for item in chunk['introduced_items']], chunk.get('language'))
        used = {item_id for edit in chunk['edits'] for item_id in edit['item_ids'] + edit['grammar_ids']}
        require(all(item['item_id'] in used for item in chunk['introduced_items']), 'invalid_generation', 'unused_definition')
    if 'dictionary_entries' in chunk:
        from .learning_dictionary import validate_entries
        validate_entries(chunk['dictionary_entries'], chunk.get('language'))
        lexical = {item_id for edit in chunk['edits'] for item_id in edit['item_ids']}
        require(all(row['item_id'] in lexical for row in chunk['dictionary_entries']),
                'invalid_generation', 'unused_dictionary_entry')
    return chunk


def validate_recap(recap):
    require_fields(recap, ("schema_version", "chapter_id", "chunk_hashes", "vocabulary", "grammar", "warnings"),
                   optional=("lesson",))
    _version(recap)
    check_id(recap["chapter_id"])
    for key in ("chunk_hashes", "vocabulary", "grammar", "warnings"):
        require(isinstance(recap[key], list), "missing_recap")
    if "lesson" in recap:  # Optional per-chapter grammar lesson (newer preparations).
        from .learning_lesson import validate_lesson
        validate_lesson(recap["lesson"])
    return recap


def word_count(text):
    """Whitespace-delimited tokens containing a letter; combining marks preserved."""
    return sum(any(c.isalpha() for c in token) for token in text.split())


def prepared_hash(chunks, recaps):
    return fingerprint({"chunks": chunks, "recaps": recaps})


def fixture_source(book_id="book-one"):
    result = {"schema_version": 1, "book_id": book_id, "revision": 1, "title": "ספר לדוגמה",
              "origin": {"kind": "hebrew_epub", "original_hash": text_hash("synthetic"),
                         "source_job_id": None, "source_revision": None},
              "chapters": [{"chapter_id": "chapter-one", "title": "פרק ראשון", "units": [
                  {"unit_id": "unit-one", "kind": "paragraph", "text": "הילד הביט בבית ואז הלך בדרך הארוכה אל העיר. היום היה יפה והספר נשאר על השולחן."}]}]}
    result["source_hash"] = source_hash(result)
    return validate_source(result)
