import numpy as np

from app.ml.vectors import centroid, cosine


def test_cosine_identical_unit_vectors_is_one() -> None:
    v = np.array([0.6, 0.8], dtype=np.float32)
    assert abs(cosine(v, v) - 1.0) < 1e-6


def test_cosine_orthogonal_is_zero() -> None:
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0], dtype=np.float32)
    assert abs(cosine(a, b)) < 1e-6


def test_cosine_opposite_is_minus_one() -> None:
    a = np.array([1.0, 0.0], dtype=np.float32)
    assert abs(cosine(a, -a) + 1.0) < 1e-6


def test_cosine_zero_vector_is_zero_not_nan() -> None:
    a = np.zeros(3, dtype=np.float32)
    b = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    assert cosine(a, b) == 0.0
    assert cosine(a, a) == 0.0


def test_centroid_mean_of_vectors() -> None:
    vs = [
        np.array([1.0, 0.0], dtype=np.float32),
        np.array([0.0, 1.0], dtype=np.float32),
    ]
    c = centroid(vs)
    assert np.allclose(c, [0.5, 0.5])


def test_centroid_empty_returns_none() -> None:
    assert centroid([]) is None
