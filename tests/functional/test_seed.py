from pathlib import Path

import httpx

from app.cli import seed
from app.core.config import Settings

DATASET = Path(__file__).resolve().parents[2] / "data" / "posts.csv"


async def test_seed_imports_dataset_and_is_idempotent(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    await seed(settings, DATASET)
    await seed(settings, DATASET)  # second run must be a no-op

    response = await client.get("/api/v1/documents/search", params={"query": "конкурс"})

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 20
    assert all("конкурс" in i["text"].lower() for i in items)
    ids = [i["id"] for i in items]
    assert len(set(ids)) == 20
    assert max(ids) <= 1500
