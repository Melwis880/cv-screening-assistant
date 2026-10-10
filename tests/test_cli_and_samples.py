import csv
import json

from click.testing import CliRunner

from cv_screen.cli import main
from cv_screen.parsing import find_cv_files, parse_file
from tests.conftest import ROOT, SAMPLES


def _ids_by_stem(out):
    """Candidate IDs are '<stem>-<sha256 prefix>'; tests refer to candidates by file stem."""
    rows = csv.DictReader((out / "shortlist.csv").open(encoding="utf-8"))
    return {r["source_file"].rsplit(".", 1)[0]: r["candidate_id"] for r in rows}


# Regression snapshot of the mock-mode demo run (as of 2026-10-01). If the samples or rules
# change on purpose, update this table.
EXPECTED_TIERS = {
    "A": {"cv01", "cv02", "cv10", "cv14", "cv16", "cv17", "cv19"},
    "B": {"cv03", "cv04", "cv06", "cv07", "cv08", "cv09", "cv11", "cv12", "cv18"},
    "C": {"cv05", "cv13", "cv15", "cv20"},
}


def test_samples_are_synthetic_and_mixed_format():
    files = find_cv_files(SAMPLES)
    assert len(files) == 20
    assert {f.suffix for f in files} == {".pdf", ".docx"}
    for f in files:
        text = parse_file(f)
        assert "SYNTHETIC CV" in text, f.name
        assert "@example.com" in text, f.name


def test_cli_mock_run_end_to_end(tmp_path):
    out = tmp_path / "out"
    result = CliRunner().invoke(main, [
        "run", str(SAMPLES), "--job", str(ROOT / "job.yaml"), "--out", str(out),
        "--as-of", "2026-10-01",
    ], env={"MOCK_LLM": "1"})
    assert result.exit_code == 0, result.output
    assert "No emails were sent" in result.output

    shortlist = (out / "shortlist.md").read_text()
    assert "This tool recommends, the hiring manager decides" in shortlist
    assert "Ranking rule:" in shortlist

    rows = list(csv.DictReader((out / "shortlist.csv").open()))
    assert len(rows) == 20
    tiers = {t: {r["source_file"].rsplit(".", 1)[0] for r in rows if r["tier"] == t}
             for t in "ABC"}
    assert tiers == EXPECTED_TIERS
    assert [r["rank"] for r in rows] == [str(i) for i in range(1, 21)]
    assert rows[0]["source_file"] == "cv01.pdf"

    ids = _ids_by_stem(out)
    for stem in ("cv01", "cv18"):
        cid = ids[stem]
        summary = (out / "candidates" / f"{cid}.md").read_text()
        assert "recommends, the hiring manager decides" in summary
        email = (out / "emails" / f"{cid}.md").read_text()
        assert "DRAFT ONLY - nothing has been sent" in email
        assert "Variant A" in email and "Variant B" in email and "Variant C" in email
    assert "variant B (ask for missing information)" in (
        out / "emails" / f"{ids['cv18']}.md").read_text()

    report = json.loads((out / "run_report.json").read_text())
    assert report["extractor"] == "mock"
    assert report["cvs"] == 20 and report["manual_review"] == 0
    assert report["cost_usd"] == 0
    assert report["dropped_claims"] == 0  # well-formed CVs lose no claim to the evidence check


def test_cli_blind_hides_names(tmp_path):
    out = tmp_path / "out"
    result = CliRunner().invoke(main, [
        "run", str(SAMPLES), "--job", str(ROOT / "job.yaml"), "--out", str(out), "--mock",
        "--blind", "--as-of", "2026-10-01",
    ])
    assert result.exit_code == 0, result.output
    assert "Erika Mustermann" not in (out / "shortlist.md").read_text()
    assert "Erika Mustermann" not in (
        out / "candidates" / f"{_ids_by_stem(out)['cv01']}.md").read_text()
    assert "Erika Mustermann" not in (out / "shortlist.csv").read_text()


def test_cli_real_mode_without_key_fails_clearly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # make sure no local .env is picked up
    result = CliRunner().invoke(main, [
        "run", str(SAMPLES), "--job", str(ROOT / "job.yaml"), "--real",
    ])
    assert result.exit_code != 0
    assert "ANTHROPIC_API_KEY" in result.output
    assert not (tmp_path / "out").exists()
