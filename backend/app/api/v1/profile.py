"""Thin HTTP endpoints for the user-owned learner profile."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.auth import get_current_user_id
from ...core.db import get_db
from ...schemas.profile import ProfileOut, ProfilePut
from ...services import profile_service

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
def get_profile(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return profile_service.profile_out(profile_service.get_or_create(db, user_id))


@router.put("", response_model=ProfileOut)
def put_profile(
    body: ProfilePut,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return profile_service.update(db, user_id, body)
