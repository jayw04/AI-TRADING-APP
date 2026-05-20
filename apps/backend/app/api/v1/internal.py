from fastapi import APIRouter, Depends

from app.auth.internal import require_workbench_auth

router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    dependencies=[Depends(require_workbench_auth)],
)


@router.get("/ping")
async def ping() -> dict[str, bool]:
    return {"pong": True}
