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

## 2026-10-09 – Reply emails are templates with all variants, never sent
- **Decision:** Each candidate gets a Markdown draft containing an "invite to interview" and a "decline" variant, with the tool's suggestion labelled. Nothing is sent. *Amended the same day:* a third variant, "ask for missing information", lists the candidate's unclear must-haves as questions, because "unknown" results needed a matching reply.
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

## 2026-10-09 – Keep the brief's default model; any model via `--model`
- **Decision:** Default extraction model `claude-haiku-4-5-20251001` as the brief specifies, overridable with `--model` or `CV_SCREEN_MODEL`. Prices for a few current models are in `extract.PRICES_PER_MTOK`; an unknown model reports cost as unknown instead of $0.
- **Alternatives:** Default to the newest Haiku (cheaper per token); a larger model for accuracy.
- **Why:** The brief fixes the default. Extraction into a strict schema with quotes is a small, well-specified task that a small model should handle; whether a newer or larger model is worth it is a question for a measured real-mode comparison, not a guess.

## 2026-10-09 – Test the real SDK path offline with a mock HTTP transport
- **Decision:** One test builds a real `anthropic.Anthropic` client whose HTTP transport is mocked, so the actual request body (`output_config.format = json_schema`) is serialised by the SDK without any network access. Other tests use a duck-typed fake client. `anthropic>=1.12` is required (the version this was built and tested with).
- **Alternatives:** Only a fake client; a recorded HTTP cassette.
- **Why:** A fake client would accept parameters the SDK rejects. The mock transport catches that while keeping the suite offline, as the brief requires.

## 2026-10-11 – Evidence must contain the claim, not just exist in the CV (security review)
- **Decision:** A claim is kept only if its quote (a) has at least 2 words or 8 characters, (b) is found in the redacted CV, and (c) contains the claimed value: skill name (same whole-term matching as the matcher); language name (English, own-language or German name) plus the CEFR token or native/mother tongue, and `level_as_written`; job title, start and end year, or a present/now/since word for "present"; education level word (shared `EDUCATION_TERMS` with the mock), field, and `in_progress` consistent with "in progress/expected"/a future year. Failing claims are dropped and listed. Two parts of a role are narrowed instead of dropping the whole role: relevance without one of the job's `relevant_experience.keywords` in the quote is set to not relevant, and a month the quote does not show falls back to the year. The CV text is HTML-escaped (`<`, `>`, `&`) in the prompt; quotes are unescaped before checking. Amends the 2026-10-09 entry, which only checked (b).
- **Alternatives:** Keep quote-exists only (audit PoC: a warehouse picker reached tier A with quotes "e", "a", "2023"); ask a second model to judge whether the quote supports the claim; drop the whole role when relevance or a month is not shown; escape only `</cv>`.
- **Why:** Matching reads the claimed values, so those values are what must be proven. Literal checks are deterministic, offline-testable and explainable; a judge model would be another thing to prompt-inject. Narrowing keeps the role's backed facts (title, years) visible instead of turning "not relevant" into "no experience found" (which reads as *unknown* and is softer than the truth). Escaping all three characters is lossless and closes every tag, not just one. Cost: stricter checks can drop true claims the model quoted badly; they are listed in the summary so the manager sees them.

