"""Local conversation guidance and analyst context. No model calls."""

import re
from .extraction import plain
from .schema import LABELS
from .checks import source_list

TOPICS = {
    "revenue": r"κυκλο\w*\s+εργασ|τζιρ|πωλησ|revenue|turnover",
    "ebitda": r"ebitda",
    "net_profit_or_loss": r"καθαρ\w*\s+(?:κερδ|αποτελεσ)|net profit",
    "total_borrowings": r"δανεισ|borrowings|debt",
    "requested_amount": r"αιτουμ\w*\s+ποσ|ποσ\w*\s+χρηματοδοτ",
    "financing_purpose": r"σκοπ\w*",
    "tenor_months": r"διαρκ\w*",
}
STARTERS = [
    ("Τι εκκρεμεί;", "Τι εκκρεμεί στον φάκελο;"),
    ("Πού διαφέρουν;", "Πού διαφέρουν τα δύο έγγραφα;"),
    ("Τι επιβεβαιώθηκε;", "Ποια στοιχεία έχουν επιβεβαιωθεί από τον αναλυτή;"),
]

DEFINITION_SCOPE = (
    "Ο βοηθός απαντά μόνο από τα PDF και τους ελέγχους αυτού του φακέλου, όχι από γενικές γνώσεις. "
    "Στα αποσπάσματα που εξετάστηκαν δεν τεκμηριώθηκε εξήγηση του όρου. "
    "Μπορείς να ρωτήσεις πού αναφέρεται ή τι προβλέπει το συγκεκριμένο έγγραφο."
)


def definition_intent(question: str) -> bool:
    q = plain(question).strip()
    return bool(
        re.match(
            r"(?:τι (?:ειναι|σημαινει|εννοουμε|εννουμε)\b|(?:μπορεις να )?εξηγησ\w* .*\bορο\b)", q
        )
        and not re.search(r"λαθος|ασυμφων|εκκρεμ|αυτο|που ειπες", q)
    )


def answer_gaps(turn: dict) -> list[str]:
    """Explain abstention without treating an echoed question as an answer.

    Also used when rendering legacy history; stored turns stay immutable.
    A retrieval miss is not proof that information is absent from the PDF.
    """

    def normalized(text):
        return re.sub(r"[^\w]+", " ", plain(text)).strip()

    question = normalized(turn.get("question", ""))
    messages = []
    for message in turn.get("unanswered", []):
        value = normalized(message)
        if value and value != question and message not in messages:
            messages.append(message)
    if not messages and (
        turn.get("unanswered") or turn.get("status") in {"not_found", "out_of_scope"}
    ):
        messages = [
            "Δεν προέκυψε τεκμηριωμένη απάντηση από τα αποσπάσματα που εξετάστηκαν. Αυτό δεν αποδεικνύει ότι η πληροφορία λείπει από ολόκληρο το PDF."
        ]
        if re.search(r"αιτησ", question) and re.search(r"χρονι|ετο[υσς]|ημερομην", question):
            messages.append(
                "Εννοείς την ημερομηνία υποβολής της αίτησης ή την οικονομική χρήση των στοιχείων της; Είναι διαφορετικές πληροφορίες."
            )
    return messages


def topics(question: str) -> list[str]:
    return [name for name, pattern in TOPICS.items() if re.search(pattern, plain(question))]


def followup(question: str, history: list[dict]) -> tuple[str, list[str]]:
    """Resolve only short references to the last explicit USER topic(s)."""
    q = plain(question).strip(" ;?.!")
    if q in {"ναι", "οκ", "δεν καταλαβα", "πιο απλα"} and history:
        previous = history[-1]
        topic = previous.get("resolved_question") or previous["question"]
        if definition_intent(topic):
            return topic, []
    short = re.fullmatch(
        r"(?:και\s+)?(?:για\s+)?(?:(?:το|την|της)\s+)?(?:20\d{2}|περσι|προηγουμενη(?:ς)?\s+χρηση(?:ς)?|αυτο)",
        q,
    )
    if not short:
        return question, []
    for turn in reversed(history[-3:]):
        names = topics(turn.get("resolved_question") or turn["question"])
        if names:
            if len(names) == 1:
                return LABELS[names[0]] + " — " + question, []
            return question, [LABELS[name] + " — " + question for name in names[:3]]
    return question, []


