"""Regression coverage for numerical integrity, provenance and document lifecycle."""

from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from creditfile import chat
from creditfile.checks import run_checks, Tolerances, usable
from creditfile.validation import amount
from creditfile.numeric_evidence import numeric_supported
from creditfile.periods import reporting_period
from chat_support import FakeModel


def field(value):
    return dict(
        status="extracted",
        normalized_value=value,
        confidence=1,
        evidence={"quote": str(value)},
        supporting_evidence=[],
        review_status="pending",
    )


@pytest.mark.parametrize("position", ["total_assets", "total_liabilities", "total_equity"])
def test_accounting_requires_all_three_documented_components(position):
    fields = dict(
        total_assets=field(300000), total_liabilities=field(200000), total_equity=field(100000)
    )
    documents = [{"type": "financials", "fields": fields}]

    def check():
        return next(
            c for c in run_checks(documents, Tolerances()) if c["check_id"] == "accounting_equation"
        )

    assert check()["status"] == "PASS"
    fields[position].update(
        status="manually_corrected", evidence_basis="manual_without_documentation", evidence=None
    )
    assert check()["status"] == "NOT_CHECKED" and check()["requires_review"]
    assert not usable(fields[position])
    validity = next(
        c
        for c in run_checks(documents, Tolerances())
        if c["check_id"] == f"financials.{position}.validity"
    )
    assert validity["status"] != "PASS"


@pytest.mark.parametrize(
    "raw,locale,scale,expected",
    [
        ("(125.000)", "el", "1", "-125000.00"),
        ("−125.000,50", "el", "1", "-125000.50"),
        ("125,000.50", "en", "1", "125000.50"),
        ("125 000", "el", "1", "125000.00"),
        ("125,50", "el", "1000", "125500.00"),
        ("4.580.000", "unknown", "1", "4580000.00"),
    ],
)
def test_numeric_normalization(raw, locale, scale, expected):
    assert amount(raw, locale, scale) == expected


@pytest.mark.parametrize("raw", ["125.000", "12 50", "(-125)", "NaN", "1e6"])
def test_ambiguous_or_malformed_numbers_rejected(raw):
    with pytest.raises(ValueError):
        amount(raw, "unknown", "1")


@pytest.mark.parametrize(
    "raw,quote,supported",
    [
        ("(125.000)", "Καθαρό αποτέλεσμα 2025: (125.000) EUR", True),
        ("125", "Καθαρό αποτέλεσμα 2025: (125.000) EUR", False),
        ("125.000", "Καθαρό αποτέλεσμα 2025: (125.000) EUR", False),
        ("125.000", "125.000", False),
    ],
)
def test_signed_whole_token_evidence(raw, quote, supported):
    text = "Καθαρό αποτέλεσμα 2025: (125.000) EUR"
    assert (
        numeric_supported(
            raw, [dict(block_id="b", quote=quote)], {"b": text}, "el", "net_profit_or_loss"
        )
        is supported
    )


def test_period_requires_explicit_valid_endpoints():
    assert reporting_period("1 Ιανουαρίου – 31 Δεκεμβρίου 2025") == "2025-01-01/2025-12-31"
    for text in ["2025", "31/12/2025", "31/12/2025 - 01/01/2025"]:
        with pytest.raises(ValueError):
            reporting_period(text)


@pytest.mark.parametrize("bad_citation", [False, True])
def test_chat_returns_concise_answer_with_validated_sources(case, monkeypatch, bad_citation):
    from creditfile.schemas import Block

    store, cid, run = case
    doc = next(d for d in run["result"]["documents"] if d["type"] == "application")
    quote = "Αιτούμενο ποσό χρηματοδότησης: 750.000 EUR"
    text = "Στοιχεία επιχείρησης και λοιπές πληροφορίες\n" + quote
    block = Block(
        case_id=cid,
        document_id=doc["id"],
        document_type="application",
        page=1,
        block_id="test-block",
        text=text,
    )
    monkeypatch.setattr(chat, "retrieve_chat", lambda *args: [block])
    answer_text = "Ζητά χρηματοδότηση 750.000 EUR."

    class Model(FakeModel):
        def generate(self, prompt, schema):
            return schema(
                status="answered",
                claims=[
                    dict(
                        text=answer_text,
                        evidence=[
                            dict(
                                document_id="other-case" if bad_citation else doc["id"],
                                page=1,
                                block_id=block.block_id,
                                quote=quote,
                            )
                        ],
                    )
                ],
                unanswered=[],
            )

    model = Model()
    model.settings = replace(model.settings, chat_query_rewrite=False, chat_retriever="bm25")
    answer = chat.ask(cid, run, store.inputs(cid), "τι ποσο ζηταει", [], model)
    if bad_citation:
        assert answer["status"] == "failed"
        assert not answer["claims"]
    else:
        assert answer["status"] == "answered", answer
        assert [c["text"] for c in answer["claims"]] == [answer_text]
        assert answer["sources"][0]["quote"] == quote
        assert answer["unanswered"] == []


