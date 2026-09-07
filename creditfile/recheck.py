"""Versioned local reassessment; original extraction files stay immutable."""

import copy
from functools import lru_cache
import json
import hashlib
import re
from decimal import Decimal
from .schemas import Block, Evidence
from .extraction import TEXT_CONTINUATIONS, complete_text_citations, raw_supported
from .parsing import normalized_text
from .validation import validate_evidence
from .viewer import source_geometry
from .checks import source_list, run_checks, Tolerances
from .schema import DocumentExtraction, FIELDS
from .extraction import validate_fields
from .schema import MONEY
from .numeric_evidence import numeric_supported

VERSION = "evidence-normalization-v7-explicit-missing"


def revalidate_stored(
    doc: dict, content: bytes, blocks: list[Block], threshold: float
) -> list[dict]:
    """Apply the same validator to saved evidence; never call AI or alter raw runs."""
    proposals = []
    originals = {p["field_name"]: p for p in doc.get("original_proposal", {}).get("fields", [])}
    for name in FIELDS[doc["type"]]:
        f = doc["fields"][name]
        original = originals.get(name, {})
        refs = source_list(f)
        proposals.append(
            dict(
                field_name=name,
                raw_value=f.get("raw_value"),
                confidence=f["confidence"],
                number_locale=f.get(
                    "number_locale", original.get("number_locale", document_locale(doc))
                ),
                uncertainty=f.get("uncertainty", original.get("uncertainty")),
                evidence=[
                    {k: e[k] for k in ("document_id", "page", "block_id", "quote")} for e in refs
                ],
            )
        )
    checked = validate_fields(
        DocumentExtraction(document_type=doc["type"], fields=proposals),
        doc,
        content,
        blocks,
        threshold,
    )
    events = []
    for name, f in doc["fields"].items():
        fixed = checked[name]
        if (
            f.get("review_status") in {"accepted", "corrected", "unresolved"}
            or f["status"] == "manually_corrected"
        ):
            continue
        if (f["normalized_value"], f["status"], f.get("raw_value")) == (
            fixed["normalized_value"],
            fixed["status"],
            fixed.get("raw_value"),
        ):
            continue
        # A partial/scanned document never becomes automatically readable.
        if doc.get("status") not in {"readable", None}:
            continue
        original = copy.deepcopy(f)
        fixed["validation_note"] = (
            "Επανέλεγχος των αποθηκευμένων πηγών με τον ενημερωμένο validator. Εκκρεμεί ανθρώπινη επιβεβαίωση."
        )
        doc["fields"][name] = fixed
        events.append(
            dict(
                version=VERSION,
                document_type=doc["type"],
                field=name,
                original_field=original,
                revalidated_value=fixed["normalized_value"],
                reason=fixed["validation_note"],
            )
        )
    return events


def document_locale(doc: dict) -> str:
    """Legacy runs did not save locale. Require unambiguous document examples."""
    text = " ".join(b["text"] for b in doc.get("blocks", []))
    conventions = set()
    if re.search(r"(?<![\d.,])\d{1,3}(?:\.\d{3}){2,}(?![\d.,])", text):
        conventions.add("el")
    if re.search(r"(?<![\d.,])\d{1,3}(?:,\d{3}){2,}(?![\d.,])", text):
        conventions.add("en")
    return next(iter(conventions)) if len(conventions) == 1 else "unknown"


def repair_currency_dependents(
    doc: dict, content: bytes, blocks: list, threshold: float
) -> list[dict]:
    """Replay only the known currency-parser rejection through the full validator."""
    targets = [
        n
        for n, f in doc["fields"].items()
        if f["status"] == "invalid"
        and (f.get("review_reason") or "").startswith("Μη υποστηριζόμενο νόμισμα")
    ]
    if not targets:
        return []
    locale = document_locale(doc)
    proposals = []
    for n in FIELDS[doc["type"]]:
        f = doc["fields"][n]
        proposals.append(
            dict(
                field_name=n,
                raw_value=f.get("raw_value"),
                confidence=f["confidence"],
                number_locale=f.get("number_locale", locale),
                uncertainty=f.get("uncertainty"),
                evidence=[
                    {k: e[k] for k in ("document_id", "page", "block_id", "quote")}
                    for e in source_list(f)
                ],
            )
        )
    output = DocumentExtraction.model_validate(
        doc.get("original_proposal") or dict(document_type=doc["type"], fields=proposals)
    )
    checked = validate_fields(output, doc, content, blocks, threshold)
    events = []
    for n in targets:
        fixed = checked[n]
        if fixed["status"] != "extracted":
            continue
        original = copy.deepcopy(doc["fields"][n])
        fixed["validation_note"] = (
            "Τοπικός επανέλεγχος ρητού νομίσματος και εξαρτώμενων ποσών. Εκκρεμεί ανθρώπινη επιβεβαίωση."
        )
        doc["fields"][n] = fixed
        events.append(
            dict(
                version=VERSION,
                document_type=doc["type"],
                field=n,
                original_field=original,
                revalidated_value=fixed["normalized_value"],
                reason=fixed["validation_note"],
                number_locale=next(p.number_locale for p in output.fields if p.field_name == n),
            )
        )
    return events


