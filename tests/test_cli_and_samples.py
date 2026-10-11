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


def test_cli_blind_hides_names_including_file_names(tmp_path):
    # Real file names often carry the applicant's name; blind mode must not show them either.
    folder = tmp_path / "cvs"
    folder.mkdir()
    for path in sorted(SAMPLES.glob("cv0[1-3].*")):
        (folder / path.name).write_bytes(path.read_bytes())
    (folder / "Erika_Mustermann_Lebenslauf.pdf").write_bytes((SAMPLES / "cv01.pdf").read_bytes())
    (folder / "Kim_Ng_CV.pdf").write_bytes(b"%PDF-1.4 broken")  # manual review, error text
    out = tmp_path / "out"
    result = CliRunner().invoke(main, [
        "run", str(folder), "--job", str(ROOT / "job.yaml"), "--out", str(out), "--mock",
        "--blind", "--as-of", "2026-10-01",
    ])
    assert result.exit_code == 0, result.output
    shown = [result.output, (out / "shortlist.md").read_text(), (out / "shortlist.csv").read_text()]
    shown += [p.read_text() for p in (out / "candidates").iterdir()]
    for text in shown:
        for word in ("Erika", "Mustermann", "Lebenslauf", "Kim_Ng", "Kim Ng"):
            assert word not in text, word
    assert all(p.name.startswith("cv-") for p in (out / "candidates").iterdir())
    report = json.loads((out / "run_report.json").read_text())
    assert {r["source_file"] for r in report["per_cv"]} >= {"Erika_Mustermann_Lebenslauf.pdf",
                                                             "Kim_Ng_CV.pdf"}


def test_cli_real_mode_without_key_fails_clearly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # make sure no local .env is picked up
    result = CliRunner().invoke(main, [
        "run", str(SAMPLES), "--job", str(ROOT / "job.yaml"), "--real",
    ])
    assert result.exit_code != 0
    assert "ANTHROPIC_API_KEY" in result.output
    assert not (tmp_path / "out").exists()
