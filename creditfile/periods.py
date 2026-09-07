"""Normalize explicit reporting ranges; never infer a start from a lone year."""

from datetime import date, datetime
import re
import unicodedata

MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "ιανουαριου",
            "φεβρουαριου",
            "μαρτιου",
            "απριλιου",
            "μαιου",
            "ιουνιου",
            "ιουλιου",
            "αυγουστου",
            "σεπτεμβριου",
            "οκτωβριου",
            "νοεμβριου",
            "δεκεμβριου",
        ),
        1,
    )
}


def reporting_period(raw: str) -> str:
    """Accept existing numeric dates and a bounded Greek written date range.

    In "1 Ιανουαρίου – 31 Δεκεμβρίου 2024", the trailing year qualifies
    both explicitly printed endpoints. A year crossing is accepted only when
    both years are printed. This function does not validate source identity;
    the extraction layer still requires the literal raw range in valid quotes.
    """
    numeric = re.findall(r"\d{2}[/.]\d{2}[/.]\d{4}", raw)
    if len(numeric) == 2:
        start, end = [datetime.strptime(v.replace(".", "/"), "%d/%m/%Y").date() for v in numeric]
    else:
        text = " ".join(
            "".join(
                c
                for c in unicodedata.normalize("NFD", raw.lower())
                if unicodedata.category(c) != "Mn"
            ).split()
        )
        month = "(?:" + "|".join(MONTHS) + ")"
        match = re.fullmatch(
            rf"(?:χρηση\s+)?(?P<sd>\d{{1,2}})\s+(?P<sm>{month})"
            rf"(?:\s+(?P<sy>\d{{4}}))?\s*(?:[-–—]|εως|μεχρι)\s*"
            rf"(?P<ed>\d{{1,2}})\s+(?P<em>{month})\s+(?P<ey>\d{{4}})\.?",
            text,
        )
        if not match:
            raise ValueError("Η περίοδος απαιτεί ημερομηνία αρχής και τέλους.")
        start = date(int(match["sy"] or match["ey"]), MONTHS[match["sm"]], int(match["sd"]))
        end = date(int(match["ey"]), MONTHS[match["em"]], int(match["ed"]))
    if start >= end or (end - start).days > 366:
        raise ValueError("Μη έγκυρη περίοδος αναφοράς.")
    return start.isoformat() + "/" + end.isoformat()
