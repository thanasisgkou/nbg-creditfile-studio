from creditfile.conversation import explain_previous
from chat_support import FakeModel


def test_new_ebitda_topic_does_not_inherit_debt_loop():
    from creditfile.conversation import relevant_history

    history = [
        dict(question="τι έχει κάνει λάθος;", claims=[{"check_id": "debt_match"}]),
        dict(question="ναι", claims=[], unanswered=["Τι σημαίνει η διαφορά στον δανεισμό;"]),
    ]
    assert relevant_history("Αφού το EBITDA είναι θετικό, γιατί είναι ζημιογόνος;", history) == []
    assert relevant_history("τι σημαίνει αυτό για τον δανεισμό;", history) == history


def check(status="FAIL", left=1120000, right=1420000):
    return dict(
        check_id="debt_match",
        status=status,
        left_value=left,
        right_value=right,
        absolute_difference=abs(left - right),
        evidence=[{"page": 2, "quote": "debt"}],
    )


def test_user_dialog_keeps_check_through_repeated_clarifications():
    history = [
        dict(
            question="τι εχει κανει λαθος?",
            mode="local_checks",
            claims=[{"check_id": "debt_match", "text": "old answer"}],
        )
    ]
    for question in [
        "δεν καταλαβα που ειναι το λαθος",
        "γιατι το εβγαλες λαθος?",
        "γιατι εβγαλες οτι ειναι λαθος το ποσο?",
        "τι σημαινει αυτο που ειπες για τον δανεισμο?",
        "ειπες εχει διαφορα στο ποσο δλδ εβαλε αλλο ποσο?",
        "ναι",
    ]:
        answer = explain_previous(question, history, {"checks": [check()]})
        assert answer and "300.000,00 € λιγότερα" in answer["claims"][0]["text"]
        assert "Δεν αποδεικνύει" in answer["claims"][0]["text"]
        history.append(dict(question=question, claims=[], unanswered=["Τι εννοείτε;"]))


def test_current_checks_override_old_answer_and_no_unrelated_topic():
    history = [dict(question="δανεισμός", claims=[{"check_id": "debt_match", "text": "9999999"}])]
    view = {"reviewed_checks": [check("PASS", 100, 100)]}
    result = explain_previous("γιατί;", history, view)
    assert "9999999" not in str(result)
    assert "δεν εντοπίζει απόκλιση" in result["claims"][0]["text"]
    assert explain_previous("γιατί είναι λάθος το αιτούμενο ποσό;", history, view) is None
    assert explain_previous("γιατί;", history, {"checks": [check("NOT_CHECKED")]}) is None


def test_unrelated_substantive_answer_stops_old_check_reference():
    history = [
        dict(question="δανεισμός", claims=[{"check_id": "debt_match"}]),
        dict(question="σκοπός", claims=[{"text": "investment"}]),
    ]
    assert explain_previous("δεν κατάλαβα", history, {"checks": [check()]}) is None


def test_conversation_uses_fresh_evidence_without_model_call(case):
    from creditfile.chat import ask

    store, cid, run = case
    model = FakeModel("missing")
    view = store.export(cid, run["id"])
    history = [
        dict(
            case_id=cid,
            run_id=run["id"],
            question="τι είναι λάθος;",
            claims=[{"check_id": "debt_match", "text": "stale value"}],
            unanswered=[],
        )
    ]
    result = ask(
        cid,
        run,
        store.inputs(cid),
        "δεν κατάλαβα πού είναι το λάθος",
        history,
        model,
        view,
        conversational=True,
    )
    assert result["mode"] == "local_checks"
    assert result["claims"][0]["sources"]
    assert "stale value" not in str(result)
    assert not model.calls


def test_planner_receives_assistant_context_but_not_failed_claims(monkeypatch):
    from creditfile.chat_rewrite import rewrite
    from creditfile.model import ModelError

    def generate(self, prompt, schema):
        assert "prior debt finding" in prompt
        assert "invalid fabricated claim" not in prompt
        assert "never as factual evidence" in prompt
        raise ModelError("test stops before provider")

    monkeypatch.setattr("creditfile.chat_rewrite.CompatibleModel.generate", generate)
    rewrite(
        FakeModel().settings,
        "γιατί;",
        [
            dict(question="έλεγχος", claims=[{"text": "prior debt finding"}]),
            dict(
                question="άλλο", error="bad citation", claims=[{"text": "invalid fabricated claim"}]
            ),
        ],
        conversational=True,
    )


def test_identity_scope_does_not_include_debt():
    from creditfile.conversation import identity_question

    view = {
        "documents": [
            {
                "type": "application",
                "fields": {
                    "registration_number": {"normalized_value": None},
                    "declared_existing_debt": {"normalized_value": 520000},
                    "tax_id": {"normalized_value": "123456789", "approved_for_credit_memo": True},
                },
            }
        ],
        "checks": [check()],
    }
    result = identity_question(
        "Και ποια στοιχεία νομιμοποίησης λείπουν ή χρειάζονται έλεγχο στην αίτηση;", view
    )
    assert "ΓΕΜΗ" in str(result)
    assert "520000" not in str(result) and "δανεισμό" not in str(result)


def test_definition_followup_preserves_topic_and_subject_change():
    from creditfile.chat_ux import followup, definition_intent

    question = "τι εννουμε με την περιοδο χαριτος?"
    history = [dict(question=question, claims=[], unanswered=["Τι εννοείτε;"])]
    assert definition_intent(question)
    assert followup("ναι", history) == (question, [])
    assert followup("τι ειναι το γεμη", history) == ("τι ειναι το γεμη", [])
    assert not definition_intent("τι είναι λάθος στον δανεισμό;")


def test_definition_does_not_repeat_planner_or_answer_clarification(case, monkeypatch):
    from dataclasses import replace
    from creditfile.chat import ask
    from creditfile.chat_rewrite import QueryPlan
    from creditfile.chat_ux import DEFINITION_SCOPE

    store, cid, run = case
    model = FakeModel()
    model.settings = replace(model.settings, chat_query_rewrite=True)
    monkeypatch.setattr("creditfile.chat_fallback.lexical_coverage", lambda *args: 0)
    monkeypatch.setattr(
        "creditfile.chat_rewrite.rewrite",
        lambda *args, **kwargs: (
            QueryPlan(
                route="clarify",
                query="",
                clarification="Τι εννοείτε με περίοδο χάριτος;",
                check_topic="all",
                exclude_amount_differences=False,
            ),
            [],
            None,
        ),
    )

    def generate(prompt, schema):
        model.prompts.append(prompt)
        return schema(
            status="needs_review", claims=[], unanswered=["Τι εννοείτε με περίοδο χάριτος;"]
        )

    model.generate = generate
    history = []
    for question in ["τι εννουμε με την περιοδο χαριτος?", "ναι", "τι ειναι το γεμη"]:
        answer = ask(cid, run, store.inputs(cid), question, history, model, conversational=True)
        assert answer["status"] == "not_found"
        assert answer["unanswered"] == [DEFINITION_SCOPE]
        assert not answer["claims"] and not answer["sources"]
        assert "never ask the user to define the term" in model.prompts[-1]
        history.append(answer)
    assert answer["resolved_question"] == "τι ειναι το γεμη"
