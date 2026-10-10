# CV Screening Assistant (human in the loop)

A command-line tool that helps a small company's hiring manager get through incoming CVs
faster. It reads PDF/DOCX CVs, removes protected attributes, extracts skills, experience,
languages and education with a quote from the CV for each claim, checks them against the
job's criteria, and writes a ranked shortlist with reasons, a one-page summary per candidate
and draft reply emails.

**The tool recommends, the human decides.** Nobody is rejected automatically, no email is
sent, and every status comes with the CV line that supports it.

Demo scenario: a 20-person online shop hiring a *Junior Customer Support Specialist*. The 20
CVs in [`samples/`](samples/) are synthetic and fictional (placeholder names, `example.com`
addresses, a "SYNTHETIC CV" footer on every page).

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Offline demo, no API key needed (rule-based mock extractor)
MOCK_LLM=1 screen run samples/ --job job.yaml

# Real mode with Claude
cp .env.example .env          # then put your ANTHROPIC_API_KEY in .env
screen run samples/ --job job.yaml
```

Output goes to `out/` (git-ignored, because it contains personal data):

| File | What it is |
|---|---|
| `out/shortlist.md` | Ranked shortlist in three tiers, criteria table, ranking rule, next steps |
| `out/shortlist.csv` | Same, one row per candidate, with status and evidence per criterion |
| `out/candidates/<id>.md` | One-page summary: criteria with evidence quotes, extracted profile, questions to ask, warnings |
| `out/emails/<id>.md` | Draft reply with three variants (invite / ask for missing info / decline), never sent |
| `out/run_report.json` | Timing, tokens and cost of the run |

If `screen` clashes with GNU screen on your machine, use `python -m cv_screen run ...`.

## Architecture

```mermaid
flowchart LR
    A[CV files<br/>PDF / DOCX / TXT] --> B[parsing.py<br/>text only, images ignored]
    B --> C[redact.py<br/>remove name, photo, age, gender,<br/>nationality, marital status,<br/>address, contact, pronouns]
    C -->|redacted text only| D{extractor}
    D -->|real mode| E[Claude API<br/>structured outputs<br/>JSON schema]
    D -->|MOCK_LLM=1| F[rule-based<br/>mock extractor]
    E --> G[extract.build_profile<br/>every quote is in the CV<br/>and shows the claimed value;<br/>compute years of experience]
    F --> G
    J[job.yaml<br/>must-have / nice-to-have] --> H
    G --> H[matching.py<br/>met / partly / not met / unknown<br/>+ evidence line]
    H --> I[ranking<br/>tiers + printed sort rule]
    I --> K[report.py<br/>shortlist.md / .csv<br/>summaries, email drafts]
    K --> M((Hiring manager<br/>decides))
    C -. name kept locally .-> K
```

Design in one paragraph: the model reads, the code decides. The LLM only turns messy CV text
into a strict schema (each item with a verbatim quote). Everything that affects the ranking
(date arithmetic, criterion rules, tiers, sort order) is plain Python driven by `job.yaml`,
so it is testable offline and identical between runs. See [`DECISIONS.md`](DECISIONS.md) for
the reasoning behind each choice.

| Module | Responsibility |
|---|---|
| `cv_screen/parsing.py` | PDF (pypdf), DOCX (python-docx, incl. tables), TXT/MD to normalised text |
| `cv_screen/redact.py` | Remove protected attributes; return the name separately for manager-facing output |
| `cv_screen/schema.py` | Pydantic models; strict JSON schema for structured outputs |
| `cv_screen/extract.py` | `ClaudeExtractor`, `MockExtractor`, quote verification, experience calculation, token cost |
| `cv_screen/matching.py` | Criterion rules, tiers, sort key |
| `cv_screen/pipeline.py` | Runs every CV (in parallel threads), failures go to manual review |
| `cv_screen/report.py` | Markdown, CSV, summaries, email drafts, run report |
| `cv_screen/cli.py` | `screen run` |

## Configuration

### Command line

```
screen run FOLDER --job job.yaml [options]

  --out PATH          output folder (default: out)
  --mock / --real     offline mock extractor or Claude API (default: real unless MOCK_LLM=1)
  --model TEXT        Claude model (default: $CV_SCREEN_MODEL or claude-haiku-4-5-20251001)
  --as-of YYYY-MM-DD  count experience up to this date (default: today)
  --blind             hide names in shortlist and summaries as well
  --workers N         parallel API calls (default: 4)
```

### Environment (`.env`, see [`.env.example`](.env.example))

| Variable | Meaning |
|---|---|
| `ANTHROPIC_API_KEY` | Required for real mode. Never commit it; `.env` is git-ignored. |
| `CV_SCREEN_MODEL` | Override the extraction model. |
| `MOCK_LLM` | `1` to run offline with the mock extractor (used by the tests and CI). |

### Job criteria (`job.yaml`)

```yaml
criteria:
  must_have:
    - id: german
      label: German at B2 or above
      type: language          # CEFR level, "native" counts above C2
      language: German
      min_level: B2
    - id: experience
      label: At least 1 year of customer-facing experience
      type: experience_years  # summed from dated roles the extractor marks as relevant
      min_years: 1
      partly_min_years: 0.5
  nice_to_have:
    - id: helpdesk_tool
      label: Experience with a helpdesk tool
      type: skill             # whole-term match on extracted skills
      any_of: [zendesk, freshdesk, gorgias, help scout, intercom]
      partly_any_of: [crm, hubspot, salesforce]
