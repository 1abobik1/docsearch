from collections.abc import AsyncIterator, Sequence
from types import TracebackType
from typing import Protocol, Self

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import DocumentModel
from app.domain import Document, NewDocument


class DocumentRepository(Protocol):
    async def get_many_by_date(self, ids: Sequence[int]) -> list[Document]:
        """Documents with the given ids, newest first. Unknown ids are skipped."""

    async def delete(self, document_id: int) -> bool:
        """Delete a document; return False if it did not exist."""

    async def add_many(self, documents: Sequence[NewDocument]) -> list[int]: ...

    async def count(self) -> int: ...

    def iter_all(self, batch_size: int) -> AsyncIterator[list[Document]]: ...


class UnitOfWork(Protocol):
    """Transaction boundary. Leaving the context without `commit()` rolls back."""

    @property
    def documents(self) -> DocumentRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


def _to_domain(model: DocumentModel) -> Document:
    return Document(
        id=model.id,
        rubrics=list(model.rubrics),
        text=model.text,
        created_date=model.created_date,
    )


class SqlDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_many_by_date(self, ids: Sequence[int]) -> list[Document]:
        if not ids:
            return []
        stmt = (
            select(DocumentModel)
            .where(DocumentModel.id.in_(ids))
            .order_by(DocumentModel.created_date.desc(), DocumentModel.id.desc())
        )
        result = await self._session.scalars(stmt)
        return [_to_domain(m) for m in result]

    async def delete(self, document_id: int) -> bool:
        stmt = delete(DocumentModel).where(DocumentModel.id == document_id)
        result = await self._session.scalar(stmt.returning(DocumentModel.id))
        return result is not None

    async def add_many(self, documents: Sequence[NewDocument]) -> list[int]:
        if not documents:
            return []
        stmt = insert(DocumentModel).returning(DocumentModel.id, sort_by_parameter_order=True)
        rows = [
            {"rubrics": d.rubrics, "text": d.text, "created_date": d.created_date}
            for d in documents
        ]
        result = await self._session.scalars(stmt, rows)
        return list(result)

    async def count(self) -> int:
        return await self._session.scalar(select(func.count()).select_from(DocumentModel)) or 0

    async def iter_all(self, batch_size: int) -> AsyncIterator[list[Document]]:
        # Keyset pagination: stable and O(batch) regardless of table size.
        last_id = 0
        while True:
            stmt = (
                select(DocumentModel)
                .where(DocumentModel.id > last_id)
                .order_by(DocumentModel.id)
                .limit(batch_size)
            )
            batch = [_to_domain(m) for m in await self._session.scalars(stmt)]
            if not batch:
                return
            yield batch
            last_id = batch[-1].id


class SqlUnitOfWork:
    documents: DocumentRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self.documents = SqlDocumentRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            await self._session.rollback()  # no-op after a successful commit
        finally:
            await self._session.close()

    async def commit(self) -> None:
        await self._session.commit()
