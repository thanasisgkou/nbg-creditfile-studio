"""Preloaded synthetic scenarios, independently copied into each visitor's store."""

import copy
import hashlib
import json

from .config import ROOT
from . import bulletin
from .bulk_review import accept_selected, eligibility

PORTFOLIO = ROOT / "demo/portfolio"
SCENARIOS = ("stafylakis", "attention", "ypnos")


def rebase_case(value, cid):
    if isinstance(value, dict):
        return {k: cid if k == "case_id" else rebase_case(v, cid) for k, v in value.items()}
    if isinstance(value, list):
        return [rebase_case(v, cid) for v in value]
    return value


def seed_portfolio(store):
    # Creation order makes the completed winery appear first in the case list.
    for slug in reversed(SCENARIOS):
        folder = PORTFOLIO / slug
        scenario = json.loads((folder / "scenario.json").read_text(encoding="utf-8"))
        recorded = json.loads((folder / "analysis.json").read_text(encoding="utf-8"))
        inputs = [
            dict(
                type=kind,
                name=f"{slug}_{kind}.pdf",
                content=(folder / (kind + ".pdf")).read_bytes(),
            )
            for kind in ("application", "financials")
        ]
        for item in inputs:
            doc = next(d for d in recorded["documents"] if d["type"] == item["type"])
            if hashlib.sha256(item["content"]).hexdigest() != doc["hash"]:
                raise ValueError("The demo PDF differs from its recorded analysis")
        cid = store.create(scenario["name"], inputs)
        result = rebase_case(copy.deepcopy(recorded), cid)
        result["example_notice"] = (
            "Προφορτωμένο συνθετικό παράδειγμα με αποθηκευμένη ανάλυση AI και προετοιμασμένο ιστορικό ελέγχου επίδειξης."
        )
        result["demo_scenario"] = slug
        rid = store.save_run(cid, result)
        exported = store.export(cid, rid)
        selected = [
            (d["type"], name)
            for d in exported["documents"]
            for name, f in d["fields"].items()
            if eligibility(f)[0]
        ]
        if scenario["stage"] == "review":
            # Four preparation fields checked; financial review and GEMI remain open.
            selected = [
                item
                for item in selected
                if item[0] == "application" and item[1] != "registration_number"
            ]
        accept_selected(store, cid, rid, selected, bulletin.fingerprint(store, cid, rid))
        run = store.raw_run(cid, rid)
        for event in run["reviews"]:
            event.update(
                reviewer="synthetic_demo_preparation",
                reviewer_comment="Προετοιμασμένος έλεγχος επίδειξης, μετά από αντιπαραβολή με τις πηγές των συνθετικών PDF.",
            )
        store.save(store.folder(cid) / ("run-" + rid + ".json"), run)
        report = bulletin.preview(store, cid, rid)
        expected = {
            "complete": "Ολοκληρώθηκε η προετοιμασία",
            "review": "Προς έλεγχο",
            "clarification": "Εκκρεμούν στοιχεία ή διευκρινίσεις",
        }[scenario["stage"]]
        if report["state"] != expected:
            raise ValueError(f"Demo scenario {slug} no longer has its expected review state")
        if scenario["stage"] == "complete":
            bulletin.issue(store, cid, rid, report["fingerprint"], studio=True)
