# Build log

Raw material for posts about the build. Factual only; numbers are labeled as demo data.

## Key decisions (and what was rejected)
- **Redact first, then extract.** Rejected "tell the model to ignore the name/age/photo". You can't test an instruction to ignore something; you can test that the text sent to the model is byte-identical when those fields change.
- **LLM reads, code decides.** Rejected a model-generated fit score. The model extracts dated jobs, skills, languages and education with a quote for each; Python does the date arithmetic and the met/partly/not met/unknown rules from `job.yaml`.
- **Quotes or it didn't happen.** Every claim must quote the CV. Quotes not found in the CV text are dropped and shown as warnings.
- **Both email variants, never sent.** Rejected generating only the variant the ranking suggests, because a pre-written decline is an auto-rejection with extra steps.
- **Mock mode as a rule-based extractor**, not recorded fixtures, so the invariance test can edit a CV and still run the whole pipeline offline.

## Problems hit and how they were solved
- **DOCX samples were not reproducible.** Re-running the generator changed 9 of 10 DOCX hashes:
  python-docx writes the current time into the zip entries. Fix: rewrite the zip with a fixed
  `ZipInfo(date_time=(2026, 10, 1, 9, 0, 0))` for each entry. PDFs use reportlab's `invariant=1`.
- **PDF line wrapping leaked a protected value.** The PDF text layer came back as
  ```
  Date of birth: 14 March 1999 | Nationality: Fictionalian | Gender: Female | Marital status:
  Single
  ```
  A line-based "drop protected labels" rule removed the first line and left `Single` on its own.
  Fix: when a protected label has an empty value at the end of a line, also drop a short
  following line.
- **The phone-number regex ate employment dates.** `08/2019 - 02/2022` has 12 digits and looked
  like a phone number, so job dates vanished from the redacted text (which would have turned
  every experience criterion into "unknown"). Fix: skip matches that look like dates or date
  ranges, and require 9+ digits or a leading `+`.
- **Stripping schema titles deleted a field.** To make the Pydantic JSON schema strict I removed
  every `"title"` key recursively. The `Experience` model has a *property* called `title`, so
  it vanished from `properties` but stayed in `required`. Fix: only strip `title` when its value
  is a string annotation, and never walk into `properties` as if it were an annotation dict.
  Caught by printing the schema before writing any API code.
- **The invariance test found a gender leak in pronoun rewriting.** `her` is object or possessive
  ("describe her as" vs "her team"), `his` is always possessive. With the text wrapped as
  `... and her\nteam relies on ...`, my end-of-line rule turned `her` into "them" while `his`
  became "their":
  ```
  - rs and their        (variant with "his")
  + rs and them         (variant with "her")
  ```
  So the redacted text still differed by gender. Fix: decide object vs possessive by looking
  past the line break. Without a test that diffs the redacted text, this would have shipped.

## Measured numbers (demo data)
All on the 20 synthetic CVs, `--as-of 2026-10-01`, in a 4-core cloud container.
- **Mock mode, wall-clock for 20 CVs:** 0.319 s, 0.336 s, 0.354 s, 0.402 s, 0.404 s over 5 runs
  (about 0.02 s per CV). Cost $0 (no API calls).
- **Mock mode shortlist:** tier A 7, tier B 9, tier C 4, manual review 0, dropped claims 0.
- **Test suite:** 97 tests, about 3 s, fully offline (before the security review; 177 tests,
  about 8 s on a 12-core laptop after it; 218 tests, about 10.5 s in a 4-core container after
  the optimization pass and security review 2).
- **After the optimization pass:** mock run 0.20-0.27 s wall for 20 CVs (5 runs; 0.33-0.39 s
  before in the same container). See "Optimization pass" below.
- **CI:** first push green on Python 3.11, 3.12 and 3.13, including a check that the sample
  generator reproduces the committed files byte-for-byte.
- **Real mode: not measured.** The build environment had no Anthropic API key. Prompt size
  measured locally: system prompt 2,069 + JSON schema 2,676 characters (about 4,750; an earlier
  version of this log said 4,300), user message for a demo CV about 840 characters on average
  (max 1,042). Token count and cost per CV are an
  estimate until a real run exists (see CASE_STUDY.md).
- **Accuracy:** not measured. The mock extractor is rule-based and written for the sample
  layout, so its results on the samples say nothing about LLM extraction accuracy.

## Security review (2026-10-11)

A `/security-audit` of the finished branch, then one small commit per finding. Every fix has a
test; where the problem could be reproduced, the test (or a script against the old commit)
showed it failing on the old code first. All numbers below are from the demo data and
hand-built hostile files on a 12-core laptop.

