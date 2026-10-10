"""Candidate IDs are unique per file, so no candidate's summary or email overwrites another's."""

import shutil

import pytest

from cv_screen.extract import MockExtractor
from cv_screen.pipeline import DuplicateCandidateError, run_screening
from cv_screen.report import write_outputs
from tests.conftest import SAMPLES


def test_same_stem_different_files_get_their_own_outputs(tmp_path, job, as_of):
    folder = tmp_path / "cvs"
    folder.mkdir()
    shutil.copy(SAMPLES / "cv01.pdf", folder / "cv01.pdf")
    shutil.copy(SAMPLES / "cv02.docx", folder / "cv01.docx")
    run = run_screening(folder, job, MockExtractor(), as_of)
    ids = [c.candidate_id for c in run.candidates]
    assert len(set(ids)) == 2
    assert all(i.startswith("cv01-") for i in ids)

    out = tmp_path / "out"
    write_outputs(run, out)
    assert len(list((out / "candidates").iterdir())) == 2
    assert len(list((out / "emails").iterdir())) == 2
    for cand in run.candidates:
        summary = (out / "candidates" / f"{cand.candidate_id}.md").read_text(encoding="utf-8")
        assert cand.source_file in summary


def test_identical_ids_fail_before_any_output(tmp_path, job, as_of):
    folder = tmp_path / "cvs"
    folder.mkdir()
    for name in ("cv01.txt", "cv01.TXT"):  # same stem, same bytes -> same ID
        (folder / name).write_text("Skills\n- Excel, live chat\n", encoding="utf-8")

    class MustNotRun:
        name = "must-not-run"

        def extract(self, text, job):
            raise AssertionError("screening started despite duplicate IDs")

    with pytest.raises(DuplicateCandidateError, match="cv01.TXT"):
        run_screening(folder, job, MustNotRun(), as_of)


def test_write_outputs_refuses_duplicate_ids(tmp_path, job, as_of):
    folder = tmp_path / "cvs"
    folder.mkdir()
    (folder / "a.txt").write_text("Skills\n- Excel, live chat\n", encoding="utf-8")
    (folder / "b.txt").write_text("Skills\n- Zendesk, live chat\n", encoding="utf-8")
    run = run_screening(folder, job, MockExtractor(), as_of)
    run.candidates[1].candidate_id = run.candidates[0].candidate_id
    out = tmp_path / "out"
    with pytest.raises(DuplicateCandidateError):
        write_outputs(run, out)
    assert not out.exists()


def test_ids_are_safe_in_file_names_and_links(tmp_path, job, as_of):
    folder = tmp_path / "cvs"
    folder.mkdir()
    long_name = "-Lebenslauf (Müller) [final] " + "x" * 200 + ".txt"
    (folder / long_name).write_text("Skills\n- Excel, live chat\n", encoding="utf-8")
    run = run_screening(folder, job, MockExtractor(), as_of)
    cid = run.candidates[0].candidate_id
    assert cid.startswith("Lebenslauf_Müller_final_x")
    assert len(cid) <= 80
    assert not set(cid) & set(" ()[]/\\")
