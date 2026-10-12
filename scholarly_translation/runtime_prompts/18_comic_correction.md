# Comic Correction Runtime Prompt

An independent reviewer found problems in the {{T:TARGET}} translation of some comic balloons (translated from {{LANGUAGE}}). Correct ONLY these problems and give each listed region's complete corrected {{T:TARGET}} text. Keep everything that was not criticised exactly as it is: same words, same voice, about the same length (it must still fit its balloon).

The attached image is the page; the regions are framed in RED and labelled with their ids. Use the picture for who speaks to whom.

NOTEBOOK (binding names and terms):
{{CHARACTERS}}
{{TERMS}}

REGIONS TO CORRECT (each with its source, current translation and the reviewer's issues; a "translation_span" the reviewer quoted may not appear verbatim any more, then apply the intent of the suggested correction):
{{REGIONS}}

Rules: correct meaning, gender and number, names and idiomatic {{T:TARGET}} as the issues require; do not add explanations; add no dash (— or –) as punctuation the source lacks. {{T:NAMES_NIQQUD}}

Output ONLY one JSON object, no commentary and no code fences, with every listed id exactly once:
{"translations": [{"id": "P11.3", "text": "the complete corrected text"}]}
