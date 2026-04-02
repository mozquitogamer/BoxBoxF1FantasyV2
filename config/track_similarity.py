# ============================================================================
# TRACK SIMILARITY — Cosine similarity between F1 circuits
# ============================================================================
# Uses the 9-dimensional feature vectors from track_classifications.py
# to compute pairwise similarity. Used by the feature pipeline to weight
# historical results from similar tracks more heavily.

from __future__ import annotations

import math
from functools import lru_cache

from config.track_classifications import TRACK_DATABASE, TRACK_FEATURE_NAMES, get_track_features


def _feature_vector(circuit_id: str) -> tuple[float, ...]:
    """Return the feature vector for a circuit as a tuple of floats."""
    features = get_track_features(circuit_id)
    return tuple(float(features[k]) for k in TRACK_FEATURE_NAMES)


@lru_cache(maxsize=1024)
def get_similarity(circuit_a: str, circuit_b: str) -> float:
    """
    Cosine similarity between two circuits (0.0 to 1.0).

    All feature dimensions are 1-10 scale (non-negative), so cosine
    similarity naturally falls in [0, 1]. A value of 1.0 means identical
    track profiles; ~0.85+ means very similar.
    """
    a = circuit_a.lower().replace(" ", "_")
    b = circuit_b.lower().replace(" ", "_")

    if a == b:
        return 1.0

    va = _feature_vector(a)
    vb = _feature_vector(b)

    dot = sum(x * y for x, y in zip(va, vb))
    mag_a = math.sqrt(sum(x * x for x in va))
    mag_b = math.sqrt(sum(x * x for x in vb))

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return dot / (mag_a * mag_b)


def get_similar_tracks(circuit_id: str, top_n: int = 5) -> list[tuple[str, float]]:
    """
    Return the top_n most similar tracks to the given circuit,
    sorted by descending similarity. Excludes the circuit itself.
    """
    cid = circuit_id.lower().replace(" ", "_")
    similarities = []
    for other_id in TRACK_DATABASE:
        if other_id == cid:
            continue
        sim = get_similarity(cid, other_id)
        similarities.append((other_id, sim))

    similarities.sort(key=lambda x: x[1], reverse=True)
    return similarities[:top_n]


def build_similarity_matrix() -> dict[str, dict[str, float]]:
    """Build full pairwise similarity matrix (for inspection/debugging)."""
    circuits = sorted(TRACK_DATABASE.keys())
    matrix = {}
    for a in circuits:
        matrix[a] = {}
        for b in circuits:
            matrix[a][b] = get_similarity(a, b)
    return matrix
