"""Reproduce the licensed 500-word reference lists; not a runtime dependency.

Only the Python standard library is used. Network is needed only for --download.
Downloaded source snapshots remain in ignored outputs/, outside delivered data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import urllib.request

SOURCE_COMMIT = "525f9b560de45753a5ea01069454e72e9aa541c6"
SOURCE_REPO = "https://github.com/hermitdave/FrequencyWords"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
LANGUAGES = {
    "fr": "צרפתית", "de": "גרמנית", "es": "ספרדית",
    "yi": "יידיש", "it": "איטלקית",
}
RAW_BASE = f"https://raw.githubusercontent.com/hermitdave/FrequencyWords/{SOURCE_COMMIT}"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SNAPSHOTS = ROOT / "outputs" / "learning_wordlist_sources" / SOURCE_COMMIT
YIDDISH_REVISION = 71268025
YIDDISH_URL = f"https://en.wiktionary.org/w/index.php?title=Wiktionary:Frequency_lists/Yiddish/Newspaper_top_600&oldid={YIDDISH_REVISION}"
YIDDISH_API = f"https://en.wiktionary.org/w/api.php?action=parse&oldid={YIDDISH_REVISION}&prop=wikitext&format=json"
YIDDISH_SNAPSHOT = SNAPSHOTS.parent / f"wiktionary_yi_{YIDDISH_REVISION}.json"


def lexical_token(word: str) -> bool:
    """Retain letters with optional internal apostrophes/hyphens; no digits."""
    cleaned = word
    for delimiter in ("’", "-", "־", "׳"):
        cleaned = cleaned.replace(delimiter, "'")
    parts = cleaned.split("'")
    return bool(parts) and all(
        part and any(c.isalpha() for c in part)
        and all(c.isalpha() or unicodedata.category(c).startswith("M") for c in part)
        for part in parts
    )


def select_words(text: str) -> list[dict]:
    rows = []
    seen = set()
    previous_count = None
    for source_rank, line in enumerate(text.splitlines(), 1):
        word, count_text = line.rsplit(" ", 1)
        count = int(count_text)
        if count < 0 or (previous_count is not None and count > previous_count):
            raise ValueError(f"source frequency order invalid at {source_rank}")
        previous_count = count
        normalized = unicodedata.normalize("NFC", word)
        key = normalized.casefold()
        if not lexical_token(normalized) or key in seen:
            continue
        seen.add(key)
        rows.append({"rank": len(rows) + 1, "source_rank": source_rank,
                     "word": normalized, "corpus_count": count})
        if len(rows) == 500:
            break
    if len(rows) != 500:
        raise ValueError("source does not contain 500 distinct lexical forms")
    return rows


def fetch(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "scholarly-translation-wordlists"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(8_000_001)
    if len(data) > 8_000_000:
        raise ValueError("unexpectedly large source")
    data.decode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    if args.download:
        for language in LANGUAGES:
            if language == "yi":
                continue
            fetch(f"{RAW_BASE}/content/2018/{language}/{language}_50k.txt",
                  SNAPSHOTS / f"{language}_50k.txt")
        fetch(f"{RAW_BASE}/README.md", SNAPSHOTS / "README.md")
        fetch(YIDDISH_API, YIDDISH_SNAPSHOT)

    source_notice = (SNAPSHOTS / "README.md").read_text(encoding="utf-8")
    if "CC-by-sa-4.0 for content" not in source_notice:
        raise ValueError("source data license declaration changed or missing")
    result = {
        "schema_version": 1,
        "dataset_id": "european-common-500-forms@1",
        "license": "CC-BY-SA-4.0", "license_url": LICENSE_URL,
        "selection": {"count_per_language": 500, "unit": "surface_form",
                      "order": "descending source corpus count",
                      "changes": "NFC, casefold deduplication, non-lexical token filtering, first 500",
                      "semantic_curation": False, "hebrew_glosses_included": False,
                      "limitations": "Not lemmas, aligned concepts, CEFR levels, or universal usefulness ranking."},
        "languages": {},
    }
    for language, name in LANGUAGES.items():
        if language == "yi":
            raw = YIDDISH_SNAPSHOT.read_bytes()
            wiki = json.loads(raw)["parse"]["wikitext"]["*"]
            pairs = re.findall(r"\{\{l\|yi\|([^|}]+)(?:\|[^}]*)?\}\}\s*\((\d+)\)", wiki)
            if len(pairs) < 550:
                raise ValueError("Yiddish source parse lost entries")
            rows = select_words("\n".join(f"{word} {count}" for word, count in pairs))
            url = YIDDISH_URL
            credit = "Wiktionary contributors / ייִדיש לעבט project"
            corpus = "פֿאָרווערטס / ווײַטער newspapers, September 2006 to March 2008"
            version = str(YIDDISH_REVISION)
            attribution = {"author": credit, "project": "Wiktionary Yiddish Newspaper top 600",
                           "source_url": url, "source_revision": YIDDISH_REVISION,
                           "history_url": "https://en.wiktionary.org/w/index.php?title=Wiktionary:Frequency_lists/Yiddish/Newspaper_top_600&action=history",
                           "corpus": corpus, "license": "CC-BY-SA-4.0", "license_url": LICENSE_URL}
        else:
            raw = (SNAPSHOTS / f"{language}_50k.txt").read_bytes()
            rows = select_words(raw.decode("utf-8"))
            url = f"{RAW_BASE}/content/2018/{language}/{language}_50k.txt"
            credit = "Hermit Dave / FrequencyWords"
            corpus = "OPUS OpenSubtitles2018"
            version = SOURCE_COMMIT
            attribution = {"author": "Hermit Dave", "project": "FrequencyWords",
                           "repository_url": SOURCE_REPO, "source_url": url,
                           "source_commit": SOURCE_COMMIT, "corpus": corpus,
                           "corpus_url": "https://opus.nlpl.eu/OpenSubtitles2018.php",
                           "license": "CC-BY-SA-4.0", "license_url": LICENSE_URL}
        result["languages"][language] = {
            "name_he": name, "source_url": url,
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "attribution": attribution, "words": rows,
        }
        lines = [f"# {name}: 500 צורות מילים נפוצות", "",
                 f"רשימת מועמדות ללמידה, לפי שכיחות בקורפוס: {corpus}.",
                 "אלה צורות כתובות, כולל נטיות ומילות תפקוד; אין כאן פירושים בעברית,",
                 "איחוד לצורת בסיס או הבטחה שזהו דירוג השימושיות לכל קורא.",
                 "ייתכנו שמות, סלנג ומילים גסות. אין סינון סמנטי או דירוג CEFR.", "",
                 f"מקור וייחוס: [{credit}]({url}).",
                 f"רישיון הנתונים: [CC BY-SA 4.0]({LICENSE_URL}); שמרו את הייחוס והרישיון עם העתקת הרשימה.",
                 f"גרסת המקור: `{version}`.",
                 "שינויים: נרמול NFC, סילוק כפילויות ללא תלות ברישיות וטוקנים שאינם מילים; בחירת 500 הראשונות.",
                 "דירוג המקור נשמר בנפרד. מונים מתייחסים לקורפוס ואינם בני השוואה בין שפות.", "",
                 "| דירוג נבחר | מילה | דירוג במקור | הופעות בקורפוס |",
                 "|---:|---|---:|---:|"]
        for row in rows:
            lines.append(f"| {row['rank']} | {row['word']} | {row['source_rank']} | {row['corpus_count']} |")
        (HERE / f"{language}_500.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"{language}: {len(rows)} distinct forms, source ranks 1..{rows[-1]['source_rank']}")
    (HERE / "european_500.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PASS: five lists, 2500 forms; provenance and data license included.")


if __name__ == "__main__":
    main()
