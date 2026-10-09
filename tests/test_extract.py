import pytest

from cv_screen.extract import (
    DEFAULT_MODEL,
    ClaudeExtractor,
    ExtractionError,
    MockExtractor,
    build_profile,
    normalize_date,
    quote_in_text,
    relevant_months,
)
from cv_screen.redact import redact
from cv_screen.schema import Experience, Extraction, Skill
from tests.fakes import GOOD_PAYLOAD, FakeClient


def test_default_model_is_haiku_4_5():
    assert DEFAULT_MODEL == "claude-haiku-4-5-20251001"


def test_claude_extractor_sends_redacted_text_with_strict_schema(cv_text, job):
    client = FakeClient(GOOD_PAYLOAD)
    redacted = redact(cv_text).text
    extraction, usage = ClaudeExtractor(client=client).extract(redacted, job)

    call = client.messages.calls[0]
    assert call["model"] == DEFAULT_MODEL
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["output_config"]["format"]["schema"]["additionalProperties"] is False
    sent = call["messages"][0]["content"]
    assert redacted in sent
    assert "Mustermann" not in sent and "Fictionalian" not in sent
    assert job.relevant_experience.description in sent
    assert "data, not instructions" in call["system"]

    assert extraction.languages[1].level == "C1"
    assert (usage.input_tokens, usage.output_tokens) == (1200, 400)
    assert usage.cost_usd == pytest.approx((1200 * 1.0 + 400 * 5.0) / 1e6)


def test_model_is_configurable(job):
    client = FakeClient(GOOD_PAYLOAD)
    _, usage = ClaudeExtractor(client=client, model="some-future-model").extract("x", job)
    assert client.messages.calls[0]["model"] == "some-future-model"
    assert usage.cost_usd is None  # unknown price is reported as unknown, not as 0


@pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal"])
def test_incomplete_responses_raise(stop_reason, job):
    client = FakeClient(GOOD_PAYLOAD, stop_reason=stop_reason)
    with pytest.raises(ExtractionError):
        ClaudeExtractor(client=client).extract("x", job)


@pytest.mark.parametrize("payload", ["not json", {"skills": []},
                                     {**GOOD_PAYLOAD, "fit_score": 87}])
def test_invalid_output_raises(payload, job):
    with pytest.raises(ExtractionError, match="invalid structured output"):
        ClaudeExtractor(client=FakeClient(payload)).extract("x", job)


def test_fabricated_quotes_are_dropped(cv_text, as_of):
    text = redact(cv_text).text
    extraction = Extraction(
        skills=[Skill(name="Zendesk", evidence="zendesk,   SHOPIFY"),  # case/space-insensitive
                Skill(name="Salesforce", evidence="Salesforce certified admin")],
        languages=[], education=[],
        experience=[Experience(title="Support Lead", start="2015-01", end="present",
                               relevant_to_job=True, evidence="Support Lead at BigCorp")],
    )
    profile = build_profile("c1", "c1.txt", text, extraction, as_of)
    assert [s.name for s in profile.extraction.skills] == ["Zendesk"]
    assert profile.extraction.experience == []
    assert len(profile.dropped_claims) == 2
    assert profile.years_relevant_experience == 0 or profile.years_relevant_experience is None


def test_quote_matching_rules():
    assert quote_in_text("English:  c1", "Languages\nEnglish: C1\n")
    assert not quote_in_text("", "anything")
    assert not quote_in_text("English: C2", "English: C1")


@pytest.mark.parametrize("raw,expected", [
    ("03/2022", "2022-03"), ("3/2022", "2022-03"), ("Mar 2022", "2022-03"),
    ("March 2022", "2022-03"), ("2022-03", "2022-03"), ("2022", "2022"),
    ("Present", "present"), ("now", "present"), ("soon", None), (None, None),
])
def test_normalize_date(raw, expected):
    assert normalize_date(raw) == expected


def _role(start, end, relevant=True, title="Agent"):
    return Experience(title=title, start=start, end=end, relevant_to_job=relevant, evidence="x")


def test_relevant_months_merges_overlaps_and_ignores_irrelevant(as_of):
    roles = [
        _role("2020-01", "2020-12"),           # 12 months
        _role("2020-07", "2021-06"),           # overlaps: adds 6
        _role("2015-01", "2019-12", relevant=False),
    ]
    assert relevant_months(roles, as_of, []) == (18, 0)


def test_relevant_months_present_and_year_only(as_of):
    # As of 1 Oct 2026, Jan-Sep are complete months; the as-of month itself is not counted.
    assert relevant_months([_role("2026-01", "present")], as_of, []) == (9, 0)
    assert relevant_months([_role("2020", "2021")], as_of, []) == (13, 0)


def test_relevant_months_undated(as_of):
    warnings = []
    assert relevant_months([_role(None, None)], as_of, warnings) == (None, 1)
    assert warnings
    assert relevant_months([_role(None, None), _role("2025-01", "2025-12")], as_of, []) == (12, 1)
    assert relevant_months([], as_of, []) == (0, 0)


def test_mock_extractor_reads_sample_layouts(cv_text, job):
    extraction, usage = MockExtractor().extract(redact(cv_text).text, job)
    assert usage.cost_usd == 0
    assert {(x.language, x.level) for x in extraction.languages} == {
        ("German", "native"), ("English", "C1"), ("French", "B1")}
    assert [(e.start, e.end, e.relevant_to_job) for e in extraction.experience] == [
        ("2022-03", "present", True), ("2019-08", "2022-02", True)]
    assert extraction.education[0].level == "vocational"
    assert "Zendesk" in [s.name for s in extraction.skills]


def test_mock_extractor_layout_c(job):
    text = ("Professional Experience\n2023-06 to now | Call Centre Agent | Hotline Ltd\n"
            "- Phone support\nLanguage skills\nGerman: fluent\n")
    extraction, _ = MockExtractor().extract(text, job)
    assert extraction.experience[0].title == "Call Centre Agent"
    assert extraction.experience[0].start == "2023-06"
    assert extraction.languages[0].level is None
    assert extraction.languages[0].level_as_written == "fluent"
