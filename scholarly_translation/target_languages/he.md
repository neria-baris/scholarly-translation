# Target-language pack: Hebrew
# Metadata lines first, then one "## KEY" section per prompt fragment ({{T:KEY}} in templates).
# Leading/trailing blank lines of a section are ignored; an empty section removes a line that
# holds only its token. The Hebrew sections reproduce the prompts exactly as they were before
# packs existed: change them only on purpose (prompt hashes change).
name: Hebrew
label_he: עברית
label_en: Hebrew
direction: rtl
html_lang: he
script: [֑-׿]
letters: [א-ת]
name_rules: hebrew_prefixes
niqqud: yes
ratio_en: 0.8
ratio_fr: 0.7
ratio_ja: 2.2

## TARGET
Hebrew

## TARGET_UPPER
HEBREW

## TARGET_CODE
he

## LIT_REGISTER_LAYERS
biblical/rabbinic/colloquial Hebrew

## LIT_ADDRESS
Decide Hebrew grammatical gender and number deliberately
for "you" (singular/plural, masculine/feminine) and for characters

## QA_CATEGORY_NOTE

## KEEPER_NAME_FORMS
- "hebrew" is the form this chapter's translation uses, unless it would collide with another name. Every Hebrew form must stay distinct from every other name, also under the Hebrew prefixes ו ה ב כ ל מ ש; a word starting with ו doubles it after a prefix (ון + ל = לוון, which equals ל + וון). Write Hebrew forms and renderings without niqqud, as the running text writes them; use niqqud only when two names would otherwise be written alike, and only the marks that tell them apart.

## KEEPER_FIELD_NOTE

## NAMES_DISTINCTNESS
- DISTINCTNESS: every Hebrew form must differ from every Hebrew form in NAMES_SO_FAR and from every other form you list, also after the Hebrew prefixes ו ה ב כ ל מ ש are attached. A word starting with ו doubles that letter after a prefix: ון + ל gives לוון, identical to ל + וון, so Wen and Woon must not be ון and וון.

## NAMES_NIQQUD
- NIQQUD: write each Hebrew form without niqqud, exactly as it will appear in the running Hebrew text (plain spelling with matres lectionis, for example אדם בוריאס, not אָדָם בּוֹרֵיאַס). Add niqqud only when two names would otherwise be written alike or misread as each other, and then only the marks that tell them apart (for example שֵׁאי against שיי).

## NAMES_FIELD_LINE
- "hebrew" holds only the Hebrew name itself (no Latin letters, no explanation). "note" is optional and short (<= 300 characters).

## NAMES_HEADER
NAMES (binding Hebrew forms for this book; use exactly these forms, Hebrew prefixes attach as usual and terms inflect as Hebrew grammar requires; two different names never share a Hebrew form):

## NT_SCH_BASE
Give the base Hebrew form (singular, not in construct state); it inflects as Hebrew grammar requires.

## NT_SCH_GENDER
"gender" of an author matters: Hebrew verbs agree with it (טוען / טוענת).

## VOICE_KEYWORD_FORM
"hebrew" the chosen Hebrew base form without niqqud (it inflects as Hebrew grammar requires)

## VOICE_EXAMPLE
"ascend": עולה, נוסק or מטפס

## NB_GENDER
the grammatical gender (Hebrew is gendered)

## NB_TERM_BASE
the base form: singular, not in construct state

## CROSS_PREFIX_NOTE
 (Hebrew prefixes ו ה ב כ ל מ ש attach as usual)

## CROSS_VAV_NOTE
 Consider prefixes and vav doubling: a word starting with ו doubles it after a prefix, so ון + ל = לוון, the same as ל + וון.

## CROSS_SPAN_PREFIX
, without prefix letters when possible

## CROSS_NIQQUD
The Hebrew text is written without niqqud. A form that differs only in niqqud is the same form: never
report it, and never add niqqud in a correction.

## CROSS_LIT_GENDER
gender agreement of each character (verbs, adjectives, pronouns) across chapters

## CROSS_SCH_INFLECTION
normal Hebrew inflection of a term (number, construct state, prefixes) is not an inconsistency: report only a different word

## CROSS_SCH_GENDER
gender agreement of each cited author and of the addressed reader across chapters
