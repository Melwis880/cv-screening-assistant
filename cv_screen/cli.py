"""Command line interface: `screen run samples/ --job job.yaml`."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import click

from cv_screen.extract import DEFAULT_MODEL, ClaudeExtractor, MockExtractor
from cv_screen.job import load_job
from cv_screen.pipeline import run_screening
from cv_screen.report import write_outputs


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Minimal .env reader; existing environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if value.strip():
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@click.group()
def main() -> None:
    """CV screening assistant. The tool recommends, the human decides."""
    _load_dotenv()


@main.command()
@click.argument("folder", type=click.Path(exists=True, path_type=Path))
@click.option("--job", "job_path", required=True, type=click.Path(exists=True, path_type=Path),
              help="Job description YAML with must-have and nice-to-have criteria.")
@click.option("--out", "out_dir", default="out", show_default=True,
              type=click.Path(path_type=Path), help="Output folder (contains personal data).")
@click.option("--mock/--real", "mock", default=None,
              help="Offline rule-based extractor instead of the Claude API. "
                   "Default: real unless MOCK_LLM=1.")
@click.option("--model", default=None,
              help=f"Claude model for extraction. Default: $CV_SCREEN_MODEL or {DEFAULT_MODEL}.")
@click.option("--as-of", "as_of", default=None,
              help="Count experience up to this date (YYYY-MM-DD). Default: today.")
@click.option("--blind", is_flag=True,
              help="Hide candidate names in the shortlist and summaries too.")
@click.option("--workers", default=4, show_default=True, help="Parallel API calls.")
def run(folder: Path, job_path: Path, out_dir: Path, mock: bool | None, model: str | None,
        as_of: str | None, blind: bool, workers: int) -> None:
    """Screen every PDF/DOCX/TXT CV in FOLDER against the job and write a ranked shortlist."""
    job = load_job(job_path)
    if mock is None:
        mock = _env_flag("MOCK_LLM")
    as_of_date = date.fromisoformat(as_of) if as_of else date.today()
    if mock:
        extractor, model_name = MockExtractor(), None
    else:
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise click.UsageError(
                "No ANTHROPIC_API_KEY set. Put it in .env (see .env.example) or run with "
                "--mock / MOCK_LLM=1 for the offline demo."
            )
        model_name = model or os.environ.get("CV_SCREEN_MODEL") or DEFAULT_MODEL
        extractor = ClaudeExtractor(model=model_name)

    click.echo(f"Screening {folder} for '{job.title}' with the {extractor.name} extractor"
               + (f" ({model_name})" if model_name else "") + " ...")
    result = run_screening(folder, job, extractor, as_of_date, model=model_name, workers=workers)
    paths = write_outputs(result, out_dir, blind=blind)

    tiers = {t: sum(1 for c in result.ranked if c.counts.tier == t) for t in "ABC"}
    click.echo(f"Screened {len(result.ranked)} of {len(result.candidates)} CVs in "
               f"{result.wall_seconds:.1f}s. Tier A: {tiers['A']}, B: {tiers['B']}, "
               f"C: {tiers['C']}, manual review: {len(result.failed)}.")
    if result.usage.input_tokens:
        cost = result.usage.cost_usd
        click.echo(f"Tokens: {result.usage.input_tokens} in / {result.usage.output_tokens} out"
                   + (f", cost ${cost:.4f}" if cost is not None else ", cost unknown for model"))
    click.echo(f"Shortlist: {paths['shortlist_md']}  (also {paths['shortlist_csv'].name}, "
               f"candidates/, emails/, run_report.json)")
    click.echo("Reminder: the tool recommends, you decide. No emails were sent.")


if __name__ == "__main__":
    main()
