"""CRUD + lifecycle endpoints for instances."""

from httpx import AsyncClient

VALID_PAYLOAD = {
    "id": "org_acme",
    "type": "Organization",
    "layer": "L1_universal_organization_ontology",
    "label_en": "Acme Corporation",
    "label_zh": "示例公司",
    "schema_version": "2.1.0",
    "source": "manual",
    "source_url": "https://example.com/acme",
    "confidence": "1.0",
    "status": "accepted",
}


async def test_create_get_list(client: AsyncClient, editor_token, auth_headers) -> None:
    r = await client.post("/instances", json=VALID_PAYLOAD, headers=auth_headers(editor_token))
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["id"] == "org_acme"
    assert created["status"] == "accepted"

    r = await client.get(f"/instances/{created['id']}", headers=auth_headers(editor_token))
    assert r.status_code == 200
    assert r.json()["label_en"] == "Acme Corporation"

    r = await client.get("/instances?limit=5", headers=auth_headers(editor_token))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == "org_acme"


async def test_duplicate_create_conflict(client: AsyncClient, editor_token, auth_headers) -> None:
    await client.post("/instances", json=VALID_PAYLOAD, headers=auth_headers(editor_token))
    r = await client.post("/instances", json=VALID_PAYLOAD, headers=auth_headers(editor_token))
    assert r.status_code == 409


async def test_invalid_id_pattern_rejected(client: AsyncClient, editor_token, auth_headers) -> None:
    bad = {**VALID_PAYLOAD, "id": "Bad-ID"}  # not snake_case
    r = await client.post("/instances", json=bad, headers=auth_headers(editor_token))
    assert r.status_code == 422


async def test_invalid_type_pattern_rejected(
    client: AsyncClient, editor_token, auth_headers
) -> None:
    bad = {**VALID_PAYLOAD, "type": "lowercase_type"}
    r = await client.post("/instances", json=bad, headers=auth_headers(editor_token))
    assert r.status_code == 422


async def test_patch_updates_fields(client: AsyncClient, editor_token, auth_headers) -> None:
    await client.post("/instances", json=VALID_PAYLOAD, headers=auth_headers(editor_token))
    r = await client.patch(
        "/instances/org_acme",
        json={"label_en": "Acme Corporation (renamed)"},
        headers=auth_headers(editor_token),
    )
    assert r.status_code == 200
    assert r.json()["label_en"] == "Acme Corporation (renamed)"


async def test_filter_by_type_and_layer(client: AsyncClient, editor_token, auth_headers) -> None:
    p1 = {**VALID_PAYLOAD, "id": "org_a", "type": "Organization"}
    p2 = {**VALID_PAYLOAD, "id": "per_b", "type": "Person"}
    await client.post("/instances", json=p1, headers=auth_headers(editor_token))
    await client.post("/instances", json=p2, headers=auth_headers(editor_token))

    r = await client.get("/instances?type=Person", headers=auth_headers(editor_token))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == "per_b"


async def test_text_search(client: AsyncClient, editor_token, auth_headers) -> None:
    await client.post(
        "/instances",
        json={**VALID_PAYLOAD, "id": "needle_one", "label_en": "Findable Inc"},
        headers=auth_headers(editor_token),
    )
    await client.post(
        "/instances",
        json={**VALID_PAYLOAD, "id": "needle_two", "label_en": "Other Corp"},
        headers=auth_headers(editor_token),
    )
    r = await client.get("/instances?q=findable", headers=auth_headers(editor_token))
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == "needle_one"


async def test_verify_flow(client: AsyncClient, editor_token, admin_token, auth_headers) -> None:
    candidate = {**VALID_PAYLOAD, "id": "candidate_one", "status": "candidate"}
    r = await client.post("/instances", json=candidate, headers=auth_headers(editor_token))
    assert r.json()["status"] == "candidate"

    r = await client.post(
        "/instances/candidate_one/verify",
        json={"note": "Looks good"},
        headers=auth_headers(admin_token),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"
    assert r.json()["verified_by"] == "root-admin"


async def test_reject_flow(client: AsyncClient, editor_token, admin_token, auth_headers) -> None:
    candidate = {**VALID_PAYLOAD, "id": "candidate_two", "status": "candidate"}
    await client.post("/instances", json=candidate, headers=auth_headers(editor_token))

    r = await client.post(
        "/instances/candidate_two/reject",
        json={"reason": "Duplicate of org_acme"},
        headers=auth_headers(admin_token),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


async def test_get_unknown_is_404(client: AsyncClient, viewer_token, auth_headers) -> None:
    r = await client.get("/instances/does_not_exist", headers=auth_headers(viewer_token))
    assert r.status_code == 404
