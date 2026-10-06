"""LEARN builder C: safe RTL HTML rendering for a prepared reading chunk.

No model-supplied HTML/CSS/script ever reaches the page; only escaped source
text and escaped foreign surfaces/glosses taken from an already-validated
GeneratedChunk. Offsets are Python Unicode codepoint offsets (see
learning_contracts/GeneratedChunk); JavaScript never re-splices them.
"""
from __future__ import annotations

import html

from .learning_contracts import check_id, require

_NO_NEW_ITEMS_HE = "לא נוספו פריטי לימוד חדשים בפרק זה."


def render_chunk(source_units, generated_chunk, support_mode):
    """Returns one escaped HTML fragment string for the chunk's source units."""
    require(isinstance(source_units, list) and bool(source_units), "invalid_generation", "source_units")
    require(support_mode in ("context", "inline", "click"), "invalid_generation", "support_mode")
    require(isinstance(generated_chunk, dict) and isinstance(generated_chunk.get("edits"), list),
            "invalid_generation", "generated_chunk")
    language = generated_chunk.get('language', 'und')
    require(language in ('und', 'fr', 'de', 'es', 'yi', 'it'), 'unsupported_language')

    units_by_id = {unit["unit_id"]: unit for unit in source_units}
    edits_by_unit = {}
    for index, edit in enumerate(generated_chunk["edits"]):
        require(edit["unit_id"] in units_by_id, "invalid_generation", "edit_unit_not_rendered")
        edits_by_unit.setdefault(edit["unit_id"], []).append((index, edit))

    fragments = []
    for unit in source_units:
        unit_id = check_id(unit["unit_id"])
        text = unit["text"]
        tag = "h3" if unit["kind"] == "heading" else "p"
        unit_edits = sorted(edits_by_unit.get(unit_id, ()), key=lambda pair: pair[1]["start"])

        pieces = []
        cursor = 0
        for index, edit in unit_edits:
            require(type(edit['start']) is int and type(edit['end']) is int and
                    cursor <= edit['start'] < edit['end'] <= len(text) and
                    text[edit['start']:edit['end']] == edit['original'] and unit['kind'] != 'heading', "invalid_generation", "render_span")
            pieces.append(html.escape(text[cursor:edit["start"]]))
            pieces.append(_render_occurrence(unit_id, index, edit, support_mode, language))
            cursor = edit["end"]
        pieces.append(html.escape(text[cursor:]))

        fragments.append(
            f'<{tag} class="learning-unit" data-unit-id="{html.escape(unit_id, quote=True)}">'
            f'{"".join(pieces)}</{tag}>'
        )
    return '<div class="learning-chunk" dir="rtl">' + "".join(fragments) + "</div>"


def _render_occurrence(unit_id, index, edit, support_mode, language):
    occurrence_id = html.escape(f"{unit_id}-{index}", quote=True)
    gloss = html.escape(edit.get("gloss_he", ""), quote=True)
    foreign = html.escape(edit["replacement"])
    if support_mode == 'context':
        return (f'<bdi lang="{language}" dir="{"rtl" if language == "yi" else "ltr"}" '
                f'data-occurrence-id="{occurrence_id}" class="learning-foreign">{foreign}</bdi>')
    css_class = "learning-foreign" + (" learning-foreign-click" if support_mode == "click" else "")
    attrs = (
        f'lang="{language}" dir="{"rtl" if language == "yi" else "ltr"}" data-occurrence-id="{occurrence_id}" '
        f'class="{css_class}" data-gloss-he="{gloss}"'
    )
    if support_mode == "click":
        return (f'<bdi {attrs} tabindex="0" role="button" aria-label="הצג פירוש: {foreign}" '
                f'aria-controls="gloss-popup" aria-expanded="false">{foreign}</bdi>')
    return f'<bdi {attrs}>{foreign}<span class="learning-gloss-inline" dir="rtl" lang="he">({gloss})</span></bdi>'


def render_recap(chapter_recap):
    """Escaped RTL HTML for a merged ChapterRecap; an honest Hebrew note if empty."""
    require(isinstance(chapter_recap, dict), "missing_recap")
    vocabulary = chapter_recap.get("vocabulary") or []
    grammar = chapter_recap.get("grammar") or []
    if not vocabulary and not grammar:
        return f'<div class="learning-recap" dir="rtl"><p>{html.escape(_NO_NEW_ITEMS_HE)}</p></div>'

    items = []
    for entry in vocabulary:
        item_id = html.escape(check_id(entry["item_id"]), quote=True)
        gloss = html.escape(entry.get("gloss_he", ""))
        items.append(f'<li data-item-id="{item_id}" class="learning-recap-vocabulary">{gloss}</li>')
    for entry in grammar:
        item_id = html.escape(check_id(entry["item_id"]), quote=True)
        explanation = html.escape(entry.get("explanation_he", ""))
        items.append(f'<li data-item-id="{item_id}" class="learning-recap-grammar">{explanation}</li>')
    return '<div class="learning-recap" dir="rtl"><ul>' + "".join(items) + "</ul></div>"
