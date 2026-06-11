"""Hand-set heuristic weights. Tuning is deferred to the eval sub-plan; these are
normalized to the feature scales in heuristic.py and intentionally conservative."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HeuristicWeights:
    personal_match: float = 1.0
    content_similarity: float = 0.8
    quality: float = 0.5
    backlog_boost: float = 0.6


DEFAULT_WEIGHTS = HeuristicWeights()
