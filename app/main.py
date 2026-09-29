from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from elasticsearch import AsyncElasticsearch
from fastapi import APIRouter, FastAPI

from app import __version__
from app.api import health
from app.api.errors import register_exception_handlers
from app.api.v1 import documents
from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.db.session import create_engine, create_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        es = AsyncElasticsearch(
            settings.elasticsearch_url,
            request_timeout=settings.elasticsearch_timeout,
            retry_on_timeout=True,
            max_retries=2,
        )
        app.state.settings = settings
        app.state.session_factory = create_session_factory(engine)
        app.state.es = es
        try:
            yield
        finally:
            await es.close()
            await engine.dispose()

    app = FastAPI(
        title="Document Search API",
        version=__version__,
        description=(
            "A simple search engine over document texts. Documents are stored in "
            "PostgreSQL, the full-text index lives in Elasticsearch."
        ),
        lifespan=lifespan,
    )

    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(documents.router)
    app.include_router(api_v1)
    app.include_router(health.router)
    register_exception_handlers(app)
    return app
