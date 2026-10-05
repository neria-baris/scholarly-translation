"""Synthetic long-document builders for planner tests (no files, no network)."""
import random

from scholarly_translation import segmentation
from scholarly_translation.records import Document, Page, Segment
from scholarly_translation.model_config import ModelConfiguration

_WORDS = ("the scholar argued that river stone harvest memory winter letter bridge quiet "
          "lantern market crossing silver ledger orchard tower archive voice season").split()


def synthetic_document(chapters=50, chars_per_chapter=16000, seed=7, headings=True):
    rng = random.Random(seed)
    pages = []
    for number in range(1, chapters + 1):
        page_id = "page-%04d" % number
        blocks = []
        if headings:
            blocks.append(("heading", 5, "Chapter %d" % number))
        size = 0
        while size < chars_per_chapter:
            sentences = []
            for _ in range(rng.randint(3, 6)):
                words = [rng.choice(_WORDS) for _ in range(rng.randint(8, 18))]
                sentences.append(" ".join(words).capitalize() + ".")
            text = " ".join(sentences)
            blocks.append(("paragraph", None, text))
            size += len(text) + 1
        parts, segments, offset = [], [], 0
        for order, (kind, level, text) in enumerate(blocks, start=1):
            if order > 1:
                parts.append("\n")
                offset += 1
            segments.append(Segment(segment_id="seg-%04d-%04d" % (number, order), page_id=page_id, order=order,
                                    text=text, source_char_start=offset, source_char_end=offset + len(text),
                                    node_kind=kind, node_level=level))
            parts.append(text)
            offset += len(text)
        pages.append(Page(page_id=page_id, document_id="doc-synth", page_number=number, segments=segments,
                          width=None, height=None, source_text="".join(parts)))
    return Document(schema_version=3, document_id="doc-synth", document_version=1, language="en",
                    source_kind="epub", source_uri="synthetic://doc", pages=pages, stage_id="digital-text-epub",
                    stage_version=1, input_hash="a" * 64, status="needs_human", warnings=[])


def synthetic_structure(unit_policy=None, **kwargs):
    document = synthetic_document(**kwargs)
    draft = segmentation.build_structure(document, unit_policy=unit_policy)
    decisions = {}
    for reading in draft["readings"]:
        if reading["status"] == "resolved":
            continue
        usable = next((c for c in reading["alternatives"] if c["usable"]), None)
        if usable:
            decisions[reading["page_id"]] = {"origin": usable["origin"], "candidate_hash": usable["candidate_hash"],
                "actor": "test", "actor_kind": "human", "reason": "synthetic"}
    if not decisions:
        return draft
    return segmentation.build_structure(document, decisions=decisions, previous=draft, unit_policy=unit_policy)


def configuration(translator_output=128000, context=400000, qa_context=400000, qa_output=8192):
    providers = {'writer': {'type': 'openai', 'credential_env': 'WRITER_API_KEY'},
                 'critic': {'type': 'anthropic', 'credential_env': 'CRITIC_API_KEY'}}

    def role(provider, model, window, usable, cap):
        return {'provider': provider, 'model': model, 'capabilities': {
            'context_window': window, 'usable_context_tokens': usable, 'max_output_tokens': cap}}
    return ModelConfiguration.from_dict({'schema_version': 1, 'providers': providers, 'models': {
        'translator': role('writer', 'gpt-6-luna', context, context, translator_output),
        'semantic_reviewer': role('critic', 'claude-sonnet-5-5', 200000, 200000, 4096),
        'chapter_qa': role('critic', 'claude-sonnet-5-5', qa_context, qa_context, qa_output)}})
