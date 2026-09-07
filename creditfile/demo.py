"""Initialize a local workspace with explicitly synthetic, recorded examples."""

import json
from dataclasses import replace

from .config import ROOT
from .demo_portfolio import seed_portfolio
from .extraction import PROMPT_VERSION, process_case


class DemoModel:
    """Replay labelled fixture proposals without contacting a provider."""

    def __init__(self, settings):
        self.settings = replace(
            settings, model="fixture/preauthored-ui", prompt_version=PROMPT_VERSION
        )
        self.calls = []
        data = json.loads(
            (ROOT / "tests/fixtures/fixture-responses.json").read_text(encoding="utf-8")
        )
        self.responses = iter(data["responses"])

    def generate(self, prompt, schema):
        return schema.model_validate(next(self.responses))


def seed_demo(store, settings):
    """Populate an empty store; never reset or overwrite an existing workspace."""
    if store.cases():
        return
    # Validate the PDF renderer before creating any cases.
    from .bulletin_pdf import fonts

    fonts()
    inputs = [
        dict(type=kind, name=name, content=(ROOT / "tests/fixtures" / name).read_bytes())
        for kind, name in [
            ("application", "SME_Financing_Application.pdf"),
            ("financials", "SME_Financial_Statements_2025.pdf"),
        ]
    ]
    cid = store.create("Aegean Foods · Συνθετικό παράδειγμα", inputs)
    result = process_case(cid, inputs, DemoModel(settings), settings)
    result.update(
        mode="fixture",
        provider="none",
        endpoint="none",
        seconds=0.0,
        notice="Συνθετικό παράδειγμα με προετοιμασμένη εξαγωγή, χωρίς κλήση AI.",
    )
    store.save_run(cid, result)
    seed_portfolio(store)
