/* ============================================================
   BoxBoxF1Fantasy — User-Scenarios Overlay
   ============================================================
   Pure client-side overlay. Lets the visitor dial per-driver
   and per-team pace bumps (UI surface unit: "positions gained")
   and see how predicted points / positions shift on the cards.

   The base ML prediction in `data` is NEVER mutated. The overlay
   returns decorated copies of driver/constructor objects with
   `expected_points_adjusted`, `predicted_finish_adjusted`,
   `points_delta`, `pace_bump` etc. — the same fields the existing
   admin-side upgrade overlay emits, so the .upgrade-delta badge
   UI just works.

   Math mirrors pipeline/apply_upgrades.py — they should stay in
   sync. Approximations vs. the admin tool:
     * Quali tier bonus for constructors (both_q3 / one_q3 etc.)
       is NOT recomputed (rare flip, documented).
     * Overtake count is NOT adjusted (would need re-running the
       sim — the overlay is a position-points / positions-gained
       delta only).
   ============================================================ */

(function() {
    'use strict';

    const STORAGE_KEY = 'boxbox_scenario_v1';
    // Phase 3: saved named scenarios live in a separate key. Cap to MAX_SAVED
    // so a malicious site can't fill up LocalStorage. Per-round map keeps
    // saves scoped — a Canada scenario won't appear when planning Monaco.
    const SAVES_KEY = 'boxbox_scenario_saves_v1';
    const MAX_SAVED_PER_ROUND = 10;

    // Mirrors config/fantasy_scoring.py — keep in sync if scoring rules change.
    const QUALI_POS_POINTS = {1:10,2:9,3:8,4:7,5:6,6:5,7:4,8:3,9:2,10:1};
    const RACE_POS_POINTS  = {1:25,2:18,3:15,4:12,5:10,6:8,7:6,8:4,9:2,10:1};
    const SPRINT_POS_POINTS= {1:8,2:7,3:6,4:5,5:4,6:3,7:2,8:1};

    // Fallback if score_unit is missing from JSON (older exports).
    // ~0.14 is the rough race adjacent-gap median observed across 2026 rounds.
    const DEFAULT_GAP_MEDIAN = 0.14;

    let _state = freshState();
    let _round = null;
    let _scoreUnit = {};
    let _listeners = [];

    function freshState() {
        return {
            scenarioName: '',
            round: null,
            driverModifiers: {},   // { abbrev -> positions (number) }
            teamModifiers:   {},   // { team_id -> positions (number) }
        };
    }

    function loadStorage() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return freshState();
            const parsed = JSON.parse(raw);
            return Object.assign(freshState(), parsed);
        } catch(e) { return freshState(); }
    }

    function saveStorage() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(_state));
        } catch(e) {}
    }

    function notify() {
        _listeners.forEach(fn => { try { fn(_state); } catch(e) {} });
    }

    // -- Saved named scenarios (Phase 3) -------------------------------------
    // Storage shape:
    //   { "<round>": [ { name, driverModifiers, teamModifiers, savedAt }, ... ] }
    function loadSavesAll() {
        try {
            const raw = localStorage.getItem(SAVES_KEY);
            return raw ? JSON.parse(raw) : {};
        } catch(e) { return {}; }
    }
    function persistSavesAll(saves) {
        try { localStorage.setItem(SAVES_KEY, JSON.stringify(saves)); } catch(e) {}
    }
    function listSavedScenarios() {
        const all = loadSavesAll();
        return (all[String(_round)] || []).slice();
    }
    function saveCurrentAs(name) {
        if (!name || !String(name).trim()) return false;
        const trimmed = String(name).trim();
        const all = loadSavesAll();
        const key = String(_round);
        all[key] = all[key] || [];
        // Replace any existing save with the same name (case-insensitive)
        all[key] = all[key].filter(s => s.name.toLowerCase() !== trimmed.toLowerCase());
        all[key].unshift({
            name: trimmed,
            driverModifiers: Object.assign({}, _state.driverModifiers),
            teamModifiers: Object.assign({}, _state.teamModifiers),
            savedAt: new Date().toISOString(),
        });
        // Cap
        if (all[key].length > MAX_SAVED_PER_ROUND) {
            all[key] = all[key].slice(0, MAX_SAVED_PER_ROUND);
        }
        persistSavesAll(all);
        notify();
        return true;
    }
    function loadSavedScenario(name) {
        const saves = listSavedScenarios();
        const found = saves.find(s => s.name === name);
        if (!found) return false;
        _state = freshState();
        _state.round = _round;
        _state.driverModifiers = Object.assign({}, found.driverModifiers || {});
        _state.teamModifiers = Object.assign({}, found.teamModifiers || {});
        _state.scenarioName = found.name;
        saveStorage();
        notify();
        return true;
    }
    function deleteSavedScenario(name) {
        const all = loadSavesAll();
        const key = String(_round);
        if (!all[key]) return false;
        const before = all[key].length;
        all[key] = all[key].filter(s => s.name !== name);
        if (all[key].length === before) return false;
        persistSavesAll(all);
        notify();
        return true;
    }
    // Compare two saved scenarios — returns per-driver { baseline, A_pts, B_pts, delta }.
    // Useful for side-by-side rendering.
    function compareSavedScenarios(nameA, nameB, predictions) {
        if (!predictions) return null;
        const saves = listSavedScenarios();
        const findOrLoad = (name) => {
            if (name === '__current__') return { driverModifiers: _state.driverModifiers, teamModifiers: _state.teamModifiers };
            return saves.find(s => s.name === name);
        };
        const a = findOrLoad(nameA);
        const b = findOrLoad(nameB);
        if (!a || !b) return null;
        // Temporarily swap _state to compute each overlay, then restore
        const original = { d: _state.driverModifiers, t: _state.teamModifiers };
        _state.driverModifiers = Object.assign({}, a.driverModifiers || {});
        _state.teamModifiers = Object.assign({}, a.teamModifiers || {});
        const viewA = applyToAll(predictions);
        _state.driverModifiers = Object.assign({}, b.driverModifiers || {});
        _state.teamModifiers = Object.assign({}, b.teamModifiers || {});
        const viewB = applyToAll(predictions);
        _state.driverModifiers = original.d;
        _state.teamModifiers = original.t;
        // Build per-driver compare row
        const drivers = (predictions.drivers || []).map(base => {
            const da = viewA.drivers.find(x => x.driver_id === base.driver_id);
            const db = viewB.drivers.find(x => x.driver_id === base.driver_id);
            return {
                driver_id: base.driver_id,
                name: base.name,
                constructor: base.constructor,
                baseline: base.expected_points,
                A_pts: da ? da.expected_points_adjusted ?? da.expected_points : base.expected_points,
                B_pts: db ? db.expected_points_adjusted ?? db.expected_points : base.expected_points,
            };
        });
        drivers.forEach(d => { d.delta = (d.A_pts || 0) - (d.B_pts || 0); });
        return { nameA, nameB, drivers };
    }

    // Public: initialize with the current-round predictions payload.
    // If the stored scenario is for a different round, it's cleared —
    // pace bumps don't carry between Canada and Monaco.
    function init(predictions) {
        if (!predictions) return;
        _round = predictions.round;
        _scoreUnit = predictions.score_unit || {};
        const stored = loadStorage();
        if (stored.round !== _round) {
            _state = freshState();
            _state.round = _round;
            saveStorage();
        } else {
            _state = stored;
            _state.round = _round;
        }
    }

    // UI surface unit ("positions gained") -> raw XGBRanker score bump.
    // The adjacent-gap median is the typical raw-score distance between
    // sequentially-ranked drivers in that session, so 1 position ≈ 1 gap.
    function positionsToRawBump(positions, sessionKey) {
        const gap = _scoreUnit[sessionKey + '_gap_median'] || DEFAULT_GAP_MEDIAN;
        return positions * gap;
    }

    function getDriverPositionsBump(driver) {
        const t = _state.teamModifiers[driver.constructor] || 0;
        const d = _state.driverModifiers[driver.driver_id] || 0;
        return t + d;
    }

    function getTeamBump(teamId) { return _state.teamModifiers[teamId] || 0; }
    function getDriverOnlyBump(abbrev) { return _state.driverModifiers[abbrev] || 0; }

    function activeCount() {
        let n = 0;
        for (const v of Object.values(_state.driverModifiers)) if (Math.abs(v) > 0.001) n++;
        for (const v of Object.values(_state.teamModifiers))   if (Math.abs(v) > 0.001) n++;
        return n;
    }

    function isEmpty() { return activeCount() === 0; }

    function setDriverBump(abbrev, positions) {
        const p = Number(positions) || 0;
        if (Math.abs(p) < 0.001) {
            delete _state.driverModifiers[abbrev];
        } else {
            _state.driverModifiers[abbrev] = p;
        }
        saveStorage();
        notify();
    }

    function setTeamBump(teamId, positions) {
        const p = Number(positions) || 0;
        if (Math.abs(p) < 0.001) {
            delete _state.teamModifiers[teamId];
        } else {
            _state.teamModifiers[teamId] = p;
        }
        saveStorage();
        notify();
    }

    function reset() {
        _state = freshState();
        _state.round = _round;
        saveStorage();
        notify();
    }

    function getState() {
        return JSON.parse(JSON.stringify(_state));  // defensive copy
    }

    function getScoreUnit() {
        return Object.assign({}, _scoreUnit);
    }

    function onChange(fn) { if (typeof fn === 'function') _listeners.push(fn); }

    // Compute new positions for one session given the user's bumps.
    // Returns { abbrev -> { baseline_pos, adjusted_pos } } only for drivers
    // that have a raw score AND a baseline position for this session.
    function computeRerank(drivers, sessionKey, baselinePosKey) {
        const eligible = drivers.filter(d =>
            d.raw_scores && typeof d.raw_scores[sessionKey] === 'number' &&
            typeof d[baselinePosKey] === 'number'
        );
        if (eligible.length === 0) return {};

        const ranked = eligible.map(d => {
            const positionsBump = getDriverPositionsBump(d);
            const rawBump = positionsToRawBump(positionsBump, sessionKey);
            return {
                abbrev: d.driver_id,
                score: d.raw_scores[sessionKey] + rawBump,
                baseline: d[baselinePosKey],
            };
        }).sort((a, b) => b.score - a.score);

        const out = {};
        ranked.forEach((r, idx) => {
            out[r.abbrev] = {
                baseline_pos: r.baseline,
                adjusted_pos: idx + 1,
            };
        });
        return out;
    }

    function ptsDeltaQuali(base, adj) {
        return (QUALI_POS_POINTS[adj] || 0) - (QUALI_POS_POINTS[base] || 0);
    }
    function ptsDeltaRace(base, adj) {
        const pts = (RACE_POS_POINTS[adj] || 0) - (RACE_POS_POINTS[base] || 0);
        const gained = (base - adj) * 1;   // RACE_POSITIONS_GAINED_PER_POS = 1
        return pts + gained;
    }
    function ptsDeltaSprint(base, adj) {
        const pts = (SPRINT_POS_POINTS[adj] || 0) - (SPRINT_POS_POINTS[base] || 0);
        const gained = (base - adj) * 1;
        return pts + gained;
    }

    // Apply the active scenario to a full predictions payload. Returns a
    // shallow-copied payload with .drivers and .constructors decorated with
    // overlay fields. Safe to call when scenario is empty (returns the
    // payload unchanged).
    function applyToAll(predictions) {
        if (!predictions || isEmpty()) return predictions;

        const drivers = predictions.drivers || [];
        const constructors = predictions.constructors || [];

        const qRanks = computeRerank(drivers, 'quali', 'predicted_quali');
        const rRanks = computeRerank(drivers, 'race',  'predicted_finish');
        const sRanks = predictions.is_sprint_weekend
            ? computeRerank(drivers, 'sprint', 'predicted_sprint')
            : {};

        const outDrivers = drivers.map(d => {
            const overlay = Object.assign({}, d);
            let totalDelta = 0;

            const q = qRanks[d.driver_id];
            if (q) {
                const qd = ptsDeltaQuali(q.baseline_pos, q.adjusted_pos);
                overlay.predicted_quali_adjusted = q.adjusted_pos;
                overlay.quali_pts_delta = qd;
                totalDelta += qd;
            }
            const r = rRanks[d.driver_id];
            if (r) {
                const rd = ptsDeltaRace(r.baseline_pos, r.adjusted_pos);
                overlay.predicted_finish_adjusted = r.adjusted_pos;
                overlay.race_pts_delta = rd;
                totalDelta += rd;
            }
            const s = sRanks[d.driver_id];
            if (s) {
                const sd = ptsDeltaSprint(s.baseline_pos, s.adjusted_pos);
                overlay.predicted_sprint_adjusted = s.adjusted_pos;
                overlay.sprint_pts_delta = sd;
                totalDelta += sd;
            }

            overlay.points_delta = Math.round(totalDelta * 10) / 10;
            overlay.expected_points_adjusted = Math.round((d.expected_points + totalDelta) * 10) / 10;
            overlay.pace_bump = Number(getDriverPositionsBump(d).toFixed(2));
            return overlay;
        });

        // Constructor delta = sum of both drivers' position-points deltas.
        // Same approximation as pipeline/apply_upgrades.py — quali tier
        // bonus (both_q3 / one_q3 etc.) is NOT recomputed.
        const deltaByDriver = {};
        outDrivers.forEach(d => { deltaByDriver[d.driver_id] = d.points_delta || 0; });

        const outConstructors = constructors.map(c => {
            const sum = (deltaByDriver[c.driver_1] || 0) + (deltaByDriver[c.driver_2] || 0);
            const overlay = Object.assign({}, c);
            overlay.points_delta = Math.round(sum * 10) / 10;
            overlay.expected_points_adjusted = Math.round((c.expected_points + sum) * 10) / 10;
            overlay.pace_bump = Number((_state.teamModifiers[c.constructor_id] || 0).toFixed(2));
            return overlay;
        });

        return Object.assign({}, predictions, {
            drivers: outDrivers,
            constructors: outConstructors,
            _scenarioActive: true,
        });
    }

    // Encode/decode for URL sharing (?scenario=...).
    function encodeForUrl() {
        try {
            const payload = {
                r: _state.round,
                d: _state.driverModifiers,
                t: _state.teamModifiers,
                n: _state.scenarioName || '',
            };
            return btoa(unescape(encodeURIComponent(JSON.stringify(payload))));
        } catch(e) { return ''; }
    }
    function decodeFromUrl(str) {
        try {
            const json = decodeURIComponent(escape(atob(str)));
            const obj = JSON.parse(json);
            return {
                round: obj.r,
                driverModifiers: obj.d || {},
                teamModifiers: obj.t || {},
                scenarioName: obj.n || '',
            };
        } catch(e) { return null; }
    }
    function loadFromShareString(str) {
        const obj = decodeFromUrl(str);
        if (!obj) return false;
        if (obj.round !== _round) return false;  // wrong round, refuse
        _state = Object.assign(freshState(), obj);
        _state.round = _round;
        saveStorage();
        notify();
        return true;
    }

    window.scenarios = {
        init,
        applyToAll,
        getState,
        getScoreUnit,
        getDriverPositionsBump,
        getTeamBump,
        getDriverOnlyBump,
        setDriverBump,
        setTeamBump,
        reset,
        activeCount,
        isEmpty,
        onChange,
        encodeForUrl,
        loadFromShareString,
        // Phase 3: saved named scenarios + compare
        listSavedScenarios,
        saveCurrentAs,
        loadSavedScenario,
        deleteSavedScenario,
        compareSavedScenarios,
    };
})();