## 2026-10-11 – Escape formula-like cells in `shortlist.csv` (security review)
- **Decision:** Every string cell that starts with `=`, `+`, `-`, `@`, tab or CR is written with a leading `'` (OWASP CSV-injection guidance). Applies to all columns, including name, file name, candidate ID, evidence, dropped claims and errors.
- **Alternatives:** Escape only the name; strip the characters; write `.xlsx` with typed text cells.
- **Why:** Every column can carry applicant-controlled text (file names, CV lines, the `Name:` value), and the manager is expected to open the CSV in a spreadsheet, where `=HYPERLINK`/`=WEBSERVICE` can send other applicants' data out. A prefix keeps the value readable and is what spreadsheet apps expect; stripping would change evidence quotes. Side effect: bullet quotes such as `- Zendesk` show as `'- Zendesk` in plain-text viewers.

## 2026-10-11 – Candidate ID = file stem + 8 hex digits of the file's SHA-256 (security review)
- **Decision:** IDs are `<stem>-<sha256[:8]>`, with the stem reduced to word characters, `.` and `-` (max 60 characters, no leading `-`/`.`). All IDs are computed before screening; if two files still share an ID (same stem and same bytes, e.g. `cv01.txt` and `cv01.TXT`), the run stops with an error listing both files before any API call or output. `write_outputs` repeats the check before writing.
- **Alternatives:** Keep `path.stem` (audit: `cv01.pdf` and `cv01.docx` shared one summary and one email draft, so the rank-1 row linked to another person's evidence); use the full file name; append a counter.
- **Why:** The hash makes the ID unique per content and stable across runs (the sample IDs never change because the samples are byte-reproducible), and it lines up with the extraction cache key. A counter would depend on folder order. Sanitising the stem keeps file names and Markdown links (`candidates/<id>.md`) safe for any upload name and under file-system name limits. Failing loudly beats silently screening one of two identical files.

## 2026-10-11 – Input limits send oversized CVs to manual review (security review)
- **Decision:** `parsing.Limits` (defaults: 5 MB per file, 10 PDF pages, 30,000 characters of text, 50 MB unpacked DOCX), configurable with `--max-file-mb`, `--max-pages`, `--max-chars`. The size is checked before reading, the page count before extracting text, the DOCX zip directory before unpacking, and the text length before redaction and extraction (PDF extraction stops early once over the limit). A CV over a limit raises `LimitError` (a `ParseError`) and is listed under "Needs manual review" with the reason; nothing is sent to the model. Files over the size limit are not hashed for their ID.
- **Alternatives:** Truncate long text and screen the rest; reject over-limit CVs; no limits (audit: anyone who applies controls input size, and the n8n flow re-screens the folder on every new file).
- **Why:** Truncation would screen a CV on partial evidence and hide that; rejection would be an auto-reject. Manual review keeps the human decision and costs nothing. 30,000 characters is roughly 15 dense pages, far above a normal 1-3 page CV (samples: max ~1,000 characters after redaction), and caps a single call at about 8k input tokens.

## 2026-10-11 – Linear-time text processing for applicant-controlled text (security review follow-up)
- **Decision:** Regexes that start with a repeated character class get a lookbehind so a match can only start at the beginning of a run (`_EMAIL_RE`, the `|` segment split in `redact.py`); `matching.term_hit` uses `str.find` plus the same `\w` boundary rule instead of compiling a regex per term (checked identical to the old regex on 200,000 random cases); `_norm` is cached so the CV text is normalised once per CV, not once per claim. A test screens four hostile 30,000-character inputs and requires each to finish in under 2 s.
- **Alternatives:** Rely on the 30,000-character limit alone; a third-party regex engine with linear-time guarantees (`re2`).
- **Why:** Found while reproducing the size-limit finding: the old code never finished a 6 MB text CV (the email regex alone took 0.28 s at 8,000 characters and grows with the square of the length), and even at the new limit a single CV took 3.5-25 s (word run, dotted run, em-space run, long skills line). The limit bounds the damage; the lookbehinds remove the cause without changing any match (a match found mid-run always also exists from the run's start). A new dependency for two regexes was not worth it.

## 2026-10-11 – Flag hidden PDF text instead of removing it (security review)
- **Decision:** While pypdf extracts a page, a small graphics-state tracker (`parsing._Visibility`) counts characters shown in invisible render mode (3/7), in white fill on a page with no coloured fill, image or shading drawn before them, at an effective size under 1 pt, or outside the page box. With 30 or more such characters the CV gets a file warning, shown in the shortlist row, the summary, `shortlist.csv` (`file_warnings`) and `run_report.json`. The text is still extracted and the CV is still screened.
- **Alternatives:** Strip hidden text before extraction; send flagged CVs to manual review; render the page and OCR it to compare with the text layer.
- **Why:** The same signals have innocent causes (the OCR layer of a scanned CV is invisible text; designed CVs put white text on dark bands), so removing text or blocking the CV would penalise people for their tools, which is the opposite of the fairness goal. A warning puts the judgement with the manager. Rendering and OCR would add heavy dependencies for a heuristic. The white-text rule ignores pages with an earlier backdrop to avoid flagging designed templates, at the cost of missing white text hidden on such pages. No sample CV and no white-on-dark-band test PDF is flagged.

## 2026-10-11 – Owner-only outputs, set explicitly (security review)
- **Decision:** `cv_screen/fileio.py` creates output folders with mode 0700 and files with 0600 and then sets the mode explicitly (`chmod`/`fchmod`), so the result does not depend on the umask and existing outputs from older runs are tightened. Files are opened with `O_NOFOLLOW`, so a symlink planted in the output folder makes the write fail instead of overwriting the link target. Used for every report file and, later, the extraction cache.
- **Alternatives:** Set `os.umask(0o077)` in the CLI; document "keep `out/` private"; leave modes to the user.
- **Why:** The audit measured 775/664 on a umask-002 machine, so group members could read every applicant's data on a shared host (the n8n setup writes to `/data/screening/...`). A process-wide umask would not fix files that already exist and would also affect library code; explicit modes are local and testable. If the folder belongs to another user, `chmod` fails and the run stops, which is the right outcome for personal data.

## 2026-10-11 – Extraction cache in the output folder (security review: cost)
- **Decision:** `cv_screen/cache.py` stores each schema-valid extraction as JSON in `OUT/.cache/extractions/` (configurable with `--cache-dir`), keyed by SHA-256 over the file's SHA-256, the redacted text sent and the extractor identity (model, max tokens, system prompt, schema and the job part of the user message). On by default in real mode, off in mock mode; `--no-cache` turns it off. Owner-only files written atomically via `fileio`, entries re-validated on read (invalid or symlinked entries are ignored), TTL 30 days (`--cache-ttl-days`) with expired entries deleted at the start of every run. Evidence checks and matching run again on cached extractions.
- **Alternatives:** No cache (audit: two runs on unchanged samples cost 20 + 20 API calls; the n8n flow re-screens the folder on each new file, so 40 applications cost ~820 calls instead of 40); key by file hash alone; cache final results instead of extractions; a cache in the user's home folder.
- **Why:** The brief asks to cache by the file's SHA-256; adding the text, model, prompt and job to the key prevents serving a stale result after any of them changes (a file-only key would reuse relevance decisions made for a different job). Caching the raw extraction keeps new verification rules effective. Keeping it under the output folder means the README's retention rule (delete `out/` when the opening closes) also deletes the cache; the TTL is a backstop. Failed calls are never cached, so a transient error does not stick.

## 2026-10-11 – Dependency floors and upper bounds, no lockfile yet (security review)
- **Decision:** Every runtime and dev dependency in `pyproject.toml` has a floor (the version range this was built and tested with) and an upper bound below the next major version (`ruff` below 1.0). `pypdf>=6.1` (was `>=4.0`). `packaging` is now an explicit dev dependency for a test that enforces these rules.
- **Alternatives:** Exact pins; a lockfile (`uv.lock`/hash-pinned requirements); SHA-pinned GitHub Actions.
- **Why:** The old `pypdf>=4.0` allowed versions with known parser and decompression DoS issues, and open-ended ranges let CI install an untested (or compromised) major release. Upper bounds are the cheap step; a lockfile and SHA-pinned actions are the thorough one and were agreed as out of scope for now (open follow-up).

## 2026-10-11 – Escape CV and model text in Markdown; show names only if they look like names (security review)
- **Decision:** Every string in `shortlist.md`, `candidates/*.md` and `emails/*.md` that comes from a CV or from the model (file names, candidate IDs, evidence, notes, titles, skills, languages, fields, dropped claims, warnings, errors) goes through `report.md()`, which backslash-escapes `\ < > [ ] ( ) ! * _ | `` ` and turns line breaks into spaces. Code spans around file names were removed (backslash escapes do not work inside them). The CV's name is shown, in the outputs and in the email greeting, only if it matches letters of any script separated by spaces, `'`, `’`, `.` or `-` (max 80 characters); otherwise "(not found)" / "Dear applicant,". Redaction still uses the raw name to remove it from the text.
- **Alternatives:** Escape only the name; strip the characters; render HTML with a sanitiser; keep the raw name and only escape it.
- **Why:** Audit: a `Name: <img src=...>` line or a `[click](...)` in a role title reached the rendered summary and email draft, giving an applicant a tracking pixel or a phishing link inside a document the manager trusts. Escaping keeps the evidence verbatim when rendered; stripping would change quotes. A name with markup or digits is not a name, and the manager still has the file. Email text from `job.yaml` is not escaped because the manager copies it into a mail client. Cost: backslashes are visible in a plain-text editor.

## 2026-10-11 – `.env` loader reads only the tool's own variables (security review)
- **Decision:** `_load_dotenv` loads `ANTHROPIC_API_KEY`, `CV_SCREEN_MODEL` and `MOCK_LLM` from `./.env` and ignores every other line. Shell variables still win.
- **Alternatives:** Load everything (old behaviour); use `python-dotenv`; read `.env` only from the project folder.
- **Why:** `screen` may be run inside a folder of downloaded applications. A planted `.env` with `ANTHROPIC_BASE_URL=https://attacker` would have redirected the API key header and all CV text; `HTTPS_PROXY`, `SSL_CERT_FILE` or `PYTHONPATH` have similar effects. An allowlist removes the whole class, needs no dependency, and keeps the documented workflow (`cp .env.example .env`). Side effect: `ANTHROPIC_AUTH_TOKEN` now only works from the shell, not from `.env`.
