# Case Study 3: CV Screening Assistant (Human in the Loop)

## Goal
Build a tool that helps a small company's hiring manager go through incoming CVs faster: it
extracts structured info, checks it against the job's requirements, and produces a ranked
shortlist with reasons. A human makes every decision. This repo is a public portfolio case study
for an AI automation consultant.

## Demo scenario
A 20-person e-commerce company hiring a "Junior Customer Support Specialist". 40 applications
arrive per opening and the manager spends evenings reading them.

## MVP scope
In scope:
- `samples/` with ~20 synthetic CVs (PDF and DOCX, generated, clearly fake people) and one job
  description with must-have and nice-to-have criteria in YAML.
- Parse PDF/DOCX to text; extract with the Claude API (default `claude-haiku-4-5-20251001`,
  configurable) into a strict schema: skills, years of relevant experience, languages, education,
  evidence quotes from the CV for each claim.
- Match against criteria: per-criterion met / partly / not met / unknown, each with a quoted
  evidence line. No hidden scoring.
- Ranked shortlist as Markdown + CSV, plus a one-page summary per candidate.
- Draft (not send) a polite reply email per candidate for the manager to edit.
- CLI: `screen run samples/ --job job.yaml`, with `MOCK_LLM=1` / fixture mode.

Out of scope: auto-rejecting anyone, sending emails, ATS integration, video/interview analysis.

## Fairness and privacy (must be in the design and README)
- Strip or ignore protected attributes (name, photo, age, gender, nationality, marital status,
  address) before matching; test that changing them does not change the result.
- The tool recommends, the human decides. Say so in the output.
- Data stays local; retention note; no real CVs in the repo.

## Constraints
- Never commit secrets; `.env.example` only.
- Tests must run offline with fixtures.

## Deliverables
1. Code + pytest suite (parsing, schema, criteria matching, the protected-attribute invariance
   test, missing-info handling).
2. GitHub Actions CI.
3. English `README.md`: architecture (Mermaid), quickstart, config, limitations, fairness note.
4. English `CASE_STUDY.md` answering: What problem does it solve? How does it work? What is the
   concrete result in a real business? Before/after table: manual minutes per CV (labeled
   estimate with assumption) vs. measured time and cost per 40 CVs on the demo run.
   Never invent client results.
5. Optional `n8n/` workflow JSON: new CV in a folder/inbox triggers screening and notifies the manager.

## Project tracking (required)
- `PROGRESS.md`: split the work into phases with checkbox tasks. Create it first, re-read it at
  the start of each work chunk, tick tasks as they finish, and leave an accurate final state
  (done / not done / next steps) at the end.
- `DECISIONS.md`: one short entry per architecture or security decision: date, decision,
  alternatives considered, why. Write it when the decision is made, not afterwards.
- Commit both with the code.

## Build log for content (required)
Keep `BUILD_LOG.md` updated as you work, so the member can turn the build into posts later:
- Key decisions and why (including options you rejected).
- Problems hit and how you solved them (real errors, short snippets).
- Measured numbers from demo runs (time, cost, accuracy), labeled as demo data.
- 3-5 "post hooks": one-sentence lessons or surprising findings worth sharing.
- Suggested screenshots/GIFs to capture (exact command or page to show).
Commit it with the code; keep it factual, no invented results.

## Definition of done
`screen run` produces the shortlist on the samples (mock and real mode), invariance test passes,
CI green, docs complete, BUILD_LOG.md, PROGRESS.md and DECISIONS.md up to date, no secrets in history, PR opened with a summary.
