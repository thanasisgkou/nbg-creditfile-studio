"""Local startup preserves data and keeps optional credentials out of files."""

import sys
import pytest
import uvicorn
from fastapi.testclient import TestClient
from scripts import run


def test_local_restart_keeps_cases_and_review_decisions(tmp_path, monkeypatch):
    from creditfile import bulletin
    from creditfile.store import CaseStore

    (tmp_path / "frontend/dist").mkdir(parents=True)
    (tmp_path / "frontend/dist/index.html").write_text("<html></html>")
    monkeypatch.setattr(run, "ROOT", tmp_path)
    directory = tmp_path / "custom-data"
    monkeypatch.setattr(sys, "argv", ["run.py", "--port", "8529", "--data-dir", str(directory)])
    saved = {}

    def serve(app, **options):
        assert options["host"] == "127.0.0.1" and options["port"] == 8529
        assert (directory / ".writer.lock").exists()
        with TestClient(app, base_url="http://127.0.0.1") as client:
            assert client.get("/api/v1/health").json()["execution_mode"] == "replay"
            cases = client.get("/api/v1/cases").json()
            assert len(cases) == 4
            ids = {c["id"] for c in cases}
            if saved:
                assert ids == saved["ids"]
            else:
                case = next(c for c in cases if c["name"].startswith("Aegean"))
                store = app.state.store
                store.review(case["id"], case["run_id"], "application", "tax_id", "accepted", "")
                saved.update(
                    ids=ids,
                    case=case,
                    fingerprint=bulletin.fingerprint(store, case["id"], case["run_id"]),
                )
        with pytest.raises(SystemExit, match="already running"):
            run.main()

    monkeypatch.setattr(uvicorn, "run", serve)
    run.main()
    run.main()
    case = saved["case"]
    assert (
        bulletin.fingerprint(CaseStore(directory / "cases"), case["id"], case["run_id"])
        == saved["fingerprint"]
    )
    assert not list(directory.rglob("*.env"))


def test_live_key_is_prompted_and_not_persisted(tmp_path, monkeypatch):
    from creditfile import demo

    (tmp_path / "frontend/dist").mkdir(parents=True)
    (tmp_path / "frontend/dist/index.html").write_text("<html></html>")
    monkeypatch.setattr(run, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["run.py", "--live", "--data-dir", str(tmp_path / "data")])
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(run.getpass, "getpass", lambda prompt: "local-test-credential")
    monkeypatch.setattr(demo, "seed_demo", lambda store, settings: None)

    def serve(app, **options):
        from creditfile.config import api_key

        assert api_key("openrouter") == "local-test-credential"
        with TestClient(app, base_url="http://127.0.0.1") as client:
            assert client.get("/api/v1/health").json()["execution_mode"] == "live"

    monkeypatch.setattr(uvicorn, "run", serve)
    run.main()
    assert "OPENROUTER_API_KEY" not in run.os.environ
    assert not any(
        b"local-test-credential" in p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    )
