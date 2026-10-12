# Learning dictionary entries runtime asset — learning-dictionary@1

Appended to the learning generation instructions for preparations started with
dictionary entries. No extra call: entries arrive in the same chunk response.

## Instructions (appended after the generation instructions)

Add the field "dictionary_entries" to the same response object: an array with a
real learner's-dictionary entry for every
lexical item (word or phrase) that one of your accepted edits uses and that is
listed in DICTIONARY_NEEDED or newly defined in introduced_items. Never write
entries for grammar items, for unused items, or for items not in those lists.
Each entry:
{"item_id":"existing or local id","part_of_speech":"noun|verb|adjective|adverb|
pronoun|preposition|conjunction|determiner|numeral|interjection|phrase|other",
"gender":"masculine|feminine|neuter|common" or null (nouns, and adjectives or
pronouns only when gender is inherent; otherwise null),
"senses_he":["main Hebrew meaning", "...up to 4 common meanings"],
"forms":[{"label_he":"רבים","form":"maisons"}],
"notes_he":"short usage note or empty"}
forms is the core inflection a learner needs, with Hebrew labels: for nouns
singular/plural (and case forms where the language has them, e.g. German
nominative/genitive, article included); for adjectives masculine/feminine and
plural; for verbs the infinitive, present tense by person, one past form
(participle or preterite as the language uses) and, if useful, future; for
other words the forms that exist. At most 16 forms, standard spelling (standard
Yiddish orthography). Do not invent forms you are unsure of; omit them.
