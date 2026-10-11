"""Small files that are expensive to parse go to manual review quickly (PDF work budget)."""

import time

import pytest

from cv_screen.parsing import LimitError, Limits, parse_cv
from tests.conftest import SAMPLES
from tests.hostile_files import EMPTY_TEXT_OP, pdf


def _parse(path, limits=None):
    started = time.perf_counter()
    with pytest.raises(LimitError) as exc:
        parse_cv(path, limits)
    return str(exc.value), time.perf_counter() - started


def test_pdf_with_megabytes_of_drawing_operators_stops_before_parsing_them(tmp_path):
    # 22 KB on disk, 8.8 MB of content; the old code spent ~16 s on it, then said "no text".
    path = tmp_path / "ops.pdf"
    pdf(path, EMPTY_TEXT_OP * 400_000)
    message, seconds = _parse(path)
    assert "PDF parsing limit" in message and "MB of page content" in message
    assert seconds < 1


def test_each_use_of_a_form_counts_against_the_budget(tmp_path):
    # 2 KB file: one form of 20k empty text blocks drawn 40 times (old code: ~21 s; pypdf
    # allows 5,000 uses, i.e. about 45 minutes).
    path = tmp_path / "forms.pdf"
    pdf(path, b"/X0 Do " * 40, EMPTY_TEXT_OP * 20_000)
    message, seconds = _parse(path)
    assert "drawing operators" in message
    assert seconds < 5


def test_form_bytes_are_charged_before_the_form_is_parsed(tmp_path):
    path = tmp_path / "forms.pdf"
    pdf(path, b"/X0 Do " * 3, EMPTY_TEXT_OP * 10_000)  # 220 KB per use
    message, _ = _parse(path, Limits(max_pdf_content_mb=0.5, max_pdf_ops=10**9))
    assert "MB of page content" in message


def test_budget_error_inside_the_last_form_is_not_lost(tmp_path):
    # pypdf catches and logs an exception raised while drawing a form; with nothing drawn
    # after the form, extraction would end normally unless the budget is checked again.
    path = tmp_path / "last.pdf"
    pdf(path, b"/X0 Do", EMPTY_TEXT_OP * 2_000)
    message, _ = _parse(path, Limits(max_pdf_ops=1_000))
    assert "drawing operators" in message


def test_a_form_listed_under_two_names_is_charged_under_both(tmp_path):
    path = tmp_path / "alias.pdf"
    pdf(path, b"/X0 Do " + b"/X1 Do " * 3, EMPTY_TEXT_OP * 10_000, form_names=(b"X0", b"X1"))
    message, _ = _parse(path, Limits(max_pdf_content_mb=0.5, max_pdf_ops=10**9))
    assert "MB of page content" in message


def test_many_large_unused_forms_do_not_exhaust_memory(tmp_path):
    # Forms are decoded up front to learn their size and pypdf keeps decoded streams, so
    # their total is capped: 20 forms of 1 MB (a 20 KB file) would otherwise be held in memory.
    import zlib

    form = zlib.compress(b"q Q " * 250_000, 9)
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /XObject << "
            + b" ".join(b"/X%d %d 0 R" % (i, 5 + i) for i in range(20))
            + b" >> >> /Contents 4 0 R >>",
            b"<< /Length 2 >>\nstream\nq \nendstream"]
    objs += [b"<< /Type /XObject /Subtype /Form /BBox [0 0 1 1] /Length %d /Filter /FlateDecode"
             b" >>\nstream\n" % len(form) + form + b"\nendstream"] * 20
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    path = tmp_path / "forms.pdf"
    path.write_bytes(bytes(out))
    message, _ = _parse(path)
    assert "MB of drawing forms" in message


def test_sample_pdfs_are_far_below_the_budget():
    for path in sorted(SAMPLES.glob("*.pdf")):
        parse_cv(path, Limits(max_pdf_ops=2_000, max_pdf_content_mb=0.1))
