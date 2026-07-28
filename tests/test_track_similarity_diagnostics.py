"""Track transforms expose saturation and anchoring has an evidence gate."""

from config import track_classifications as tracks
from config.track_similarity import similarity_diagnostics


def test_current_track_similarity_saturation_is_reported() -> None:
    result = similarity_diagnostics()

    assert result["circuits"] > 20
    assert result["pairs"] > 200
    assert result["median"] > 0.95
    assert result["share_at_or_above_threshold"] > 0.50
    assert result["is_saturated"] is True


def test_grid_anchor_cannot_reactivate_before_minimum_evidence() -> None:
    assert (
        tracks.GRID_ANCHOR_VALIDATED_EVENTS
        < tracks.GRID_ANCHOR_MIN_VALIDATED_EVENTS
    )
    assert tracks.GRID_ANCHOR_CANDIDATE_CEIL == 0.85
    assert tracks.GRID_ANCHOR_CEIL == 0.0
    assert tracks.grid_anchor_weight("monaco") == 0.0
