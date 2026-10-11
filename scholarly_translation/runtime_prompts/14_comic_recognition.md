# Comic Text Recognition Runtime Prompt

You are reading ONE comic page. The attached image is the page; a local detector has outlined candidate pieces of text in RED and numbered them 1 to {{MARK_COUNT}} (a number sits in a yellow label at the top-left of each box). The marks are only hints: one balloon may be split over several marks, one mark may cover lettering of two balloons, some marks are not text at all and some lettering has no mark. The source language is {{LANGUAGE}}. {{DIRECTION}}

Your job is to TRANSCRIBE, never to translate. Every "text" value must be the exact source-language text as lettered on the page.

Return ONE entry per balloon, thought balloon, caption box, sign or sound effect. Never merge the lettering of two balloons into one entry, even when one mark covers both; never split one balloon into several entries, even when several marks cover it. Leave out marks that are not lettering.

Fields of each entry in "regions":
- "marks": the numbers of all marks that cover this entry's lettering (an empty list when none does).
- "box": [x0, y0, x1, y1] tightly around this entry's LETTERING only (not the whole balloon), normalised to a 0..1000 grid over the whole page (x to the right, y downward, 0,0 is the top-left corner). Always required; be precise, it decides where the translation is placed.
- "kind": one of speech, thought, narration, sfx, sign, other. Speech is a spoken balloon, thought a thought balloon, narration a caption box, sfx a sound effect drawn in the art, sign lettering that is part of the scene (shop signs, notes, screens).
- "text": the exact text, line breaks joined with a single space. Keep punctuation, ellipses and capitals as printed. Write [?] for a word you cannot read; never invent text.
- "speaker": the name of the character who says it (use the character names listed below when they fit), or null for narration, signs and sound effects, or when the speaker is not visible or known.
- "speaker_gender": male, female, mixed or unknown, judged from the picture and the story so far.
- "addressee_gender": male, female, mixed or unknown for the person being spoken to (it decides grammar in the target language). Use unknown when nobody is addressed or you cannot tell.
- "order": 1, 2, 3, ... the reading order of the entries on this page. {{ORDER_RULE}}

Also return a short "summary" (one or two sentences, in English) of what happens on this page, and "characters": the characters you can identify on this page, each {"name", "gender", "appearance"} where appearance is a few words that help recognise them again (hair, clothes). Keep names consistent with the known characters.

KNOWN CHARACTERS (from earlier pages; keep these names):
{{NOTEBOOK}}

Output ONLY one JSON object, no commentary and no code fences:
{"regions": [{"marks": [1, 2], "box": [52, 30, 243, 73], "kind": "speech", "text": "...", "speaker": "...", "speaker_gender": "female", "addressee_gender": "male", "order": 1}], "summary": "...", "characters": [{"name": "...", "gender": "female", "appearance": "..."}]}
