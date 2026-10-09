"""The qualifying transform shared by live forecasts and chronological experiments."""
from __future__ import annotations
import numpy as np
import pandas as pd
from config.track_classifications import fp_quali_blend_weight

FP_QUALI_BLEND_TUNABLES = {
    "weight": 0.6,                 # base (normal tracks): 0 = pure model, 1 = pure FP pace
    "weight_hard_track": 0.80,     # FP weight at overtaking_difficulty 10 (Monaco)
    "weight_sprint": 0.15,         # SPRINT weekends: only FP1 (short, quali-sim heavy) AND
                                   # the actual Sprint-Qualifying grid is now a strong
                                   # in-model quali signal -> lean FAR less on FP pace.
                                   # Sweep on 23 sprint folds: min at 0.10, 0.15 robust;
                                   # 0.15 vs 0.60 = -0.34 quali MAE (95% CI excludes 0).
    "hard_track_pivot": 6,         # at/below this difficulty, use base weight
    "min_drivers_with_pace": 10,   # need at least this many FP times to blend
    "pace_cols": ["best_lap_time", "best_3_lap_avg", "best_5_lap_avg"],  # composite; lower = faster
    "min_laps_for_composite": 5,
    "max_best5_gap_seconds": 5.0,  # reject FP samples padded by traffic/slow laps
}


def representative_fp_pace_mask(features: pd.DataFrame) -> pd.Series:
    """Exclude sparse FP samples whose best-five average includes slow laps."""
    required = {"total_laps", "best_lap_time", "best_5_lap_avg"}
    if not required.issubset(features.columns):
        return pd.Series(True, index=features.index)
    lap_count = pd.to_numeric(features["total_laps"], errors="coerce")
    best = pd.to_numeric(features["best_lap_time"], errors="coerce")
    best_five = pd.to_numeric(features["best_5_lap_avg"], errors="coerce")
    return (
        lap_count.ge(FP_QUALI_BLEND_TUNABLES["min_laps_for_composite"])
        & best_five.sub(best).between(
            0, FP_QUALI_BLEND_TUNABLES["max_best5_gap_seconds"]
        )
    )



def _zscore(values):
    values = np.asarray(values, dtype=float)
    sd = values.std()
    return (values - values.mean()) / sd if sd > 1e-9 else values - values.mean()


def blend_qualifying_scores(features, scores, circuit_id, is_sprint=False):
    """Return live-equivalent scores and evidence without mutating the inputs."""
    settings = FP_QUALI_BLEND_TUNABLES
    cols = [col for col in settings['pace_cols'] if col in features.columns]
    weight = settings['weight_sprint'] if is_sprint else fp_quali_blend_weight(
        circuit_id, settings['weight'], settings['weight_hard_track'], settings['hard_track_pivot'])
    evidence = {'applied': False, 'driver_count': 0, 'weight': float(weight), 'pace_cols': cols}
    scores = np.asarray(scores, dtype=float).copy()
    if weight <= 0 or not cols:
        return scores, evidence
    representative = representative_fp_pace_mask(features)
    zmat = []
    for col_name in cols:
        col = pd.to_numeric(features[col_name], errors='coerce').where(representative)
        sd = col.std()
        zmat.append(-(col - col.mean()) / sd if sd and sd > 1e-9 else col * 0.0)
    pace = pd.concat(zmat, axis=1).mean(axis=1, skipna=True)
    has_pace = pace.notna().to_numpy()
    evidence['driver_count'] = int(has_pace.sum())
    if evidence['driver_count'] < settings['min_drivers_with_pace']:
        return scores, evidence
    blended = _zscore(scores)
    comp = _zscore(pace.to_numpy()[has_pace])
    blended[has_pace] = (1.0 - weight) * blended[has_pace] + weight * comp
    evidence['applied'] = True
    return blended, evidence


def blend_event_scores(frame, scores):
    """Blend independently within each historical event, preserving row order."""
    result = np.asarray(scores, dtype=float).copy()
    for indices in frame.groupby(['season', 'round'], sort=False).indices.values():
        event = frame.iloc[indices]
        circuit = str(event['circuit_id'].iloc[0]) if 'circuit_id' in event else 'unknown'
        circuit = {'madring': 'madrid'}.get(circuit, circuit)
        sprint = 'sprint_grid' in event and bool(event['sprint_grid'].notna().any())
        result[indices], _ = blend_qualifying_scores(event, result[indices], circuit, sprint)
    return result
