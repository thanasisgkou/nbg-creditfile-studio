"""Exact layout-cell completion, including source lines across chunk boundaries."""

import re
from .parsing import normalized_text
from .schemas import Block, Evidence
from .numeric_evidence import fold

LABELS = {
    "business_activity": r"δραστηριοτητα|δραστηριοτητας|business activity|business_activity",
    "financing_purpose": r"σκοπος χρηματοδοτησης|financing purpose|financing_purpose|purpose",
    "company_legal_name": r"επωνυμια|company|company_legal_name",
    "legal_form": r"νομικη μορφη|μορφη οντοτητας|legal form|legal_form",
}


def complete_cell(
    raw: str,
    evidence: list[Evidence],
    blocks: list[Block],
    pages: list[str],
    field: str = "financing_purpose",
) -> tuple[str, list[Evidence], bool]:
    """Expand only a cited, exact prefix of a uniquely located two-column cell.

    Never join pages, blank-separated paragraphs, new labels or other columns.
    The stored original proposal remains available separately for audit.
    """
    value = normalized_text(raw)
    candidates = []
    for e in evidence:
        if not 1 <= e.page <= len(pages):
            continue
        lines = pages[e.page - 1].splitlines()
        for index, line in enumerate(lines):
            cells = list(re.finditer(r"\S(?:.*?\S)?(?=\s{2,}|$)", line))
            if len(cells) != 2:
                continue
            if not re.search(LABELS.get(field, r"(?!)"), fold(cells[0].group())):
                continue
            first = normalized_text(cells[1].group())
            quote = normalized_text(e.quote)
            if (
                not quote
                or quote not in normalized_text(line)
                or not (first in quote or quote in first)
            ):
                continue
            # Both the value and the continuation must be in the right column.
            column = cells[1].start()
            pieces = [first]
            physical = [line.strip()]
            for following in lines[index + 1 : index + 4]:
                if not following.strip():
                    break
                indent = len(following) - len(following.lstrip())
                if abs(indent - column) > 3 or re.search(r"\s{2,}", following.strip()):
                    break
                pieces.append(following.strip())
                physical.append(following.strip())
            full = normalized_text(" ".join(pieces))
            if full != value and not full.startswith(value + " "):
                continue
            refs = []
            for text in physical:
                matches = [
                    b
                    for b in blocks
                    if b.document_id == e.document_id
                    and b.page == e.page
                    and any(
                        normalized_text(x) == normalized_text(text) for x in b.text.splitlines()
                    )
                ]
                if not matches:
                    break
                block = next((b for b in matches if b.block_id == e.block_id), matches[0])
                refs.append(
                    Evidence(
                        document_id=e.document_id, page=e.page, block_id=block.block_id, quote=text
                    )
                )
            if len(refs) == len(physical):
                candidates.append((e.page, index, full, refs))
    unique = {(p, i): (v, refs) for p, i, v, refs in candidates}
    if len(unique) == 1:
        full, refs = next(iter(unique.values()))
        return full, refs, True
    return raw, evidence, False
