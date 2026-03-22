"""
Circuit GPS coordinates for weather forecasting.

Maps circuit names (as used in races.json) to latitude/longitude
for the Open-Meteo weather API.
"""

CIRCUIT_COORDINATES = {
    # Circuit name from races.json → (latitude, longitude, timezone)
    "Melbourne":          (-37.8497, 144.9680, "Australia/Melbourne"),
    "Shanghai":           (31.3389, 121.2197, "Asia/Shanghai"),
    "Suzuka":             (34.8431, 136.5407, "Asia/Tokyo"),
    "Sakhir":             (26.0325, 50.5106, "Asia/Bahrain"),
    "Jeddah":             (21.6319, 39.1044, "Asia/Riyadh"),
    "Miami":              (25.9581, -80.2389, "America/New_York"),
    "Montreal":           (45.5000, -73.5228, "America/Toronto"),
    "Monaco":             (43.7347, 7.4206,  "Europe/Monaco"),
    "Barcelona":          (41.5700, 2.2611,  "Europe/Madrid"),
    "Spielberg":          (47.2197, 14.7647, "Europe/Vienna"),
    "Silverstone":        (52.0786, -1.0169, "Europe/London"),
    "Spa-Francorchamps":  (50.4372, 5.9714,  "Europe/Brussels"),
    "Budapest":           (47.5789, 19.2486, "Europe/Budapest"),
    "Zandvoort":          (52.3888, 4.5409,  "Europe/Amsterdam"),
    "Monza":              (45.6156, 9.2811,  "Europe/Rome"),
    "Madrid":             (40.4614, -3.5892, "Europe/Madrid"),
    "Baku":               (40.3725, 49.8533, "Asia/Baku"),
    "Singapore":          (1.2914,  103.8640, "Asia/Singapore"),
    "Austin":             (30.1328, -97.6411, "America/Chicago"),
    "Mexico City":        (19.4042, -99.0907, "America/Mexico_City"),
    "São Paulo":          (-23.7014, -46.6969, "America/Sao_Paulo"),
    "Las Vegas":          (36.1162, -115.1745, "America/Los_Angeles"),
    "Lusail":             (25.4900, 51.4542, "Asia/Qatar"),
    "Yas Marina":         (24.4672, 54.6031, "Asia/Dubai"),
}


def get_circuit_location(circuit_name: str) -> tuple[float, float, str] | None:
    """Return (lat, lon, timezone) for a circuit, or None if not found."""
    return CIRCUIT_COORDINATES.get(circuit_name)
