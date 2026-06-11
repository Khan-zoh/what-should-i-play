"""Orchestrates heuristic recommendations: loads candidates from repositories,
hands plain dataclasses to ml/, writes impression telemetry, returns DTOs.

The ml/ package does the scoring; this layer owns all persistence and I/O.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from app.db.repositories import (
    GameTagRepository,
    LibraryEntryRepository,
    PreferencesRepository,
    RecommendationEventRepository,
)
from app.ml.explanations import explain
from app.ml.heuristic import score_candidates
from app.ml.types import GameFeatures, UserProfile
from app.ml.weights import DEFAULT_WEIGHTS

MODEL_VERSION = "heuristic-v0"
SURFACE = "for_you"
ABSTENTION_PATH = "heuristic"
EXPLANATION_VARIANT = "templated"
_HIGH_RATED_THRESHOLD = 4


@dataclass(frozen=True)
class Recommendation:
    event_id: int
    game_id: int
    name: str
    slug: str
    cover_url: str | None
    genres: list[str]
    critic_score: float | None
    hours_played: float
    status: str | None
    reason_codes: list[str]
    explanation: str
    score: float
    model_version: str


class CandidateSource(Protocol):
    def candidates(self) -> list[GameFeatures]:
        ...


class OwnedLibraryCandidateSource:
    """v0 source: the user's owned library. A buyable source can implement the
    same `candidates()` shape later without changing the service or scorer."""

    def __init__(
        self, *, library: LibraryEntryRepository, tags: GameTagRepository
    ) -> None:
        self._library = library
        self._tags = tags

    def candidates(self) -> list[GameFeatures]:
        rows = self._library.list_with_user_data()
        game_ids = [g.id for _entry, g, _r, _s in rows]
        tag_map = self._tags.tags_by_game(game_ids)
        features: list[GameFeatures] = []
        for entry, g, rating, state in rows:
            kinds = tag_map.get(g.id, {})
            features.append(
                GameFeatures(
                    game_id=g.id,
                    slug=g.slug,
                    name=g.name,
                    cover_url=g.cover_url,
                    genres=frozenset(kinds.get("genre", set())),
                    themes=frozenset(kinds.get("theme", set())),
                    critic_score=g.critic_score,
                    hours_played=entry.hours_played,
                    status=state.status if state else None,
                    user_enjoyment=rating.enjoyment if rating else None,
                    release_year=g.release_year,
                )
            )
        return features


def _feature_hash(profile: UserProfile, candidates: list[GameFeatures]) -> str:
    payload = {
        "liked": sorted(profile.liked_genres),
        "disliked": sorted(profile.disliked_genres),
        "high_rated": sorted(profile.high_rated_genres),
        "games": [
            {
                "id": c.game_id,
                "genres": sorted(c.genres),
                "critic": c.critic_score,
                "hours": c.hours_played,
                "status": c.status,
                "enjoyment": c.user_enjoyment,
            }
            for c in sorted(candidates, key=lambda c: c.game_id)
        ],
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


class RecommenderService:
    def __init__(
        self,
        *,
        candidate_source: CandidateSource,
        preferences: PreferencesRepository,
        events: RecommendationEventRepository,
    ) -> None:
        self._source = candidate_source
        self._prefs = preferences
        self._events = events

    def _build_profile(
        self, candidates: list[GameFeatures]
    ) -> UserProfile:
        prefs = self._prefs.get_or_create()
        high_rated: set[str] = set()
        for c in candidates:
            if c.user_enjoyment is not None and c.user_enjoyment >= _HIGH_RATED_THRESHOLD:
                high_rated |= c.genres
        return UserProfile(
            liked_genres=frozenset(prefs.liked_genres),
            disliked_genres=frozenset(prefs.disliked_genres),
            liked_types=frozenset(prefs.liked_types),
            high_rated_genres=frozenset(high_rated),
            session_length_pref=prefs.session_length_pref,
            difficulty_pref=prefs.difficulty_pref,
        )

    def recommend(self, limit: int) -> list[Recommendation]:
        candidates = self._source.candidates()
        if not candidates:
            return []
        profile = self._build_profile(candidates)
        feature_hash = _feature_hash(profile, candidates)
        scored = score_candidates(profile, candidates, DEFAULT_WEIGHTS)[:limit]

        by_id = {c.game_id: c for c in candidates}
        recs: list[Recommendation] = []
        for rank, sc in enumerate(scored):
            feat = by_id[sc.game_id]
            ev = self._events.create_impression(
                game_id=sc.game_id,
                surface=SURFACE,
                rank=rank,
                score=sc.score,
                reason_codes=sc.reason_codes,
                model_version=MODEL_VERSION,
                feature_hash=feature_hash,
                filters_applied={},
                abstention_path=ABSTENTION_PATH,
                explanation_variant=EXPLANATION_VARIANT,
            )
            recs.append(
                Recommendation(
                    event_id=ev.id,
                    game_id=feat.game_id,
                    name=feat.name,
                    slug=feat.slug,
                    cover_url=feat.cover_url,
                    genres=sorted(feat.genres),
                    critic_score=feat.critic_score,
                    hours_played=feat.hours_played,
                    status=feat.status,
                    reason_codes=sc.reason_codes,
                    explanation=explain(sc.reason_codes),
                    score=sc.score,
                    model_version=MODEL_VERSION,
                )
            )
        return recs
