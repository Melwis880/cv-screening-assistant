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
- **Alternatives:** No cache (audit: two runs on unchanged samples cost 20 + 20 API calls; the n8n flow re-screens the folder on each new file, so with one trigger per application, 40 applications cost up to 1 + 2 + ... + 40 = 820 calls instead of 40); key by file hash alone; cache final results instead of extractions; a cache in the user's home folder.
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

## 2026-10-11 – Sanitise applicant-controlled text printed to the terminal (security review)
- **Decision:** `cli.term_safe` replaces characters of Unicode categories Cc, Cf, Zl and Zp with `?`. It is applied to everything the CLI prints that can come from a CV file: the new "Needs manual review" and "Check before relying on the extracted claims" lists (file names, errors, warning labels), the duplicate-ID error, and pypdf's log warnings (routed through a sanitising handler on the `pypdf` logger).
- **Alternatives:** Escape with `repr()`; strip only ESC; never print file names.
- **Why:** File names are chosen by applicants (email attachments) and can contain ESC/OSC sequences (fake hyperlinks, screen clearing) or a right-to-left override that disguises `cv.exe` style names. The old CLI printed no such strings; the manual-review list added in this review does, and the manager needs it, so the names are printed but made inert. `?` keeps names readable, unlike `repr()`; stripping only ESC would miss bidi and C1 controls.

## 2026-10-11 – A work budget for PDF parsing, not a timeout (optimization pass)
- **Decision:** `Limits.max_pdf_ops` (300,000 drawing operators) and `max_pdf_content_mb` (5 MB of decoded content, a form counted each time it is drawn and all decoded forms counted once) are enforced in the visitor callback pypdf calls for every operator; over budget -> `LimitError` -> manual review. Not exposed as CLI options.
- **Alternatives:** A wall-clock timeout per file; parsing in a subprocess that can be killed; lowering pypdf's global decompression limit.
- **Why:** Small PDFs took 15-21 s (and ~45 min extrapolated) before any existing limit fired. Threads cannot be killed, and a timeout would make the outcome depend on machine speed; counting work is deterministic and testable. A subprocess is heavier and platform-specific. A global pypdf setting would affect the whole process. Samples use ~200 operators and 6 KB, so the defaults leave a wide margin; a very graphic-heavy CV lands in manual review, never in a rejection.

## 2026-10-11 – Read DOCX with a small XML walker (optimization pass)
- **Decision:** `parsing._DocxReader` walks the body XML in document order: paragraphs, table rows (one `<w:tc>` per cell, so merged cells appear once), text boxes once (the DrawingML copy, not the VML fallback) after their anchor paragraph, content controls and tracked insertions; deleted text is skipped. Style IDs are mapped once per document. Reading stops as soon as the text is over `max_chars`; XML parts over 10 MB go to manual review. python-docx still opens the package.
- **Alternatives:** Keep `doc.paragraphs` + `doc.tables` and only cache the style lookup; `doc.iter_inner_content()`.
- **Why:** The old path spent 71% of DOCX time in python-docx's per-paragraph style scan (0.9 ms per paragraph, so empty paragraphs were a DoS), put tables after all paragraphs and silently dropped text boxes and content controls, which template CVs use for sidebars. `iter_inner_content()` fixes the order but still skips text boxes, content controls and insertions. The sample DOCX files parse to byte-identical text.

## 2026-10-11 – Drop Unicode format characters from CV text (optimization pass)
- **Decision:** `normalize_text` removes all category-Cf characters (soft hyphen, zero-width space/joiner, bidi controls, BOM).
- **Alternatives:** Remove only the soft hyphen; keep them and normalise only for matching.
- **Why:** They split words ("Zen<SHY>desk" did not match "zendesk") and can reorder how quoted evidence is displayed. Removing them once at parse time keeps the text the model sees, the quotes it returns and the matcher consistent.

## 2026-10-11 – The first-line name guess ignores headlines (optimization pass)
- **Decision:** A first line is not taken as the name if it contains a CV heading or job word (customer, support, specialist, profile, experience, ...).
- **Alternatives:** Only remove the full name string, never its single words; use the job's relevance keywords as the stop list.
- **Why:** "Customer Support Specialist" as the name erased every "customer" and "support" in the CV and moved a tier-A candidate to tier C. Removing single name words is still needed (first names in free text), so the guess itself has to be stricter. A fixed list keeps redaction independent of the job, so the text sent for one CV is the same for every job. Cost: a person named like a job word is not auto-detected without a `Name:` label.

