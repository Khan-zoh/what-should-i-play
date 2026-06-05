"""HTTP endpoints for first-run onboarding state (stored on the Preferences row)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.db.repositories import PreferencesRepository

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class OnboardingStatus(BaseModel):
    completed: bool


@router.get("", response_model=OnboardingStatus)
def get_onboarding(session: Session = Depends(get_db_session)) -> OnboardingStatus:
    completed = PreferencesRepository(session).get_onboarding_completed()
    session.commit()
    return OnboardingStatus(completed=completed)


@router.put("", response_model=OnboardingStatus)
def put_onboarding(
    body: OnboardingStatus, session: Session = Depends(get_db_session)
) -> OnboardingStatus:
    PreferencesRepository(session).set_onboarding_completed(body.completed)
    session.commit()
    return OnboardingStatus(completed=body.completed)
