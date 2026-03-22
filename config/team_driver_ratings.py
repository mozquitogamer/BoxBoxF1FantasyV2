# ============================================================================
# TEAM STRATEGY & DRIVER SKILL RATINGS
# ============================================================================
# Manual expert ratings for team strategy and driver-specific skills
# Scale: 1-10 (higher = better)

# ============================================================================
# TEAM STRATEGY RATINGS (2026 — updated post China GP Round 2 race results)
# ============================================================================
# Based on 2026 performance + 2025 track record. Constructor order: Mercedes >
# Ferrari > McLaren ≈ Red Bull > Haas/VCARB > Alpine/Audi > rest
# R2 race: Antonelli P1, Russell P2, Hamilton P3, Leclerc P4, Bearman P5, Lawson P7
# R2 DNFs: Norris, Verstappen, Piastri, Albon, Alonso, Stroll, Bortoleto

TEAM_STRATEGY_RATINGS = {
    # 2026 season ratings — updated to reflect current constructor order
    'mercedes': {
        'strategy_rating': 9,    # Dominant car, Hamilton + Russell precision strategy
        'pit_stop_speed': 9,
        'adaptability': 9,
    },
    'ferrari': {
        'strategy_rating': 7,    # Hamilton upgrade — experience clearly elevating strategy
        'pit_stop_speed': 8,
        'adaptability': 7,
    },
    'red_bull': {
        'strategy_rating': 7,    # Excellent infrastructure but car clearly off-pace in 2026; DNF China
        'pit_stop_speed': 9,     # Consistently sub-2.5s stops
        'adaptability': 7,       # Car not adapting well to new 2026 regs
    },
    'mclaren': {
        'strategy_rating': 8,    # Very strong in 2024/2025, continues in 2026
        'pit_stop_speed': 9,     # World record stop holders
        'adaptability': 8,
    },
    'haas': {
        'strategy_rating': 7,    # Bearman + Ocon strong pairing — P9/P12 in China SQ
        'pit_stop_speed': 7,
        'adaptability': 7,
    },
    'rb': {                      # VCARB / Racing Bulls
        'strategy_rating': 7,    # Lawson P7 race R2, punching above weight
        'pit_stop_speed': 7,
        'adaptability': 7,       # Lawson adapting well to new regs
    },
    'racing_bulls': {            # Alias for 'rb' — used in V2 pipeline
        'strategy_rating': 7,
        'pit_stop_speed': 7,
        'adaptability': 7,
    },
    'alpine': {
        'strategy_rating': 5,
        'pit_stop_speed': 6,
        'adaptability': 5,
    },
    'williams': {
        'strategy_rating': 6,    # Improving, Sainz brings experience
        'pit_stop_speed': 7,
        'adaptability': 6,
    },
    'aston_martin': {
        'strategy_rating': 5,    # Struggling in 2026
        'pit_stop_speed': 6,
        'adaptability': 5,
    },
    'audi': {                    # Formerly Kick Sauber / Sauber
        'strategy_rating': 5,
        'pit_stop_speed': 6,
        'adaptability': 5,
    },
    'cadillac': {                # New 2026 entry
        'strategy_rating': 4,    # Brand new team, still learning
        'pit_stop_speed': 5,
        'adaptability': 4,
    },
    # Legacy constructor IDs kept for 2020-2025 training data compatibility
    'kick_sauber': {
        'strategy_rating': 5,
        'pit_stop_speed': 6,
        'adaptability': 5,
    },
    'alfa': {
        'strategy_rating': 5,
        'pit_stop_speed': 6,
        'adaptability': 5,
    },
    'alphatauri': {
        'strategy_rating': 6,
        'pit_stop_speed': 7,
        'adaptability': 6,
    },
}

# ============================================================================
# DRIVER SKILL RATINGS
# ============================================================================

DRIVER_TIRE_MANAGEMENT = {
    # 2026 grid — updated post Round 1 Australia + China SQ
    # Legendary tire managers
    'fernando_alonso': 10,
    'lewis_hamilton': 9,

    # Very good
    'max_verstappen': 9,
    'george_russell': 8,
    'carlos_sainz': 8,
    'oscar_piastri': 8,
    'lando_norris': 8,
    'nico_hulkenberg': 8,

    # Good
    'valtteri_bottas': 7,
    'sergio_perez': 7,
    'esteban_ocon': 7,
    'pierre_gasly': 7,
    'alexander_albon': 7,
    'lance_stroll': 7,
    'charles_leclerc': 8,     # Consistently strong race pace — P4 race R2, P2 sprint
    'kimi_antonelli': 8,      # R2 race winner — controlled, composed tire management

    # Average-Good
    'oliver_bearman': 7,      # P5 R2 race — strong tire management for a young driver
    'liam_lawson': 7,         # P7 R2 race — overperforming vs car expectations
    'isack_hadjar': 6,
    'gabriel_bortoleto': 6,
    'franco_colapinto': 6,

    # Rookie / limited F1 data
    'arvid_lindblad': 5,

    # Legacy drivers (2020-2025 training data compatibility)
    'daniel_ricciardo': 7,
    'kevin_magnussen': 7,
    'yuki_tsunoda': 6,
    'zhou_guanyu': 6,
    'mick_schumacher': 6,
    'nicholas_latifi': 6,
    'nikita_mazepin': 5,
    'logan_sargeant': 6,
    'jack_doohan': 6,
    'ollie_bearman': 6,
}

