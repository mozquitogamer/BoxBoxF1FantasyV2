# ============================================================================
# F1 TRACK CLASSIFICATIONS (2020-2025)
# ============================================================================
# Manual expert classification of all F1 circuits
# Scale: 1-10 where applicable, or 0/1 for binary features
# Uses exact circuit_id names from your data

TRACK_DATABASE = {
    # === STREET CIRCUITS ===
    'monaco': {
        'is_street': 1,
        'overtaking_difficulty': 10,  # Nearly impossible
        'avg_corner_speed': 2,        # Very slow
        'straight_line_importance': 1,
        'downforce_level': 9,
        'turn1_incident_risk': 8,
        'safety_car_probability': 8,
        'track_evolution': 9,
        'grip_level': 7,
    },

    'marina_bay': {  # Singapore
        'is_street': 1,
        'overtaking_difficulty': 8,
        'avg_corner_speed': 3,
        'straight_line_importance': 2,
        'downforce_level': 9,
        'turn1_incident_risk': 7,
        'safety_car_probability': 7,
        'track_evolution': 8,
        'grip_level': 6,
    },

    'baku': {
        'is_street': 1,
        'overtaking_difficulty': 4,
        'avg_corner_speed': 4,
        'straight_line_importance': 8,
        'downforce_level': 6,
        'turn1_incident_risk': 9,
        'safety_car_probability': 9,
        'track_evolution': 8,
        'grip_level': 5,
    },

    'jeddah': {
        'is_street': 1,
        'overtaking_difficulty': 5,
        'avg_corner_speed': 7,
        'straight_line_importance': 6,
        'downforce_level': 7,
        'turn1_incident_risk': 8,
        'safety_car_probability': 7,
        'track_evolution': 7,
        'grip_level': 6,
    },

    'miami': {
        'is_street': 1,
        'overtaking_difficulty': 6,
        'avg_corner_speed': 5,
        'straight_line_importance': 5,
        'downforce_level': 6,
        'turn1_incident_risk': 7,
        'safety_car_probability': 6,
        'track_evolution': 7,
        'grip_level': 6,
    },

    'vegas': {  # Las Vegas
        'is_street': 1,
        'overtaking_difficulty': 4,
        'avg_corner_speed': 6,
        'straight_line_importance': 8,
        'downforce_level': 4,
        'turn1_incident_risk': 6,
        'safety_car_probability': 6,
        'track_evolution': 7,
        'grip_level': 5,
    },

    # === HIGH-SPEED CIRCUITS ===
    'monza': {
        'is_street': 0,
        'overtaking_difficulty': 3,
        'avg_corner_speed': 8,
        'straight_line_importance': 10,
        'downforce_level': 2,
        'turn1_incident_risk': 9,
        'safety_car_probability': 5,
        'track_evolution': 4,
        'grip_level': 8,
    },

    'spa': {
        'is_street': 0,
        'overtaking_difficulty': 4,
        'avg_corner_speed': 8,
        'straight_line_importance': 8,
        'downforce_level': 5,
        'turn1_incident_risk': 7,
        'safety_car_probability': 6,
        'track_evolution': 5,
        'grip_level': 7,
    },

    'silverstone': {
        'is_street': 0,
        'overtaking_difficulty': 5,
        'avg_corner_speed': 8,
        'straight_line_importance': 6,
        'downforce_level': 7,
        'turn1_incident_risk': 8,
        'safety_car_probability': 5,
        'track_evolution': 5,
        'grip_level': 8,
    },

    'suzuka': {
        'is_street': 0,
        'overtaking_difficulty': 6,
        'avg_corner_speed': 8,
        'straight_line_importance': 5,
        'downforce_level': 8,
        'turn1_incident_risk': 7,
        'safety_car_probability': 5,
        'track_evolution': 5,
        'grip_level': 8,
    },

    'red_bull_ring': {
        'is_street': 0,
        'overtaking_difficulty': 4,
        'avg_corner_speed': 7,
        'straight_line_importance': 7,
        'downforce_level': 6,
        'turn1_incident_risk': 8,
        'safety_car_probability': 5,
        'track_evolution': 4,
        'grip_level': 7,
    },

    # === TECHNICAL/BALANCED CIRCUITS ===
    'catalunya': {  # Barcelona
        'is_street': 0,
        'overtaking_difficulty': 7,
        'avg_corner_speed': 6,
        'straight_line_importance': 4,
        'downforce_level': 7,
        'turn1_incident_risk': 6,
        'safety_car_probability': 4,
        'track_evolution': 5,
        'grip_level': 8,
    },

    'hungaroring': {
        'is_street': 0,
        'overtaking_difficulty': 9,
        'avg_corner_speed': 4,
        'straight_line_importance': 2,
        'downforce_level': 9,
        'turn1_incident_risk': 8,
        'safety_car_probability': 5,
        'track_evolution': 6,
        'grip_level': 6,
    },

    'imola': {
        'is_street': 0,
        'overtaking_difficulty': 7,
        'avg_corner_speed': 6,
        'straight_line_importance': 4,
        'downforce_level': 7,
        'turn1_incident_risk': 7,
        'safety_car_probability': 6,
        'track_evolution': 5,
        'grip_level': 7,
    },

    'zandvoort': {
        'is_street': 0,
        'overtaking_difficulty': 8,
        'avg_corner_speed': 5,
        'straight_line_importance': 3,
        'downforce_level': 8,
        'turn1_incident_risk': 7,
        'safety_car_probability': 5,
        'track_evolution': 6,
        'grip_level': 7,
    },

    # === MEDIUM-SPEED CIRCUITS ===
    'bahrain': {
        'is_street': 0,
        'overtaking_difficulty': 4,
        'avg_corner_speed': 6,
        'straight_line_importance': 6,
        'downforce_level': 6,
        'turn1_incident_risk': 7,
        'safety_car_probability': 5,
        'track_evolution': 5,
        'grip_level': 6,
    },

    'albert_park': {  # Australia/Melbourne
        'is_street': 0,
        'overtaking_difficulty': 5,
        'avg_corner_speed': 6,
        'straight_line_importance': 5,
        'downforce_level': 6,
        'turn1_incident_risk': 7,
        'safety_car_probability': 6,
        'track_evolution': 6,
        'grip_level': 7,
    },

    'villeneuve': {  # Canada/Montreal
        'is_street': 0,
        'overtaking_difficulty': 4,
        'avg_corner_speed': 6,
        'straight_line_importance': 7,
        'downforce_level': 5,
        'turn1_incident_risk': 6,
        'safety_car_probability': 7,
        'track_evolution': 6,
        'grip_level': 6,
    },

    'americas': {  # COTA/Austin
        'is_street': 0,
        'overtaking_difficulty': 5,
        'avg_corner_speed': 7,
        'straight_line_importance': 6,
        'downforce_level': 7,
        'turn1_incident_risk': 7,
        'safety_car_probability': 5,
        'track_evolution': 5,
        'grip_level': 7,
    },

    'rodriguez': {  # Mexico City
        'is_street': 0,
        'overtaking_difficulty': 4,
        'avg_corner_speed': 5,
        'straight_line_importance': 7,
        'downforce_level': 8,
        'turn1_incident_risk': 8,
        'safety_car_probability': 5,
        'track_evolution': 5,
        'grip_level': 5,
    },

    'interlagos': {  # Brazil/Sao Paulo
        'is_street': 0,
        'overtaking_difficulty': 5,
        'avg_corner_speed': 6,
        'straight_line_importance': 5,
        'downforce_level': 6,
        'turn1_incident_risk': 7,
        'safety_car_probability': 6,
        'track_evolution': 5,
        'grip_level': 6,
    },

    'losail': {  # Qatar
        'is_street': 0,
        'overtaking_difficulty': 5,
        'avg_corner_speed': 7,
        'straight_line_importance': 5,
        'downforce_level': 7,
        'turn1_incident_risk': 6,
        'safety_car_probability': 4,
        'track_evolution': 4,
        'grip_level': 7,
    },

    'shanghai': {  # China
        'is_street': 0,
        'overtaking_difficulty': 5,
        'avg_corner_speed': 6,
        'straight_line_importance': 7,
        'downforce_level': 6,
        'turn1_incident_risk': 7,
        'safety_car_probability': 5,
        'track_evolution': 5,
        'grip_level': 6,
    },

    'yas_marina': {  # Abu Dhabi
        'is_street': 0,
        'overtaking_difficulty': 6,
        'avg_corner_speed': 5,
        'straight_line_importance': 6,
        'downforce_level': 6,
        'turn1_incident_risk': 6,
        'safety_car_probability': 5,
        'track_evolution': 5,
        'grip_level': 7,
    },

    # === NEW FOR 2026 ===
    'madrid': {  # Madrid GP (new for 2026)
        'is_street': 0,
        'overtaking_difficulty': 5,
        'avg_corner_speed': 6,
        'straight_line_importance': 6,
        'downforce_level': 6,
        'turn1_incident_risk': 7,
        'safety_car_probability': 5,
        'track_evolution': 5,
        'grip_level': 7,
    },

    # === HISTORIC/ONE-OFF CIRCUITS (2020-2021) ===
    'mugello': {  # Tuscany 2020
        'is_street': 0,
        'overtaking_difficulty': 6,
        'avg_corner_speed': 7,
        'straight_line_importance': 6,
        'downforce_level': 7,
        'turn1_incident_risk': 8,
        'safety_car_probability': 6,
        'track_evolution': 5,
        'grip_level': 7,
    },

    'sochi': {  # Russia (until 2021)
        'is_street': 1,
        'overtaking_difficulty': 6,
        'avg_corner_speed': 5,
        'straight_line_importance': 7,
        'downforce_level': 6,
        'turn1_incident_risk': 6,
        'safety_car_probability': 6,
        'track_evolution': 6,
        'grip_level': 6,
    },

    'nurburgring': {  # Eifel 2020
        'is_street': 0,
        'overtaking_difficulty': 5,
        'avg_corner_speed': 6,
        'straight_line_importance': 6,
        'downforce_level': 6,
        'turn1_incident_risk': 7,
        'safety_car_probability': 5,
        'track_evolution': 5,
        'grip_level': 7,
    },

    'portimao': {  # Portugal/Algarve
        'is_street': 0,
        'overtaking_difficulty': 5,
        'avg_corner_speed': 6,
        'straight_line_importance': 6,
        'downforce_level': 6,
        'turn1_incident_risk': 7,
        'safety_car_probability': 5,
        'track_evolution': 6,
        'grip_level': 6,
    },

    'istanbul': {  # Turkey
        'is_street': 0,
        'overtaking_difficulty': 5,
        'avg_corner_speed': 7,
        'straight_line_importance': 5,
        'downforce_level': 7,
        'turn1_incident_risk': 7,
        'safety_car_probability': 5,
        'track_evolution': 6,
        'grip_level': 6,
    },

    'ricard': {  # Paul Ricard/France (until 2022)
        'is_street': 0,
        'overtaking_difficulty': 4,
        'avg_corner_speed': 7,
        'straight_line_importance': 7,
        'downforce_level': 6,
        'turn1_incident_risk': 6,
        'safety_car_probability': 4,
        'track_evolution': 4,
        'grip_level': 8,
    },
}

