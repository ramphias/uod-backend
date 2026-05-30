"""CRUD endpoints for the instance store.

Authorisation model (matches the decisions in docs-site/architecture/data-architecture.md):
- GET endpoints require authentication (any role) — instances are private data.
- POST / PATCH / DELETE require editor or admin.
- Verify / reject (admin gate) require admin.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, require_principal, require_role
from app.db import get_session
from app.models import AuditLog, Instance
from app.schemas import (
    InstanceCreate,
    InstanceList,
    InstanceRead,
    InstanceUpdate,
    RejectRequest,
    VerifyRequest,
)

router = APIRouter(prefix="/instances", tags=["instances"])


# ── helpers ─────────────────────────────────────────────────────────────


async def _get_or_404(session: AsyncSession, instance_id: str) -> Instance:
    obj = await session.get(Instance, instance_id)
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance '{instance_id}' not found",
        )
    return obj


async def _log(
    session: AsyncSession,
    *,
    instance_id: str | None,
    action: str,
    actor: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            instance_id=instance_id,
            action=action,
            actor=actor,
            before=before,
            after=after,
        )
    )


def _serialize(inst: Instance) -> dict:
    """Snapshot for audit log — keeps it stable across schema additions."""
    return {
        "id": inst.id,
        "type": inst.type,
        "layer": inst.layer,
        "label_en": inst.label_en,
        "label_zh": inst.label_zh,
        "data": inst.data,
        "status": inst.status,
        "confidence": float(inst.confidence) if inst.confidence is not None else None,
    }


# ── reads ───────────────────────────────────────────────────────────────


@router.get("", response_model=InstanceList)
async def list_instances(
    _: Annotated[Principal, Depends(require_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
    type: str | None = Query(None, description="Filter by class id"),
    layer: str | None = Query(None, description="Filter by layer id"),
    status_: str | None = Query(None, alias="status"),
    q: str | None = Query(None, description="Free-text search across label_en / label_zh"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> InstanceList:
    stmt = select(Instance)
    count_stmt = select(func.count()).select_from(Instance)
    if type:
        stmt = stmt.where(Instance.type == type)
        count_stmt = count_stmt.where(Instance.type == type)
    if layer:
        stmt = stmt.where(Instance.layer == layer)
        count_stmt = count_stmt.where(Instance.layer == layer)
    if status_:
        stmt = stmt.where(Instance.status == status_)
        count_stmt = count_stmt.where(Instance.status == status_)
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Instance.label_en.ilike(like)) | (Instance.label_zh.ilike(like)))
        count_stmt = count_stmt.where(
            (Instance.label_en.ilike(like)) | (Instance.label_zh.ilike(like))
        )

    stmt = stmt.order_by(Instance.harvested_at.desc()).offset(offset).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()

    return InstanceList(
        items=[InstanceRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{instance_id}", response_model=InstanceRead)
async def get_instance(
    instance_id: str,
    _: Annotated[Principal, Depends(require_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InstanceRead:
    obj = await _get_or_404(session, instance_id)
    return InstanceRead.model_validate(obj)


# ── writes ──────────────────────────────────────────────────────────────


@router.post("", response_model=InstanceRead, status_code=status.HTTP_201_CREATED)
async def create_instance(
    payload: InstanceCreate,
    principal: Annotated[Principal, Depends(require_role("editor", "admin"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InstanceRead:
    existing = await session.get(Instance, payload.id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Instance '{payload.id}' already exists",
        )

    inst = Instance(**payload.model_dump())
    session.add(inst)
    await session.flush()
    await _log(
        session,
        instance_id=inst.id,
        action="create",
        actor=principal.login,
        after=_serialize(inst),
    )
    return InstanceRead.model_validate(inst)


@router.patch("/{instance_id}", response_model=InstanceRead)
async def update_instance(
    instance_id: str,
    payload: InstanceUpdate,
    principal: Annotated[Principal, Depends(require_role("editor", "admin"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InstanceRead:
    obj = await _get_or_404(session, instance_id)
    before = _serialize(obj)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    await session.flush()
    await _log(
        session,
        instance_id=obj.id,
        action="update",
        actor=principal.login,
        before=before,
        after=_serialize(obj),
    )
    return InstanceRead.model_validate(obj)


@router.delete("/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instance(
    instance_id: str,
    principal: Annotated[Principal, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    obj = await _get_or_404(session, instance_id)
    before = _serialize(obj)
    await session.delete(obj)
    await _log(
        session,
        instance_id=instance_id,
        action="delete",
        actor=principal.login,
        before=before,
    )


# ── admin: verify / reject ──────────────────────────────────────────────


@router.post("/{instance_id}/verify", response_model=InstanceRead)
async def verify_instance(
    instance_id: str,
    payload: VerifyRequest,
    principal: Annotated[Principal, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InstanceRead:
    obj = await _get_or_404(session, instance_id)
    before = _serialize(obj)
    obj.status = "accepted"
    obj.verified_by = principal.login
    obj.verified_at = datetime.now(UTC)
    await session.flush()
    await _log(
        session,
        instance_id=obj.id,
        action="verify",
        actor=principal.login,
        before=before,
        after=_serialize(obj) | {"note": payload.note},
    )
    return InstanceRead.model_validate(obj)


@router.post("/{instance_id}/reject", response_model=InstanceRead)
async def reject_instance(
    instance_id: str,
    payload: RejectRequest,
    principal: Annotated[Principal, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InstanceRead:
    obj = await _get_or_404(session, instance_id)
    before = _serialize(obj)
    obj.status = "rejected"
    obj.verified_by = principal.login
    obj.verified_at = datetime.now(UTC)
    await session.flush()
    await _log(
        session,
        instance_id=obj.id,
        action="reject",
        actor=principal.login,
        before=before,
        after=_serialize(obj) | {"reason": payload.reason},
    )
    return InstanceRead.model_validate(obj)
