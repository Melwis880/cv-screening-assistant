# Decisions

One entry per architecture or security decision, written when the decision is made.

## 2026-10-09 – Python CLI package, `screen` entry point
- **Decision:** Python 3.11+ package `cv_screen` with a click CLI installed as `screen` (also runnable as `python -m cv_screen`).
- **Alternatives:** Node/TypeScript CLI; a notebook; a small web app.
- **Why:** The PDF/DOCX parsing libraries (pypdf, python-docx) and the Anthropic SDK are mature in Python; a CLI is the smallest thing a hiring manager (or n8n) can run. `screen` collides with GNU screen outside a virtualenv, so `python -m cv_screen` is documented as the fallback.

## 2026-10-09 – Redact protected attributes before the LLM sees anything
- **Decision:** Protected attributes (name, photo, age/date of birth, gender, nationality, marital status, address, email, phone, gendered pronouns and titles) are removed from the CV text locally, before extraction. Only redacted text is sent to the API. The name is kept locally only for the manager-facing outputs (shortlist, email draft).
- **Alternatives:** Tell the model to "ignore" protected attributes; redact after extraction; drop names entirely from outputs.
- **Why:** An instruction to ignore information is not verifiable; removing it is. Redacting first also minimises the personal data that leaves the machine. The invariance test can then assert that the exact text sent to the model is identical when protected attributes change, which holds for both mock and real mode. The manager still needs the name to contact people, so it reappears only after matching.

## 2026-10-09 – Model extracts facts, code does arithmetic and matching
- **Decision:** The LLM returns dated experience entries, skills, languages (CEFR level) and education, each with a verbatim evidence quote. Years of relevant experience, criterion status (met / partly / not met / unknown) and ranking are computed deterministically in Python from `job.yaml` rules.
- **Alternatives:** Ask the model for a per-criterion verdict or a 0–100 fit score.
- **Why:** "No hidden scoring" is a requirement; rule-based matching is inspectable, unit-testable offline, and identical between runs. LLMs are unreliable at date arithmetic. The model does what it is good at (reading messy CVs); the code does what must be auditable.

## 2026-10-09 – Evidence quotes must be found in the CV, otherwise the claim is dropped
- **Decision:** Every extracted claim carries an evidence quote. After extraction, each quote is checked (case- and whitespace-insensitive) against the redacted CV text. Claims whose quote is not found are dropped and listed as warnings in the candidate summary.
- **Alternatives:** Trust the model; flag but keep the claim.
- **Why:** A fabricated claim could move a candidate up or down. Dropping turns a hallucination into an "unknown", which the manager sees and can ask about, instead of a silent wrong "met".

## 2026-10-09 – Mock mode is a rule-based extractor, not recorded fixtures
- **Decision:** `MOCK_LLM=1` / `--mock` uses a deterministic, offline, rule-based extractor that reads the section layout of the sample CVs and fills the same schema with real quotes.
- **Alternatives:** Pre-recorded JSON responses per sample file.
- **Why:** Recorded fixtures would be keyed to exact files, so the invariance test (which edits a CV) could not run through the full pipeline. A rule-based extractor works on any CV in the sample format and keeps tests offline. The real extractor is tested separately against a fake API client. Limitation: mock-mode output says nothing about LLM accuracy.

## 2026-10-09 – Structured outputs with a JSON schema generated from Pydantic
- **Decision:** Real mode calls `messages.create` with `output_config.format = json_schema` built from the Pydantic model, then validates the response with the same model.
- **Alternatives:** Free-text JSON with "please return JSON"; tool use with a forced tool.
- **Why:** Structured outputs constrain the response to the schema at decode time; Pydantic validation gives a second check and typed objects. One source of truth for the schema.

## 2026-10-09 – Reply emails are templates with both variants, never sent
- **Decision:** Each candidate gets a Markdown draft containing both an "invite to interview" and a "decline" variant, with the tool's suggestion labelled. Nothing is sent.
- **Alternatives:** One LLM-written email per candidate in the variant the ranking suggests.
- **Why:** Writing only the decline would be an auto-rejection in practice. Templates cost nothing, cannot hallucinate, and keep the decision visibly with the manager.

## 2026-10-09 – Transparent tiers instead of a score
- **Decision:** Candidates are grouped into tier A (all must-haves met), B (no must-have clearly missing, some partly/unknown) and C (at least one must-have looks not met). Within a tier they are sorted by counts (must-haves met, must-haves partly, nice-to-haves met, nice-to-haves partly, fewer unknowns, candidate ID). The rule is printed at the top of every shortlist.
- **Alternatives:** Weighted points per criterion; a model-assigned score.
- **Why:** Weights look precise but are arbitrary and hard to explain to a rejected candidate. Counts can be checked by hand in the summary table. Tier C is a review flag, not a rejection: those candidates still appear with all their evidence and a draft email.

## 2026-10-09 – "Unknown" is a first-class result
- **Decision:** Missing sections (no languages, no dates, no skills), non-CEFR levels ("fluent") and roles without dates produce `unknown`, never `not met`. Unknowns become questions in the summary and in the "ask for missing information" email variant.
- **Alternatives:** Treat missing as not met (typical keyword ATS behaviour); let the model guess ("fluent" = C1).
- **Why:** Penalising an incomplete CV hurts people who format CVs differently, often career changers or people from other countries, without telling the manager anything. Asking is cheap.

## 2026-10-09 – Names shown to the manager after matching, `--blind` to hide them
- **Decision:** The shortlist and summaries show the name in a column labelled "not used for matching". `--blind` hides it everywhere except the email drafts.
- **Alternatives:** Always blind; always named.
- **Why:** The manager has to contact people, and real CV filenames often contain names anyway. Blind review is still useful for the first pass, so it is one flag away.

## 2026-10-09 – One bad CV never stops the run
- **Decision:** Parse errors, empty text layers (scanned PDFs) and failed or invalid API responses put that CV under "Needs manual review" in the shortlist; the run continues.
- **Alternatives:** Abort the run; skip silently.
- **Why:** Silently skipping a CV is a hidden rejection. Aborting wastes the other 39 results.

## 2026-10-09 – Process files in parallel threads
- **Decision:** `--workers 4` by default, using a thread pool. SDK retries (`max_retries=3`) cover 429/5xx.
- **Alternatives:** Sequential calls; Message Batches API (50% cheaper, asynchronous).
- **Why:** 40 sequential calls take minutes; a manager runs this interactively. Batches would halve a cost that is already cents per opening, at the price of waiting up to hours.