def get_track_features(circuit_id):
    """
    Get track characteristics for a given circuit_id
    Returns dict of features, or default values if circuit not found
    """
    # Normalize circuit_id
    circuit_id = circuit_id.lower().replace(' ', '_')

    if circuit_id in TRACK_DATABASE:
        return TRACK_DATABASE[circuit_id]
    else:
        # Default/average values for unknown circuits
        print(f"Warning: Unknown circuit '{circuit_id}', using default values")
        return {
            'is_street': 0,
            'overtaking_difficulty': 5,
            'avg_corner_speed': 5,
            'straight_line_importance': 5,
            'downforce_level': 6,
            'turn1_incident_risk': 6,
            'safety_car_probability': 5,
            'track_evolution': 5,
            'grip_level': 6,
        }

# Export feature names for easy integration
TRACK_FEATURE_NAMES = list(next(iter(TRACK_DATABASE.values())).keys())


# ============================================================================
# Race name → circuit_id mapping (for 2026 season prediction pipeline)
# ============================================================================
RACE_NAME_TO_CIRCUIT = {
    'australian grand prix': 'albert_park',
    'chinese grand prix': 'shanghai',
    'japanese grand prix': 'suzuka',
    'bahrain grand prix': 'bahrain',
    'saudi arabian grand prix': 'jeddah',
    'miami grand prix': 'miami',
    'canadian grand prix': 'villeneuve',
    'monaco grand prix': 'monaco',
    'spanish grand prix': 'catalunya',
    'austrian grand prix': 'red_bull_ring',
    'british grand prix': 'silverstone',
    'belgian grand prix': 'spa',
    'hungarian grand prix': 'hungaroring',
    'dutch grand prix': 'zandvoort',
    'italian grand prix': 'monza',
    'spanish grand prix (madrid)': 'madrid',
    'azerbaijan grand prix': 'baku',
    'singapore grand prix': 'marina_bay',
    'united states grand prix': 'americas',
    'mexican grand prix': 'rodriguez',
    'brazilian grand prix': 'interlagos',
    'las vegas grand prix': 'vegas',
    'qatar grand prix': 'losail',
    'abu dhabi grand prix': 'yas_marina',
    # Additional aliases
    'emilia romagna grand prix': 'imola',
    'portuguese grand prix': 'portimao',
    'turkish grand prix': 'istanbul',
    'french grand prix': 'ricard',
    'tuscan grand prix': 'mugello',
    'eifel grand prix': 'nurburgring',
    'russian grand prix': 'sochi',
}


