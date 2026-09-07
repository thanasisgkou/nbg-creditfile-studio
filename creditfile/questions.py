"""Ten grounded readouts of stored extraction and deterministic checks. No LLM."""

from .schema import QUESTIONS, LABELS, MONEY
from .checks import source_list, usable

MAPPING = {
    0: [("application", "company_legal_name"), ("application", "tax_id")],
    1: [("application", "requested_amount")],
    2: [("application", "financing_purpose"), ("application", "tenor_months")],
    3: [("financials", "revenue")],
    4: [("financials", "ebitda")],
    5: [("financials", "net_profit_or_loss")],
    6: [
        ("financials", "total_assets"),
        ("financials", "total_liabilities"),
        ("financials", "total_equity"),
    ],
    7: [("financials", "total_borrowings")],
}


def answer_predefined(result: dict, index: int, reviews: list[dict] | None = None) -> dict:
    if not 0 <= index < len(QUESTIONS):
        raise ValueError("Μόνο οι δέκα προκαθορισμένες ερωτήσεις υποστηρίζονται.")
    docs = {d["type"]: d for d in result["documents"]}
    claims = []
    unanswered = []
    unanswered_evidence = []
    decisions = {(e["document_type"], e["field"]): e["review_decision"] for e in reviews or []}
    if index in MAPPING:
        for kind, name in MAPPING[index]:
            f = docs[kind]["fields"][name]
            if not usable(f):
                unanswered.append(f"{LABELS[name]}: {f['review_reason'] or f['status']}")
                unanswered_evidence += source_list(f)
                continue
            value = f["normalized_value"]
            suffix = " EUR" if name in MONEY else " μήνες" if name == "tenor_months" else ""
            period = docs[kind]["fields"].get("reporting_period")
            period_text = (
                f" · Περίοδος {period['normalized_value']}"
                if period and usable(period) and name in MONEY
                else ""
            )
            evidence = source_list(f)
            if name in MONEY:
                for extra in ["currency", "unit_scale", "reporting_period"]:
                    evidence += source_list(docs[kind]["fields"].get(extra))
            claims.append(
                dict(
                    text=f"{LABELS[name]}: {value}{suffix}{period_text}",
                    evidence=evidence,
                    confidence=f["confidence"],
                    review_status=decisions.get((kind, name), f["review_status"]),
                )
            )
    elif index == 8:
        c = next(c for c in result["checks"] if c["check_id"] == "turnover_match")
        if c["status"] == "NOT_CHECKED":
            unanswered.append(c["explanation"])
        else:
            percentage = (
                f"{c['percentage_difference']:.2f}%"
                if c["percentage_difference"] is not None
                else "μη ορισμένη (μηδενική βάση)"
            )
            claims.append(
                dict(
                    text=f"{c['status']}: Αίτηση {c['left_value']} EUR / Καταστάσεις {c['right_value']} EUR. Απόλυτη διαφορά {c['absolute_difference']} EUR, ποσοστιαία {percentage}. {c['explanation']}",
                    evidence=c["evidence"],
                    confidence=None,
                    review_status="pending",
                )
            )
    else:
        for kind, doc in docs.items():
            for name, f in doc["fields"].items():
                if f["requires_review"]:
                    text = f"{kind} / {LABELS[name]}: {f['status']} - {f['review_reason']}"
                    if source_list(f):
                        claims.append(
                            dict(
                                text=text,
                                evidence=source_list(f),
                                confidence=f["confidence"],
                                review_status=f["review_status"],
                            )
                        )
                    else:
                        unanswered.append(text)
        for c in result["checks"]:
            if c["status"] == "FAIL" and c["check_id"] in {
                "turnover_match",
                "debt_match",
                "company_match",
                "tax_id_match",
                "currency_match",
                "accounting_equation",
            }:
                claims.append(
                    dict(
                        text=f"{c['check_id']}: {c['left_value']} / {c['right_value']}. {c['explanation']}",
                        evidence=c["evidence"],
                        confidence=None,
                        review_status="pending",
                    )
                )
        if not claims and not unanswered:
            unanswered.append(
                "Δεν εντοπίστηκαν αποκλίσεις στους προκαθορισμένους ελέγχους. Η ανθρώπινη επαλήθευση και η κατάσταση προετοιμασίας εμφανίζονται χωριστά στον Έλεγχο και στο Δελτίο."
            )
    return dict(
        question=QUESTIONS[index],
        status="partial" if claims and unanswered else "answered" if claims else "not_found",
        claims=claims,
        unanswered=unanswered,
        unanswered_evidence=unanswered_evidence,
        engine="deterministic stored evidence",
        llm_calls=0,
        uses_original_documents=True,
    )
