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


def cmd_ocr_pdf(
    input_path: str,
    document_path: str,
    language: str,
    output_dir: str,
    tesseract: str,
    tessdata_dir: str = None,
    pages=None,
    timeout: float = 30.0,
) -> int:
    try:
        from .ocr import OCRInputError, run_ocr
    except ImportError:
        print("OCR dependencies unavailable; install requirements.txt in a local venv.", file=sys.stderr)
        return 1
    try:
        document = load_document(Path(document_path))
    except RecordValidationError as exc:
        print(f"Invalid document: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"Document not found: {exc}", file=sys.stderr)
        return 1

    out_path = Path(output_dir)
    try:
        bundle = run_ocr(
            input_path,
            document,
            language=language,
            tesseract_path=tesseract,
            output_dir=out_path,
            tessdata_dir=tessdata_dir,
            timeout=timeout,
            pages=pages,
        )
    except OCRInputError as exc:
        print(f"OCR input invalid: {exc}", file=sys.stderr)
        return 1

    out_path.mkdir(parents=True, exist_ok=True)
    bundle_path = out_path / "ocr.json"
    with open(bundle_path, "w", encoding="utf-8") as handle:
        json.dump(bundle, handle, ensure_ascii=False, indent=2)

    print(f"Wrote OCR bundle: {bundle_path}")
    for page in bundle["pages"]:
        if page["image_uri"]:
            print(f"Wrote render: {page['image_uri']}")
    return 0


def _load_structure_json(path):
    """Strict JSON for source decisions and derived structure consumers."""
    from .source_reading import StructureError

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise StructureError("duplicate JSON object key")
            result[key] = value
        return result

    def finite(_):
        raise StructureError("nonfinite JSON value")

    try:
        return json.loads(Path(path).read_text(encoding="utf-8"),
                          object_pairs_hook=unique, parse_constant=finite)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise StructureError("cannot read valid UTF-8 JSON input") from None


def cmd_structure(
    document_path: str,
    output: str,
    ocr_path: str = None,
    decisions_path: str = None,
    boundaries_path: str = None,
    previous_path: str = None,
) -> int:
    from .segmentation import build_structure
    from .source_reading import StructureError

    try:
        document = Document.from_dict(_load_structure_json(document_path))
        ocr_bundle, decisions, boundaries, previous = [
            _load_structure_json(p) if p is not None else None
            for p in (ocr_path, decisions_path, boundaries_path, previous_path)
        ]
    except (RecordValidationError, StructureError):
        print("Invalid structure input.", file=sys.stderr)
        return 1

    try:
        structure = build_structure(
            document, ocr_bundle=ocr_bundle, decisions=decisions,
            boundaries=boundaries, previous=previous,
        )
    except StructureError as exc:
        print(f"Structure resolution failed: {exc}", file=sys.stderr)
        return 1

    out_path = Path(output)
    from urllib.parse import urlparse
    from urllib.request import url2pathname
    protected = [Path(p).resolve() for p in (document_path, ocr_path, decisions_path,
                                             boundaries_path, previous_path) if p is not None]
    evidence_uris = [document.source_uri] + [
        c["image"]["uri"] for r in structure["readings"] for c in r["alternatives"] if c["image"]
    ]
    protected.extend(Path(url2pathname(urlparse(uri).path)).resolve()
                     for uri in evidence_uris if urlparse(uri).scheme == "file")
    if out_path.resolve() in protected:
        print("Output must be separate from source evidence and input files.", file=sys.stderr)
        return 1
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as handle:
            json.dump(structure, handle, ensure_ascii=False, indent=2, allow_nan=False)
    except OSError:
        print("Cannot write structure output.", file=sys.stderr)
        return 1

    resolved = sum(1 for r in structure["readings"] if r["status"] == "resolved")
    print(f"Wrote structure: {out_path}")
    print(f"readings: {len(structure['readings'])} resolved: {resolved} units: {len(structure['units'])}")
    if structure["continuity"]:
        print(f"continuity findings: {len(structure['continuity'])}")
    return 0


def cmd_inspect_structure(structure_path: str) -> int:
    from .segmentation import validate_structure
    from .source_reading import StructureError

    try:
        data = _load_structure_json(structure_path)
    except StructureError as exc:
        print(f"Invalid structure: {exc}", file=sys.stderr)
        return 1

    try:
        validate_structure(data)
    except StructureError as exc:
        print(f"Invalid structure: {exc}", file=sys.stderr)
        return 1

    print(f"document_id: {data['document_id']} pdf_hash: {data['pdf_hash']}")
    print(f"revision: {data['revision']['id']} parent_revision: {data['revision']['parent_revision']}")
    for r in data["readings"]:
        print(
            f"  reading_id: {r['reading_id']} version: {r['version']} page_number: {r['page_number']} "
            f"status: {r['status']} reasons: {r['reasons']} selected: {r['selected']}"
        )
    for u in data["units"]:
        print(
            f"    unit_id: {u['unit_id']} v{u['unit_version']} page_id: {u['page_id']} "
            f"[{u['source_char_start']}:{u['source_char_end']}] status: {u['status']}"
        )
    print(f"continuity findings: {len(data['continuity'])}")
    for finding in data["continuity"]:
        print(f"  {finding}")
    return 0


def cmd_terminology(
    structure_path: str,
    glossary_path: str,
    output: str,
    memory_path: str = None,
    action_path: str = None,
) -> int:
    from .glossary import GlossaryError, new_store as new_glossary_store
    from .glossary import propose_rule, resolve_applicable, review_rule, validate_glossary
    from .segmentation import validate_structure
    from .source_reading import StructureError
    from .translation_memory import MemoryError, new_store as new_memory_store
    from .translation_memory import remember, validate_memory

    try:
        structure = _load_structure_json(structure_path)
        validate_structure(structure)
    except StructureError as exc:
        print(f"Invalid structure: {exc}", file=sys.stderr)
        return 1

    try:
        glossary = _load_structure_json(glossary_path) if Path(glossary_path).exists() else new_glossary_store()
        validate_glossary(glossary)
    except (StructureError, GlossaryError) as exc:
        print(f"Invalid glossary: {exc}", file=sys.stderr)
        return 1

    memory = new_memory_store()
    if memory_path is not None:
        try:
            memory = _load_structure_json(memory_path) if Path(memory_path).exists() else new_memory_store()
            validate_memory(memory)
        except (StructureError, MemoryError) as exc:
            print(f"Invalid memory: {exc}", file=sys.stderr)
            return 1

    action = None
    if action_path is not None:
        try:
            action = _load_structure_json(action_path)
        except StructureError as exc:
            print(f"Invalid action: {exc}", file=sys.stderr)
            return 1

    kind, resolution = None, None
    try:
        if action is not None:
            if not isinstance(action, dict):
                raise GlossaryError("action must be an object")
            kind = action.get("action")
            action_fields = {
                "propose": ({"action", "unit_id", "source_language", "source_char_start", "source_char_end", "target_term"},
                            {"scope", "loaded"}),
                "review": ({"action", "rule_id", "expected_version", "expected_rule_fingerprint",
                            "actor", "actor_kind", "reason", "status"}, {"target_term", "scope"}),
                "remember": ({"action", "unit_id", "target_text", "actor", "actor_kind", "reason"}, set()),
                "resolve": ({"action", "unit_id"}, set()),
            }
            if not isinstance(kind, str) or kind not in action_fields:
                raise GlossaryError("unknown terminology action")
            required, optional = action_fields[kind]
            if not required <= set(action) or not set(action) <= required | optional:
                raise GlossaryError("invalid terminology action fields")
            if kind == "propose":
                glossary = propose_rule(
                    glossary, structure, action["unit_id"], action["source_language"],
                    action["source_char_start"], action["source_char_end"], action["target_term"],
                    scope=action.get("scope"), loaded=action.get("loaded", False),
                )
            elif kind == "review":
                glossary = review_rule(
                    glossary, action["rule_id"], action["expected_version"],
                    action["expected_rule_fingerprint"], action["actor"], action["actor_kind"],
                    action["reason"], action["status"],
                    target_term=action.get("target_term"), scope=action.get("scope"),
                )
            elif kind == "remember":
                resolution = resolve_applicable(glossary, structure, action["unit_id"])
                memory = remember(
                    memory, structure, action["unit_id"], resolution, action["target_text"],
                    action["actor"], action["actor_kind"], action["reason"],
                )
            elif kind == "resolve":
                resolution = resolve_applicable(glossary, structure, action["unit_id"])
            else:
                raise GlossaryError("unknown terminology action")
    except (GlossaryError, MemoryError, KeyError, TypeError) as exc:
        print(f"Action failed: {exc}", file=sys.stderr)
        return 1

    out_path = Path(output)
    protected = [Path(p).resolve() for p in (structure_path, action_path) if p is not None]
    from urllib.parse import urlparse
    from urllib.request import url2pathname
    uris = [structure["source_uri"]] + [c["image"]["uri"] for r in structure["readings"]
                                       for c in r["alternatives"] if c["image"] is not None]
    try:
        protected.extend(Path(url2pathname(urlparse(uri).path)).resolve()
                         for uri in uris if urlparse(uri).scheme == "file")
    except ValueError:
        print("Invalid source evidence URI.", file=sys.stderr)
        return 1
    glossary_out_path = out_path / "glossary.json"
    memory_out_path = out_path / "memory.json"
    resolution_out_path = out_path / "resolution.json"
    write_memory = memory_path is not None or kind == "remember"
    targets = [glossary_out_path] + ([memory_out_path] if write_memory else []) \
        + ([resolution_out_path] if resolution is not None else [])
    if any(t.resolve() in protected for t in targets):
        print("Output must be separate from structure and action input files.", file=sys.stderr)
        return 1

    try:
        out_path.mkdir(parents=True, exist_ok=True)
        with open(glossary_out_path, "w", encoding="utf-8") as handle:
            json.dump(glossary, handle, ensure_ascii=False, indent=2, allow_nan=False)
        if write_memory:
            with open(memory_out_path, "w", encoding="utf-8") as handle:
                json.dump(memory, handle, ensure_ascii=False, indent=2, allow_nan=False)
        if resolution is not None:
            with open(resolution_out_path, "w", encoding="utf-8") as handle:
                json.dump(resolution, handle, ensure_ascii=False, indent=2, allow_nan=False)
    except OSError:
        print("Cannot write terminology output.", file=sys.stderr)
        return 1

    print(f"Wrote glossary: {glossary_out_path}")
    if write_memory:
        print(f"Wrote memory: {memory_out_path}")
    if resolution is not None:
        print(f"Wrote resolution: {resolution_out_path}")
        print(f"resolution status: {resolution['status']}")
    return 0


PROBE_SOURCE_TEXT = "This is a fixed synthetic diagnostic phrase for Gate 6."
PROBE_MODELS = {"mock": "mock-diagnostic-1", "openai": "gpt-6-luna"}


def cmd_probe_provider(provider: str, output_dir: str) -> int:
    from .model_adapter import (
        DiagnosticRequest,
        OpenAIConfigurationError,
        RequestValidationError,
        SYNTHETIC_MARKER,
        build_adapter,
    )

    if provider not in PROBE_MODELS:
        print(f"Unsupported provider; allowed: {sorted(PROBE_MODELS)}", file=sys.stderr)
        return 1

    out_path = Path(output_dir)
    package_dir = Path(__file__).resolve().parent
    unsafe_roots = [package_dir, package_dir.parent / "tests"]
    resolved_out = out_path.resolve()
    if any(resolved_out == root or root in resolved_out.parents for root in unsafe_roots):
        print("Output path must not be inside the source or test tree.", file=sys.stderr)
        return 1
    result_path = out_path / "probe_result.json"
    if result_path.exists():
        print(f"Refusing to overwrite existing probe result: {result_path}", file=sys.stderr)
        return 1

    source_text = PROBE_SOURCE_TEXT
    try:
        request = DiagnosticRequest(
            request_id=str(uuid.uuid4()),
            profile_id="scholarly",
            marker=SYNTHETIC_MARKER,
            source_language="en",
            target_language="he",
            source_text=source_text,
            source_sha256=hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
            prompt_version="gate6-v1",
            config_version="gate6-v1",
            provider=provider,
            model=PROBE_MODELS[provider],
        )
        adapter = build_adapter(provider, PROBE_MODELS[provider])
    except RequestValidationError as exc:
        print(f"Invalid diagnostic request: {exc}", file=sys.stderr)
        return 1

    print(f"Probing provider={provider} model={PROBE_MODELS[provider]} purpose=gate6-diagnostic")
    if provider == "openai":
        print(
            "Cost notice: at most one live call, list-price estimate below $0.01, "
            "actual charge is reported as unknown; no automatic retries."
        )

    try:
        result = adapter.run(request)
    except OpenAIConfigurationError as exc:
        print(f"OpenAI probe not configured: {exc}", file=sys.stderr)
        return 1

    try:
        out_path.mkdir(parents=True, exist_ok=True)
        with open(result_path, "x", encoding="utf-8") as handle:
            json.dump(result.to_dict(), handle, ensure_ascii=False, indent=2, allow_nan=False)
    except OSError:
        print("Cannot write probe result.", file=sys.stderr)
        return 1

    print(f"Wrote probe result: {result_path}")
    print(f"status: {result.status} duration_seconds: {result.duration_seconds:.4f}")
    print(f"token_usage: {result.token_usage} estimated_cost_usd: {result.estimated_cost_usd}")
    print(f"actual_charge: {result.actual_charge} approved: {result.approved}")
    return 0 if result.status in ("mock_placeholder", "completed_unapproved") else 1


TRANSLATE_MODELS = {"mock": "mock-translation-1", "openai": "gpt-6-luna"}


def _open_runtime_controls(
    control_store_path, task_id, max_calls, hard_list_usd, *, stage, provider, model,
    document_id, unit_id, protected_paths,
):
    """Open (or create) a control store and build its budget/cache for one call site.

    Returns one shared persistent store, task budget and raw-result cache.
    Omitted path uses the ignored default store. Mock dispatches are recorded
    as synthetic and non-billed; their usage is never a paid-provider charge.
    """
    from .model_adapter import OPENAI_MAX_OUTPUT_TOKENS, PRICING_VERSION
    from .runtime_controls import ControlStore, PersistentBudget, RuntimeCache, RuntimeControlsError, validate_store_path, DEFAULT_CONTROL_STORE

    control_store_path = DEFAULT_CONTROL_STORE if control_store_path is None else control_store_path
    resolved = validate_store_path(control_store_path, protected_paths=protected_paths)
    resolved_task_id = document_id if task_id is None else task_id
    from .runtime_controls import _identifier
    if not _identifier(resolved_task_id) or not ControlStore._valid_policy(max_calls, hard_list_usd, PRICING_VERSION, OPENAI_MAX_OUTPUT_TOKENS):
        raise RuntimeControlsError("invalid task identity or control policy")
    control_store = ControlStore(resolved, create=True)
    try:
        budget = PersistentBudget(
            control_store, resolved_task_id, max_calls=max_calls, hard_list_usd=hard_list_usd,
            stage=stage, provider=provider, model=model, document_id=document_id, unit_id=unit_id,
        )
        cache = RuntimeCache(control_store, stage=stage, provider=provider, model=model)
    except Exception:
        control_store.close()
        raise
    return control_store, budget, cache


def cmd_translate_unit(
    structure_path: str, glossary_path: str, unit_id: str, profile: str, provider: str, output_dir: str,
    control_store: str = None, task_id: str = None, max_calls: int = 3, hard_list_usd: float = 0.01,
    model_config_path: str = None,
) -> int:
    from .glossary import GlossaryError, validate_glossary
    from .model_adapter import OpenAIConfigurationError, RequestValidationError
    from .runtime_controls import RuntimeControlsError
    from .segmentation import validate_structure
    from .source_reading import StructureError
    from .translation import (
        TranslationRequestError, build_translation_request,
        build_translation_request_for_role, run_translation,
    )
    from .model_config import ModelConfigError, load_model_configuration

    try:
        structure = _load_structure_json(structure_path)
        validate_structure(structure)
    except StructureError as exc:
        print(f"Invalid structure: {exc}", file=sys.stderr)
        return 1

    try:
        glossary = _load_structure_json(glossary_path)
        validate_glossary(glossary)
    except (StructureError, GlossaryError) as exc:
        print(f"Invalid glossary: {exc}", file=sys.stderr)
        return 1

    try:
        if model_config_path:
            if provider is not None:
                raise TranslationRequestError("use either --model-config or --provider, not both")
            configuration = load_model_configuration(model_config_path)
            request = build_translation_request_for_role(
                structure, glossary, unit_id, profile, configuration, "translator",
            )
        else:
            if provider not in TRANSLATE_MODELS:
                raise TranslationRequestError(
                    f"unsupported provider; allowed legacy providers: {sorted(TRANSLATE_MODELS)}"
                )
            request = build_translation_request(
                structure, glossary, unit_id, profile, provider, TRANSLATE_MODELS[provider],
            )
    except (TranslationRequestError, RequestValidationError, ModelConfigError) as exc:
        print(f"Translation request refused: {exc}", file=sys.stderr)
        return 1
    provider, model = request.provider, request.model

    out_path = Path(output_dir)
    package_dir = Path(__file__).resolve().parent
    unsafe_roots = [package_dir, package_dir.parent / "tests"]
    resolved_out = out_path.resolve()
    if any(resolved_out == root or root in resolved_out.parents for root in unsafe_roots):
        print("Output path must not be inside the source or test tree.", file=sys.stderr)
        return 1

    from urllib.parse import urlparse
    from urllib.request import url2pathname
    protected = [Path(structure_path).resolve(), Path(glossary_path).resolve()]
    if model_config_path:
        protected.append(Path(model_config_path).resolve())
    uris = [structure["source_uri"]] + [
        c["image"]["uri"] for r in structure["readings"] for c in r["alternatives"] if c["image"] is not None
    ]
    try:
        protected.extend(
            Path(url2pathname(urlparse(uri).path)).resolve() for uri in uris if urlparse(uri).scheme == "file"
        )
    except ValueError:
        print("Invalid source evidence URI.", file=sys.stderr)
        return 1
    if any(resolved_out == item or resolved_out in item.parents for item in protected):
        print("Output must be separate from structure/glossary/source evidence.", file=sys.stderr)
        return 1

    draft_path = out_path / "translation_draft.json"
    if draft_path.exists():
        print(f"Refusing to overwrite existing translation draft: {draft_path}", file=sys.stderr)
        return 1

    print(f"Translating unit={unit_id} profile={profile} provider={provider} model={model}")
    if provider != "mock":
        print(
            "Cost notice: at most one live call and no automatic retries. "
            "The local cap is a reservation, not an account billing limit; provider-specific "
            "pricing is reported only when configured rates apply, and actual charge is unknown."
        )

    try:
        store, budget, cache = _open_runtime_controls(
            control_store, task_id, max_calls, hard_list_usd, stage="translate",
            provider=provider, model=model,
            document_id=structure["document_id"], unit_id=unit_id,
            protected_paths=protected,
        )
    except RuntimeControlsError as exc:
        print(f"Control store refused: {exc}", file=sys.stderr)
        return 1

    try:
        draft = run_translation(request, budget=budget, cache=cache)
    except OpenAIConfigurationError as exc:
        print(f"Translation provider not configured: {exc}", file=sys.stderr)
        return 1
    except TranslationRequestError as exc:
        print(f"Translation refused: {exc}", file=sys.stderr)
        return 1
    except RuntimeControlsError as exc:
        print(f"Control store refused: {exc}", file=sys.stderr)
        return 1
    finally:
        if store is not None:
            store.close()

    try:
        out_path.mkdir(parents=True, exist_ok=True)
        with open(draft_path, "x", encoding="utf-8") as handle:
            json.dump(draft, handle, ensure_ascii=False, indent=2, allow_nan=False)
    except OSError:
        print("Cannot write translation draft.", file=sys.stderr)
        return 1

    print(f"Wrote translation draft: {draft_path}")
    print(f"status: {draft['status']} approved: {draft['approved']}")
    print(f"token_usage: {draft['token_usage']} estimated_cost_usd: {draft['estimated_cost_usd']}")
    print(f"actual_charge: {draft['actual_charge']} findings: {len(draft['findings'])}")
    return 0 if draft["status"] not in ("failed_transport", "failed_empty_response") else 1


def cmd_semantic_review(
    structure_path: str, glossary_path: str, draft_path: str, provider: str, output_dir: str,
    control_store: str = None, task_id: str = None, max_calls: int = 3, hard_list_usd: float = 0.01,
    model_config_path: str = None,
) -> int:
    from .glossary import GlossaryError, validate_glossary
    from .model_adapter import OpenAIConfigurationError
    from .runtime_controls import RuntimeControlsError
    from .segmentation import validate_structure
    from .semantic_review import (
        SEMANTIC_REVIEW_MODELS, SemanticReviewRequestError,
        build_semantic_review_request, build_semantic_review_request_for_role,
        run_semantic_review,
    )
    from .model_config import ModelConfigError, load_model_configuration
    from .source_reading import StructureError

    try:
        structure = _load_structure_json(structure_path)
        validate_structure(structure)
    except StructureError as exc:
        print(f"Invalid structure: {exc}", file=sys.stderr)
        return 1

    try:
        glossary = _load_structure_json(glossary_path)
        validate_glossary(glossary)
    except (StructureError, GlossaryError) as exc:
        print(f"Invalid glossary: {exc}", file=sys.stderr)
        return 1

    try:
        draft = _load_structure_json(draft_path)
    except StructureError as exc:
        print(f"Invalid draft: {exc}", file=sys.stderr)
        return 1

    try:
        if model_config_path:
            if provider is not None:
                raise SemanticReviewRequestError("use either --model-config or --provider, not both")
            configuration = load_model_configuration(model_config_path)
            request = build_semantic_review_request_for_role(
                structure, glossary, draft, configuration, "semantic_reviewer",
            )
        else:
            if provider not in SEMANTIC_REVIEW_MODELS:
                raise SemanticReviewRequestError(
                    f"unsupported legacy review provider; allowed: {sorted(SEMANTIC_REVIEW_MODELS)}"
                )
            request = build_semantic_review_request(structure, glossary, draft, provider)
    except (SemanticReviewRequestError, ModelConfigError) as exc:
        print(f"Semantic review request refused: {exc}", file=sys.stderr)
        return 1
    provider, model = request.provider, request.model

    out_path = Path(output_dir)
    package_dir = Path(__file__).resolve().parent
    unsafe_roots = [package_dir, package_dir.parent / "tests"]
    resolved_out = out_path.resolve()
    if any(resolved_out == root or root in resolved_out.parents for root in unsafe_roots):
        print("Output path must not be inside the source or test tree.", file=sys.stderr)
        return 1

    from urllib.parse import urlparse
    from urllib.request import url2pathname
    protected = [Path(structure_path).resolve(), Path(glossary_path).resolve(), Path(draft_path).resolve()]
    if model_config_path:
        protected.append(Path(model_config_path).resolve())
    uris = [structure["source_uri"]] + [
        c["image"]["uri"] for r in structure["readings"] for c in r["alternatives"] if c["image"] is not None
    ]
    try:
        protected.extend(
            Path(url2pathname(urlparse(uri).path)).resolve() for uri in uris if urlparse(uri).scheme == "file"
        )
    except ValueError:
        print("Invalid source evidence URI.", file=sys.stderr)
        return 1
    if any(resolved_out == item or resolved_out in item.parents for item in protected):
        print("Output must be separate from structure/glossary/draft/source evidence.", file=sys.stderr)
        return 1

    review_path = out_path / "semantic_review.json"
    if review_path.exists():
        print(f"Refusing to overwrite existing semantic review: {review_path}", file=sys.stderr)
        return 1

    print(f"Reviewing unit={request.unit['unit_id']} provider={provider} model={model}")
    if provider != "mock":
        print(
            "Cost notice: at most one critic call and one correction call, with no automatic retries. "
            "The local cap is a reservation, not an account billing limit; provider-specific pricing "
            "is reported only when configured rates apply, and actual charge is unknown."
        )

    try:
        store, budget, cache = _open_runtime_controls(
            control_store, task_id, max_calls, hard_list_usd, stage="semantic_review",
            provider=provider, model=model,
            document_id=request.unit["document_id"], unit_id=request.unit["unit_id"],
            protected_paths=protected,
        )
    except RuntimeControlsError as exc:
        print(f"Control store refused: {exc}", file=sys.stderr)
        return 1

    try:
        review = run_semantic_review(request, budget=budget, cache=cache)
    except OpenAIConfigurationError as exc:
        print(f"Semantic-review provider not configured: {exc}", file=sys.stderr)
        return 1
    except SemanticReviewRequestError as exc:
        print(f"Semantic review refused: {exc}", file=sys.stderr)
        return 1
    except RuntimeControlsError as exc:
        print(f"Control store refused: {exc}", file=sys.stderr)
        return 1
    finally:
        if store is not None:
            store.close()

    try:
        out_path.mkdir(parents=True, exist_ok=True)
        with open(review_path, "x", encoding="utf-8") as handle:
            json.dump(review, handle, ensure_ascii=False, indent=2, allow_nan=False)
    except OSError:
        print("Cannot write semantic review.", file=sys.stderr)
        return 1

    print(f"Wrote semantic review: {review_path}")
    print(f"status: {review['status']} review_disposition: {review['review_disposition']} approved: {review['approved']}")
    print(f"risk_triggers: {len(review['risk_triggers'])} claims: {len(review['claims'])}")
    return 0 if not review["status"].startswith("failed_") else 1


def _load_optional_json(path):
    return _load_structure_json(path) if path is not None else None


def _protect_output(out_path, extra_inputs, structure=None):
    """Refuse writing inside the package/tests tree or colliding with input files."""
    package_dir = Path(__file__).resolve().parent
    unsafe_roots = [package_dir, package_dir.parent / "tests"]
    resolved_out = out_path.resolve()
    if any(resolved_out == root or root in resolved_out.parents for root in unsafe_roots):
        return "Output path must not be inside the source or test tree."
    protected = [Path(p).resolve() for p in extra_inputs if p is not None]
    if structure is not None:
        from urllib.parse import urlparse
        from urllib.request import url2pathname
        uris = [structure["source_uri"]] + [
            c["image"]["uri"] for r in structure["readings"]
            for c in r["alternatives"] if c["image"] is not None
        ]
        try:
            protected.extend(
                Path(url2pathname(urlparse(uri).path)).resolve()
                for uri in uris if urlparse(uri).scheme == "file"
            )
        except ValueError:
            return "Invalid source evidence URI."
    if any(resolved_out == item or resolved_out in item.parents for item in protected):
        return "Output must be separate from input files."
    return None


def cmd_human_review_render(
    structure_path: str, glossary_path: str, draft_path: str, review_path: str, output_dir: str,
) -> int:
    from .glossary import GlossaryError, validate_glossary
    from .human_review import HumanReviewRequestError, render_review_page, resolve_review_unit
    from .segmentation import validate_structure
    from .source_reading import StructureError

    try:
        structure = _load_structure_json(structure_path)
        validate_structure(structure)
    except StructureError as exc:
        print(f"Invalid structure: {exc}", file=sys.stderr)
        return 1
    try:
        glossary = _load_structure_json(glossary_path)
        validate_glossary(glossary)
    except (StructureError, GlossaryError) as exc:
        print(f"Invalid glossary: {exc}", file=sys.stderr)
        return 1
    try:
        draft = _load_structure_json(draft_path)
        review = _load_optional_json(review_path)
    except StructureError as exc:
        print(f"Invalid draft/review: {exc}", file=sys.stderr)
        return 1

    try:
        review_unit = resolve_review_unit(structure, glossary, draft, review)
    except HumanReviewRequestError as exc:
        print(f"Human review request refused: {exc}", file=sys.stderr)
        return 1

    out_path = Path(output_dir)
    problem = _protect_output(out_path, [structure_path, glossary_path, draft_path, review_path], structure)
    if problem:
        print(problem, file=sys.stderr)
        return 1

    page_path = out_path / "review.html"
    if page_path.exists():
        print(f"Refusing to overwrite existing review page: {page_path}", file=sys.stderr)
        return 1
    try:
        out_path.mkdir(parents=True, exist_ok=True)
        with open(page_path, "x", encoding="utf-8") as handle:
            handle.write(render_review_page(review_unit))
    except OSError:
        print("Cannot write review page.", file=sys.stderr)
        return 1

    print(f"Wrote review page: {page_path}")
    print(f"unit_id: {review_unit.unit['unit_id']} risk_triggers: {len(review_unit.risk_triggers)}")
    return 0


def cmd_human_review_decide(
    structure_path: str, glossary_path: str, draft_path: str, review_path: str,
    decision_path: str, previous_path: str, output_dir: str,
) -> int:
    from .glossary import GlossaryError, validate_glossary
    from .human_review import HumanReviewRequestError, resolve_review_unit, run_human_review
    from .segmentation import validate_structure
    from .source_reading import StructureError

    try:
        structure = _load_structure_json(structure_path)
        validate_structure(structure)
    except StructureError as exc:
        print(f"Invalid structure: {exc}", file=sys.stderr)
        return 1
    try:
        glossary = _load_structure_json(glossary_path)
        validate_glossary(glossary)
    except (StructureError, GlossaryError) as exc:
        print(f"Invalid glossary: {exc}", file=sys.stderr)
        return 1
    try:
        draft = _load_structure_json(draft_path)
        review = _load_optional_json(review_path)
        decision = _load_structure_json(decision_path)
        previous = _load_optional_json(previous_path)
    except StructureError as exc:
        print(f"Invalid draft/review/decision/previous: {exc}", file=sys.stderr)
        return 1

    try:
        review_unit = resolve_review_unit(structure, glossary, draft, review)
        record = run_human_review(review_unit, decision, previous)
    except HumanReviewRequestError as exc:
        print(f"Human review decision refused: {exc}", file=sys.stderr)
        return 1

    out_path = Path(output_dir)
    problem = _protect_output(
        out_path, [structure_path, glossary_path, draft_path, review_path, decision_path], structure,
    )
    if problem:
        print(problem, file=sys.stderr)
        return 1

    from .source_reading import fingerprint
    decision_key = fingerprint({
        "unit_id": record["unit_id"], "draft_hash": record["draft_hash"],
        "review_cache_key": record["review_cache_key"], "decision": decision,
    })[:16]
    record_path = out_path / f"human_review_{record['unit_id']}_{decision_key}.json"
    if record_path.exists():
        print(f"Refusing to overwrite existing decision record: {record_path}", file=sys.stderr)
        return 1
    if previous is None and list(out_path.glob(f"human_review_{record['unit_id']}_*.json")):
        print("A prior decision exists; supply --previous to preserve its history.", file=sys.stderr)
        return 1
    try:
        out_path.mkdir(parents=True, exist_ok=True)
        with open(record_path, "x", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2, allow_nan=False)
    except OSError:
        print("Cannot write decision record.", file=sys.stderr)
        return 1

    print(f"Wrote decision record: {record_path}")
    print(f"action: {record['action']} status: {record['status']} approved: {record['approved']}")
    return 0


def cmd_human_review_export(
    structure_path: str, glossary_path: str, draft_path: str, review_path: str,
    record_path: str, output_dir: str,
) -> int:
    from .glossary import GlossaryError, validate_glossary
    from .human_review import HumanReviewRequestError, export_bilingual_html, latest_decision, resolve_review_unit
    from .segmentation import validate_structure
    from .source_reading import StructureError

    try:
        structure = _load_structure_json(structure_path)
        validate_structure(structure)
    except StructureError as exc:
        print(f"Invalid structure: {exc}", file=sys.stderr)
        return 1
    try:
        glossary = _load_structure_json(glossary_path)
        validate_glossary(glossary)
    except (StructureError, GlossaryError) as exc:
        print(f"Invalid glossary: {exc}", file=sys.stderr)
        return 1
    try:
        draft = _load_structure_json(draft_path)
        review = _load_optional_json(review_path)
        record = _load_structure_json(record_path)
    except StructureError as exc:
        print(f"Invalid draft/review/record: {exc}", file=sys.stderr)
        return 1

    try:
        review_unit = resolve_review_unit(structure, glossary, draft, review)
        history_paths = sorted(Path(record_path).parent.glob(f"human_review_{review_unit.unit['unit_id']}_*.json"))
        history = [_load_structure_json(str(path)) for path in history_paths]
        if not any(item.get("record_hash") == record.get("record_hash") for item in history):
            history.append(record)
        head = latest_decision(history)
        if head is None or head.get("record_hash") != record.get("record_hash"):
            raise HumanReviewRequestError("record has been superseded by a later decision")
        exported = export_bilingual_html(review_unit, record)
    except (HumanReviewRequestError, StructureError) as exc:
        print(f"Export refused: {exc}", file=sys.stderr)
        return 1

    out_path = Path(output_dir)
    problem = _protect_output(
        out_path, [structure_path, glossary_path, draft_path, review_path, record_path], structure,
    )
    if problem:
        print(problem, file=sys.stderr)
        return 1

    export_path = out_path / "export.html"
    if export_path.exists():
        print(f"Refusing to overwrite existing export: {export_path}", file=sys.stderr)
        return 1
    try:
        out_path.mkdir(parents=True, exist_ok=True)
        with open(export_path, "x", encoding="utf-8") as handle:
            handle.write(exported)
    except OSError:
        print("Cannot write export.", file=sys.stderr)
        return 1

    print(f"Wrote bilingual export: {export_path}")
    return 0


def cmd_evaluate_pilot(manifest_path: str, output_dir: str) -> int:
    from .evaluation import EvaluationError, build_report
    from .source_reading import StructureError

    try:
        manifest = _load_structure_json(manifest_path)
    except StructureError as exc:
        print(f"Invalid manifest: {exc}", file=sys.stderr)
        return 1

    try:
        report = build_report(manifest)
    except EvaluationError as exc:
        print(f"Pilot manifest refused: {exc}", file=sys.stderr)
        return 1

    out_path = Path(output_dir)
    problem = _protect_output(out_path, [manifest_path])
    if problem:
        print(problem, file=sys.stderr)
        return 1

    report_path = out_path / "pilot_report.json"
    if report_path.exists():
        print(f"Refusing to overwrite existing pilot report: {report_path}", file=sys.stderr)
        return 1
    try:
        out_path.mkdir(parents=True, exist_ok=True)
        with open(report_path, "x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
    except OSError:
        print("Cannot write pilot report.", file=sys.stderr)
        return 1

    print(f"Wrote pilot report: {report_path}")
    print(f"status: {report['status']}")
    print(f"sample_counts: {report['sample_counts']}")
    return 0


def cmd_runtime_status(control_store_path: str, task_id: str) -> int:
    from .runtime_controls import ControlStore, RuntimeControlsError, validate_store_path

    try:
        store = ControlStore(validate_store_path(control_store_path), create=False)
    except RuntimeControlsError as exc:
        print(f"Control store refused: {exc}", file=sys.stderr)
        return 1
    try:
        status = store.status(task_id)
    except RuntimeControlsError as exc:
        print(f"Control store refused: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()

    print(f"task_id: {status['task_id']}")
    print(f"max_calls: {status['max_calls']} hard_list_usd: {status['hard_list_usd']}")
    print(f"attempted_calls: {status['attempted_calls']} settled_calls: {status['settled_calls']}")
    print(f"held_usd: {status['held_usd']} list_estimated_spent_usd: {status['list_estimated_spent_usd']}")
    print(f"stopped: {status['stopped']} cache_hits: {status['cache_hits']} cache_misses: {status['cache_misses']}")
    for event in status["events"]:
        print(
            f"  event_id: {event['event_id']} stage: {event['stage']} outcome: {event['outcome']} "
            f"reserved_usd: {event['reserved_usd']} observed_usd: {event['observed_usd']} "
            f"actual_charge: {event['actual_charge']} timestamp: {event['timestamp']}"
        )
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

    ocr_pdf_parser = subparsers.add_parser("ocr-pdf")
    ocr_pdf_parser.add_argument("input")
    ocr_pdf_parser.add_argument("document_json")
    ocr_pdf_parser.add_argument("--language", required=True)
    ocr_pdf_parser.add_argument("--output", required=True)
    ocr_pdf_parser.add_argument("--tesseract", required=True)
    ocr_pdf_parser.add_argument("--tessdata-dir", default=None)
    ocr_pdf_parser.add_argument("--pages", nargs="+", type=int, default=None)
    ocr_pdf_parser.add_argument("--timeout", type=float, default=30.0)

    structure_parser = subparsers.add_parser("structure")
    structure_parser.add_argument("document_json")
    structure_parser.add_argument("--output", required=True)
    structure_parser.add_argument("--ocr", default=None)
    structure_parser.add_argument("--decisions", default=None)
    structure_parser.add_argument("--boundaries", default=None)
    structure_parser.add_argument("--previous", default=None)

    inspect_structure_parser = subparsers.add_parser("inspect-structure")
    inspect_structure_parser.add_argument("structure_json")

    terminology_parser = subparsers.add_parser("terminology")
    terminology_parser.add_argument("structure_json")
    terminology_parser.add_argument("--glossary", required=True)
    terminology_parser.add_argument("--memory", default=None)
    terminology_parser.add_argument("--action", default=None)
    terminology_parser.add_argument("--output", required=True)

    probe_provider_parser = subparsers.add_parser("probe-provider")
    probe_provider_parser.add_argument("--provider", required=True, choices=["mock", "openai"])
    probe_provider_parser.add_argument("--output", required=True)

    translate_unit_parser = subparsers.add_parser("translate-unit")
    translate_unit_parser.add_argument("structure_json")
    translate_unit_parser.add_argument("--glossary", required=True)
    translate_unit_parser.add_argument("--unit-id", required=True)
    translate_unit_parser.add_argument("--profile", required=True, choices=["scholarly"])
    translate_unit_parser.add_argument("--provider", choices=["mock", "openai"])
    translate_unit_parser.add_argument("--model-config", default=None,
                                       help="Role-based model configuration JSON; resolves translator")
    translate_unit_parser.add_argument("--output", required=True)
    translate_unit_parser.add_argument("--control-store", default=None)
    translate_unit_parser.add_argument("--task-id", default=None)
    translate_unit_parser.add_argument("--max-calls", type=int, default=3)
    translate_unit_parser.add_argument("--hard-list-usd", type=float, default=0.01)

    semantic_review_parser = subparsers.add_parser("semantic-review")
    semantic_review_parser.add_argument("structure_json")
    semantic_review_parser.add_argument("--glossary", required=True)
    semantic_review_parser.add_argument("--draft", required=True)
    semantic_review_parser.add_argument("--provider", choices=["mock", "openai"])
    semantic_review_parser.add_argument("--model-config", default=None,
                                        help="Role-based model configuration JSON; resolves semantic_reviewer")
    semantic_review_parser.add_argument("--output", required=True)
    semantic_review_parser.add_argument("--control-store", default=None)
    semantic_review_parser.add_argument("--task-id", default=None)
    semantic_review_parser.add_argument("--max-calls", type=int, default=3)
    semantic_review_parser.add_argument("--hard-list-usd", type=float, default=0.01)

    hr_render_parser = subparsers.add_parser("human-review-render")
    hr_render_parser.add_argument("structure_json")
    hr_render_parser.add_argument("--glossary", required=True)
    hr_render_parser.add_argument("--draft", required=True)
    hr_render_parser.add_argument("--review", default=None)
    hr_render_parser.add_argument("--output", required=True)

    hr_decide_parser = subparsers.add_parser("human-review-decide")
    hr_decide_parser.add_argument("structure_json")
    hr_decide_parser.add_argument("--glossary", required=True)
    hr_decide_parser.add_argument("--draft", required=True)
    hr_decide_parser.add_argument("--review", default=None)
    hr_decide_parser.add_argument("--decision", required=True)
    hr_decide_parser.add_argument("--previous", default=None)
    hr_decide_parser.add_argument("--output", required=True)

    hr_export_parser = subparsers.add_parser("human-review-export")
    hr_export_parser.add_argument("structure_json")
    hr_export_parser.add_argument("--glossary", required=True)
    hr_export_parser.add_argument("--draft", required=True)
    hr_export_parser.add_argument("--review", default=None)
    hr_export_parser.add_argument("--record", required=True)
    hr_export_parser.add_argument("--output", required=True)

    evaluate_pilot_parser = subparsers.add_parser("evaluate-pilot")
    evaluate_pilot_parser.add_argument("manifest_json")
    evaluate_pilot_parser.add_argument("--output", required=True)

    runtime_status_parser = subparsers.add_parser("runtime-status")
    runtime_status_parser.add_argument("--control-store", required=True)
    runtime_status_parser.add_argument("--task-id", required=True)

    args = parser.parse_args(argv)

    if args.command == "demo":
        return cmd_demo(args.output, args.config)
    if args.command == "inspect":
        return cmd_inspect(args.document_path)
    if args.command == "extract-pdf":
        return cmd_extract_pdf(args.input, args.language, args.output)
    if args.command == "ocr-pdf":
        return cmd_ocr_pdf(
            args.input, args.document_json, args.language, args.output,
            args.tesseract, args.tessdata_dir, args.pages, args.timeout,
        )
    if args.command == "structure":
        return cmd_structure(
            args.document_json, args.output, args.ocr, args.decisions,
            args.boundaries, args.previous,
        )
    if args.command == "inspect-structure":
        return cmd_inspect_structure(args.structure_json)
    if args.command == "terminology":
        return cmd_terminology(
            args.structure_json, args.glossary, args.output, args.memory, args.action,
        )
    if args.command == "probe-provider":
        return cmd_probe_provider(args.provider, args.output)
    if args.command == "translate-unit":
        return cmd_translate_unit(
            args.structure_json, args.glossary, args.unit_id, args.profile, args.provider, args.output,
            args.control_store, args.task_id, args.max_calls, args.hard_list_usd,
            args.model_config,
        )
    if args.command == "semantic-review":
        return cmd_semantic_review(
            args.structure_json, args.glossary, args.draft, args.provider, args.output,
            args.control_store, args.task_id, args.max_calls, args.hard_list_usd,
            args.model_config,
        )
    if args.command == "human-review-render":
        return cmd_human_review_render(
            args.structure_json, args.glossary, args.draft, args.review, args.output,
        )
    if args.command == "human-review-decide":
        return cmd_human_review_decide(
            args.structure_json, args.glossary, args.draft, args.review,
            args.decision, args.previous, args.output,
        )
    if args.command == "human-review-export":
        return cmd_human_review_export(
            args.structure_json, args.glossary, args.draft, args.review, args.record, args.output,
        )
    if args.command == "evaluate-pilot":
        return cmd_evaluate_pilot(args.manifest_json, args.output)
    if args.command == "runtime-status":
        return cmd_runtime_status(args.control_store, args.task_id)
    return 1


if __name__ == "__main__":
    sys.exit(main())