```

Criterion types: `language`, `language_any`, `experience_years`, `skill`, `education`
(`secondary < vocational < bachelor < master < doctorate`). `relevant_experience.description`
is given to the model to decide which roles count; `relevant_experience.keywords` is used by
the mock extractor.

### Ranking rule (no hidden score)

- **Tier A:** all must-haves met.
- **Tier B:** no must-have clearly missing, but some are `partly` or `unknown`. Check these.
- **Tier C:** at least one must-have looks `not met`. A review flag, not a rejection.

Within a tier: more must-haves met, then more must-haves partly met, then more nice-to-haves
met, then more nice-to-haves partly met, then fewer unknowns, then candidate ID. The rule is
printed at the top of every shortlist.

## Fairness and privacy

**Protected attributes are removed before matching, and a test proves it.**

- Before extraction, `redact.py` removes: name (header line, `Name:` field and every later
  mention), photo markers, date of birth and age phrases, gender, nationality and place of
  birth, marital status and children, religion, address, email, phone, URLs, titles
  (Mr/Ms/Herr/Frau) and gendered pronouns (rewritten to they/them/their). Images are never
  read at all: only the text layer is parsed.
- Only the redacted text is sent to the API. The name stays on your machine and reappears only
  in the manager-facing outputs, in a column labelled "not used for matching" (`--blind`
  hides it there too).
- `tests/test_invariance.py` changes name, address, email, phone, date of birth, nationality,
  gender, marital status, photo and pronouns, and asserts that (a) the text given to the
  extractor is byte-identical, (b) the prompt sent to Claude is byte-identical, and (c) the
  match results are identical. It runs on hand-written variants, on four sample CVs (PDF and
  DOCX), and on DOCX files with and without an embedded photo.
- Missing information is `unknown`, never `not met`, and becomes a question for the
  candidate. Language levels like "fluent" are not guessed into CEFR levels.
- Every claim needs a quote of at least two words (or eight characters) that is found in the CV
  **and contains the claimed value**: the skill name, the language and its level, the job title
  and its start and end years (or "present"/"now"/"since"), the qualification type, field and
  "in progress"/"expected" if unfinished. Claims that fail are dropped and listed as warnings
  in the summary. A role whose quote has none of the job's `relevant_experience.keywords`
  stays in the profile but does not count as relevant, and a month the quote does not show is
  counted as the year only. This is strict on purpose: a true claim the model quoted badly is
  also dropped, but it is listed, so the manager can check the CV instead of trusting a guess.
- **The tool recommends, the human decides.** Every output says so. There is no auto-reject
  and no email sending; the email drafts contain an invite, a "please tell us more" and a
  decline variant, and the manager chooses.

**Data handling and retention**

- Everything runs locally except the extraction call in real mode, which sends redacted CV
  text to the Anthropic API under your own API key and your organisation's data retention
  settings with Anthropic. Mock mode sends nothing anywhere.
- Output in `out/` contains names and CV content. It is git-ignored. Delete it when the
  opening is closed, within the retention period your local rules set (under GDPR, only as
  long as needed for the hiring decision and possible legal claims, unless the candidate agrees
  to longer storage; this is not legal advice). The tool itself keeps no database and no
  cache.
- No real CVs are in this repository. `scripts/generate_samples.py` regenerates the
  fictional samples byte-for-byte.

## Limitations

- **Redaction is pattern-based.** It covers labelled fields, the name line, contact details,
  pronouns and titles. It does not catch every proxy: graduation and employment years hint at
  age, school or club names can hint at origin or gender, and "native" language can hint at
  nationality. Read the redacted text in the summaries if you are unsure.
- **Hidden text counts.** White-on-white text in a PDF is extracted like visible text. Because
  matching only uses quoted lines, a stuffed keyword still needs to be in the CV, and the
  manager sees the quote, but it can move a candidate up.
- **Prompt injection.** The CV is treated as data in the prompt (with `<`, `>` and `&`
  escaped, so it cannot open or close a prompt tag), and the model never decides the ranking,
  but a CV can still try to influence what the model extracts. Evidence checking limits this
  to claims whose value is written in the CV itself: a model told to "add Zendesk" or "start
  the job in 2010" has no quote that shows it, and the claim is dropped.
- **No OCR.** Scanned image-only PDFs go to "manual review".
- **Mock mode only understands the sample layout.** It exists for offline tests and demos; its
  results say nothing about LLM accuracy.
- **Skill matching is literal.** `any_of` terms are matched as whole words against extracted
  skills; synonyms must be listed in `job.yaml`.
- **Year-only dates** count from the middle of the year; "present" counts up to the start of
  the `--as-of` month.
- **Real-mode accuracy has not been measured yet** (see [`CASE_STUDY.md`](CASE_STUDY.md)).
- English-language CVs and criteria only.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest -q                               # offline, no API key needed
python scripts/generate_samples.py      # regenerate samples (deterministic)
```

CI (`.github/workflows/ci.yml`) runs lint, the test suite, a reproducibility check of the
samples and a mock-mode run on Python 3.11 to 3.13.

Optional automation: [`n8n/`](n8n/) has a workflow that runs the screening when a new CV lands
in a folder and notifies the manager.

Project tracking: [`PROGRESS.md`](PROGRESS.md), [`DECISIONS.md`](DECISIONS.md),
[`BUILD_LOG.md`](BUILD_LOG.md), case study in [`CASE_STUDY.md`](CASE_STUDY.md).
