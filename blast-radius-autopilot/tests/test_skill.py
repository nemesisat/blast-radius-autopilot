"""B9 — the packaged DataHub Skill runs and returns structured impact JSON."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "datahub-skill" / "skill.py"
CATALOG = ROOT / "examples" / "showcase-ecommerce" / "catalog.json"


def test_skill_emits_impact_json():
    proc = subprocess.run(
        [sys.executable, str(SKILL), "--catalog", str(CATALOG),
         "--dataset", "analytics.fct_orders", "--column", "customer_zip", "--op", "drop"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["change"] == "drop analytics.fct_orders.customer_zip"
    assert out["counts"]["breaks"] == 6      # B15: filter-only refs now break on a drop
    assert out["risk"]["level"] == "CRITICAL"
    assert any(v["verdict"] == "BREAKS" for v in out["verdicts"])
