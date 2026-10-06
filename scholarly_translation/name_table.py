"""Book name table (``name-table@1``): one binding Hebrew form per name.

Pure, deterministic, no I/O (beyond reading the prompt asset) and no provider
calls. A model builds the table before translation (and the notebook keeper
adds names later); this module only extracts candidates for that prompt,
validates and bounds what the model returns (never raises on model output
except ``parse_prepass_response`` when nothing usable came back), merges
add-only and renders a table excerpt. It never checks a translation.
"""
from __future__ import annotations

import copy
import re
import unicodedata
from pathlib import Path

SCHEMA = "name-table@1"
STATUSES = ("pending", "ready", "skipped")
KINDS = ("character", "person", "place", "organization", "title", "work", "term", "other")
GENDERS = ("female", "male", "plural", "none", "unknown")
ORIGINS = ("prepass", "keeper", "human")
MAX_ENTRIES = 1000
MAX_SOURCE = 80
MAX_ALIAS = 80
MAX_ALIASES = 12
MAX_HEBREW = 80
MAX_NOTE = 300
MAX_WARNINGS = 200
MAX_WARNING_LEN = 300
HEADER = ("NAMES (binding Hebrew forms for this book; use exactly these forms, Hebrew prefixes attach "
          "as usual and terms inflect as Hebrew grammar requires; two different names never share a "
          "Hebrew form):")

# Languages written in a cased (Latin) script, where a capital letter marks a name.
# Anything else (Hebrew, Arabic, CJK, Cyrillic/Greek, ...) yields no candidates.
CASED_LANGUAGES = frozenset(
    "en fr de es it pt nl ca ro sv da no nb nn fi pl cs sk sl hr hu tr id ms vi la et lv lt af sq is".split())

_PROMPT_PATH = Path(__file__).resolve().parent / "runtime_prompts" / "09_name_table.md"
_HEBREW_RE = re.compile("[א-ת]")
_WORD_RE = re.compile(r"(?<!\w)[^\W\d_](?:\w|['’\-](?=\w))*")
_OPENERS = "\"'“„‘‚«‹([{¿¡—"


class NameTableError(ValueError):
    pass


def _clip(value, limit):
    if value is None:
        return ""
    return " ".join(str(value).split())[:limit].strip()


def _nfc(value):
    return unicodedata.normalize("NFC", value)


def _key(value):
    return _nfc(value).casefold()


def _has_hebrew(value):
    return bool(_HEBREW_RE.search(value))


def new_table():
    return {"schema": SCHEMA, "status": "pending", "entries": [], "warnings": []}


def _check_entry(e, i):
    if not isinstance(e, dict):
        raise NameTableError(f"entry {i} is not an object")
    src, heb = e.get("source"), e.get("hebrew")
    if not isinstance(src, str) or not src.strip() or len(src) > MAX_SOURCE:
        raise NameTableError(f"entry {i}: invalid source")
    if not isinstance(heb, str) or len(heb) > MAX_HEBREW or not _has_hebrew(heb):
        raise NameTableError(f"entry {i}: hebrew must contain a Hebrew letter (<= {MAX_HEBREW})")
    al = e.get("aliases")
    if not isinstance(al, list) or len(al) > MAX_ALIASES:
        raise NameTableError(f"entry {i}: invalid aliases")
    for a in al:
        if not isinstance(a, str) or not a.strip() or len(a) > MAX_ALIAS or a == src:
            raise NameTableError(f"entry {i}: invalid alias")
    if e.get("kind") not in KINDS:
        raise NameTableError(f"entry {i}: invalid kind")
    if e.get("gender") not in GENDERS:
        raise NameTableError(f"entry {i}: invalid gender")
    if not isinstance(e.get("note"), str) or len(e["note"]) > MAX_NOTE:
        raise NameTableError(f"entry {i}: invalid note")
    fc = e.get("first_chapter")
    if fc is not None and (type(fc) is not int or fc < 0):
        raise NameTableError(f"entry {i}: invalid first_chapter")
    if e.get("origin") not in ORIGINS:
        raise NameTableError(f"entry {i}: invalid origin")


