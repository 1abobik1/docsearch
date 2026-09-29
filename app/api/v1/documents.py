from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, status
from pydantic import StringConstraints

from app.api.deps import DocumentServiceDep
from app.api.schemas import DocumentOut, ErrorResponse, SearchResponse

router = APIRouter(prefix="/documents", tags=["documents"])

SearchQuery = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
    Query(description="Free-form text query", examples=["конкурс скин"]),
]
DocumentId = Annotated[int, Path(gt=0, description="Document id")]

_UNAVAILABLE: dict[int | str, dict[str, Any]] = {
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorResponse,
        "description": "Search backend is unavailable",
    }
}


@router.get(
    "/search",
    summary="Full-text search over documents",
    description=(
        "Finds documents whose text matches **all** words of the query (with Russian/English "
        "morphology), takes the 20 most relevant ones and returns them with all fields, "
        "ordered by creation date, newest first."
    ),
    responses={**_UNAVAILABLE},
)
async def search_documents(query: SearchQuery, service: DocumentServiceDep) -> SearchResponse:
    documents = await service.search(query)
    return SearchResponse(items=[DocumentOut.model_validate(d) for d in documents])


@router.delete(
    "/{document_id}",
    summary="Delete a document",
    description="Deletes the document from both the database and the search index.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Document not found"},
        **_UNAVAILABLE,
    },
)
async def delete_document(document_id: DocumentId, service: DocumentServiceDep) -> None:
    await service.delete(document_id)
