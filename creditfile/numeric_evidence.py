"""Whole-token numeric evidence, bound to the quoted physical source row.

This is conservative evidence validation, not a general financial table parser.
No guessed locale, sign, scale, missing digits or arithmetic reconstruction.
"""

from decimal import Decimal
import re
import unicodedata
from .parsing import normalized_text
from .validation import amount

# Single spaces can group thousands; wide layout gaps separate table columns.
NUMBER = r"(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d+)*)"
CURRENCY = r"(?:EUR|ευρώ|ευρω|€)"
SIGNED = r"(?:[+−-]\s*(?:" + CURRENCY + r"\s*)?)?" + NUMBER
TOKEN = re.compile(
    r"(?<![\w.,+\-−])(?:\(\s*(?:"
    + CURRENCY
    + r"\s*)?"
    + SIGNED
    + r"(?:\s*"
    + CURRENCY
    + r")?\s*\)|"
    + SIGNED
    + r")(?![\d.,])",
    re.I,
)
DATE = re.compile(r"\b(?:\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}|\d{4}-\d{2}-\d{2})\b")
ROWS = {
    "requested_amount": r"αιτουμ|αιτειται|requested|amount requested",
    "declared_annual_turnover": r"κυκλ\w*\s+εργασι|τζιρ|turnover|revenue",
    "declared_existing_debt": r"δανεισ|debt|borrow",
    "revenue": r"κυκλ\w*\s+εργασι|πωλησ|revenue|turnover|εσοδα\s+απο\s+συμβασεις\s+με\s+πελατες",
    "ebitda": r"\bebitda\b",
    "net_profit_or_loss": r"καθαρ\w*\s+(?:αποτελεσ|κερδ|ζημι)|net\s+(?:profit|loss|income)|αποτελεσ\w*.*μετα.*φορ|κερδ\w*\s*/\s*\(ζημι\w*\)\s+μετα\s+(?:απο\s+)?φορ",
    "total_assets": r"συνολ\w*\s+(?:στοιχει\w*\s+)?ενεργητικ|συνολο\s+ενεργητικ|total\s+assets|συνολο\s+περιουσιακων\s+στοιχειων",
    "total_liabilities": r"συνολ\w*\s+υποχρεωσ|συνολο\s+υποχρεωσ|total\s+liabilities",
    "total_equity": r"(?:συνολο\s+)?ιδι\w*\s+κεφαλ|καθαρη\s+θεση|total\s+equity|συνολο\s+καθαρης\s+θεσης",
    "total_borrowings": r"(?:συνολ\w*|συνολο).*δανεισ|δανεισ\w*\s*\(συνολο\)|total.*(?:borrow|debt)|total bank loans",
    "tenor_months": r"διαρκ|tenor|duration",
}


def fold(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn"
    ).replace("_", " ")


