"""
FORESIGHT — /rules router

CRUD endpoints for tenant-scoped alert rules.
Alert rules define thresholds and conditions that trigger real-time alerts
in the Spark Structured Streaming pipeline.

Endpoints
---------
GET  /rules/{tenant_id}           — list all rules for tenant
GET  /rules/{tenant_id}/{rule_id} — get a single rule
POST /rules/{tenant_id}           — create a new rule
PUT  /rules/{tenant_id}/{rule_id} — update an existing rule
DELETE /rules/{tenant_id}/{rule_id} — soft-delete a rule
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.models.schemas import AlertRuleCreate, AlertRuleResponse, AlertRuleUpdate

log = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/{tenant_id}",
    response_model=List[AlertRuleResponse],
    summary="List alert rules for a tenant",
    description=(
        "Returns all active alert rules for the specified tenant. "
        "Rules define thresholds (e.g. vibration > 8 m/s²) that trigger alerts "
        "in the Spark streaming pipeline."
    ),
)
async def list_rules(
    tenant_id: str,
    asset_type: Optional[str] = None,
    is_active: Optional[bool] = True,
    db: AsyncSession = Depends(get_db),
) -> List[AlertRuleResponse]:
    from infrastructure.db.base import AlertRule

    stmt = select(AlertRule).where(AlertRule.tenant_id == tenant_id)
    if is_active is not None:
        stmt = stmt.where(AlertRule.is_active == is_active)
    if asset_type:
        stmt = stmt.where(AlertRule.asset_type == asset_type)
    stmt = stmt.order_by(AlertRule.created_at.desc())

    result = await db.execute(stmt)
    rules = result.scalars().all()

    return [
        AlertRuleResponse(
            id=str(r.id),
            tenant_id=str(r.tenant_id),
            name=r.name,
            description=r.description,
            asset_type=r.asset_type,
            metric=r.metric,
            operator=r.operator,
            threshold=r.threshold,
            severity=r.severity,
            is_active=r.is_active,
            created_at=r.created_at,
        )
        for r in rules
    ]


@router.get(
    "/{tenant_id}/{rule_id}",
    response_model=AlertRuleResponse,
    summary="Get a single alert rule",
)
async def get_rule(
    tenant_id: str,
    rule_id: str,
    db: AsyncSession = Depends(get_db),
) -> AlertRuleResponse:
    from infrastructure.db.base import AlertRule

    stmt = (
        select(AlertRule).where(AlertRule.tenant_id == tenant_id).where(AlertRule.id == rule_id)
    )
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found.")

    return AlertRuleResponse(
        id=str(rule.id),
        tenant_id=str(rule.tenant_id),
        name=rule.name,
        description=rule.description,
        asset_type=rule.asset_type,
        metric=rule.metric,
        operator=rule.operator,
        threshold=rule.threshold,
        severity=rule.severity,
        is_active=rule.is_active,
        created_at=rule.created_at,
    )


@router.post(
    "/{tenant_id}",
    response_model=AlertRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an alert rule",
    description=(
        "Creates a new threshold-based alert rule for the tenant. "
        "The Spark streaming pipeline picks up new rules within ~60 seconds."
    ),
)
async def create_rule(
    tenant_id: str,
    payload: AlertRuleCreate,
    db: AsyncSession = Depends(get_db),
) -> AlertRuleResponse:
    from infrastructure.db.base import AlertRule

    rule = AlertRule(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=payload.name,
        description=payload.description,
        asset_type=payload.asset_type,
        metric=payload.metric,
        operator=payload.operator,
        threshold=payload.threshold,
        severity=payload.severity,
        is_active=True,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    log.info("Created alert rule id=%s tenant=%s", rule.id, tenant_id)

    return AlertRuleResponse(
        id=str(rule.id),
        tenant_id=str(rule.tenant_id),
        name=rule.name,
        description=rule.description,
        asset_type=rule.asset_type,
        metric=rule.metric,
        operator=rule.operator,
        threshold=rule.threshold,
        severity=rule.severity,
        is_active=rule.is_active,
        created_at=rule.created_at,
    )


@router.put(
    "/{tenant_id}/{rule_id}",
    response_model=AlertRuleResponse,
    summary="Update an alert rule",
)
async def update_rule(
    tenant_id: str,
    rule_id: str,
    payload: AlertRuleUpdate,
    db: AsyncSession = Depends(get_db),
) -> AlertRuleResponse:
    from infrastructure.db.base import AlertRule

    stmt = (
        select(AlertRule).where(AlertRule.tenant_id == tenant_id).where(AlertRule.id == rule_id)
    )
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found.")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value)

    await db.commit()
    await db.refresh(rule)
    log.info(
        "Updated alert rule id=%s tenant=%s fields=%s", rule_id, tenant_id, list(update_data)
    )

    return AlertRuleResponse(
        id=str(rule.id),
        tenant_id=str(rule.tenant_id),
        name=rule.name,
        description=rule.description,
        asset_type=rule.asset_type,
        metric=rule.metric,
        operator=rule.operator,
        threshold=rule.threshold,
        severity=rule.severity,
        is_active=rule.is_active,
        created_at=rule.created_at,
    )


@router.delete(
    "/{tenant_id}/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate (soft-delete) an alert rule",
    description=(
        "Sets is_active=False on the rule. "
        "The Spark pipeline will stop evaluating it within ~60 seconds. "
        "Hard deletion is not permitted to preserve audit history."
    ),
)
async def delete_rule(
    tenant_id: str,
    rule_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    from infrastructure.db.base import AlertRule

    stmt = (
        select(AlertRule).where(AlertRule.tenant_id == tenant_id).where(AlertRule.id == rule_id)
    )
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found.")

    rule.is_active = False
    await db.commit()
    log.info("Soft-deleted alert rule id=%s tenant=%s", rule_id, tenant_id)
