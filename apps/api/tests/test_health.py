from httpx import ASGITransport, AsyncClient

from character_vein_api.main import app


async def test_health_endpoint() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "字脉 API",
        "version": "0.1.0",
        "environment": "development",
    }


async def test_glyph_catalog_endpoints() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        all_response = await client.get("/api/v1/glyphs")
        complete_response = await client.get("/api/v1/glyphs", params={"all_scripts": True})
        cloud_response = await client.get("/api/v1/glyphs/云")
        removed_response = await client.get("/api/v1/glyphs/风")

    assert all_response.status_code == 200
    assert len(all_response.json()) == 4
    assert complete_response.status_code == 200
    assert len(complete_response.json()) == 4
    assert cloud_response.status_code == 200
    assert cloud_response.json()["available_script_count"] == 7
    assert removed_response.status_code == 404