## 2026-10-11 – 120-second timeout per API attempt (optimization pass)
- **Decision:** `anthropic.Anthropic(max_retries=3, timeout=120)`. Amends the 2026-10-09 "parallel threads" entry, which set the retries.
- **Alternatives:** SDK default (10 minutes); a shorter timeout; streaming.
- **Why:** Timeouts are retried, so the default allowed 40 minutes per stalled CV. A Haiku extraction with `max_tokens=4096` takes seconds; 120 s leaves room for a slow response, and after four attempts the CV goes to manual review.

## 2026-10-11 – Single-flight extraction per cache key (optimization pass)
- **Decision:** `ExtractionCache.lock(key)` is held from lookup to write, so identical files in one run are extracted once.
- **Alternatives:** De-duplicate files by hash before screening; accept the duplicate call.
- **Why:** Both duplicates still need their own outputs (different file names, possibly different people sending the same template), so de-duplicating the file list would hide one. A per-key lock only makes the second wait for the first; it is a no-op without the cache.

## 2026-10-11 – Redaction covers names in any script, particles and German labels (security review 2)
- **Decision:** The first-line name check accepts capitalised or caseless letters of any script and lower-case particles (van, der, de, la, bin, ...); particles are not replaced throughout the text, but particles next to a removed name are folded into the token (at most three in a row, linear time). German field labels (Geburtsdatum, Staatsangehörigkeit, Familienstand, Geschlecht, Anschrift, ...) and more age phrases are removed. The invariance tests include such names and a German CV.
- **Alternatives:** A named-entity model for names; a language-detection step with per-language rules; leave it documented as a limitation.
- **Why:** The old rule removed "Anna Schmidt" but sent "Özlem Yılmaz" and "Anna van der Berg" to the model, so redaction treated people differently by origin, which is exactly what it exists to prevent. The demo employer is German, so German labels are the expected case, not an edge case. An NER model is a heavy dependency that is itself hard to test for bias; rules plus invariance tests stay explainable.

## 2026-10-11 – Flag hidden DOCX text like hidden PDF text (security review 2)
- **Decision:** Runs marked hidden, under 1 pt, or white with no shading behind them (run, paragraph or cell) are counted; 30+ characters give a "Hidden text in the DOCX" file warning. The text is still read. Extends the PDF entry of the first review.
- **Alternatives:** Drop hidden runs; ignore DOCX.
- **Why:** Same reasoning as for PDFs: the signals have innocent causes (template leftovers, white text on dark bands), so the manager decides. Without it, DOCX was the easy way around the PDF warning.

## 2026-10-11 – `--blind` hides file names and uses neutral IDs (security review 2)
- **Decision:** With `--blind`, candidate IDs are `cv-` plus 8 hex digits of SHA-256 over the file hash and file name, and the shortlist, CSV, summaries and terminal show "(hidden, see run_report.json)" instead of the file name (also inside error messages). `run_report.json` lists each ID's source file in every mode. Amends the 2026-10-09 blind entry ("hides it everywhere except the email drafts" now includes file names) and the security-review candidate-ID entry (stem + hash stays the default).
- **Alternatives:** Keep stem-based IDs and only hide the source column; a separate mapping file.
- **Why:** Real file names often are the applicant's name, so blind mode showed the name on every row. The hash of content and name keeps IDs unique per file and stable across runs; the mapping in `run_report.json` lets the manager find the CV after deciding. Email drafts keep the file name: they are written after the decision.

## 2026-10-11 – Error messages without CV text; n8n stores counts only (security review 2)
- **Decision:** Pydantic validation errors are reported as location + message, never with the input value. The n8n *Run screening* node prints only `job`, `cvs`, `manual_review` and `tiers` from `run_report.json`.
- **Alternatives:** Truncate the messages; let n8n read the report from disk without printing it.
- **Why:** Pydantic quotes the offending input, here model output copied from the CV, and errors are printed and stored in `run_report.json`. n8n keeps every execution's stdout in its database by default, so the whole report (candidate IDs, i.e. file names, and errors) ended up there with n8n's retention, not ours. Truncation would still leak a prefix.

## 2026-10-11 – Symbolic links in the CV folder are not followed (security review 2)
- **Decision:** `parse_cv` refuses a symlinked file (manual review, "symbolic link; not read") and its SHA-256 is not computed.
- **Alternatives:** Follow links inside the folder only; skip links silently.
- **Why:** A link in a shared applications folder could point at any file the manager can read, which would be sent to the API and quoted in outputs. Skipping silently would hide a file the manager might expect to be screened; manual review keeps it visible.
