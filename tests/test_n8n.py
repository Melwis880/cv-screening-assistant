"""The optional n8n workflow keeps per-candidate data out of n8n's execution log."""

import json
import re
import subprocess
import sys

from tests.conftest import ROOT

WORKFLOW = json.loads((ROOT / "n8n" / "cv-screening-workflow.json").read_text(encoding="utf-8"))


def _node(kind):
    return next(n for n in WORKFLOW["nodes"] if n["type"] == f"n8n-nodes-base.{kind}")


def test_run_node_prints_only_the_counts_the_email_needs(tmp_path):
    command = _node("executeCommand")["parameters"]["command"]
    assert "cat " not in command  # the whole report has candidate IDs and error messages
    script = re.search(r'python -c "(.*)"$', command).group(1)
    report = {"job": "J", "cvs": 2, "manual_review": 1, "tiers": {"A": 1, "B": 0, "C": 0},
              "per_cv": [{"candidate_id": "Erika_Mustermann_CV-12345678", "error": "x"}]}
    path = tmp_path / "run_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    script = script.replace("/data/screening/junior-support/run_report.json", str(path))
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                         check=True).stdout
    assert json.loads(out) == {k: report[k] for k in ("job", "cvs", "manual_review", "tiers")}
    used = set(re.findall(r"report\.(\w+)", _node("code")["parameters"]["jsCode"]))
    assert used <= set(json.loads(out))
