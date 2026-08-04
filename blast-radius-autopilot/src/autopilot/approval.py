"""B19.4 / B19.5 — the human-approval path, and the line it must never cross.

`gated` has to mean "needs a human", not "impossible". B16–B18 built a verifier that
correctly refuses to auto-apply an unproven migration, but refusal alone leaves a
reviewer with nowhere to go: they can read the assessment and then have to reproduce
the mutations by hand, which is exactly the error-prone step the tool exists to remove.

An APPROVAL MANIFEST is the way through. It is the queued mutation set, written down,
so that a human approves *a specific list of writes against a specific verdict of a
specific change* — never "this migration, generally".

Four properties, each of which is a test:

    EMITTED ONLY ON REVIEW_REQUIRED
        A PASS needs no approval (it already earned the write). A **FAIL is never
        approvable by anyone or anything** — no manifest is written, and presenting an
        older manifest while the verification is a FAIL is refused. There is
        deliberately no flag, env var, or parameter anywhere that applies a FAIL.

    BOUND
        The manifest carries a fingerprint over the change, the catalog, the
        verification verdict AND the exact queued mutation set. If any of those differ
        at approval time, the approval no longer describes what would happen, so it is
        refused (`manifest_stale`). An approval cannot be replayed against a different
        change or a mutated queue.

    SINGLE-USE
        Approval is consumed on success. Re-presenting it is refused
        (`already_consumed`), so a stored manifest is not a standing credential.

    ATTRIBUTED
        The approver is supplied by the caller (`--approver`, or `BRA_APPROVER`) and is
        never invented, defaulted, or inferred. No approver, no approval.

The manifest is a plain JSON file: reviewable in a PR, diffable, and greppable. It
contains no secrets — only URNs, tool names and payload *summaries*.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Refusal codes. Stable strings — safe to assert on and to branch a CLI exit code off.
E_NO_MANIFEST = "no_manifest"
E_ALREADY_CONSUMED = "already_consumed"
E_STALE = "manifest_stale"
E_FAIL_NOT_APPROVABLE = "fail_not_approvable"
E_NOT_REVIEW_REQUIRED = "not_review_required"
E_NO_APPROVER = "no_approver"

_MESSAGES = {
    E_NO_MANIFEST: "no approval manifest was found at that path",
    E_ALREADY_CONSUMED: "this approval manifest has already been used — approvals are "
                        "single-use, so a new one must be generated and reviewed",
    E_STALE: "the change, the verification verdict, or the queued mutation set no longer "
             "matches what was approved — this approval does not describe what would "
             "happen now",
    E_FAIL_NOT_APPROVABLE: "the verification FAILED. A failed migration cannot be approved "
                           "by anyone or anything; fix the patch and re-verify",
    E_NOT_REVIEW_REQUIRED: "approval applies only to a REVIEW_REQUIRED verification",
    E_NO_APPROVER: "no approver was supplied — pass --approver or set BRA_APPROVER. An "
                   "approver is never inferred",
}


class ApprovalError(Exception):
    """A refusal, with a machine-readable `code` from the constants above."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        msg = _MESSAGES.get(code, code)
        super().__init__(f"{code}: {msg}" + (f" ({detail})" if detail else ""))


@dataclass
class QueuedMutation:
    """One write a human is being asked to approve, described in full enough terms to
    decide on: what tool, against what URN, doing what."""

    mutation_id: str
    tool: str
    target_urn: str
    payload_summary: str


@dataclass
class ApprovalManifest:
    manifest_id: str
    created_at: str
    change: str
    catalog: str
    verification_status: str
    verification_reasons: list[str]
    fingerprint: str
    mutations: list[QueuedMutation] = field(default_factory=list)
    consumed_at: str | None = None
    approver: str | None = None
    note: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=False)


def _summarise_payload(tool: str, payload: dict) -> str:
    """A short, human-readable description of what the mutation would write.

    Deliberately a SUMMARY: the manifest is meant to be read in a review, and dumping
    the full structured-property blob or an assessment body into it would bury the
    thing being decided.

    TIMESTAMPS ARE EXCLUDED, and that is load-bearing rather than cosmetic. This summary
    is what `fingerprint_for()` binds an approval to, and `blast_radius_assessed_at` /
    `blast_radius_verified_at` change on every run — so including them would bind the
    approval to the CLOCK, and every manifest would be stale the moment it was written.
    An approval must be bound to the decision, not to when it was printed. The manifest
    carries its own `created_at` for the audit trail.
    """
    if tool == "add_tags":
        return "tags: " + ", ".join(payload.get("tags", []))
    if tool == "update_description":
        return "append footer: " + str(payload.get("footer", ""))[:160]
    if tool == "save_document":
        return f"institutional-memory link -> {payload.get('url', '')}"
    if tool == "add_structured_properties":
        keys = sorted(k for k in payload
                      if k.startswith("blast_radius_") and not k.endswith("_at"))
        return f"{len(keys)} structured propert{'y' if len(keys) == 1 else 'ies'}: " + ", ".join(
            f"{k}={payload[k]}" for k in keys[:6]) + (" …" if len(keys) > 6 else "")
    return f"{len(payload)} field(s)"


