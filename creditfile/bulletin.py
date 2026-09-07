"""Deterministic, versioned preparation bulletin; never imports an LLM client.

Scope is the original FieldKey contract, projected onto the current 24 fields.
No optional flags exist in that contract. Other fields remain in the application.
"""

import copy
import hashlib
import json
import time
from pathlib import Path
from .schemas import FIELD_LABELS, Block, Evidence
from .checks import source_list, usable
from .validation import validate_evidence
from .viewer import source_geometry

POLICY = "preparation-10-v2"
SCOPE = {
    "company_name": ("application", "company_legal_name"),
    "requested_amount": ("application", "requested_amount"),
    "loan_purpose": ("application", "financing_purpose"),
    "duration_months": ("application", "tenor_months"),
    "financial_year": ("financials", "reporting_period"),
    "revenue": ("financials", "revenue"),
    "net_income": ("financials", "net_profit_or_loss"),
    "total_assets": ("financials", "total_assets"),
    "total_liabilities": ("financials", "total_liabilities"),
    "equity": ("financials", "total_equity"),
}
CROSS = {
    "company_match",
    "tax_id_match",
    "currency_match",
    "turnover_match",
    "debt_match",
    "accounting_equation",
    "unit_scale",
}
RESOLUTION_BASIS = "comparison-state-v2"
CHECK_FIELDS = {
    "company_match": {("application", "company_legal_name"), ("financials", "company_legal_name")},
    "tax_id_match": {("application", "tax_id"), ("financials", "tax_id")},
    "currency_match": {("application", "currency"), ("financials", "currency")},
    "unit_scale": {("financials", "unit_scale")},
    "accounting_equation": {
        ("financials", n)
        for n in (
            "total_assets",
            "total_liabilities",
            "total_equity",
            "currency",
            "unit_scale",
            "reporting_period",
        )
    },
}
for _check, _left, _right in [
    ("turnover_match", "declared_annual_turnover", "revenue"),
    ("debt_match", "declared_existing_debt", "total_borrowings"),
]:
    CHECK_FIELDS[_check] = (
        CHECK_FIELDS["company_match"]
        | CHECK_FIELDS["tax_id_match"]
        | CHECK_FIELDS["currency_match"]
        | {
            ("application", _left),
            ("financials", _right),
            ("financials", "unit_scale"),
            ("financials", "reporting_period"),
        }
    )
CHECK_LABELS = dict(
    company_match="Επωνυμία",
    tax_id_match="ΑΦΜ",
    currency_match="Νόμισμα",
    turnover_match="Κύκλος εργασιών",
    debt_match="Δανεισμός",
    accounting_equation="Λογιστική εξίσωση",
    unit_scale="Κλίμακα ποσών",
)
DISCLAIMER = "Το δελτίο αφορά την προετοιμασία και επαλήθευση των στοιχείων που καλύπτει το PoC. Δεν αποτελεί πιστωτική αξιολόγηση, έγκριση χρηματοδότησης ή βεβαίωση πληρότητας όλων των δικαιολογητικών της τράπεζας."
DRAFT = "ΠΡΟΣΧΕΔΙΟ — ΕΚΚΡΕΜΕΙΣ ΕΛΕΓΧΟΙ / ΣΤΟΙΧΕΙΑ"
IDENTITY = "Έλεγχος στην τοπική συνεδρία χωρίς επαλήθευση ταυτότητας."


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def document_hashes(store, cid: str) -> dict:
    return {i["type"]: hashlib.sha256(i["content"]).hexdigest() for i in store.inputs(cid)}


def fingerprint(store, cid: str, rid: str) -> str:
    from .recheck import VERSION

    case = json.loads((store.folder(cid) / "case.json").read_text(encoding="utf-8"))
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in store.folder(cid).glob("run-*.json")]
    latest = max(runs, key=lambda r: r["created"])["id"] if runs else None
    return digest(
        [POLICY, VERSION, case, store.raw_run(cid, rid), document_hashes(store, cid), latest]
    )


