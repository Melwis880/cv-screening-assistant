"""Run the full screening: parse -> redact -> extract -> verify -> match -> rank."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from cv_screen.extract import ExtractionError, Extractor, Usage, build_profile
from cv_screen.job import JobSpec
from cv_screen.matching import Counts, count, match_profile, sort_key
from cv_screen.parsing import ParseError, find_cv_files, parse_file
from cv_screen.redact import redact
from cv_screen.schema import CandidateProfile, CriterionResult


@dataclass
class CandidateResult:
    candidate_id: str
    source_file: str
    name: str | None  # local only, never used for extraction or matching
    redacted_text: str = ""
    removed: dict[str, int] = field(default_factory=dict)
    profile: CandidateProfile | None = None
    results: list[CriterionResult] = field(default_factory=list)
    counts: Counts | None = None
    error: str | None = None
    usage: Usage = field(default_factory=Usage)
    seconds: float = 0.0
    rank: int | None = None


@dataclass
class ScreeningRun:
    job: JobSpec
    extractor: str
    model: str | None
    as_of: date
    candidates: list[CandidateResult]
    wall_seconds: float
    usage: Usage

    @property
    def ranked(self) -> list[CandidateResult]:
        return [c for c in self.candidates if c.counts is not None]

    @property
    def failed(self) -> list[CandidateResult]:
        return [c for c in self.candidates if c.counts is None]


def screen_text(
    candidate_id: str,
    source_file: str,
    text: str,
    job: JobSpec,
    extractor: Extractor,
    as_of: date,
) -> CandidateResult:
    """Screen one CV given as text. Protected attributes are removed first."""
    red = redact(text)
    cand = CandidateResult(candidate_id, source_file, red.name, red.text, red.removed)
    try:
        extraction, usage = extractor.extract(red.text, job)
    except ExtractionError as exc:
        cand.error = f"extraction failed: {exc}"
        return cand
    cand.usage = usage
    cand.profile = build_profile(candidate_id, source_file, red.text, extraction, as_of,
                                 relevance_keywords=job.relevant_experience.keywords)
    cand.results = match_profile(cand.profile, job)
    cand.counts = count(cand.results)
    return cand


def _screen_file(path: Path, job: JobSpec, extractor: Extractor, as_of: date) -> CandidateResult:
    started = time.perf_counter()
    try:
        text = parse_file(path)
    except ParseError as exc:
        cand = CandidateResult(path.stem, path.name, None, error=str(exc))
    else:
        try:
            cand = screen_text(path.stem, path.name, text, job, extractor, as_of)
        except Exception as exc:  # one bad CV must not stop the run; it goes to manual review
            cand = CandidateResult(path.stem, path.name, None,
                                   error=f"{type(exc).__name__}: {exc}")
    cand.seconds = time.perf_counter() - started
    return cand


def run_screening(
    folder: Path,
    job: JobSpec,
    extractor: Extractor,
    as_of: date,
    model: str | None = None,
    workers: int = 4,
) -> ScreeningRun:
    files = find_cv_files(folder)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        candidates = list(pool.map(lambda f: _screen_file(f, job, extractor, as_of), files))
    wall = time.perf_counter() - started

    ranked = sorted((c for c in candidates if c.counts is not None),
                    key=lambda c: sort_key(c.candidate_id, c.counts))
    for i, cand in enumerate(ranked, start=1):
        cand.rank = i
    total = Usage()
    for cand in candidates:
        total.add(cand.usage)
    ordered = ranked + [c for c in candidates if c.counts is None]
    return ScreeningRun(job, extractor.name, model, as_of, ordered, wall, total)