DRIVER_WET_WEATHER_SKILL = {
    # 2026 grid — updated ratings
    # Elite in the wet
    'max_verstappen': 10,
    'lewis_hamilton': 10,

    # Excellent
    'fernando_alonso': 9,
    'charles_leclerc': 8,
    'george_russell': 8,
    'lando_norris': 8,

    # Good
    'kimi_antonelli': 8,      # Exceptional wet form in junior categories; R2 race winner composure
    'carlos_sainz': 7,
    'sergio_perez': 7,
    'oscar_piastri': 7,
    'pierre_gasly': 7,
    'esteban_ocon': 7,
    'alexander_albon': 7,
    'isack_hadjar': 7,
    'franco_colapinto': 7,

    # Average
    'valtteri_bottas': 6,
    'nico_hulkenberg': 6,
    'lance_stroll': 6,
    'oliver_bearman': 6,
    'liam_lawson': 6,
    'gabriel_bortoleto': 6,

    # Rookie / limited data
    'arvid_lindblad': 5,

    # Legacy drivers (2020-2025 training data compatibility)
    'daniel_ricciardo': 7,
    'yuki_tsunoda': 6,
    'kevin_magnussen': 6,
    'zhou_guanyu': 6,
    'mick_schumacher': 6,
    'nicholas_latifi': 5,
    'nikita_mazepin': 4,
    'logan_sargeant': 5,
    'jack_doohan': 6,
    'ollie_bearman': 6,
}

DRIVER_OVERTAKING_SKILL = {
    # 2026 grid — updated ratings
    # Elite overtakers
    'max_verstappen': 10,
    'fernando_alonso': 10,
    'lewis_hamilton': 9,

    # Very good
    'charles_leclerc': 9,
    'carlos_sainz': 8,
    'lando_norris': 8,
    'george_russell': 8,

    # Good
    'kimi_antonelli': 8,      # R2 race winner — controlled passes, excellent race craft
    'gabriel_bortoleto': 7,   # F2 champion, excellent racecraft
    'franco_colapinto': 7,
    'oscar_piastri': 7,
    'pierre_gasly': 7,
    'esteban_ocon': 7,
    'alexander_albon': 7,
    'isack_hadjar': 7,
    'liam_lawson': 7,
    'oliver_bearman': 7,
    'sergio_perez': 7,
    'nico_hulkenberg': 7,

    # Average
    'valtteri_bottas': 6,
    'lance_stroll': 6,
    'arvid_lindblad': 6,

    # Legacy drivers (2020-2025 training data compatibility)
    'daniel_ricciardo': 9,
    'yuki_tsunoda': 7,
    'kevin_magnussen': 8,
    'zhou_guanyu': 6,
    'mick_schumacher': 6,
    'nicholas_latifi': 5,
    'logan_sargeant': 5,
    'jack_doohan': 6,
    'ollie_bearman': 7,
}

DRIVER_QUALIFYING_SPECIALIST = {
    # 2026 grid — updated post China GP R2 (SQ + race results)
    # One-lap pace kings
    'george_russell': 10,     # P1 China SQ, consistently best qualifier in 2026
    'charles_leclerc': 9,     # Elite one-lap pace; P6 SQ but P4 race shows consistency
    'max_verstappen': 9,      # P8 China SQ — exceptional driver, car not at 2023/24 level
    'lewis_hamilton': 9,      # P4 China SQ — still elite over one lap
    'lando_norris': 9,        # P3 China SQ — one-lap pace unaffected by reliability

    # Very good
    'kimi_antonelli': 9,      # P2 China SQ — exceptional one-lap pace from day 1
    'oscar_piastri': 8,       # P5 China SQ
    'isack_hadjar': 8,        # Strong quali record from junior series, P10 SQ
    'carlos_sainz': 8,
    'fernando_alonso': 8,

    # Good
    'pierre_gasly': 7,        # P7 China SQ — impressive for Alpine
    'oliver_bearman': 7,      # P9 China SQ — punching above car weight
    'esteban_ocon': 7,
    'alexander_albon': 7,
    'nico_hulkenberg': 7,
    'liam_lawson': 7,
    'gabriel_bortoleto': 7,   # F2 champion
    'franco_colapinto': 7,

    # Average
    'sergio_perez': 6,        # DNS China SQ (mechanical), historically struggles vs teammate
    'valtteri_bottas': 6,
    'lance_stroll': 6,
    'arvid_lindblad': 6,

    # Legacy drivers (2020-2025 training data compatibility)
    'daniel_ricciardo': 7,
    'yuki_tsunoda': 7,
    'kevin_magnussen': 6,
    'zhou_guanyu': 6,
    'mick_schumacher': 6,
    'nicholas_latifi': 5,
    'logan_sargeant': 5,
    'jack_doohan': 6,
    'ollie_bearman': 7,
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_team_strategy_rating(constructor_id):
    """Get strategy rating for a constructor"""
    if constructor_id in TEAM_STRATEGY_RATINGS:
        return TEAM_STRATEGY_RATINGS[constructor_id]['strategy_rating']
    return 5  # Default average

def get_team_adaptability(constructor_id):
    """Get adaptability rating (important for SC/rain)"""
    if constructor_id in TEAM_STRATEGY_RATINGS:
        return TEAM_STRATEGY_RATINGS[constructor_id]['adaptability']
    return 5

def get_driver_tire_mgmt(driver_id):
    """Get driver tire management skill"""
    return DRIVER_TIRE_MANAGEMENT.get(driver_id, 6)  # Default average

def get_driver_wet_skill(driver_id):
    """Get driver wet weather skill"""
    return DRIVER_WET_WEATHER_SKILL.get(driver_id, 6)

def get_driver_overtaking(driver_id):
    """Get driver overtaking ability"""
    return DRIVER_OVERTAKING_SKILL.get(driver_id, 6)

def get_driver_quali_skill(driver_id):
    """Get driver qualifying specialist rating"""
    return DRIVER_QUALIFYING_SPECIALIST.get(driver_id, 6)
