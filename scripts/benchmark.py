"""Measure the offline pipeline on the sample CVs and on a few hostile files (demo data).

    python scripts/benchmark.py            # samples + hostile files
    python scripts/benchmark.py --samples  # samples only

Prints per-stage times for the 20 samples (best of N repetitions), the size of the prompt
that real mode would send, and the parse time of generated hostile PDF/DOCX files that are
small on disk but expensive to parse. Nothing is sent anywhere; no API key is needed.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

from cv_screen.extract import SYSTEM_PROMPT, MockExtractor, build_profile, build_user_message
from cv_screen.job import load_job
from cv_screen.matching import match_profile
from cv_screen.parsing import ParseError, find_cv_files, parse_cv
from cv_screen.redact import redact
from cv_screen.schema import extraction_json_schema

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.hostile_files import EMPTY_TEXT_OP, docx_with_body, pdf  # noqa: E402

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


HOSTILE = {
    "pdf_400k_empty_text_ops": lambda p: pdf(p, EMPTY_TEXT_OP * 400_000),
    "pdf_form_20k_ops_x40": lambda p: pdf(p, b"/X0 Do " * 40, EMPTY_TEXT_OP * 20_000),
    "docx_20k_empty_paragraphs": lambda p: docx_with_body(p, b"<w:p/>" * 20_000),
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
