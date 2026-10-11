"""File names and errors printed by the CLI cannot carry terminal escape or bidi sequences."""

import unicodedata

from click.testing import CliRunner

from cv_screen.cli import main, term_safe
from tests.conftest import ROOT

# OSC 8 hyperlink, screen clear, BEL, right-to-left override, line separator
HOSTILE = "cv\x1b]8;;evil.example\x07click\x1b]8;;\x07\x1b[2J\u202egpj\u2028x"
BANNED = {"Cc", "Cf", "Zl", "Zp"}


def _clean(output):
    return [ch for ch in output if ch != "\n" and unicodedata.category(ch) in BANNED]


def _run(folder, tmp_path):
    return CliRunner().invoke(main, ["run", str(folder), "--job", str(ROOT / "job.yaml"),
                                     "--mock", "--out", str(tmp_path / "out"),
                                     "--as-of", "2026-10-01"])


def test_manual_review_list_is_printed_without_control_characters(tmp_path):
    folder = tmp_path / "cvs"
    folder.mkdir()
    (folder / f"{HOSTILE}.pdf").write_bytes(b"%PDF-1.4 garbage")
    result = _run(folder, tmp_path)
    assert result.exit_code == 0, result.output
    assert "Needs manual review:" in result.output
    assert "cv?]8;;evil.example?click" in result.output
    assert _clean(result.output) == []


def test_duplicate_id_error_is_printed_without_control_characters(tmp_path):
    folder = tmp_path / "cvs"
    folder.mkdir()
    for suffix in (".txt", ".TXT"):
        (folder / f"{HOSTILE}{suffix}").write_text("Skills\n- Excel, live chat\n")
    result = _run(folder, tmp_path)
    assert result.exit_code != 0
    assert "same candidate ID" in result.output
    assert _clean(result.output) == []


def test_pdf_library_warnings_are_sanitised(tmp_path, capsys):
    import logging

    from cv_screen import cli

    cli._route_library_warnings()
    logging.getLogger("pypdf._page").warning("Impossible to decode XFormObject %s", HOSTILE)
    err = capsys.readouterr().err
    assert "XFormObject cv?]8;;evil.example?click" in err
    assert _clean(err) == []


def test_term_safe_keeps_ordinary_text():
    assert term_safe("Zoë Ångström-Øberg, cv01.pdf: 11 pages") == (
        "Zoë Ångström-Øberg, cv01.pdf: 11 pages")
    assert term_safe("a\tb\x1b[31mc\u200bd") == "a?b?[31mc?d"
