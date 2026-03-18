# ============================================================================
# TEAM STRATEGY & DRIVER SKILL RATINGS
# ============================================================================
# Manual expert ratings for team strategy and driver-specific skills
# Scale: 1-10 (higher = better)
# Keys use Jolpica-style driver IDs (e.g., "max_verstappen", "hamilton")

# ============================================================================
# TEAM STRATEGY RATINGS (2026 -- updated post China GP Round 2)
# ============================================================================

TEAM_STRATEGY_RATINGS = {
    # 2026 season ratings
    'mercedes': {'strategy_rating': 9, 'pit_stop_speed': 9, 'adaptability': 9},
    'ferrari': {'strategy_rating': 7, 'pit_stop_speed': 8, 'adaptability': 7},
    'red_bull': {'strategy_rating': 7, 'pit_stop_speed': 9, 'adaptability': 7},
    'mclaren': {'strategy_rating': 8, 'pit_stop_speed': 9, 'adaptability': 8},
    'haas': {'strategy_rating': 7, 'pit_stop_speed': 7, 'adaptability': 7},
    'rb': {'strategy_rating': 7, 'pit_stop_speed': 7, 'adaptability': 7},
    'alpine': {'strategy_rating': 5, 'pit_stop_speed': 6, 'adaptability': 5},
    'williams': {'strategy_rating': 6, 'pit_stop_speed': 7, 'adaptability': 6},
    'aston_martin': {'strategy_rating': 5, 'pit_stop_speed': 6, 'adaptability': 5},
    'audi': {'strategy_rating': 5, 'pit_stop_speed': 6, 'adaptability': 5},
    'cadillac': {'strategy_rating': 4, 'pit_stop_speed': 5, 'adaptability': 4},
    # Legacy constructor IDs (2020-2025 compatibility)
    'sauber': {'strategy_rating': 5, 'pit_stop_speed': 6, 'adaptability': 5},
    'kick_sauber': {'strategy_rating': 5, 'pit_stop_speed': 6, 'adaptability': 5},
    'alfa': {'strategy_rating': 5, 'pit_stop_speed': 6, 'adaptability': 5},
    'alphatauri': {'strategy_rating': 6, 'pit_stop_speed': 7, 'adaptability': 6},
    'racing_point': {'strategy_rating': 6, 'pit_stop_speed': 7, 'adaptability': 6},
    'renault': {'strategy_rating': 5, 'pit_stop_speed': 6, 'adaptability': 5},
}

# ============================================================================
# DRIVER SKILL RATINGS
# ============================================================================

DRIVER_TIRE_MANAGEMENT = {
    # 2026 grid
    'alonso': 10, 'hamilton': 9, 'max_verstappen': 9, 'russell': 8,
    'sainz': 8, 'piastri': 8, 'norris': 8, 'hulkenberg': 8,
    'leclerc': 8, 'antonelli': 8, 'bottas': 7, 'perez': 7,
    'ocon': 7, 'gasly': 7, 'albon': 7, 'stroll': 7,
    'bearman': 7, 'lawson': 7, 'hadjar': 6, 'bortoleto': 6,
    'colapinto': 6, 'lindblad': 5,
    # Legacy (2020-2025)
    'ricciardo': 7, 'kevin_magnussen': 7, 'tsunoda': 6, 'zhou': 6,
    'mick_schumacher': 6, 'latifi': 6, 'mazepin': 5, 'sargeant': 6,
    'doohan': 6, 'de_vries': 6, 'giovinazzi': 6, 'raikkonen': 7,
    'vettel': 8, 'kvyat': 6, 'grosjean': 6, 'nissany': 5,
}

