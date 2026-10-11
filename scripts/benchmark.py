"""Measure the offline pipeline on the sample CVs and on a few hostile files (demo data).

    python scripts/benchmark.py            # samples + hostile files
    python scripts/benchmark.py --samples  # samples only

Prints per-stage times for the 20 samples (best of N repetitions), the size of the prompt
that real mode would send, and the parse time of generated hostile PDF/DOCX files that are
small on disk but expensive to parse. Nothing is sent anywhere; no API key is needed.
"""

from __future__ import annotations

import argparse
import io
import json
import tempfile
import time
import zipfile
from datetime import date
from pathlib import Path

from docx import Document

from cv_screen.extract import SYSTEM_PROMPT, MockExtractor, build_profile, build_user_message
from cv_screen.job import load_job
from cv_screen.matching import match_profile
from cv_screen.parsing import ParseError, find_cv_files, parse_cv
from cv_screen.redact import redact
from cv_screen.schema import extraction_json_schema

ROOT = Path(__file__).resolve().parent.parent
AS_OF = date(2026, 10, 1)


def bench_samples(reps: int) -> None:
    job = load_job(ROOT / "job.yaml")
    files = find_cv_files(ROOT / "samples")
    best: dict[str, float] = {}
    for _ in range(reps):
        t = dict.fromkeys(["parse_pdf", "parse_docx", "redact", "extract_mock", "verify",
                           "match"], 0.0)
        for f in files:
            s = time.perf_counter()
            text = parse_cv(f).text
            t["parse_" + f.suffix[1:]] += time.perf_counter() - s
            s = time.perf_counter()
            red = redact(text)
            t["redact"] += time.perf_counter() - s
            s = time.perf_counter()
            ex, _ = MockExtractor().extract(red.text, job)
            t["extract_mock"] += time.perf_counter() - s
            s = time.perf_counter()
            prof = build_profile("c", f.name, red.text, ex, AS_OF,
                                 job.relevant_experience.keywords)
            t["verify"] += time.perf_counter() - s
            s = time.perf_counter()
            match_profile(prof, job)
            t["match"] += time.perf_counter() - s
        for k, v in t.items():
            best[k] = min(best.get(k, v), v)
    print(f"Samples: {len(files)} CVs, best of {reps} runs, total ms per stage:")
    for k, v in best.items():
        print(f"  {k:<13} {v * 1000:8.1f}")
    print(f"  {'total':<13} {sum(best.values()) * 1000:8.1f}")

    msgs = [build_user_message(redact(parse_cv(f).text).text, job) for f in files]
    schema = json.dumps(extraction_json_schema())
    print("Prompt size per CV (characters; tokens ~ characters / 4, an estimate):")
    print(f"  system prompt {len(SYSTEM_PROMPT)}, JSON schema {len(schema)}, "
          f"user message avg {sum(map(len, msgs)) // len(msgs)} (max {max(map(len, msgs))})")


def _pdf(path: Path, page_ops: bytes, form_ops: bytes | None = None) -> None:
    """A one-page PDF with Flate-compressed content (and optionally one form XObject)."""
    import zlib

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


def _docx(path: Path, body_xml: bytes) -> None:
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


HOSTILE = {
    "pdf_400k_empty_text_ops": lambda p: _pdf(p, b"BT /F1 12 Tf () Tj ET " * 400_000),
    "pdf_form_20k_ops_x40": lambda p: _pdf(p, b"/X0 Do " * 40,
                                           b"BT /F1 12 Tf () Tj ET " * 20_000),
    "docx_20k_empty_paragraphs": lambda p: _docx(p, b"<w:p/>" * 20_000),
}


def bench_hostile() -> None:
    print("Hostile files (parse only; each ends as manual review):")
    with tempfile.TemporaryDirectory() as tmp:
        for name, make in HOSTILE.items():
            path = Path(tmp) / (name + (".pdf" if name.startswith("pdf") else ".docx"))
            make(path)
            s = time.perf_counter()
            try:
                parse_cv(path)
                outcome = "parsed"
            except ParseError as exc:
                outcome = str(exc).split(":")[0][:60] if ":" in str(exc) else str(exc)[:60]
            took = time.perf_counter() - s
            print(f"  {name:<27} {path.stat().st_size:>7} bytes  {took:7.2f} s  ({outcome})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", action="store_true", help="skip the hostile files")
    ap.add_argument("--reps", type=int, default=5)
    args = ap.parse_args()
    bench_samples(args.reps)
    if not args.samples:
        bench_hostile()
