"""Health endpoints — public, no auth needed."""

from httpx import AsyncClient


async def test_root(client: AsyncClient) -> None:
    r = await client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "uod-backend"
    assert body["docs"] == "/docs"


async def test_health_db_up(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"
    assert "version" in body