def get_circuit_id_from_race_name(race_name: str) -> str:
    """Map a GP name (e.g. 'Australian Grand Prix') to a circuit_id."""
    return RACE_NAME_TO_CIRCUIT.get(race_name.lower().strip(), 'unknown')


# ============================================================================
# Track-difficulty modifiers — overtakes & MC position-noise damping
# ============================================================================
# Hard-to-overtake circuits (Monaco, Singapore) produce far fewer overtakes and
# far less position shuffling than the track-agnostic heuristics assume. Both
# multipliers are derived from each track's `overtaking_difficulty` (1-10):
#   * tracks at/below the PIVOT are unaffected (multiplier 1.0)
#   * harder tracks ramp linearly down to the FLOOR at difficulty 10
# Monaco (difficulty 10) lands exactly on the floor. Lower a floor to make the
# effect stronger, raise it to soften. (estimate_overtakes itself is due a
# data-driven retune later; this damping sits on top of it.)
OVERTAKE_DAMP_PIVOT: int = 6        # difficulty at/below which overtakes are unchanged
OVERTAKE_DAMP_FLOOR: float = 0.13   # overtake multiplier at difficulty 10 -> Monaco ~15-20 field total
POS_NOISE_DAMP_PIVOT: int = 6       # difficulty at/below which MC position noise is unchanged
POS_NOISE_DAMP_FLOOR: float = 0.70  # MC position-noise multiplier at difficulty 10 (Monaco)

