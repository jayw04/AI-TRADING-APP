from datetime import datetime

from sqlalchemy import DDL, DateTime, ForeignKey, String, event, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.observability.audit_hash import compute_row_hash


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload_json: Mapped[str | None] = mapped_column(String, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # P5 §8.1 — hash chain. Self-hash over the canonical row content +
    # prev_hash; prev_hash links to the previous row in this user's chain.
    # Populated by the before_insert event below (the only write path).
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


# --- P5 §8.1: hash chain population ------------------------------------------
#
# Computed in a before_insert mapper event rather than in AuditLogger.write so
# the (async, ORM) write path stays a plain ``session.add(row)`` — zero call-site
# churn, and the hash is set BEFORE the INSERT so the no_update trigger (below)
# never fires. The async session runs flush in a greenlet, so the sync
# ``connection.execute`` here is valid.
#
# Chain ordering invariant: rows link in COMMIT order. ``prev_hash`` is read
# from the last committed row for the user. Every AuditLogger.write call site in
# the codebase writes exactly one row and lets the caller commit it (router
# ``_audit`` / ``_audit_live_submission``, the activation service, auth) — so the
# previous row is always already committed when the next one inserts. (Writing
# several audit rows for one user inside a *single* flush would leave them
# unchained, because the ORM batches those INSERTs and the SELECT below wouldn't
# see its siblings yet — the integrity verifier would then flag it. No code path
# does that; one-row-per-transaction is the documented contract.)


@event.listens_for(AuditLog, "before_insert")
def _audit_log_fill_hash_chain(_mapper, connection, target: "AuditLog") -> None:
    prev_hash: str | None = None
    if target.user_id is not None:
        prev_hash = connection.execute(
            text(
                "SELECT row_hash FROM audit_log "
                "WHERE user_id = :uid ORDER BY id DESC LIMIT 1"
            ),
            {"uid": target.user_id},
        ).scalar()
    target.prev_hash = prev_hash
    target.row_hash = compute_row_hash(
        user_id=target.user_id,
        actor_type=target.actor_type,
        actor_id=target.actor_id,
        action=target.action,
        target_type=target.target_type,
        target_id=target.target_id,
        payload_json=target.payload_json,
        ts=target.ts,
        prev_hash=prev_hash,
    )


# --- P5 §8.1: storage-layer immutability triggers ----------------------------
#
# Attached to the table's after_create so they exist wherever the table is
# created: Base.metadata.create_all (tests) AND the explicit op.execute in the
# migration (prod). audit_log is append-only — UPDATE and DELETE both abort.
# (The migration also creates them directly for the already-existing prod table;
# IF NOT EXISTS keeps the two paths from colliding.)
_NO_UPDATE_TRIGGER = (
    "CREATE TRIGGER IF NOT EXISTS audit_log_no_update "
    "BEFORE UPDATE ON audit_log "
    "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only; UPDATE forbidden'); END;"
)
_NO_DELETE_TRIGGER = (
    "CREATE TRIGGER IF NOT EXISTS audit_log_no_delete "
    "BEFORE DELETE ON audit_log "
    "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only; DELETE forbidden'); END;"
)

event.listen(AuditLog.__table__, "after_create", DDL(_NO_UPDATE_TRIGGER))
event.listen(AuditLog.__table__, "after_create", DDL(_NO_DELETE_TRIGGER))
