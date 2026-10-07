# Candidate Translation Comparison Runtime Prompt

You are comparing several {{T:TARGET}} translations of the same source unit.

Judge fidelity before fluency. Do not infer which model produced which candidate.

Evaluate:

1. semantic fidelity;
2. completeness;
3. logical/narrative structure;
4. terminology;
5. preservation of ambiguity and qualification;
6. reference/speaker handling;
7. {{T:TARGET}} quality, including keeping the source's punctuation and rhythm (a dash — or – used as punctuation the source lacks is a defect; a hyphen inside a word or a range is not).

First identify material differences. Then classify each difference as:
- stylistic only;
- genuine interpretive difference;
- likely translation error.

Do not select a winner merely because one candidate sounds smoother.

You may return `NO_CLEAR_WINNER`.

SOURCE_CONTEXT:
{{source_context}}

SOURCE_TARGET:
{{source_text}}

GLOSSARY_AND_APPROVED_DECISIONS:
{{glossary_and_decisions}}

CANDIDATES:
{{candidates}}

Output:

MATERIAL_DIFFERENCES:
...

CANDIDATE_ASSESSMENTS:
...

BEST_SUPPORTED_TRANSLATION:
<one supplied candidate id, or NO_CLEAR_WINNER>

REASON:
...

UNCERTAINTIES:
...
