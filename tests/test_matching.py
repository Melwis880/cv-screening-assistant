import pytest

from cv_screen.matching import Counts, count, match_profile, sort_key
from cv_screen.schema import (
    CandidateProfile,
    Education,
    Experience,
    Extraction,
    Language,
    Skill,
)


def profile(skills=(), languages=(), education=(), experience=(), years=None, undated=0):
    return CandidateProfile(
        candidate_id="c", source_file="c.txt",
        extraction=Extraction(skills=list(skills), languages=list(languages),
                              education=list(education), experience=list(experience)),
        years_relevant_experience=years, undated_relevant_roles=undated,
    )


def lang(name, level, written=None):
    return Language(language=name, level=level, level_as_written=written or level,
                    evidence=f"{name}: {written or level}")


def role(relevant=True):
    return Experience(title="Agent", start="2020-01", end="present", relevant_to_job=relevant,
                      evidence="Agent - 2020")


def status(p, job, cid):
    return next(r for r in match_profile(p, job) if r.criterion_id == cid)


@pytest.mark.parametrize("languages,expected", [
    ([lang("English", "C2")], "met"),
    ([lang("English", "native")], "met"),
    ([lang("English", "C1")], "met"),
    ([lang("English", "B2")], "partly"),
    ([lang("English", None, "fluent")], "unknown"),
    ([lang("German", "C1")], "not met"),
    ([], "unknown"),
])
def test_language_criterion(languages, expected, job):
    r = status(profile(languages=languages), job, "english")
    assert r.status == expected
    if expected in ("met", "partly"):
        assert r.evidence.startswith("English")


def test_language_any_picks_best_listed_language(job):
    p = profile(languages=[lang("Spanish", "A2"), lang("Dutch", "B2")])
    r = status(p, job, "third_language")
    assert r.status == "met" and r.evidence == "Dutch: B2"


@pytest.mark.parametrize("years,undated,roles,expected", [
    (2.0, 0, [role()], "met"),
    (1.0, 0, [role()], "met"),
    (0.6, 0, [role()], "partly"),
    (0.2, 0, [role()], "not met"),
    (0.0, 0, [role(relevant=False)], "not met"),
    (None, 2, [role()], "unknown"),
    (0.2, 1, [role()], "unknown"),
    (None, 0, [], "unknown"),
])
def test_experience_criterion(years, undated, roles, expected, job):
    p = profile(experience=roles, years=years, undated=undated)
    assert status(p, job, "experience").status == expected


@pytest.mark.parametrize("skills,expected", [
    (["live chat"], "met"),
    (["Email support for webshops"], "met"),
    (["phone support"], "partly"),
    (["Excel"], "not met"),
    (["chatting"], "not met"),  # whole-term match, not substring
    ([], "unknown"),
])
def test_skill_criterion(skills, expected, job):
    p = profile(skills=[Skill(name=s, evidence=s) for s in skills])
    assert status(p, job, "written_support").status == expected


@pytest.mark.parametrize("education,expected", [
    ([("master", False)], "met"),
    ([("vocational", False)], "met"),
    ([("secondary", False)], "not met"),
    ([("secondary", False), ("bachelor", True)], "partly"),
    ([("other", False)], "unknown"),
    ([], "unknown"),
])
def test_education_criterion(education, expected, job):
    p = profile(education=[Education(level=lvl, field=None, in_progress=ip, evidence=lvl)
                           for lvl, ip in education])
    assert status(p, job, "education").status == expected


def test_every_result_has_note_and_status(job):
    results = match_profile(profile(), job)
    assert len(results) == 9
    assert {r.status for r in results} == {"unknown"}
    assert all(r.note for r in results)


def test_tiers():
    base = dict(nice_met=0, nice_partly=0, unknown_total=0)
    assert Counts(4, 0, 0, 0, **base).tier == "A"
    assert Counts(3, 1, 0, 0, **base).tier == "B"
    assert Counts(3, 0, 0, 1, **base).tier == "B"
    assert Counts(3, 0, 1, 0, **base).tier == "C"


def test_sort_key_order():
    a = Counts(4, 0, 0, 0, nice_met=1, nice_partly=0, unknown_total=0)
    a_more_nice = Counts(4, 0, 0, 0, nice_met=3, nice_partly=0, unknown_total=0)
    b = Counts(3, 1, 0, 0, nice_met=5, nice_partly=0, unknown_total=0)
    c = Counts(3, 0, 1, 0, nice_met=5, nice_partly=0, unknown_total=0)
    ordered = sorted([("c", c), ("b", b), ("a", a), ("a2", a_more_nice)],
                     key=lambda x: sort_key(x[0], x[1]))
    assert [x[0] for x in ordered] == ["a2", "a", "b", "c"]


def test_count(job):
    p = profile(languages=[lang("English", "C1"), lang("German", "B1")],
                skills=[Skill(name="Zendesk", evidence="Zendesk")])
    k = count(match_profile(p, job))
    assert (k.must_met, k.must_partly, k.must_not_met, k.must_unknown) == (1, 1, 1, 1)
    assert k.nice_met == 1
