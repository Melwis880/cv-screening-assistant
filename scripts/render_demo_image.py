"""Render docs/demo-run.png from a real mock-mode run of the README quickstart command.

Runs `MOCK_LLM=1 screen run samples/ --job job.yaml` in a temporary copy of `samples/` and
`job.yaml`, then screenshots its terminal output and the rendered `out/shortlist.md` (cut
after tier A) with headless Chromium. Nothing in the output is edited.

Extra requirements (not in the dev extras): pip install markdown playwright
Chromium: set CHROMIUM_PATH if Playwright's own browser is not installed.

Usage: python scripts/render_demo_image.py [docs/demo-run.png]
"""

from __future__ import annotations

import html
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
COMMAND = "MOCK_LLM=1 screen run samples/ --job job.yaml"

STYLE = """
body { margin: 0; padding: 24px; width: 1240px; background: #f6f8fa; color: #1f2328;
       font: 14px -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }
.label { margin: 18px 0 6px; font-size: 12px; color: #59636e; }
.term { padding: 14px 18px; border-radius: 8px; background: #0d1117; color: #e6edf3;
        font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        white-space: pre-wrap; }
.term .prompt { color: #7ee787; }
.md { padding: 4px 24px 16px; border: 1px solid #d1d9e0; border-radius: 8px; background: #fff; }
.md h1 { font-size: 22px; padding-bottom: 6px; border-bottom: 1px solid #d1d9e0; }
.md h2 { font-size: 18px; } .md h3 { font-size: 15px; }
.md blockquote { margin: 0; padding: 2px 14px; border-left: 4px solid #d1d9e0; color: #59636e; }
.md table { border-collapse: collapse; font-size: 12.5px; }
.md th, .md td { padding: 5px 8px; border: 1px solid #d1d9e0; vertical-align: top; }
.md th { background: #f6f8fa; }
.md a { color: #0969da; text-decoration: none; }
"""


def main(out_png: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copytree(ROOT / "samples", work / "samples")
        shutil.copy(ROOT / "job.yaml", work / "job.yaml")
        run = subprocess.run(["screen", "run", "samples/", "--job", "job.yaml"], cwd=work,
                             env=dict(os.environ, MOCK_LLM="1"), capture_output=True,
                             text=True, check=True)
        shortlist = (work / "out" / "shortlist.md").read_text(encoding="utf-8")

        # A crop, not an edit: the header and tier A, as written by the tool.
        header = shortlist.split("## Criteria")[0]
        tier_a = shortlist.split("## Ranking")[1].split("### Tier B")[0]
        rendered = markdown.markdown(header + "## Ranking" + tier_a, extensions=["tables"])
        page = work / "demo.html"
        page.write_text(
            f'<!doctype html><meta charset="utf-8"><style>{STYLE}</style>'
            '<div class="label">Terminal</div>'
            f'<div class="term"><span class="prompt">$ {html.escape(COMMAND)}</span>\n'
            f"{html.escape(run.stdout.rstrip())}</div>"
            '<div class="label">out/shortlist.md (rendered, cut after tier A)</div>'
            f'<div class="md">{rendered}</div>',
            encoding="utf-8",
        )
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH"))
            tab = browser.new_page(viewport={"width": 1288, "height": 800},
                                   device_scale_factor=1.5)
            tab.goto(page.as_uri())
            tab.screenshot(path=str(out_png), full_page=True)
            browser.close()
    print(run.stdout, end="")
    print(f"Wrote {out_png}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "demo-run.png")