# Grid-anchoring: on hard-to-overtake circuits the race result tracks the
# starting grid far more than pure race-pace ranking implies. This blends the
# race model's predicted finish toward the qualifying grid, scaled by
# `overtaking_difficulty`. Unlike the damping multipliers above this ramps UP
# with difficulty: 0 at/below the pivot (normal tracks untouched) -> CEIL at
# difficulty 10 (Monaco ~grid-locked). Raise the ceiling to freeze the grid
# harder, lower it to let race pace re-order more.
GRID_ANCHOR_PIVOT: int = 6          # difficulty at/below which finish is NOT anchored to grid
GRID_ANCHOR_CEIL: float = 0.85      # grid-anchor weight at difficulty 10 (Monaco)


def _difficulty_for(circuit_id: str) -> int:
    """overtaking_difficulty (1-10) for a circuit_id; 5 (neutral) if unknown."""
    cid = (circuit_id or "").lower().replace(" ", "_")
    feats = TRACK_DATABASE.get(cid)
    return int(feats.get("overtaking_difficulty", 5)) if feats else 5


def _difficulty_damp(circuit_id: str, pivot: int, floor: float) -> float:
    """Linear ramp: 1.0 at/below `pivot`, down to `floor` at difficulty 10."""
    diff = _difficulty_for(circuit_id)
    if diff <= pivot:
        return 1.0
    if diff >= 10:
        return floor
    return 1.0 - (1.0 - floor) * (diff - pivot) / (10 - pivot)


def overtake_multiplier(circuit_id: str) -> float:
    """Multiplier (<=1.0) applied to estimated overtakes on hard-to-pass tracks."""
    return _difficulty_damp(circuit_id, OVERTAKE_DAMP_PIVOT, OVERTAKE_DAMP_FLOOR)


def position_noise_multiplier(circuit_id: str) -> float:
    """Multiplier (<=1.0) applied to Monte-Carlo position noise on sticky-grid tracks."""
    return _difficulty_damp(circuit_id, POS_NOISE_DAMP_PIVOT, POS_NOISE_DAMP_FLOOR)


def _difficulty_ramp_up(circuit_id: str, pivot: int, ceil: float) -> float:
    """Linear ramp UP: 0.0 at/below `pivot`, up to `ceil` at difficulty 10."""
    diff = _difficulty_for(circuit_id)
    if diff <= pivot:
        return 0.0
    if diff >= 10:
        return ceil
    return ceil * (diff - pivot) / (10 - pivot)


def grid_anchor_weight(circuit_id: str) -> float:
    """Weight (0..CEIL) for blending the predicted race finish toward the grid.

    On hard-to-overtake circuits the race result tracks the starting grid far
    more than pure race-pace ranking implies. 0 at/below the pivot (normal
    tracks unchanged) ramping to GRID_ANCHOR_CEIL at difficulty 10 (Monaco).
    """
    return _difficulty_ramp_up(circuit_id, GRID_ANCHOR_PIVOT, GRID_ANCHOR_CEIL)


def fp_quali_blend_weight(circuit_id: str, base: float, hard: float, pivot: int = 6) -> float:
    """FP-pace qualifying blend weight, scaled UP on quali-dominant circuits.

    On hard-to-overtake tracks (Monaco, Singapore, Hungary) one-lap pace decides
    the weekend far more than season-long race form, so we lean the quali
    prediction harder on this weekend's FP single-lap pace. Returns `base` at/below
    `pivot` (normal tracks keep the backtested weight) ramping linearly to `hard`
    at difficulty 10. Keyed off the same `overtaking_difficulty` as grid-anchoring.
    """
    diff = _difficulty_for(circuit_id)
    if diff <= pivot:
        return base
    if diff >= 10:
        return hard
    return base + (hard - base) * (diff - pivot) / (10 - pivot)
