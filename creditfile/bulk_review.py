"""Explicit, atomic multi-field acceptance of unchanged, evidenced proposals."""

from .store import LOCK, now
from .bulletin import fingerprint, digest, verified_sources
from .checks import source_list
from uuid import uuid4


def eligibility(field: dict) -> tuple[bool, str]:
    if field.get("status") == "manually_corrected" and "original_evidence" not in field:
        return False, "Διόρθωση χωρίς τεκμηρίωση"
    if field.get("approved_for_credit_memo"):
        return False, "Ήδη ελεγμένο"
    if field.get("review_status") == "unresolved":
        return False, "Ανεπίλυτο"
    if field.get("status") == "missing":
        return False, "Λείπει τιμή"
    if field.get("status") == "uncertain":
        return False, "Αβέβαιη τιμή"
    if field.get("status") == "invalid":
        return False, "Δεν επαληθεύτηκε"
    if field.get("normalized_value") is None:
        return False, "Λείπει τιμή"
    if field.get("requires_review"):
        return False, "Απαιτείται επανέλεγχος"
    if field.get("status") != "extracted":
        return False, "Απαιτείται ατομικός έλεγχος"
    if not source_list(field):
        return False, "Χωρίς τεκμηρίωση"
    return True, "Προς επιβεβαίωση"


def accept_selected(
    store, cid: str, rid: str, selected: list[tuple[str, str]], expected: str
) -> int:
    if not selected or len(selected) != len(set(selected)):
        raise ValueError("Επίλεξε διαφορετικά στοιχεία για επιβεβαίωση.")
    with LOCK:
        if fingerprint(store, cid, rid) != expected:
            raise ValueError("Ο φάκελος άλλαξε. Έλεγξε ξανά τα επιλεγμένα στοιχεία.")
        exported = store.export(cid, rid)
        docs = {d["type"]: d for d in exported["documents"]}
        raw = store.raw_run(cid, rid)
        originals = {d["type"]: d for d in raw["result"]["documents"]}
        batch_id = uuid4().hex
        events = []
        for kind, name in selected:
            field = docs.get(kind, {}).get("fields", {}).get(name)
            if field is None or not eligibility(field)[0]:
                raise ValueError(
                    "Η επιλογή περιλαμβάνει στοιχείο που χρειάζεται ατομικό έλεγχο ή έχει ήδη ελεγχθεί. Δεν αποθηκεύτηκε καμία αλλαγή."
                )
            verified_sources(store, cid, rid, source_list(field), kind)
            original = originals[kind]["fields"][name]
            events.append(
                dict(
                    timestamp=now(),
                    document_type=kind,
                    field=name,
                    original_value=original["normalized_value"],
                    original_raw_value=original["raw_value"],
                    corrected_value=None,
                    reviewed_value=field["normalized_value"],
                    review_decision="accepted",
                    reviewer_comment="Ρητή μαζική επιβεβαίωση επιλεγμένων στοιχείων μετά τον έλεγχο των πηγών.",
                    reviewer="local_session_unverified",
                    local_validation_version=exported.get("local_validation_version"),
                    document_hash=docs[kind]["hash"],
                    field_basis=digest(original),
                    documented_sources=[],
                    batch_id=batch_id,
                )
            )
        if fingerprint(store, cid, rid) != expected:
            raise ValueError("Ο φάκελος άλλαξε κατά τον έλεγχο. Δεν αποθηκεύτηκε καμία αλλαγή.")
        raw["reviews"].extend(events)
        store.save(store.folder(cid) / ("run-" + rid + ".json"), raw)
        return len(events)
