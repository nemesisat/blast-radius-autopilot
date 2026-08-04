"""Guard K — every file the docs cite as evidence must actually exist.

The docs make claims and cite artifacts as the evidence for them. A citation that does not
resolve is a claim with nothing behind it — the exact failure mode this project exists to
avoid. (It happened for real: `LIMITATIONS.md` was deleted by an `rsync --delete` while
README.md and PROGRESS.md both still linked to it.)

RESOLUTION RULES, in order. A reference passes if any of these finds it:
  1. exact path, relative to the citing doc, to blast-radius-autopilot/, or to the repo root
  2. brace expansion — `out/x.{html,json}` is checked as each of its members
  3. basename anywhere in the repo — so prose that names `run.py` or `01_orders.png`
     without a directory still counts as resolved

Rule 3 is deliberately generous. This guard is for *dangling evidence*, not for prose style;
flagging every backticked filename that lacks a full path would bury the real failures. What
it will still catch: a cited artifact that exists nowhere under the repo at all.

Run:  python blast-radius-autopilot/scripts/check_referenced_paths.py [-v]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
BRA = HERE.parents[1]
ROOT = BRA.parent

DOCS = [
    ROOT / "README.md", ROOT / "PROGRESS.md", ROOT / "BACKLOG.md",
    ROOT / "EXAMPLES.md", ROOT / "AGENTS.md", ROOT / "BUILD_GUIDE.md",
    ROOT / "SETUP.md",
    BRA / "README.md", BRA / "TEST_GUIDE.md", BRA / "LIMITATIONS.md",
    BRA / "DESIGN.md", BRA / "MCP_EVIDENCE.md", BRA / "LIVE_DATAHUB_EVIDENCE.md",
    BRA / "demo" / "demo_script.md", BRA / "out" / "README.md",
]

EXTS = (".py", ".md", ".json", ".yaml", ".yml", ".html", ".txt", ".png", ".sql",
        ".toml", ".cfg", ".csv")

SKIP = re.compile(
    r"^(https?:|file://|urn:|mailto:|#|/)"      # URLs, URNs, anchors, absolute paths
    r"|[*?\[\]]"                                # globs ANYWHERE in the token
    r"|[<>]"                                     # <placeholders> ANYWHERE
    r"|\.\.\.|\$\{|\{\{"                         # ellipses, templating
    r"|^_"                                       # line-wrap fragments like `_step2.txt`
)

PATTERNS = [
    re.compile(r"\[[^\]]*\]\(([^)\s]+)\)"),      # [text](path)
    re.compile(r"`([^`\s]+)`"),                  # `path`
    re.compile(r"(?<![\w/`.<-])((?:[\w.-]+/)+[\w.-]+\.\w{2,5})(?![\w/])"),  # bare a/b/c.ext
]

BRACE = re.compile(r"^(.*)\{([^}]+)\}(.*)$")

# Tokens that are path-shaped but are NOT evidence citations. Each needs a reason, so the
# allowlist can be audited instead of quietly absorbing real failures.
ALLOWLIST: dict[str, str] = {
    # Named in PROGRESS.md's 2026-07-23 entry, which now states explicitly that these four
    # files no longer exist (the 2026-07-25 real-datapack capture replaced slots 01-04).
    "01_fct_orders_overview.png": "historical name, documented as replaced",
    "02_fct_orders_properties.png": "historical name, documented as replaced",
    "03_fct_orders_documentation.png": "historical name, documented as replaced",
    "04_downstream_impacted.png": "historical name, documented as replaced",
    # A value inside a quoted test assertion (`unmapped_files == ['models/rpt_orphan.sql']`),
    # not a file on disk — the fixture lives in a pytest tmp dir.
    "models/rpt_orphan.sql": "test-fixture path quoted in an assertion",
    # An output path in a sample command (`--html out/report.html`), i.e. a file the reader
    # would create by running it, not an artifact being cited.
    "out/report.html": "output path in an example command",
    "report.html": "documented in out/README.md as never regenerated",
    # An upstream DataHub file the `datapack --help` crash referred to; not ours.
    "DATAPACK_AGENT_CONTEXT.md": "upstream DataHub file, not an artifact of this repo",
    # Deliberately OUTSIDE the repo: it lives in ~/bra to warn anyone who opens that stale
    # scratch tree. Tracking it here would defeat its purpose.
    "SCRATCH-DO-NOT-SYNC-FROM-HERE.md": "intentionally outside the repo, in ~/bra",
}


def build_index() -> dict[str, list[Path]]:
    """basename -> every file with that name in the repo (excluding heavy/ignored dirs)."""
    idx: dict[str, list[Path]] = {}
    skip_dirs = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules"}
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part in skip_dirs for part in p.parts):
            continue
        idx.setdefault(p.name, []).append(p)
    return idx


def expand(tok: str) -> list[str]:
    m = BRACE.match(tok)
    if not m:
        return [tok]
    pre, inner, post = m.groups()
    return [f"{pre}{part.strip()}{post}" for part in inner.split(",")]


def is_candidate(tok: str) -> bool:
    if SKIP.search(tok):
        return False
    # A bare extension fragment (".md") is not a reference.
    if tok.startswith("."):
        return False
    return tok.endswith(EXTS) or (("/" in tok) and tok.rsplit("/", 1)[-1].endswith(EXTS))


def resolve(tok: str, doc: Path, idx: dict[str, list[Path]]) -> bool:
    tok = tok.split("#")[0].rstrip(".,;:)")
    if tok in ALLOWLIST:
        return True
    for base in (doc.parent, BRA, ROOT):
        if (base / tok).exists():
            return True
    return bool(idx.get(Path(tok).name))


def main() -> int:
    verbose = "-v" in sys.argv
    idx = build_index()
    missing: list[tuple[str, str]] = []
    per_doc: dict[str, int] = {}
    checked = 0

    for doc in DOCS:
        if not doc.exists():
            missing.append((str(doc), "<the citing doc itself is missing>"))
            continue
        text = doc.read_text(errors="replace")
        toks: set[str] = set()
        for pat in PATTERNS:
            for m in pat.finditer(text):
                toks.update(expand(m.group(1)))
        rel = str(doc.relative_to(ROOT))
        n = 0
        for tok in sorted(toks):
            if not is_candidate(tok):
                continue
            n += 1
            checked += 1
            if not resolve(tok, doc, idx):
                missing.append((rel, tok))
        per_doc[rel] = n

    print(f"Checked {checked} path references across {len(per_doc)} docs "
          f"({len(idx)} distinct filenames indexed).\n")
    if verbose:
        for rel, n in sorted(per_doc.items()):
            print(f"   {n:>4} refs   {rel}")
        print()

    if missing:
        print(f"  {len(missing)} UNRESOLVED reference(s) — a cited artifact exists nowhere:")
        for rel, tok in missing:
            print(f"    {rel:<44} -> {tok}")
        return 1
    print("  All cited paths resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
