"""Missing or unreadable information becomes 'unknown' or 'manual review', never a silent no."""

from cv_screen.extract import ClaudeExtractor, MockExtractor
from cv_screen.pipeline import run_screening, screen_text
from tests.fakes import FakeClient

SPARSE = """Support Agent, Various employers
Looking for a job in customer support.
"""


def test_sparse_cv_gives_unknowns_not_rejections(job, as_of):
    cand = screen_text("c", "c.txt", SPARSE, job, MockExtractor(), as_of)
    by = {r.criterion_id: r.status for r in cand.results}
    assert by["english"] == "unknown"
    assert by["german"] == "unknown"
    assert by["written_support"] == "unknown"
    assert by["education"] == "unknown"
    assert "not met" not in [r.status for r in cand.results if r.must_have]
    assert cand.counts.tier == "B"
    assert any("No languages" in w for w in cand.profile.warnings)


def test_missing_dates_ask_instead_of_reject(job, as_of):
    text = ("Experience\nCustomer Advisor, Telecom Shop\n- Advised customers by email\n"
            "Languages\nGerman: C1\nEnglish: C1\nSkills\ncustomer emails\n")
    cand = screen_text("c", "c.txt", text, job, MockExtractor(), as_of)
    exp = next(r for r in cand.results if r.criterion_id == "experience")
    assert exp.status == "unknown"
    assert "dates" in exp.note.lower()
    assert exp.evidence == "Customer Advisor, Telecom Shop"


def test_failures_go_to_manual_review_and_run_continues(tmp_path, job, as_of):
    (tmp_path / "good.txt").write_text(
        "Languages\nGerman: C1\nEnglish: C1\nSkills\nlive chat\n", encoding="utf-8")
    (tmp_path / "broken.pdf").write_bytes(b"%PDF-1.4 garbage")
    (tmp_path / "empty.txt").write_text("   \n", encoding="utf-8")
    run = run_screening(tmp_path, job, MockExtractor(), as_of)
    assert [c.source_file for c in run.ranked] == ["good.txt"]
    assert sorted(c.source_file for c in run.failed) == ["broken.pdf", "empty.txt"]
    assert all(c.error for c in run.failed)


def test_api_failure_goes_to_manual_review(tmp_path, job, as_of):
    (tmp_path / "a.txt").write_text("Skills\nExcel\n", encoding="utf-8")
    client = FakeClient("{not json")
    run = run_screening(tmp_path, job, ClaudeExtractor(client=client), as_of)
    assert run.ranked == []
    assert "extraction failed" in run.failed[0].error


def test_unexpected_exception_goes_to_manual_review(tmp_path, job, as_of):
    class Boom:
        name = "boom"

        def extract(self, text, job):
            raise ConnectionError("network down")

    (tmp_path / "a.txt").write_text("Skills\nExcel\n", encoding="utf-8")
    run = run_screening(tmp_path, job, Boom(), as_of)
    assert "ConnectionError" in run.failed[0].error
