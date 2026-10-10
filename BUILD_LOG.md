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
- **Test suite:** 97 tests, about 3 s, fully offline.
- **CI:** first push green on Python 3.11, 3.12 and 3.13, including a check that the sample
  generator reproduces the committed files byte-for-byte.
- **Real mode: not measured.** The build environment had no Anthropic API key. Prompt size
  measured locally: fixed system prompt + JSON schema about 4,300 characters, redacted demo CV
  message about 840 characters on average (max 1,042). Token count and cost per CV are an
  estimate until a real run exists (see CASE_STUDY.md).
- **Accuracy:** not measured. The mock extractor is rule-based and written for the sample
  layout, so its results on the samples say nothing about LLM extraction accuracy.

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
- **CI run** with the invariance test in the pytest output:
  `pytest -v tests/test_invariance.py`.
