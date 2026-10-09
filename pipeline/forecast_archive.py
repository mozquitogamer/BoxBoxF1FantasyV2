"""Select forecasts whose generation and export both preceded Fantasy lock.

Some phase archives were backfilled after the race. Their phase label alone
does not establish that a forecast was available when a team could use it.
"""

from __future__ import annotations

import json
import hashlib
import math
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_SOURCE = ROOT / "web" / "public" / "app.js"
_DEADLINE_RE = re.compile(r"\{\s*round:\s*(\d+),\s*race:\s*'[^']+',\s*lock:\s*'([^']+)'", re.S)


def fantasy_lock_utc(round_num: int, source: Path = LOCK_SOURCE) -> datetime | None:
    """Read the UTC lock already displayed on the website; fail closed if absent."""
    try:
        content = source.read_text(encoding="utf-8")
    except OSError:
        return None
    for number, iso in _DEADLINE_RE.findall(content):
        if int(number) == round_num:
            return _parse_utc(iso)
    return None


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if result.tzinfo is None:
        return None
    return result.astimezone(timezone.utc)


def load_lock_forecast(
    round_num: int,
    data_dir: Path,
    *,
    lock_source: Path = LOCK_SOURCE,
    audit_dir: Path | None = None,
) -> tuple[dict, Path] | None:
    """Return the latest provable pre-lock ``post_fp`` archive, if any."""
    return load_prelock_forecast(round_num, data_dir, phase="post_fp", lock_source=lock_source, audit_dir=audit_dir)


def load_prelock_forecast(
    round_num: int,
    data_dir: Path,
    *,
    phase: str,
    lock_source: Path = LOCK_SOURCE,
    audit_dir: Path | None = None,
) -> tuple[dict, Path] | None:
    """Consider named, session and immutable audit archives; accept only pre-lock.

    A retrospective phase archive may be *newer* than a legitimate canonical
    forecast. Timestamp each independently and choose the latest eligible one.
    """
    if phase not in {"pre_fp", "post_fp"}:
        raise ValueError(f"Pre-lock evaluation cannot use phase {phase!r}")
    deadline = fantasy_lock_utc(round_num, lock_source)
    if deadline is None:
        return None
    paths = [data_dir / f"predictions_round{round_num}_{phase}.json",
             data_dir / f"predictions_round{round_num}.json"]
    paths.extend(sorted(data_dir.glob(f"predictions_round{round_num}_{phase}_*.json")))
    if audit_dir is None and data_dir.resolve() == (ROOT / 'web/public/data').resolve():
        audit_dir = ROOT / 'data/audit/snapshots'
    if audit_dir is not None:
        paths.extend(sorted((audit_dir / f'round{round_num}').glob('*.json')))
    actual_path = data_dir / f'actual_round{round_num}.json'
    actual = json.loads(actual_path.read_text(encoding='utf-8')) if actual_path.exists() else None
    eligible = []
    for path in paths:
        payload = _load(path, round_num)
        if not payload or payload.get('phase') != phase:
            continue
        generated = _parse_utc(payload.get('generated_at'))
        exported = _parse_utc(payload.get('exported_at'))
        if generated and exported and generated <= exported <= deadline and matching_roster(payload, actual):
            eligible.append((exported, payload, path))
    if not eligible:
        return None
    _, payload, path = max(eligible, key=lambda candidate: candidate[0])
    return payload, path


def _load(path: Path, round_num: int) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and isinstance(data.get('predictions'), dict):
        wrapper = data
        data = dict(wrapper['predictions'])
        data.setdefault('phase', wrapper.get('phase'))
        data.setdefault('fp_sessions_included', (wrapper.get('prediction_metadata') or {}).get('fp_sessions_included', []))
        data.setdefault('exported_at', wrapper.get('audit_timestamp'))
        inferred = _parse_utc((wrapper.get('prediction_metadata') or {}).get('generated_at'))
        exported = _parse_utc(data.get('exported_at'))
        if inferred and (not exported or inferred > exported):
            return None
    if not isinstance(data, dict) or data.get("round") != round_num or data.get("reconstructed", False):
        return None
    return data


def matching_roster(forecast: dict, actual: dict | None) -> bool:
    """Require one-to-one asset coverage, with explicit seat-safe legacy IDs."""
    if actual is None:
        return True
    for group, key in [('drivers', 'driver_id'), ('constructors', 'constructor_id')]:
        observed = {row[key]: row for row in actual.get(group, [])}
        rows = forecast.get(group, [])
        if len(rows) != len(observed) or not rows:
            return False
        seen = set()
        for row in rows:
            ids = [row.get(key)] + (row.get('asset_legacy_ids', []) if group == 'drivers' else [])
            matches = [asset for asset in ids if asset in observed and
                       (group != 'drivers' or observed[asset].get('constructor') == row.get('constructor'))]
            if not matches or matches[0] in seen:
                return False
            points = row.get('expected_points')
            if not isinstance(points, (int, float)) or not math.isfinite(points):
                return False
            seen.add(matches[0])
        if seen != set(observed):
            return False
    return True


def build_accuracy_prelock_index(data_dir: Path, *, audit_dir: Path | None = None,
                                 lock_source: Path = LOCK_SOURCE) -> dict:
    """Public evidence for the last complete actionable forecast of each race."""
    records, excluded = [], []
    numbers = sorted(int(path.stem.removeprefix('actual_round'))
                     for path in data_dir.glob('actual_round*.json')
                     if path.stem.removeprefix('actual_round').isdigit())
    for round_num in numbers:
        selected = load_prelock_forecast(round_num, data_dir, phase='post_fp',
                                        audit_dir=audit_dir, lock_source=lock_source)
        if selected is None:
            selected = load_prelock_forecast(round_num, data_dir, phase='pre_fp',
                                            audit_dir=audit_dir, lock_source=lock_source)
        if selected is None:
            excluded.append(round_num)
            continue
        payload, path = selected
        try:
            source = path.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            source = path.name
        keep = ['round', 'race', 'season', 'phase', 'generated_at', 'exported_at',
                'simulation_generated_at', 'fp_sessions_included', 'drivers', 'constructors']
        records.append({'round': round_num, 'lock_utc': fantasy_lock_utc(round_num, lock_source).isoformat(),
                        'source': source, 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'forecast': {key: payload[key] for key in keep if key in payload}})
    return {'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
            'selection': 'last_complete_forecast_before_fantasy_lock',
            'rounds': records, 'excluded_rounds': excluded}