def verified_sources(
    store, cid: str, rid: str, sources: list[dict], kind: str | None = None
) -> list[dict]:
    """Validate case/document/page/quote and recompute geometry from local bytes."""
    run = store.raw_run(cid, rid)
    inputs = {i["type"]: i for i in store.inputs(cid)}
    result = []
    for source in sources:
        e = Evidence.model_validate(
            {k: source[k] for k in ("document_id", "page", "block_id", "quote")}
        )
        doc = next(
            (
                d
                for d in run["result"]["documents"]
                if d["id"] == e.document_id and (kind is None or d["type"] == kind)
            ),
            None,
        )
        if doc is None or doc["case_id"] != cid:
            raise ValueError("Η πηγή δεν ανήκει στο σωστό έγγραφο αυτού του φακέλου.")
        content = inputs[doc["type"]]["content"]
        if hashlib.sha256(content).hexdigest() != doc["hash"]:
            raise ValueError("Το έγγραφο άλλαξε. Χρειάζεται νέα ανάλυση και επαλήθευση.")
        blocks = [Block.model_validate(b) for b in doc["blocks"]]
        validate_evidence([e], blocks, cid)
        block = next(b for b in doc["blocks"] if b["block_id"] == e.block_id)
        enriched = source_geometry(content, e.model_dump(), block)
        enriched.update(document_name=doc["name"], excerpt=e.quote)
        if enriched not in result:
            result.append(enriched)
    return result


def check_token(check: dict, exported: dict, hashes: dict) -> str:
    # Accepting an unchanged field records progress, not a new comparison basis.
    # Relevant corrections/unresolved decisions invalidate earlier resolutions,
    # including an edit followed by a return to the original value.
    dependencies = CHECK_FIELDS[check["check_id"]]
    docs = {d["type"]: d["fields"] for d in exported["documents"]}
    fields = []
    for kind, name in sorted(dependencies):
        field = docs.get(kind, {}).get(name)
        refs = [
            {k: s.get(k) for k in ("document_id", "page", "block_id", "quote")}
            for s in source_list(field)
        ]
        fields.append(
            [kind, name, field.get("normalized_value") if field else None, usable(field), refs]
        )
    edits = [
        e
        for e in exported["review_events"]
        if (e["document_type"], e["field"]) in dependencies and e["review_decision"] != "accepted"
    ]
    return digest([RESOLUTION_BASIS, check, fields, edits, hashes])


def resolution_matches(event: dict, check: dict, exported: dict, hashes: dict, token: str) -> bool:
    if event.get("basis_version") == RESOLUTION_BASIS:
        return event["basis"] == token
    if event.get("basis_version") or not event.get("timestamp"):
        return False
    # Old records hashed all review events. Keep them after ordinary acceptance
    # without rewriting history or accepting a materially changed comparison.
    prior = [e for e in exported["review_events"] if e["timestamp"] <= event["timestamp"]]
    later = [
        e
        for e in exported["review_events"]
        if e["timestamp"] > event["timestamp"]
        and (e["document_type"], e["field"]) in CHECK_FIELDS[check["check_id"]]
    ]
    if event["basis"] != digest([check, prior, hashes]):
        return False
    previously_changed = {
        (e["document_type"], e["field"]) for e in prior if e["review_decision"] != "accepted"
    }
    return all(
        e["review_decision"] == "accepted"
        and (e["document_type"], e["field"]) not in previously_changed
        for e in later
    )


