import httpx
from elasticsearch import AsyncElasticsearch

from app.core.config import Settings
from tests.functional.conftest import SeedFn, make_doc

URL = "/api/v1/documents/search"


async def search(client: httpx.AsyncClient, query: str) -> list[dict[str, object]]:
    response = await client.get(URL, params={"query": query})
    assert response.status_code == 200, response.text
    items: list[dict[str, object]] = response.json()["items"]
    return items


async def test_returns_all_db_fields(client: httpx.AsyncClient, seed: SeedFn) -> None:
    [doc] = await seed(make_doc("Конкурс на новый скин", "2019-05-31T17:18:42", ["VK-1", "VK-2"]))

    assert await search(client, "скин") == [
        {
            "id": doc.id,
            "rubrics": ["VK-1", "VK-2"],
            "text": "Конкурс на новый скин",
            "created_date": "2019-05-31T17:18:42Z",
        }
    ]


async def test_results_are_ordered_by_created_date_desc(
    client: httpx.AsyncClient, seed: SeedFn
) -> None:
    await seed(
        make_doc("скин один", "2019-03-01"),
        make_doc("скин два", "2019-12-01"),
        make_doc("скин три", "2019-07-01"),
        make_doc("что-то другое", "2020-01-01"),
    )

    items = await search(client, "скин")

    assert [i["text"] for i in items] == ["скин два", "скин три", "скин один"]


async def test_returns_at_most_20_documents(client: httpx.AsyncClient, seed: SeedFn) -> None:
    await seed(*(make_doc(f"новость номер {n}", f"2019-01-{n:02d}") for n in range(1, 26)))

    items = await search(client, "новость")

    assert len(items) == 20
    dates = [str(i["created_date"]) for i in items]
    assert dates == sorted(dates, reverse=True)


async def test_takes_the_most_relevant_documents_before_sorting_by_date(
    client: httpx.AsyncClient, seed: SeedFn
) -> None:
    # 20 recent weak matches and one old document that matches much better.
    weak = [make_doc(f"скин {'бла ' * 50}{n}", f"2019-12-{n:02d}") for n in range(1, 21)]
    [strong, *_] = await seed(make_doc("скин скин скин", "2019-01-01"), *weak)

    items = await search(client, "скин")

    assert len(items) == 20
    assert strong.id in {i["id"] for i in items}
    assert items[-1]["id"] == strong.id  # the oldest one goes last


async def test_uses_russian_morphology(client: httpx.AsyncClient, seed: SeedFn) -> None:
    [doc] = await seed(make_doc("Итоги конкурса подведём завтра"))

    for query in ("конкурс", "КОНКУРСЫ", "итог", "подведем"):
        assert [i["id"] for i in await search(client, query)] == [doc.id], query


async def test_requires_all_query_terms(client: httpx.AsyncClient, seed: SeedFn) -> None:
    both, _ = await seed(make_doc("новый скин для Леона"), make_doc("новый режим игры"))

    assert [i["id"] for i in await search(client, "новый скин")] == [both.id]


async def test_no_matches_returns_empty_list(client: httpx.AsyncClient, seed: SeedFn) -> None:
    await seed(make_doc("что-то совсем другое"))

    assert await search(client, "бравл") == []


async def test_search_before_any_data_is_indexed(client: httpx.AsyncClient) -> None:
    response = await client.get(URL, params={"query": "скин"})

    # The index does not exist at all: this is an infrastructure problem, not "no results".
    assert response.status_code == 503


async def test_skips_documents_missing_in_database(
    client: httpx.AsyncClient,
    seed: SeedFn,
    es: AsyncElasticsearch,
    settings: Settings,
) -> None:
    [doc] = await seed(make_doc("скин"))
    # A stale entry in the index (e.g. left after a failed commit) must not leak out.
    await es.index(
        index=settings.elasticsearch_index,
        id="999",
        document={"id": 999, "text": "скин"},
        refresh=True,
    )

    assert [i["id"] for i in await search(client, "скин")] == [doc.id]


async def test_rejects_blank_query(client: httpx.AsyncClient) -> None:
    for params in ({}, {"query": ""}, {"query": "   "}, {"query": "x" * 1001}):
        response = await client.get(URL, params=params)
        assert response.status_code == 422, params


async def test_returns_503_when_search_is_unavailable(client_without_es: httpx.AsyncClient) -> None:
    response = await client_without_es.get(URL, params={"query": "скин"})

    assert response.status_code == 503
    assert response.headers["Retry-After"]
