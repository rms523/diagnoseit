"""Match printed lab test names to catalog tests without merging different analytes.

Reports print one test many ways: "ALT (SGPT), SERUM", "C-REACTIVE PROTEIN; CRP, SERUM",
"MEAN CORPUSCULAR VOLUME (MCV), WHOLE BLOOD (Electrical Impedance)". A printed name is read several
ways (the whole name, the name without bracketed notes, and each comma, semicolon, dash-separated,
or bracketed part) and matches a catalog test when a reading equals a reading of the test's name, display name,
or an alias. Word order, plurals, and specimen or method words do not matter.

Qualifiers that make a different analyte (urine, free, hs, direct or indirect, ratio, fasting, ...)
are compared separately: a printed name matches only a catalog name or alias carrying the same
qualifiers, and only if the test's names and aliases allow every qualifier the printed name has.
So "Free T3" never becomes T3, "hsCRP" never becomes CRP, and "BUN/Creatinine Ratio" never becomes
BUN, while an alias such as "direct LDL" is how the catalog opts into merging a variant.

Every catalog test is a measurement, so a result whose value does not start with a number ("Negative",
"Absent", "G1") is never linked: it would break the test's trend. A row outside a known report section
takes one from its unit: counts per microscope field are urine microscopy, percentages are a
differential count, and cells per volume an absolute count. A user can also link a printed name the
catalog does not know to a test; those links apply to that user's results only, in sections that fit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

# Specimen, method, and filler words: ignored when comparing names.
IGNORED_WORDS = frozenset({
    'total', 'serum', 'plasma', 'whole', 'blood', 'level', 'count', 'test', 'value', 'estimation',
    'of', 'and', 'the', 'in', 'for', 'by', 'with', 'method',
    'calculated', 'calc', 'derived', 'automated', 'modified',
    'photometry', 'photometric', 'spectrophotometry', 'spectrophotometric', 'colorimetric', 'colourimetric',
    'enzymatic', 'kinetic', 'hexokinase', 'clia', 'cmia', 'eclia', 'elisa', 'eia', 'ria',
    'immunoturbidimetry', 'immunoturbidimetric', 'turbidimetry', 'turbidimetric', 'nephelometry', 'nephelometric',
    'electrical', 'impedance', 'flow', 'cytometry', 'flowcytometry', 'hplc', 'ise', 'westergren',
    'edta', 'naf', 'fluoride',
})

# Words that make a different analyte or variant, mapped to the qualifier they express.
QUALIFIER_WORDS = {
    'urine': 'urine', 'urinary': 'urine', 'csf': 'csf', 'stool': 'stool', 'fecal': 'stool', 'faecal': 'stool',
    'free': 'free', 'ionized': 'ionized', 'ionised': 'ionized',
    'direct': 'direct', 'conjugated': 'direct', 'indirect': 'indirect', 'unconjugated': 'indirect',
    'hs': 'hs', 'cardio': 'hs', 'sensitivity': 'hs', 'sensitive': 'hs', 'ultrasensitive': 'hs',
    'non': 'non', 'ratio': 'ratio', 'index': 'index',
    'absolute': 'absolute', 'abs': 'absolute', 'alc': 'absolute', 'differential': 'differential', 'dlc': 'differential',
    'fasting': 'fasting', 'random': 'random', 'pp': 'postprandial', 'postprandial': 'postprandial', 'prandial': 'postprandial',
}

# Report sections the parser tracks, and the qualifier each implies for rows inside it.
CONTEXT_QUALIFIERS = {'urine': 'urine', 'dlc': 'differential', 'alc': 'absolute'}

_BRACKET_RE = re.compile(r"\(([^()]*)\)|\[([^\[\]]*)\]")
# Commas, semicolons, and spaced dashes separate a test from notes: "TSH - CHEMILUMINESCENCE", "Hemoglobin — Photometry".
_PART_SEPARATOR_RE = re.compile(r"[,;]|\s+[-\u2013\u2014]+(?:\s+|$)")
_WORD_RE = re.compile(r"[a-z0-9]+")
# Counted per high- or low-power microscope field: urine or stool microscopy, never a blood count.
_MICROSCOPY_UNIT_RE = re.compile(r"\b[hl]pf\b", re.IGNORECASE)
# "BUN/Creatinine", "A/G": a ratio of two analytes, unlike a unit such as "cells/cumm".
_RATIO_RE = re.compile(r"[a-z]{2,}\s*/\s*(?!(?:cumm|cmm|ul|dl|ml|hpf|lpf|hr|hrs|min|day)\b)[a-z]{2,}", re.IGNORECASE)
_MEASUREMENT_RE = re.compile(r"^\s*(?:[<>]=?|\u2264|\u2265)?\s*[-+]?\d")
_PERCENT_UNIT_RE = re.compile(r"%")
# Cells per volume: "thou/mm3", "10^3/uL", "million/cumm", "cells/cumm", "lakh/cumm".
_ABSOLUTE_COUNT_UNIT_RE = re.compile(r"thou|lakh|mill|10\s*\^|x\s*10|cells|/\s*c\.?u?\.?\s*mm|/\s*mm3|/\s*[u\u00b5\u03bc]l\b", re.IGNORECASE)
# An antibody class names a total immunoglobulin only as the whole name ("IgG", "Total IgE"); as one part of a
# longer name it qualifies another test ("Herpes simplex virus 1+2, IgG"), so that part alone never matches.
_ANTIBODY_CLASS_KEYS = frozenset({'iga', 'igd', 'ige', 'igg', 'igm'})
# "E.S.R." is ESR.
_DOTTED_ABBREVIATION_RE = re.compile(r"\b(?:[a-z]\.){2,}", re.IGNORECASE)


def _words(text: str) -> list[str]:
    words: list[str] = []
    text = _DOTTED_ABBREVIATION_RE.sub(lambda match: match.group().replace('.', ''), text.casefold())
    for word in _WORD_RE.findall(text):
        if len(word) >= 5 and word.startswith('hs') and word[2:].isalpha():
            words.extend(('hs', word[2:]))  # "hsCRP" is hs + CRP
        elif len(word) > 3 and word.endswith('s') and not word.endswith(('ss', 'us', 'is')):
            words.append(word[:-1])
        else:
            words.append(word)
    return words


def _key(words: Iterable[str]) -> str:
    """The analyte words of a name in a stable order; qualifiers are compared separately."""
    return ' '.join(sorted({word for word in words if word not in IGNORED_WORDS and word not in QUALIFIER_WORDS}))


def qualifiers(text: str) -> frozenset[str]:
    """Qualifiers a name carries, such as urine, free, hs, or ratio."""
    text = str(text or '')
    found = {QUALIFIER_WORDS[word] for word in _words(text) if word in QUALIFIER_WORDS}
    if _RATIO_RE.search(text):
        found.add('ratio')
    return frozenset(found)


def is_measurement(value: object) -> bool:
    """Whether a result value can belong to a catalog test: it starts with a number, or is not known yet."""
    text = str(value if value is not None else '').strip()
    return not text or bool(_MEASUREMENT_RE.match(text))


def context_from_unit(unit: object) -> str | None:
    """The report section a unit implies for a row printed outside a known section."""
    unit = str(unit or '')
    if _MICROSCOPY_UNIT_RE.search(unit):
        return 'urine'
    if _PERCENT_UNIT_RE.search(unit):
        return 'dlc'
    if _ABSOLUTE_COUNT_UNIT_RE.search(unit):
        return 'alc'
    return None


def alias_key(text: object) -> str | None:
    """How a user's name link is looked up: the analyte words in any order, plus the name's qualifiers."""
    key = _key(_words(str(text or '')))
    if not key:
        return None
    return f"{key}|{','.join(sorted(qualifiers(text)))}"


def readings(text: str) -> list[str]:
    """Keys a name can be read as: the whole name, the name without brackets, then each part."""
    return [key for key, _ in _readings_with_parts(text)]


def _readings_with_parts(text: str) -> list[tuple[str, bool]]:
    """Each reading of a name, and whether it comes from only one part of the name."""
    text = str(text or '')
    bracketed = [round_part or square_part for round_part, square_part in _BRACKET_RE.findall(text)]
    outer_parts = _PART_SEPARATOR_RE.split(_BRACKET_RE.sub(',', text))
    bracket_parts = [part for inner in bracketed for part in _PART_SEPARATOR_RE.split(inner)]

    keys = [_key(_words(text)), _key(word for part in outer_parts for word in _words(part))]
    keys += [_key(_words(part)) for part in outer_parts + bracket_parts]
    ordered: list[tuple[str, bool]] = []
    seen: set[str] = set()
    for index, key in enumerate(keys):
        # A lone letter ("(F)", "(R)") counts only as the whole name, like potassium's "K".
        if not key or key in seen or (index > 0 and len(key) == 1):
            continue
        seen.add(key)
        ordered.append((key, index >= 2))
    return ordered


@dataclass(frozen=True)
class _Candidate:
    test_type: Any
    required: frozenset  # qualifiers of the catalog name or alias this key came from
    allowed: frozenset  # qualifiers any of the test's names or aliases carry


def allowed_qualifiers(test_type: Any) -> frozenset:
    """Every qualifier a catalog test's name, display name, or aliases carry."""
    return frozenset().union(*(qualifiers(text) for text in _texts(test_type)))


