"""Write-back — contribute the assessment to the graph (approve-before-write).

MCP tool mapping (enable TOOLS_IS_MUTATION_ENABLED=true on the server):
    set_status        -> add_structured_properties   (blast_radius_* on the target)
    tag_pending       -> add_tags                     ("pending-schema-change" + impacted tags)
    save_assessment   -> save_document                (a LINK + title, see below)
    annotate          -> update_description           (a one-line pending-change footer)

WHAT ACTUALLY LANDS IN THE CATALOG, EXACTLY (B18.3)
    Checked against the shipped aspect schema, not assumed:

        InstitutionalMemoryMetadata fields = {url, description, createStamp,
                                              updateStamp, settings}

    There is **no document-body field**. On DataHub OSS the `institutionalMemory`
    aspect can therefore hold a *reference* to the Impact Assessment — a URL plus its
    title — and nothing more. It cannot hold the assessment markdown, and this module
    must never imply that it does. (On DataHub Cloud a real `save_document` exists;
    that path is not what runs here.)

    So the write-back is split honestly:

        stored IN DataHub   structured properties (blast_radius_*), tags, a one-line
                            pending-change footer on editableProperties.description,
                            and an institutional-memory LINK (url + title)
        stored OUTSIDE      the full Impact Assessment markdown, written to
                            `assessment_dir` (default `out/`) as ASSESSMENT.md — which
                            is exactly what that link points at

    `plan_mutations()` writes that file while planning, deliberately: a link is only
    honest if its target exists before the link is emitted.

Gating (a standing rule): recording an *assessment* is additive and safe, so it
auto-writes when --write is given. But when the catalog is marked `require_review`
(regulated data — see EXAMPLES healthcare/finance) or the report has only
low-confidence signal, every mutation is QUEUED for a human instead of applied.
`dry_run` prints intended mutations without touching the catalog.

Structured properties must be *defined once* before values can be set
(docs/api/tutorials/structured-properties); `ensure_property_definitions()` does
that on a live instance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .assessment import AssessmentDoc, build_assessment
from .schema import ImpactReport

# Where the assessment BODY goes, since the catalog aspect cannot hold it.
DEFAULT_ASSESSMENT_DIR = Path("out")


@dataclass
class Mutation:
    tool: str                 # add_structured_properties | add_tags | save_document | update_description
    target_urn: str
    summary: str
    payload: dict = field(default_factory=dict)
    auto: bool = True         # False -> queued for human review
    # WHY it is queued, machine-readable (B19.3). "" when auto. A gate whose reason a
    # reviewer cannot see is a gate they cannot act on.
    queue_reason: str = ""


@dataclass
class WriteBackResult:
    """What actually happened, not what was intended (B17.4).

    `total` is the denominator: every mutation the run planned. Each one then lands in
    exactly ONE outcome bucket, and the buckets are the only thing any surface is
    allowed to print:

        written             emitted to the catalog and the emit returned successfully
        queued_for_review   deliberately NOT applied — a human must approve it
        failed              attempted and raised; the catalog does not have it
        planned             not attempted because this was a dry run
        skipped             not attempted for any other reason

    The distinction between `planned` and `written` is the whole point: the previous
    implementation appended to `written` *before* checking `dry_run`, so a dry run
    that touched nothing reported "6 written". A dry run must never say "written".
    """

    dry_run: bool
    total: int = 0
    # B19.6 — WHO applied it, split at the source. A machine decision and a human
    # approval are different events with different accountability, and no surface may
    # report one as the other. `written` is their union, never a bucket of its own.
    written_auto: list[str] = field(default_factory=list)
    written_human_approved: list[str] = field(default_factory=list)
    queued_for_review: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    planned: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    # Why the queue was queued (B19.3), and the approval it was applied under (B19.4).
    queue_reasons: list[str] = field(default_factory=list)
    manifest_path: str | None = None
    manifest_id: str = ""
    approver: str | None = None
    # B20.3 — the approval audit that goes INTO the graph. `approved_at` and
    # `verification_status_at_approval` are recorded at approval time (the verdict a
    # human actually consented to), and `audit_status` says whether the trail reached
    # the catalog: "" (no approval happened) | emitted | failed | planned (dry run).
    approved_at: str = ""
    verification_status_at_approval: str = ""
    audit_status: str = ""
    audit_error: str = ""
    audit_properties: dict = field(default_factory=dict)

    @property
    def written(self) -> list[str]:
        """Everything that reached the catalog, however it was authorised. Read-only:
        callers must append to the bucket that names the authorising path."""
        return [*self.written_auto, *self.written_human_approved]

    @property
    def applied_by(self) -> str:
        if self.written_human_approved and self.written_auto:
            return "mixed"          # cannot happen today; reported honestly if it ever does
        if self.written_human_approved:
            return "human-approved"
        if self.written_auto:
            return "auto"
        return "none"

    def counts(self) -> dict[str, int]:
        return {
            "total": self.total,
            "written": len(self.written),
            "written_auto": len(self.written_auto),
            "written_human_approved": len(self.written_human_approved),
            "queued_for_review": len(self.queued_for_review),
            "failed": len(self.failed),
            "planned": len(self.planned),
            "skipped": len(self.skipped),
        }

    def reconciles(self) -> bool:
        """Every planned mutation is accounted for exactly once. Asserted in tests on
        every path — a summary whose buckets do not add up to `total` is hiding a
        mutation. `written` is excluded from the sum because it is a derived union."""
        c = self.counts()
        return (c["written_auto"] + c["written_human_approved"] + c["queued_for_review"]
                + c["failed"] + c["planned"] + c["skipped"]) == self.total

    def summary_line(self) -> str:
        """The one string every surface prints. Derived from the counters, so no
        surface can invent a number — and the two write paths are always both shown,
        so a zero is as explicit as a non-zero."""
        c = self.counts()
        who = f" by {self.approver}" if self.approver else ""
        return (f"{c['planned']} planned, {c['written_auto']} written (auto), "
                f"{c['written_human_approved']} written (human-approved{who}), "
                f"{c['queued_for_review']} queued, {c['failed']} failed, "
                f"{c['skipped']} skipped")

    def queue_reason_line(self) -> str:
        return ", ".join(dict.fromkeys(self.queue_reasons)) or ""

    def audit_line(self) -> str:
        """What the graph now records about the approval — or why it does not (B20.3).

        Kept out of `summary_line()` deliberately: that line accounts for the approved
        MUTATIONS, and the audit record is not one of them. Conflating the two would
        make the write counters stop reconciling with `total`.
        """
        if not self.audit_status:
            return ""
        c = self.counts()
        trail = (f"approved_by={self.approver}, at={self.approved_at}, "
                 f"manifest={self.manifest_id}, "
                 f"verification_at_approval={self.verification_status_at_approval}, "
                 f"writes={c['written_human_approved']}, failures={c['failed']}")
        return {
            "emitted": f"Approval audit recorded in the catalog: {trail}",
            "failed": f"Approval audit NOT recorded — {self.audit_error} ({trail})",
            "planned": f"Approval audit not recorded (dry run) — would be: {trail}",
        }.get(self.audit_status, f"Approval audit {self.audit_status}: {trail}")

    def _p(self, prefix: str, m: Mutation) -> None:
        tag = "[dry-run] would " if self.dry_run else "[write] "
        print(f"{tag}{prefix}: {m.tool} on {m.target_urn} — {m.summary}")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80] or "assessment"


def persist_assessment_body(assessment: AssessmentDoc, report: ImpactReport,
                            assessment_dir: Path | str | None = None) -> Path:
    """Write the FULL assessment markdown where it can actually live, and return the path.

    B18.3. The catalog aspect this links from stores `url` + `description` only, so the
    document body has to live somewhere else or not at all. It lives here, and the
    institutional-memory link points at exactly this file — so the link never dangles
    and no surface has to pretend the catalog is holding the text.
    """
    d = Path(assessment_dir) if assessment_dir is not None else DEFAULT_ASSESSMENT_DIR
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"ASSESSMENT-{_slug(report.change.describe())}.md"
    path.write_text(assessment.markdown)
    return path


def plan_mutations(report: ImpactReport, assessment: AssessmentDoc, require_review: bool = False,
                   verification=None, assessment_dir: Path | str | None = None) -> list[Mutation]:
    """The intended catalog mutations for an assessment.

    One deliberate side effect (B18.3): the full assessment body is written to
    `assessment_dir` here, because the `save_document` mutation below is a LINK to it
    and a link planned before its target exists would be a dangling reference. Nothing
    else here touches anything — this remains safe to dry-run.

    Fails closed. A mutation is `auto` ONLY when a static verification returned PASS
    for this exact change, the catalog is not `require_review`, and the impact
    assessment left nothing unresolved. Anything else is queued with a machine-readable
    `queue_reason`:

        not_verified            no verification was run — nothing was proven  (B19.3)
        verification_review_required / verification_fail                      (B19.3)
        require_review          regulated catalog (healthcare / finance)
        unresolved_impact       unassessed or unattributable consumers  (B15 / B17.1)

    A queued run is not a dead end: `approval.build_manifest()` turns a
    REVIEW_REQUIRED queue into something a human can approve. A FAIL never can be.
    """
    if not report.target_urn:
        return []
    body_path = persist_assessment_body(assessment, report, assessment_dir).resolve()
    body_url = body_path.as_uri()
    # THE GATE (B19.3). Auto-write requires a PASS — positively, not by absence of a
    # failure. The previous rule was `verification is not None and not auto_applicable`,
    # which let a run that had *never verified anything* write to the catalog: absence
    # of evidence was being read as permission. Every refusal carries a reason code so
    # a reviewer knows which of the three gates fired.
    status = getattr(verification, "status", None)
    # EVERY applicable gate, in "what must change first" order — not just the first one
    # that fired. A reviewer who only sees `not_verified` on a regulated catalog would
    # run --verify, get a PASS, and be surprised it still queues.
    gates: list[str] = []
    if verification is None:
        gates.append("not_verified")
    elif status != "PASS":
        gates.append(f"verification_{str(status).lower()}")
    if require_review:
        gates.append("require_review")            # regulated catalog
    if report.review_required():
        gates.append("unresolved_impact")         # B15 coverage / B17.1 ambiguity
    queue_reason = "+".join(gates)
    auto = not queue_reason
    muts: list[Mutation] = [
        Mutation(
            "add_structured_properties",
            report.target_urn,
            f"blast_radius_status=pending-change, risk={assessment.properties['blast_radius_risk']}",
            payload=assessment.properties,
            auto=auto,
            queue_reason=queue_reason,
        ),
        Mutation(
            "add_tags",
            report.target_urn,
            "tag 'pending-schema-change'",
            payload={"tags": ["pending-schema-change"]},
            auto=auto,
            queue_reason=queue_reason,
        ),
        Mutation(
            "save_document",
            report.target_urn,
            # Says exactly what the aspect stores: a link + a title. The body is a file.
            f"add institutional-memory link '{assessment.title}' -> {body_path} "
            f"(catalog stores the link + title only; the full assessment body is that file)",
            payload={"url": body_url, "description": assessment.title,
                     "body_path": str(body_path), "title": assessment.title},
            auto=auto,
            queue_reason=queue_reason,
        ),
        Mutation(
            "update_description",
            report.target_urn,
            "append pending-change footer",
            payload={"footer": f"⚠️ {assessment.summary} "
                               f"(full Blast Radius Assessment linked in institutional memory)"},
            auto=auto,
            queue_reason=queue_reason,
        ),
    ]
    # Tag each impacted downstream asset.
    for v in report.assets_impacted():
        muts.append(
            Mutation(
                "add_tags",
                v.asset_urn,
                f"tag 'impacted-by-upstream-change' ({v.verdict.value})",
                payload={"tags": ["impacted-by-upstream-change", f"impact-{v.verdict.value.lower()}"]},
                auto=auto,
                queue_reason=queue_reason,
            )
        )
    return muts


class WriteBack:
    def __init__(self, gms_url: str = "", token: str = "", dry_run: bool = True,
                 require_review: bool = False, assessment_dir=None, manifest_dir=None):
        self.gms_url, self.token, self.dry_run, self.require_review = gms_url, token, dry_run, require_review
        # Where the assessment BODY is persisted, since the catalog aspect holds only a
        # link to it (B18.3).
        self.assessment_dir = assessment_dir
        # Where approval manifests are written / read (B19.4).
        self.manifest_dir = manifest_dir
        self._graph = None

    def run(self, report: ImpactReport, fixes: list | None = None, now=None,
            verification=None) -> tuple[WriteBackResult, AssessmentDoc]:
        """Execute the plan and report what actually happened.

        A mutation reaches `written` ONLY after `_emit()` returns without raising.
        On a dry run nothing is attempted at all, so every auto mutation is `planned`.

        The assessment is built TWICE on purpose. The first copy is what gets written
        into the catalog, and it carries no write-back counters — a document cannot
        honestly report the outcome of the write that saved it. The copy returned to
        the caller (for the CLI summary, HTML, and PR comment) does carry them.
        """
        now = now or datetime.now(timezone.utc)   # pin it: both copies must agree
        planned_doc = build_assessment(report, fixes, now=now, verification=verification)
        mutations = plan_mutations(report, planned_doc, require_review=self.require_review,
                                   verification=verification,
                                   assessment_dir=self.assessment_dir)
        body = next((m.payload["body_path"] for m in mutations
                     if m.tool == "save_document"), None)
        if body:
            print(f"Assessment body -> {body}  "
                  f"(the catalog stores a link + title to it, not the text)")
        res = WriteBackResult(dry_run=self.dry_run, total=len(mutations))
        for m in mutations:
            mid = f"{m.tool}:{m.target_urn}"
            if not m.auto:
                res._p(f"QUEUE for review ({m.queue_reason})", m)
                res.queued_for_review.append(mid)
                res.queue_reasons.append(m.queue_reason)
                continue
            res._p("apply", m)
            if self.dry_run:
                # Nothing was attempted, so nothing may be reported as written.
                res.planned.append(mid)
                continue
            self._emit_into(m, mid, res, res.written_auto)
        # B19.4 — a queued REVIEW_REQUIRED run is not a dead end. Offer the route.
        self._maybe_write_manifest(report, verification, mutations, res, now)
        # Printed here, from the counters, so no caller can restate it differently.
        print(f"Summary: {res.summary_line()}."
              + ("  (dry run — nothing was written)" if self.dry_run else ""))
        if res.queued_for_review:
            print(f"  queued because: {res.queue_reason_line()}")
        return res, build_assessment(report, fixes, now=now, verification=verification,
                                     writeback=res)

    def _emit_into(self, m: Mutation, mid: str, res: WriteBackResult,
                   bucket: list[str]) -> None:
        """Emit one mutation and file the outcome in `bucket` (auto or human-approved).

        `bucket` is passed in rather than inferred, so the authorising path is decided
        by the caller that knows it and can never be guessed after the fact.
        """
        try:
            self._emit(m)
        except Exception as e:  # noqa: BLE001
            # Keep going — one bad aspect must not abort the rest — but record the
            # failure honestly instead of counting it as a write.
            print(f"    ! FAILED {m.tool} on {m.target_urn}: {e}")
            res.failed.append({
                "mutation": mid, "tool": m.tool, "target_urn": m.target_urn,
                "error": str(e),
            })
        else:
            bucket.append(mid)

    def _maybe_write_manifest(self, report, verification, mutations, res, now) -> None:
        from .approval import build_manifest, manifest_path_for, render_manifest_md

        manifest = build_manifest(report, verification, mutations,
                                  manifest_dir=self.manifest_dir or DEFAULT_ASSESSMENT_DIR,
                                  now=now)
        if manifest is None:
            return
        path = manifest_path_for(report, self.manifest_dir or DEFAULT_ASSESSMENT_DIR)
        res.manifest_path = str(path)
        res.manifest_id = manifest.manifest_id
        path.with_suffix(".md").write_text(render_manifest_md(manifest))
        print(f"Approval manifest -> {path}  ({len(manifest.mutations)} mutation(s) await a "
              f"human; apply with --approve <that file> --approver <you>)")

    def approve(self, manifest_path, report: ImpactReport, fixes: list | None = None,
                now=None, verification=None, approver: str | None = None,
                ) -> tuple[WriteBackResult, AssessmentDoc]:
        """Apply EXACTLY the mutations a human approved in `manifest_path` (B19.4).

        Refuses — applying nothing — unless the approval still describes what would
        happen: the verification must be REVIEW_REQUIRED (a **FAIL is never approvable**,
        by this or any other route), the manifest must be unconsumed, and its
        fingerprint must still match the change, the verdict and the queued set. The
        approver is supplied, never inferred.

        The manifest is burned only AFTER the mutations are applied, so a crash
        mid-apply leaves the approval usable rather than silently spending it.
        """
        from .approval import load_manifest, mark_consumed, validate_approval

        now = now or datetime.now(timezone.utc)
        manifest = load_manifest(manifest_path)
        planned_doc = build_assessment(report, fixes, now=now, verification=verification)
        mutations = plan_mutations(report, planned_doc, require_review=self.require_review,
                                   verification=verification,
                                   assessment_dir=self.assessment_dir)
        approved = validate_approval(manifest, report, verification, mutations, approver)

        by_id = {f"{m.tool}:{m.target_urn}": m for m in mutations}
        res = WriteBackResult(dry_run=self.dry_run, total=len(approved),
                              manifest_path=str(manifest_path),
                              manifest_id=manifest.manifest_id, approver=approver,
                              # B20.3 — the verdict the human consented to, taken from
                              # the manifest rather than recomputed. `validate_approval`
                              # has already refused any drift between the two, so this
                              # cannot silently record a verdict nobody approved.
                              approved_at=now.isoformat(timespec="seconds"),
                              verification_status_at_approval=manifest.verification_status)
        print(f"APPROVED by {approver} — manifest {manifest.manifest_id} "
              f"({len(approved)} mutation(s), verification {manifest.verification_status})")
        for qm in approved:
            m = by_id.get(qm.mutation_id)
            if m is None:                      # unreachable: the fingerprint covers this
                res.skipped.append(qm.mutation_id)
                continue
            res._p("apply (human-approved)", m)
            if self.dry_run:
                res.planned.append(qm.mutation_id)
                continue
            self._emit_into(m, qm.mutation_id, res, res.written_human_approved)
        # B20.3 — contribute the approval trail to the graph. AFTER the loop, because
        # two of its six fields are outcomes; BEFORE the burn, so the manifest is still
        # spendable if this or the burn dies.
        self._record_approval_audit(report, planned_doc, res)
        if not self.dry_run:
            mark_consumed(manifest, manifest_path, approver, now=now)
            print(f"  manifest {manifest.manifest_id} consumed — approvals are single-use")
        print(f"Summary: {res.summary_line()}."
              + ("  (dry run — nothing was written)" if self.dry_run else ""))
        if res.audit_line():
            print(f"  {res.audit_line()}")
        return res, build_assessment(report, fixes, now=now, verification=verification,
                                     writeback=res)

    def _record_approval_audit(self, report: ImpactReport, planned_doc: AssessmentDoc,
                               res: WriteBackResult) -> None:
        """Write WHO approved WHAT, and how it turned out, into the catalog (B20.3).

        Until now the approval trail lived only in a local `WriteBackResult` and a
        manifest file on the approver's disk. The catalog — the thing every other human
        looks at — recorded that the dataset had a pending change, and nothing about who
        consented to writing it. This puts the accountability in the graph itself.

        THREE THINGS THIS DELIBERATELY IS NOT:

        1. *Not part of the approved set.* The manifest is written before the approval
           exists, so it cannot list a record OF that approval. Rather than quietly
           enlarging an approved mutation's payload — which would make the emitted write
           differ from the payload summary the human read — this is a separate, named
           event, disclosed in the manifest the approver signs off. `written_human_approved`
           therefore still equals exactly the approved set, and `reconciles()` still holds
           over `total`.
        2. *Not counted as a write.* It is provenance about the approval, not one of the
           mutations the approval authorised. It gets `audit_status` instead of a bucket.
        3. *Not silent when it fails.* An audit trail that can vanish while the run still
           reports a clean approval is the same class of untruth B17.4 removed from the
           write counters.

        The payload is the planned properties PLUS the audit fields, because a
        `structuredProperties` emit REPLACES the aspect: sending the six audit fields
        alone would delete the assessment we just wrote. This is a superset, so it is
        also idempotent with the mutation that preceded it.
        """
        from .assessment import approval_audit_properties

        audit = approval_audit_properties(res)
        if not audit or not report.target_urn:
            return
        res.audit_properties = dict(audit)
        m = Mutation(
            "add_structured_properties",
            report.target_urn,
            f"record the approval audit (approved_by={res.approver}, "
            f"manifest={res.manifest_id})",
            payload={**planned_doc.properties, **audit},
            auto=False,
        )
        if self.dry_run:
            res.audit_status = "planned"
            return
        try:
            self._emit(m)
        except Exception as e:  # noqa: BLE001
            # The mutations may well have landed; the record of who authorised them did
            # not. Say so — do not report an approval as fully recorded.
            res.audit_status, res.audit_error = "failed", str(e)
            print(f"    ! FAILED to record the approval audit on {report.target_urn}: {e}")
        else:
            res.audit_status = "emitted"

    # --- live emit (SDK; MCP equivalents in module docstring) --------------
    @property
    def graph(self):
        """The DataHub client, built on FIRST USE rather than at construction.

        Since B19.3 a live-mode run can legitimately emit nothing — every mutation may
        be queued because no verification PASSed — and demanding GMS credentials to
        reach that conclusion is wrong. `--loop --write` is the clearest case: it never
        verifies, so it can only ever queue, and it should not need a token to say so.
        """
        if self._graph is None:
            from datahub.ingestion.graph.client import DataHubGraph, DatahubClientConfig

            self._graph = DataHubGraph(
                DatahubClientConfig(server=self.gms_url, token=self.token))
        return self._graph

    def _emit(self, m: Mutation) -> None:
        """Emit one mutation. Raises on failure — deliberately.

        This used to swallow its own exceptions and print a warning, which let a
        rejected live mutation be counted as written. Failure information belongs to
        the caller, which is the only place that knows how to account for it.
        """
        if m.tool == "update_description":
            self._append_description(m.target_urn, m.payload["footer"])
        elif m.tool == "add_tags":
            self._add_tags(m.target_urn, m.payload["tags"])
        elif m.tool == "save_document":
            self._save_document(m.target_urn, m.payload["description"], m.payload["url"])
        elif m.tool == "add_structured_properties":
            self._set_structured_properties(m.target_urn, m.payload)
        else:
            raise ValueError(f"unknown mutation tool: {m.tool}")

    def _append_description(self, urn: str, footer: str) -> None:
        from datahub.emitter.mcp import MetadataChangeProposalWrapper
        from datahub.metadata.schema_classes import EditableDatasetPropertiesClass

        aspect = self.graph.get_aspect(urn, EditableDatasetPropertiesClass) or EditableDatasetPropertiesClass()
        base = (aspect.description or "").split("\n\n⚠️")[0]
        aspect.description = f"{base}\n\n{footer}"
        self.graph.emit(MetadataChangeProposalWrapper(entityUrn=urn, aspect=aspect))

    def _add_tags(self, urn: str, tags: list[str]) -> None:
        from datahub.emitter.mcp import MetadataChangeProposalWrapper
        from datahub.metadata.schema_classes import GlobalTagsClass, TagAssociationClass

        existing = self.graph.get_aspect(urn, GlobalTagsClass) or GlobalTagsClass(tags=[])
        have = {t.tag for t in existing.tags}
        for t in tags:
            tag_urn = f"urn:li:tag:{t}"
            if tag_urn not in have:
                existing.tags.append(TagAssociationClass(tag=tag_urn))
        self.graph.emit(MetadataChangeProposalWrapper(entityUrn=urn, aspect=existing))

    def _save_document(self, urn: str, title: str, url: str) -> None:
        """Attach an institutional-memory LINK (url + title). B18.3: this aspect has no
        body field, so the assessment text is NOT sent here — `url` points at the file
        `persist_assessment_body()` wrote. On DataHub Cloud, a real `save_document` exists.
        """
        from datetime import datetime, timezone

        from datahub.emitter.mcp import MetadataChangeProposalWrapper
        from datahub.metadata.schema_classes import (
            AuditStampClass,
            InstitutionalMemoryClass,
            InstitutionalMemoryMetadataClass,
        )

        stamp = AuditStampClass(
            time=int(datetime.now(timezone.utc).timestamp() * 1000),
            actor="urn:li:corpuser:blast-radius-autopilot",
        )
        aspect = self.graph.get_aspect(urn, InstitutionalMemoryClass) or InstitutionalMemoryClass(elements=[])
        aspect.elements = [e for e in aspect.elements if e.url != url]  # idempotent
        aspect.elements.append(
            InstitutionalMemoryMetadataClass(url=url, description=title, createStamp=stamp)
        )
        self.graph.emit(MetadataChangeProposalWrapper(entityUrn=urn, aspect=aspect))

    def ensure_property_definitions(self, props: dict) -> None:
        """Define the blast_radius_* structured properties once (idempotent).

        Structured-property *values* can only be set after the property is defined
        (docs/api/tutorials/structured-properties). Safe to call before each write.
        """
        from datahub.emitter.mcp import MetadataChangeProposalWrapper
        from datahub.metadata.schema_classes import StructuredPropertyDefinitionClass

        for key in props:
            prop_urn = f"urn:li:structuredProperty:{key}"
            defn = StructuredPropertyDefinitionClass(
                qualifiedName=key,
                displayName=key.replace("_", " ").title(),
                valueType="urn:li:dataType:datahub.string",
                entityTypes=["urn:li:entityType:datahub.dataset"],
                cardinality="SINGLE",
            )
            self.graph.emit(MetadataChangeProposalWrapper(entityUrn=prop_urn, aspect=defn))

    def _set_structured_properties(self, urn: str, props: dict) -> None:
        from datahub.emitter.mcp import MetadataChangeProposalWrapper
        from datahub.metadata.schema_classes import (
            StructuredPropertiesClass,
            StructuredPropertyValueAssignmentClass,
        )

        self.ensure_property_definitions(props)  # define-once before setting values
        assignments = [
            StructuredPropertyValueAssignmentClass(
                propertyUrn=f"urn:li:structuredProperty:{k}", values=[str(v)]
            )
            for k, v in props.items()
        ]
        self.graph.emit(
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=StructuredPropertiesClass(properties=assignments))
        )