def queued_from(mutations) -> list[QueuedMutation]:
    """The queued (non-auto) mutations, as manifest entries."""
    return [
        QueuedMutation(
            mutation_id=f"{m.tool}:{m.target_urn}",
            tool=m.tool,
            target_urn=m.target_urn,
            payload_summary=_summarise_payload(m.tool, m.payload),
        )
        for m in mutations if not m.auto
    ]


def fingerprint_for(report, verification, queued: list[QueuedMutation]) -> str:
    """A stable digest over everything the approval is consent to.

    Includes the payload summaries, not just the mutation ids: if the same tool would
    now write *different values* to the same URN, that is not what was approved either.
    """
    h = hashlib.sha256()
    parts = [
        report.change.describe(),
        report.catalog,
        str(report.target_urn),
        getattr(verification, "status", "NONE"),
        "|".join(sorted(getattr(verification, "reasons", []) or [])),
        # sorted so mutation ORDER does not invalidate an approval, but content does
        "|".join(sorted(f"{q.mutation_id}::{q.payload_summary}" for q in queued)),
    ]
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80] or "change"


def manifest_path_for(report, manifest_dir: Path | str) -> Path:
    return Path(manifest_dir) / f"APPROVAL-{_slug(report.change.describe())}.json"


def build_manifest(report, verification, mutations, manifest_dir: Path | str,
                   now: datetime | None = None) -> ApprovalManifest | None:
    """Write an approval manifest for a REVIEW_REQUIRED run, or return None.

    Returns None — and writes NOTHING — for a PASS (no approval needed), a FAIL (never
    approvable), or a run with no verification at all (nothing was assessed, so there is
    no verdict to approve against; re-run with `--verify`).
    """
    status = getattr(verification, "status", None)
    if status != "REVIEW_REQUIRED":
        return None
    queued = queued_from(mutations)
    if not queued:
        return None
    now = now or datetime.now(timezone.utc)
    fp = fingerprint_for(report, verification, queued)
    manifest = ApprovalManifest(
        # Derived from the fingerprint + creation time: two manifests for the same
        # queue at different times are distinct approvals, as they should be.
        manifest_id=hashlib.sha256(
            f"{fp}{now.isoformat()}".encode()).hexdigest()[:16],
        created_at=now.isoformat(timespec="seconds"),
        change=report.change.describe(),
        catalog=report.catalog,
        verification_status=status,
        verification_reasons=list(verification.reasons),
        fingerprint=fp,
        mutations=queued,
        note=("Static verification returned REVIEW_REQUIRED. Approving this manifest applies "
              "exactly the mutations listed above and nothing else. It is single-use and is "
              "bound to this change, this verdict and this queue. No query was executed to "
              "produce it. Approving also RECORDS THE APPROVER — your identity, the "
              "approval time, this manifest id, the verdict you approved against, and how "
              "many writes succeeded or failed — as structured properties on the changed "
              "dataset in DataHub, where anyone with access to the catalog can read them."),
    )
    path = manifest_path_for(report, manifest_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.to_json())
    return manifest


def load_manifest(path: Path | str) -> ApprovalManifest:
    p = Path(path)
    if not p.exists():
        raise ApprovalError(E_NO_MANIFEST, str(p))
    try:
        raw = json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        raise ApprovalError(E_NO_MANIFEST, f"{p}: unreadable ({e})") from e
    muts = [QueuedMutation(**m) for m in raw.pop("mutations", [])]
    return ApprovalManifest(mutations=muts, **raw)


