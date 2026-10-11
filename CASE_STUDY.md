# Case study: CV screening assistant for a small online shop

> Portfolio case study. The company, the job and all 20 CVs are fictional and synthetic.
> There is no client deployment yet, so there are **no client results** in this document.
> Numbers are labelled as **demo data** (measured on the synthetic samples in mock mode) or
> **estimate** (with the assumption stated). No run against the real Claude API has been
> measured yet.

## What problem does it solve?

A 20-person online shop hires a *Junior Customer Support Specialist*. Each opening brings
around 40 applications. There is no HR department: the hiring manager reads every CV in the
evening, keeps notes in a spreadsheet and writes replies one by one. That is slow, it is
inconsistent (CV number 35 is read by a more tired person than CV number 3), and it is easy to
be swayed by things that should not matter, such as a photo, a name or an age.

Off-the-shelf applicant tracking systems solve this with keyword filters and auto-rejects,
which a small company often does not want: it cannot explain those rejections, and it loses
good people whose CVs are just formatted differently.

## How does it work?

`screen run applications/ --job job.yaml` does six things for every CV:

1. **Reads** the PDF or DOCX as text (photos and other images are never read).
2. **Removes protected attributes** locally: name, photo, date of birth and age, gender,
   nationality, marital status, address, contact details, gendered pronouns and titles
   (field labels in English and German, names in any script).
3. **Extracts** skills, dated roles, languages (CEFR level) and education with Claude
   (default model `claude-haiku-4-5-20251001`) into a strict JSON schema. Every item must
   carry a verbatim quote from the CV. Only the redacted text is sent.
4. **Verifies** each quote against the CV text and drops claims whose quote is not there or
   does not contain the claimed value (the skill, the language level, the job's dates).
   Years of relevant experience are computed in code, not by the model.
5. **Matches** against the job's must-haves and nice-to-haves from a YAML file. Each
   criterion is *met*, *partly*, *not met* or *unknown*, with the CV line as evidence.
   Missing information is *unknown* and becomes a question, never a silent "no".
6. **Ranks and reports**: three tiers (all must-haves met / some unclear / one looks missing),
   a sort rule printed at the top, a one-page summary per candidate, and three draft replies
   per candidate (invite, ask for missing information, decline). Nothing is sent.

The manager then reads the shortlist, checks the quotes, decides, and edits and sends the
emails they choose. Architecture diagram and design decisions: [`README.md`](README.md),
[`DECISIONS.md`](DECISIONS.md).

Fairness is tested, not promised: a test changes name, age, gender, nationality, marital
status, address, photo and pronouns on the same CV and asserts that the exact text sent to the
model, the prompt and the match results are identical. That test found a real leak during the
build, and extending it in the second security review found two more: names starting with a
letter like Ö or Ł, or containing "van der", were not removed at all, and neither were German
field labels such as `Geburtsdatum:` (see [`BUILD_LOG.md`](BUILD_LOG.md)). A fairness test is
only as good as the people it imagines.

## What is the concrete result in a real business?

No real business has used it yet, so there is no measured business result to report. What
the demo shows, and what a pilot would need to confirm:

- **Demo data (mock mode):** on the 20 synthetic CVs the tool produced a complete shortlist with
  7 candidates in tier A, 9 in tier B (each with specific questions to ask) and 4 in tier C,
  with an evidence quote for every met/partly/not met status and 0 CVs dropped. This is the
  mock extractor on CVs in a known layout; it shows the pipeline works, not how accurate
  Claude is on real CVs.
- **Expected effect (estimate):** the manager stops reading every CV start to finish and
  instead reviews a one-page summary per candidate, reading the full CV only for the people
  they are considering. Replies start from a draft instead of a blank page.
- **What a pilot should measure:** manager minutes per opening before and after (timed, not
  remembered), how often the manager disagrees with a tier, how many extracted claims were
  wrong when checked against the CV, and real API cost per opening.

## Before / after per opening (40 CVs)

| | Before: manual | After: with the tool |
|---|---|---|
| Reading and assessing CVs | **Estimate:** ~7 min per CV, so ~280 min (~4.7 h) for 40. Assumption: ~5 min to read a 1-2 page CV and compare it with the requirements, ~2 min for notes. | **Estimate:** ~2 min per CV to check a one-page summary and its quotes, plus reading the full CV of the ~10 strongest candidates (~5 min each): ~130 min for 40. Not yet timed with a real manager. |
| Tool processing time | - | **Demo data, mock mode:** 0.20-0.27 s for 20 CVs (5 runs on a 4-core Linux machine, after the optimization pass; 0.33-0.39 s before; see [`BUILD_LOG.md`](BUILD_LOG.md)), i.e. under 1 s per 40 CVs. **Real mode: not measured yet** (no API key was used while building it). It is bounded by API latency; with 4 parallel calls, expect minutes rather than seconds. |
| API cost | - | **Demo data, mock mode:** $0. **Real mode: not measured yet.** **Estimate:** the fixed prompt plus schema is ~4,750 characters and the user message for a demo CV averages ~840 characters, so roughly 1,500-2,000 input tokens and up to ~1,000 output tokens per CV. At Haiku 4.5 prices ($1 / $5 per million input / output tokens) that is under $0.01 per CV, roughly **$0.20-0.40 per 40 CVs**. Real CVs are longer than the demo CVs. |
| Writing replies | **Estimate:** ~2 min per reply, ~80 min for 40. | **Estimate:** ~30 s to pick and personalise a draft, ~20 min for 40. |
| Consistency | Depends on the evening. | Same rules for every CV, written down in `job.yaml`, printed in the shortlist. |
| Protected attributes | Visible while reading. | Removed before matching; invariance is tested in CI. The manager still sees the name after matching (or not, with `--blind`). |

**How to replace the estimates with measurements:** run
`screen run <folder> --job job.yaml` with an API key; `out/run_report.json` records
wall-clock time, input/output tokens and cost for the run, and `cost_usd_per_40_cvs`
normalises it to one opening.

## Limits worth saying out loud

- Redaction is best-effort: regular expressions, with the name taken only from a `Name:`
  label or the CV's first line. Dates still hint at age; school names can hint at origin.
- Hostile files (PDF/DOCX that are cheap to send but expensive to parse, hidden text) end in
  manual review or carry a warning; they cannot stall a run for more than a few seconds each
  (worst case found in testing: about 7 s, demo data from
  [`OPTIMIZATIONS.md`](OPTIMIZATIONS.md)).
- The model can still misread a CV. Quote verification catches invented quotes and quotes
  that do not show the claimed value, not every wrong interpretation of a real one, which is
  why the summary shows the quote.
- The tool is built for the demo role; prompts and outputs are in English and redaction knows
  English and German field labels. Other roles need their own `job.yaml` and a quick check
  that the criteria types fit.
- A pilot with a real hiring manager is the next step, not a formality.
