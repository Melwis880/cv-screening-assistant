import json

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
from cv_screen.pipeline import run_screening
from cv_screen.redact import redact
from cv_screen.report import run_report
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


def test_relevant_months_future_role_does_not_subtract(as_of):
    warnings = []
    roles = [_role("2025-01", "2025-12"), _role("2027", "2028")]
    assert relevant_months(roles, as_of, warnings) == (12, 0)
    assert any("starts after" in w for w in warnings)


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


def test_request_serialises_through_real_sdk(job):
    """Use the real Anthropic client with a mock HTTP transport: no network, real request body."""
    import json

    import anthropic
    import httpx2

    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant",
            "model": DEFAULT_MODEL, "stop_reason": "end_turn", "stop_sequence": None,
            "content": [{"type": "text", "text": json.dumps(GOOD_PAYLOAD)}],
            "usage": {"input_tokens": 1500, "output_tokens": 600},
        })

    client = anthropic.Anthropic(
        api_key="test-key", base_url="http://127.0.0.1:9", max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    extraction, usage = ClaudeExtractor(client=client).extract("Skills\nExcel\n", job)
    assert seen["url"].endswith("/v1/messages")
    assert seen["body"]["output_config"]["format"]["type"] == "json_schema"
    assert seen["body"]["model"] == DEFAULT_MODEL
    assert extraction.skills[0].name == "Zendesk"
    assert usage.cost_usd == pytest.approx((1500 * 1.0 + 600 * 5.0) / 1e6)


def test_default_client_has_a_request_timeout(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")  # client is built, never called
    client = ClaudeExtractor().client
    assert client.timeout == 120.0
    assert client.max_retries == 3


def test_schema_errors_do_not_quote_cv_text(job, as_of, tmp_path):
    # Error text reaches the terminal, run_report.json and the n8n execution log.
    secret = "Customer Support Agent at Example GmbH since 2019"
    bad = {"skills": [{"name": "Zendesk", "evidence": secret, "extra": secret}],
           "languages": secret, "education": [], "experience": []}
    with pytest.raises(ExtractionError) as exc:
        ClaudeExtractor(client=FakeClient(bad)).extract("x", job)
    assert secret not in str(exc.value)
    assert "skills.0.extra" in str(exc.value) and "languages" in str(exc.value)

    (tmp_path / "cv.txt").write_text("Skills\nZendesk\n", encoding="utf-8")
    run = run_screening(tmp_path, job, ClaudeExtractor(client=FakeClient(bad)), as_of)
    report = json.dumps(run_report(run))
    assert "schema error" in report and secret not in report
