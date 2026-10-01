"""Prepare unapproved, reproducible source candidates from local public PDFs.

Run with --root pointing to the ignored download directory containing
source_metadata.json and the six PDFs. Writes a new candidates/ directory;
never approves text or produces gold references. No network or provider calls.
"""
import argparse
import hashlib
import html
import json
import re
from collections import Counter
from pathlib import Path

import pdfplumber


SPECS = {
    "en_logic": (2, [(200, 65, 575, 735)]),
    "en_publishing": (2, [(56, 55, 299, 733), (313, 55, 557, 733)]),
    "fr_philosophy": (3, [(55, 75, 405, 565)]),
    "fr_math_education": (3, [(80, 105, 540, 724)]),
    "ja_epistemology": (2, [(55, 50, 287, 734), (306, 50, 540, 734)]),
    "ja_books": (2, [(47, 80, 287, 775), (309, 80, 551, 775)]),
}


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def japanese_chars(value):
    return len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff]", value))


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def chunks(reading, language):
    """Keep exact full-line slices; all boundaries still require human review."""
    spans, start, end = [], 0, 0
    for line in reading["text"].splitlines(keepends=True):
        end += len(line)
        part = reading["text"][start:end]
        size = len(part) if language == "ja" else len(part.split())
        if size >= (650 if language == "ja" else 180):
            spans.append((start, end))
            start = end
    tail = reading["text"][start:end]
    if (len(tail) >= 450 if language == "ja" else len(tail.split()) >= 100):
        spans.append((start, end))
    return [(a, b) for a, b in spans if language != "ja" or
            japanese_chars(reading["text"][a:b]) >= .4 * (b - a)]


