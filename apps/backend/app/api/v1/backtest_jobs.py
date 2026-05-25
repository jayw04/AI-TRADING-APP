"""Per-job endpoints for backtest jobs (P4 §2).

``GET  /api/v1/backtest-jobs/{id}``          — current state
``POST /api/v1/backtest-jobs/{id}/cancel``   — request cancellation

The submit + list-for-strategy endpoints live on the strategies router
because they're inherently strategy-scoped; the per-job endpoints sit on
their own router so an UI cancelling by job_id doesn't need to know
which strategy owns the job.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.strategies import BacktestJobResponse
from app.auth.stub import CurrentUser, get_current_user
from app.db.models.backtest_job import BacktestJob
from app.db.session import get_session

router = APIRouter(prefix="/backtest-jobs", tags=["backtest-jobs"])


def _get_worker(request: Request):
    w = getattr(request.app.state, "backtest_worker", None)
    if w is None:
        raise HTTPException(
            status_code=503, detail="Backtest worker not initialized"
        )
    return w


@router.get("/{job_id}", response_model=BacktestJobResponse)
async def get_job(
    job_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BacktestJobResponse:
    row = await session.get(BacktestJob, job_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Backtest job not found")
    return BacktestJobResponse.model_validate(row, from_attributes=True)


@router.post("/{job_id}/cancel", response_model=BacktestJobResponse)
async def cancel_job(
    job_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BacktestJobResponse:
    row = await session.get(BacktestJob, job_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Backtest job not found")

    worker = _get_worker(request)
    accepted = await worker.request_cancel(job_id)
    if not accepted:
        # Already terminal (completed / failed / cancelled).
        raise HTTPException(
            status_code=409,
            detail=(
                f"Job is in status {row.status.value}; "
                "cancellation not applicable."
            ),
        )

    # For QUEUED jobs the worker updated the row inline; for RUNNING jobs
    # the worker just set the flag — the row will transition asynchronously
    # at the next bar boundary. Either way return the latest DB snapshot.
    await session.refresh(row)
    return BacktestJobResponse.model_validate(row, from_attributes=True)
