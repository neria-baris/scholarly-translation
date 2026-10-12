"""Target-language packs (audit/contracts/target_languages.md).

A pack is one editable file ``target_languages/<code>.md``: metadata lines
(``key: value``) followed by ``## KEY`` sections whose text fills the
``{{T:KEY}}`` tokens of the prompt templates. Prompt builders call
``localize`` on their *template* text before any book data is substituted,
so book content is never scanned for tokens. The active pack is a context
variable set by the job runner (``use``); it defaults to Hebrew, so code that
never sets it behaves exactly as before.
"""
from __future__ import annotations

import contextlib
import contextvars
import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT = "he"
_DIR = Path(__file__).resolve().parent / "target_languages"
_TOKEN_RE = re.compile(r"\{\{T:([A-Z0-9_]+)\}\}")
_LONE_TOKEN_LINE_RE = re.compile(r"^[ \t]*\{\{T:([A-Z0-9_]+)\}\}[ \t]*\n", re.M)
_CODE_RE = re.compile(r"^[a-z]{2,3}$")
_REQUIRED_META = ("name", "label_he", "label_en", "direction", "html_lang", "script", "name_rules", "niqqud")


class TargetLanguageError(ValueError):
    """Unknown pack, malformed pack file or unknown prompt token."""


@dataclass(frozen=True)
class Pack:
    code: str
    meta: dict
    fragments: dict = field(repr=False)

    @property
    def name(self):
        return self.meta["name"]

    @property
    def direction(self):
        return self.meta["direction"]

    @property
    def rtl(self):
        return self.meta["direction"] == "rtl"

    @property
    def html_lang(self):
        return self.meta["html_lang"]

    @property
    def hebrew_prefixes(self):
        return self.meta["name_rules"] == "hebrew_prefixes"

    @property
    def niqqud(self):
        return self.meta["niqqud"] == "yes"

    @property
    def script_re(self):
        return _compiled(self.code)

    @property
    def letters_re(self):
        return _compiled(self.code, "letters")

    def has_script(self, text):
        """True when ``text`` contains a letter of the target script."""
        return bool(self.script_re.search(text or ""))

    def ratio(self, source_language):
        """Expected target/source character ratio for a source language, or None."""
        value = self.meta.get("ratio_" + str(source_language))
        return float(value) if value else None

    def fragment(self, key):
        if key not in self.fragments:
            raise TargetLanguageError(f"target-language pack {self.code!r} has no section {key!r}")
        return self.fragments[key]


def _parse(code, text):
    meta, fragments, current, lines = {}, {}, None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                fragments[current] = "\n".join(lines).strip("\n")
            current, lines = line[3:].strip(), []
            if not re.fullmatch(r"[A-Z0-9_]+", current) or current in fragments:
                raise TargetLanguageError(f"pack {code!r}: bad or repeated section {current!r}")
        elif current is None:
            if line.strip() and not line.startswith("#"):
                key, sep, value = line.partition(":")
                if not sep:
                    raise TargetLanguageError(f"pack {code!r}: metadata line without ':'")
                meta[key.strip()] = value.strip()
        else:
            lines.append(line)
    if current is not None:
        fragments[current] = "\n".join(lines).strip("\n")
    missing = [k for k in _REQUIRED_META if not meta.get(k)]
    if missing:
        raise TargetLanguageError(f"pack {code!r}: missing metadata {missing}")
    if meta["direction"] not in ("rtl", "ltr") or meta["name_rules"] not in ("hebrew_prefixes", "exact") \
            or meta["niqqud"] not in ("yes", "no"):
        raise TargetLanguageError(f"pack {code!r}: invalid direction, name_rules or niqqud")
    re.compile(meta["script"])
    return Pack(code, meta, fragments)


_CACHE = {}
_SCRIPT_CACHE = {}


def load(code):
    if not isinstance(code, str) or not _CODE_RE.match(code):
        raise TargetLanguageError("unsupported target language")
    pack = _CACHE.get(code)
    if pack is None:
        path = _DIR / f"{code}.md"
        if not path.is_file():
            raise TargetLanguageError("unsupported target language")
        pack = _CACHE[code] = _parse(code, path.read_text(encoding="utf-8"))
    return pack


def _compiled(code, key="script"):
    rx = _SCRIPT_CACHE.get((code, key))
    if rx is None:
        meta = load(code).meta
        rx = _SCRIPT_CACHE[(code, key)] = re.compile(meta.get(key) or meta["script"])
    return rx


def available():
    """Codes of the installed packs, Hebrew first."""
    codes = sorted(p.stem for p in _DIR.glob("*.md") if _CODE_RE.match(p.stem))
    return sorted(codes, key=lambda c: (c != DEFAULT, c))


_ACTIVE = contextvars.ContextVar("target_language", default=DEFAULT)


def current():
    return load(_ACTIVE.get())


def current_code():
    return _ACTIVE.get()


@contextlib.contextmanager
def use(code):
    """Make ``code`` the active target language inside the block."""
    load(code or DEFAULT)
    token = _ACTIVE.set(code or DEFAULT)
    try:
        yield load(code or DEFAULT)
    finally:
        _ACTIVE.reset(token)


def localize(text, pack=None):
    """``text`` (a prompt template, never book data) with its ``{{T:KEY}}`` tokens filled."""
    pack = pack or current()
    if "{{T:" not in text:
        return text

    def lone(match):
        value = pack.fragment(match.group(1))
        return match.group(0) if value else ""
    text = _LONE_TOKEN_LINE_RE.sub(lone, text)
    return _TOKEN_RE.sub(lambda m: pack.fragment(m.group(1)), text)


def settings_code(settings):
    """The target language of a job's settings (jobs saved before packs are Hebrew)."""
    return (settings or {}).get("target_language") or DEFAULT
