"""Conversational references identify checks; current stored checks supply facts."""

import re
from .extraction import plain
from .chat_ux import topics


def relevant_history(question, history):
    """An explicit new topic must not inherit an unrelated clarification loop."""
    current = set(topics(question))
    if current:
        for turn in reversed(history):
            previous = set(topics(turn.get("resolved_question") or turn["question"]))
            previous.update(
                {"debt_match": "total_borrowings", "turnover_match": "revenue"}[c["check_id"]]
                for c in turn.get("claims", [])
                if c.get("check_id") in {"debt_match", "turnover_match"}
            )
            if previous:
                if current.isdisjoint(previous):
                    return []
                break
    return history


def explain_previous(question, history, view):
    q = plain(question)
    if not (
        re.search(
            r"γιατι|λαθος|δεν καταλαβ|εξηγη|τι εννο|τι σημαιν|πιο απλα|που.*διαφορ|ειπες|δηλαδη|δλδ",
            q,
        )
        or q.strip(" ;?.!") in {"ναι", "οκ", "εξηγησε"}
    ):
        return None
    # A new explicit subject must not inherit an unrelated check.
    names = set(topics(question))
    if names - {"total_borrowings", "revenue"}:
        return None
    previous = None
    for turn in reversed(history[-8:]):
        if turn.get("error"):
            continue
        if turn.get("claims"):
            previous = turn
            break
    if not previous:
        return None
    ids = {c.get("check_id") for c in previous["claims"]}
    if names:
        ids &= {"debt_match" if n == "total_borrowings" else "turnover_match" for n in names}
    checks = [
        c
        for c in view.get("reviewed_checks", view.get("checks", []))
        if c["check_id"] in ids and c["check_id"] in {"debt_match", "turnover_match"}
    ]
    if not checks:
        return None

    def money(value):
        return f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") + " €"

    claims = []
    for c in checks:
        left, right, difference = (
            c.get("left_value"),
            c.get("right_value"),
            c.get("absolute_difference"),
        )
        if c["status"] == "NOT_CHECKED" or left is None or right is None or not c.get("evidence"):
            continue
        subject = (
            "υφιστάμενο τραπεζικό δανεισμό" if c["check_id"] == "debt_match" else "κύκλο εργασιών"
        )
        text = (
            f"Στην αίτηση ο αιτών δηλώνει {money(left)} για τον {subject}, "
            f"ενώ οι οικονομικές καταστάσεις αναφέρουν {money(right)}."
        )
        if c["status"] == "PASS":
            text += " Ο τρέχων έλεγχος δεν εντοπίζει απόκλιση εκτός ανοχής."
        elif difference is not None:
            direction = "λιγότερα" if left < right else "περισσότερα"
            text += (
                f" Δηλαδή, στην αίτηση εμφανίζονται {money(difference)} {direction}. "
                "Αυτή είναι η ασυμφωνία που επισήμανα. Δεν αποδεικνύει από μόνη της ποια τιμή είναι λανθασμένη ή γιατί διαφέρουν."
            )
        claims.append({"text": text, "sources": c["evidence"], "check_id": c["check_id"]})
    if not claims:
        return None
    return dict(
        status="answered",
        mode="local_checks",
        claims=claims,
        sources=[s for c in claims for s in c["sources"]],
        unanswered=[
            "Για να διευκρινιστεί, ελέγξτε αν τα δύο ποσά αφορούν την ίδια ημερομηνία και την ίδια βάση αναφοράς."
        ],
        check_context=previous.get("check_context", previous["question"]),
    )


def identity_question(question, view):
    q = plain(question)
    if not re.search(r"νομιμοποι|στοιχεια ταυτοτ", q) or not re.search(r"λειπ|ελεγ|εκκρεμ", q):
        return None
    from .schema import LABELS
    from .checks import source_list

    fields = {
        "company_legal_name",
        "tax_id",
        "registration_number",
        "legal_form",
        "business_activity",
        "establishment_date",
    }
    doc = next((d for d in view.get("documents", []) if d["type"] == "application"), None)
    if not doc:
        return None
    claims, gaps = [], []
    for name, field in doc["fields"].items():
        if name not in fields or field.get("approved_for_credit_memo"):
            continue
        missing = field.get("normalized_value") is None
        text = LABELS[name] + (
            ": δεν έχει τεκμηριωθεί τιμή στην εξαγωγή της αίτησης."
            if missing
            else ": υπάρχει τιμή, αλλά εκκρεμεί επιβεβαίωση από τον αναλυτή."
        )
        sources = source_list(field)
        if sources:
            claims.append(dict(text=text, sources=sources))
        else:
            gaps.append(text)
    return dict(
        mode="local_reviews",
        status="partial" if claims or gaps else "answered",
        claims=claims,
        sources=[s for c in claims for s in c["sources"]],
        unanswered=gaps
        + [
            "Η απάντηση αφορά τα αποθηκευμένα πεδία ταυτότητας της αίτησης. Δεν ελέγχεται εδώ η πληρότητα πρόσθετων νομιμοποιητικών εγγράφων."
        ],
    )
