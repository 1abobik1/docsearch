from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import DocumentNotFoundError, SearchUnavailableError


async def _not_found(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


async def _unavailable(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Search backend is temporarily unavailable"},
        headers={"Retry-After": "5"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DocumentNotFoundError, _not_found)
    app.add_exception_handler(SearchUnavailableError, _unavailable)
