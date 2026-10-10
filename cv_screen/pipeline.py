"""Run the full screening: parse -> redact -> extract -> verify -> match -> rank."""

from __future__ import annotations

import hashlib
import re
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


class DuplicateCandidateError(ValueError):
    """Two CV files would get the same candidate ID, so one would overwrite the other's output."""


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


def file_sha256(path: Path) -> str | None:
    try:
        with path.open("rb") as fh:
            return hashlib.file_digest(fh, "sha256").hexdigest()
    except OSError:
        return None  # unreadable: parsing reports it and the CV goes to manual review


def candidate_id(path: Path, sha256: str | None) -> str:
    """File stem plus 8 hex digits of the file's SHA-256: two files never share outputs, and the
    ID is safe as a file name and inside a Markdown link."""
    stem = re.sub(r"[^\w.-]+", "_", path.stem).strip("_").lstrip("-.")[:60] or "cv"
    digest = sha256 or hashlib.sha256(path.name.encode()).hexdigest()
    return f"{stem}-{digest[:8]}"


def assign_ids(files: list[Path]) -> list[str]:
    """IDs for all files, checked for collisions before anything is screened or written."""
    ids = [candidate_id(f, file_sha256(f)) for f in files]
    first: dict[str, Path] = {}
    clashes = []
    for path, cid in zip(files, ids, strict=True):
        if cid in first:
            clashes.append(f"{first[cid].name} and {path.name} (both {cid})")
        first.setdefault(cid, path)
    if clashes:
        raise DuplicateCandidateError(
            "These CV files would get the same candidate ID (same name and content?): "
            + "; ".join(clashes) + ". Remove the duplicate and run again. Nothing was screened."
        )
    return ids


def _screen_file(path: Path, cid: str, job: JobSpec, extractor: Extractor,
                 as_of: date) -> CandidateResult:
    started = time.perf_counter()
    try:
        text = parse_file(path)
    except ParseError as exc:
        cand = CandidateResult(cid, path.name, None, error=str(exc))
    else:
        try:
            cand = screen_text(cid, path.name, text, job, extractor, as_of)
        except Exception as exc:  # one bad CV must not stop the run; it goes to manual review
            cand = CandidateResult(cid, path.name, None, error=f"{type(exc).__name__}: {exc}")
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
    ids = assign_ids(files)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        candidates = list(pool.map(lambda f, cid: _screen_file(f, cid, job, extractor, as_of),
                                   files, ids))
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
