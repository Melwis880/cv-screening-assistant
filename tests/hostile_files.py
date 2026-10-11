"""Small files that are expensive to parse, built in code (used by tests and the benchmark)."""

from __future__ import annotations

import io
import zipfile
import zlib
from pathlib import Path

from docx import Document

EMPTY_TEXT_OP = b"BT /F1 12 Tf () Tj ET "  # 5 operators that draw nothing


def pdf(path: Path, page_ops: bytes, form_ops: bytes | None = None) -> None:
    """A one-page PDF with Flate-compressed content (and optionally one form XObject)."""
    font = b"/Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >>"
    page = zlib.compress(page_ops, 9)
    xobj = b" /XObject << /X0 5 0 R >>" if form_ops is not None else b""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << " + font
            + xobj + b" >> /Contents 4 0 R >>",
            b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(page) + page
            + b"\nendstream"]
    if form_ops is not None:
        form = zlib.compress(form_ops, 9)
        objs.append(b"<< /Type /XObject /Subtype /Form /BBox [0 0 612 792] /Resources << "
                    + font + b" >> /Length %d /Filter /FlateDecode >>\nstream\n" % len(form)
                    + form + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1,
                                                                           xref)
    path.write_bytes(bytes(out))


def docx_with_body(path: Path, body_xml: bytes) -> None:
    """A DOCX made from python-docx's default template with `body_xml` as the body."""
    buf = io.BytesIO()
    Document().save(buf)
    src = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as out:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "word/document.xml":
                head, rest = data.split(b"<w:body>")
                data = head + b"<w:body>" + body_xml + rest[rest.index(b"<w:sectPr"):]
            out.writestr(info.filename, data)
