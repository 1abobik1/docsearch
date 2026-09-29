import logging
from collections.abc import AsyncIterable, Iterable
from datetime import UTC, datetime
from typing import Any, Protocol

from elasticsearch import ApiError, AsyncElasticsearch, NotFoundError, TransportError
from elasticsearch.helpers import async_bulk

from app.core.exceptions import SearchUnavailableError
from app.domain import Document
from app.search.mapping import INDEX_MAPPINGS, INDEX_SETTINGS

logger = logging.getLogger(__name__)


class DocumentIndex(Protocol):
    async def search(self, query: str, limit: int) -> list[int]:
        """Ids of the `limit` most relevant documents for the query."""

    async def delete(self, document_id: int) -> None:
        """Remove a document from the index. Idempotent."""


class ElasticsearchDocumentIndex:
    def __init__(self, client: AsyncElasticsearch, alias: str) -> None:
        self._client = client
        self._alias = alias

    async def search(self, query: str, limit: int) -> list[int]:
        try:
            response = await self._client.search(
                index=self._alias,
                query={"match": {"text": {"query": query, "operator": "and"}}},
                size=limit,
                source=False,
                track_total_hits=False,
            )
        except (ApiError, TransportError) as exc:
            logger.exception("Search request failed")
            raise SearchUnavailableError from exc
        return [int(hit["_id"]) for hit in response["hits"]["hits"]]

    async def delete(self, document_id: int) -> None:
        try:
            await self._client.delete(index=self._alias, id=str(document_id))
        except NotFoundError:
            return
        except (ApiError, TransportError) as exc:
            logger.exception("Failed to delete document %s from index", document_id)
            raise SearchUnavailableError from exc


# ------------------------------------------------------------ index admin ---


def _to_action(index: str, document: Document) -> dict[str, Any]:
    return {
        "_op_type": "index",
        "_index": index,
        "_id": str(document.id),
        "_source": {"id": document.id, "text": document.text},
    }


async def index_documents(
    client: AsyncElasticsearch, index: str, documents: Iterable[Document]
) -> int:
    success, _ = await async_bulk(
        client, (_to_action(index, d) for d in documents), raise_on_error=True
    )
    return success


async def rebuild_index(
    client: AsyncElasticsearch,
    alias: str,
    batches: AsyncIterable[list[Document]],
) -> str:
    """Build a fresh versioned index and atomically point the alias at it.

    Readers keep using the old index until the swap, so a rebuild never
    causes downtime or partially filled search results.
    """
    new_index = f"{alias}-{datetime.now(UTC):%Y%m%d%H%M%S%f}"
    await client.indices.create(index=new_index, settings=INDEX_SETTINGS, mappings=INDEX_MAPPINGS)
    total = 0
    try:
        async for batch in batches:
            total += await index_documents(client, new_index, batch)
        await client.indices.refresh(index=new_index)
    except BaseException:
        await client.indices.delete(index=new_index, ignore_unavailable=True)
        raise

    old_indices = await _indices_behind_alias(client, alias)
    actions: list[dict[str, Any]] = [{"remove": {"index": i, "alias": alias}} for i in old_indices]
    actions.append({"add": {"index": new_index, "alias": alias}})
    await client.indices.update_aliases(actions=actions)
    for old in old_indices:
        await client.indices.delete(index=old, ignore_unavailable=True)

    logger.info("Indexed %d documents into %s (alias %s)", total, new_index, alias)
    return new_index


async def alias_exists(client: AsyncElasticsearch, alias: str) -> bool:
    return bool(await client.indices.exists_alias(name=alias))


async def _indices_behind_alias(client: AsyncElasticsearch, alias: str) -> list[str]:
    try:
        response = await client.indices.get_alias(name=alias)
    except NotFoundError:
        return []
    return list(response.body)
