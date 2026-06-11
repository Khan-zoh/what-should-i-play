"""Pure content-similarity pre-pass: candidate vectors vs the user's high-rated
games. Computes a leave-one-out centroid similarity plus the nearest high-rated
neighbor (for the grounded SIMILAR_TO_HIGH_RATED_GAME reason code).

Designed as the single typed channel into the heuristic scorer — the scorer never
sees raw vectors, only ContentScore values. No I/O, no ORM.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.ml.vectors import centroid, cosine


@dataclass(frozen=True)
class HighRatedItem:
    game_id: int
    slug: str
    name: str
    vector: np.ndarray


@dataclass(frozen=True)
class ContentScore:
    similarity: float  # max(0, cosine(candidate, leave-one-out centroid)), in [0,1]
    nearest_slug: str | None
    nearest_name: str | None


def content_scores(
    candidate_vecs: dict[int, np.ndarray],
    high_rated: list[HighRatedItem],
) -> dict[int, ContentScore]:
    if not high_rated:
        return {}

    scores: dict[int, ContentScore] = {}
    for game_id, vec in candidate_vecs.items():
        # Leave-one-out: a candidate that is itself high-rated must not be
        # compared against its own vector (self-similarity is degenerate).
        others = [h for h in high_rated if h.game_id != game_id]
        if not others:
            scores[game_id] = ContentScore(
                similarity=0.0, nearest_slug=None, nearest_name=None
            )
            continue

        center = centroid([h.vector for h in others])
        similarity = max(0.0, cosine(vec, center)) if center is not None else 0.0

        nearest = max(others, key=lambda h: (cosine(vec, h.vector), -h.game_id))
        scores[game_id] = ContentScore(
            similarity=similarity,
            nearest_slug=nearest.slug,
            nearest_name=nearest.name,
        )
    return scores