def _texts(test_type: Any) -> list[str]:
    texts = [str(test_type.name).replace('_', ' '), str(test_type.display_name)]
    return texts + [str(alias) for alias in (test_type.aliases or [])]


class TestNameMatcher:
    """Resolves printed names against a fixed set of catalog tests; build once per request or parse.

    user_aliases are (printed name, test type) links one user confirmed; they are checked before the catalog.
    """

    def __init__(self, test_types: Iterable[Any], user_aliases: Iterable[tuple[str, Any]] = ()):
        self._candidates: dict[str, list[_Candidate]] = {}
        for test_type in test_types:
            texts = _texts(test_type)
            allowed = frozenset().union(*(qualifiers(text) for text in texts))
            for text in texts:
                candidate = _Candidate(test_type, qualifiers(text), allowed)
                for key in readings(text):
                    bucket = self._candidates.setdefault(key, [])
                    if candidate not in bucket:
                        bucket.append(candidate)
        self._user_aliases: dict[str, tuple[Any, frozenset]] = {}
        for name, test_type in user_aliases:
            key = alias_key(name)
            if key:
                self._user_aliases[key] = (test_type, allowed_qualifiers(test_type))

    def match(
        self, printed: object, context: str | None = None, unit: str | None = None, value: object = None
    ) -> Any | None:
        """The one catalog test a printed name refers to, or None when none fits or several do.

        A value that does not start with a number never links (see is_measurement); leave value out to match
        a name alone. A section context (dlc, alc, urine) is applied first; without one, the unit implies one
        (see context_from_unit). A blood count section (dlc, alc) can run on past its rows, so it is dropped
        when no test fits; rows in a urine section never fall back to blood tests, since a wrong merge is
        worse than an unlinked result. A user's link applies only where its test fits the section.
        """
        if not is_measurement(value):
            return None
        context = context or context_from_unit(unit)
        text = str(printed or '')
        found = qualifiers(text)
        keys = _readings_with_parts(text)
        context_qualifier = CONTEXT_QUALIFIERS.get(context or '')
        linked = self._user_aliases.get(alias_key(text) or '')
        if linked and _link_fits(linked[1], context_qualifier):
            return linked[0]
        if context_qualifier:
            matched = self._first_fit(keys, found | {context_qualifier})
            if matched is not None or context_qualifier == 'urine':
                return matched
        return self._first_fit(keys, found)

    def _first_fit(self, keys: list[tuple[str, bool]], found: frozenset) -> Any | None:
        for key, from_part in keys:
            if from_part and key in _ANTIBODY_CLASS_KEYS:
                continue
            fits = {
                id(candidate.test_type): candidate.test_type
                for candidate in self._candidates.get(key, ())
                if candidate.required <= found <= candidate.allowed
            }
            if len(fits) == 1:
                return next(iter(fits.values()))
        return None


def _link_fits(allowed: frozenset, context_qualifier: str | None) -> bool:
    """Whether a user's link to a test with these qualifiers applies to a row in this section.

    A link to a differential or absolute count variant must agree with a blood count section, and a
    link applies in a urine section only to a urine test; other links apply in any blood count section.
    """
    if context_qualifier is None or context_qualifier in allowed:
        return True
    if context_qualifier == 'urine':
        return False
    return not allowed & {'differential', 'absolute'}
