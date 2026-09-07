"""Answer preparation questions from current review state, without PDF retrieval."""

import re

from .extraction import plain
from .schema import LABELS
from .checks import source_list


def workflow_intent(question: str, history: list[dict]) -> bool:
    q = plain(question).strip(" ;?.!")
    # Readiness of this workflow is distinct from loan approval or financial facts.
    if re.search(
        r"εγκρι|απορρι|πιστοληπ|scor|approv|kyc|aml|αλλ\w*\s+φακελ|other\s+(case|folder)", q
    ):
        return False
    if re.search(
        r"ποσο|υπολοιπ|δοσε[ις]|επιτοκ|δανει|τζιρ|κυκλο|ebitda|κερδ|χρηματοδοτ|20\d{2}", q
    ):
        return False
    if re.search(
        r"(ετοιμ|ολοκληρ|τελειω|ενταξει).*φακελ|φακελ.*(ετοιμ|ολοκληρ|τελειω|ενταξει|οκ)|"
        r"(ετοιμ|εκδο|εκδω|βγαλ|ολοκληρ).*δελτι|καταστασ.*φακελ|σταδιο.*φακελ|"
        r"(?:τι|κατι|τιποτα|καποιο|καμια).*ανοιχτ|τι.*(?:μενει|απομενει)|"
        r"(?:μενει|εμεινε|απομενει).*?(?:κατι|τιποτα)|"
        r"χρειαζεται.*κατι|τι.*(?:πρεπει|χρειαζεται).*καν|επομεν.*βημα|"
        r"τι.*(?:εκκρεμ|λειπει|προβλημ)|(?:υπαρχ|εχουμε|εχει).*εκκρεμ|ολα\s+(?:καλα|οκ)|"
        r"(?:case|folder).*(?:ready|complete|status)|(?:ready|complete).*(?:case|folder)|"
        r"what.*(?:pending|left|open)|anything.*(?:pending|left|open)",
        q,
    ):
        return True
    return bool(
        history
        and history[-1].get("mode") == "local_workflow"
        and re.fullmatch(
            r"(?:και\s+)?(?:γιατι|τι εννοεις|εξηγησε|εξηγησε το|πιο απλα|τι αλλο|τωρα|ειναι ετοιμος(?: τωρα)?|τελειωσαμε|ολοκληρωθηκε)",
            q,
        )
    )


def answer_workflow(question: str, report: dict, view: dict) -> dict:
    if (report["case_id"], report["run_id"]) != (view["case_id"], view["run_id"]):
        raise ValueError("Η κατάσταση δεν ανήκει στον επιλεγμένο φάκελο και ανάλυση.")
    claims = []
    covered_fields = set()
    for doc in view["documents"]:
        unreviewed = []
        for name, field in doc["fields"].items():
            if field.get("approved_for_credit_memo"):
                continue
            covered_fields.add((doc["type"], name))
            if field.get("normalized_value") is None or field.get("review_status") == "unresolved":
                label = LABELS[name]
                claims.append(
                    dict(
                        text=f"{label}: χρειάζεται συμπλήρωση ή διευκρίνιση με τεκμηρίωση.",
                        sources=source_list(field),
                    )
                )
            else:
                unreviewed.append(name)
        if unreviewed:
            subject = (
                "της αίτησης" if doc["type"] == "application" else "των οικονομικών καταστάσεων"
            )
            claims.append(
                dict(text=f"Εκκρεμεί επιβεβαίωση {len(unreviewed)} πεδίων {subject}.", sources=[])
            )
    unresolved = [c for c in report["conflicts"] if not c["resolution"]]
    for check in unresolved:
        text = check["label"] + ": " + check["explanation"]
        difference = check.get("absolute_difference")
        if difference is not None:
            amount = f"{difference:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
            text += f" Διαφορά: {amount} €."
        text += " Χρειάζεται καταγεγραμμένη διευκρίνιση με πηγές."
        claims.append(
            dict(text=text, sources=check.get("evidence", []), check_id=check["check_id"])
        )
    # Include processing, stale-analysis and evidence failures, beyond ordinary fields.
    known = {c["check_id"] for c in unresolved}
    for issue in report["issues"]:
        if issue["id"] in known:
            continue
        row = next((f for f in report["fields"] if f["key"] == issue["id"]), None)
        if row and (row["document_type"], row["field"]) in covered_fields:
            continue
        claims.append(dict(text=issue["label"] + ": " + issue["reason"], sources=[]))
    complete = not report["draft"] and not claims
    count = report["reviewed_count"]
    if complete:
        message = (
            "Η προετοιμασία του φακέλου έχει ολοκληρωθεί. "
            "Έχουν ελεγχθεί και τα 10/10 στοιχεία του δελτίου και δεν απομένει ανοιχτή εκκρεμότητα στους ελέγχους της εφαρμογής. "
            "Μπορείς να δεις ή να εκδώσεις το δελτίο."
        )
    elif not report["draft"]:
        message = "Η προετοιμασία του δελτίου έχει ολοκληρωθεί (10/10), αλλά στον υπόλοιπο φάκελο παραμένουν τα εξής:"
    else:
        message = f"Υπάρχουν ακόμη εκκρεμότητες. Έχουν ελεγχθεί {count}/10 στοιχεία του δελτίου. Ανοιχτά παραμένουν τα εξής:"
    return dict(
        case_id=report["case_id"],
        run_id=report["run_id"],
        question=question,
        mode="local_workflow",
        status="answered",
        message=message,
        claims=claims,
        sources=[s for c in claims for s in c["sources"]],
        unanswered=[],
        calls=[],
        error=None,
        seconds=0,
        workflow=dict(
            state=report["state"],
            complete=complete,
            reviewed_count=count,
            fingerprint=report["fingerprint"],
        ),
    )
