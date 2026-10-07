"""Rolling, model-maintained book notebook (``book-notebook@1``).

Pure, deterministic, no I/O (beyond reading the prompt asset) and no provider
calls. The model decides what is worth remembering (free tags, e.g.
wordplay/humor/quote/name/character); this module validates and bounds
everything the model returns, never raises on model output, and renders a
priority-ordered excerpt for later prompts.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from .target_languages import localize

SCHEMA = "book-notebook@1"
SUGGESTED_TAGS = (
    "wordplay", "humor", "quote", "allusion", "name", "character", "description",
    "place", "term", "register", "motif", "ambiguity", "style", "address", "gender",
)
SCHOLARLY_SUGGESTED_TAGS = (
    "term", "concept", "definition", "distinction", "argument", "author", "work",
    "citation", "quotation", "abbreviation", "transliteration", "notation", "ambiguity",
    "register", "style",
)
_PROFILE_GUIDANCE = {
    "literary": (
        "- Record forms of address and {{T:NB_GENDER}} of characters and "
        "addressees, plus each character's voice and register.\n"
        "- Record running jokes, recurring wordplay, motifs, quotations and allusions, and how they were "
        "rendered in {{T:TARGET}}.\n"
        "- \"story_so_far\" is the translation's only memory of the plot. Rewrite it from the existing "
        "STORY_SO_FAR plus this chapter, keeping every plot line, subplot, relationship, secret and open "
        "question that may still matter. Compress older or resolved events instead of dropping threads.",
        "updated running summary of the whole book so far"),
    "scholarly": (
        "- The text may be a single article rather than a book: \"book\" then means the article and "
        "\"chapter\" one of its parts.\n"
        "- \"story_so_far\" holds THE ARGUMENT SO FAR: the translation's only memory of the book's reasoning. "
        "Rewrite it from the existing STORY_SO_FAR plus this chapter: the thesis, each step of the argument, the "
        "concepts defined and how the author uses them, the distinctions the author insists on, the positions of "
        "cited authors or opponents and the author's stance toward them, and questions left open. Compress "
        "settled material instead of dropping it.\n"
        "- Terminology is the main risk in scholarly translation. Record one {{T:TARGET}} rendering per technical term "
        "and keep it; note when the original-language term is kept in parentheses; record which established "
        "{{T:TARGET}} translation is used when canonical works are quoted; record transliterations of authors' names, "
        "titles and foreign terms; record abbreviations and notation; and record the reading chosen for an "
        "ambiguous term so later chapters keep it.\n"
        "- Record {{T:NB_GENDER}} of cited authors and of the reader or addressee, "
        "the author's own voice (first person singular or plural, impersonal), register and hedging habits, "
        "and how cross-references (chapters, sections, figures, equations, notes) are rendered.\n"
        "- Names include cited authors and scholars (\"kind\": person), cited works (\"kind\": work, the "
        "established {{T:TARGET}} title when one exists) and the author's key technical terms and coinages "
        "(\"kind\": term, {{T:NB_TERM_BASE}}).",
        "updated running summary of the whole argument so far"),
}
MAX_ENTRIES = 3000
MAX_HISTORY = 200
MAX_TAGS = 4
MAX_TAG_LEN = 32
MAX_TITLE = 120
MAX_NOTE = 2000
MAX_RENDERING = 600
MAX_MATCH_TERMS = 24
MAX_MATCH_TERM_LEN = 60
MAX_SUMMARY = 5000
MAX_STORY = 60000  # safety bound only; the summary keeps every thread the book needs
SCOPES = ("global", "local")
STATUSES = ("active", "superseded")
ORIGINS = ("model", "human")

_PROMPT_PATH = Path(__file__).resolve().parent / "runtime_prompts" / "07_book_notebook_keeper.md"
_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯豈-﫿]")


class NotebookError(ValueError):
    pass


def _norm_text(value):
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


def _clip(value, limit):
    if value is None:
        return ""
    return " ".join(str(value).split())[:limit].strip()


def _norm_tags(tags):
    out = []
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, (list, tuple)):
        return out
    for tag in tags:
        if not isinstance(tag, str):
            continue
        t = " ".join(tag.lower().split())[:MAX_TAG_LEN].strip()
        if t and t not in out:
            out.append(t)
        if len(out) >= MAX_TAGS:
            break
    return out


def _norm_terms(terms):
    out = []
    if not isinstance(terms, (list, tuple)):
        return out
    for term in terms:
        if not isinstance(term, str):
            continue
        t = " ".join(term.split())[:MAX_MATCH_TERM_LEN].strip()
        if t and t not in out:
            out.append(t)
        if len(out) >= MAX_MATCH_TERMS:
            break
    return out


def make_entry_id(document_id, title, first_tag):
    key = "\x1f".join((str(document_id), _norm_text(title), _norm_text(first_tag)))
    return "n_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def new_notebook(document_id):
    return {
        "schema": SCHEMA, "document_id": str(document_id), "revision": 0,
        "entries": [], "chapter_summaries": {}, "story_so_far": "", "history": [],
    }


def validate_notebook(nb):
    """Return True, or raise NotebookError if ``nb`` is not a well-formed book-notebook@1."""
    def req(cond, msg):
        if not cond:
            raise NotebookError(msg)
    req(isinstance(nb, dict) and nb.get("schema") == SCHEMA, "not a book-notebook@1")
    req(isinstance(nb.get("document_id"), str), "document_id must be a string")
    req(type(nb.get("revision")) is int and nb["revision"] >= 0, "bad revision")
    entries = nb.get("entries")
    req(isinstance(entries, list) and len(entries) <= MAX_ENTRIES, "bad entries")
    seen = set()
    for e in entries:
        req(isinstance(e, dict), "entry must be an object")
        eid = e.get("entry_id")
        req(isinstance(eid, str) and eid and eid not in seen, "bad or duplicate entry_id")
        seen.add(eid)
        tags = e.get("tags")
        req(isinstance(tags, list) and 1 <= len(tags) <= MAX_TAGS, "tags must be 1-4")
        req(all(isinstance(t, str) and t and len(t) <= MAX_TAG_LEN and t == t.lower().strip()
                for t in tags), "bad tag")
        req(isinstance(e.get("title"), str) and 0 < len(e["title"]) <= MAX_TITLE, "bad title")
        req(isinstance(e.get("note"), str) and len(e["note"]) <= MAX_NOTE, "bad note")
        hr = e.get("hebrew_rendering", "")
        req(isinstance(hr, str) and len(hr) <= MAX_RENDERING, "bad hebrew_rendering")
        mt = e.get("match_terms")
        req(isinstance(mt, list) and len(mt) <= MAX_MATCH_TERMS and
            all(isinstance(t, str) and t and len(t) <= MAX_MATCH_TERM_LEN for t in mt), "bad match_terms")
        req(e.get("scope") in SCOPES, "bad scope")
        req(e.get("status") in STATUSES, "bad status")
        req(e.get("origin") in ORIGINS, "bad origin")
        req(type(e.get("pinned")) is bool, "bad pinned")
        for k in ("first_chapter", "last_chapter"):
            req(type(e.get(k)) is int and e[k] >= 0, "bad chapter index")
        req(e["first_chapter"] <= e["last_chapter"], "chapter range inverted")
    cs = nb.get("chapter_summaries")
    req(isinstance(cs, dict), "bad chapter_summaries")
    for k, v in cs.items():
        req(isinstance(k, str) and k.isdigit() and isinstance(v, str) and len(v) <= MAX_SUMMARY,
            "bad chapter summary")
    req(isinstance(nb.get("story_so_far"), str) and len(nb["story_so_far"]) <= MAX_STORY, "bad story_so_far")
    h = nb.get("history")
    req(isinstance(h, list) and len(h) <= MAX_HISTORY and all(isinstance(r, dict) for r in h), "bad history")
    return True


# ---------------------------------------------------------------- prompt

def build_keeper_prompt(notebook_excerpt_text, source_chapter, hebrew_chapter, chapter_index, profile_id,
                        story_words=None, names_text=""):
    text = localize(_PROMPT_PATH.read_text(encoding="utf-8"))
    scholarly = profile_id == "scholarly"
    guidance, story_description = map(localize, _PROFILE_GUIDANCE["scholarly" if scholarly else "literary"])
    subs = {
        "PROFILE_ID": str(profile_id), "CHAPTER_INDEX": str(chapter_index),
        "CHAPTER_NUMBER": str(int(chapter_index) + 1),
        "SUGGESTED_TAGS": ", ".join(SCHOLARLY_SUGGESTED_TAGS if scholarly else SUGGESTED_TAGS),
        "PROFILE_GUIDANCE": guidance, "STORY_DESCRIPTION": story_description,
        "NOTEBOOK_EXCERPT": notebook_excerpt_text or "(empty)",
        "NAMES_TABLE": (names_text or "").strip() or "(empty)",
        "SOURCE_CHAPTER": source_chapter or "", "HEBREW_CHAPTER": hebrew_chapter or "",
        "STORY_LENGTH": ("as long as the book needs to keep every thread" if not story_words
                         else "at most %d words" % int(story_words)),
    }
    return re.sub(r"\{\{(" + "|".join(subs) + r")\}\}", lambda m: subs[m.group(1)], text)


# ---------------------------------------------------------------- parsing

_FENCE_RE = re.compile(r"^\s*```[\w+-]*[ \t]*\r?\n?(.*?)\r?\n?[ \t]*```\s*$", re.S)
MAX_JSON_REPAIRS = 4


def _decode_with_repair(text, start, keys):
    """raw_decode at ``start``; delete a stray ] or } at the error position (<= 4 times)."""
    decoder = json.JSONDecoder()
    repairs = 0
    while True:
        try:
            obj, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError as exc:
            if repairs >= MAX_JSON_REPAIRS or not (start <= exc.pos < len(text)) or text[exc.pos] not in "]}":
                return None, False
            text = text[:exc.pos] + text[exc.pos + 1:]
            repairs += 1
            continue
        except ValueError:
            return None, False
        if isinstance(obj, dict) and any(k in obj for k in keys):
            return obj, repairs > 0
        return None, False


def extract_json_object(raw_text, keys):
    """Return ``(obj, repaired)`` for the JSON object in model output, or ``(None, False)``.

    Strips surrounding code fences; parses strictly; deletes up to 4 stray ``]``/``}``
    characters at the error position (``repaired=True``). Only a dict holding at least one of
    ``keys`` is accepted, so an inner object such as one op is never returned. Falls back to
    scanning ``{`` positions (prose around the JSON)."""
    if not isinstance(raw_text, str):
        return None, False
    keys = tuple(keys)
    text = raw_text.strip()
    m = _FENCE_RE.match(text)
    if m:
        text = m.group(1).strip()
    if text.startswith("{"):
        obj, repaired = _decode_with_repair(text, 0, keys)
        if obj is not None:
            return obj, repaired
    pos = text.find("{")
    while pos != -1:
        obj, repaired = _decode_with_repair(text, pos, keys)
        if obj is not None:
            return obj, repaired
        pos = text.find("{", pos + 1)
    return None, False


def _report(status, warnings=None):
    return {"status": status, "added": 0, "updated": 0, "superseded": 0, "skipped": 0,
            "warnings": list(warnings or []), "format_repaired": False, "names_raw": None}


def apply_keeper_response(notebook, raw_text, chapter_index):
    """Return ``(new_notebook, report)``; never mutates ``notebook``, never raises on model output."""
    if type(chapter_index) is not int or chapter_index < 0:
        raise NotebookError("chapter_index must be a nonnegative integer")
    obj, repaired = extract_json_object(raw_text, ("ops", "chapter_summary", "story_so_far", "names"))
    if obj is None:
        return notebook, _report("unparsed", ["keeper output was not parseable JSON"])
    nb = copy.deepcopy(notebook)
    rep = _report("ok")
    rep["format_repaired"] = bool(repaired)
    rep["names_raw"] = obj.get("names")
    warn = rep["warnings"]
    entries = nb["entries"]
    by_id = {e["entry_id"]: e for e in entries}
    by_title = {}
    for e in entries:
        if e["status"] == "active":
            by_title.setdefault(_norm_text(e["title"]), e)
    ops = obj.get("ops", [])
    if not isinstance(ops, list):
        warn.append("ops was not a list")
        ops = []
    for i, op in enumerate(ops):
        try:
            _apply_op(nb, op, i, chapter_index, by_id, by_title, rep)
        except Exception:  # defensive: model output must never raise
            rep["skipped"] += 1
            warn.append("op %d: could not be applied" % i)
    cs = obj.get("chapter_summary")
    if isinstance(cs, str) and cs.strip():
        summary = " ".join(cs.split())
        if len(summary) > MAX_SUMMARY:
            warn.append("chapter_summary exceeded %d characters and was shortened" % MAX_SUMMARY)
        nb["chapter_summaries"][str(chapter_index)] = summary[:MAX_SUMMARY].strip()
    elif "chapter_summary" not in obj:
        warn.append("chapter_summary missing")
    else:
        warn.append("chapter_summary invalid")
    sf = obj.get("story_so_far")
    if isinstance(sf, str) and sf.strip():
        story = " ".join(sf.split())
        if len(story) > MAX_STORY:
            warn.append("story_so_far exceeded %d characters and was shortened" % MAX_STORY)
        nb["story_so_far"] = story[:MAX_STORY].strip()
    elif "story_so_far" not in obj:
        warn.append("story_so_far missing")
    else:
        warn.append("story_so_far invalid")
    nb["revision"] += 1
    record = {"revision": nb["revision"], "chapter_index": chapter_index, "warnings": len(warn)}
    for k in ("added", "updated", "superseded", "skipped"):
        record[k] = rep[k]
    nb["history"].append(record)
    nb["history"] = nb["history"][-MAX_HISTORY:]
    return nb, rep


VOICE_TITLE = "משלב וקול הספר"
KEY_WORD_TITLE = "מילת מפתח: %s"


def add_voice_entries(notebook, voice, chapter_index=0):
    """BOOK-VOICE: the register and key words decided before chapter 1 as ordinary global entries
    (the keeper may refine them). ``(new_notebook, report)``; never mutates, never raises on ``voice``."""
    rep = _report("ok")
    if not isinstance(voice, dict):
        return notebook, _report("skipped", ["no voice"])
    ops = []
    if isinstance(voice.get("register"), str) and voice["register"].strip():
        ops.append({"op": "add", "tags": ["voice"], "title": VOICE_TITLE, "note": voice["register"],
                    "scope": "global"})
    for word in voice.get("key_words") if isinstance(voice.get("key_words"), list) else []:
        if not isinstance(word, dict) or not word.get("source"):
            continue
        forms = [word["source"]] + [f for f in word.get("forms") or [] if isinstance(f, str)]
        ops.append({"op": "add", "tags": ["key-word"], "title": KEY_WORD_TITLE % word["source"],
                    "note": word.get("note") or "", "hebrew_rendering": word.get("hebrew") or "",
                    "match_terms": forms, "scope": "global"})
    if not ops:
        return notebook, _report("skipped", ["empty voice"])
    nb = copy.deepcopy(notebook)
    by_id = {e["entry_id"]: e for e in nb["entries"]}
    by_title = {}
    for e in nb["entries"]:
        if e["status"] == "active":
            by_title.setdefault(_norm_text(e["title"]), e)
    for i, op in enumerate(ops):
        try:
            _apply_op(nb, op, i, chapter_index, by_id, by_title, rep)
        except Exception:  # defensive: model output must never raise
            rep["skipped"] += 1
            rep["warnings"].append("voice op %d: could not be applied" % i)
    nb["revision"] += 1
    record = {"revision": nb["revision"], "chapter_index": chapter_index, "warnings": len(rep["warnings"])}
    for k in ("added", "updated", "superseded", "skipped"):
        record[k] = rep[k]
    nb["history"].append(record)
    nb["history"] = nb["history"][-MAX_HISTORY:]
    return nb, rep


USER_TERM_TAG = "user-term"
USER_TERM_TITLE = "מונח מחייב: %s"


def add_user_terms(notebook, terms, chapter_index=0):
    """USER-TERMS: the user's personal-glossary terms (``user_glossary`` rows that occur in the
    document) as global, human entries: the keeper cannot change them and they shadow any model
    entry sharing one of their source forms. ``(new_notebook, report)``; never mutates."""
    rep = _report("ok")
    nb = copy.deepcopy(notebook)
    by_id = {e["entry_id"]: e for e in nb["entries"]}
    for term in terms or []:
        title = _clip(USER_TERM_TITLE % term["source"], MAX_TITLE)
        eid = make_entry_id(nb["document_id"], title, USER_TERM_TAG)
        entry = {
            "entry_id": eid, "tags": [USER_TERM_TAG], "title": title,
            "note": _clip(term.get("note"), MAX_NOTE),
            "hebrew_rendering": _clip(term["target"], MAX_RENDERING),
            "match_terms": _norm_terms([term["source"]] + list(term.get("forms") or [])),
            "scope": "global", "first_chapter": chapter_index, "last_chapter": chapter_index,
            "status": "active", "origin": "human", "pinned": False,
        }
        if eid in by_id:
            by_id[eid].update({k: entry[k] for k in ("note", "hebrew_rendering", "match_terms", "status")})
            rep["updated"] += 1
        else:
            if len(nb["entries"]) >= MAX_ENTRIES:
                rep["skipped"] += 1
                rep["warnings"].append("notebook is full, user term not added")
                continue
            nb["entries"].append(entry)
            by_id[eid] = entry
            rep["added"] += 1
    if not rep["added"] and not rep["updated"]:
        return notebook, _report("skipped", ["no user terms"])
    nb["revision"] += 1
    nb["history"].append({"revision": nb["revision"], "chapter_index": chapter_index, "user_terms": len(terms),
                          "added": rep["added"], "updated": rep["updated"], "superseded": 0,
                          "skipped": rep["skipped"], "warnings": len(rep["warnings"])})
    nb["history"] = nb["history"][-MAX_HISTORY:]
    return nb, rep


def user_terms(notebook):
    """Active human user-term entries as ``[(forms, rendering)]``."""
    return [(e["match_terms"], e["hebrew_rendering"]) for e in (notebook or {}).get("entries", [])
            if e["status"] == "active" and e["origin"] == "human" and USER_TERM_TAG in e["tags"]
            and e["match_terms"] and e["hebrew_rendering"]]


def _shadowed_ids(entries):
    """Model entries that share a source form with a human entry: the human choice wins, so
    they are not shown to the translator (they stay in the notebook, marked in the download)."""
    human = {_norm_text(t) for e in entries if e["origin"] == "human" and e["status"] == "active"
             for t in e["match_terms"]}
    if not human:
        return set()
    return {e["entry_id"] for e in entries if e["origin"] == "model"
            and any(_norm_text(t) in human for t in e["match_terms"])}


def _protected(entry):
    return bool(entry.get("pinned")) or entry.get("origin") == "human"


def _has_content(op):
    return bool(_norm_tags(op.get("tags"))) and bool(_clip(op.get("title"), MAX_TITLE))


def _apply_op(nb, op, i, chapter, by_id, by_title, rep):
    warn = rep["warnings"]
    if not isinstance(op, dict):
        rep["skipped"] += 1
        warn.append("op %d: not an object" % i)
        return
    kind = op.get("op")
    if kind not in ("add", "update", "supersede"):
        rep["skipped"] += 1
        warn.append("op %d: unknown op" % i)
        return
    target = None
    if kind in ("update", "supersede"):
        target = by_id.get(op.get("entry_id"))
        if target is None:
            if kind == "supersede" or not _has_content(op):
                rep["skipped"] += 1
                warn.append("op %d: unknown entry_id" % i)
                return
            kind = "add"
    if kind == "supersede":
        if _protected(target):
            rep["skipped"] += 1
            warn.append("op %d: entry is pinned/human, not modified" % i)
            return
        target["status"] = "superseded"
        target["last_chapter"] = max(target["last_chapter"], chapter)
        rep["superseded"] += 1
        return
    for field, limit in (("note", MAX_NOTE), ("hebrew_rendering", MAX_RENDERING)):
        if isinstance(op.get(field), str) and len(" ".join(op[field].split())) > limit:
            warn.append("op %d: %s longer than %d characters was shortened" % (i, field, limit))
    tags = _norm_tags(op.get("tags"))
    title = _clip(op.get("title"), MAX_TITLE)
    if kind == "add":
        if not tags or not title:
            rep["skipped"] += 1
            warn.append("op %d: add needs tags and title" % i)
            return
        existing = by_title.get(_norm_text(title)) or by_id.get(make_entry_id(nb["document_id"], title, tags[0]))
        if existing is not None:
            target, kind = existing, "update"
    if kind == "update":
        if _protected(target):
            rep["skipped"] += 1
            warn.append("op %d: entry is pinned/human, not modified" % i)
            return
        if tags:
            target["tags"] = tags
        if title:
            target["title"] = title
        if isinstance(op.get("note"), str):
            target["note"] = _clip(op["note"], MAX_NOTE)
        if isinstance(op.get("hebrew_rendering"), str):
            target["hebrew_rendering"] = _clip(op["hebrew_rendering"], MAX_RENDERING)
        terms = _norm_terms(op.get("match_terms"))
        if terms:
            target["match_terms"] = _norm_terms(list(target["match_terms"]) + terms)
        if op.get("scope") in SCOPES:
            target["scope"] = op["scope"]
        target["status"] = "active"
        target["last_chapter"] = max(target["last_chapter"], chapter)
        rep["updated"] += 1
        return
    if len(nb["entries"]) >= MAX_ENTRIES:
        rep["skipped"] += 1
        warn.append("op %d: notebook is full (%d entries), add refused" % (i, MAX_ENTRIES))
        return
    eid = make_entry_id(nb["document_id"], title, tags[0])
    if eid in by_id:
        rep["skipped"] += 1
        warn.append("op %d: entry id collision" % i)
        return
    entry = {
        "entry_id": eid, "tags": tags, "title": title,
        "note": _clip(op.get("note"), MAX_NOTE),
        "hebrew_rendering": _clip(op.get("hebrew_rendering"), MAX_RENDERING),
        "match_terms": _norm_terms(op.get("match_terms")),
        "scope": op.get("scope") if op.get("scope") in SCOPES else "local",
        "first_chapter": chapter, "last_chapter": chapter,
        "status": "active", "origin": "model", "pinned": False,
    }
    nb["entries"].append(entry)
    by_id[eid] = entry
    by_title.setdefault(_norm_text(title), entry)
    rep["added"] += 1


# ---------------------------------------------------------------- retrieval

def _default_counter(text):
    from .token_counting import count_tokens
    return count_tokens(text)["upper_bound"]


def _compile_terms(entries):
    """Per-entry matcher: one regex for spaced terms plus CJK substring list."""
    out = []
    for e in entries:
        words, cjk = [], []
        for t in e["match_terms"]:
            t = t.casefold()
            (cjk if _CJK_RE.search(t) else words).append(t)
        rx = None
        if words:
            alts = "|".join(re.escape(w) for w in sorted(set(words), key=lambda w: (-len(w), w)))
            rx = re.compile(r"(?<!\w)(?:" + alts + r")(?!\w)")
        out.append((rx, cjk))
    return out


def _entry_line(e, with_id=False):
    line = "- [%s] %s — %s" % (", ".join(e["tags"]), e["title"], e["note"])
    if e["origin"] == "human" and USER_TERM_TAG in e["tags"]:
        line = "- [%s, BINDING: set by the user, use exactly this rendering] %s — %s" % (
            ", ".join(e["tags"]), e["title"], e["note"])
    if e.get("hebrew_rendering"):
        line += localize(" ({{T:TARGET}}: ") + e["hebrew_rendering"] + ")"
    if with_id:
        line += " {entry_id: %s}" % e["entry_id"]
    return line


def _ranked_entries(notebook, text):
    """Active entries as (pinned, matching, other global, recent local) buckets for ``text``."""
    low = (text or "").casefold()
    shadowed = _shadowed_ids(notebook["entries"])
    entries = [e for e in notebook["entries"] if e["status"] == "active" and e["entry_id"] not in shadowed]
    matchers = _compile_terms(entries)
    cur = max((int(k) for k in notebook["chapter_summaries"]), default=-1)
    recent_from = max(0, cur - 1)
    buckets = [[], [], [], []]
    for idx, e in enumerate(entries):
        rx, cjk = matchers[idx]
        if e["pinned"]:
            buckets[0].append(e)
        elif (rx is not None and rx.search(low)) or any(t in low for t in cjk):
            buckets[1].append(e)
        elif e["scope"] == "global":
            buckets[2].append(e)
        elif cur >= 0 and e["last_chapter"] >= recent_from:
            buckets[3].append(e)
    return buckets


STORY_SHARE = 0.5  # translation/review excerpts: story + previous summary use at most 50%


def render_for_chapter(notebook, chapter_source, token_budget=6000, count_tokens=None, story_share=STORY_SHARE,
                       *, with_ids=False, keep_story=False):
    """Deterministic, budgeted excerpt of the notebook for the chapter about to be handled.

    STORY_SO_FAR and the previous chapter's summary get at most ``story_share`` of the
    budget (middle shortened, opening and latest events kept; the previous summary is
    dropped last). Entries fill the rest in priority order: pinned, entries whose match
    terms occur in the chapter (any scope), other global entries, entries touched in the
    last 2 summarised chapters. The keeper passes ``story_share=1`` because it rebuilds
    the story from this excerpt and must see all of it.

    ``with_ids=True`` ends every entry line with ``{entry_id: ...}`` so the keeper can update
    by id. ``keep_story=True`` never shortens STORY_SO_FAR or the previous summary; entries
    then fill ``token_budget`` counted WITHOUT the story/summary, so the whole text may exceed
    ``token_budget`` by the size of the story and summary.
    """
    counter = count_tokens or _default_counter
    cur = max((int(k) for k in notebook["chapter_summaries"]), default=-1)
    prev_summary = notebook["chapter_summaries"].get(str(cur), "") if cur >= 0 else ""
    pinned, matching, other_global, recent = _ranked_entries(notebook, chapter_source)

    header = ("BOOK_NOTEBOOK (memory of this book; follow unless the source contradicts, "
              "note departures; approved terminology overrides; do not quote)")
    tail_parts = []
    if notebook["story_so_far"]:
        tail_parts.append("STORY_SO_FAR:\n" + notebook["story_so_far"])
    if prev_summary:
        tail_parts.append("PREVIOUS_CHAPTER_SUMMARY:\n" + prev_summary)

    def assemble(lines, tail):
        body = header + ":\n" + ("\n".join(lines) if lines else "(no relevant entries)")
        return body + ("\n\n" + tail if tail else "") + "\n"

    story_limit = token_budget * min(max(story_share, 0), 1)
    tail_text = "\n\n".join(tail_parts)
    story = notebook["story_so_far"]
    while not keep_story and tail_parts and (
            counter(assemble([], tail_text)) > token_budget or counter(tail_text) > story_limit):
        if story and len(story) > 400:
            keep = int(len(story) * .8) // 2
            story = story[:keep] + " [... earlier middle of the story omitted for length ...] " + story[-keep:]
            tail_parts[0] = "STORY_SO_FAR:\n" + story
        else:
            tail_parts.pop()
            story = ""
        tail_text = "\n\n".join(tail_parts)
    used = counter(assemble([], "" if keep_story else tail_text))
    lines = []
    for e in pinned + matching + other_global + recent:
        line = _entry_line(e, with_ids)
        cost = counter(line + "\n")
        if used + cost > token_budget:
            break
        lines.append(line)
        used += cost
    result = assemble(lines, tail_text)
    while lines and counter(assemble(lines, "" if keep_story else tail_text)) > token_budget:
        lines.pop()  # whole-text bound may exceed the sum of parts
        result = assemble(lines, tail_text)
    return result


def render_entries_for_text(notebook, text, token_budget=3000, count_tokens=None):
    """Only the pinned entries and the entries whose match terms occur in ``text``
    (for a unit reviewer); empty string when none apply."""
    counter = count_tokens or _default_counter
    pinned, matching, _, _ = _ranked_entries(notebook, text)
    header = ("BOOK_NOTEBOOK entries for this passage (earlier decisions for this book; the translation "
              "should follow them unless the source contradicts; approved terminology overrides):")
    lines, used = [], counter(header + "\n")
    for e in pinned + matching:
        line = _entry_line(e)
        cost = counter(line + "\n")
        if used + cost > token_budget:
            break
        lines.append(line)
        used += cost
    return header + "\n" + "\n".join(lines) + "\n" if lines else ""


# ---------------------------------------------------------------- markdown

def render_markdown(notebook):
    out = ["# Book notebook", ""]
    if notebook["story_so_far"]:
        out += ["## Story so far", "", notebook["story_so_far"], ""]
    groups = {}
    shadowed = _shadowed_ids(notebook["entries"])
    for e in notebook["entries"]:
        groups.setdefault(e["tags"][0], []).append(e)
    for tag in sorted(groups):
        out += ["## " + tag, ""]
        for e in groups[tag]:
            flags = []
            if e["status"] == "superseded":
                flags.append("superseded")
            if e["pinned"]:
                flags.append("pinned")
            if e["origin"] == "human":
                flags.append("human")
            if e["entry_id"] in shadowed:
                flags.append("overridden by a user term")
            head = "- **%s**" % e["title"]
            if flags:
                head += " (%s)" % ", ".join(flags)
            out.append(head + " — " + e["note"])
            if e.get("hebrew_rendering"):
                out.append("  - Hebrew: " + e["hebrew_rendering"])
            if len(e["tags"]) > 1:
                out.append("  - tags: " + ", ".join(e["tags"]))
            if e["match_terms"]:
                out.append("  - terms: " + ", ".join(e["match_terms"]))
            out.append("  - chapters: %d–%d, scope: %s" % (e["first_chapter"], e["last_chapter"], e["scope"]))
        out.append("")
    if notebook["chapter_summaries"]:
        out += ["## Chapter summaries", ""]
        for k in sorted(notebook["chapter_summaries"], key=int):
            out += ["### Chapter %s" % k, "", notebook["chapter_summaries"][k], ""]
    return "\n".join(out)
