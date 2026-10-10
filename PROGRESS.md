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
- [x] Tests: parsing, redaction

## Phase 3 – Extraction
- [x] Strict schema (skills, experience entries, languages, education, evidence quote per claim)
- [x] Claude API extractor (default `claude-haiku-4-5-20251001`, configurable), structured outputs
- [x] Mock extractor (`MOCK_LLM=1` / `--mock`) that works offline on the sample format
- [x] Evidence verification: every quote must appear in the CV text, else the claim is dropped and flagged
- [x] Years of relevant experience computed in code from dated entries
- [x] Tests: schema validation, real extractor against a fake client, evidence verification, missing info

## Phase 4 – Matching and ranking
- [x] Per-criterion met / partly / not met / unknown with evidence line
- [x] Transparent ranking (sort order printed, no hidden score)
- [x] Tests: criteria matching, ranking, protected-attribute invariance

## Phase 5 – Outputs
- [x] `shortlist.md` + `shortlist.csv`
- [x] One-page summary per candidate
- [x] Draft reply email per candidate (not sent): three variants (invite / ask for missing info / decline), tool suggestion labelled
- [x] `run_report.json` with timing, tokens, cost
- [x] "Tool recommends, human decides" notice in every output

## Phase 6 – CI and docs
- [x] GitHub Actions: ruff + pytest + sample reproducibility + mock-mode smoke run (Python 3.11-3.13)
- [x] README.md (architecture Mermaid, quickstart, config, limitations, fairness, privacy/retention)
- [x] CASE_STUDY.md with before/after table (estimate labeled, measured numbers only from demo runs)
- [x] Optional `n8n/` workflow JSON (not tested against a live n8n instance)

## Phase 7 – Definition of done
- [x] Mock-mode run on samples produces shortlist
- [ ] Real-mode run on samples produces shortlist — **blocked: no API key in the build environment.** Code path tested offline (fake client + real SDK with mocked HTTP transport).
- [x] Invariance test passes
- [x] CI green
- [x] No secrets in history
- [x] PR opened with summary (as draft, because the real-mode run is still open)

## Phase 8 – Security review fixes (2026-10-11)
Findings from the `/security-audit` of this branch. Each fix has a test that fails on the old code
where the issue can be reproduced.
- [x] Evidence must prove the claim: min quote length, claim value inside its own quote, CV text escaped in the prompt
- [x] CSV formula injection: escape every string cell in `shortlist.csv`
- [ ] Unique candidate IDs (stem + short SHA-256), fail before writing output if IDs collide
- [ ] Input limits (file size, PDF pages, DOCX unpacked size, text length) -> manual review, configurable
- [ ] Flag PDFs with hidden text (white, invisible, tiny or off-page)
- [ ] Output folder 0700, files 0600 regardless of umask
- [ ] Extraction cache by file SHA-256 (validated results only, owner-only, TTL)
- [ ] Dependency floors and upper bounds (`pypdf>=6.1`)
- [ ] Markdown escaping of applicant/model strings; strict name pattern
- [ ] `.env` loader allowlist
- [ ] Control/format characters stripped from applicant strings printed by the CLI
- [ ] README: redaction is best-effort; IMAP attachments saved under generated names
- [ ] BUILD_LOG "Security review" section, DECISIONS entries
- Out of scope (agreed): SHA-pinning GitHub Actions, a lockfile.

## Final state (2026-10-09)

**Done**
- Full pipeline: parse (PDF/DOCX/TXT) -> redact protected attributes -> extract (Claude structured outputs or offline mock) -> verify quotes -> match -> tiered ranking -> shortlist.md/.csv, per-candidate summaries, three-variant email drafts, run_report.json.
- 20 synthetic, reproducible sample CVs (10 PDF, 10 DOCX, three layouts) and `job.yaml`.
- 97 offline tests, including protected-attribute invariance (text, Claude prompt and results identical) and missing-info handling. CI green on Python 3.11-3.13.
- README (Mermaid architecture, quickstart, config, fairness/privacy, limitations), CASE_STUDY (measured vs estimated clearly labelled), DECISIONS, BUILD_LOG, optional n8n workflow.

**Not done**
- Real-mode demo run on the samples (needs `ANTHROPIC_API_KEY`). Therefore no measured real-mode time, tokens, cost or extraction accuracy yet; CASE_STUDY shows estimates labelled as such.
- n8n workflow not tested in a running n8n instance.

**Next steps**
1. `cp .env.example .env`, add a key, run `screen run samples/ --job job.yaml --as-of 2026-10-01`; copy `out/run_report.json` numbers into CASE_STUDY.md and BUILD_LOG.md; compare tiers with the mock run and note differences.
2. Spot-check extraction accuracy on the samples (claims vs CV) and record it as demo data.
3. Optionally compare a second model via `--model` on the same samples.
4. Pilot with a real hiring manager: time per opening, disagreement with tiers, wrong claims found.
