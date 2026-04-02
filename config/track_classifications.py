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
