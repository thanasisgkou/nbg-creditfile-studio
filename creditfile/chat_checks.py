"""Deterministic answers to questions about application checks, not PDF search."""

import re
from .extraction import plain
from .handoff import CHECK_LABELS
from .schema import LABELS

FOLLOWUP = r"(?:και\s+)?(?:γιατι|τι εννοεις|εξηγησε το|ποιες|ποια|και μετα)[;?.! ]*"


def check_context(question: str, history: list[dict]) -> str:
    q = plain(question)
    if not re.fullmatch(FOLLOWUP, q):
        return q
    for turn in reversed(history):
        if turn.get("mode") != "local_checks":
            break
        prior = plain(turn.get("check_context", turn["question"]))
        if not re.fullmatch(FOLLOWUP, prior):
            return prior
    return q


def check_intent(question: str, history: list[dict]) -> bool:
    q = check_context(question, history)
    if (
        history
        and history[-1].get("mode") == "local_checks"
        and re.fullmatch(
            r"(?:και\s+)?(?:γιατι|τι εννοεις|εξηγησε το|ποιες|ποια|και μετα)[;?.! ]*", q
        )
    ):
        q = plain(history[-1]["question"])
    # A targeted financial fact remains RAG; case/problem questions use actual checks.
    if re.search(
        r"(?:κατι|τιποτα)\s+(?:αλλο\s+)?(?:περιεργ|παραξεν)|τι\s+(?:αλλο\s+)?(?:να|πρεπει\s+να)\s+προσεξ|(?:κατι|τι)\s+δεν\s+(?:παει\s+καλα|στεκει)",
        q,
    ):
        return True
    if re.search(
        r"προβλημ|αποκλισ|εκκρεμ|ασυμφων|ελλειψ|mismatch|discrepanc|issues?|missing fields|ολα\s+καλα|ενταξει.*φακελ|φακελ.*ενταξει|τι.*χρειαζεται.*ελεγ|τι.*λειπει",
        q,
    ):
        return True
    if re.search(r"συμφων|διαφορ|διαφερ", q) and re.search(
        r"δανει|κυκλο|τζιρ|αιτησ|καταστασ|φακελ|εγγραφ", q
    ):
        return True
    return bool(
        history
        and history[-1].get("mode") == "local_checks"
        and re.fullmatch(
            r"(?:και\s+)?(?:γιατι|τι εννοεις|εξηγησε το|ποιες|ποια|και μετα)[;?.! ]*", q
        )
    )


