# Progress

Status legend: `[x]` done, `[ ]` not done. Re-read at the start of each work chunk.

## Phase 0 – Tracking and skeleton
- [x] PROGRESS.md, DECISIONS.md, BUILD_LOG.md created
- [x] `pyproject.toml`, package layout (`cv_screen/`), `.env.example`
- [x] `screen` CLI entry point stub

## Phase 1 – Samples
- [x] `job.yaml`: Junior Customer Support Specialist, must-have + nice-to-have criteria
- [x] `scripts/generate_samples.py`: ~20 synthetic CVs (PDF + DOCX), clearly fictional, deterministic
- [x] Generated files committed under `samples/`

## Phase 2 – Parsing and privacy
- [x] PDF/DOCX/TXT to text
- [x] Redaction of protected attributes (name, photo, age/DOB, gender, nationality, marital status, address, contact details, gendered pronouns)
- [ ] Tests: parsing, redaction

## Phase 3 – Extraction
- [x] Strict schema (skills, experience entries, languages, education, evidence quote per claim)
- [x] Claude API extractor (default `claude-haiku-4-5-20251001`, configurable), structured outputs
- [x] Mock extractor (`MOCK_LLM=1` / `--mock`) that works offline on the sample format
- [x] Evidence verification: every quote must appear in the CV text, else the claim is dropped and flagged
- [x] Years of relevant experience computed in code from dated entries
- [ ] Tests: schema validation, real extractor against a fake client, evidence verification, missing info

## Phase 4 – Matching and ranking
- [x] Per-criterion met / partly / not met / unknown with evidence line
- [x] Transparent ranking (sort order printed, no hidden score)
- [ ] Tests: criteria matching, ranking, protected-attribute invariance

## Phase 5 – Outputs
- [x] `shortlist.md` + `shortlist.csv`
- [x] One-page summary per candidate
- [x] Draft reply email per candidate (not sent): three variants (invite / ask for missing info / decline), tool suggestion labelled
- [x] `run_report.json` with timing, tokens, cost
- [x] "Tool recommends, human decides" notice in every output

## Phase 6 – CI and docs
- [ ] GitHub Actions: ruff + pytest + mock-mode smoke run
- [ ] README.md (architecture Mermaid, quickstart, config, limitations, fairness, privacy/retention)
- [ ] CASE_STUDY.md with before/after table (estimate labeled, measured numbers only from demo runs)
- [ ] Optional `n8n/` workflow JSON

## Phase 7 – Definition of done
- [ ] Mock-mode run on samples produces shortlist
- [ ] Real-mode run on samples produces shortlist
- [ ] Invariance test passes
- [ ] CI green
- [ ] No secrets in history
- [ ] PR opened with summary

## Final state
_Filled in at the end._