def numeric_part(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("(") and raw.endswith(")"):
        return "(" + numeric_part(raw[1:-1]) + ")"
    raw = re.sub(r"^([+−-]?)\s*(?:EUR|€)\s*", r"\1", raw, flags=re.I)
    raw = re.sub(
        r"\s*(?:EUR|ευρώ|ευρω|€|μήνες|μηνες|months|έτη|ετη|years)\s*$", "", raw, flags=re.I
    ).strip()
    return re.sub(r"^([+−-])\s+", r"\1", raw)


def token_value(raw: str, locale: str) -> Decimal:
    return Decimal(amount(numeric_part(raw), locale, "1"))


def column_header(line: str, previous: str, position: int, field: str) -> str:
    """Use only an aligned, immediate multi-column header for this value cell."""
    headers = list(re.finditer(r"\S(?:.*?\S)?(?=\s{2,}|$)", previous))
    cells = list(re.finditer(r"\S(?:.*?\S)?(?=\s{2,}|$)", line))
    if len(headers) < 2 or len(headers) != len(cells):
        return ""
    for cell, header in zip(cells, headers):
        if cell.start() <= position < cell.end() and abs(cell.start() - header.start()) <= 3:
            text = fold(header.group())
            if re.search(ROWS.get(field, r"(?!)"), text) and not re.search(r"χαριτ|grace", text):
                return header.group()
    return ""


def row_context(lines: list[str], index: int, token: re.Match, field: str) -> tuple[str, str]:
    """Return field label context and an explicitly printed column unit."""
    line = lines[index]
    context = fold(normalized_text(line))
    pattern = ROWS.get(field)
    previous = lines[index - 1] if index else ""
    header = column_header(line, previous, token.start(), field)
    if header:
        unit = re.search(r"μήνες|μηνες|months|έτη|ετη|years", header, re.I)
        return fold(header), unit.group() if unit else ""
    if (
        field in {"requested_amount", "tenor_months"}
        and re.search(r"\s{2,}", previous.strip())
        and re.search(r"αιτουμ|requested", fold(previous))
    ):
        return "", ""  # A different column (e.g. grace) must not borrow the tenor label.
    if (
        field == "tenor_months"
        and re.search(r"περιοδο\w*\s+χαριτ|grace\s+period", context)
        and not re.search(r"συνολικ\w*\s+διαρκ|total\s+(?:tenor|duration)", context)
    ):
        return "", ""
    if not pattern or re.search(pattern, context):
        return context, ""
    # A wrapped narrative total: only the first value immediately after an
    # unfinished "amounts to" label, never the later component amounts.
    before = line[: token.start()].strip()
    if (
        not before
        and re.search(pattern, fold(previous))
        and re.search(r"(?:ανερχεται σε|amounts? to)\s*$", fold(previous))
    ):
        return fold(previous), ""
    if not re.search(r"[A-Za-zΑ-Ωα-ω]", numeric_part(normalized_text(line))) and re.search(
        pattern, fold(previous)
    ):
        return fold(previous), ""
    return "", ""


def numeric_context_citations(evidence, blocks, field):
    """Attach the actual preceding header/label used by numeric validation."""
    from .schemas import Evidence

    result = list(evidence)
    by_id = {b.block_id: b for b in blocks}
    for e in evidence:
        block = by_id.get(e.block_id)
        if not block:
            continue
        lines = block.text.splitlines()
        quote = normalized_text(e.quote)
        for index, line in enumerate(lines):
            if not quote or quote not in normalized_text(line):
                continue
            if (
                index + 1 < len(lines)
                and re.search(ROWS[field], fold(line))
                and re.search(r"(?:ανερχεται σε|amounts? to)\s*$", fold(line))
            ):
                following = lines[index + 1]
                first = TOKEN.match(following.lstrip())
                if first:
                    ref = Evidence(
                        document_id=e.document_id,
                        page=e.page,
                        block_id=e.block_id,
                        quote=following.strip(),
                    )
                    if ref not in result:
                        result.append(ref)
            if not index:
                continue
            if any(
                column_header(line, lines[index - 1], t.start(), field)
                or row_context(lines, index, t, field)[0]
                and not re.search(ROWS[field], fold(line))
                for t in TOKEN.finditer(line)
            ):
                ref = Evidence(
                    document_id=e.document_id,
                    page=e.page,
                    block_id=e.block_id,
                    quote=lines[index - 1].strip(),
                )
                if ref.quote and ref not in result:
                    result.append(ref)
    return result


def tenor_unit(raw: str, evidence: list[dict], blocks: dict[str, str], locale: str) -> str | None:
    units = set()
    for e in evidence:
        lines = blocks.get(e["block_id"], "").splitlines()
        for index, line in enumerate(lines):
            if normalized_text(e["quote"]) not in normalized_text(line):
                continue
            for token in TOKEN.finditer(line):
                try:
                    if token_value(token.group(), locale) != token_value(raw, locale):
                        continue
                except ValueError:
                    continue
                context, unit = row_context(lines, index, token, "tenor_months")
                if not context:
                    continue
                adjacent = re.match(
                    r"\s*(μήνες|μηνες|months|έτη|ετη|years)\b", line[token.end() :], re.I
                )
                if adjacent:
                    units.add(fold(adjacent[1]))
                elif unit:
                    units.add(fold(unit))
    return next(iter(units)) if len(units) == 1 else None


def numeric_supported(
    raw: str, evidence: list[dict], blocks: dict[str, str], locale: str, field: str | None = None
) -> bool:
    """Require a complete signed token inside a valid quote and its source row.

    Amount-only quotes cannot borrow a label from another row in the block.
    A numeric-only continuation may use its immediately preceding label line.
    Unknown labels stay reviewable instead of pretending semantic proof.
    """
    try:
        expected = token_value(raw, locale)
    except ValueError:
        return False
    for e in evidence:
        source = blocks.get(e["block_id"], "")
        # Preserve physical rows while normalizing only whitespace within rows.
        lines = source.splitlines()
        flat = normalized_text(source)
        quote = normalized_text(e["quote"])
        spans = (
            [(m.start(), m.start() + len(quote)) for m in re.finditer(re.escape(quote), flat)]
            if quote
            else []
        )
        offset = 0
        for index, line in enumerate(lines):
            text = normalized_text(line)
            if not text:
                continue
            dates = [m.span() for m in DATE.finditer(text)]
            # Tokenize the physical row BEFORE collapsing wide column gaps.
            for token in TOKEN.finditer(line):
                start = len(normalized_text(line[: token.start()]))
                if start and line[: token.start()].endswith((" ", "\t", "\u00a0", "\u202f")):
                    start += 1
                end = start + len(normalized_text(token.group()))
                if any(a <= start < b for a, b in dates):
                    continue
                if not any(a <= offset + start and offset + end <= b for a, b in spans):
                    continue  # A partial quote must not conceal a sign or grouping.
                if re.match(r"\s*%", line[token.end() :]):
                    continue  # Percentages are not amounts or loan months.
                try:
                    if token_value(token.group(), locale) != expected:
                        continue
                except ValueError:
                    continue
                context, header_unit = row_context(lines, index, token, field)
                if not context:
                    continue
                if field in {"total_liabilities", "total_equity"} and re.search(
                    r"ιδι\w*\s+κεφαλ.*υποχρεωσ|equity\s+and\s+liabilities|υποχρεωσ.*ιδι\w*\s+κεφαλ|υποχρεωσ.*καθαρης\s+θεσης|καθαρης\s+θεσης.*υποχρεωσ",
                    context,
                ):
                    continue  # The combined total is neither component.
                if field == "tenor_months":
                    unit = re.search(r"(μήνες|μηνες|months|έτη|ετη|years)\s*$", raw, re.I)
                    adjacent = re.match(
                        r"\s*(μήνες|μηνες|months|έτη|ετη|years)\b", line[token.end() :], re.I
                    )
                    actual_unit = adjacent[1] if adjacent else header_unit
                    if not actual_unit or unit and fold(unit[1]) != fold(actual_unit):
                        continue
                return True
            offset += len(text) + 1
    return False
