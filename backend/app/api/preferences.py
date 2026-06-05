"""HTTP endpoints for the singleton user preferences row."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.db.repositories import PreferencesRepository

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


class PreferencesModel(BaseModel):
    liked_genres: list[str]
    disliked_genres: list[str]
    liked_types: list[str]
    session_length_pref: str
    difficulty_pref: str


@router.get("", response_model=PreferencesModel)
def get_preferences(session: Session = Depends(get_db_session)) -> PreferencesModel:
    prefs = PreferencesRepository(session).get_or_create()
    session.commit()
    return PreferencesModel(
        liked_genres=prefs.liked_genres,
        disliked_genres=prefs.disliked_genres,
        liked_types=prefs.liked_types,
        session_length_pref=prefs.session_length_pref,
        difficulty_pref=prefs.difficulty_pref,
    )


@router.put("", response_model=PreferencesModel)
def put_preferences(
    body: PreferencesModel, session: Session = Depends(get_db_session)
) -> PreferencesModel:
    prefs = PreferencesRepository(session).update(
        liked_genres=body.liked_genres,
        disliked_genres=body.disliked_genres,
        liked_types=body.liked_types,
        session_length_pref=body.session_length_pref,
        difficulty_pref=body.difficulty_pref,
    )
    session.commit()
    return PreferencesModel(
        liked_genres=prefs.liked_genres,
        disliked_genres=prefs.disliked_genres,
        liked_types=prefs.liked_types,
        session_length_pref=prefs.session_length_pref,
        difficulty_pref=prefs.difficulty_pref,
    )