def prepare(root, output_name):
    if not output_name or Path(output_name).name != output_name or output_name in (".", ".."):
        raise ValueError("output-name must be a simple child directory name")
    output = root / output_name
    output.mkdir(exist_ok=False)
    rows = json.loads((root / "source_metadata.json").read_text(encoding="utf-8"))
    candidates, readings, source_summary = [], [], []
    for row in rows:
        source_id = row["id"]
        pdf_path = root / row["local_pdf"]
        assert pdf_path.read_bytes().startswith(b"%PDF-")
        assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == row["pdf_hash"]
        first_page, boxes = SPECS[source_id]
        pool = []
        with pdfplumber.open(pdf_path) as pdf:
            # Leave final reference-heavy pages out. Selection is provisional.
            for number in range(first_page, min(len(pdf.pages), first_page + 10)):
                page = pdf.pages[number - 1]
                for column, box in enumerate(boxes, 1):
                    crop = page.crop(box)
                    lines = sorted(crop.extract_text_lines(x_tolerance=1, strip=True),
                                   key=lambda line: (round(line["top"], 2), line["x0"]))
                    text = "\n".join(line["text"] for line in lines)
                    identity = json.dumps([row["pdf_hash"], number, box, "crop-lines-v1"], separators=(",", ":"))
                    reading = {"reading_id": digest(identity), "reading_version": 1,
                               "source_id": source_id, "pdf_hash": row["pdf_hash"],
                               "page_number": number, "column": column, "crop_bbox": box,
                               "extractor": "pdfplumber", "extractor_version": pdfplumber.__version__,
                               "extractor_options": {"x_tolerance": 1, "strip": True},
                               "origin": "unapproved_column_crop", "text": text,
                               "text_hash": digest(text), "lines": [
                                   {"text": line["text"], "bbox": [line[k] for k in ("x0", "top", "x1", "bottom")]}
                                   for line in lines]}
                    pool.append((reading, chunks(reading, row["language"])))
            # Round robin over readings spreads the provisional sample across pages.
            selected = []
            for depth in range(max((len(spans) for _, spans in pool), default=0)):
                for reading, spans in pool:
                    if depth < len(spans) and len(selected) < 12:
                        selected.append((reading, spans[depth]))
            if len(selected) != 12:
                raise ValueError(source_id + ": insufficient candidate passages")
            used_readings, rendered = set(), set()
            for reading, (start, end) in selected:
                text = reading["text"][start:end]
                number = reading["page_number"]
                image_name = f"{source_id}-page-{number}.png"
                if number not in rendered:
                    pdf.pages[number - 1].to_image(resolution=110).save(str(output / image_name))
                    rendered.add(number)
                if reading["reading_id"] not in used_readings:
                    readings.append(reading)
                    used_readings.add(reading["reading_id"])
                identity = f"{reading['reading_id']}:{start}:{end}"
                candidates.append({"candidate_id": source_id + "-" + digest(identity)[:12],
                                   "source_id": source_id, "language": row["language"],
                                   "genre": row["genre"], "pdf_hash": row["pdf_hash"],
                                   "page_number": number, "reading_id": reading["reading_id"],
                                   "reading_version": 1, "source_char_start": start,
                                   "source_char_end": end, "source_text": text,
                                   "source_text_hash": digest(text), "source_image": image_name,
                                   "crop_bbox": reading["crop_bbox"], "status": "needs_human",
                                   "whitespace_token_count": len(text.split()),
                                   "character_count": len(text), "japanese_character_count": japanese_chars(text),
                                   "approved_word_count": None, "source_approval": None,
                                   "hebrew_reference": None, "reference_approval": None,
                                   "mqm_labels": None, "warnings": ["layout_unverified", "passage_boundary_unverified",
                                   "column_crop_unapproved", "glyph_mapping_unverified", "notes_tables_formulas_may_be_present",
                                   "sample_not_representative"]})
        source_summary.append({**row, "candidate_count": 12, "sampled_pages": sorted(rendered)})
    by_reading = {r["reading_id"]: r for r in readings}
    spans = {}
    for candidate in candidates:
        reading = by_reading[candidate["reading_id"]]
        start, end = candidate["source_char_start"], candidate["source_char_end"]
        assert reading["text"][start:end] == candidate["source_text"]
        assert digest(candidate["source_text"]) == candidate["source_text_hash"]
        assert digest(reading["text"]) == reading["text_hash"]
        prior = spans.setdefault(reading["reading_id"], [])
        assert all(end <= a or start >= b for a, b in prior)
        prior.append((start, end))
    counts = Counter(c["language"] for c in candidates)
    assert counts == {"en": 24, "fr": 24, "ja": 24}
    assert len({c["source_text_hash"] for c in candidates}) == 72
    write_json(output / "readings.json", readings)
    write_json(output / "source_candidates.json", {"schema": "pilot-source-candidates@1", "status": "needs_human",
               "quality_acceptance": False, "sources": source_summary, "candidates": candidates})
    context_plans, context_sections = [], []
    for source in source_summary:
        document = json.loads((root / source["id"] / "document.json").read_text(encoding="utf-8"))
        assert document["input_hash"] == source["pdf_hash"]
        for first in source["sampled_pages"][:3]:
            numbers = [first, first + 1]
            assert all(n in source["sampled_pages"] for n in numbers)
            plan_id = f"{source['id']}-pages-{first}-{first + 1}"
            page_records = [{"page_number": n, "page_id": document["pages"][n - 1]["page_id"],
                             "primary_text_hash": digest(document["pages"][n - 1]["source_text"]),
                             "image": f"{source['id']}-page-{n}.png"} for n in numbers]
            context_plans.append({"context_plan_id": plan_id, "source_id": source["id"],
                                  "pdf_hash": source["pdf_hash"], "language": source["language"],
                                  "primary_document": f"../{source['id']}/document.json",
                                  "pages": page_records, "status": "needs_human", "human_approval": None,
                                  "reading_ids": [x["reading_id"] for x in readings
                                                  if x["source_id"] == source["id"] and x["page_number"] in numbers],
                                  "candidate_ids": [c["candidate_id"] for c in candidates
                                                    if c["source_id"] == source["id"] and c["page_number"] in numbers],
                                  "warnings": ["context_not_run", "reading_order_unverified", "overlapping_context_windows"]})
            context_sections.append(f'<section><h2>{plan_id}</h2><p>Human approval pending; context comparison not run.</p>'
                                    + ''.join(f'<img style="width:48%" src="{p["image"]}" alt="Source PDF page {p["page_number"]}">'
                                              for p in page_records) + '</section>')
    assert len(context_plans) == 18
    write_json(output / "context_plans.json", {"schema": "pilot-context-plans@1", "status": "needs_human", "plans": context_plans})
    (output / "context_review.html").write_text('<!doctype html><html lang="en"><meta charset="utf-8">'
        '<title>Gate 10 context plans</title><h1>18 unapproved two-page context plans</h1>'
        '<p>Six per source language. Adjacent windows overlap and are not additional independent source segments. '
        'Review source order before any experiment.</p>' + ''.join(context_sections) + '</html>', encoding="utf-8")
    sections = []
    for c in candidates:
        row = next(r for r in rows if r["id"] == c["source_id"])
        sections.append(f'<section id="{c["candidate_id"]}"><h2>{c["candidate_id"]} ({c["language"]})</h2>'
                        f'<p>{html.escape(row["attribution"])}; {html.escape(row["license"])}</p>'
                        f'<p>PDF page {c["page_number"]}; crop bbox {c["crop_bbox"]}; span '
                        f'{c["source_char_start"]}:{c["source_char_end"]}. All approvals pending.</p>'
                        f'<p><a href="../{row["local_pdf"]}#page={c["page_number"]}">Original PDF</a> | '
                        f'<a href="{html.escape(row["url"], quote=True)}">Publisher</a></p>'
                        f'<div><img src="{c["source_image"]}" alt="Original source page">'
                        f'<pre>{html.escape(c["source_text"])}</pre></div></section>')
    (output / "review.html").write_text('<!doctype html><html lang="en"><meta charset="utf-8">'
        '<title>Gate 10 candidate source review</title><style>body{font-family:system-ui;margin:2rem}'
        'section{border-top:1px solid #aaa;margin-top:2rem}section div{display:grid;grid-template-columns:1fr 1fr;gap:1rem}'
        'img{max-width:100%}pre{white-space:pre-wrap;font-family:inherit}@media(max-width:800px){section div{display:block}}</style>'
        '<h1>72 source candidates: human review pending</h1><p>24 each in English, French and Japanese. '
        'These are exact extracted slices of unapproved cropped readings, separate from primary document.json. '
        'Check reading order, footnotes, formulas, boundaries and source language against the PDF. '
        'Japanese character and whitespace counts are not approved word counts. Hebrew references and MQM labels are empty. '
        'No translation quality or model recommendation is established.</p>'
        '<p><a href="context_review.html">Review 18 two-page context plans</a></p>' + ''.join(sections) + '</html>', encoding="utf-8")
    summary = {"schema": "pilot-source-preparation-summary@1", "status": "needs_human", "counts": dict(counts),
               "source_count": len(rows), "reading_count": len(readings), "span_checks_passed": len(candidates),
               "context_plan_count": len(context_plans),
               "manifest_hash": hashlib.sha256((output / "source_candidates.json").read_bytes()).hexdigest(),
               "readings_hash": hashlib.sha256((output / "readings.json").read_bytes()).hexdigest(),
               "context_plans_hash": hashlib.sha256((output / "context_plans.json").read_bytes()).hexdigest(),
               "sources": source_summary}
    write_json(output / "verification.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "sources"}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output-name", default="candidates")
    args = parser.parse_args()
    prepare(args.root.resolve(), args.output_name)
