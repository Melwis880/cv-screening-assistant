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
_(added after demo runs)_

## Post hooks
- "Tell the model to ignore gender" is not a fairness control. "The model never receives it, and a
  test proves the text is identical" is.
- My fairness test caught a leak I would never have spotted by reading output: a pronoun rewrite
  that produced "them" for women and "their" for men, only when a PDF line wrapped.
- A CV parser's phone-number regex silently deleted every employment date. Every candidate would
  have become "experience unknown". Test the boring parts.

## Screenshots / GIFs to capture
_(collected during the build)_
