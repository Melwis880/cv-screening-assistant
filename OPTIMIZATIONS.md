# Optimization audit (2026-10-11)

Scope: the code on this branch after the first security review (`c9f0821`): parsing, redaction,
extraction (Claude and mock), evidence checks, matching, cache, reports, CLI. Measured with
`scripts/benchmark.py` (added for this audit) and the mock-mode demo run on the 20 samples.
All numbers are **demo data** from this build container (Python 3.13, no API key); anything
about real-mode tokens or cost is an **estimate** and says so.

## Summary

The happy path is already fast: 20 sample CVs take 266 ms of CPU end to end, and a whole mock
run takes 0.39 s. The real problems are elsewhere:

1. **Parsing is unbounded in CPU time for small hostile files.** A 22 KB PDF takes 15.6 s, a
   1.9 KB PDF that invokes one form 40 times takes 21.5 s (pypdf allows 5,000 invocations,
   which extrapolates to about 45 minutes), and a 37 KB DOCX of empty paragraphs takes 19.8 s
   (0.9 ms per paragraph; the 50 MB unpacked limit allows millions). None of this is caught
   by the existing size, page, unpacked-size or character limits, because the expensive part
   happens before any text is counted.
2. **Four correctness bugs that the sample fixtures hide** change real candidates' results:
   "mother tongue" is redacted to "[REDACTED] tongue" so a native language loses its level; a
   CV whose first line is a headline ("Customer Support Specialist") has that headline taken
   as the name, and every "customer" and "support" in the CV is replaced by `[CANDIDATE]`;
   DOCX tables are moved to the end of the text and text boxes are not read at all; a role
   dated in the future subtracts months from the experience total.
3. **No request timeout on the API client.** The SDK default is 10 minutes and timeouts are
   retried, so one stalled connection can hold a worker for 40 minutes.
4. **LLM spend is already lean.** One call per CV, cached across runs. The fixed part of each
   prompt (system prompt + JSON schema) is about 70% of the input (estimate) but is far below
   the 4,096-token minimum that prompt caching needs on Haiku 4.5, so caching cannot help;
   batching several CVs into one call would mix applicants in one context. The one avoidable
   call is a duplicate file in the same run (two concurrent cache misses).

No material dead code was found. Two small duplications are listed under quick wins.

## Baseline (demo data)

`python scripts/benchmark.py` before any change:

| Stage (20 samples, best of 5) | ms |
|---|---|
| parse PDF (10 files) | 58.9 |
| parse DOCX (10 files) | 189.9 |
| redact | 7.7 |
| mock extract | 3.9 |
| verify evidence | 3.3 |
| match | 1.9 |
| **total** | **265.6** |

| Hostile file (parse only) | Size | Time |
|---|---|---|
| PDF, one page, 400k empty text operators | 21,923 B | 15.60 s |
| PDF, one form of 20k empty text operators, invoked 40 times | 1,915 B | 21.50 s |
| DOCX, 20,000 empty paragraphs | 36,819 B | 19.78 s |

Mock demo run (`screen run samples/ --job job.yaml --mock --as-of 2026-10-01`): 0.39-0.40 s wall
inside the run, 0.85-0.91 s for the whole process (import time about 0.31 s); tiers A 7 / B 9 /
C 4. Prompt per CV: system prompt 2,069 characters, JSON schema 2,676, user message 842 on
average (max 1,042), so roughly 1,400 input tokens per call, about 900 of them fixed (estimate:
characters / 4 + structured-output overhead, not measured with the API).

## Findings (prioritized)

### O1. PDF text extraction has no CPU budget — High
- **Category:** unbounded parsing (resource exhaustion).
- **Evidence:** `cv_screen/parsing.py:97-117`. `page.extract_text(...)` (line 106) runs before
  any limit can fire; the character check (line 109) only counts text that was produced. pypdf
  decompresses a content stream up to 75 MB and re-parses a form XObject on each `Do`, up to
  5,000 times per page.
- **Why it matters:** anyone who applies controls the file. The n8n flow screens new
  attachments automatically, and `--workers 4` means four such files stall the whole run.
- **Measured:** 15.6 s for a 22 KB file (400k empty `Tj`), 21.5 s for a 1.9 KB file (form
  invoked 40 times; about 0.5 s per invocation). Parsing 8.8 MB of content takes 11 s before the
  first operator reaches our callback.
