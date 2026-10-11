"""DOCX text comes out in reading order, with tables, text boxes and content controls, fast."""

import time

import pytest

from cv_screen.extract import MockExtractor
from cv_screen.parsing import LimitError, Limits, parse_cv
from cv_screen.pipeline import screen_text
from tests.hostile_files import docx_with_body


def p(text, style=None):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{ppr}<w:r><w:t xml:space=\"preserve\">{text}</w:t></w:r></w:p>"


def row(*cells):
    return "<w:tr>" + "".join(f"<w:tc>{c}</w:tc>" for c in cells) + "</w:tr>"


def text_box(*paras):
    """A text box as Word writes it: DrawingML in mc:Choice plus a VML copy in mc:Fallback."""
    inner = "<w:txbxContent>" + "".join(paras) + "</w:txbxContent>"
    return ("<w:r><mc:AlternateContent><mc:Choice Requires=\"wps\"><w:drawing><wps:wsp>"
            f"<wps:txbx>{inner}</wps:txbx></wps:wsp></w:drawing></mc:Choice>"
            f"<mc:Fallback><w:pict><v:shape><v:textbox>{inner}</v:textbox></v:shape></w:pict>"
            "</mc:Fallback></mc:AlternateContent></w:r>")


def parse(tmp_path, body, limits=None):
    path = tmp_path / "cv.docx"
    docx_with_body(path, body.encode())
    return parse_cv(path, limits).text


def test_table_rows_stay_under_their_heading(tmp_path, job, as_of):
    body = (p("Experience")
            + "<w:tbl>" + row(p("Customer Support Agent"), p("Shop GmbH"), p("2020 - present"))
            + "</w:tbl>"
            + p("Languages") + p("German: native") + p("English: C1")
            + p("Skills") + p("Zendesk, live chat"))
    text = parse(tmp_path, body)
    lines = text.splitlines()
    assert lines.index("Customer Support Agent | Shop GmbH | 2020 - present") == 1
    cand = screen_text("c", "cv.docx", text, job, MockExtractor(), as_of)
    assert [r.title for r in cand.profile.extraction.experience] == ["Customer Support Agent"]


def test_text_box_is_read_once_after_its_anchor(tmp_path):
    body = (p("Profile") + "<w:p>" + text_box(p("Languages"), p("German: C1")) + "</w:p>"
            + p("Skills"))
    text = parse(tmp_path, body)
    assert text.count("German: C1") == 1  # not twice (DrawingML + VML copy)
    assert text.index("German: C1") < text.index("Skills")


def test_merged_cell_is_read_once(tmp_path):
    span = '<w:tcPr><w:gridSpan w:val="3"/></w:tcPr>'
    body = "<w:tbl><w:tr><w:tc>" + span + p("Customer Support Agent") + "</w:tc></w:tr></w:tbl>"
    assert parse(tmp_path, body).count("Customer Support Agent") == 1


def test_content_controls_and_tracked_insertions_are_read(tmp_path):
    body = ("<w:sdt><w:sdtContent>" + p("Zendesk, live chat") + "</w:sdtContent></w:sdt>"
            + "<w:p><w:ins><w:r><w:t>English: C1</w:t></w:r></w:ins>"
            + "<w:del><w:r><w:delText>English: A2</w:delText></w:r></w:del></w:p>")
    text = parse(tmp_path, body)
    assert "Zendesk, live chat" in text and "English: C1" in text
    assert "A2" not in text


def test_list_style_marks_bullets(tmp_path):
    assert parse(tmp_path, p("Answered emails", style="ListBullet")) == "- Answered emails\n"


def test_many_empty_paragraphs_stop_at_the_text_limit(tmp_path):
    # 40,000 empty paragraphs = 40,000 newlines, over the 30,000-character limit. The old code
    # resolved the style of every paragraph first (~0.9 ms each, ~37 s here).
    started = time.perf_counter()
    with pytest.raises(LimitError, match="characters of text"):
        parse(tmp_path, "<w:p/>" * 40_000)
    assert time.perf_counter() - started < 3


def test_docx_markup_over_the_limit_goes_to_manual_review(tmp_path):
    with pytest.raises(LimitError, match="document markup"):
        parse(tmp_path, p("Skills") * 500, Limits(max_docx_xml_mb=0.02))