def preview(store, cid: str, rid: str) -> dict:
    raw = store.raw_run(cid, rid)
    exported = store.export(cid, rid)
    docs = {d["type"]: d for d in exported["documents"]}
    hashes = document_hashes(store, cid)
    latest = {(e["document_type"], e["field"]): e for e in raw["reviews"]}
    rows, issues = [], []
    for key, (kind, name) in SCOPE.items():
        field = docs[kind]["fields"][name]
        event = latest.get((kind, name))
        reviewed = field.get("review_status") in {"accepted", "corrected"}
        sources = (
            event.get("documented_sources", [])
            if event and event["review_decision"] == "corrected"
            else source_list(field)
        )
        try:
            sources = verified_sources(store, cid, rid, sources, kind)
        except (ValueError, KeyError):
            sources = []
        value = field["normalized_value"] if reviewed else None
        if key == "financial_year" and value:
            value = int(str(value).split("/")[-1][:4])
        reason = None
        if field.get("review_status") == "unresolved":
            reason = "Ανεπίλυτο στοιχείο."
        elif field["normalized_value"] is None:
            reason = "Λείπει απαιτούμενη πληροφορία."
        elif not reviewed:
            reason = (
                field.get("review_reason")
                if field.get("review_status") == "pending" and event
                else None
            ) or "Εκκρεμεί ανθρώπινη επαλήθευση."
        elif not sources:
            reason = (
                "Χειροκίνητη καταχώριση χωρίς τεκμηρίωση."
                if event and event["review_decision"] == "corrected"
                else "Δεν υπάρχει έγκυρη πηγή."
            )
        if reason:
            issues.append(dict(id=key, label=FIELD_LABELS[key], reason=reason))
        period = docs["financials"]["fields"]["reporting_period"]
        year = (
            period["normalized_value"]
            if period.get("review_status") in {"accepted", "corrected"}
            else None
        )
        unit = None
        if name in {
            "requested_amount",
            "revenue",
            "net_profit_or_loss",
            "total_assets",
            "total_liabilities",
            "total_equity",
        }:
            currency = docs[kind]["fields"]["currency"]
            unit = (
                currency["normalized_value"]
                if currency["status"] in {"extracted", "manually_corrected"}
                else None
            )
        rows.append(
            dict(
                key=key,
                document_type=kind,
                field=name,
                label=FIELD_LABELS[key],
                value=value,
                year=year if kind == "financials" else None,
                unit=unit,
                review_status=field.get("review_status", "pending"),
                reviewed=reviewed,
                complete=reason is None,
                note=reason,
                sources=sources,
            )
        )
    resolutions = raw.get("resolutions", [])
    conflicts = []
    for check in exported["reviewed_checks"]:
        ident = check["check_id"]
        if ident not in CROSS:
            continue
        # Current comparisons determine pending work; corrections remain in audit.
        if check["status"] == "PASS":
            continue
        token = check_token(check, exported, hashes)
        resolution = next(
            (
                e
                for e in reversed(resolutions)
                if e["check_id"] == ident and resolution_matches(e, check, exported, hashes, token)
            ),
            None,
        )
        if resolution:
            try:
                if not verified_sources(store, cid, rid, resolution["sources"]):
                    resolution = None
            except (ValueError, KeyError):
                resolution = None
        conflicts.append(
            dict(**check, label=CHECK_LABELS[ident], basis=token, resolution=resolution)
        )
        if not resolution:
            reason = (
                "Ο έλεγχος δεν ολοκληρώθηκε. Έλεγξε πρώτα τα απαιτούμενα πεδία. "
                if check["status"] == "NOT_CHECKED"
                else "Απαιτείται καταγεγραμμένη επίλυση με αιτιολογία και πηγή. "
            )
            issues.append(
                dict(id=ident, label=CHECK_LABELS[ident], reason=reason + check["explanation"])
            )
    if exported.get("errors"):
        issues.append(
            dict(id="processing", label="Ανάλυση", reason="Υπάρχουν σφάλματα επεξεργασίας.")
        )
    saved_runs = [
        json.loads(p.read_text(encoding="utf-8")) for p in store.folder(cid).glob("run-*.json")
    ]
    if max(saved_runs, key=lambda r: r["created"])["id"] != rid:
        issues.append(
            dict(
                id="old_analysis",
                label="Προηγούμενη ανάλυση",
                reason="Υπάρχει νεότερη ανάλυση. Έλεγξε τα πεδία της πριν την τελική έκδοση.",
            )
        )
    unreviewed = sum(not r["reviewed"] for r in rows)
    state = (
        "Προς έλεγχο"
        if unreviewed
        else "Εκκρεμούν στοιχεία ή διευκρινίσεις"
        if issues
        else "Ολοκληρώθηκε η προετοιμασία"
    )
    # Missing/unresolved takes priority over merely pending proposals.
    if any(
        r["note"]
        and (
            r["review_status"] == "unresolved"
            or docs[r["document_type"]]["fields"][r["field"]]["normalized_value"] is None
            or (r["reviewed"] and not r["sources"])
        )
        for r in rows
    ) or any(not c["resolution"] for c in conflicts):
        state = "Εκκρεμούν στοιχεία ή διευκρινίσεις"
    company = next(r for r in rows if r["key"] == "company_name")
    audit = copy.deepcopy([e for e in raw["reviews"] if e["review_decision"] == "corrected"])
    resolution_audit = copy.deepcopy(resolutions)
    for event in audit + resolution_audit:
        source_key = "documented_sources" if "review_decision" in event else "sources"
        try:
            event[source_key] = verified_sources(
                store, cid, rid, event.get(source_key, []), event.get("document_type")
            )
        except (ValueError, KeyError):
            event[source_key] = []
            event["source_notice"] = "Η ιστορική πηγή δεν αντιστοιχεί στα τρέχοντα έγγραφα."
    return dict(
        policy=POLICY,
        case_id=cid,
        run_id=rid,
        company=company["value"] if company["complete"] else None,
        state=state,
        draft=bool(issues),
        reviewed_count=10 - unreviewed,
        pending_count=sum(not r["complete"] for r in rows),
        fields=rows,
        issues=issues,
        conflicts=conflicts,
        documents=[
            dict(
                **{k: d[k] for k in ("id", "type", "name", "page_count")},
                hash=hashes[d["type"]],
                analysis_hash=d["hash"],
                requires_reanalysis=hashes[d["type"]] != d["hash"],
            )
            for d in exported["documents"]
        ],
        corrections=audit,
        resolutions=resolution_audit,
        fingerprint=fingerprint(store, cid, rid),
        version=len(versions(store, cid)) + 1,
        synthetic=True,
        identity=IDENTITY,
        disclaimer=DISCLAIMER,
        example_notice=raw["result"].get("example_notice"),
    )


