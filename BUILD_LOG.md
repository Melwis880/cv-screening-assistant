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
  about 8 s on a 12-core laptop after it).
- **CI:** first push green on Python 3.11, 3.12 and 3.13, including a check that the sample
  generator reproduces the committed files byte-for-byte.
- **Real mode: not measured.** The build environment had no Anthropic API key. Prompt size
  measured locally: fixed system prompt + JSON schema about 4,300 characters, redacted demo CV
  message about 840 characters on average (max 1,042). Token count and cost per CV are an
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

## Screenshots / GIFs to capture
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
- **CI run** with the invariance test in the pytest output:
  `pytest -v tests/test_invariance.py`.