def answer_checks(question: str, view: dict, history: list[dict]) -> dict:
    checks = view.get("reviewed_checks", view.get("checks", []))
    q = check_context(question, history)
    if (
        history
        and history[-1].get("mode") == "local_checks"
        and re.fullmatch(
            r"(?:και\s+)?(?:γιατι|τι εννοεις|εξηγησε το|ποιες|ποια|και μετα)[;?.! ]*", q
        )
    ):
        q = plain(history[-1]["question"])
    debt = bool(re.search(r"δανει|δανεισ|debt|borrow", q))
    turnover = bool(re.search(r"κυκλο|τζιρ|turnover|revenue", q))
    exclude_amount_differences = bool(
        re.search(
            r"(?:εκτος|περα)\s+απο\s+(?:(?:την|τις|τη)\s+)?(?:διαφορ\w*|αποκλισ\w*)\s+(?:στα|των)\s+ποσ\w*",
            q,
        )
    )
    if exclude_amount_differences:
        checks = [c for c in checks if c["check_id"] not in {"debt_match", "turnover_match"}]
    relevant = (
        [
            c
            for c in checks
            if (debt and any(t in c["check_id"] for t in ("debt", "borrowings")))
            or (turnover and any(t in c["check_id"] for t in ("turnover", "revenue")))
        ]
        if debt or turnover
        else checks
    )
    if not relevant:
        message = "Δεν υπάρχουν αποθηκευμένοι έλεγχοι για αυτή την ερώτηση. Χρειάζεται ανάλυση του φακέλου."
        if exclude_amount_differences:
            message = "Δεν υπάρχουν άλλοι σχετικοί αποθηκευμένοι έλεγχοι πέρα από τις διαφορές ποσών που ζήτησες να εξαιρεθούν. Αυτό δεν αποκλείει άλλα προβλήματα στο PDF."
        return dict(status="needs_review", claims=[], unanswered=[message], sources=[])
    findings = [c for c in relevant if c["status"] != "PASS"]
    claims = []
    unanswered = []
    display_checks = [
        c
        for c in relevant
        if c["status"] != "PASS"
        or ((debt or turnover) and c["check_id"] in {"debt_match", "turnover_match"})
    ]
    for c in display_checks:
        label = CHECK_LABELS.get(c["check_id"], c["check_id"])
        parts = c["check_id"].split(".")
        if len(parts) == 3 and parts[1] in LABELS:
            label = (
                ("Αίτηση" if parts[0] == "application" else "Οικονομικές καταστάσεις")
                + " / "
                + LABELS[parts[1]]
            )
        text = f"{label}: " + c["explanation"]
        if c["check_id"] in {"debt_match", "turnover_match"}:
            text += f" Αίτηση: {str(c['left_value']) + ' EUR' if c['left_value'] is not None else 'μη επαληθευμένη τιμή'} · Οικονομικές καταστάσεις: {str(c['right_value']) + ' EUR' if c['right_value'] is not None else 'μη επαληθευμένη τιμή'}."
            if c["absolute_difference"] is not None:
                text += f" Διαφορά: {c['absolute_difference']:g} EUR" + (
                    f" ({c['percentage_difference']:.2f}%)."
                    if c["percentage_difference"] is not None
                    else "."
                )
            if c["status"] == "NOT_CHECKED":
                text += " Δεν μπορεί ακόμη να εξαχθεί συμπέρασμα συμφωνίας ή απόκλισης."
        if c["evidence"]:
            claims.append(dict(text=text, sources=c["evidence"], check_id=c["check_id"]))
        else:
            unanswered.append(text + " Δεν υπάρχει διαθέσιμη παραπομπή.")
    count = view.get("approved_field_count", 0)
    if findings:
        unanswered.insert(
            0,
            (
                "Υπάρχει 1 έλεγχος που χρειάζεται προσοχή"
                if len(findings) == 1
                else f"Υπάρχουν {len(findings)} έλεγχοι που χρειάζονται προσοχή"
            )
            + (" στον δανεισμό." if debt and not turnover else " σε αυτό το ερώτημα."),
        )
    else:
        unanswered.insert(
            0,
            "Πέρα από τις διαφορές ποσών, δεν προκύπτει άλλο εύρημα στους σχετικούς προκαθορισμένους ελέγχους. Αυτό δεν αποτελεί πλήρη έλεγχο όλων των πιθανών προβλημάτων του φακέλου."
            if exclude_amount_differences
            else "Οι σχετικοί προκαθορισμένοι έλεγχοι συμφωνούν. Αυτό δεν σημαίνει πιστωτική έγκριση ή ότι ο φάκελος έχει ολοκληρωθεί.",
        )
    if exclude_amount_differences:
        unanswered.append(
            "Οι διαφορές ποσών εξαιρέθηκαν μόνο από αυτή την απάντηση· η κατάστασή τους στον φάκελο δεν άλλαξε."
        )
    unanswered.append(
        f"Έλεγχος αναλυτή: {count}/24 πεδία ολοκληρωμένα. Οι εκκρεμότητες χρειάζονται ανθρώπινο έλεγχο."
    )
    if view.get("review_events"):
        unanswered.append(
            "Χρησιμοποιούνται οι τρέχουσες τιμές μετά τις διορθώσεις αναλυτή. Οι παραπομπές δείχνουν το αρχικό κείμενο των PDF."
        )
    return dict(
        status="needs_review" if findings or count < 24 else "answered",
        claims=claims,
        unanswered=unanswered,
        sources=[s for c in claims for s in c["sources"]],
        check_context=q,
    )
