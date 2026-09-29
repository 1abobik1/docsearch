import asyncio
import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import EsClientDep, SessionFactoryDep
from app.api.schemas import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", summary="Liveness probe")
async def live() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    summary="Readiness probe: checks PostgreSQL and Elasticsearch",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def ready(
    response: Response, session_factory: SessionFactoryDep, es: EsClientDep
) -> HealthResponse:
    async def check_db() -> bool:
        try:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            logger.exception("Database health check failed")
            return False
        return True

    async def check_es() -> bool:
        try:
            return bool(await es.ping())
        except Exception:
            logger.exception("Elasticsearch health check failed")
            return False

    db_ok, es_ok = await asyncio.gather(check_db(), check_es())
    healthy = db_ok and es_ok
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if healthy else "unavailable",
        checks={"postgres": db_ok, "elasticsearch": es_ok},
    )