DRIVER_WET_WEATHER_SKILL = {
    # 2026 grid
    'max_verstappen': 10, 'hamilton': 10, 'alonso': 9, 'leclerc': 8,
    'russell': 8, 'norris': 8, 'antonelli': 8, 'sainz': 7,
    'perez': 7, 'piastri': 7, 'gasly': 7, 'ocon': 7,
    'albon': 7, 'hadjar': 7, 'colapinto': 7, 'bottas': 6,
    'hulkenberg': 6, 'stroll': 6, 'bearman': 6, 'lawson': 6,
    'bortoleto': 6, 'lindblad': 5,
    # Legacy
    'ricciardo': 7, 'tsunoda': 6, 'kevin_magnussen': 6, 'zhou': 6,
    'mick_schumacher': 6, 'latifi': 5, 'mazepin': 4, 'sargeant': 5,
    'doohan': 6, 'de_vries': 6, 'giovinazzi': 5, 'raikkonen': 8,
    'vettel': 9, 'kvyat': 6, 'grosjean': 6,
}

DRIVER_OVERTAKING_SKILL = {
    # 2026 grid
    'max_verstappen': 10, 'alonso': 10, 'hamilton': 9, 'leclerc': 9,
    'sainz': 8, 'norris': 8, 'russell': 8, 'antonelli': 8,
    'bortoleto': 7, 'colapinto': 7, 'piastri': 7, 'gasly': 7,
    'ocon': 7, 'albon': 7, 'hadjar': 7, 'lawson': 7,
    'bearman': 7, 'perez': 7, 'hulkenberg': 7, 'bottas': 6,
    'stroll': 6, 'lindblad': 6,
    # Legacy
    'ricciardo': 9, 'tsunoda': 7, 'kevin_magnussen': 8, 'zhou': 6,
    'mick_schumacher': 6, 'latifi': 5, 'sargeant': 5, 'doohan': 6,
    'de_vries': 6, 'giovinazzi': 6, 'raikkonen': 7, 'vettel': 8,
    'kvyat': 7, 'grosjean': 6,
}

DRIVER_QUALIFYING_SPECIALIST = {
    # 2026 grid
    'russell': 10, 'leclerc': 9, 'max_verstappen': 9, 'hamilton': 9,
    'norris': 9, 'antonelli': 9, 'piastri': 8, 'hadjar': 8,
    'sainz': 8, 'alonso': 8, 'gasly': 7, 'bearman': 7,
    'ocon': 7, 'albon': 7, 'hulkenberg': 7, 'lawson': 7,
    'bortoleto': 7, 'colapinto': 7, 'perez': 6, 'bottas': 6,
    'stroll': 6, 'lindblad': 6,
    # Legacy
    'ricciardo': 7, 'tsunoda': 7, 'kevin_magnussen': 6, 'zhou': 6,
    'mick_schumacher': 6, 'latifi': 5, 'sargeant': 5, 'doohan': 6,
    'de_vries': 7, 'giovinazzi': 6, 'raikkonen': 7, 'vettel': 8,
    'kvyat': 6, 'grosjean': 6,
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_team_strategy_rating(constructor_id: str) -> int:
    """Get strategy rating for a constructor."""
    if constructor_id in TEAM_STRATEGY_RATINGS:
        return TEAM_STRATEGY_RATINGS[constructor_id]['strategy_rating']
    return 5

def get_team_adaptability(constructor_id: str) -> int:
    """Get adaptability rating (important for SC/rain)."""
    if constructor_id in TEAM_STRATEGY_RATINGS:
        return TEAM_STRATEGY_RATINGS[constructor_id]['adaptability']
    return 5

def get_driver_tire_mgmt(driver_id: str) -> int:
    """Get driver tire management skill."""
    return DRIVER_TIRE_MANAGEMENT.get(driver_id, 6)

def get_driver_wet_skill(driver_id: str) -> int:
    """Get driver wet weather skill."""
    return DRIVER_WET_WEATHER_SKILL.get(driver_id, 6)

def get_driver_overtaking(driver_id: str) -> int:
    """Get driver overtaking ability."""
    return DRIVER_OVERTAKING_SKILL.get(driver_id, 6)

def get_driver_quali_skill(driver_id: str) -> int:
    """Get driver qualifying specialist rating."""
    return DRIVER_QUALIFYING_SPECIALIST.get(driver_id, 6)
