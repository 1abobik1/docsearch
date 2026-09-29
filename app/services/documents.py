import logging
from collections.abc import Callable

from app.core.exceptions import DocumentNotFoundError
from app.domain import Document
from app.repositories.documents import UnitOfWork
from app.search.index import DocumentIndex

logger = logging.getLogger(__name__)


class DocumentService:
    """Use cases of the service. Depends only on abstractions (ports)."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        index: DocumentIndex,
        search_limit: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._index = index
        self._search_limit = search_limit

    async def search(self, query: str) -> list[Document]:
        """Top-N most relevant documents, returned ordered by creation date (newest first).

        The index finds *which* documents match; the database, as the source of
        truth, provides all fields and the ordering. Ids that are present in the
        index but already gone from the database are silently dropped.
        """
        ids = await self._index.search(query, limit=self._search_limit)
        if not ids:
            return []
        async with self._uow_factory() as uow:
            return await uow.documents.get_many_by_date(ids)

    async def delete(self, document_id: int) -> None:
        """Delete from the database and the index consistently.

        The row is deleted inside a transaction that is committed only after the
        index deletion succeeds. If Elasticsearch is unavailable the transaction
        rolls back, nothing changes, and the (idempotent) request can be retried.
        """
        async with self._uow_factory() as uow:
            if not await uow.documents.delete(document_id):
                raise DocumentNotFoundError(document_id)
            await self._index.delete(document_id)
            await uow.commit()
        logger.info("Document %s deleted", document_id)
