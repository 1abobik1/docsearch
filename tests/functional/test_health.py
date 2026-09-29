import httpx


async def test_live(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.status_code == 200


async def test_ready(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"postgres": True, "elasticsearch": True}}


async def test_not_ready_without_elasticsearch(client_without_es: httpx.AsyncClient) -> None:
    response = await client_without_es.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {"postgres": True, "elasticsearch": False}
