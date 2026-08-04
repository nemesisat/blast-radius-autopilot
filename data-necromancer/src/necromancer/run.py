"""CLI: scan -> investigate -> rank -> write back.

Offline demo (no DataHub needed) reads a JSON list of assets so you can rehearse
the whole flow, including the leaderboard cold-open:

    python -m necromancer.run --assets examples/sample_catalog.json

Against DataHub, pass URNs and --write to apply (approve-before-write gate means
only strongly-evidenced reconstructions are written; the rest are queued):

    python -m necromancer.run --online --write --urns urn:li:dataset:(...)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .evidence import Evidence
from .health import classify, coverage, leaderboard
from .investigator import investigate


def _load_offline(path: Path) -> list[Evidence]:
    raw = json.loads(path.read_text())
    return [Evidence(**a) for a in raw]


def _load_online(urns: list[str]) -> list[Evidence]:
    from .evidence import collect_from_datahub

    gms = os.getenv("DATAHUB_GMS_URL", "http://localhost:8080")
    token = os.getenv("DATAHUB_TOKEN", "")
    return [collect_from_datahub(gms, token, u) for u in urns]


def _print_leaderboard(results) -> None:
    cov = coverage(results)
    print("\n" + "=" * 68)
    print("CATALOG KNOWLEDGE LEADERBOARD  (worst first)")
    print("=" * 68)
    for r in leaderboard(results):
        print(f"  {r.status.value:<16} {r.urn}")
        print(f"      └ {r.reasons[0]}")
    print("-" * 68)
    print(
        f"  coverage: {cov['healthy_pct']}% healthy  |  "
        f"🔴 {cov['critical']}  🟡 {cov['needs_review']}  🟠 {cov['forgotten']}  🟢 {cov['healthy']}"
    )
    print("=" * 68 + "\n")


def _print_trace(ev: Evidence, inv) -> None:
    print(f"INVESTIGATION — {ev.urn}")
    for step in inv.rationale:
        print(f"  • {step}")
    if inv.contradictions:
        print("  ⚠️  ZOMBIE — documentation contradicts evidence:")
        for c in inv.contradictions:
            print(f"       - {c}")
    print(f"  → action: {inv.action.upper()}  (confidence: {inv.confidence})")
    print(f"  → proposed: {inv.proposed_description}\n")


def main() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:  # noqa: BLE001
        pass

    ap = argparse.ArgumentParser(description="The Data Necromancer")
    ap.add_argument("--assets", type=Path, help="Offline JSON catalog of assets")
    ap.add_argument("--online", action="store_true", help="Collect evidence from DataHub")
    ap.add_argument("--urns", nargs="*", default=[], help="Asset URNs (with --online)")
    ap.add_argument("--write", action="store_true", help="Apply write-back (default: dry run)")
    ap.add_argument("--trace-all", action="store_true", help="Print an investigation trace for every asset")
    args = ap.parse_args()

    evidences = _load_online(args.urns) if args.online else _load_offline(args.assets)

    investigations = {ev.urn: investigate(ev) for ev in evidences}
    results = [classify(ev, investigations[ev.urn]) for ev in evidences]

    _print_leaderboard(results)

    # Drill into the worst asset (the demo beat) — or all with --trace-all.
    ordered = leaderboard(results)
    focus = ordered if args.trace_all else ordered[:1]
    ev_by_urn = {ev.urn: ev for ev in evidences}
    for r in focus:
        _print_trace(ev_by_urn[r.urn], investigations[r.urn])

    # Write back (gate: only action=="write" is applied).
    from .writeback import WriteBack, WriteBackResult

    wb = WriteBack(
        gms_url=os.getenv("DATAHUB_GMS_URL", ""),
        token=os.getenv("DATAHUB_TOKEN", ""),
        dry_run=not args.write,
    )
    res = WriteBackResult(dry_run=not args.write)
    health_by_urn = {r.urn: r for r in results}
    for ev in evidences:
        wb.apply(ev, investigations[ev.urn], health_by_urn[ev.urn], res)

    print(
        f"\nSummary: {len(res.written)} written, "
        f"{len(res.queued_for_review)} queued for review, {len(res.skipped)} skipped."
    )


if __name__ == "__main__":
    main()
