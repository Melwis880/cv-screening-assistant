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
where the issue can be reproduced (the old CLI printed no applicant strings, so the terminal fix
guards the new output only).
- [x] Evidence must prove the claim: min quote length, claim value inside its own quote, CV text escaped in the prompt
- [x] CSV formula injection: escape every string cell in `shortlist.csv`
- [x] Unique candidate IDs (stem + short SHA-256), fail before writing output if IDs collide
- [x] Input limits (file size, PDF pages, DOCX unpacked size, text length) -> manual review, configurable
- [x] *Found while testing the limits:* quadratic-time regexes in redaction and evidence checks (one 30,000-character CV took 4-25 s; a 6 MB one would have run for hours) -> linear
- [x] Flag PDFs with hidden text (white, invisible, tiny or off-page)
- [x] Output folder 0700, files 0600 regardless of umask
- [x] Extraction cache by file SHA-256 (validated results only, owner-only, TTL)
- [x] Dependency floors and upper bounds (`pypdf>=6.1`)
- [x] Markdown escaping of applicant/model strings; strict name pattern
- [x] `.env` loader allowlist
- [x] Control/format characters stripped from applicant strings printed by the CLI
- [x] README: redaction is best-effort; IMAP attachments saved under generated names
- [x] BUILD_LOG "Security review" section, DECISIONS entries
- Out of scope (agreed): SHA-pinning GitHub Actions, a lockfile.

## Phase 9 – Optimization pass (2026-10-11)
Report first (`OPTIMIZATIONS.md`, `scripts/benchmark.py`), then one commit per fix, each with a
test that fails on the old code.
- [x] Audit report with prioritized findings, quick wins, deeper items, validation plan
- [x] PDF work budget (operators + decoded content) -> manual review instead of 15-45 s+ per hostile file
- [x] DOCX reader: reading order, tables in place, text boxes, content controls, merged cells once, early stop, XML cap (DOCX parsing 2× faster on samples)
- [x] "mother tongue" no longer redacted
- [x] Unicode format characters dropped (soft hyphens no longer break matching)
- [x] Future-dated roles no longer subtract experience
- [x] 120 s API timeout per attempt
- [x] Headline on the first line no longer taken as the name
- [x] Duplicate files in one run extracted once (single-flight cache)
- [x] Tier counts in one place
- [x] "Applied" section with measured before/after numbers and deferred items
- Deferred (see OPTIMIZATIONS.md): schema trimming, grouping skills by evidence (need a real-mode run)

## Phase 10 – Security review 2 (2026-10-11)
Adversarial review of everything since `main`; PoC first, then fix + test.
- [x] Names in any script / with particles redacted; invariance variants added
- [x] German labels and free-text age phrases redacted; German invariance test
- [x] Hidden DOCX text flagged
- [x] `--blind` hides file names (neutral IDs, mapping in run_report.json)
- [x] PDF budget: decoded forms capped (memory regression from Phase 9)
- [x] Particle folding bounded (quadratic regression from the name fix)
- [x] No CV text in error messages; n8n stores counts only
- [x] Symlinked CVs not followed
- [x] Left-out items documented (BUILD_LOG "Security review 2", README Limitations)
- [x] README, CASE_STUDY, BUILD_LOG, DECISIONS updated

## Phase 11 – Public-release prep (2026-10-11)
Presentation and consistency pass only: no behaviour, default model or DECISIONS entries changed.
- [x] MIT `LICENSE`, README License section, SPDX `license` in pyproject.toml
- [x] README / CASE_STUDY checked against the code; mock quickstart run as written; numbers labelled demo data / estimate
- [x] Relative links in all Markdown files resolve
- [x] Demo image `docs/demo-run.png` from a real mock run, with alt text
- [x] Full-history scan for secrets and personal data (gitleaks + custom scan): nothing found
- [x] `.gitignore` covers `.env`, caches and `out/`; `.env.example` has no values
- [x] PR opened (#2), CI green on Python 3.11-3.13 (`186ced9`)

## Final state (2026-10-11, after the optimization pass and security review 2)

**Done**
- Full pipeline: parse (PDF with a work budget; DOCX in reading order incl. tables, text boxes and content controls; TXT; input limits; hidden-text flags for PDF and DOCX) -> redact protected attributes (English and German labels, names in any script) -> extract (Claude structured outputs with a 120 s timeout, or offline mock; cached by file SHA-256 in real mode, one call per distinct CV) -> verify that each quote is in the CV and contains the claim -> match -> tiered ranking -> shortlist.md/.csv, per-candidate summaries, three-variant email drafts, run_report.json, all owner-only and escaped; `--blind` hides names and file names.
- 20 synthetic, reproducible sample CVs (10 PDF, 10 DOCX, three layouts) and `job.yaml`.
- 218 offline tests (97 at the first PR, 177 after the first security review), including protected-attribute invariance (now with non-ASCII, particle and German-labelled variants), missing-info handling, and one test per optimization and security finding. ruff clean.
- CI green on Python 3.11-3.13 for the security-review commits (`c9f0821`), the optimization pass (`0fb9245`) and security review 2 (`926e138`).
- Mock demo run unchanged in content (A 7 / B 9 / C 4), 0.20-0.27 s instead of 0.33-0.39 s.
- README, CASE_STUDY, DECISIONS, BUILD_LOG, OPTIMIZATIONS, optional n8n workflow.

**Not done**
- Real-mode demo run on the samples (needs `ANTHROPIC_API_KEY`). No measured real-mode time, tokens, cost or extraction accuracy yet; CASE_STUDY shows estimates labelled as such.
- n8n workflow not tested in a running n8n instance.
- Agreed out of scope: SHA-pinned GitHub Actions, a lockfile. Consciously left out: see BUILD_LOG "Security review 2" and OPTIMIZATIONS "Deferred".

**Next steps**
1. `cp .env.example .env`, add a key, run `screen run samples/ --job job.yaml --as-of 2026-10-01`; copy `out/run_report.json` numbers into CASE_STUDY.md and BUILD_LOG.md; compare tiers with the mock run.
2. Spot-check extraction accuracy on the samples (claims vs CV) and record it as demo data, including true claims dropped by the evidence check.
3. With real-mode numbers, decide on the deferred token savings (O10/O11 in OPTIMIZATIONS.md).
4. Try a few real-world CV templates (Word text-box sidebars, designed PDFs) against the PDF budget and the DOCX reader; tune `max_pdf_content_mb` if designed CVs land in manual review.
5. Pilot with a real hiring manager: time per opening, disagreement with tiers, wrong claims found.
