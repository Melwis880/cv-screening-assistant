"""Oversized input goes to manual review before any parsing work or API call, never to a reject."""

import time

import pytest
from click.testing import CliRunner
from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from cv_screen.cli import main
from cv_screen.extract import MockExtractor
from cv_screen.parsing import Limits, normalize_text
from cv_screen.pipeline import run_screening, screen_text
from tests.conftest import ROOT

CV = "Languages\nGerman: native\nEnglish: C1\nSkills\n- Excel, live chat\n"


class CountingExtractor:
    """Mock-like extractor that records whether it was called."""

    name = "counting"

    def __init__(self):
        self.inner = MockExtractor()
        self.calls = 0

    def extract(self, text, job):
        self.calls += 1
        return self.inner.extract(text, job)


def _pdf(path, pages):
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    for i in range(pages):
        c.drawString(72, 800, f"Skills page {i + 1}: Excel, live chat")
        c.showPage()
    c.save()


def _screen(folder, job, as_of, **limits):
    extractor = CountingExtractor()
    run = run_screening(folder, job, extractor, as_of, limits=Limits(**limits))
    return run, extractor


def test_default_limits():
    assert Limits() == Limits(max_file_mb=5, max_pdf_pages=10, max_chars=30_000,
                              max_unpacked_mb=50)


def test_file_over_the_size_limit_goes_to_manual_review(tmp_path, job, as_of):
    (tmp_path / "big.txt").write_text(CV + "x" * 6_000_000, encoding="utf-8")
    run, extractor = _screen(tmp_path, job, as_of)
    assert run.ranked == [] and extractor.calls == 0
    assert "MB" in run.failed[0].error and "read it manually" in run.failed[0].error


def test_pdf_over_the_page_limit_goes_to_manual_review(tmp_path, job, as_of):
    _pdf(tmp_path / "long.pdf", pages=11)
    _pdf(tmp_path / "short.pdf", pages=2)
    run, extractor = _screen(tmp_path, job, as_of)
    assert [c.source_file for c in run.failed] == ["long.pdf"]
    assert "11 pages" in run.failed[0].error
    assert [c.source_file for c in run.ranked] == ["short.pdf"]
    assert extractor.calls == 1


def test_text_over_the_character_limit_is_not_sent(tmp_path, job, as_of):
    (tmp_path / "long.txt").write_text(CV + "Profile\n" + "Helpful. " * 4000, encoding="utf-8")
    run, extractor = _screen(tmp_path, job, as_of)
    assert run.ranked == [] and extractor.calls == 0
    assert "characters" in run.failed[0].error


def test_docx_unpacking_to_more_than_the_limit_goes_to_manual_review(tmp_path, job, as_of):
    doc = Document()
    for line in CV.splitlines():
        doc.add_paragraph(line)
    doc.save(tmp_path / "cv.docx")
    run, extractor = _screen(tmp_path, job, as_of, max_unpacked_mb=0.01)
    assert run.ranked == [] and extractor.calls == 0
    assert "unpacks to" in run.failed[0].error


def test_limits_are_configurable_from_the_cli(tmp_path):
    (tmp_path / "cvs").mkdir()
    (tmp_path / "cvs" / "a.txt").write_text(CV, encoding="utf-8")
    args = ["run", str(tmp_path / "cvs"), "--job", str(ROOT / "job.yaml"), "--mock",
            "--out", str(tmp_path / "out"), "--as-of", "2026-10-01"]
    result = CliRunner().invoke(main, [*args, "--max-chars", "20"])
    assert result.exit_code == 0, result.output
    assert "manual review: 1" in result.output
    result = CliRunner().invoke(main, [*args, "--max-chars", "30000", "--max-file-mb", "1",
                                       "--max-pages", "3"])
    assert "manual review: 0" in result.output


# Text an applicant controls, at the --max-chars limit. Each used to take 3-20+ s because a
# regex or the evidence check was quadratic in the length of a run of characters.
HOSTILE_RUNS = {
    "word run": "x" * 30_000,
    "dotted run": "a." * 15_000,
    "em-space run": "a" + "\u2003" * 30_000 + "b",
    "long skills line": "Skills\n" + ", ".join(f"Tool{i}" for i in range(4_000)),
}


@pytest.mark.parametrize("body", HOSTILE_RUNS.values(), ids=HOSTILE_RUNS.keys())
def test_hostile_text_is_processed_in_linear_time(body, job, as_of):
    text = normalize_text("Experience\n" + body + "\n")
    started = time.perf_counter()
    screen_text("c", "c.txt", text, job, MockExtractor(), as_of)
    assert time.perf_counter() - started < 2.0