def validate_approval(manifest: ApprovalManifest, report, verification,
                      mutations, approver: str | None) -> list[QueuedMutation]:
    """Raise `ApprovalError` unless this approval may be applied; else return the
    mutations to apply, in manifest order.

    Order of checks is deliberate — the most serious refusal is reported first, so a
    caller presenting a stale manifest against a FAIL is told about the FAIL.
    """
    status = getattr(verification, "status", None)
    # A FAIL is refused before anything else is even considered, so a caller who
    # presents a stale manifest against a failed migration is told about the FAIL.
    if status == "FAIL":
        raise ApprovalError(E_FAIL_NOT_APPROVABLE)
    if not (approver or "").strip():
        raise ApprovalError(E_NO_APPROVER)
    if manifest.consumed_at:
        raise ApprovalError(E_ALREADY_CONSUMED,
                            f"consumed at {manifest.consumed_at} by {manifest.approver}")
    # BINDING. Any drift between what was approved and what is in front of us now is
    # staleness, including a verdict that has since changed — an approval of a
    # REVIEW_REQUIRED queue is not consent to act on some other verdict.
    if manifest.change != report.change.describe():
        raise ApprovalError(E_STALE,
                            f"manifest is for `{manifest.change}`, this run is for "
                            f"`{report.change.describe()}`")
    if manifest.verification_status != status:
        raise ApprovalError(E_STALE, f"manifest verdict {manifest.verification_status}, "
                                     f"current verdict {status}")
    if status != "REVIEW_REQUIRED":
        raise ApprovalError(E_NOT_REVIEW_REQUIRED, f"verification is {status}")
    current = fingerprint_for(report, verification, queued_from(mutations))
    if manifest.fingerprint != current:
        raise ApprovalError(E_STALE, "fingerprint mismatch — the change, verdict or queued "
                                     "mutation set has moved since this was approved")
    # The manifest's own body must match its fingerprint too, so an edited file is
    # caught even when the run it is compared against is unchanged.
    if fingerprint_for(report, verification, manifest.mutations) != manifest.fingerprint:
        raise ApprovalError(E_STALE, "the manifest's mutation list does not match its own "
                                     "fingerprint — it has been edited")
    return list(manifest.mutations)


def mark_consumed(manifest: ApprovalManifest, path: Path | str, approver: str,
                  now: datetime | None = None) -> ApprovalManifest:
    """Burn the manifest: record who approved it and when, and write it back.

    Done AFTER the mutations are applied, so a crash mid-apply leaves the manifest
    usable rather than silently spending an approval that never took effect.
    """
    now = now or datetime.now(timezone.utc)
    manifest.consumed_at = now.isoformat(timespec="seconds")
    manifest.approver = approver
    Path(path).write_text(manifest.to_json())
    return manifest


def render_manifest_md(manifest: ApprovalManifest) -> str:
    """A human-readable view of what is being approved."""
    L = [f"# Approval required — `{manifest.change}`", ""]
    L.append(f"**Manifest** `{manifest.manifest_id}` · created {manifest.created_at}")
    L.append("")
    L.append(f"**Static verification:** {manifest.verification_status} — "
             + ", ".join(f"`{r}`" for r in manifest.verification_reasons))
    L.append("")
    L.append(f"Approving this applies **exactly these {len(manifest.mutations)} "
             f"mutation(s)**, and nothing else:")
    L.append("")
    L.append("| Tool | Target | Would write |")
    L.append("|---|---|---|")
    for m in manifest.mutations:
        L.append(f"| `{m.tool}` | `{m.target_urn}` | {m.payload_summary} |")
    L.append("")
    L.append(f"> {manifest.note}")
    L.append("")
    # B20.3 — spell out the audit fields by name, so the approver can see exactly what
    # is recorded about them before they consent, not afterwards.
    L.append("**What approving records about you** (structured properties on the changed "
             "dataset):")
    L.append("")
    L.append("| Property | Value |")
    L.append("|---|---|")
    L.append("| `blast_radius_approved_by` | the `--approver` you pass — never inferred |")
    L.append("| `blast_radius_approved_at` | when you approved |")
    L.append(f"| `blast_radius_manifest_id` | `{manifest.manifest_id}` |")
    L.append(f"| `blast_radius_verification_status_at_approval` | "
             f"`{manifest.verification_status}` |")
    L.append("| `blast_radius_approved_writes` | how many of the mutations above landed |")
    L.append("| `blast_radius_approved_failures` | how many were attempted and failed |")
    L.append("")
    if manifest.consumed_at:
        L.append(f"**CONSUMED** at {manifest.consumed_at} by `{manifest.approver}`. "
                 f"Approvals are single-use; this one can no longer be applied.")
    else:
        L.append("Apply with:")
        L.append("")
        L.append("```bash")
        L.append("autopilot --catalog <same catalog> --change \"<same change>\" --verify \\")
        L.append("          --approve <this file> --approver you@example.com --write")
        L.append("```")
    return "\n".join(L) + "\n"