def review_intent(question: str) -> bool:
    return bool(
        re.search(
            r"(?:ποια|τι)\s+(?:στοιχεια\s+)?(?:εχουν\s+)?(?:ηδη\s+)?(?:επιβεβαιω|διορθωθ)|ελεγμενα\s+στοιχεια",
            plain(question),
        )
    )


def review_answer(view: dict) -> dict:
    claims = []
    unanswered = []
    for doc in view.get("documents", []):
        for name, field in doc["fields"].items():
            if not field.get("approved_for_credit_memo"):
                continue
            from .handoff import value_text

            sources = source_list(field)
            text = (
                ("Αίτηση" if doc["type"] == "application" else "Οικονομικές καταστάσεις")
                + " / "
                + LABELS[name]
                + ": "
                + value_text(field["normalized_value"], name)
            )
            if not sources:
                unanswered.append(
                    text
                    + " · Χειροκίνητη καταχώριση χωρίς τεκμηρίωση. Δεν επιβεβαιώνεται από τα PDF."
                )
            else:
                claims.append(
                    dict(
                        text=text,
                        sources=sources,
                        field_target=dict(type="field", kind=doc["type"], name=name),
                    )
                )
    if not claims and not unanswered:
        unanswered = [
            "Δεν έχει επιβεβαιωθεί ακόμη κανένα στοιχείο από τον αναλυτή. Μπορείς να ξεκινήσεις από τα «Στοιχεία»."
        ]
    unanswered.append(
        "Η αποδοχή έγινε στην τοπική συνεδρία, χωρίς επαλήθευση ταυτότητας. Δεν αποτελεί πιστωτική έγκριση."
    )
    return dict(
        status="partial" if unanswered else "answered",
        claims=claims,
        unanswered=unanswered,
        sources=[s for c in claims for s in c["sources"]],
    )


def suggestions(turns: list[dict]) -> list[tuple[str, str]]:
    if not turns:
        return STARTERS
    last = turns[-1]
    if last.get("suggested_questions"):
        return [(q, q) for q in last["suggested_questions"][:3]]
    if last.get("error"):
        return [("Δοκίμασε ξανά", last["question"]), STARTERS[0]]
    names = topics(last.get("resolved_question") or last["question"])
    candidates = []
    if last.get("mode") == "local_checks":
        checks = {c.get("check_id") for c in last.get("claims", [])}
        if "debt_match" in checks:
            candidates.append(("Έλεγχος δανεισμού;", "Υπάρχει απόκλιση στον δανεισμό;"))
        if "turnover_match" in checks:
            candidates.append(("Έλεγχος κύκλου εργασιών;", "Υπάρχει απόκλιση στον κύκλο εργασιών;"))
    if last.get("mode") not in {"local_checks", "local_reviews"} and names:
        for name in names[:1]:
            if name in {"revenue", "ebitda", "net_profit_or_loss", "total_borrowings"}:
                if last.get("status") not in {"not_found", "needs_review"} and not re.search(
                    r"προηγ|περσι", plain(last["question"])
                ):
                    candidates.append(
                        (
                            "Και την προηγούμενη χρήση;",
                            f"Ποιο είναι το {LABELS[name]} της προηγούμενης χρήσης;",
                        )
                    )
                if name in {"revenue", "total_borrowings"}:
                    candidates.append(
                        (
                            "Συμφωνεί με την αίτηση;",
                            "Συμφωνεί ο "
                            + ("κύκλος εργασιών" if name == "revenue" else "δανεισμός")
                            + " μεταξύ αίτησης και καταστάσεων;",
                        )
                    )
            if name in {"requested_amount", "financing_purpose"}:
                candidates.append(
                    ("Ποια είναι η διάρκεια;", "Ποια είναι η διάρκεια της χρηματοδότησης;")
                )
    candidates += STARTERS
    recent = {plain(t["question"]) for t in turns[-3:]}
    return [(label, question) for label, question in candidates if plain(question) not in recent][
        :3
    ]


def related_corrections(turn: dict, view: dict) -> list[dict]:
    """Current corrections shown separately from immutable PDF answers."""
    if turn.get("mode") in {"local_checks", "local_reviews"}:
        return []
    names = set(topics(turn.get("resolved_question") or turn["question"]))
    rows = []
    for doc in view.get("documents", []):
        for name, field in doc["fields"].items():
            if name in names and field.get("status") == "manually_corrected":
                rows.append(
                    dict(
                        kind=doc["type"],
                        field=name,
                        value=field["normalized_value"],
                        sources=source_list(field),
                        approved=field.get("approved_for_credit_memo", False),
                    )
                )
    return rows
