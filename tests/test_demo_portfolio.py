"""Prepared cases retain their source documents and distinct review states."""

import pymupdf
from fastapi.testclient import TestClient
from creditfile.api import create_app
from creditfile.config import Settings
from creditfile.demo import seed_demo

EXPECTED = {
    "Σταφυλάκης Οινοποιητική Α.Ε.": ("Ολοκληρώθηκε η προετοιμασία", 320000, 54, 10),
    "Attention Is All You Need Α.Ε.": ("Προς έλεγχο", 280000, 48, 4),
    "Ypnos Palace Ξενοδοχειακή Α.Ε.": ("Εκκρεμούν στοιχεία ή διευκρινίσεις", 600000, 84, 10),
}


def test_prepared_companies_keep_their_data_and_pdf_evidence(tmp_path, monkeypatch):
    def no_provider(*args, **kwargs):
        raise AssertionError("Prepared examples must not contact an AI provider")

    monkeypatch.setattr("creditfile.providers.create_model", no_provider)
    settings = Settings(execution_mode="replay")
    app = create_app(tmp_path / "cases", settings=settings)
    try:
        seed_demo(app.state.store, settings)
        with TestClient(app, base_url="http://127.0.0.1") as client:
            cases = client.get("/api/v1/cases").json()
            assert len(cases) == 4
            assert {c["name"] for c in cases} >= EXPECTED.keys()
            for case in cases:
                if case["name"] not in EXPECTED:
                    continue
                state, amount, tenor, reviewed = EXPECTED[case["name"]]
                base = f"/api/v1/cases/{case['id']}/runs/{case['run_id']}"
                workspace = client.get(base).json()
                assert workspace["report"]["state"] == state
                assert workspace["report"]["reviewed_count"] == reviewed
                assert not workspace["errors"]
                fields = {f["id"]: f for f in workspace["fields"]}
                assert fields["application.company_legal_name"]["normalized_value"] == case["name"]
                assert fields["financials.company_legal_name"]["normalized_value"] == case["name"]
                assert fields["application.requested_amount"]["normalized_value"] == amount
                assert fields["application.tenor_months"]["normalized_value"] == tenor
                for kind in ["application", "financials"]:
                    response = client.get(f"/api/v1/cases/{case['id']}/documents/{kind}")
                    with pymupdf.open(stream=response.content, filetype="pdf") as pdf:
                        text = "\n".join(page.get_text() for page in pdf)
                        assert len(pdf) == 2 and case["name"] in text
                        assert "Συνθετικά δεδομένα επίδειξης" in text
                if case["name"].startswith("Σταφυλάκης"):
                    assert not workspace["report"]["draft"]
                    assert len(workspace["versions"]) == 1
                    assert client.get(
                        f"/api/v1/cases/{case['id']}/versions/1/bulletin.pdf"
                    ).content.startswith(b"%PDF")
                elif case["name"].startswith("Attention"):
                    assert fields["application.registration_number"]["status"] == "missing"
                    assert "GPU" in fields["application.financing_purpose"]["normalized_value"]
                else:
                    debt = next(
                        c for c in workspace["report"]["conflicts"] if c["check_id"] == "debt_match"
                    )
                    assert debt["status"] == "FAIL" and not debt["resolution"]
                    assert debt["absolute_difference"] == 300000
            seed_demo(app.state.store, settings)
            assert client.get("/api/v1/cases").json() == cases
    finally:
        app.state.executor.shutdown(wait=True)
