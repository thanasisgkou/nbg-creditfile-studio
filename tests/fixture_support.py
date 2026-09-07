"""Visibly marked fixtures for offline UI testing; never a quality measurement."""

from dataclasses import replace
import json
from creditfile.config import ROOT, Settings
from creditfile.extraction import process_case, PROMPT_VERSION
from creditfile.store import CaseStore


def sample_inputs() -> list[dict]:
    return [
        dict(type=kind, name=name, content=(ROOT / "tests/fixtures" / name).read_bytes())
        for kind, name in [
            ("application", "SME_Financing_Application.pdf"),
            ("financials", "SME_Financial_Statements_2025.pdf"),
        ]
    ]


class FixtureModel:
    def __init__(self, settings: Settings):
        self.settings = replace(
            settings, model="fixture/preauthored-ui", prompt_version=PROMPT_VERSION
        )
        self.calls = []
        self.responses = json.loads(
            (ROOT / "tests/fixtures/fixture-responses.json").read_text(encoding="utf-8")
        )["responses"]
        self.index = 0

    def generate(self, prompt: str, schema):
        value = self.responses[self.index]
        self.index += 1
        return schema.model_validate(value)


def create_fixture(store: CaseStore) -> str:
    inputs = sample_inputs()
    cid = store.create("Aegean Foods | Synthetic UI fixture", inputs)
    settings = replace(Settings.load(), prompt_version=PROMPT_VERSION)
    result = process_case(cid, inputs, FixtureModel(settings), settings)
    result.update(
        mode="fixture",
        provider="none",
        endpoint="none",
        seconds=0.0,
        notice="Προσημασμένο fixture, όχι πραγματική απόκριση μοντέλου ή αξιολόγηση AI.",
    )
    store.save_run(cid, result)
    return cid
