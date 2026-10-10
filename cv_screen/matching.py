"""Rule-based matching of a verified profile against job criteria, and transparent ranking.

Every result is one of met / partly / not met / unknown with the CV line that supports it.
There is no numeric score: ranking is a plain sort on counts that are printed in the output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from cv_screen.job import (
    Criterion,
    EducationCriterion,
    ExperienceCriterion,
    JobSpec,
    LanguageAnyCriterion,
    LanguageCriterion,
    SkillCriterion,
)
from cv_screen.schema import (
    CEFR_ORDER,
    EDUCATION_ORDER,
    CandidateProfile,
    CriterionResult,
    Language,
)


def match_profile(profile: CandidateProfile, job: JobSpec) -> list[CriterionResult]:
    results = []
    for must, criteria in ((True, job.criteria.must_have), (False, job.criteria.nice_to_have)):
        for c in criteria:
            status, evidence, note = _evaluate(c, profile)
            results.append(CriterionResult(
                criterion_id=c.id, label=c.label, must_have=must,
                status=status, evidence=evidence, note=note,
            ))
    return results


def _evaluate(c: Criterion, p: CandidateProfile) -> tuple[str, str | None, str]:
    if isinstance(c, LanguageCriterion):
        return _language([c.language], c.min_level, p.extraction.languages)
    if isinstance(c, LanguageAnyCriterion):
        return _language(c.languages, c.min_level, p.extraction.languages)
    if isinstance(c, ExperienceCriterion):
        return _experience(c, p)
    if isinstance(c, SkillCriterion):
        return _skill(c, p)
    if isinstance(c, EducationCriterion):
        return _education(c, p)
    raise TypeError(f"unknown criterion type: {c!r}")


def _level_rank(level: str) -> int:
    return CEFR_ORDER.index(level)


def _language(wanted: list[str], min_level: str, langs: list[Language]):
    if not langs:
        return "unknown", None, "No languages listed in the CV. Ask the candidate."
    wanted_l = {w.lower() for w in wanted}
    found = [x for x in langs if x.language.lower() in wanted_l]
    if not found:
        return "not met", None, f"{' / '.join(wanted)} not listed among the CV's languages."
    with_level = [x for x in found if x.level is not None]
    if with_level:
        best = max(with_level, key=lambda x: _level_rank(x.level))
        if _level_rank(best.level) >= _level_rank(min_level):
            return "met", best.evidence, f"{best.language} {best.level} (needs {min_level})."
        if len(with_level) == len(found):
            return "partly", best.evidence, (
                f"{best.language} {best.level} is below the required {min_level}."
            )
    unclear = next(x for x in found if x.level is None)
    written = unclear.level_as_written or "no level given"
    return "unknown", unclear.evidence, (
        f"{unclear.language} listed as '{written}', not a CEFR level. Ask the candidate."
    )


def _experience(c: ExperienceCriterion, p: CandidateProfile):
    relevant = [r for r in p.extraction.experience if r.relevant_to_job]
    evidence = relevant[0].evidence if relevant else None
    years = p.years_relevant_experience
    if not p.extraction.experience:
        return "unknown", None, "No work experience found in the CV."
    if years is None:
        return "unknown", evidence, "Relevant role(s) found but without dates. Ask for dates."
    undated = (
        f" Plus {p.undated_relevant_roles} relevant role(s) without dates."
        if p.undated_relevant_roles else ""
    )
    if years >= c.min_years:
        return "met", evidence, f"{years:g} years of relevant experience (needs {c.min_years:g})."
    if c.partly_min_years is not None and years >= c.partly_min_years:
        return "partly", evidence, (
            f"{years:g} years of relevant experience (needs {c.min_years:g}).{undated}"
        )
    if p.undated_relevant_roles:
        return "unknown", evidence, (
            f"{years:g} dated years, plus undated relevant role(s). Ask for dates."
        )
    if not relevant:
        return "not met", None, "No role in the CV matches the relevant-experience definition."
    return "not met", evidence, f"{years:g} years of relevant experience (needs {c.min_years:g})."


def term_hit(term: str, text: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(term.lower()) + r"(?!\w)", text.lower()) is not None


def _skill(c: SkillCriterion, p: CandidateProfile):
    skills = p.extraction.skills
    if not skills:
        return "unknown", None, "No skills listed in the CV. Ask the candidate."
    for terms, status in ((c.any_of, "met"), (c.partly_any_of, "partly")):
        for s in skills:
            hit = next((t for t in terms if term_hit(t, s.name)), None)
            if hit:
                note = f"Skill '{s.name}' matches '{hit}'."
                if status == "partly":
                    note += " Related, but not exactly what the criterion asks for."
                return status, s.evidence, note
    return "not met", None, "None of the listed skills match: " + ", ".join(c.any_of) + "."


def _education(c: EducationCriterion, p: CandidateProfile):
    edu = p.extraction.education
    if not edu:
        return "unknown", None, "No education listed in the CV. Ask the candidate."
    ranked = [e for e in edu if e.level in EDUCATION_ORDER]
    need = EDUCATION_ORDER.index(c.min_level)
    done = [e for e in ranked if not e.in_progress]
    if done:
        best = max(done, key=lambda e: EDUCATION_ORDER.index(e.level))
        if EDUCATION_ORDER.index(best.level) >= need:
            return "met", best.evidence, f"Completed: {best.level} (needs {c.min_level} or higher)."
    ongoing = [e for e in ranked if e.in_progress and EDUCATION_ORDER.index(e.level) >= need]
    if ongoing:
        return "partly", ongoing[0].evidence, f"{ongoing[0].level} in progress, not completed yet."
    if not ranked:
        return "unknown", edu[0].evidence, "Education level unclear. Ask the candidate."
    best = max(ranked, key=lambda e: EDUCATION_ORDER.index(e.level))
    return "not met", best.evidence, f"Highest listed: {best.level} (needs {c.min_level})."


# --------------------------------------------------------------------------- Ranking

TIERS = {
    "A": "All must-haves met",
    "B": "No must-have clearly missing - check the partly/unknown items",
    "C": "At least one must-have looks not met - review before deciding",
}

RANKING_RULE = (
    "Tier first (A: all must-haves met; B: none clearly missing; C: at least one not met). "
    "Within a tier: more must-haves met, then more must-haves partly met, then more "
    "nice-to-haves met, then more nice-to-haves partly met, then fewer unknowns, then "
    "candidate ID. No hidden score, no weights."
)


@dataclass
class Counts:
    must_met: int
    must_partly: int
    must_not_met: int
    must_unknown: int
    nice_met: int
    nice_partly: int
    unknown_total: int

    @property
    def tier(self) -> str:
        if self.must_not_met:
            return "C"
        if self.must_partly or self.must_unknown:
            return "B"
        return "A"


def count(results: list[CriterionResult]) -> Counts:
    def n(must: bool, status: str) -> int:
        return sum(1 for r in results if r.must_have == must and r.status == status)

    return Counts(
        must_met=n(True, "met"), must_partly=n(True, "partly"),
        must_not_met=n(True, "not met"), must_unknown=n(True, "unknown"),
        nice_met=n(False, "met"), nice_partly=n(False, "partly"),
        unknown_total=sum(1 for r in results if r.status == "unknown"),
    )


def sort_key(candidate_id: str, c: Counts) -> tuple:
    return (c.tier, -c.must_met, -c.must_partly, -c.nice_met, -c.nice_partly,
            c.unknown_total, candidate_id)
