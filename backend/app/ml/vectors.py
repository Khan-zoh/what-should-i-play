"""Pure vector math over numpy arrays. No I/O, no ORM, no model loading."""
from __future__ import annotations

import numpy as np


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity; returns 0.0 (not NaN) when either vector is zero."""
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def centroid(vectors: list[np.ndarray]) -> np.ndarray | None:
    """Mean vector, or None for an empty list."""
    if not vectors:
        return None
    return np.mean(np.stack(vectors), axis=0)