**What was found and fixed**

| Finding (audit severity) | Reproduced on the old code | Fix |
|---|---|---|
| Evidence only had to *exist* in the CV (High) | Fake model returning "Zendesk" with evidence `"e"`, "German native" with `"a"`, a 2010-present role with `"2023"`: a warehouse picker reached **tier A, 4/4 must-haves**. 13 hand-written unbacked claims: all 13 kept. | Quote needs 2 words or 8 characters and must contain the claimed value (skill, language + level, title + years, education level/field/in-progress). Relevance needs a job keyword; unshown months fall back to the year. CV text HTML-escaped in the prompt. Now: all PoC claims dropped, tier B. |
| CSV formula injection (Medium) | `Name: =HYPERLINK(...)`, a file called `=2+5+cmd\|' -C calc'!A0.txt` and a `=WEBSERVICE(...)` skills line reached `shortlist.csv` as live formulas | Leading `'` on every cell starting with `= + - @` tab CR |
| Same stem, same outputs (Medium) | `cv01.pdf` + `cv01.docx` -> IDs `['cv01', 'cv01']`, one summary for two people | ID = stem + 8 hex of SHA-256; collision check before screening and before writing |
| No input limits (Medium) | 11-page PDF and a 36,000-character CV both sent to the model; a 6 MB text file **never finished** (killed after 3 min) | 5 MB / 10 pages / 30,000 characters / 50 MB unpacked DOCX -> "Needs manual review", configurable |
| *Found while reproducing the above:* quadratic regexes | Email regex 0.28 s at 8,000 characters, growing with the square (6 MB extrapolates to ~44 h). At the new 30,000-character limit: word run 4.6 s, dotted run 3.5 s, em-space run 16.5 s, long skills line 24.7 s | Lookbehinds so matches start only at the beginning of a run, `term_hit` via `str.find` (identical to the old regex on 200,000 random cases), CV text normalised once. Now all four < 0.4 s |
| Re-runs re-bill every CV (Medium, cost) | Two real-mode runs on unchanged samples: **20 + 20** API calls | Extraction cache by file SHA-256 + text + model/prompt/job, owner-only, 30-day TTL: **20 + 0** |
| Hidden PDF text (audit: optional) | Not detected at all | Flag (not removal) for white/invisible/tiny/off-page text; 0 of 20 samples flagged, white-on-dark-band not flagged |
| Markdown injection (Low) | `<img src=...>` name and `[click](//evil...)` title rendered as-is in summary, shortlist and email | All CV/model text escaped; names shown only if they look like names |
| `.env` loads anything (Low) | `ANTHROPIC_BASE_URL=https://attacker...` from `./.env` was loaded | Allowlist: `ANTHROPIC_API_KEY`, `CV_SCREEN_MODEL`, `MOCK_LLM` |
| Output permissions (Low) | 775/664 on a umask-002 machine; a planted symlink `out/shortlist.md` -> other file was followed and overwrote it | 0700/0600 set explicitly, `O_NOFOLLOW` |
| Terminal output | Old CLI printed no applicant strings; the new duplicate-ID error printed raw ESC, BEL, RLO and LS characters | `term_safe` on file names, errors and pypdf warnings |
| `pypdf>=4.0`, no upper bounds | - | Floors + upper bounds on every dependency, `pypdf>=6.1`, enforced by a test |

**What was left out, and why**
- SHA-pinning GitHub Actions and a lockfile: agreed as out of scope for this round.
- Hidden text is flagged, not removed: OCR layers of scanned CVs and white text on dark
  template bands trigger the same signals, and removing text would penalise people for their tools.
- Redaction stays regex-based (now documented as best-effort); a named-entity model would be a
  new dependency and a new thing to test for fairness.
- The stricter evidence check can drop true claims that the real model quotes badly. Not
  measured: there is still no real-mode run (no API key in the build environment). Dropped
  claims are listed in each summary, so the manager can see them.

**Cost of the fixes:** mock-mode run on the 20 samples, same laptop, 5 runs each: 0.46-0.58 s
before the review, 0.52-0.65 s after (hashing, hidden-text tracking, stricter checks). Sample
tiers (A 7, B 9, C 4), names and dropped claims (0) are unchanged.

**Problems hit during the fixes**
- Reproducing the size limit hung: the old code was still redacting a 6 MB text file after
  three minutes. Profiling showed the email regex rescanning a run of word characters from
  every position. A limit hides that; a lookbehind removes it.
- The first version of the Markdown escaping also escaped the tool's own placeholder, so the
  summary said `\(not found\)`. Escape the untrusted value, not the whole line.
