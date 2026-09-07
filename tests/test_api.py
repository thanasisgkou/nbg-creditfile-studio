import pytest
from fastapi.testclient import TestClient
from creditfile.api import create_app
from creditfile.config import Settings
from fixture_support import create_fixture


@pytest.fixture
def app(tmp_path):
    app = create_app(tmp_path / "cases", settings=Settings(execution_mode="replay"))
    yield app
    app.state.executor.shutdown(wait=True)


def test_health_and_removed_legacy_routes(app):
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/legacy-cases").status_code == 404
        assert client.post("/api/v1/demo").status_code in (404, 405)
        assert client.get("/api/v1/cases").json() == []


def test_local_api_rejects_foreign_hosts_and_write_origins(app):
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/v1/health", headers={"Host": "attacker.example"}).status_code == 400
        assert client.get("/api/v1/health", headers={"Host": "localhost:8520"}).status_code == 200
        assert (
            client.post("/api/v1/cases", headers={"Origin": "https://attacker.example"}).status_code
            == 403
        )


def test_review_and_bulletin(app):
    from uuid import uuid4

    store = app.state.store
    cid = create_fixture(store)
    rid = store.runs(cid)[0]["id"]
    base = f"/api/v1/cases/{cid}/runs/{rid}"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        ws = client.get(base).json()
        response = client.post(
            base + "/review",
            json=dict(
                request_id=str(uuid4()),
                expected=ws["report"]["fingerprint"],
                kind="application",
                field="tax_id",
                decision="accepted",
            ),
        )
        assert response.status_code == 200, response.text
        updated = client.get(base).json()
        assert next(f for f in updated["fields"] if f["id"] == "application.tax_id")[
            "approved_for_credit_memo"
        ]
        pdf = client.get(base + "/preview.pdf")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        issued = client.post(
            base + "/issue",
            json=dict(request_id=str(uuid4()), expected=updated["report"]["fingerprint"]),
        )
        assert issued.status_code == 200, issued.text
        assert client.get(
            f"/api/v1/cases/{cid}/versions/{issued.json()['version']}/bulletin.pdf"
        ).content.startswith(b"%PDF")


def test_correction_clears_current_conflict_but_preserves_history(app):
    from creditfile.bulletin import preview
    from creditfile.checks import source_list

    store = app.state.store
    cid = create_fixture(store)
    rid = store.runs(cid)[0]["id"]
    original = store.raw_run(cid, rid)
    exported = store.export(cid, rid)
    field = next(d for d in exported["documents"] if d["type"] == "application")["fields"][
        "declared_annual_turnover"
    ]
    assert any(c["check_id"] == "turnover_match" for c in preview(store, cid, rid)["conflicts"])

    store.review(
        cid,
        rid,
        "application",
        "declared_annual_turnover",
        "corrected",
        "Διόρθωση δοκιμαστικής τιμής",
        "4580000",
        source_list(field),
    )
    report = preview(store, cid, rid)
    assert not any(c["check_id"] == "turnover_match" for c in report["conflicts"])
    assert not any(i["id"] == "turnover_match" for i in report["issues"])
    assert any(c["check_id"] == "debt_match" for c in report["conflicts"])
    assert report["corrections"][-1]["corrected_value"] == 4580000
    assert store.raw_run(cid, rid)["result"] == original["result"]

    # A later edit that disagrees must reopen the comparison.
    store.review(
        cid,
        rid,
        "application",
        "declared_annual_turnover",
        "corrected",
        "Νέα δοκιμαστική διόρθωση",
        "4900000",
        source_list(field),
    )
    assert any(c["check_id"] == "turnover_match" for c in preview(store, cid, rid)["conflicts"])


@pytest.mark.parametrize("documented", [False, True])
def test_missing_amount_correction_persists_after_store_reopen(tmp_path, documented):
    from uuid import uuid4

    root = tmp_path / "cases"
    original_app = create_app(root, settings=Settings(execution_mode="replay"))
    try:
        store = original_app.state.store
        cid = create_fixture(store)
        rid = store.runs(cid)[0]["id"]
        original = store.raw_run(cid, rid)["result"]
        base = f"/api/v1/cases/{cid}/runs/{rid}"
        with TestClient(original_app, base_url="http://127.0.0.1") as client:
            ws = client.get(base).json()
            amount = next(f for f in ws["fields"] if f["id"] == "application.requested_amount")
            assert amount["normalized_value"] is None
            # A test analyst explicitly supplies a synthetic amount. The fixture
            # remains unreadable; a source-less correction must stay incomplete.
            req = dict(
                request_id=str(uuid4()),
                expected=ws["report"]["fingerprint"],
                kind="application",
                field="requested_amount",
                decision="corrected",
                corrected="750000.50",
                comment="Synthetic correction persistence test",
                sources=amount["sources"] if documented else [],
            )
            for _ in range(2):
                response = client.post(base + "/review", json=req)
                assert response.status_code == 200, response.text
            updated = client.get(base).json()
            rejected = client.post(
                base + "/review",
                json={
                    **req,
                    "request_id": str(uuid4()),
                    "expected": updated["report"]["fingerprint"],
                    "corrected": "750.?00",
                },
            )
            assert rejected.status_code == 400
    finally:
        original_app.state.executor.shutdown(wait=True)

    reopened = create_app(root, settings=Settings(execution_mode="replay"))
    try:
        with TestClient(reopened, base_url="http://127.0.0.1") as client:
            ws = client.get(base).json()
            amount = next(f for f in ws["fields"] if f["id"] == "application.requested_amount")
            row = next(f for f in ws["report"]["fields"] if f["key"] == "requested_amount")
            assert amount["normalized_value"] == row["value"] == 750000.50
            assert amount["review_status"] == "corrected"
            assert bool(amount["sources"]) is documented
            assert row["complete"] is documented
            assert len(ws["reviews"]) == 1
            assert ws["reviews"][0]["corrected_value"] == 750000.50
            assert reopened.state.store.raw_run(cid, rid)["result"] == original
            assert {c["check_id"] for c in ws["report"]["conflicts"]} == {
                "turnover_match",
                "debt_match",
            }
    finally:
        reopened.state.executor.shutdown(wait=True)