@lru_cache(maxsize=24)
def assessed_result(serialized: str, application: bytes, financials: bytes) -> dict:
    result = json.loads(serialized)
    events = []
    for doc in result["documents"]:
        content = application if doc["type"] == "application" else financials
        if hashlib.sha256(content).hexdigest() != doc.get("hash"):
            continue
        blocks = [
            Block.model_validate(b)
            for b in doc.get("blocks", [])
            if b["case_id"] == result["case_id"] and b["document_id"] == doc["id"]
        ]
        if blocks:
            try:
                events.extend(
                    revalidate_stored(
                        doc,
                        content,
                        blocks,
                        result.get("tolerances", {}).get("critical_confidence", 0.8),
                    )
                )
            except (ValueError, KeyError):
                pass
        try:
            events.extend(
                repair_currency_dependents(
                    doc,
                    content,
                    blocks,
                    result.get("tolerances", {}).get("critical_confidence", 0.8),
                )
            )
        except (ValueError, KeyError):
            pass  # Malformed legacy proposals stay rejected, never guessed.
        by_id = {b.block_id: b for b in blocks}
        for name, f in doc["fields"].items():
            if name not in MONEY or f["status"] != "extracted" or not f.get("raw_value"):
                continue
            if numeric_supported(
                f["raw_value"],
                source_list(f),
                {k: b.text for k, b in by_id.items()},
                f.get("number_locale", document_locale(doc)),
                name,
            ):
                continue
            original = copy.deepcopy(f)
            f.update(
                status="invalid",
                normalized_value=None,
                requires_review=True,
                review_reason="Ο αριθμός δεν τεκμηριώνεται ως ολόκληρη τιμή με σωστό πρόσημο στη σχετική γραμμή. Απαιτείται έλεγχος αναλυτή.",
            )
            events.append(
                dict(
                    version=VERSION,
                    document_type=doc["type"],
                    field=name,
                    original_field=original,
                    revalidated_value=None,
                    reason=f["review_reason"],
                )
            )
        for name, f in doc["fields"].items():
            reason = f.get("review_reason") or ""
            if name not in TEXT_CONTINUATIONS or f["status"] != "invalid" or not f.get("raw_value"):
                continue
            if not any(
                t in reason
                for t in [
                    "Η τιμή δεν υπάρχει αυτούσια",
                    "Η προτεινόμενη τιμή δεν αντιστοιχεί αυτούσια",
                ]
            ):
                continue
            try:
                evidence = [
                    Evidence.model_validate(
                        {k: e[k] for k in ("document_id", "page", "block_id", "quote")}
                    )
                    for e in source_list(f)
                ]
                validate_evidence(evidence, blocks, result["case_id"])
                completed = complete_text_citations(name, f["raw_value"], evidence, blocks)
                validate_evidence(completed, blocks, result["case_id"])
                if not raw_supported(
                    f["raw_value"],
                    [e.model_dump() for e in completed],
                    {k: b.text for k, b in by_id.items()},
                ):
                    continue
                original = copy.deepcopy(f)
                sources = []
                content = application if doc["type"] == "application" else financials
                for e in completed:
                    g = source_geometry(
                        content, e.model_dump(), by_id[e.block_id].model_dump(), f["raw_value"]
                    )
                    sources.append(
                        {
                            **g,
                            "document_name": doc["name"],
                            "excerpt": e.quote,
                            "bounding_box": None,
                        }
                    )
                f.update(
                    status="extracted",
                    normalized_value=normalized_text(f["raw_value"]),
                    requires_review=False,
                    review_reason=None,
                    evidence=sources[0],
                    supporting_evidence=sources[1:],
                    validation_note="Επαληθεύτηκε τοπικά το πλήρες κείμενο στις συνεχόμενες γραμμές. Εκκρεμεί επιβεβαίωση αναλυτή.",
                )
                events.append(
                    dict(
                        version=VERSION,
                        document_type=doc["type"],
                        field=name,
                        original_field=original,
                        revalidated_value=f["normalized_value"],
                        reason=f["validation_note"],
                    )
                )
            except (ValueError, KeyError):
                continue
    result["local_validation_version"] = VERSION
    result["local_validation_events"] = events
    if events:
        config = result["tolerances"]
        result["checks_before_local_validation"] = result["checks"]
        result["checks"] = run_checks(
            result["documents"],
            Tolerances(
                Decimal(config["absolute"]),
                Decimal(config["relative"]),
                config["critical_confidence"],
            ),
        )
        if not result.get("errors"):
            result["status"] = (
                "warning" if any(c["status"] != "PASS" for c in result["checks"]) else "complete"
            )
    return result
