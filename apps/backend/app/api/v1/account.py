from fastapi import APIRouter

router = APIRouter(tags=["account"])


@router.get("/account")
async def get_account() -> dict[str, object]:
    return {"id": 1, "mode": "paper", "status": "connected_stub"}
