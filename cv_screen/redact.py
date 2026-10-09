"""Remove protected attributes from CV text before any matching or LLM call.

Removed: name, photo markers, date of birth / age, gender, nationality, marital status,
address, email, phone, URLs, gendered pronouns and titles, and a few other protected fields
(religion, place of birth, children). The candidate's name is returned separately so the
manager-facing outputs can show it; it is never passed to extraction or matching.

Known limits (see README): employment and graduation dates still hint at age, names of
schools or clubs can hint at origin or gender, and free text is only handled by the
patterns below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CANDIDATE_TOKEN = "[CANDIDATE]"

# Labels whose whole "Label: value" segment is dropped.
PROTECTED_LABELS = {
    "name": "name",
    "full name": "name",
    "first name": "name",
    "last name": "name",
    "surname": "name",
    "address": "address",
    "home address": "address",
    "street": "address",
    "city": "address",
    "postcode": "address",
    "zip": "address",
    "email": "contact",
    "e-mail": "contact",
    "phone": "contact",
    "mobile": "contact",
    "tel": "contact",
    "telephone": "contact",
    "linkedin": "contact",
    "website": "contact",
    "date of birth": "age",
    "dob": "age",
    "born": "age",
    "birthday": "age",
    "birth date": "age",
    "age": "age",
    "place of birth": "nationality",
    "nationality": "nationality",
    "citizenship": "nationality",
    "gender": "gender",
    "sex": "gender",
    "pronouns": "gender",
    "marital status": "marital_status",
    "family status": "marital_status",
    "children": "marital_status",
    "religion": "religion",
    "photo": "photo",
}

_LABEL_RE = re.compile(
    r"^\s*(?P<label>" + "|".join(sorted(map(re.escape, PROTECTED_LABELS), key=len, reverse=True))
    + r")\s*:\s*(?P<value>.*)$",
    re.IGNORECASE,
)
_PHOTO_RE = re.compile(r"^\s*[\[(]?\s*(photo|picture|image|foto)\s*[\])]?\s*$", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_URL_RE = re.compile(r"(https?://\S+|www\.\S+|linkedin\.com/\S+)", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<![\w/])\+?\d[\d ()/.-]{7,}\d(?![\w/])")
# Dates and date ranges look like phone numbers to a naive regex ("08/2019 - 02/2022").
_DATE_LIKE_RE = re.compile(
    r"^(\d{1,2}[/.])?\d{4}([-/.]\d{1,2})?(\s*-\s*((\d{1,2}[/.])?\d{4}([-/.]\d{1,2})?))?$"
)
_AGE_RE = re.compile(r"\b(aged?\s+\d{2}|\d{2}\s*(years|yrs)\s*old)\b", re.IGNORECASE)
_TITLE_RE = re.compile(r"\b(Mr|Mrs|Ms|Miss|Mx|Herr|Frau)\b\.?\s*")
_PRONOUNS = {
    "he": "they", "she": "they", "him": "them", "his": "their", "her": "their",
    "hers": "theirs", "himself": "themselves", "herself": "themselves",
}
_PRONOUN_RE = re.compile(r"\b(" + "|".join(_PRONOUNS) + r")\b", re.IGNORECASE)
_PRONOUN_VERB_RE = re.compile(r"\b(he|she) (is|was|has)\b", re.IGNORECASE)
_VERB_FIX = {"is": "are", "was": "were", "has": "have"}
# "her" is object ("describe her as") or possessive ("her team"); "his" is always possessive.
# Look past line breaks: PDF wrapping must not change which form is chosen, or the redacted
# text would still differ by gender.
_HER_OBJECT_RE = re.compile(r"\bher\b(?=\s+(as|to|for|with|and|or|on|at|in|by)\b|\s*[.,;!?])",
                            re.IGNORECASE)
_GENDERED_WORDS_RE = re.compile(
    r"\b(male|female|man|woman|husband|wife|mother|father|mum|dad)\b", re.IGNORECASE
)
_NAME_LINE_RE = re.compile(r"^[A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*){1,3}$")
_GENERIC_TITLES = {"curriculum vitae", "cv", "resume", "résumé", "lebenslauf"}


@dataclass
class RedactionResult:
    text: str
    name: str | None
    removed: dict[str, int] = field(default_factory=dict)

    def bump(self, category: str, n: int = 1) -> None:
        if n:
            self.removed[category] = self.removed.get(category, 0) + n


def redact(text: str) -> RedactionResult:
    result = RedactionResult(text="", name=None)
    lines = text.split("\n")
    kept: list[str] = []
    skip_next = False
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            result.bump("wrapped_value")
            continue
        if _PHOTO_RE.match(line):
            result.bump("photo")
            continue
        segments = [s for s in re.split(r"\s+\|\s+|\s{2,}\|\s*|\s*\|\s{2,}", line)]
        kept_segments = []
        for seg in segments:
            m = _LABEL_RE.match(seg)
            if not m:
                kept_segments.append(seg)
                continue
            category = PROTECTED_LABELS[m.group("label").lower()]
            result.bump(category)
            if category == "name" and m.group("value").strip() and result.name is None:
                result.name = m.group("value").strip()
            # PDF wrapping can push the value onto the next line ("Marital status:\nSingle").
            if not m.group("value").strip() and seg is segments[-1]:
                skip_next = _looks_like_wrapped_value(lines, i + 1)
        if len(kept_segments) != len(segments):
            line = " | ".join(s for s in kept_segments if s.strip())
            if not line.strip():
                continue
        kept.append(line)

    if result.name is None:
        idx = _guess_name_line(kept)
        if idx is not None:
            result.name = kept.pop(idx).strip()
            result.bump("name")

    body = "\n".join(kept)
    if result.name:
        body = _remove_name(body, result.name, result)
    body, n = _EMAIL_RE.subn("", body)
    result.bump("contact", n)
    body, n = _URL_RE.subn("", body)
    result.bump("contact", n)
    phones_before = len(_PHONE_RE.findall(body))
    body = _PHONE_RE.sub(_drop_phone, body)
    result.bump("contact", phones_before - len(_PHONE_RE.findall(body)))
    body, n = _AGE_RE.subn("", body)
    result.bump("age", n)
    body, n = _TITLE_RE.subn("", body)
    result.bump("gender", n)
    body, n = _PRONOUN_VERB_RE.subn(
        lambda m: _match_case("they", m.group(1)) + " " + _VERB_FIX[m.group(2).lower()], body
    )
    result.bump("gender", n)
    body, n = _HER_OBJECT_RE.subn(lambda m: _match_case("them", m.group(0)), body)
    result.bump("gender", n)
    body, n = _PRONOUN_RE.subn(lambda m: _match_case(_PRONOUNS[m.group(1).lower()], m.group(1)),
                               body)
    result.bump("gender", n)
    body, n = _GENDERED_WORDS_RE.subn("[REDACTED]", body)
    result.bump("gender", n)

    body = "\n".join(re.sub(r"[ \t]+", " ", ln).strip(" |") for ln in body.split("\n"))
    body = re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"
    result.text = body
    return result


def _drop_phone(m: re.Match[str]) -> str:
    raw = m.group(0)
    digits = sum(ch.isdigit() for ch in raw)
    if _DATE_LIKE_RE.match(raw.strip()) or (digits < 9 and not raw.startswith("+")):
        return raw
    return ""


def _looks_like_wrapped_value(lines: list[str], idx: int) -> bool:
    if idx >= len(lines):
        return False
    nxt = lines[idx].strip()
    return bool(nxt) and len(nxt) <= 40 and ":" not in nxt and not nxt.startswith("-")


def _guess_name_line(lines: list[str]) -> int | None:
    """The first non-empty line of a CV is usually the name."""
    for idx, line in enumerate(lines[:3]):
        s = line.strip()
        if not s or s.lower() in _GENERIC_TITLES:
            continue
        if _NAME_LINE_RE.match(s) and not any(ch.isdigit() for ch in s):
            return idx
        return None
    return None


def _remove_name(body: str, name: str, result: RedactionResult) -> str:
    tokens = [t for t in re.split(r"[\s,]+", name) if len(t.strip(".")) >= 2]
    for token in sorted(tokens, key=len, reverse=True):
        pattern = re.compile(r"\b" + re.escape(token) + r"(?:'s)?\b", re.IGNORECASE)
        body, n = pattern.subn(CANDIDATE_TOKEN, body)
        result.bump("name", n)
    tok = re.escape(CANDIDATE_TOKEN)
    return re.sub(rf"{tok}(?:\s+(?:\w\.\s+)?{tok})+", CANDIDATE_TOKEN, body)


def _match_case(replacement: str, original: str) -> str:
    return replacement.capitalize() if original[:1].isupper() else replacement
