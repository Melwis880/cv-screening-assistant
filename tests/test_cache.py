"""Re-runs (e.g. the n8n trigger on every new CV) only pay for CVs that were not seen before."""

import os
import stat
import time

import pytest
from click.testing import CliRunner

from cv_screen import cli
from cv_screen.cache import ExtractionCache
from cv_screen.extract import ClaudeExtractor
from cv_screen.pipeline import run_screening
from tests.conftest import CV_TEXT, ROOT, SAMPLES
from tests.fakes import GOOD_PAYLOAD, FakeClient


def _folder(tmp_path, n=3):
    folder = tmp_path / "cvs"
    folder.mkdir(exist_ok=True)
    for i in range(n):
        (folder / f"cv{i}.txt").write_text(f"{CV_TEXT}Reference {i}\n", encoding="utf-8")
    return folder


def _run(folder, job, as_of, cache, payload=GOOD_PAYLOAD, model="claude-haiku-4-5-20251001"):
    client = FakeClient(payload)
    run = run_screening(folder, job, ClaudeExtractor(client=client, model=model), as_of,
                        cache=cache)
    return run, len(client.messages.calls)


def test_second_run_makes_no_api_calls(tmp_path, job, as_of):
    folder, cache = _folder(tmp_path), ExtractionCache(tmp_path / "cache")
    first, calls1 = _run(folder, job, as_of, cache)
    second, calls2 = _run(folder, job, as_of, cache)
    assert (calls1, calls2) == (3, 0)
    assert second.usage.input_tokens == 0 and second.usage.cost_usd == 0
    assert all(c.cached for c in second.candidates) and not any(c.cached for c in first.candidates)
    assert [c.results for c in first.candidates] == [c.results for c in second.candidates]


def test_the_same_cv_twice_in_one_run_is_billed_once(tmp_path, job, as_of):
    folder = tmp_path / "cvs"
    folder.mkdir()
    for name in ("cv.txt", "cv (1).txt", "cv-again.txt"):  # one attachment saved three times
        (folder / name).write_text(CV_TEXT, encoding="utf-8")

    def slow(_):
        time.sleep(0.2)  # all workers start before the first call returns
        return GOOD_PAYLOAD

    client = FakeClient(slow)
    run = run_screening(folder, job, ClaudeExtractor(client=client), as_of, workers=4,
                        cache=ExtractionCache(tmp_path / "cache"))
    assert len(client.messages.calls) == 1
    assert sorted(c.cached for c in run.candidates) == [False, True, True]
    assert len({str(c.results) for c in run.candidates}) == 1


def test_only_new_or_changed_cvs_are_billed(tmp_path, job, as_of):
    folder, cache = _folder(tmp_path), ExtractionCache(tmp_path / "cache")
    _run(folder, job, as_of, cache)
    (folder / "cv0.txt").write_text(CV_TEXT + "Changed\n", encoding="utf-8")
    (folder / "new.txt").write_text(CV_TEXT + "New\n", encoding="utf-8")
    _, calls = _run(folder, job, as_of, cache)
    assert calls == 2


def test_a_different_model_or_job_is_not_served_from_cache(tmp_path, job, as_of):
    folder, cache = _folder(tmp_path, n=1), ExtractionCache(tmp_path / "cache")
    _run(folder, job, as_of, cache)
    assert _run(folder, job, as_of, cache, model="claude-sonnet-5-5")[1] == 1
    other_job = job.model_copy(update={"relevant_experience": job.relevant_experience.model_copy(
        update={"description": "Any warehouse work."})})
    assert _run(folder, other_job, as_of, cache)[1] == 1


def test_failed_extractions_are_not_cached(tmp_path, job, as_of):
    folder, cache = _folder(tmp_path, n=1), ExtractionCache(tmp_path / "cache")
    run, _ = _run(folder, job, as_of, cache, payload="{not json")
    assert run.failed
    assert _run(folder, job, as_of, cache)[1] == 1


def test_cache_is_owner_only(tmp_path, job, as_of):
    old = os.umask(0)
    try:
        cache = ExtractionCache(tmp_path / "cache")
        _run(_folder(tmp_path), job, as_of, cache)
    finally:
        os.umask(old)
    assert stat.S_IMODE((tmp_path / "cache").stat().st_mode) == 0o700
    files = list((tmp_path / "cache").iterdir())
    assert len(files) == 3
    assert {stat.S_IMODE(f.stat().st_mode) for f in files} == {0o600}


def test_expired_entries_are_not_used_and_are_deleted(tmp_path, job, as_of):
    folder, cache = _folder(tmp_path), ExtractionCache(tmp_path / "cache", ttl_days=30)
    _run(folder, job, as_of, cache)
    old = time.time() - 31 * 86400
    for f in (tmp_path / "cache").iterdir():
        os.utime(f, (old, old))
    assert cache.purge_expired() == 3
    assert list((tmp_path / "cache").iterdir()) == []
    assert _run(folder, job, as_of, cache)[1] == 3


def test_corrupt_or_tampered_entries_are_ignored(tmp_path, job, as_of):
    folder, cache = _folder(tmp_path, n=1), ExtractionCache(tmp_path / "cache")
    _run(folder, job, as_of, cache)
    entry = next((tmp_path / "cache").iterdir())
    entry.write_text('{"skills": "not a list"}')
    assert _run(folder, job, as_of, cache)[1] == 1  # invalid entry -> fresh call
    assert _run(folder, job, as_of, cache)[1] == 0  # and the fresh result was stored


@pytest.fixture
def fake_api(monkeypatch):
    """The CLI's real-mode extractor, with a fake client that counts calls."""
    clients = []

    def make(model):
        clients.append(FakeClient(GOOD_PAYLOAD))
        return ClaudeExtractor(client=clients[-1], model=model)

    monkeypatch.setattr(cli, "ClaudeExtractor", make)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")
    return clients


def test_cli_caches_in_real_mode_by_default(tmp_path, fake_api):
    args = ["run", str(SAMPLES), "--job", str(ROOT / "job.yaml"), "--real",
            "--out", str(tmp_path / "out"), "--as-of", "2026-10-01"]
    first = CliRunner().invoke(cli.main, args)
    second = CliRunner().invoke(cli.main, args)
    assert first.exit_code == 0 and second.exit_code == 0, first.output + second.output
    assert [len(c.messages.calls) for c in fake_api] == [20, 0]
    assert "20 of 20 CVs reused from the cache" in second.output
    assert (tmp_path / "out" / ".cache" / "extractions").is_dir()

    third = CliRunner().invoke(cli.main, [*args, "--no-cache"])
    assert third.exit_code == 0 and len(fake_api[2].messages.calls) == 20
