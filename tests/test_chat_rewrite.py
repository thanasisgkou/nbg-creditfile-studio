from dataclasses import replace
import pytest
from creditfile import chat
from creditfile.chat_rewrite import QueryPlan, rewrite
from creditfile.model import ModelError
from chat_support import FakeModel


@pytest.mark.parametrize("route", ["pdf", "checks", "reviews", "clarify", "out_of_scope"])
def test_planned_routes_preserve_question_and_calls(case, monkeypatch, route):
    store, cid, run = case
    model = FakeModel("missing")
    model.settings = replace(model.settings, chat_query_rewrite=True)
    plan = QueryPlan(
        route=route,
        query="Ημερομηνία υποβολής αίτησης",
        clarification="Εννοείς λάθος εξαγωγής ή ασυμφωνία στα έγγραφα;"
        if route == "clarify"
        else "",
        check_topic="all",
        exclude_amount_differences=False,
    )
    monkeypatch.setattr("creditfile.chat_fallback.lexical_coverage", lambda *args: 0)
    monkeypatch.setattr(
        "creditfile.chat_rewrite.rewrite", lambda *args: (plan, [{"operation": "QueryPlan"}], None)
    )
    q = "τι μπερδεψε στην αιτηση"
    answer = chat.ask(cid, run, store.inputs(cid), q, [], model, store.export(cid, run["id"]))
    assert answer["question"] == q and answer["query_rewrite"]["plan"]["route"] == route
    assert answer["calls"][0]["operation"] == "QueryPlan"
    assert len(model.calls) == (1 if route == "pdf" else 0)
    if route == "pdf":
        assert "\nQuestion:\n" + q + "\n" in model.prompts[0]
    if route == "clarify":
        assert answer["unanswered"] == [plan.clarification]
    if route == "checks":
        assert answer["mode"] == "local_checks"


def test_rewrite_failure_preserves_original_retrieval(case, monkeypatch):
    store, cid, run = case
    model = FakeModel("missing")
    model.settings = replace(model.settings, chat_query_rewrite=True)
    monkeypatch.setattr("creditfile.chat_fallback.lexical_coverage", lambda *args: 0)
    monkeypatch.setattr(
        "creditfile.chat_rewrite.rewrite",
        lambda *args: (None, [{"operation": "QueryPlan", "error": "test"}], "query_rewrite_failed"),
    )
    answer = chat.ask(cid, run, store.inputs(cid), "Πότε έγινε η αίτηση;", [], model)
    assert not answer["error"] and answer["retrieved_ids"]
    assert answer["query_rewrite"]["error"] == "query_rewrite_failed"
    assert len(model.calls) == 1 and len(answer["calls"]) == 2


def test_planner_uses_locked_openrouter_and_bounded_output(monkeypatch):
    def generate(self, prompt, schema):
        assert self.settings.provider == "openrouter" and self.settings.num_predict == 700
        assert self.settings.retries == 0
        assert "History contains only user questions" in prompt
        self.calls.append({"operation": "QueryPlan"})
        raise ModelError("unavailable")

    monkeypatch.setattr("creditfile.chat_rewrite.CompatibleModel.generate", generate)
    plan, calls, error = rewrite(FakeModel().settings, "Πότε έγινε η αίτηση;", [])
    assert plan is None and error and len(calls) == 1