- **Fix:** a per-file budget enforced inside the existing visitor callback: count operators and
  the decoded bytes of every content stream that will be parsed (page contents up front, a
  form's bytes each time it is invoked, checked *before* the `Do` runs). Over budget → `LimitError`
  → manual review, like every other limit. Defaults far above real CVs (samples: 150-213
  operators per file).
- **Tradeoffs:** a very graphics-heavy designed CV could hit the budget and go to manual review
  (never a rejection). pypdf logs and swallows the first exception raised inside a form; the
  next operator at page level raises again, so the budget still stops extraction (tested).
- **Expected impact:** worst case bounded to a few seconds per file whatever the structure.
- **Removal safety:** additive; no output changes for files under the budget.

### O2. DOCX parsing is O(paragraphs × styles) and never stops early — High
- **Category:** slow + unbounded parsing.
- **Evidence:** `cv_screen/parsing.py:191-193`. `para.style` resolves the style through
  python-docx, which scans every style in `styles.xml` when a paragraph has no explicit style.
  cProfile on the 10 sample DOCX files: 0.324 s of 0.454 s (71%) in `Paragraph.style`. The text
  length is only checked after the whole document is converted (`parse_cv`, line 81).
  `row.cells` (line 196) yields a spanned cell once per grid column, so a cell with a huge
  `gridSpan` is repeated that many times.
- **Measured:** 19.8 s for 20,000 empty paragraphs (37 KB file); about 0.9 ms per paragraph with
  the default 160 styles.
- **Fix:** map style IDs to names once per document; stop as soon as the text passes
  `max_chars` (empty paragraphs count as one newline each); read table rows from the actual
  `<w:tc>` cells, so a spanned cell appears once. Add a cap on the XML parts of the package, so
  the 50 MB unpacked limit (meant for embedded images) cannot be spent on markup.
- **Tradeoffs:** none for normal files; a DOCX whose XML is over the new cap goes to manual review.
- **Expected impact:** DOCX parsing on samples about 2× faster (see Applied for the measured
  number); hostile DOCX bounded by `max_chars`.
- **Removal safety:** the produced text for the samples must stay byte-identical (checked by the
  invariance and sample tests, and by comparing the redacted text of all 20 samples).

### O3. DOCX tables lose their place; text boxes are dropped; merged cells repeat — Medium
- **Category:** correctness bug hidden by fixtures (no sample uses tables or text boxes).
- **Evidence:** `cv_screen/parsing.py:190-197` reads all paragraphs, then all tables. A CV
  whose Experience section is a table ends up with its roles after the last heading (Skills),
  so the mock assigns them to the wrong section and the model sees roles without their
  heading. Text in Word text boxes (common for sidebars with languages and skills) is not in
  `doc.paragraphs` at all, so it silently disappears and those criteria become *unknown* or
  *not met*. Horizontally merged cells are printed once per spanned column.
- **Fix:** walk the body in document order (paragraphs and tables), and read text-box
  paragraphs right after the paragraph that anchors them (only the `mc:Choice` copy, not the
  VML fallback, so text is not duplicated).
- **Tradeoffs:** CVs that used text boxes now send more text to the model (the text that was
  always there). Headers and footers are still not read (they usually hold the name/contact
  block, which we would redact anyway).
- **Expected impact:** template-based DOCX CVs are screened on their full content.
- **Removal safety:** the 10 sample DOCX files have no tables or text boxes; their text must not
  change.

### O4. "mother tongue" is redacted, so native speakers lose their level — Medium
- **Category:** correctness bug hidden by fixtures (all samples write "native").
- **Evidence:** `cv_screen/redact.py:312-314` replaces `mother` everywhere. "German (mother
  tongue)" becomes "German ([REDACTED] tongue)", so `_NATIVE_RE` (`extract.py:374`) and the
  model can no longer see a level; the German must-have becomes *unknown* (tier B instead of A).
  The phrase is typical for people translating "Muttersprache", i.e. it is correlated with
  origin.
- **Fix:** do not redact "mother" when "tongue" follows.
- **Expected impact:** native languages written this way count as native again.
- **Removal safety:** a regression test with the phrase; samples unchanged.

### O5. A headline on the first line is taken as the name and erased everywhere — Medium
- **Category:** correctness bug hidden by fixtures (every sample starts with a name or a
  `Name:` label).
- **Evidence:** `cv_screen/redact.py:315` and `416-425`: the first of the first three lines that
  looks like 2-4 capitalised words is the name; `_remove_name` (line 428) then replaces each of
  its words anywhere in the CV. PoC: a CV starting "Customer Support Specialist" (name in a DOCX
  header, which is not read) comes out as "[CANDIDATE] Agent ... Answered [CANDIDATE] emails".
  The relevance keywords and the written-support skill disappear, so a strong candidate drops
  to tier C.
- **Fix:** a line is not a name if one of its words is a common CV heading or job word
  (customer, support, service, agent, assistant, specialist, manager, experience, profile,
  summary, ...), or one of the job's relevance keywords.
