"""Management commands.

python -m app.cli seed data/posts.csv   # import CSV (if DB is empty) and build the index
python -m app.cli load-csv data/posts.csv
python -m app.cli reindex               # rebuild the ES index from the DB, zero downtime
python -m app.cli export-openapi docs.json
"""

import argparse
import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from elasticsearch import AsyncElasticsearch
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.db.session import create_engine, create_session_factory
from app.repositories.documents import SqlUnitOfWork
from app.search.index import alias_exists, rebuild_index
from app.services.loader import load_csv

logger = logging.getLogger("app.cli")

REINDEX_BATCH_SIZE = 500


@asynccontextmanager
async def _resources(
    settings: Settings,
) -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], AsyncElasticsearch]]:
    engine = create_engine(settings)
    es = AsyncElasticsearch(settings.elasticsearch_url, request_timeout=60)
    try:
        yield create_session_factory(engine), es
    finally:
        await es.close()
        await engine.dispose()


async def reindex(settings: Settings) -> None:
    async with _resources(settings) as (session_factory, es):
        await _reindex(session_factory, es, settings)


async def _reindex(
    session_factory: async_sessionmaker[AsyncSession], es: AsyncElasticsearch, settings: Settings
) -> None:
    async with SqlUnitOfWork(session_factory) as uow:
        await rebuild_index(
            es, settings.elasticsearch_index, uow.documents.iter_all(REINDEX_BATCH_SIZE)
        )


async def load(settings: Settings, path: Path) -> None:
    async with _resources(settings) as (session_factory, _):
        await load_csv(SqlUnitOfWork(session_factory), path)


async def seed(settings: Settings, path: Path) -> None:
    """Idempotent bootstrap used by `docker compose up`."""
    async with _resources(settings) as (session_factory, es):
        async with SqlUnitOfWork(session_factory) as uow:
            count = await uow.documents.count()
        if count == 0:
            await load_csv(SqlUnitOfWork(session_factory), path)
            await _reindex(session_factory, es, settings)
        elif not await alias_exists(es, settings.elasticsearch_index):
            logger.info("Database has %d documents but no index, building it", count)
            await _reindex(session_factory, es, settings)
        else:
            logger.info("Database and index already initialized (%d documents), skipping", count)


def export_openapi(output: Path) -> None:
    from app.main import create_app  # noqa: PLC0415 - keep CLI startup light

    schema = create_app(get_settings()).openapi()
    output.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.info("OpenAPI schema written to %s", output)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="docsearch")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("seed", "load-csv"):
        cmd = sub.add_parser(name)
        cmd.add_argument("path", type=Path)
    sub.add_parser("reindex")
    cmd = sub.add_parser("export-openapi")
    cmd.add_argument("output", type=Path, nargs="?", default=Path("docs.json"))
    args = parser.parse_args(argv)

    settings = get_settings()
    setup_logging(settings.log_level)

    commands: dict[str, Callable[[], Coroutine[Any, Any, None]]] = {
        "seed": lambda: seed(settings, args.path),
        "load-csv": lambda: load(settings, args.path),
        "reindex": lambda: reindex(settings),
    }
    if args.command == "export-openapi":
        export_openapi(args.output)
    else:
        asyncio.run(commands[args.command]())


if __name__ == "__main__":
    main()
