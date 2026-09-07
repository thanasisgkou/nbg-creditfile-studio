"""Local folder discovery and tentative case names. No inference or gold data."""

import re
from .config import Settings
from .parsing import parse_pdf
from .extraction import document_titles, inspect_document, plain
from .checks import company_key


def discover(files: list[dict], settings: Settings) -> dict:
    pdfs = [f for f in files if f["name"].lower().endswith(".pdf")]
    if len(pdfs) > 30 or sum(len(f["content"]) for f in pdfs) > 100 * 1024 * 1024:
        raise ValueError("Επίλεξε έναν πιστωτικό φάκελο: έως 30 PDF και 100 MB συνολικά.")
    items = []
    warnings = []
    for index, f in enumerate(pdfs):
        try:
            parsed = parse_pdf(f["content"], "import", str(index), "application", settings)
            readable = [
                p for i, p in enumerate(parsed["pages"], 1) if i not in parsed["unreadable_pages"]
            ]
            titles = document_titles(readable[0]) if readable else set()
            kind = next(iter(titles)) if len(titles) == 1 else None
            if kind:
                inspect_document(f["content"], f["name"], kind, settings, "import")
            items.append(
                {
                    **f,
                    "id": str(index),
                    "kind": kind,
                    "status": parsed["status"],
                    "pages": parsed["pages"],
                }
            )
            if not kind:
                warnings.append(
                    f"{f['name']}: ο τύπος δεν αναγνωρίστηκε αυτόματα. Μπορείς να το επιλέξεις χειροκίνητα."
                )
        except ValueError as exc:
            warnings.append(f"{f['name']}: {exc}")
    return {"items": items, "warnings": warnings}


def company_names(pages: list[str], name: str) -> list[dict]:
    found = []
    label = r"(?:επωνυμια(?:\s+(?:επιχειρησης|εταιρειας|αιτουσας(?:\s+επιχειρησης)?))?|company\s+(?:legal\s+)?name|legal\s+name)"
    for page, text in enumerate(pages, 1):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for i, line in enumerate(lines):
            # Match the normalized label, but retain the original company text.
            match = re.match("^" + label + r"\s*(?::|\s{2,})\s*(.+)$", plain_preserving_gaps(line))
            value = None
            if match:
                # Normalization strips accents only and keeps character lengths
                # for the ordinary Greek/Latin labels used by these PDFs.
                parts = re.split(r":|\s{2,}", line, maxsplit=1)
                if len(parts) == 2:
                    value = parts[1].strip()
            elif re.fullmatch(label + r"\s*:?", " ".join(plain(line).split())) and i + 1 < len(
                lines
            ):
                value = lines[i + 1]
            if not value:
                continue
            value = re.split(r"\s{2,}|\s+[|·]\s+", value)[0].strip()
            folded = plain(value).strip(" .:-")
            if not 3 <= len(value) <= 100 or ":" in value or not any(c.isalpha() for c in value):
                continue
            if folded in {"δεν συμπληρωθηκε", "δεν αναφερεται", "n/a", "not provided", "—"}:
                continue
            if re.match(r"^(?:α\.?φ\.?μ|αριθμος|νομικη μορφη|συνθετικα δεδομενα)", folded):
                continue
            found.append(dict(value=value, document=name, page=page, excerpt=line))
    return found


def plain_preserving_gaps(text: str) -> str:
    import unicodedata

    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn"
    )


def prepare_name(inputs: list[dict], settings: Settings) -> dict:
    names = []
    for item in inputs:
        doc = inspect_document(
            item["content"], item["name"], item["type"], settings, "import-confirm"
        )
        if doc.get("preflight_error") or doc.get("unreadable_pages"):
            raise ValueError(
                doc.get("preflight_error")
                or "Υπάρχουν μη αναγνώσιμες σελίδες. Απαιτείται manual review ή αναγνώσιμο PDF."
            )
        names += company_names(doc["pages"], doc["name"])
    unique = {company_key(n["value"]): n for n in names}
    return dict(
        inputs=inputs,
        suggested_name=next(iter(unique.values()))["value"] if len(unique) == 1 else "",
        name_sources=list(unique.values()),
        name_conflict=len(unique) > 1,
    )
