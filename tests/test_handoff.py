"""The exported summary must agree with current review and resolution state."""

from fastapi.testclient import TestClient
from creditfile import bulletin, handoff
from creditfile.api import create_app
from creditfile.config import Settings
from fixture_support import create_fixture


def test_handoff_uses_saved_resolutions_and_excludes_undocumented_values(tmp_path):
    app = create_app(tmp_path / "cases", settings=Settings(execution_mode="replay"))
    store = app.state.store
    try:
        cid = create_fixture(store)
        rid = store.runs(cid)[0]["id"]
        for check in bulletin.preview(store, cid, rid)["conflicts"]:
            bulletin.resolve(
                store,
                cid,
                rid,
                check["check_id"],
                "Resolved in test",
                check["evidence"],
                check["basis"],
            )
        store.review(
            cid, rid, "application", "requested_amount", "corrected", "Manual test value", "750000"
        )
        report = handoff.summary(
            store.export(cid, rid), "Synthetic test", bulletin.preview(store, cid, rid)
        )
        assert not any(r["field"] == "requested_amount" for r in report["approved"])
        assert any(r["field"] == "requested_amount" for r in report["pending"])
        assert not {"turnover_match", "debt_match"} & {c["id"] for c in report["clarifications"]}
        assert "application.requested_amount" in {c["id"] for c in report["clarifications"]}
        with TestClient(app, base_url="http://127.0.0.1") as client:
            response = client.get(f"/api/v1/cases/{cid}/runs/{rid}/handoff")
            assert response.status_code == 200
            assert "text/markdown" in response.headers["content-type"]
            assert "requested_amount" not in response.text
            assert "Παρακαλούμε διευκρινίστε τη διαφορά" not in response.text
        # A material change must bring the affected comparison back.
        store.review(cid, rid, "financials", "reporting_period", "unresolved", "Recheck period")
        report = handoff.summary(
            store.export(cid, rid), "Synthetic test", bulletin.preview(store, cid, rid)
        )
        assert {"turnover_match", "debt_match"} <= {c["id"] for c in report["clarifications"]}
    finally:
        app.state.executor.shutdown(wait=True)
