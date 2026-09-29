import httpx
from elasticsearch import AsyncElasticsearch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models import DocumentModel
from tests.functional.conftest import SeedFn, make_doc


async def db_ids(session_factory: async_sessionmaker[AsyncSession]) -> set[int]:
    async with session_factory() as session:
        return set(await session.scalars(select(DocumentModel.id)))


async def test_deletes_from_database_and_index(
    client: httpx.AsyncClient,
    seed: SeedFn,
    session_factory: async_sessionmaker[AsyncSession],
    es: AsyncElasticsearch,
    settings: Settings,
) -> None:
    doc, other = await seed(make_doc("скин один"), make_doc("скин два"))

    response = await client.delete(f"/api/v1/documents/{doc.id}")

    assert response.status_code == 204
    assert response.content == b""
    assert await db_ids(session_factory) == {other.id}
    assert not await es.exists(index=settings.elasticsearch_index, id=str(doc.id))
    await es.indices.refresh(index=settings.elasticsearch_index)
    search = await client.get("/api/v1/documents/search", params={"query": "скин"})
    assert [i["id"] for i in search.json()["items"]] == [other.id]


async def test_second_delete_returns_404(client: httpx.AsyncClient, seed: SeedFn) -> None:
    [doc] = await seed(make_doc("скин"))

    assert (await client.delete(f"/api/v1/documents/{doc.id}")).status_code == 204
    response = await client.delete(f"/api/v1/documents/{doc.id}")

    assert response.status_code == 404
    assert response.json() == {"detail": f"Document {doc.id} not found"}


async def test_unknown_id_returns_404(client: httpx.AsyncClient, seed: SeedFn) -> None:
    await seed(make_doc("скин"))

    assert (await client.delete("/api/v1/documents/100500")).status_code == 404


async def test_rejects_invalid_id(client: httpx.AsyncClient) -> None:
    for bad in ("0", "-1", "abc"):
        assert (await client.delete(f"/api/v1/documents/{bad}")).status_code == 422, bad


async def test_keeps_document_when_index_is_unavailable(
    client_without_es: httpx.AsyncClient,
    seed: SeedFn,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    [doc] = await seed(make_doc("скин"))

    response = await client_without_es.delete(f"/api/v1/documents/{doc.id}")

    # Transaction is rolled back: DB and index stay consistent, the call can be retried.
    assert response.status_code == 503
    assert await db_ids(session_factory) == {doc.id}
