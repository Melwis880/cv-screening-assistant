"""Write the shortlist (Markdown + CSV), per-candidate summaries, email drafts, run report."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from cv_screen.fileio import open_private, private_dir, write_private
from cv_screen.job import (
    EducationCriterion,
    ExperienceCriterion,
    LanguageAnyCriterion,
    LanguageCriterion,
)
from cv_screen.matching import RANKING_RULE, TIERS
from cv_screen.pipeline import CandidateResult, DuplicateCandidateError, ScreeningRun

HUMAN_DECIDES = (
    "**This tool recommends, the hiring manager decides.** Nobody is rejected automatically. "
    "Protected attributes (name, photo, age, gender, nationality, marital status, address) were "
    "removed before matching. Check the evidence quotes before acting on any line below."
)
SYMBOL = {"met": "met", "partly": "partly", "not met": "NOT met", "unknown": "unknown"}
# Spreadsheet apps evaluate a cell that starts with one of these as a formula.
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def write_outputs(run: ScreeningRun, out: Path, blind: bool = False) -> dict[str, Path]:
    ids = [c.candidate_id for c in run.candidates]
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise DuplicateCandidateError(
            f"duplicate candidate IDs {', '.join(dupes)}: nothing was written")
    private_dir(out)  # the outputs hold names and CV content
    private_dir(out / "candidates")
    private_dir(out / "emails")
    paths = {
        "shortlist_md": out / "shortlist.md",
        "shortlist_csv": out / "shortlist.csv",
        "run_report": out / "run_report.json",
    }
    write_private(paths["shortlist_md"], shortlist_markdown(run, blind))
    write_csv(run, paths["shortlist_csv"], blind)
    for cand in run.candidates:
        write_private(out / "candidates" / f"{cand.candidate_id}.md",
                      candidate_summary(run, cand, blind))
        write_private(out / "emails" / f"{cand.candidate_id}.md", email_draft(run, cand))
    write_private(paths["run_report"], json.dumps(run_report(run), indent=2))
    return paths


# Letters (any script), single spaces, ' . - between them: "Anne-Marie O'Neil", "J. R. Smith".
_NAME_RE = re.compile(r"[^\W\d_]+(?:[ '’.-]+[^\W\d_]+)*\.?")
_MD_SPECIAL = re.compile(r"([\\<>\[\]()!*_|`])")


def safe_name(name: str | None) -> str | None:
    """The name from the CV, only if it looks like a name; anything else is not shown."""
    name = (name or "").strip()
    return name if len(name) <= 80 and _NAME_RE.fullmatch(name) else None


def md(text: str) -> str:
    """Escape applicant- or model-supplied text for Markdown: it can't become a link, image,
    HTML, emphasis, code span, table cell break or new line."""
    return _MD_SPECIAL.sub(r"\\\1", re.sub(r"[\r\n]+", " ", text))


def _display_name(cand: CandidateResult, blind: bool) -> str:
    """Safe as-is in Markdown and CSV: a name that passed `safe_name`, or a fixed placeholder."""
    if blind:
        return "(hidden)"
    return safe_name(cand.name) or "(not found)"


def _reasons(cand: CandidateResult) -> str:
    """Must-haves first (every status), then only the nice-to-haves that are met or partly."""
    must = []
    for status in ("not met", "unknown", "partly", "met"):
        ids = [r.criterion_id for r in cand.results if r.must_have and r.status == status]
        if ids:
            must.append(f"{SYMBOL[status]}: {', '.join(ids)}")
    nice = [r.criterion_id + (" (partly)" if r.status == "partly" else "")
            for r in cand.results if not r.must_have and r.status in ("met", "partly")]
    nice_text = f". Nice-to-haves: {', '.join(nice)}" if nice else ""
    flags = "".join(f" WARNING: {f.split(':')[0]} (see summary)." for f in cand.flags)
    return "Must-haves " + "; ".join(must) + nice_text + flags


def _question(run: ScreeningRun, criterion_id: str) -> str:
    """A candidate-facing question for an unclear criterion."""
    crit = {c.id: c for c in run.job.criteria.must_have + run.job.criteria.nice_to_have}
    c = crit[criterion_id]
    if isinstance(c, LanguageCriterion):
        return f"Your {c.language} level, ideally as a CEFR level (e.g. B2 or C1)"
    if isinstance(c, LanguageAnyCriterion):
        return "Which other languages you speak, and at what level"
    if isinstance(c, ExperienceCriterion):
        return "The start and end dates (month and year) of your customer-facing roles"
    if isinstance(c, EducationCriterion):
        return "Your completed qualifications or vocational training"
    return f"Your experience with: {c.label[0].lower() + c.label[1:]}"


def shortlist_markdown(run: ScreeningRun, blind: bool) -> str:
    job = run.job
    n_must = len(job.criteria.must_have)
    n_nice = len(job.criteria.nice_to_have)
    lines = [
        f"# Shortlist: {job.title}",
        "",
        f"> {HUMAN_DECIDES}",
        "",
        f"- Company: {job.company}" if job.company else None,
        f"- CVs screened: {len(run.candidates)} ({len(run.failed)} need manual review)",
        f"- Extractor: {run.extractor}" + (f" ({run.model})" if run.model else ""),
        f"- Experience counted up to: {run.as_of.isoformat()}",
        f"- Ranking rule: {RANKING_RULE}",
        "",
        "## Criteria",
        "",
        "| ID | Must-have? | Criterion |",
        "|---|---|---|",
    ]
    for must, crit in ((True, job.criteria.must_have), (False, job.criteria.nice_to_have)):
        for c in crit:
            kind = "yes" if must else "nice to have"
            lines.append(f"| {c.id} | {kind} | {md(c.label)} |")
    lines += ["", "## Ranking", ""]
    for tier, title in TIERS.items():
        group = [c for c in run.ranked if c.counts.tier == tier]
        lines += [f"### Tier {tier}: {title} ({len(group)})", ""]
        if not group:
            lines += ["_None._", ""]
            continue
        lines += [
            f"| Rank | Candidate | Name (not used for matching) | Must-haves met (of {n_must}) "
            f"| Nice-to-haves met (of {n_nice}) | Unknowns | Reasons |",
            "|---|---|---|---|---|---|---|",
        ]
        for c in group:
            k = c.counts
            lines.append(
                f"| {c.rank} | [{md(c.candidate_id)}](candidates/{c.candidate_id}.md) "
                f"| {_display_name(c, blind)} "
                f"| {k.must_met} (+{k.must_partly} partly) "
                f"| {k.nice_met} (+{k.nice_partly} partly) "
                f"| {k.unknown_total} | {md(_reasons(c))} |"
            )
        lines.append("")
    if run.failed:
        lines += ["## Needs manual review (could not be screened)", ""]
        for c in run.failed:
            lines.append(f"- {md(c.source_file)}: {md(c.error or '')}")
        lines.append("")
    lines += [
        "## Next steps for the manager",
        "",
        "1. Open each candidate summary and check the quoted evidence against the CV.",
        "2. Resolve the `unknown` items (they are listed as questions in each summary).",
        "3. Decide who to invite. Draft emails are in `emails/`; nothing has been sent.",
        "",
    ]
    return "\n".join(line for line in lines if line is not None) + "\n"


def csv_cell(value: object) -> object:
    """Make a cell inert in Excel/LibreOffice: CV text like =HYPERLINK(...) stays text."""
    if isinstance(value, str) and value.startswith(FORMULA_START):
        return "'" + value
    return value


def write_csv(run: ScreeningRun, path: Path, blind: bool) -> None:
    crit_ids = [c.id for c in run.job.criteria.must_have + run.job.criteria.nice_to_have]
    header = ["rank", "candidate_id", "name", "source_file", "tier", "must_met", "must_partly",
              "must_not_met", "must_unknown", "nice_met", "nice_partly", "unknown_total"]
    header += [f"{cid}_status" for cid in crit_ids] + [f"{cid}_evidence" for cid in crit_ids]
    header += ["years_relevant_experience", "dropped_claims", "error", "file_warnings"]
    with open_private(path) as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for c in run.candidates:
            by_id = {r.criterion_id: r for r in c.results}
            k = c.counts
            row = [c.rank or "", c.candidate_id, _display_name(c, blind), c.source_file,
                   k.tier if k else "manual review"]
            row += ([k.must_met, k.must_partly, k.must_not_met, k.must_unknown, k.nice_met,
                     k.nice_partly, k.unknown_total] if k else [""] * 7)
            row += [by_id[cid].status if cid in by_id else "" for cid in crit_ids]
            row += [(by_id[cid].evidence or "") if cid in by_id else "" for cid in crit_ids]
            years = c.profile.years_relevant_experience if c.profile else None
            row += ["" if years is None else years,
                    " / ".join(c.profile.dropped_claims) if c.profile else "", c.error or "",
                    " / ".join(c.flags)]
            w.writerow([csv_cell(v) for v in row])


def candidate_summary(run: ScreeningRun, cand: CandidateResult, blind: bool) -> str:
    lines = [
        f"# {md(cand.candidate_id)}: summary for {run.job.title}",
        "",
        f"> {HUMAN_DECIDES}",
        "",
        f"- Source file: {md(cand.source_file)}",
        f"- Name (not used for matching): {_display_name(cand, blind)}",
    ]
    if cand.counts is None:
        lines += ["", f"**Could not be screened:** {md(cand.error or '')}", "",
                  "Please read this CV manually.", ""]
        return "\n".join(lines)
    k = cand.counts
    p = cand.profile

    years = "unknown" if p.years_relevant_experience is None else f"{p.years_relevant_experience:g}"
    lines += [
        f"- Rank {cand.rank}, tier {k.tier}: {TIERS[k.tier]}",
        f"- Must-haves: {k.must_met} met, {k.must_partly} partly, {k.must_not_met} not met, "
        f"{k.must_unknown} unknown",
        f"- Years of relevant experience (computed from dated roles): {years}",
        "",
        "## Criteria",
        "",
        "| Criterion | Must-have? | Status | Evidence from the CV | Note |",
        "|---|---|---|---|---|",
    ]
    for r in cand.results:
        ev = f'"{md(r.evidence)}"' if r.evidence else "-"
        lines.append(f"| {md(r.label)} | {'yes' if r.must_have else 'no'} "
                     f"| **{SYMBOL[r.status]}** | {ev} | {md(r.note)} |")
    e = p.extraction
    lines += ["", "## Extracted profile", ""]
    lines.append("- Roles: " + ("; ".join(
        f"{md(x.title)} ({md(x.start or '?')} to {md(x.end or '?')}"
        f"{', relevant' if x.relevant_to_job else ''})"
        for x in e.experience) or "none found"))
    lines.append("- Languages: " + (", ".join(
        f"{md(x.language)} {md(x.level or (x.level_as_written or 'level not given'))}"
        for x in e.languages) or "none found"))
    lines.append("- Education: " + ("; ".join(
        f"{x.level}{' (in progress)' if x.in_progress else ''}"
        + (f", {md(x.field)}" if x.field else "")
        for x in e.education) or "none found"))
    lines.append("- Skills: " + (", ".join(md(x.name) for x in e.skills) or "none found"))

    questions = [r for r in cand.results if r.status in ("unknown", "partly")]
    if questions:
        lines += ["", "## Questions to ask before deciding", ""]
        for r in questions:
            lines.append(f"- {md(r.label)}: {md(r.note)}")
    if cand.flags or p.dropped_claims or p.warnings:
        lines += ["", "## Warnings", ""]
        for f in cand.flags:
            lines.append(f"- **{md(f)}**")
        for d in p.dropped_claims:
            lines.append(f"- Dropped unverified claim: {md(d)}")
        for wmsg in p.warnings:
            lines.append(f"- {md(wmsg)}")
    removed = ", ".join(f"{k_}: {v}" for k_, v in sorted(cand.removed.items())) or "nothing found"
    lines += ["", f"_Removed before matching: {removed}._", ""]
    return "\n".join(lines)


def suggested_variant(cand: CandidateResult) -> str:
    if cand.counts is None:
        return "none - read the CV manually first"
    k = cand.counts
    if k.tier == "A":
        return "A (invite)"
    if k.tier == "B":
        return "B (ask for missing information)" if k.must_unknown else "A (invite)"
    return "C (decline)"


def email_draft(run: ScreeningRun, cand: CandidateResult) -> str:
    title = run.job.title
    company = run.job.company.split("(")[0].strip() or "our company"
    name = safe_name(cand.name)  # letters, spaces and ' . - only: safe in the email text
    greeting = f"Dear {name}," if name else "Dear applicant,"
    unknowns = [r for r in cand.results if r.must_have and r.status in ("unknown", "partly")]
    questions = "\n".join(f"- {_question(run, r.criterion_id)}" for r in unknowns)
    questions = questions or "- [add your question]"
    return f"""# Email drafts for {md(cand.candidate_id)} ({md(cand.source_file)})