- Hostile test file names with `//` cannot exist on Linux (`/` is the path separator); the
  tests use `evil.example` without a scheme.
- Unicode escapes in the commands I typed were decoded before reaching the files, which put a
  literal em-space and a right-to-left override into two test files. A scan for Cc/Cf/Zl/Zp/Zs
  characters found them; they are now escape sequences.

## Optimization pass (2026-10-11)

Full report with file:line evidence: [`OPTIMIZATIONS.md`](OPTIMIZATIONS.md). Measured with the new
`scripts/benchmark.py` in a 4-core container; demo data.

**Decisions (and what was rejected)**
- **A work budget inside the PDF parser, not a timeout.** Python threads cannot be killed, and a
  wall-clock limit would send a CV to manual review on a slow machine but not on a fast one. The
  budget counts drawing operators (300,000) and decoded content bytes (5 MB) in the callback pypdf
  already calls for every operator, so it is deterministic. Rejected: parsing in a subprocess with
  a timeout (heavier, platform-specific), lowering pypdf's global decompression limit (affects the
  whole process).
- **No prompt caching, no batching of CVs.** The fixed prompt is ~1,200 tokens (estimate); Haiku 4.5
  only caches prefixes of 4,096+ tokens, so a cache marker would silently do nothing. Several CVs
  per call would put applicants in one context.
- **Kept `max_retries=3`, added a 120 s timeout per attempt.** The SDK default (10 min, retried)
  allowed 40 minutes per stalled CV.
- **Deferred:** trimming the schema descriptions and grouping skills by evidence line (both need a
  real-mode accuracy run first).

**Problems hit**
- Profiling the DOCX path: 71% of the time was `Paragraph.style`, which scans every style for each
  unstyled paragraph. A 37 KB file of 20,000 empty paragraphs took 19.8 s.
- pypdf catches exceptions raised inside a form XObject and logs them:
  ```
  Impossible to decode XFormObject /X0: ... has more than 300000 drawing operators ...
  ```
  With the form as the last thing on the page, extraction ended normally. The budget is now
  checked again after every page (a test covers exactly this case).
- The budget itself introduced a memory problem, found in the security review: it decodes every
  form to learn its size, and pypdf keeps decoded streams, so 20 unused 4 MB forms added 80 MB of
  RSS (44 -> 125 MB) from an 81 KB file. Decoded forms now count against the budget.
- The fixtures hid four correctness bugs, each reproduced before fixing: "German (mother tongue)"
  became "German ([REDACTED] tongue)" (German must-have -> unknown); a CV starting with "Customer
  Support Specialist" had that line taken as the name, every "customer"/"support" became
  `[CANDIDATE]`, and the candidate fell from tier A to C; DOCX tables were moved to the end and text
  boxes were dropped; a role dated after `--as-of` subtracted 8 months.

**Measured (demo data)**

