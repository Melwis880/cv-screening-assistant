# n8n workflow (optional)

`cv-screening-workflow.json` watches a folder for new CVs, waits two minutes so a batch of
uploads triggers one run, runs `screen run` on the whole folder, and emails the hiring manager
a short notice with the tier counts and where to find the shortlist.

The email goes to the **manager only**. Nothing is ever sent to candidates; the reply drafts
stay in the output folder for the manager to edit and send.

## Setup

1. Self-hosted n8n (the *Local File Trigger* and *Execute Command* nodes are not available on
   n8n Cloud). Install this repo on the same machine, e.g. in `/opt/cv-screening-assistant`
   with a virtualenv in `.venv`, and put `ANTHROPIC_API_KEY` in its `.env`.
2. Import the JSON in n8n (*Workflows -> Import from file*).
3. Adjust the folder paths in *New CV in folder* and *Run screening*, set the manager's
   address in *Notify hiring manager*, and select your SMTP credential.
4. Activate the workflow.

To use an inbox instead of a folder, replace the trigger with an *Email Trigger (IMAP)* node
and a *Write Binary File* node that saves attachments into the watched folder. **Save each
attachment under a generated name, never under the applicant's file name:** a UUID (for
example from a *Crypto* node, action *Generate*, type *UUID*) plus the extension, and only if
the extension is on a whitelist (`.pdf`, `.docx`, `.txt`); skip every other attachment. An
attachment name is chosen by the sender and can contain `../` (writing outside the folder),
start with a dot (hidden from screening), overwrite another applicant's file, or carry
terminal and markup tricks. Keep the original name and the sender's address only in your
mailbox, not in the screening folder.

## Notes

- The output folder contains personal data; keep it on the same machine and delete it when
  the opening is closed.
- Each run re-screens the whole folder, but unchanged CVs come from the extraction cache in
  `/data/screening/junior-support/.cache/extractions` (owner-only, entries deleted after 30
  days), so only new or changed CVs are sent to the API. Ranks can shift as new CVs arrive; a
  candidate's tier and criteria do not.
- Status: the JSON follows the n8n workflow export format but has **not been tested against a
  live n8n instance** in this repo's build. Check node versions after import.
