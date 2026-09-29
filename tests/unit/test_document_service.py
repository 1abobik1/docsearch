"""Business rules of DocumentService, checked with in-memory fakes (no infrastructure)."""

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from types import TracebackType
from typing import Self

import pytest

from app.core.exceptions import DocumentNotFoundError, SearchUnavailableError
from app.domain import Document, NewDocument
from app.services.documents import DocumentService


def doc(id_: int, day: int) -> Document:
    return Document(
        id=id_, text=f"doc {id_}", rubrics=[], created_date=datetime(2019, 1, day, tzinfo=UTC)
    )


class FakeRepository:
    def __init__(self, docs: list[Document]) -> None:
        self.docs = {d.id: d for d in docs}

    async def get_many_by_date(self, ids: Sequence[int]) -> list[Document]:
        found = [self.docs[i] for i in ids if i in self.docs]
        return sorted(found, key=lambda d: d.created_date, reverse=True)

    async def delete(self, document_id: int) -> bool:
        return self.docs.pop(document_id, None) is not None

    async def add_many(self, documents: Sequence[NewDocument]) -> list[int]:
        raise NotImplementedError

    async def count(self) -> int:
        return len(self.docs)

    async def iter_all(self, batch_size: int) -> AsyncIterator[list[Document]]:
        yield list(self.docs.values())


class FakeUnitOfWork:
    """Snapshot on enter, restore on exit unless committed — like a real transaction."""

    def __init__(self, repo: FakeRepository) -> None:
        self.documents = repo
        self.committed = False
        self.entered = False

    async def __aenter__(self) -> Self:
        self.entered = True
        self._snapshot = dict(self.documents.docs)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self.committed:
            self.documents.docs = self._snapshot

    async def commit(self) -> None:
        self.committed = True


class FakeIndex:
    def __init__(self, hits: list[int], fail: bool = False) -> None:
        self.hits = hits
        self.fail = fail
        self.deleted: list[int] = []
        self.requested_limit: int | None = None

    async def search(self, query: str, limit: int) -> list[int]:
        self.requested_limit = limit
        return self.hits[:limit]

    async def delete(self, document_id: int) -> None:
        if self.fail:
            raise SearchUnavailableError
        self.deleted.append(document_id)


@pytest.fixture
def repo() -> FakeRepository:
    return FakeRepository([doc(1, 1), doc(2, 3), doc(3, 2)])


def make_service(repo: FakeRepository, index: FakeIndex) -> tuple[DocumentService, FakeUnitOfWork]:
    uow = FakeUnitOfWork(repo)
    return DocumentService(lambda: uow, index, search_limit=20), uow


async def test_search_orders_hits_by_date(repo: FakeRepository) -> None:
    index = FakeIndex(hits=[1, 2, 3, 42])
    service, _ = make_service(repo, index)

    result = await service.search("doc")

    assert [d.id for d in result] == [2, 3, 1]  # 42 is only in the index -> dropped
    assert index.requested_limit == 20


async def test_search_without_hits_does_not_touch_db(repo: FakeRepository) -> None:
    service, uow = make_service(repo, FakeIndex(hits=[]))

    assert await service.search("nothing") == []
    assert not uow.entered


async def test_delete_removes_from_db_and_index(repo: FakeRepository) -> None:
    index = FakeIndex(hits=[])
    service, uow = make_service(repo, index)

    await service.delete(2)

    assert 2 not in repo.docs
    assert index.deleted == [2]
    assert uow.committed


async def test_delete_unknown_does_not_touch_index(repo: FakeRepository) -> None:
    index = FakeIndex(hits=[])
    service, uow = make_service(repo, index)

    with pytest.raises(DocumentNotFoundError):
        await service.delete(100)

    assert index.deleted == []
    assert not uow.committed


async def test_delete_rolls_back_when_index_fails(repo: FakeRepository) -> None:
    service, uow = make_service(repo, FakeIndex(hits=[], fail=True))

    with pytest.raises(SearchUnavailableError):
        await service.delete(2)

    assert not uow.committed
    assert 2 in repo.docs
