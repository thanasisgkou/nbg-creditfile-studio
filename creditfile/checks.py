"""Reproducible comparisons in Python/Decimal, with both sides' evidence."""

from dataclasses import dataclass
from decimal import Decimal
import os
import re
import unicodedata
from .schema import MONEY


@dataclass(frozen=True)
class Tolerances:
    absolute: Decimal = Decimal("1000")
    relative: Decimal = Decimal("0.01")
    critical_confidence: float = 0.8

    @classmethod
    def load(cls) -> "Tolerances":
        env = os.environ
        result = cls(
            Decimal(env.get("CHECK_ABS_TOLERANCE", "1000")),
            Decimal(env.get("CHECK_REL_TOLERANCE", "0.01")),
            float(env.get("CRITICAL_CONFIDENCE_THRESHOLD", ".8")),
        )
        if (
            not result.absolute.is_finite()
            or not result.relative.is_finite()
            or min(result.absolute, result.relative) < 0
            or not 0 <= result.critical_confidence <= 1
        ):
            raise ValueError("Invalid comparison tolerances")
        return result


def usable(field: dict | None) -> bool:
    return bool(
        field
        and field["status"] in {"extracted", "manually_corrected"}
        and field.get("review_status") != "unresolved"
        and field.get("evidence_basis") != "manual_without_documentation"
        and field["normalized_value"] is not None
    )


def source_list(field: dict | None) -> list[dict]:
    if not field:
        return []
    return ([field["evidence"]] if field.get("evidence") else []) + field.get(
        "supporting_evidence", []
    )


def company_key(value: str) -> str:
    text = "".join(
        c for c in unicodedata.normalize("NFD", value.casefold()) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^\w]", "", text)


def compare(
    check_id: str,
    left: dict | None,
    right: dict | None,
    tolerance: Tolerances,
    numeric: bool = False,
) -> dict:
    result = dict(
        check_id=check_id,
        status="NOT_CHECKED",
        left_value=left.get("normalized_value") if left else None,
        right_value=right.get("normalized_value") if right else None,
        absolute_difference=None,
        percentage_difference=None,
        explanation="Ανεπαρκείς ή μη επικυρωμένες τιμές. Απαιτείται έλεγχος αναλυτή.",
        evidence=source_list(left) + source_list(right),
        requires_review=True,
    )
    if not usable(left) or not usable(right):
        return result
    if any(f.get("evidence_basis") == "manual_without_documentation" for f in (left, right)):
        result["explanation"] = (
            "Υπάρχει χειροκίνητη τιμή χωρίς τεκμηριωμένη πηγή. Η σύγκριση εκκρεμεί μέχρι να τεκμηριωθεί."
        )
        return result
    a, b = result["left_value"], result["right_value"]
    if numeric:
        a, b = Decimal(str(a)), Decimal(str(b))
        diff = abs(a - b)
        pct = diff / abs(b) if b else None
        result.update(
            absolute_difference=float(diff),
            percentage_difference=float(pct * 100) if pct is not None else None,
        )
        same = diff <= max(tolerance.absolute, abs(b) * tolerance.relative)
    else:
        same = company_key(str(a)) == company_key(str(b)) if check_id == "company_match" else a == b
    result.update(
        status="PASS" if same else "FAIL",
        requires_review=not same,
        explanation="Οι τιμές συμφωνούν εντός της επιλεγμένης ανοχής."
        if same
        else "Οι τεκμηριωμένες τιμές διαφέρουν. Απαιτείται αντιπαραβολή από αναλυτή.",
    )
    return result


