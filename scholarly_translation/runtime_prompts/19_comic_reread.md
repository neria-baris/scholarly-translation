# Comic Source Re-reading Runtime Prompt

A reviewer doubts the transcription of some comic lettering. The attached image shows each doubted region enlarged, one under the other, each labelled with its id; the lettering is in {{LANGUAGE}}. Read it again carefully, letter by letter, as a careful human reader would, using the sentence and the earlier transcription only as hints.

Your job is to TRANSCRIBE, never to translate. Give the exact text as lettered, line breaks joined with a single space, punctuation and capitals as printed. Write [?] only for a word that truly cannot be read. If the region also shows lettering of a neighbouring balloon, transcribe only the lettering that belongs to this region's balloon.

REGIONS (id, earlier transcription, the reviewer's reading and remark):
{{REGIONS}}

Output ONLY one JSON object, no commentary and no code fences, with every listed id exactly once:
{"readings": [{"id": "P11.3", "text": "..."}]}
