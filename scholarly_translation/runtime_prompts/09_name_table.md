You build the NAME TABLE of a book before it is translated into Hebrew. Every later translation call will receive this table as binding, so each decision you make here is final for the whole book.

Profile: {{PROFILE_ID}}. Source language: {{SOURCE_LANGUAGE}}.

CANDIDATES are capitalized words and phrases found in the whole book, one per line as `- Name (count): snippet` (count = occurrences, snippet = context of the first one):

{{CANDIDATES}}

Task:
- Choose ONE Hebrew form for every real name: character, place, organization, title, or invented term (invented words, titles of rank, ranks, fictional institutions). Skip ordinary capitalized words (sentence starts, days, common nouns, ordinary words that happen to be capitalized).
- Group aliases under one entry: full name, short name, nickname, title forms, spelling variants. "source" is the most complete or most common form; "aliases" lists the other source forms. Do not list the same form twice.
- Real people, places and works that have an established Hebrew form must use that established form. Otherwise transliterate by sound, consistently.
- "gender": female, male, plural, none (not a person or no gender), or unknown. Use the snippets; if unsure, unknown.
- "kind": character, place, organization, title, term or other.
- DISTINCTNESS: every Hebrew form must be different from every other Hebrew form in the table, also after the Hebrew prefixes ו ה ב כ ל מ ש are attached. A word that starts with ו doubles that letter after a prefix: ון + ל gives לוון, which is identical to ל + וון. So two names such as Wen and Woon must not be ון and וון. Niqqud is allowed and encouraged when needed to tell two forms apart (for example שֵׁאי against שיי). Choose the forms so no two collide.
- "hebrew" must contain Hebrew letters only for the name itself (no Latin letters, no explanation). "note" is optional and short (<= 300 characters): role, meaning, why a form was chosen.

Output strict JSON only, with no text before or after it and no code fence:
{"names":[{"source":"","aliases":[],"hebrew":"","kind":"character","gender":"unknown","note":""}]}
