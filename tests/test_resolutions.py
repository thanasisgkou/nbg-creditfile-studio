"""Recording source resolutions before field review must remain a valid workflow."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from creditfile.api import create_app
from creditfile.config import Settings
from creditfile import bulletin
from creditfile.checks import source_list
from fixture_support import create_fixture


def test_resolve_both_comparisons_then_confirm_fields(tmp_path):
    app = create_app(tmp_path / "cases", settings=Settings(execution_mode="replay"))
    store = app.state.store
    cid = create_fixture(store)
    rid = store.runs(cid)[0]["id"]
    base = f"/api/v1/cases/{cid}/runs/{rid}"
    with TestClient(app, base_url="http://127.0.0.1") as client:

        def command(path, **body):
            report = client.get(base).json()["report"]
            response = client.post(
                base + path,
                json=dict(request_id=str(uuid4()), expected=report["fingerprint"], **body),
            )
            assert response.status_code == 200, response.text

        initial = client.get(base).json()["report"]
        assert {c["check_id"] for c in initial["conflicts"]} == {"turnover_match", "debt_match"}
        for check in initial["conflicts"]:
            command(
                "/resolve",
                check_id=check["check_id"],
                reason="OK",
                sources=check["evidence"],
                basis=check["basis"],
            )
        assert len(store.raw_run(cid, rid)["resolutions"]) == 2
        assert all(c["resolution"] for c in client.get(base).json()["report"]["conflicts"])
        command("/review", kind="application", field="tax_id", decision="accepted", comment="")
        assert all(c["resolution"] for c in client.get(base).json()["report"]["conflicts"])
        fields = client.get(base).json()["fields"]
        selected = [(f["kind"], f["name"]) for f in fields if f["eligible"]]
        command("/bulk", selected=selected)
        final = client.get(base).json()["report"]
        assert all(c["resolution"]["reason"] == "OK" for c in final["conflicts"])
        assert len(store.raw_run(cid, rid)["resolutions"]) == 2
        assert not any(i["id"] in {"turnover_match", "debt_match"} for i in final["issues"])


@pytest.mark.parametrize("legacy", [False, True])
def test_only_material_changes_to_comparison_dependencies_reopen_it(tmp_path, legacy):
    app = create_app(tmp_path / "cases", settings=Settings(execution_mode="replay"))
    store = app.state.store
    cid = create_fixture(store)
    rid = store.runs(cid)[0]["id"]
    with TestClient(app, base_url="http://127.0.0.1"):

        def report():
            return bulletin.preview(store, cid, rid)

        def field(kind, name):
            return next(d for d in store.export(cid, rid)["documents"] if d["type"] == kind)[
                "fields"
            ][name]

        def resolved():
            return {c["check_id"] for c in report()["conflicts"] if c["resolution"]}

        for c in report()["conflicts"]:
            bulletin.resolve(store, cid, rid, c["check_id"], "OK", c["evidence"], c["basis"])
        if legacy:
            run = store.raw_run(cid, rid)
            exported = store.export(cid, rid)
            for event in run["resolutions"]:
                check = next(
                    c for c in exported["reviewed_checks"] if c["check_id"] == event["check_id"]
                )
                event["basis"] = bulletin.digest(
                    [check, exported["review_events"], bulletin.document_hashes(store, cid)]
                )
                event.pop("basis_version")
            store.save(store.folder(cid) / ("run-" + rid + ".json"), run)
        original_records = store.raw_run(cid, rid)["resolutions"]
        snapshot = bulletin.issue(store, cid, rid, report()["fingerprint"], studio=True)
        saved = bulletin.version_folder(store, snapshot) / "snapshot.json"
        saved_bytes = saved.read_bytes()
        store.review(cid, rid, "application", "tax_id", "accepted", "")
        tenor = field("application", "tenor_months")
        store.review(
            cid,
            rid,
            "application",
            "tenor_months",
            "corrected",
            "Επανέλεγχος διάρκειας",
            str(tenor["normalized_value"]),
            source_list(tenor),
        )
        assert resolved() == {"turnover_match", "debt_match"}

        debt = field("financials", "total_borrowings")
        store.review(
            cid,
            rid,
            "financials",
            "total_borrowings",
            "corrected",
            "Συνθετική διόρθωση δανεισμού",
            str(debt["normalized_value"] + 20000),
            source_list(debt),
        )
        assert resolved() == {"turnover_match"}
        store.review(
            cid, rid, "financials", "total_borrowings", "accepted", "Επαναφορά αρχικής τιμής"
        )
        assert resolved() == {"turnover_match"}  # Do not resurrect a superseded resolution.
        store.review(
            cid, rid, "financials", "reporting_period", "unresolved", "Εκκρεμεί έλεγχος περιόδου"
        )
        assert not resolved()
        assert store.raw_run(cid, rid)["resolutions"] == original_records
        assert saved.read_bytes() == saved_bytes
