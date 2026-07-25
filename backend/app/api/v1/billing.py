"""Thin HTTP endpoint for the caller's credit balance."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.auth import AuthPrincipal, get_current_principal
from ...core.db import get_db
from ...schemas.billing import BillingUsageOut
from ...services import billing_service

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/usage", response_model=BillingUsageOut)
def get_usage(
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(get_current_principal),
):
    return billing_service.usage_out(db, principal.user_id, principal.plan_slug)