def test_static_branding_and_spa(tmp_path, monkeypatch):
    from creditfile import api
    from creditfile.config import Settings

    dist = tmp_path / "frontend" / "dist"
    (dist / "branding").mkdir(parents=True)
    (dist / "index.html").write_text("<html>SPA</html>")
    for name in ["nbg-logo.png", "nbg-favicon.png"]:
        (dist / "branding" / name).write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(api, "ROOT", tmp_path)
    app = api.create_app(tmp_path / "cases", settings=Settings(execution_mode="replay"))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        for name in ["nbg-logo.png", "nbg-favicon.png"]:
            response = client.get("/branding/" + name)
            assert response.status_code == 200 and response.headers["content-type"] == "image/png"
        for path in ["/branding/missing.png", "/missing.png", "/assets/missing.js", "/api/missing"]:
            assert client.get(path).status_code == 404
        assert client.get("/cases/example/review").text == "<html>SPA</html>"
    app.state.executor.shutdown(wait=True)


def test_provider_failure_is_failed_job_with_saved_diagnostics(tmp_path, monkeypatch):
    from creditfile.api import create_app
    from creditfile.config import Settings
    from fixture_support import sample_inputs

    app = create_app(tmp_path / "cases", settings=Settings(execution_mode="live"))
    cid = app.state.store.create("Synthetic failure", sample_inputs())
    monkeypatch.setattr("creditfile.providers.create_model", lambda settings: FakeModel("error"))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post(f"/api/v1/cases/{cid}/analyses")
        assert response.status_code == 200, response.text
        app.state.executor.shutdown(wait=True)
        job = client.get(f"/api/v1/cases/{cid}/jobs").json()[0]
        assert job["state"] == "failed", job
        result = app.state.store.raw_run(cid, job["run_id"])["result"]
        assert result["status"] == "failed" and len(result["errors"]) == 2


def test_metadata_edit_does_not_resurrect_old_amount_approval(case):
    store, cid, run = case
    rid = run["id"]
    store.review(cid, rid, "financials", "revenue", "accepted", "")
    store.review(cid, rid, "financials", "unit_scale", "unresolved", "Επανέλεγχος κλίμακας")
    store.review(cid, rid, "financials", "unit_scale", "accepted", "")
    doc = next(d for d in store.export(cid, rid)["documents"] if d["type"] == "financials")
    assert not doc["fields"]["revenue"]["approved_for_credit_memo"]
    assert doc["fields"]["revenue"]["requires_review"]


def test_replacement_invalidates_review_and_preserves_old_pdf(case):
    import hashlib
    from creditfile.config import Settings

    store, cid, run = case
    rid = run["id"]
    store.review(cid, rid, "financials", "revenue", "accepted", "")
    original = store.analysis_inputs(cid, rid)
    old = next(i for i in original if i["type"] == "financials")
    content = old["content"] + b"\n% synthetic replacement\n"
    store.replace_document(
        cid,
        "financials",
        "replacement.pdf",
        content,
        Settings(),
        hashlib.sha256(old["content"]).hexdigest(),
        True,
    )
    assert store.analysis_inputs(cid, rid) == original
    doc = next(d for d in store.export(cid, rid)["documents"] if d["type"] == "financials")
    assert all(
        not f["approved_for_credit_memo"] and f["requires_review"] for f in doc["fields"].values()
    )
    with pytest.raises(ValueError):
        store.replace_document(
            cid,
            "financials",
            "stale.pdf",
            content,
            Settings(),
            hashlib.sha256(old["content"]).hexdigest(),
            True,
        )


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Υπάρχει διαφορά το 2024;", False),
        ("Υπάρχει διαφορά το 2025;", True),
        ("Σύγκρινε 2024 και 2025", False),
    ],
)
def test_local_checks_do_not_substitute_current_year(question, expected):
    result = {
        "documents": [
            {"type": "financials", "fields": {"reporting_period": field("2025-01-01/2025-12-31")}}
        ]
    }
    assert chat.local_period_matches(question, result) is expected


@pytest.mark.parametrize("fabricated", [False, True])
def test_explicit_missing_registration_with_source_annotation(fabricated):
    from pathlib import Path
    from creditfile.config import Settings
    from creditfile.extraction import inspect_document, extraction_blocks, validate_fields
    from creditfile.schema import DocumentExtraction, FIELDS

    content = (Path(__file__).parent / "fixtures/application-missing-gemi.pdf").read_bytes()
    doc = inspect_document(content, "application.pdf", "application", Settings(), "synthetic-gemi")
    blocks = extraction_blocks(doc)
    block = next(b for b in blocks if "Αριθμός ΓΕΜΗ:" in b.text)
    quote = next(line.strip() for line in block.text.splitlines() if "Αριθμός ΓΕΜΗ:" in line)
    raw = "Δεν καταχωρήθηκε (εκκρεμεί βεβαίωση ΓΕΜΗ)"
    if fabricated:
        raw = "Δεν καταχωρήθηκε (εκκρεμεί πλαστή βεβαίωση)"
    fields = [
        dict(
            field_name=name,
            raw_value=raw if name == "registration_number" else None,
            confidence=1 if name == "registration_number" else 0,
            number_locale="unknown",
            uncertainty=None,
            evidence=[
                dict(document_id=doc["id"], block_id=block.block_id, page=block.page, quote=quote)
            ]
            if name == "registration_number"
            else [],
        )
        for name in FIELDS["application"]
    ]
    result = validate_fields(
        DocumentExtraction(document_type="application", fields=fields), doc, content, blocks, 0.8
    )["registration_number"]
    assert result["status"] == ("invalid" if fabricated else "missing")
    assert result["normalized_value"] is None and result["requires_review"]
    assert result["evidence"]["quote"] == quote