def run_checks(documents: list[dict], tolerance: Tolerances | None = None) -> list[dict]:
    tolerance = tolerance or Tolerances.load()
    by_kind = {d["type"]: d["fields"] for d in documents}
    app, fin = by_kind.get("application", {}), by_kind.get("financials", {})
    checks = []
    for name, a, b, numeric in [
        ("company_match", "company_legal_name", "company_legal_name", False),
        ("tax_id_match", "tax_id", "tax_id", False),
        ("currency_match", "currency", "currency", False),
        ("turnover_match", "declared_annual_turnover", "revenue", True),
        ("debt_match", "declared_existing_debt", "total_borrowings", True),
    ]:
        c = compare(name, app.get(a), fin.get(b), tolerance, numeric)
        if numeric and (
            not usable(app.get("currency"))
            or not usable(fin.get("currency"))
            or app["currency"]["normalized_value"] != fin["currency"]["normalized_value"]
        ):
            c.update(
                status="NOT_CHECKED",
                requires_review=True,
                absolute_difference=None,
                percentage_difference=None,
                explanation="Δεν συγκρίνονται ποσά χωρίς κοινό τεκμηριωμένο νόμισμα.",
            )
        if numeric and any(
            p["status"] != "PASS"
            for p in checks
            if p["check_id"] in {"company_match", "tax_id_match"}
        ):
            c.update(
                status="NOT_CHECKED",
                requires_review=True,
                absolute_difference=None,
                percentage_difference=None,
                explanation="Πρώτα απαιτείται αντιστοίχιση εταιρείας και ΑΦΜ.",
            )
        if numeric:
            period = fin.get("reporting_period")
            # The contract assumes comparable standalone annual statements.
            # Do not claim comparability when the explicit evidence contradicts it.
            texts = " ".join(e.get("quote", e.get("excerpt", "")) for e in source_list(app.get(a)))
            years = set(re.findall(r"(?<!\d)20\d{2}(?!\d)", texts))
            end = str(period.get("normalized_value") or "").split("/")[-1] if period else ""
            year = end[:4]
            if not usable(period) or years and years != {year}:
                c.update(
                    status="NOT_CHECKED",
                    requires_review=True,
                    absolute_difference=None,
                    percentage_difference=None,
                    explanation="Η περίοδος δεν τεκμηριώνεται ή οι αναφερόμενες χρήσεις διαφέρουν. Απαιτείται έλεγχος συγκρισιμότητας από αναλυτή.",
                )
            c["comparison_basis"] = (
                "Ίδια εταιρεία και συγκρίσιμη ετήσια περίοδος/εταιρικό scope σύμφωνα με το περιορισμένο contract του PoC. Δεν εκτελείται γενικό reconciliation ομίλου ή ενδιάμεσων χρήσεων."
            )
        checks.append(c)
    assets, liabilities, equity = (
        fin.get(k) for k in ("total_assets", "total_liabilities", "total_equity")
    )
    combined = None
    if usable(liabilities) and usable(equity):
        combined = {
            **liabilities,
            "normalized_value": float(
                Decimal(str(liabilities["normalized_value"]))
                + Decimal(str(equity["normalized_value"]))
            ),
            "supporting_evidence": source_list(liabilities) + source_list(equity),
        }
    checks.append(compare("accounting_equation", assets, combined, tolerance, True))
    for kind, fields in by_kind.items():
        for name, f in fields.items():
            status = (
                "PASS"
                if usable(f)
                else "WARNING"
                if f["status"] in {"missing", "uncertain"}
                else "FAIL"
            )
            checks.append(
                dict(
                    check_id=f"{kind}.{name}.validity",
                    status=status,
                    left_value=f["normalized_value"],
                    right_value=None,
                    absolute_difference=None,
                    percentage_difference=None,
                    explanation=f.get("review_reason")
                    or "Μορφή και πηγή ελέγχθηκαν. Η αποδοχή αναλυτή εκκρεμεί.",
                    evidence=source_list(f),
                    requires_review=status != "PASS",
                )
            )
            if (
                name in MONEY
                and f["confidence"] < tolerance.critical_confidence
                and f.get("review_status") not in {"accepted", "corrected"}
            ):
                checks.append(
                    dict(
                        check_id=f"{kind}.{name}.confidence",
                        status="WARNING",
                        left_value=f["normalized_value"],
                        right_value=None,
                        absolute_difference=None,
                        percentage_difference=None,
                        explanation="Χαμηλή μη βαθμονομημένη ένδειξη βεβαιότητας κρίσιμου ποσού.",
                        evidence=source_list(f),
                        requires_review=True,
                    )
                )
    scale = fin.get("unit_scale")
    checks.append(
        dict(
            check_id="unit_scale",
            status="PASS" if usable(scale) else "NOT_CHECKED",
            left_value=scale.get("normalized_value") if scale else None,
            right_value=None,
            absolute_difference=None,
            percentage_difference=None,
            explanation="Η κλίμακα εφαρμόστηκε με Decimal στο backend."
            if usable(scale)
            else "Λείπει τεκμηριωμένη κλίμακα.",
            evidence=source_list(scale),
            requires_review=not usable(scale),
        )
    )
    return checks
