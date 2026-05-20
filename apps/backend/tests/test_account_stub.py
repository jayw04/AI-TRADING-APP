from httpx import AsyncClient


async def test_account_stub(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/account")
    assert resp.status_code == 200
    assert resp.json() == {"id": 1, "mode": "paper", "status": "connected_stub"}
