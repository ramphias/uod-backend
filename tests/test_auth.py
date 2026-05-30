"""Auth middleware behaviour."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from jose import jwt


async def test_anonymous_read_is_forbidden(client: AsyncClient) -> None:
    r = await client.get("/instances")
    # require_principal → 401 Unauthorized
    assert r.status_code == 401


async def test_invalid_token_rejected(client: AsyncClient, auth_headers) -> None:
    r = await client.get("/instances", headers=auth_headers("not-a-real-jwt"))
    assert r.status_code == 401


async def test_expired_token_rejected(client: AsyncClient, auth_headers) -> None:
    import os

    expired = jwt.encode(
        {
            "login": "octocat",
            "role": "viewer",
            "iat": int((datetime.now(UTC) - timedelta(hours=2)).timestamp()),
            "exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
        },
        os.environ["NEXTAUTH_SECRET"],
        algorithm="HS256",
    )
    r = await client.get("/instances", headers=auth_headers(expired))
    assert r.status_code == 401


async def test_viewer_can_read(client: AsyncClient, viewer_token, auth_headers) -> None:
    r = await client.get("/instances", headers=auth_headers(viewer_token))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["items"] == []


async def test_viewer_cannot_write(client: AsyncClient, viewer_token, auth_headers) -> None:
    payload = {
        "id": "test_one",
        "type": "Organization",
        "layer": "L1_universal_organization_ontology",
        "label_en": "Test",
        "schema_version": "2.1.0",
        "source": "manual",
    }
    r = await client.post("/instances", json=payload, headers=auth_headers(viewer_token))
    assert r.status_code == 403


async def test_editor_can_write(client: AsyncClient, editor_token, auth_headers) -> None:
    payload = {
        "id": "test_two",
        "type": "Organization",
        "layer": "L1_universal_organization_ontology",
        "label_en": "Test 2",
        "schema_version": "2.1.0",
        "source": "manual",
    }
    r = await client.post("/instances", json=payload, headers=auth_headers(editor_token))
    assert r.status_code == 201


async def test_editor_cannot_delete(
    client: AsyncClient, editor_token, admin_token, auth_headers
) -> None:
    payload = {
        "id": "test_three",
        "type": "Organization",
        "layer": "L1_universal_organization_ontology",
        "label_en": "Test 3",
        "schema_version": "2.1.0",
        "source": "manual",
    }
    await client.post("/instances", json=payload, headers=auth_headers(editor_token))
    r = await client.delete("/instances/test_three", headers=auth_headers(editor_token))
    assert r.status_code == 403
    r = await client.delete("/instances/test_three", headers=auth_headers(admin_token))
    assert r.status_code == 204