def validate_table(table):
    if not isinstance(table, dict):
        raise NameTableError("table is not an object")
    if table.get("schema") != SCHEMA:
        raise NameTableError("bad schema")
    if table.get("status") not in STATUSES:
        raise NameTableError("bad status")
    entries = table.get("entries")
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise NameTableError("bad entries")
    for i, e in enumerate(entries):
        _check_entry(e, i)
    warnings = table.get("warnings")
    if not isinstance(warnings, list) or not all(isinstance(w, str) for w in warnings):
        raise NameTableError("bad warnings")
    return True


# ---------------------------------------------------------------- candidates

def _is_sentence_initial(text, start):
    i = start
    while i > 0 and (text[i - 1].isspace() or text[i - 1] in _OPENERS):
        i -= 1
    return i == 0 or text[i - 1] in ".!?…" or "\n" in text[i:start]


def name_candidates(texts, language, limit=400, min_count=2, snippet_chars=160):
    """Capitalized words/sequences for the name-table prompt; ``[]`` for uncased languages."""
    lang = re.split(r"[-_]", str(language or "").strip().lower())[0]
    if lang not in CASED_LANGUAGES:
        return []
    if isinstance(texts, str):
        texts = [texts]
    found = {}    # key -> [name, count, (text_idx, pos), snippet]
    words = {}    # word -> [count, noninitial_count]
    lower_words = set()

    def bump(name, key, ti, text, start, end):
        rec = found.get(key)
        if rec is None:
            half = max(snippet_chars - (end - start), 0) // 2
            snip = _clip(text[max(0, start - half):end + half], snippet_chars)
            found[key] = rec = [name, 0, (ti, start), snip]
        rec[1] += 1

    texts = [_nfc(t) for t in texts if isinstance(t, str)]
    for text in texts:
        lower_words.update(m.group(0) for m in _WORD_RE.finditer(text) if m.group(0)[0].islower())
    for ti, text in enumerate(texts):
        run = []  # consecutive capitalized words: (word, start, end, initial)

        def flush():
            for w, s, e, init in run:
                bump(w, ("w", w), ti, text, s, e)
                rec = words.setdefault(w, [0, 0])
                rec[0] += 1
                rec[1] += 0 if init else 1
            seq = list(run)
            # A sentence-initial ordinary word ("Then Kaul Shae") is not part of the name.
            if len(seq) > 1 and seq[0][3] and seq[0][0].lower() in lower_words:
                seq = seq[1:]
            if len(seq) > 1:
                name = " ".join(w for w, _, _, _ in seq)
                bump(name, ("s", name), ti, text, seq[0][1], seq[-1][2])
            run.clear()

        prev_end = 0
        for m in _WORD_RE.finditer(text):
            w = m.group(0)
            if w[0].isupper():
                if run and re.fullmatch(r"[ \t]+", text[prev_end:m.start()]) is None:
                    flush()
                run.append((w, m.start(), m.end(), _is_sentence_initial(text, m.start())))
                prev_end = m.end()
            else:
                flush()
        flush()
    out = []
    for key, (name, count, pos, snip) in found.items():
        if count < min_count:
            continue
        if key[0] == "w" and words[name][1] == 0 and name.lower() in lower_words:
            continue
        out.append((-count, pos, {"name": name, "count": count, "snippet": snip}))
    out.sort(key=lambda t: (t[0], t[1]))
    return [o[2] for o in out[:max(int(limit), 0)]]


# -------------------------------------------------------------------- prompt

_PLACEHOLDER_RE = re.compile(
    r"\{\{(NAMES_SO_FAR|CANDIDATES|PROFILE_ID|PROFILE_GUIDANCE|SOURCE_LANGUAGE|CHAPTERS)\}\}")
