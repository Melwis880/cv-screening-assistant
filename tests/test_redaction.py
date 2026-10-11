from cv_screen.extract import MockExtractor
from cv_screen.parsing import parse_file
from cv_screen.pipeline import screen_text
from cv_screen.redact import CANDIDATE_TOKEN, redact
from tests.conftest import SAMPLES

PROTECTED_VALUES = [
    "Erika", "Mustermann", "Example Street", "10115", "erika.mustermann@example.com",
    "+49 30 0000 0100", "14 March 1999", "Fictionalian", "Female", "Single", "[Photo]",
]


def test_removes_all_protected_values(cv_text):
    result = redact(cv_text)
    for value in PROTECTED_VALUES:
        assert value.lower() not in result.text.lower(), value
    assert result.name == "Erika Mustermann"


def test_keeps_job_relevant_content(cv_text):
    text = redact(cv_text).text
    assert "Customer Service Agent, Example Shop GmbH (fictional) - 03/2022 - present" in text
    assert "Sales Assistant, Sampletown Fashion (fictional) - 08/2019 - 02/2022" in text
    assert "2016 - 2019" in text, "date ranges must not be mistaken for phone numbers"
    assert "English: C1" in text


def test_wrapped_protected_value_is_removed(cv_text):
    # "Marital status:" ends the line, "Single" is on the next one (PDF wrapping).
    lines = redact(cv_text).text.splitlines()
    assert "Single" not in lines
    assert redact(cv_text).removed["wrapped_value"] == 1


def test_name_in_body_and_pronouns_are_neutralised(cv_text):
    text = redact(cv_text).text
    assert f"{CANDIDATE_TOKEN} is a customer service agent" in text
    assert "They enjoys" in text  # verb agreement is only fixed for is/was/has; good enough
    assert "their manager" in text
    assert "describes them as calm" in text
    for word in [" she ", " her ", " he ", " his "]:
        assert word not in f" {text.lower()} "


def test_name_from_label_field():
    result = redact("CURRICULUM VITAE\nName: Max Mustermann\nProfile\nMax likes support.\n")
    assert result.name == "Max Mustermann"
    assert "Max" not in result.text
    assert f"{CANDIDATE_TOKEN} likes support." in result.text


def test_titles_age_and_urls_are_removed():
    text = redact(
        "Ms. Jane Roe\nAged 34, mother of two.\nPortfolio: https://example.com/jane\n"
        "Skills\nExcel\n"
    ).text
    for value in ["Ms", "Jane", "Aged 34", "mother", "https://"]:
        assert value not in text


def test_mother_tongue_is_kept_and_counts_as_native(job, as_of):
    cv = "Languages\nGerman (mother tongue)\nEnglish: C1\nSkills\nlive chat\n"
    assert "German (mother tongue)" in redact(cv).text
    assert "[REDACTED] of two" in redact("Mother of two.\n").text
    cand = screen_text("c", "c.txt", cv, job, MockExtractor(), as_of)
    german = next(r for r in cand.results if r.criterion_id == "german")
    assert german.status == "met", german.note


def test_headline_on_the_first_line_is_not_taken_as_name(job, as_of):
    # e.g. a DOCX whose name sits in the page header (not read): the first body line is a title
    cv = ("Customer Support Specialist\nExperience\nCustomer Support Agent, Shop GmbH, "
          "2020 - present\n- Answered customer emails in Zendesk\nLanguages\nGerman: native\n"
          "English: C1\nSkills\nZendesk, customer emails, live chat\n")
    result = redact(cv)
    assert result.name is None
    assert CANDIDATE_TOKEN not in result.text
    cand = screen_text("c", "c.txt", cv, job, MockExtractor(), as_of)
    assert cand.counts.tier == "A"


def test_section_heading_is_not_taken_as_name():
    result = redact("Profile\nCustomer support agent.\n")
    assert result.name is None
    assert result.text.startswith("Profile")


def test_all_samples_lose_their_protected_header():
    for path in sorted(SAMPLES.glob("cv*.*")):
        result = redact(parse_file(path))
        assert result.name, path.name
        assert result.name.split()[-1] not in result.text, path.name
        for label in ["Date of birth", "Nationality", "Gender", "Marital status", "Address"]:
            assert label not in result.text, (path.name, label)
        assert "@example.com" not in result.text