| | Before | After |
|---|---|---|
| 20 samples, all stages (best of 5 / 10) | 265.6 ms | 168.1 ms |
| DOCX parsing, 10 samples | 189.9 ms | 87.7 ms |
| PDF parsing, 10 samples | 58.9 ms | 65.2 ms (budget overhead ~0.6 ms per file) |
| Mock run, `wall_seconds`, 5 runs | 0.325-0.385 s | 0.203-0.272 s |
| PDF 22 KB, 8.8 MB of operators | 15.6 s | 0.02 s (manual review) |
| PDF 1.9 KB, one form drawn 40× | 21.5 s (~45 min at pypdf's 5,000-use cap, extrapolated) | 2.15 s (manual review) |
| DOCX 37 KB, 20,000 empty paragraphs | 19.8 s | 0.13 s |
| Worst case found inside the budget | - | 6.9 s (4.8 MB of `q Q`) |

The redacted text of all 20 samples and the mock shortlist (tiers A 7 / B 9 / C 4) are unchanged.

## Security review 2 (2026-10-11)

An adversarial review of everything since `main`, after the optimization pass: injection, path
handling, data exposure, resource exhaustion, and above all whether the evidence check, the
protected-attribute invariance and the fairness guarantees can be bypassed. Every finding was
reproduced with a local PoC (no network, no keys) and has a test that fails on the old code.

**Fixed**

| Finding (severity) | PoC on the old code | Fix |
|---|---|---|
| Names not recognised outside ASCII or with particles (High, fairness) | "Özlem Yılmaz", "Łukasz Nowak", "Émile Dubois", Arabic script and "Anna van der Berg" on the first line went to the model unredacted; "Anna Schmidt" was removed. The invariance test passed because all its names were ASCII. | Name check accepts any script and particles; particles next to the name are folded into the token. Two such variants in the invariance tests. |
| German labels not redacted (High, fairness) | `Geburtsdatum`, `Staatsangehörigkeit`, `Familienstand`, `Geschlecht`, `Anschrift`, `Telefon` and their values reached the model unchanged; so did "a 45-year-old", "born in 1980", "34 Jahre alt". | German labels and more age phrases; German invariance test with two very different people. |
| DOCX hidden text not flagged (Medium, evidence bypass) | A hidden run (`w:vanish`), white or 0.5 pt text with "Customer Support Agent 2010 - present, Zendesk, German native" was read, passed the evidence check and ranked, with no warning (PDFs already got one). | "Hidden text in the DOCX" file warning; shaded and highlighted white text counts as visible. |
| `--blind` showed file names (Medium, fairness) | `Erika_Mustermann_Lebenslauf.pdf` appeared as the candidate ID, source file and in errors in the shortlist, CSV, summaries and terminal. | Blind IDs `cv-<8 hex>`, file names hidden in those outputs; `run_report.json` maps IDs to files. |
| PDF budget held decoded forms in memory (Medium, introduced by the optimization pass) | 20 unused 4 MB forms in an 81 KB file: RSS 44 -> 125 MB (a 5 MB file could reach GBs). | Decoded forms count against the 5 MB budget, once per file; a form under two names is charged under both. |
| CV text in error messages and n8n logs (Medium, data exposure) | An invalid model response produced `input_value='Customer Support Agent at Example GmbH since 2019...'` in the terminal and `run_report.json`; the n8n flow printed the whole report into n8n's execution history, with candidate IDs (file names). | Schema errors described by location only; n8n prints only the counts its email uses. |
| Symlinked CV followed (Low) | `cv.txt -> ~/.ssh/id_rsa` in the folder: read, sent to the model, quoted in outputs. | Links go to manual review unread. |
| Quadratic particle folding (Low, introduced by the name fix) | Once a name was found, 7,000 × "van " took 5.4 s. | At most 3 particles in a row: 0.02 s. |

**Checked and held:** the prompt escaping (`</cv>` in a CV stays data); the evidence check against
the redacted text (a claim can only use text that survived redaction); CSV and Markdown escaping
of every new field (blind placeholders, DOCX warnings); terminal sanitising of the new blind labels;
cache poisoning (entries are re-validated and claims re-checked against the CV); path handling of
candidate IDs; regex run time of the new age and name patterns on 30,000-character hostile inputs
(all at most 0.02 s).

**Left out on purpose**
- **Quotes may span a line break.** Whitespace is normalised so PDF line wrapping does not break
  true quotes; a model could therefore stitch a title from one line to dates on the next. Requiring
  single-line quotes would drop many true claims. The summary shows every quote.
- **Bare URLs in dropped-claim text.** Only text the evidence check *rejected* can carry
  model-written URLs (URLs and emails are removed from the CV before extraction); some Markdown
  viewers would autolink them. Low impact, labelled "Dropped unverified claim"; not worth escaping
  every `.` and `:`.
- **Text-box names.** DOCX text boxes are now read (O3). A name in a sidebar text box that is not at
  the top of the document is not recognised as the name; labelled fields in it are still removed.
- **Cost exhaustion.** Each CV costs one API call (cached afterwards); a flood of applications to
  the n8n inbox costs money. Documented: set a spend limit on the API key.
- **Concurrent runs** writing the same output folder (overlapping n8n executions) can interleave
  report files; the cache writes are atomic. The n8n flow debounces for two minutes.
- Known and out of scope: SHA-pinning GitHub Actions, a lockfile.

**Problems hit**
- Both regressions above were introduced by this session's own fixes and found by re-attacking
  them: the memory one by asking "what does the budget itself decode?", the quadratic one by
  running the same hostile-input checks as the first review against the new regex.
- The first German invariance test failed for a bad reason: one variant said "a 65-year-old", and
  the redaction (correctly) kept the article "a". The test data, not the code, was wrong.

## Public-release prep (2026-10-11)
Presentation and consistency pass before making the repo public; no behaviour change.
- **License:** MIT. `license = { text = "MIT" }` built, but setuptools 84 warned
  ``WARNING `project.license` as a TOML table is deprecated ... By 2027-Feb-18, you need to
  update your project``; switched to the SPDX string `license = "MIT"` with
  `license-files = ["LICENSE"]` (needs setuptools>=77). The wheel now carries
  `License-Expression: MIT` and the LICENSE file.
- **Docs checked against the code, not trusted:** the mock quickstart ran exactly as written
  (A 7 / B 9 / C 4). Gaps found: `cv_screen/job.py` was missing from the module table, and the
  README did not say that `--blind` keeps the name in the email drafts (by design, see
  DECISIONS.md). CASE_STUDY labelled mock-mode numbers "measured"; they are now "demo data", so
  nobody reads them as real-mode results. Prompt sizes re-measured: system prompt 2,069 +
  schema 2,676 characters, user message 842 characters on average (min 522, max 1,042).
- **Demo image:** `docs/demo-run.png` from a real mock run (`scripts/render_demo_image.py`).
  Playwright's Python package expected a newer headless shell than the one installed
  (`Executable doesn't exist at .../chromium_headless_shell-1243/...`); passing the existing
  Chromium via `CHROMIUM_PATH` avoided a browser download.
- **History scan (all 42 commits):** gitleaks found nothing; a custom pass over every blob
  (including text inside the sample PDFs/DOCX) found no API keys or tokens, only
  example-domain email addresses and `0000`-pattern phone numbers. Three test fixtures use
  `example.de` / `example.nl`, which are not reserved example domains (fictional, left as is).

## Post hooks
- "Tell the model to ignore gender" is not a fairness control. "The model never receives it, and a
  test proves the text is identical" is.
- My fairness test caught a leak I would never have spotted by reading output: a pronoun rewrite
  that produced "them" for women and "their" for men, only when a PDF line wrapped.
- A CV parser's phone-number regex silently deleted every employment date. Every candidate would
  have become "experience unknown". Test the boring parts.
- Asking the model for quotes is only half the trick. Checking that each quote is actually in
  the CV is what turns a hallucination into a visible "unknown" instead of a silent "met".
- "Unknown" is a feature: a CV that says "German: fluent" gets a question, not a rejection.
  Keyword filters punish people for formatting, not for skills.
- "The quote exists in the CV" is not evidence. A warehouse picker reached tier A with the quotes
  "e", "a" and "2023". The quote has to contain the claim.
- I added a file-size limit to cap API cost and found a regex that would have run for about 44
  hours on one 6 MB upload. Reproduce the attack before you trust the fix.
- The slowest CV in my tests was 37 KB of empty paragraphs: 20 seconds, because the DOCX library
  looks up each paragraph's style by scanning every style. File-size limits do not measure work.
- My invariance test swapped "Erika Mustermann" for "Mohammed Al-Beispiel" and passed. It never
  tried "Özlem Yılmaz", whose name the redaction did not recognise at all. A fairness test is only
  as diverse as the people you write into it.

## Screenshots / GIFs to capture
- **Done:** `docs/demo-run.png` (terminal output + rendered shortlist, tier A), used in the
  README; regenerate with `python scripts/render_demo_image.py`.
- **Terminal GIF of the demo run:** `MOCK_LLM=1 screen run samples/ --job job.yaml --as-of 2026-10-01`
  (shows the one-line summary and "No emails were sent").
- **Rendered `out/shortlist.md`** on GitHub or in VS Code preview: the three tiers and the printed
  ranking rule.
- **Before/after redaction:** `samples/cv14.docx` opened in Word next to the "Removed before
  matching" line and the "They are a patient support agent" sentence (e.g. from a debug print of
  `redact(parse_file(...)).text`).
- **`out/candidates/cv08-df627b25.md`:** an `unknown` experience criterion with the quoted role line and the
  question "Ask for dates".
- **`out/emails/cv11-3510f9c6.md`:** variant B asking for CEFR levels instead of guessing from "fluent".
- **Hidden-text warning:** the shortlist row and summary for a PDF with white text (generate
  one with `tests/test_hidden_text.py::_pdf(path, "white")`).
- **Terminal run with a broken and an oversized CV:** the "Needs manual review" list, e.g.
  `screen run demo/ --job job.yaml --mock --max-pages 1`.
- **Benchmark before/after:** `python scripts/benchmark.py` on the old and new commit side by side
  (the hostile-file lines: 15.6 s / 21.5 s / 19.8 s vs 0.02 s / 2.15 s / 0.13 s).
- **Blind shortlist:** `screen run <folder with Erika_Mustermann_CV.pdf> --job job.yaml --mock --blind`
  and the rendered `shortlist.md` showing only `cv-xxxxxxxx` IDs.
- **Redaction of a German CV:** the `GERMAN_TEMPLATE` from `tests/test_invariance.py` next to
  `redact(...).text`.
- **CI run** with the invariance test in the pytest output:
  `pytest -v tests/test_invariance.py`.