def resolve(
    store, cid: str, rid: str, check_id: str, reason: str, sources: list[dict], basis: str
) -> None:
    from .store import LOCK, now

    with LOCK:
        report = preview(store, cid, rid)
        check = next((c for c in report["conflicts"] if c["check_id"] == check_id), None)
        if not check or check["basis"] != basis:
            raise ValueError("Ο έλεγχος άλλαξε. Δες ξανά τις τιμές πριν καταγράψεις επίλυση.")
        if check["status"] == "NOT_CHECKED":
            raise ValueError(
                "Λείπουν στοιχεία για τη σύγκριση. Συμπλήρωσε και τεκμηρίωσε τα πεδία πριν επιλύσεις τον έλεγχο."
            )
        refs = verified_sources(store, cid, rid, sources)
        if not reason.strip() or not refs:
            raise ValueError("Η επίλυση απαιτεί αιτιολογία και τουλάχιστον μία τεκμηριωμένη πηγή.")
        expected_docs = {e["document_id"] for e in check.get("evidence", [])}
        if not expected_docs.issubset({e["document_id"] for e in refs}):
            raise ValueError(
                "Τεκμηρίωσε την επίλυση με πηγές και από τα δύο συγκρινόμενα έγγραφα, όπου υπάρχουν."
            )
        run = store.raw_run(cid, rid)
        run.setdefault("resolutions", []).append(
            dict(
                timestamp=now(),
                check_id=check_id,
                reason=reason.strip(),
                sources=refs,
                basis=basis,
                basis_version=RESOLUTION_BASIS,
                identity=IDENTITY,
            )
        )
        store.save(store.folder(cid) / ("run-" + rid + ".json"), run)


def versions(store, cid: str) -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((store.folder(cid) / "bulletins").glob("*/snapshot.json"))
        if p.parent.name.isdecimal()
    ]


def is_stale(store, snapshot: dict) -> bool:
    try:
        return snapshot["fingerprint"] != fingerprint(
            store, snapshot["case_id"], snapshot["run_id"]
        )
    except (ValueError, OSError):
        return True


def publish_version(staging: Path, folder: Path) -> None:
    """Retry short Windows sharing/antivirus locks; never replace a version."""
    for attempt in range(4):
        if folder.exists():
            raise ValueError("Η έκδοση υπάρχει ήδη. Άνοιξε ξανά την προεπισκόπηση.")
        try:
            staging.rename(folder)
            return
        except PermissionError:
            if attempt == 3:
                raise ValueError(
                    "Το δελτίο δεν αποθηκεύτηκε: προσωρινό κλείδωμα αρχείων. Δοκίμασε ξανά. Οι προηγούμενες εκδόσεις διατηρούνται."
                ) from None
            time.sleep(0.1 * 2**attempt)


def issue(store, cid: str, rid: str, expected_fingerprint: str, studio: bool = False) -> dict:
    from .store import LOCK, now
    from .bulletin_pdf import render_pdf

    with LOCK:
        report = preview(store, cid, rid)
        if report["fingerprint"] != expected_fingerprint:
            raise ValueError("Τα στοιχεία άλλαξαν. Άνοιξε ξανά την προεπισκόπηση.")
        report["issued_at"] = now()
        inputs = store.inputs(cid)
        root = store.folder(cid) / "bulletins"
        root.mkdir(exist_ok=True)
        folder = root / f"{report['version']:04d}"
        # Build before publishing the immutable version; failed rendering never issues it.
        pdf = render_pdf(report, studio=True) if studio else render_pdf(report)
        if report["fingerprint"] != fingerprint(store, cid, rid) or any(
            hashlib.sha256(i["content"]).hexdigest()
            != next(d["hash"] for d in report["documents"] if d["type"] == i["type"])
            for i in inputs
        ):
            raise ValueError(
                "Τα στοιχεία άλλαξαν κατά τη δημιουργία. Άνοιξε ξανά την προεπισκόπηση."
            )
        from uuid import uuid4

        staging = root / (".pending-" + uuid4().hex)
        staging.mkdir()
        for item in inputs:
            (staging / (item["type"] + ".pdf")).write_bytes(item["content"])
        (staging / "bulletin.pdf").write_bytes(pdf)
        store.save(staging / "snapshot.json", report)
        publish_version(staging, folder)
        return copy.deepcopy(report)


def version_folder(store, snapshot: dict) -> Path:
    version = int(snapshot["version"])
    if version < 1:
        raise ValueError("Invalid version")
    return store.folder(snapshot["case_id"]) / "bulletins" / f"{version:04d}"
