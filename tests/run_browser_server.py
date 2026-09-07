import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DATA_DIR"] = str(ROOT / "output" / "browser-tests")
os.environ["LLM_EXECUTION_MODE"] = "replay"
from creditfile.api import StudioStore
from fixture_support import create_fixture
from uuid import uuid4

store = StudioStore(ROOT / "output" / "browser-tests" / uuid4().hex / "cases")
for _ in range(4):
    create_fixture(store)
from creditfile.api import create_app
import uvicorn

uvicorn.run(
    create_app(root=store.root),
    host="127.0.0.1",
    port=int(os.environ.get("STUDIO_TEST_PORT", "8521")),
)