_PROFILE_GUIDANCE = {
    "literary": (
        "- List every person, place, organization, title or rank, and invented term that appears in these "
        "chapters and is NOT already in NAMES_SO_FAR. Include lowercase invented terms and coinages. Skip "
        "ordinary words."),
    "scholarly": (
        "- This is a scholarly book. List every cited author, scholar or historical figure (kind person), "
        "cited work such as a book, article or text (kind work), school, movement or -ism, institution and "
        "place that appears in these chapters and is NOT already in NAMES_SO_FAR.\n"
        "- Also list the author's key technical terms and coinages: terms the author defines, distinguishes "
        "or keeps returning to (kind term). Give the base Hebrew form (singular, not in construct state); "
        "it inflects as Hebrew grammar requires. When the original term should stay in parentheses at first "
        "use, say so in \"note\". Skip ordinary vocabulary and words capitalized only by the source "
        "language's rules (German nouns, for example).\n"
        "- A work with an established Hebrew title uses it; otherwise translate the title and say so in "
        "\"note\". \"gender\" of an author matters: Hebrew verbs agree with it (טוען / טוענת)."),
}


def build_source_pass_prompt(chapters, names_text, candidates, profile_id, source_language):
    """Prompt for one source-pass step: consecutive ORIGINAL chapters ``[{"index","source"}]``."""
    blocks = []
    for ch in chapters or []:
        if not isinstance(ch, dict):
            continue
        blocks.append(f"=== CHAPTER {int(ch.get('index') or 0) + 1} ===\n{ch.get('source') or ''}")
    lines = []
    for c in candidates or []:
        if not isinstance(c, dict):
            continue
        name = _clip(c.get("name"), MAX_SOURCE)
        if name:
            lines.append(f"- {name} ({int(c.get('count') or 0)})")
    values = {
        "NAMES_SO_FAR": str(names_text or "").strip() or "(none)",
        "CANDIDATES": "\n".join(lines) if lines else "(none)",
        "PROFILE_ID": str(profile_id or "literary"),
        "PROFILE_GUIDANCE": _PROFILE_GUIDANCE["scholarly" if profile_id == "scholarly" else "literary"],
        "SOURCE_LANGUAGE": str(source_language or "unknown"),
        "CHAPTERS": "\n\n".join(blocks),
    }
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    # Single pass: text inserted for one placeholder is never scanned for others.
    return _PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], template)


# ------------------------------------------------------------------- parsing

def _clean_entry(item, origin):
    if not isinstance(item, dict):
        return None, "not an object"
    source = _clip(item.get("source"), MAX_SOURCE)
    if not source:
        return None, "missing source"
    hebrew = _clip(item.get("hebrew"), MAX_HEBREW)
    if not _has_hebrew(hebrew):
        return None, "hebrew has no Hebrew letter"
    aliases, seen = [], {_key(source)}
    raw_aliases = item.get("aliases")
    if isinstance(raw_aliases, str):
        raw_aliases = [raw_aliases]
    for a in raw_aliases if isinstance(raw_aliases, (list, tuple)) else []:
        if not isinstance(a, str):
            continue
        a = _clip(a, MAX_ALIAS)
        if a and _key(a) not in seen:
            seen.add(_key(a))
            aliases.append(a)
        if len(aliases) >= MAX_ALIASES:
            break
    kind = str(item.get("kind") or "").strip().lower()
    gender = str(item.get("gender") or "").strip().lower()
    fc = item.get("first_chapter")
    return {
        "source": source, "aliases": aliases, "hebrew": hebrew,
        "kind": kind if kind in KINDS else "other",
        "gender": gender if gender in GENDERS else "unknown",
        "note": _clip(item.get("note"), MAX_NOTE),
        "first_chapter": fc if type(fc) is int and fc >= 0 else None,
        "origin": origin,
    }, None


def parse_names(value, origin="prepass"):
    """``value`` (model output) -> ``(entries, dropped)``; never raises."""
    if origin not in ORIGINS:
        origin = "keeper"
    entries, dropped = [], []
    if not isinstance(value, (list, tuple)):
        return entries, dropped
    for i, item in enumerate(value):
        entry, reason = _clean_entry(item, origin)
        if entry is None:
            dropped.append({"index": i, "reason": reason})
        else:
            entries.append(entry)
    return entries, dropped


