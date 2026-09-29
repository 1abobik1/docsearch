"""Functional tests run against real PostgreSQL and Elasticsearch.

They use a dedicated database (created on demand) and a dedicated index alias,
so they never touch development data. Configure via DATABASE_URL /
ELASTICSEARCH_URL / ELASTICSEARCH_INDEX; defaults match `docker compose up`.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Callable, Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import pytest
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from elasticsearch import AsyncElasticsearch
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.session import create_engine, create_session_factory
from app.domain import Document, NewDocument
from app.main import create_app
from app.repositories.documents import SqlUnitOfWork
from app.search.index import rebuild_index

ROOT = Path(__file__).resolve().parents[2]

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://docsearch:docsearch@localhost:5432/docsearch_test"
)
os.environ.setdefault("ELASTICSEARCH_INDEX", "test-documents")
os.environ.setdefault("ENVIRONMENT", "test")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "functional" in item.nodeid:
            item.add_marker(pytest.mark.functional)


async def _ensure_database(url: str) -> None:
    parsed = make_url(url)
    conn = await asyncpg.connect(
        user=parsed.username,
        password=parsed.password,
        host=parsed.host,
        port=parsed.port or 5432,
        database="postgres",
    )
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", parsed.database
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{parsed.database}"')
    finally:
        await conn.close()


async def _drop_indices(es: AsyncElasticsearch, alias: str) -> None:
    # ES 9 forbids wildcard deletes (action.destructive_requires_name), resolve names first.
    found = await es.indices.get(index=f"{alias}-*", allow_no_indices=True)
    if found.body:
        await es.indices.delete(index=",".join(found.body))


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(log_level="WARNING")


@pytest.fixture(scope="session")
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    url = str(settings.database_url)
    await _ensure_database(url)
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["database_url"] = url
    # Migrations are part of what we test; env.py runs its own event loop.
    await asyncio.to_thread(command.upgrade, cfg, "head")
    engine = create_engine(settings)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest.fixture(scope="session")
async def es(settings: Settings) -> AsyncIterator[AsyncElasticsearch]:
    client = AsyncElasticsearch(settings.elasticsearch_url)
    yield client
    await _drop_indices(client, settings.elasticsearch_index)
    await client.close()


@pytest.fixture(autouse=True)
async def _clean_state(engine: AsyncEngine, es: AsyncElasticsearch, settings: Settings) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE documents RESTART IDENTITY"))
    await _drop_indices(es, settings.elasticsearch_index)


async def _client_for(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    async with (
        LifespanManager(app) as manager,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=manager.app), base_url="http://test"
        ) as client,
    ):
        yield client


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    async for c in _client_for(settings):
        yield c


@pytest.fixture
async def client_without_es(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    """App whose Elasticsearch is unreachable, while PostgreSQL works."""
    broken = settings.model_copy(
        update={"elasticsearch_url": "http://127.0.0.1:1", "elasticsearch_timeout": 1.0}
    )
    async for c in _client_for(broken):
        yield c


SeedFn = Callable[..., Coroutine[Any, Any, list[Document]]]


def make_doc(
    text: str, created: str = "2019-01-01", rubrics: list[str] | None = None
) -> NewDocument:
    return NewDocument(
        text=text,
        created_date=datetime.fromisoformat(created).replace(tzinfo=UTC),
        rubrics=rubrics if rubrics is not None else ["VK-1"],
    )


@pytest.fixture
def seed(
    session_factory: async_sessionmaker[AsyncSession], es: AsyncElasticsearch, settings: Settings
) -> SeedFn:
    """Insert documents into the DB and build the index from the DB, like production does."""

    async def _seed(*docs: NewDocument) -> list[Document]:
        async with SqlUnitOfWork(session_factory) as uow:
            ids = await uow.documents.add_many(docs)
            await uow.commit()
        async with SqlUnitOfWork(session_factory) as uow:
            await rebuild_index(es, settings.elasticsearch_index, uow.documents.iter_all(100))
        return [
            Document(id=i, text=d.text, created_date=d.created_date, rubrics=d.rubrics)
            for i, d in zip(ids, docs, strict=True)
        ]

    return _seed
