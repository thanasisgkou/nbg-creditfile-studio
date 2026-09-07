"""Readiness uses current review decisions, including resolved and reopened checks."""

from uuid import uuid4

from fastapi.testclient import TestClient

from creditfile.api import create_app
from creditfile.config import Settings
from creditfile.demo_portfolio import seed_portfolio
from creditfile.chat_workflow import workflow_intent
from creditfile import bulletin
from creditfile.bulk_review import accept_selected, eligibility


def test_workflow_phrasings_and_financial_boundaries():
    for question in [
        "ειναι ετοιμος ο φακελος?",
        "έχει μείνει κάτι ανοιχτό;",
        "τι μενει ανοιχτο?",
        "Τι εκκρεμεί στον φάκελο;",
        "τι λείπει;",
        "χρειάζεται κάτι άλλο;",
        "Τι πρέπει να κάνω;",
        "Ποιο είναι το επόμενο βήμα;",
        "όλα καλά;",
        "Ολοκληρώθηκε ο φάκελος;",
        "Μπορώ να εκδώσω δελτίο;",
        "ο φάκελος είναι οκ;",
        "Τι προβλήματα έχει ο φάκελος;",
        "Is the case ready?",
        "What is still pending?",
    ]:
        assert workflow_intent(question, []), question
    for question in [
        "Τι ποσό μένει ανοιχτό στο δάνειο;",
        "Ποιο είναι το ανοιχτό υπόλοιπο;",
        "Ποιο ποσό χρηματοδότησης ζητείται;",
        "Υπάρχει διαφορά στον δανεισμό;",
        "Είναι έτοιμος ο φάκελος για έγκριση;",
        "Τι λείπει στον άλλο φάκελο;",
        "Τι εκκρεμούσε το 2024;",
        "Τι είναι το EBITDA;",
        "γιατί;",
        "πιο απλά",
    ]:
        assert not workflow_intent(question, []), question
    for question in ["γιατί;", "τι εννοείς;", "πιο απλά", "και τώρα;", "είναι έτοιμος τώρα;"]:
        assert workflow_intent(question, [{"mode": "local_workflow"}]), question
        assert not workflow_intent(question, [{"mode": "live"}]), question


def test_chat_reports_current_portfolio_state_without_a_model(tmp_path, monkeypatch):
    def no_provider(*args, **kwargs):
        raise AssertionError("Workflow answers must not need an AI provider")

    monkeypatch.setattr("creditfile.providers.create_model", no_provider)
    app = create_app(tmp_path / "cases", settings=Settings(execution_mode="live"))
    store = app.state.store
    seed_portfolio(store)
    cases = {c["name"].split()[0]: c for c in store.cases()}
    sessions = {}
    with TestClient(app, base_url="http://127.0.0.1") as client:

        def ask(case, question):
            cid = case["id"]
            rid = store.runs(cid)[0]["id"]
            response = client.post(
                f"/api/v1/cases/{cid}/runs/{rid}/chat",
                json=dict(question=question, request_id=str(uuid4()), session_id=sessions.get(cid)),
            )
            assert response.status_code == 200, response.text
            answer = response.json()
            sessions[cid] = answer["session_id"]
            turn = answer["turn"]
            assert turn["mode"] == "local_workflow" and turn["status"] == "answered"
            assert not turn["calls"] and not turn["error"] and not turn["unanswered"]
            assert (
                turn["workflow"]["fingerprint"] == bulletin.preview(store, cid, rid)["fingerprint"]
            )
            return turn

        winery = cases["Σταφυλάκης"]
        attention = cases["Attention"]
        hotel = cases["Ypnos"]
        ready = ask(winery, "ειναι ετοιμος ο φακελος?")
        assert (
            ready["workflow"]["complete"]
            and "έχει ολοκληρωθεί" in ready["message"]
            and "10/10" in ready["message"]
        )
        assert not ready["claims"]
        for question in ["έχει μείνει κάτι ανοιχτό;", "τι μενει ανοιχτο?"]:
            turn = ask(attention, question)
            assert not turn["workflow"]["complete"] and "4/10" in turn["message"]
            assert turn["message"].startswith("Υπάρχουν ακόμη εκκρεμότητες.")
            assert any("ΓΕΜΗ" in c["text"] for c in turn["claims"])
            assert any("οικονομικών" in c["text"] for c in turn["claims"])
        turn = ask(hotel, "τι εκκρεμεί;")
        assert not turn["workflow"]["complete"]
        assert any("300.000,00 €" in c["text"] and c["sources"] for c in turn["claims"])

        # The validated resolution, rather than the original failed comparison,
        # determines whether this discrepancy is still open.
        cid = hotel["id"]
        rid = store.runs(cid)[0]["id"]
        conflict = bulletin.preview(store, cid, rid)["conflicts"][0]
        bulletin.resolve(
            store,
            cid,
            rid,
            conflict["check_id"],
            "Συνθετική τεκμηριωμένη διευκρίνιση δοκιμής",
            conflict["evidence"],
            conflict["basis"],
        )
        assert ask(hotel, "είναι έτοιμος τώρα;")["workflow"]["complete"]
        store.review(
            cid, rid, "application", "declared_existing_debt", "accepted", "Επανέλεγχος δοκιμής"
        )
        assert ask(hotel, "και τώρα;")["workflow"]["complete"]
        store.review(
            cid,
            rid,
            "application",
            "declared_existing_debt",
            "unresolved",
            "Χρειάζεται νέα διευκρίνιση",
        )
        assert not ask(hotel, "και τώρα;")["workflow"]["complete"]

        # Completing the bulletin's ten fields must not hide missing GEMI outside it.
        cid = attention["id"]
        rid = store.runs(cid)[0]["id"]
        exported = store.export(cid, rid)
        selected = [
            (d["type"], name)
            for d in exported["documents"]
            for name, field in d["fields"].items()
            if eligibility(field)[0]
        ]
        accept_selected(store, cid, rid, selected, bulletin.fingerprint(store, cid, rid))
        assert not bulletin.preview(store, cid, rid)["draft"]
        turn = ask(attention, "χρειάζεται κάτι άλλο;")
        assert not turn["workflow"]["complete"] and "10/10" in turn["message"]
        assert any("ΓΕΜΗ" in c["text"] for c in turn["claims"])

        # A previously complete answer is context, not current evidence.
        cid = winery["id"]
        rid = store.runs(cid)[0]["id"]
        store.review(
            cid, rid, "financials", "revenue", "unresolved", "Εκκρεμεί επανέλεγχος δοκιμής"
        )
        turn = ask(winery, "τι μένει ανοιχτό;")
        assert not turn["workflow"]["complete"] and any(
            "Κύκλος" in c["text"] for c in turn["claims"]
        )