- **Tradeoffs:** a person whose name is such a word ("Victoria Service") is not auto-detected by
  the first-line guess; the `Name:` label still works, and the manager sees "(not found)".
- **Removal safety:** the guess still finds the names in all samples and invariance tests.

### O6. API calls have no timeout — Medium
- **Category:** timeouts/retries.
- **Evidence:** `cv_screen/extract.py:139` `anthropic.Anthropic(max_retries=3)`. The SDK default
  timeout is 10 minutes and timed-out requests are retried, so a stalled connection can block a
  worker for up to 4 × 10 = 40 minutes.
- **Fix:** `timeout=120` seconds (a Haiku extraction with `max_tokens=4096` finishes well inside
  that); keep `max_retries=3` (DECISIONS 2026-10-09).
- **Tradeoffs:** a genuinely slow response over 2 minutes is retried and, after four attempts,
  the CV goes to manual review.
- **Expected impact:** worst case per CV 8 minutes instead of 40.
- **Removal safety:** offline test that the default client carries the timeout.

### O7. Future-dated roles subtract experience — Low
- **Category:** correctness bug.
- **Evidence:** `cv_screen/extract.py:579` clips a role's end to the `as_of` month but keeps its
  start, so a role from 2027-2028 becomes an interval of negative length. PoC: a 12-month 2025
  role plus a 2027-2028 role gives 4 months instead of 12.
- **Fix:** skip roles that start after `as_of` (with a warning), and never add an empty interval.
- **Removal safety:** unit test; samples have no future roles.

### O8. Soft hyphens and zero-width characters break term matching — Low
- **Category:** correctness bug.
- **Evidence:** `cv_screen/parsing.py:200-211` keeps Unicode format characters. PDF exports often
  contain soft hyphens (U+00AD) inside words; "Zen­desk" no longer matches "zendesk", and the
  model may quote the word without the invisible character so the quote check fails.
- **Fix:** drop characters of category Cf (soft hyphen, zero-width space/joiner, bidi marks, BOM)
  in `normalize_text`. These characters are also how text is visually reordered (bidi
  overrides), so outputs get safer too.
- **Removal safety:** samples contain none; regression test.

### O9. Duplicate files in one run are extracted twice — Low
- **Category:** unnecessary LLM calls / cache correctness.
- **Evidence:** `cv_screen/pipeline.py:80-96`. With 4 workers, two files with the same bytes
  (the same attachment sent twice) both miss the cache before either writes it, so both are
  billed.
- **Fix:** single-flight per cache key: the second worker waits for the first and then reads its
  cache entry.
- **Expected impact:** one call per distinct CV instead of one per file (real mode, cache on).
- **Removal safety:** only active when the cache is on; test counts calls on a fake client.

### O10. Fixed prompt overhead — Info (no change)
- **Evidence:** about 4,750 of about 5,600 input characters per call are the system prompt and
  the schema (`extract.py:76-105`, `schema.py`); estimate ~900 of ~1,400 tokens.
- **Options considered:** prompt caching (rejected: Haiku 4.5 caches only prefixes of 4,096+
  tokens, ours is ~1,200, so the marker would silently do nothing); several CVs per call
  (rejected: mixes applicants in one context, one bad CV fails the others, harder to verify);
  Message Batches (already rejected in DECISIONS: interactive use); trimming schema descriptions
  that repeat the prompt (deferred: saves an estimated ~$0.0002 per CV and changes model
  behaviour; needs the real-mode accuracy run first).

### O11. Output tokens dominate cost — Info (deferred)
- **Evidence:** every skill repeats its evidence line, so a skills line with five tools is quoted
  five times. At $5/MTok output vs $1/MTok input on Haiku 4.5, output is probably most of the
  ~$0.004-0.008 per CV (estimate).
- **Option:** group skills by evidence line in the schema. Deferred: schema and prompt change,
  invalidates the cache, and the saving can only be measured with real runs.

### O12. Quick wins (small duplication) — Low
- Tier counts are computed in `cli.py:467` and again in `report.py:357`; a `ScreeningRun.tiers`
  property removes the duplication.
- Each file is read twice (SHA-256 in `pipeline.assign_ids`, then `parse_cv`). Rejected: 20 small
  files, microseconds; reading once would couple hashing to parsing.

## Quick wins
O4, O6, O7, O8, O12 (one-line to ten-line changes with a test each).

## Deeper items
O1, O2, O3 (parser changes with tests and before/after numbers), O5 (heuristic with a stop list),
O9 (concurrency). O10, O11 deferred to after a real-mode run.

## Validation plan
1. Each fix gets a test that fails on the old code (or, for pure speed, a time bound the old
   code cannot meet), and the full suite stays green (`pytest -q`, `ruff check .`).
