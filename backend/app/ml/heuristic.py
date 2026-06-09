"""Deterministic heuristic ranker. Pure: same inputs -> same outputs, no I/O."""
from __future__ import annotations

import math

from app.ml.types import GameFeatures, ScoredCandidate, UserProfile
from app.ml.weights import HeuristicWeights

EXCLUDED_STATUSES = frozenset({"hidden", "abandoned", "not_interested"})
_BACKLOG_STATUSES = frozenset({"backlog", "installed"})
_HIGH_CRITIC = 80.0
_UNPLAYED_HOURS = 1.0
_MAX_GENRE_CODES = 3


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _score_one(
    profile: UserProfile, g: GameFeatures, w: HeuristicWeights
) -> ScoredCandidate:
    liked_present = g.genres & profile.liked_genres
    disliked_present = g.genres & profile.disliked_genres
    shared_high = g.genres & profile.high_rated_genres

    personal = len(liked_present) - len(disliked_present)
    content = _jaccard(g.genres, profile.high_rated_genres)
    # Guard against NaN/inf from external (IGDB) data: a NaN score would make
    # the final sort non-total and the ranking input-order-dependent.
    quality = (
        g.critic_score / 100.0
        if g.critic_score is not None and math.isfinite(g.critic_score)
        else 0.0
    )
    backlog = (1.0 if g.hours_played < _UNPLAYED_HOURS else 0.0) + (
        0.5 if g.status in _BACKLOG_STATUSES else 0.0
    )
    penalties = (1.0 if g.status == "completed" else 0.0) + (
        1.0 if g.user_enjoyment is not None and g.user_enjoyment <= 2 else 0.0
    )

    contributions = {
        "personal_match": w.personal_match * personal,
        "content_similarity": w.content_similarity * content,
        "quality": w.quality * quality,
        "backlog_boost": w.backlog_boost * backlog,
        "penalties": -penalties,
    }
    score = sum(contributions.values())

    codes: list[str] = []
    for genre in sorted(liked_present)[:_MAX_GENRE_CODES]:
        codes.append(f"MATCHES_LIKED_GENRE:{genre}")
    if shared_high:
        codes.append(f"SIMILAR_TO_HIGH_RATED:{sorted(shared_high)[0]}")
    if g.critic_score is not None and g.critic_score >= _HIGH_CRITIC:
        codes.append("HIGH_CRITIC_SCORE")
    if g.hours_played < _UNPLAYED_HOURS:
        codes.append("OWNED_AND_UNPLAYED")
    if g.status in _BACKLOG_STATUSES:
        codes.append("BACKLOG_PRIORITY")
    if not codes:
        codes.append("IN_YOUR_LIBRARY")

    return ScoredCandidate(
        game_id=g.game_id, score=score, reason_codes=codes, contributions=contributions
    )


def score_candidates(
    profile: UserProfile,
    candidates: list[GameFeatures],
    weights: HeuristicWeights,
) -> list[ScoredCandidate]:
    scored = [
        _score_one(profile, g, weights)
        for g in candidates
        if g.status not in EXCLUDED_STATUSES
    ]
    scored.sort(key=lambda c: (-c.score, c.game_id))
    return scored
