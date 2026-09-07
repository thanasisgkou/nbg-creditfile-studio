import re
from decimal import Decimal, InvalidOperation
from .parsing import normalized_text
from .schemas import MONEY


class CitationValidationError(ValueError):
    """Content-free diagnostic code; callers must still reject the answer."""

    def __init__(self, code: str):
        self.code = code
        super().__init__("Μη έγκυρη παραπομπή ή απόσπασμα εκτός φακέλου/context.")


def validate_evidence(evidence, blocks, case_id):
    allowed = {b.block_id: b for b in blocks if b.case_id == case_id}
    for source in evidence:
        block = allowed.get(source.block_id)
        if block is None:
            raise CitationValidationError("source_outside_context")
        if block.document_id != source.document_id or block.page != source.page:
            raise CitationValidationError("source_identity_mismatch")
        if not normalized_text(source.quote):
            raise CitationValidationError("empty_quote")
        if normalized_text(source.quote) not in normalized_text(block.text):
            raise CitationValidationError("quote_not_in_source")


def amount(raw, locale, multiplier):
    text = raw.strip().replace("\u2212", "-").replace("\u00a0", " ").replace("\u202f", " ")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1].strip()
        if text.startswith(("-", "+")):
            raise ValueError("Αντικρουόμενα πρόσημα ποσού.")
    if text.startswith("+"):
        text = text[1:]
    if " " in text:
        if not re.fullmatch(r"-?\d{1,3}(?: \d{3})+(?:[.,]\d{1,2})?", text):
            raise ValueError("Μη έγκυρη ομαδοποίηση χιλιάδων.")
        text = text.replace(" ", "")
    if locale == "unknown" and ("," in text or "." in text):
        # Multiple complete groups cannot be a decimal separator. A single
        # separator (e.g. 1.500) remains ambiguous without document context.
        if re.fullmatch(r"-?\d{1,3}(?:\.\d{3}){2,}", text):
            locale = "el"
        elif re.fullmatch(r"-?\d{1,3}(?:,\d{3}){2,}", text):
            locale = "en"
        else:
            raise ValueError("Αμφίσημη μορφή αριθμού.")
    if locale == "el":
        pattern = r"-?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?"
        if not re.fullmatch(pattern, text):
            raise ValueError("Μη έγκυρος ελληνικός αριθμός.")
        text = text.replace(".", "").replace(",", ".")
    elif locale == "en":
        if not re.fullmatch(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?", text):
            raise ValueError("Μη έγκυρος αγγλικός αριθμός.")
        text = text.replace(",", "")
    elif not re.fullmatch(r"-?\d+", text):
        raise ValueError("Μη έγκυρος αριθμός.")
    if multiplier not in {"1", "1000"}:
        raise ValueError("Λείπει τεκμηριωμένη μονάδα.")
    try:
        value = Decimal(text) * Decimal(multiplier) * (-1 if negative else 1)
        return format(value.quantize(Decimal("0.01")), "f")
    except InvalidOperation as exc:
        raise ValueError("Μη έγκυρο ποσό.") from exc


def normalize_candidate(candidate):
    raw = candidate.raw_value.strip()
    quotes = " ".join(normalized_text(e.quote) for e in candidate.evidence)
    if normalized_text(raw) not in quotes:
        raise ValueError("Η αυθεντική τιμή δεν εντοπίζεται στα αποσπάσματα.")
    if not candidate.entity or normalized_text(candidate.entity) not in quotes:
        raise ValueError("Λείπει πηγή εταιρείας.")
    if not any(
        normalized_text(e.quote) == normalized_text(candidate.entity)
        or re.search(
            r"(?:Επωνυμία|Εταιρεία|Company)\s*:\s*" + re.escape(normalized_text(candidate.entity)),
            normalized_text(e.quote),
            re.IGNORECASE,
        )
        for e in candidate.evidence
    ):
        raise ValueError("Η εταιρεία δεν συνδέεται με επικεφαλίδα επωνυμίας.")
    if candidate.financial_year is not None and str(candidate.financial_year) not in quotes:
        raise ValueError("Λείπει πηγή χρήσης.")
    if candidate.field_key in MONEY:
        lower = quotes.lower()
        if candidate.currency != "EUR" or not any(s in lower for s in ("ευρώ", "ευρω", "eur", "€")):
            raise ValueError("Λείπει τεκμηρίωση νομίσματος.")
        thousands = bool(
            re.search(
                r"(?:σε\s+)?χιλι[άα]δες\s+ευρ[ώω]|thousands?\s+(?:of\s+)?(?:euros?|eur)", lower
            )
        )
        if (
            candidate.unit_multiplier == "1000"
            and not thousands
            or candidate.unit_multiplier == "1"
            and thousands
        ):
            raise ValueError("Μη τεκμηριωμένος ή ασυνεπής πολλαπλασιαστής.")
        numeric = re.sub(r"\s*(?:ευρώ|ευρω|eur|€)(?:\s*\(EUR\))?\s*$", "", raw, flags=re.I).strip()
        numeric = re.sub(r"^(?:EUR|€)\s*", "", numeric, flags=re.I)
        return amount(numeric, candidate.number_locale, candidate.unit_multiplier)
    if candidate.field_key == "duration_months":
        match = re.fullmatch(
            r"(\d+)\s*(μήνες|μηνες|μήνα|έτη|ετη|χρόνια|years|months)?", raw.lower()
        )
        if not match:
            raise ValueError("Ασαφής διάρκεια.")
        count = int(match[1])
        unit = match[2]
        if unit is None:
            raise ValueError("Λείπει μονάδα διάρκειας στην αυθεντική τιμή.")
        return str(count * 12 if unit in {"έτη", "ετη", "χρόνια", "years"} else count)
    if candidate.field_key == "financial_year":
        end_date = re.fullmatch(r"31[./]12[./](20\d{2})", raw)
        year = end_date[1] if end_date else raw
        if not re.fullmatch(r"20\d{2}", year) or int(year) != candidate.financial_year:
            raise ValueError("Ασαφής οικονομική χρήση.")
        return year
    return raw