2. The redacted text of all 20 samples must be byte-identical before and after (checked with a
   one-off script; the invariance tests also compare it).
3. Mock demo run: same tiers (A 7 / B 9 / C 4), same shortlist content.
4. `scripts/benchmark.py` before/after for the samples and the hostile files.
5. CI on Python 3.11-3.13.

## Applied (2026-10-11)

One commit per finding, each with a test that fails on the old code (the list-style test in
`tests/test_docx_layout.py` is a guard that passes on both). The redacted text of all 20 samples
is byte-identical before and after, and the mock demo run gives the same shortlist, summaries
and emails (only timing fields in `run_report.json` differ).

| Finding | Commit | Change |
|---|---|---|
| O1 PDF budget | `c7926b0` | operator + decoded-content budget per file (300,000 / 5 MB), forms charged per use |
| O2 + O3 DOCX | `1eff8e6` | XML walker in reading order: tables in place, text boxes once, content controls, tracked insertions, merged cells once; style map once; early stop at `max_chars`; 10 MB XML cap |
| O4 mother tongue | `76d744f` | not redacted when followed by "tongue" |
| O8 format characters | `a469fa2` | Unicode Cf dropped in `normalize_text` |
| O7 future roles | `0972981` | skipped with a warning instead of subtracting months |
| O6 timeout | `2f94872` | 120 s per attempt, `max_retries=3` kept |
| O5 headline as name | `894950b` | first-line name guess rejects lines with CV heading / job words |
| O9 duplicate files | `1e940b5` | one lock per cache key (single-flight) |
| O12 tier counts | `b742a92` | `ScreeningRun.tiers` |

### Measured before / after (demo data, this container)

`python scripts/benchmark.py` (samples: best of 5 before, best of 10 after):

| Stage (20 samples) | Before (ms) | After (ms) |
|---|---|---|
| parse PDF (10 files) | 58.9 | 65.2 |
| parse DOCX (10 files) | 189.9 | 87.7 |
| redact | 7.7 | 7.3 |
| mock extract + verify + match | 9.1 | 7.9 |
| **total** | **265.6** | **168.1** |

PDF parsing is about 0.6 ms per file slower: the budget decodes each page's content once more
and looks up form sizes before extraction. That is the price of the bound below.

| Hostile file | Before | After |
|---|---|---|
| PDF, 22 KB, 8.8 MB of empty text operators | 15.60 s, then "no text found" | 0.02 s, manual review (content budget) |
| PDF, 1.9 KB, form of 20k operators used 40× | 21.50 s, then "no text found" | 2.15 s, manual review (operator budget) |
| DOCX, 37 KB, 20,000 empty paragraphs | 19.78 s, then "no text found" | 0.13 s, "no text found" |
| DOCX, 40,000 empty paragraphs (test) | ~37 s, then over `max_chars` | < 0.5 s, over `max_chars` |

Worst cases still inside the PDF budget (measured): 4.8 MB of empty text operators 5.6 s,
4.8 MB of `q Q` 6.9 s, a 2.4 MB form drawn twice 4.0 s; all end in manual review. Before the
fix the same structure scaled to about 45 minutes per file (5,000 form uses × 0.5 s).

Mock demo run (`screen run samples/ --job job.yaml --mock --as-of 2026-10-01`, 5 runs each):
`wall_seconds` 0.325-0.385 before, 0.203-0.272 after; whole process 0.85-0.91 s before,
0.63-0.66 s after. Tiers unchanged (A 7 / B 9 / C 4).

Real mode (not measured, no API key): O9 saves one call per duplicate file in a run; O6 bounds a
stalled call at 8 minutes instead of 40; O3, O4, O5 and O8 change results for CVs unlike the
samples (tables, text boxes, "mother tongue", a headline first line, soft hyphens), which is
the point of fixing them.

### Deferred, and why
- **O10 prompt overhead:** prompt caching cannot apply (prefix ~1,200 tokens, Haiku 4.5 needs
  4,096); several CVs per call would mix applicants; trimming the schema descriptions needs a
  real-mode accuracy run to show it does not hurt extraction.
- **O11 output tokens:** grouping skills by evidence line is a schema and prompt change; it would
  invalidate the cache and needs real runs to measure both the saving and the accuracy.
- **Reading each file once (O12, second item):** microseconds on 20 files; not worth coupling
  hashing to parsing.
- **Lower PDF content budget:** 2 MB would cut the worst case to about 3 s, but designed CVs
  with vector graphics could then land in manual review; 5 MB keeps that unlikely. Revisit with
  real-world PDFs.
- **DOCX headers, footers, footnotes and nested tables** are still not read. Headers usually hold
  the name and contact block (redacted anyway); the others are rare in CVs.
