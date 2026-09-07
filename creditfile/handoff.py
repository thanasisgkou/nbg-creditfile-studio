"""Deterministic analyst handoff, using reviewed values and current checks."""

from .schema import LABELS, MONEY
from .checks import source_list, usable

KINDS = {"application": "Αίτηση", "financials": "Οικονομικές καταστάσεις"}
CHECK_LABELS = {
    "company_match": "Επωνυμία",
    "tax_id_match": "ΑΦΜ",
    "currency_match": "Νόμισμα",
    "turnover_match": "Κύκλος εργασιών",
    "debt_match": "Τραπεζικός δανεισμός",
    "accounting_equation": "Λογιστική εξίσωση",
    "unit_scale": "Μονάδα ποσών",
}


def value_text(value, field="") -> str:
    if value is None:
        return "Δεν έχει επιβεβαιωθεί τιμή"
    return str(value) + (" EUR" if field in MONEY else "")


def clarifications(exported: dict, resolved: set[str]) -> list[dict]:
    items = []
    for c in exported["reviewed_checks"]:
        if c["check_id"] not in CHECK_LABELS or c["status"] == "PASS" or c["check_id"] in resolved:
            continue
        label = CHECK_LABELS[c["check_id"]]
        if c["status"] == "FAIL" and c["right_value"] is not None:
            question = f"Για το στοιχείο «{label}» καταγράφηκαν οι τιμές {c['left_value']} και {c['right_value']}. Παρακαλούμε διευκρινίστε τη διαφορά, τη μονάδα και την περίοδο αναφοράς, παρέχοντας σχετική τεκμηρίωση."
        else:
            question = f"Παρακαλούμε προσκομίστε τεκμηρίωση για το στοιχείο «{label}», ώστε να ολοκληρωθεί ο σχετικός έλεγχος."
        items.append(
            dict(
                id=c["check_id"],
                question=question,
                reason=c["explanation"],
                sources=c["evidence"],
                basis="Τρέχουσες τιμές μετά τον έλεγχο αναλυτή· όχι κατ’ ανάγκη όλες επιβεβαιωμένες.",
            )
        )
    for doc in exported["documents"]:
        for name, f in doc["fields"].items():
            if f["approved_for_credit_memo"] and usable(f) and source_list(f):
                continue
            if (
                f["status"] not in {"missing", "uncertain", "invalid", "manually_corrected"}
                and f["review_status"] != "unresolved"
            ):
                continue
            items.append(
                dict(
                    id=doc["type"] + "." + name,
                    question=f"Παρακαλούμε επιβεβαιώστε το στοιχείο «{LABELS[name]}» στο έγγραφο «{KINDS[doc['type']]}» και προσκομίστε σαφή τεκμηρίωση.",
                    reason=f.get("reviewer_comment") or f.get("review_reason"),
                    sources=source_list(f),
                    basis="Εκκρεμές στοιχείο· δεν θεωρείται επιβεβαιωμένο.",
                )
            )
    return items


def summary(exported: dict, case_name: str, preparation: dict) -> dict:
    approved = []
    pending = []
    for d in exported["documents"]:
        for name, f in d["fields"].items():
            complete = bool(f["approved_for_credit_memo"] and usable(f) and source_list(f))
            row = dict(
                document=d["name"],
                document_type=d["type"],
                field=name,
                label=LABELS[name],
                value=f["normalized_value"] if complete else None,
                review_status=f["review_status"],
                sources=source_list(f),
                comment=f.get("reviewer_comment", ""),
                corrected=f["status"] == "manually_corrected",
            )
            (approved if complete else pending).append(row)
    resolved = {c["check_id"] for c in preparation["conflicts"] if c["resolution"]}
    return dict(
        case_name=case_name,
        case_id=exported["case_id"],
        run_id=exported["run_id"],
        created=exported["exported_at"],
        approved=approved,
        pending=pending,
        clarifications=clarifications(exported, resolved),
        checks=exported["reviewed_checks"],
        ready_for_credit_memo=not pending and not preparation["draft"],
        notice="Προσχέδιο προετοιμασίας φακέλου. Δεν αποτελεί πιστωτική απόφαση. Οι χειροκίνητες διορθώσεις δεν τεκμηριώνονται αυτομάτως από τις αρχικές παραπομπές.",
    )


def references(sources: list[dict]) -> str:
    return (
        "; ".join(
            dict.fromkeys(
                f"{e.get('document_name', e['document_id'])} · σελ. {e['page']} · {e.get('quote') or e.get('excerpt', '')}"
                for e in sources
            )
        )
        or "Χωρίς διαθέσιμη παραπομπή"
    )


def markdown(report: dict) -> str:
    lines = [
        f"# Σύνοψη ελεγμένου φακέλου: {report['case_name']}",
        "",
        report["notice"],
        "",
        f"Επιβεβαιωμένα: {len(report['approved'])}/24 · Εκκρεμή: {len(report['pending'])}",
        "",
        "## Επιβεβαιωμένα στοιχεία",
        "",
    ]
    for row in report["approved"]:
        lines.extend(
            [
                f"- {KINDS[row['document_type']]} / {row['label']}: {value_text(row['value'], row['field'])}"
                + (" — διορθώθηκε από αναλυτή" if row["corrected"] else ""),
                f"  Πηγή: {references(row['sources'])}",
                f"  Σχόλιο αναλυτή: {row['comment']}",
            ]
        )
    if not report["approved"]:
        lines.append("Δεν έχουν επιβεβαιωθεί στοιχεία από αναλυτή.")
    lines += ["", "## Εκκρεμής έλεγχος", ""] + [
        f"- {KINDS[r['document_type']]} / {r['label']} ({r['review_status']})"
        for r in report["pending"]
    ]
    lines += ["", "## Προσχέδιο διευκρινίσεων — απαιτεί έλεγχο πριν αποσταλεί", ""]
    for i, item in enumerate(report["clarifications"], 1):
        lines.extend(
            [
                f"{i}. {item['question']}",
                f"   Βάση: {item['basis']}",
                f"   Πηγή: {references(item['sources'])}",
            ]
        )
    if not report["clarifications"]:
        lines.append(
            "Δεν προέκυψαν διευκρινίσεις από τους προκαθορισμένους ελέγχους. Τυχόν μη ελεγμένα πεδία παραμένουν εκκρεμή."
        )
    return "\n".join(lines)
