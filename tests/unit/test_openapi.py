import json
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

DOCS = Path(__file__).resolve().parents[2] / "docs.json"


def test_docs_json_is_up_to_date() -> None:
    """docs.json is committed for reviewers; make sure it never drifts from the code."""
    actual = create_app(Settings()).openapi()

    assert json.loads(DOCS.read_text(encoding="utf-8")) == actual, (
        "docs.json is stale, run `make openapi`"
    )
