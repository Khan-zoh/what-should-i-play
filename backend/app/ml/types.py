"""Plain dataclasses exchanged across the ml/ boundary. No I/O, no ORM."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GameFeatures:
    game_id: int
    slug: str
    name: str
    genres: frozenset[str] = frozenset()
    themes: frozenset[str] = frozenset()
    critic_score: float | None = None
    hours_played: float = 0.0
    status: str | None = None
    user_enjoyment: int | None = None
    release_year: int | None = None


@dataclass(frozen=True)
class UserProfile:
    liked_genres: frozenset[str] = frozenset()
    disliked_genres: frozenset[str] = frozenset()
    liked_types: frozenset[str] = frozenset()
    high_rated_genres: frozenset[str] = frozenset()
    session_length_pref: str = "any"
    difficulty_pref: str = "any"


@dataclass(frozen=True)
class ScoredCandidate:
    game_id: int
    score: float
    reason_codes: list[str] = field(default_factory=list)
    contributions: dict[str, float] = field(default_factory=dict)