> DRAFT ONLY - nothing has been sent. Pick one variant, edit it, and send it yourself.
> Tool suggestion: variant {suggested_variant(cand)}. The decision is yours.

## Variant A: invite to a short call

Subject: Your application for {title}

{greeting}

thank you for applying for the {title} role at {company}. We enjoyed reading your application
and would like to get to know you in a 30-minute video call.

Would one of these times work for you? [add 2-3 time slots]

Best regards,
[Your name]
{company}

## Variant B: ask for missing information

Subject: Your application for {title} - a quick question

{greeting}

thank you for applying for the {title} role at {company}. Before we decide on next steps,
could you tell us a bit more about the following?

{questions}

Best regards,
[Your name]
{company}

## Variant C: decline

Subject: Your application for {title}

{greeting}

thank you for your interest in the {title} role at {company} and for the time you put into
your application. After careful consideration we have decided to move forward with other
candidates whose experience matches this particular role more closely.

We wish you all the best in your search.

Kind regards,
[Your name]
{company}
"""


def run_report(run: ScreeningRun) -> dict:
    n = len(run.candidates)
    return {
        "job": run.job.title,
        "extractor": run.extractor,
        "model": run.model,
        "as_of": run.as_of.isoformat(),
        "cvs": n,
        "screened": len(run.ranked),
        "manual_review": len(run.failed),
        "wall_seconds": round(run.wall_seconds, 3),
        "seconds_per_cv": round(run.wall_seconds / n, 3) if n else None,
        "input_tokens": run.usage.input_tokens,
        "output_tokens": run.usage.output_tokens,
        "cost_usd": None if run.usage.cost_usd is None else round(run.usage.cost_usd, 5),
        "cost_usd_per_40_cvs": (
            None if run.usage.cost_usd is None or not n
            else round(run.usage.cost_usd / n * 40, 4)
        ),
        "tiers": {t: sum(1 for c in run.ranked if c.counts.tier == t) for t in ("A", "B", "C")},
        "dropped_claims": sum(len(c.profile.dropped_claims) for c in run.ranked),
        "file_warnings": sum(len(c.flags) for c in run.candidates),
        "cache_hits": run.cache_hits,
        "per_cv": [
            {"candidate_id": c.candidate_id, "seconds": round(c.seconds, 3),
             "input_tokens": c.usage.input_tokens, "output_tokens": c.usage.output_tokens,
             "cached": c.cached, "error": c.error, "file_warnings": c.flags}
            for c in run.candidates
        ],
    }
