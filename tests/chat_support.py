import pytest
import json
from creditfile.config import Settings
from creditfile.store import CaseStore
from creditfile import chat
from creditfile.model import ModelError
from fixture_support import create_fixture


@pytest.fixture
def case(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    store = CaseStore()
    cid = create_fixture(store)
    run = store.runs(cid)[0]
    return store, cid, run


class FakeModel:
    def __init__(self, mode="answer"):
        self.settings = Settings(num_ctx=131072, prompt_version=chat.PROMPT_VERSION)
        self.calls = []
        self.prompts = []
        self.mode = mode

    def fits(self, *args):
        return True

    def generate(self, prompt, schema):
        self.prompts.append(prompt)
        self.calls.append({"mode": "mock", "seconds": 0})
        if self.mode == "error":
            raise ModelError("API timeout")
        if self.mode == "missing":
            return schema(
                status="not_found", claims=[], unanswered=["Δεν τεκμηριώνεται στα αποσπάσματα."]
            )
        blocks = json.loads(prompt.split("Current source blocks:\n")[1])
        b = blocks[0]
        quote = next(line.strip() for line in b["text"].splitlines() if line.strip())
        e = dict(document_id=b["document_id"], page=b["page"], block_id=b["block_id"], quote=quote)
        if self.mode == "bad_citation":
            e["document_id"] = "another-case"
        return schema(
            status="answered", claims=[dict(text="Απάντηση δοκιμής", evidence=[e])], unanswered=[]
        )