def parse_prepass_response(raw):
    from scholarly_translation import book_notebook
    obj, _repaired = book_notebook.extract_json_object(raw, ("names",))
    if not isinstance(obj, dict) or not isinstance(obj.get("names"), list):
        raise NameTableError("no JSON object with a names list in the model response")
    return parse_names(obj["names"], "prepass")


# --------------------------------------------------------------------- merge

def _add_warning(table, text):
    w = _clip(text, MAX_WARNING_LEN)
    if w not in table["warnings"] and len(table["warnings"]) < MAX_WARNINGS:
        table["warnings"].append(w)


def merge_names(table, entries, chapter_index, origin):
    """Add-only merge; returns ``(new_table, report)`` and never mutates the inputs."""
    validate_table(table)
    if origin not in ORIGINS:
        raise NameTableError("bad origin")
    new = copy.deepcopy(table)
    report = {"added": [], "ignored": [], "conflicts": []}
    taken = {}
    hebrew = {}
    for e in new["entries"]:
        for form in [e["source"], *e["aliases"]]:
            taken.setdefault(_key(form), e)
        hebrew.setdefault(_nfc(e["hebrew"]), e["source"])
    fc = chapter_index if type(chapter_index) is int and chapter_index >= 0 else None
    for item in entries if isinstance(entries, (list, tuple)) else []:
        entry, reason = _clean_entry(item, origin)
        if entry is None:
            src = _clip(item.get("source"), MAX_SOURCE) if isinstance(item, dict) else ""
            report["ignored"].append({"source": src, "reason": reason})
            continue
        entry["first_chapter"] = fc
        forms = [entry["source"], *entry["aliases"]]
        clash = next((f for f in forms if _key(f) in taken), None)
        if clash is not None:
            report["ignored"].append({"source": entry["source"],
                                      "reason": f"'{clash}' already in table as '{taken[_key(clash)]['source']}'"})
            continue
        if len(new["entries"]) >= MAX_ENTRIES:
            report["ignored"].append({"source": entry["source"], "reason": "table full"})
            _add_warning(new, f"name table full ({MAX_ENTRIES}); further names ignored")
            continue
        other = hebrew.get(_nfc(entry["hebrew"]))
        if other is not None:
            report["conflicts"].append({"source": entry["source"], "other": other, "hebrew": entry["hebrew"]})
            _add_warning(new, f"same Hebrew form {entry['hebrew']} for '{entry['source']}' and '{other}'")
        new["entries"].append(entry)
        report["added"].append(entry["source"])
        hebrew.setdefault(_nfc(entry["hebrew"]), entry["source"])
        for f in forms:
            taken[_key(f)] = entry
    return new, report


# -------------------------------------------------------------------- render

def _default_count(text):
    from scholarly_translation import token_counting
    return token_counting.count_tokens(text)["upper_bound"]


def _occurs(form, text):
    return re.search(r"(?<!\w)" + re.escape(form) + r"(?!\w)", text) is not None


def _line(e):
    also = f" (also: {', '.join(e['aliases'])})" if e["aliases"] else ""
    note = f" — {e['note']}" if e["note"] else ""
    return f"- {e['source']}{also} → {e['hebrew']} [{e['kind']}, {e['gender']}]{note}"


def render_names(table, text=None, token_budget=None, count_tokens=None):
    validate_table(table)
    entries = table["entries"]
    if text is not None:
        entries = [e for e in entries if any(_occurs(f, text) for f in (e["source"], *e["aliases"]))]
    if not entries:
        return ""
    counter = count_tokens or _default_count
    lines = [HEADER]
    used = counter(HEADER) if token_budget is not None else 0
    for i, e in enumerate(entries):
        line = _line(e)
        if token_budget is not None:
            cost = counter("\n" + line)
            if used + cost > token_budget:
                lines.append(f"(... {len(entries) - i} more names omitted)")
                break
            used += cost
        lines.append(line)
    return "\n".join(lines)
