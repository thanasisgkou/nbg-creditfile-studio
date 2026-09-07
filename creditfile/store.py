"""Local JSON/PDF persistence with append-only review events per immutable run."""

import copy
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import threading
from uuid import uuid4
from .config import Settings
from .extraction import convert
from .schema import MONEY
from .checks import run_checks, Tolerances
from decimal import Decimal
from .recheck import assessed_result

LOCK = threading.RLock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CaseStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else Settings.load().data_dir / "cases"
        self.root.mkdir(parents=True, exist_ok=True)

    def folder(self, case_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", case_id):
            raise ValueError("Invalid case ID")
        return self.root / case_id

    def save(self, path: Path, value: dict) -> None:
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    def cases(self) -> list[dict]:
        return sorted(
            [json.loads(p.read_text(encoding="utf-8")) for p in self.root.glob("*/case.json")],
            key=lambda c: c["created"],
            reverse=True,
        )

    def create(self, name: str, inputs: list[dict]) -> str:
        if not name.strip():
            raise ValueError("Δώστε όνομα φακέλου.")
        if len(inputs) != 2 or {i["type"] for i in inputs} != {"application", "financials"}:
            raise ValueError("Απαιτούνται ακριβώς δύο διαφορετικοί τύποι PDF.")
        cid = uuid4().hex
        folder = self.folder(cid)
        folder.mkdir()
        docs = []
        for item in inputs:
            name_ = item["name"].replace("\\", "/").split("/")[-1]
            (folder / (item["type"] + ".pdf")).write_bytes(item["content"])
            docs.append(dict(name=name_, type=item["type"]))
        self.save(
            folder / "case.json",
            dict(
                id=cid, name=name.strip()[:100], created=now(), documents=docs, synthetic_only=True
            ),
        )
        return cid

    def inputs(self, cid: str) -> list[dict]:
        folder = self.folder(cid)
        case = json.loads((folder / "case.json").read_text(encoding="utf-8"))
        items = []
        for d in case["documents"]:
            path = d.get("path", d["type"] + ".pdf")
            if path not in {"application.pdf", "financials.pdf"} and not re.fullmatch(
                r"document_versions/[a-f0-9]{64}\.pdf", path
            ):
                raise ValueError("Invalid document path")
            items.append({**d, "content": (folder / path).read_bytes()})
        return items

    def replace_document(
        self,
        cid: str,
        kind: str,
        name: str,
        content: bytes,
        settings: Settings,
        expected_hash: str,
        synthetic: bool,
    ) -> None:
        """Publish the new manifest atomically; old bytes and analyses survive."""
        from .extraction import inspect_document

        if not synthetic:
            raise ValueError("Επιβεβαίωσε ότι το PDF περιέχει μόνο συνθετικά δεδομένα.")
        doc = inspect_document(content, name, kind, settings, cid)
        if doc.get("preflight_error") or doc.get("unreadable_pages"):
            raise ValueError(doc.get("preflight_error") or "Το PDF έχει μη αναγνώσιμες σελίδες.")
        with LOCK:
            folder = self.folder(cid)
            current = next(i for i in self.inputs(cid) if i["type"] == kind)
            old_hash = hashlib.sha256(current["content"]).hexdigest()
            new_hash = hashlib.sha256(content).hexdigest()
            if old_hash != expected_hash:
                raise ValueError("Το αρχείο άλλαξε. Άνοιξε ξανά τα Έγγραφα.")
            if new_hash == old_hash:
                raise ValueError("Επέλεξες το ίδιο PDF. Δεν χρειάζεται αντικατάσταση.")
            archive = folder / "document_versions"
            archive.mkdir(exist_ok=True)
            for digest_, data in [(old_hash, current["content"]), (new_hash, content)]:
                target = archive / (digest_ + ".pdf")
                if not target.exists():
                    target.write_bytes(data)
                if hashlib.sha256(target.read_bytes()).hexdigest() != digest_:
                    raise ValueError("Αποτυχία επαλήθευσης αντιγράφου PDF.")
            case = json.loads((folder / "case.json").read_text(encoding="utf-8"))
            new_name = name.replace("\\", "/").split("/")[-1]
            for d in case["documents"]:
                if d["type"] == kind:
                    d.update(name=new_name, path="document_versions/" + new_hash + ".pdf")
            case.setdefault("document_history", []).append(
                dict(
                    type=kind,
                    old_name=current["name"],
                    new_name=new_name,
                    old_hash=old_hash,
                    new_hash=new_hash,
                    timestamp=now(),
                    reviewer="local_session_unverified",
                )
            )
            self.save(folder / "case.json", case)

    def analysis_inputs(self, cid: str, rid: str) -> list[dict]:
        """Use the exact PDF version underlying each historical source."""
        current = {i["type"]: i for i in self.inputs(cid)}
        items = []
        for doc in self.raw_run(cid, rid)["result"]["documents"]:
            data = current[doc["type"]]["content"]
            if hashlib.sha256(data).hexdigest() != doc["hash"]:
                if not re.fullmatch(r"[a-f0-9]{64}", doc["hash"]):
                    raise ValueError("Invalid document hash")
                path = self.folder(cid) / "document_versions" / (doc["hash"] + ".pdf")
                if not path.exists():
                    raise ValueError(
                        "Το αρχικό PDF αυτής της ανάλυσης δεν είναι διαθέσιμο. Απαιτείται νέα ανάλυση."
                    )
                data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != doc["hash"]:
                raise ValueError("Το ιστορικό PDF δεν συμφωνεί με την ανάλυση.")
            items.append(dict(type=doc["type"], name=doc["name"], content=data))
        return items

    def save_run(self, cid: str, result: dict) -> str:
        if result["case_id"] != cid:
            raise ValueError("Run outside case")
        rid = uuid4().hex
        self.save(
            self.folder(cid) / ("run-" + rid + ".json"),
            dict(id=rid, created=now(), result=result, reviews=[]),
        )
        return rid

    def runs(self, cid: str) -> list[dict]:
        return sorted(
            [self.run(cid, p.stem[4:]) for p in self.folder(cid).glob("run-*.json")],
            key=lambda r: r["created"],
            reverse=True,
        )

    def run(self, cid: str, rid: str) -> dict:
        r = self.raw_run(cid, rid)
        inputs = {i["type"]: i["content"] for i in self.inputs(cid)}
        r["result"] = copy.deepcopy(
            assessed_result(
                json.dumps(r["result"], ensure_ascii=False),
                inputs["application"],
                inputs["financials"],
            )
        )
        return r

    def raw_run(self, cid: str, rid: str) -> dict:
        if not re.fullmatch(r"[a-f0-9]{32}", rid):
            raise ValueError("Invalid run ID")
        r = json.loads((self.folder(cid) / ("run-" + rid + ".json")).read_text(encoding="utf-8"))
        if r["result"]["case_id"] != cid:
            raise ValueError("Wrong case")
        return r

    def review(
        self,
        cid: str,
        rid: str,
        kind: str,
        field: str,
        decision: str,
        comment: str,
        corrected: str | None = None,
        documented_sources: list[dict] | None = None,
    ) -> None:
        if decision not in {"accepted", "corrected", "unresolved"}:
            raise ValueError("Μη έγκυρη απόφαση review.")
        with LOCK:
            assessed = self.run(cid, rid)
            run = self.raw_run(cid, rid)
            doc = next((d for d in assessed["result"]["documents"] if d["type"] == kind), None)
            if doc is None or field not in doc["fields"]:
                raise ValueError("Άγνωστο πεδίο εγγράφου.")
            from .bulletin import document_hashes, verified_sources, digest

            if document_hashes(self, cid)[kind] != doc["hash"]:
                raise ValueError(
                    "Το έγγραφο άλλαξε. Χρειάζεται νέα ανάλυση και έλεγχος των επηρεαζόμενων στοιχείων."
                )
            refs = (
                verified_sources(self, cid, rid, documented_sources or [], kind)
                if decision == "corrected"
                else []
            )
            original = doc["fields"][field]
            value = original["normalized_value"]
            if decision == "accepted" and (original["status"] != "extracted" or value is None):
                raise ValueError(
                    "Αποδοχή μόνο extracted τιμής. Για μη επικυρωμένη τιμή χρησιμοποιήστε διόρθωση με αιτιολόγηση."
                )
            if decision in {"corrected", "unresolved"} and not comment.strip():
                raise ValueError("Απαιτείται σύντομη αιτιολόγηση.")
            if decision == "corrected":
                if not corrected or not corrected.strip():
                    raise ValueError("Δώστε διορθωμένη τιμή.")
                if field in MONEY:
                    # Analyst types normalized EUR, dot decimal, no grouping.
                    if not re.fullmatch(r"-?\d+(?:\.\d{1,2})?", corrected.strip()):
                        raise ValueError(
                            "Γράψτε ποσό σε EUR χωρίς διαχωριστικά χιλιάδων, π.χ. 750000.00."
                        )
                    value = convert(corrected, field, "en", 1)
                elif field == "tenor_months":
                    value = convert(
                        corrected + " μήνες" if corrected.isdigit() else corrected, field, "en"
                    )
                else:
                    value = convert(corrected, field, "en")
            if decision == "unresolved":
                value = None
            stored = next(d for d in run["result"]["documents"] if d["type"] == kind)["fields"][
                field
            ]
            run["reviews"].append(
                dict(
                    timestamp=now(),
                    document_type=kind,
                    field=field,
                    original_value=stored["normalized_value"],
                    original_raw_value=stored["raw_value"],
                    corrected_value=value if decision == "corrected" else None,
                    reviewed_value=value,
                    review_decision=decision,
                    reviewer_comment=comment.strip(),
                    reviewer="local_session_unverified",
                    local_validation_version=assessed["result"].get("local_validation_version"),
                )
            )
            run["reviews"][-1].update(
                document_hash=doc["hash"], field_basis=digest(stored), documented_sources=refs
            )
            self.save(self.folder(cid) / ("run-" + rid + ".json"), run)

    def export(self, cid: str, rid: str) -> dict:
        run = self.run(cid, rid)
        result = copy.deepcopy(run["result"])
        latest = {(e["document_type"], e["field"]): e for e in run["reviews"]}
        approved = []
        for doc in result["documents"]:
            for name, f in doc["fields"].items():
                event = latest.get((doc["type"], name))
                f["approved_for_credit_memo"] = bool(
                    event and event["review_decision"] in {"accepted", "corrected"}
                )
                f["review_status"] = event["review_decision"] if event else "pending"
                f["original_value"] = f["normalized_value"]
                if event:
                    f["reviewer_comment"] = event["reviewer_comment"]
                    if event["review_decision"] == "corrected":
                        f.update(
                            status="manually_corrected",
                            normalized_value=event["reviewed_value"],
                            requires_review=False,
                            review_reason="Χειροκίνητη διόρθωση αναλυτή. Η αρχική παραπομπή δεν τεκμηριώνει αυτομάτως τη νέα τιμή.",
                        )
                        if event.get("documented_sources"):
                            f["original_evidence"] = f.get("evidence")
                            f["evidence"] = event["documented_sources"][0]
                            f["supporting_evidence"] = event["documented_sources"][1:]
                        else:
                            f["unverified_original_evidence"] = f.get("evidence")
                            f.update(
                                evidence=None,
                                supporting_evidence=[],
                                evidence_basis="manual_without_documentation",
                                review_reason="Η τιμή αποθηκεύτηκε. Εκκρεμεί επιλογή πηγής που τεκμηριώνει τη διόρθωση.",
                            )
                    elif event["review_decision"] == "unresolved":
                        f.update(requires_review=True)
                    elif event["review_decision"] == "accepted":
                        reviewed_value = event.get("reviewed_value", event.get("original_value"))
                        current_value = f["normalized_value"]
                        from .parsing import normalized_text

                        same = (
                            normalized_text(reviewed_value) == normalized_text(current_value)
                            if isinstance(reviewed_value, str) and isinstance(current_value, str)
                            else reviewed_value == current_value
                        )
                        if not same:
                            f.update(
                                requires_review=True,
                                approved_for_credit_memo=False,
                                review_status="pending",
                                review_reason="Ο τοπικός επανέλεγχος άλλαξε την προτεινόμενη τιμή. Απαιτείται νέα ανθρώπινη επιβεβαίωση.",
                            )
                        else:
                            f.update(requires_review=False)
                approved.append(f["approved_for_credit_memo"])
            # Export fields and evidence, not every raw PDF block/page.
            doc.pop("blocks", None)
            doc.pop("pages", None)
        # Changing interpretation metadata invalidates earlier acceptance of
        # dependent amounts. No silent rescaling of an analyst's EUR value.
        positions = {(e["document_type"], e["field"]): i for i, e in enumerate(run["reviews"])}
        for doc in result["documents"]:
            metadata = ["currency"] + (
                ["unit_scale", "reporting_period", "company_legal_name"]
                if doc["type"] == "financials"
                else []
            )
            # Scan history, not just the latest event: re-accepting metadata
            # must not resurrect amounts approved before a correction/unresolved.
            changed = max(
                [
                    i
                    for i, e in enumerate(run["reviews"])
                    if e["document_type"] == doc["type"]
                    and e["field"] in metadata
                    and e["review_decision"] in {"corrected", "unresolved"}
                ]
                or [-1]
            )
            for name, f in doc["fields"].items():
                if (
                    name in MONEY
                    and changed >= 0
                    and positions.get((doc["type"], name), -1) <= changed
                ):
                    f.update(
                        status="uncertain",
                        requires_review=True,
                        approved_for_credit_memo=False,
                        review_status="pending",
                        review_reason="Άλλαξαν τα metadata. Απαιτείται νέα επιβεβαίωση του ποσού σε EUR.",
                    )
        from .bulletin import document_hashes, digest

        hashes = document_hashes(self, cid)
        raw_docs = {d["type"]: d for d in self.raw_run(cid, rid)["result"]["documents"]}
        for doc in result["documents"]:
            for name, f in doc["fields"].items():
                event = latest.get((doc["type"], name))
                changed = hashes[doc["type"]] != doc["hash"] or bool(
                    event
                    and event.get("field_basis")
                    and event["field_basis"] != digest(raw_docs[doc["type"]]["fields"][name])
                )
                if changed:
                    f.update(
                        review_status="pending",
                        approved_for_credit_memo=False,
                        requires_review=True,
                        status="uncertain",
                        review_reason="Άλλαξε το έγγραφο ή η αρχική τιμή. Απαιτείται νέα ανάλυση όπου άλλαξε έγγραφο και νέα ανθρώπινη επαλήθευση.",
                    )
                if (
                    f["status"] not in {"extracted", "manually_corrected"}
                    or f["normalized_value"] is None
                ):
                    f["approved_for_credit_memo"] = False
        approved = [
            f["approved_for_credit_memo"] for d in result["documents"] for f in d["fields"].values()
        ]
        config = result["tolerances"]
        reviewed_checks = run_checks(
            result["documents"],
            Tolerances(
                Decimal(config["absolute"]),
                Decimal(config["relative"]),
                config["critical_confidence"],
            ),
        )
        return dict(
            **result,
            run_id=rid,
            exported_at=now(),
            review_events=run["reviews"],
            reviewed_checks=reviewed_checks,
            approved_field_count=sum(approved),
            ready_for_credit_memo=all(approved)
            and all(c["status"] == "PASS" for c in reviewed_checks),
            checks_basis="checks: original document extraction; reviewed_checks: latest explicit analyst decisions, recalculated in Python.",
            credit_memo_warning="Only explicitly reviewed fields may be used. Outstanding mismatches still require analyst resolution. No credit decision is produced.",
        )

    def chats(self, cid: str, rid: str) -> list[dict]:
        self.run(cid, rid)
        path = self.folder(cid) / ("chat-" + rid + ".json")
        return json.loads(path.read_text(encoding="utf-8"))["sessions"] if path.exists() else []

    def new_chat(self, cid: str, rid: str) -> str:
        with LOCK:
            sessions = self.chats(cid, rid)
            sid = uuid4().hex
            sessions.append(dict(id=sid, created=now(), turns=[]))
            self.save(self.folder(cid) / ("chat-" + rid + ".json"), dict(sessions=sessions))
            return sid

    def append_chat(self, cid: str, rid: str, sid: str, turn: dict) -> None:
        if turn["case_id"] != cid or turn["run_id"] != rid:
            raise ValueError("Συνομιλία εκτός φακέλου ή ανάλυσης.")
        with LOCK:
            sessions = self.chats(cid, rid)
            session = next((s for s in sessions if s["id"] == sid), None)
            if session is None:
                raise ValueError("Δεν βρέθηκε η συνομιλία.")
            session["turns"].append(dict(**turn, id=uuid4().hex, created=now()))
            self.save(self.folder(cid) / ("chat-" + rid + ".json"), dict(sessions=sessions))
