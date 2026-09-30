"""Offline CLI: demo persists a synthetic document, inspect prints it back."""
from __future__ import annotations

import argparse
import json
import hashlib
import sys
import time
import uuid
from pathlib import Path

from .provider import ConfigValidationError, ProviderConfig, UnsupportedProviderError, build_adapter
from .records import Document, Page, RecordValidationError, Segment
from .store import deterministic_id, load_document, save_document
from .usage import UsageEvent, append_usage


def _ensure_utf8_stdio() -> None:
    """Force UTF-8 stdout/stderr regardless of caller environment/console encoding."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="strict")


SOURCE_KIND = "synthetic"
SOURCE_IDENTITY = "gate1-tiny-multilingual"
DOCUMENT_VERSION = 1

# Original tiny synthetic multilingual text: French, English, Japanese lines.
SYNTHETIC_TEXT = (
    "Ceci est un texte synthétique pour le test hors ligne.\n"
    "This is a synthetic offline test sentence.\n"
    "これは合成のオフラインテスト文です。\n"
)


def _write_source_file(output_dir: Path) -> Path:
    source_path = output_dir / "source.txt"
    output_dir.mkdir(parents=True, exist_ok=True)
    source_path.write_text(SYNTHETIC_TEXT, encoding="utf-8")
    return source_path


def _build_document(source_uri: str, input_hash: str = None) -> Document:
    document_id = deterministic_id(SOURCE_IDENTITY, str(DOCUMENT_VERSION))
    page_id = deterministic_id(SOURCE_IDENTITY, str(DOCUMENT_VERSION), "page", "1")

    lines = SYNTHETIC_TEXT.splitlines(keepends=True)
    segments = []
    offset = 0
    for order, line in enumerate(lines, start=1):
        stripped = line.rstrip("\n")
        start = offset
        end = start + len(stripped)
        segment_id = deterministic_id(
            SOURCE_IDENTITY, str(DOCUMENT_VERSION), "page", "1", "segment", str(order)
        )
        segments.append(
            Segment(
                segment_id=segment_id,
                page_id=page_id,
                order=order,
                text=stripped,
                source_char_start=start,
                source_char_end=end,
            )
        )
        offset += len(line)

    page = Page(page_id=page_id, document_id=document_id, page_number=1, segments=segments)
    return Document(
        schema_version=2,
        document_id=document_id,
        document_version=DOCUMENT_VERSION,
        language="mixed",
        source_kind=SOURCE_KIND,
        source_uri=source_uri,
        pages=[page],
        stage_id="synthetic-demo",
        stage_version=1,
        input_hash=input_hash or hashlib.sha256(SYNTHETIC_TEXT.encode("utf-8")).hexdigest(),
        status="synthetic",
        warnings=["synthetic_fixture_not_quality_evidence"],
    )


def cmd_demo(output_dir: str, config_path: str = None) -> int:
    config = ProviderConfig()
    if config_path is not None:
        try:
            raw = Path(config_path).read_text(encoding="utf-8")
            data = json.loads(raw)
            config = ProviderConfig.from_dict(data)
        except OSError as exc:
            print(f"Cannot read config: {exc.strerror}", file=sys.stderr)
            return 1
        except json.JSONDecodeError as exc:
            print(f"Invalid config JSON: {exc}", file=sys.stderr)
            return 1
        except (ConfigValidationError, UnsupportedProviderError, ValueError) as exc:
            print(f"Invalid config: {exc}", file=sys.stderr)
            return 1

    out_path = Path(output_dir)
    source_path = _write_source_file(out_path)
    document = _build_document(source_uri=source_path.resolve().as_uri(),
                               input_hash=hashlib.sha256(source_path.read_bytes()).hexdigest())

    document_path = out_path / "document.json"
    save_document(document, document_path)

    adapter = build_adapter(config)

    start = time.monotonic()
    for page in document.pages:
        for segment in page.segments:
            adapter.translate(segment.text, config.target_language)
    duration = time.monotonic() - start

    usage_path = out_path / "usage.jsonl"
    event = UsageEvent(
        run_id=str(uuid.uuid4()),
        task_id="G1-offline-skeleton",
        document_id=document.document_id,
        provider=config.provider,
        model=config.model,
        reason="demo_translate_mock",
        duration_seconds=duration,
        outcome="success",
        cost_basis="synthetic_non_billed",
    )
    append_usage(event, usage_path)

    print(f"Wrote document: {document_path}")
    print(f"Wrote source: {source_path}")
    print(f"Appended usage: {usage_path}")
    return 0


def cmd_inspect(document_path: str) -> int:
    try:
        document = load_document(Path(document_path))
    except RecordValidationError as exc:
        print(f"Invalid document: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"Document not found: {exc}", file=sys.stderr)
        return 1

    print(f"schema_version: {document.schema_version}")
    print(f"document_id: {document.document_id}")
    print(f"document_version: {document.document_version}")
    print(f"language: {document.language}")
    print(f"source_kind: {document.source_kind}")
    print(f"source_uri: {document.source_uri}")
    print(f"stage: {document.stage_id}@{document.stage_version} input_hash: {document.input_hash}")
    print(f"status: {document.status} warnings: {document.warnings}")
    for page in document.pages:
        print(f"  page_id: {page.page_id} page_number: {page.page_number}")
        for segment in page.segments:
            print(
                f"    region_id: {segment.region_id} segment_id: {segment.segment_id} order: {segment.order} "
                f"[{segment.source_char_start}:{segment.source_char_end}] "
                f"text: {segment.text!r}"
            )
    return 0


def cmd_extract_pdf(input_path: str, language: str, output_dir: str) -> int:
    try:
        from .pdf_extract import ExtractionError, extract_pdf, render_pages, write_comparison_html
    except ImportError:
        print("PDF dependencies unavailable; install requirements.txt in a local venv.", file=sys.stderr)
        return 1
    try:
        document = extract_pdf(input_path, language)
    except ExtractionError as exc:
        print(f"Extraction failed: {exc}", file=sys.stderr)
        return 1

    out_path = Path(output_dir)
    document_path = out_path / "document.json"
    save_document(document, document_path)

    try:
        image_paths = render_pages(input_path, out_path)
    except ExtractionError as exc:
        print(f"Rendering failed: {exc}", file=sys.stderr)
        return 1
    write_comparison_html(document, image_paths, out_path / "comparison.html")

    print(f"Wrote document: {document_path}")
    for image_path in image_paths:
        print(f"Wrote render: {image_path}")
    print(f"Wrote comparison: {out_path / 'comparison.html'}")
    return 0


def main(argv=None) -> int:
    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(prog="scholarly_translation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo_parser = subparsers.add_parser("demo")
    demo_parser.add_argument("--output", required=True)
    demo_parser.add_argument(
        "--config",
        default=None,
        help="Optional path to a provider config JSON file (see config.example.json). "
        "Defaults to the built-in mock config.",
    )

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("document_path")

    extract_pdf_parser = subparsers.add_parser("extract-pdf")
    extract_pdf_parser.add_argument("input")
    extract_pdf_parser.add_argument("--language", required=True)
    extract_pdf_parser.add_argument("--output", required=True)

    args = parser.parse_args(argv)

    if args.command == "demo":
        return cmd_demo(args.output, args.config)
    if args.command == "inspect":
        return cmd_inspect(args.document_path)
    if args.command == "extract-pdf":
        return cmd_extract_pdf(args.input, args.language, args.output)
    return 1


if __name__ == "__main__":
    sys.exit(main())
