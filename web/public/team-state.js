(function (root, factory) {
    if (typeof module !== 'undefined' && module.exports) module.exports = factory(null);
    else root.BoxBoxTeamState = factory(root);
}(typeof window !== 'undefined' ? window : globalThis, function (root) {
    'use strict';

    /*
     * Canonical client-side Pit Wall state.
     *
     * The API may still return the old singular `team`, `f1_link`, and
     * `f1_snapshot` fields.  This adapter always exposes three stable slots,
     * and keeps all writes explicitly scoped to the selected slot.  The
     * parent app can load this file before members.js; no framework is
     * required.
     */

    const SLOT_COUNT = 3;
    const CHIP_KEYS = ['limitless', '3x_boost', 'wild_card', 'no_negative', 'autopilot', 'final_fix'];

    function canonicalChipKey(key) {
        const normalized = String(key || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
        return normalized === 'boost' ? '3x_boost' : normalized;
    }

    function unknownChipState() {
        return { status: 'unknown', remaining: null };
    }

    function parseChipState(value) {
        if (typeof value === 'boolean') return { status: value ? 'available' : 'used', remaining: value };
        if (typeof value === 'number' && (value === 0 || value === 1)) return parseChipState(value === 1);
        if (typeof value === 'string') {
            const status = value.trim().toLowerCase();
            if (['available', 'unused', 'remaining', 'left', 'ready'].includes(status)) return { status: 'available', remaining: true };
            if (['used', 'spent', 'unavailable', 'disabled'].includes(status)) return { status: 'used', remaining: false };
            return unknownChipState();
        }
        if (!value || typeof value !== 'object') return unknownChipState();
        if (value.remaining === true || value.available === true || value.used === false) return { status: 'available', remaining: true };
        if (value.remaining === false || value.available === false || value.used === true) return { status: 'used', remaining: false };
        if (value.status !== undefined) return parseChipState(value.status);
        return unknownChipState();
    }

    function numberOr(value, fallback = null) {
        const number = Number(value);
        return Number.isFinite(number) ? number : fallback;
    }

    function firstFinite(...values) {
        for (const value of values) {
            if (value === null || value === undefined || value === '') continue;
            const number = Number(value);
            if (Number.isFinite(number)) return number;
        }
        return null;
    }

    function resolveOfficialTeamFinance(snapshot, currentSquadValue) {
        const squadValue = firstFinite(currentSquadValue, snapshot?.squad_value_millions);
        let bank = firstFinite(snapshot?.bank_millions, snapshot?.cash_millions, snapshot?.cash_balance);
        let spendingPower = firstFinite(snapshot?.spending_power_millions, snapshot?.total_budget_millions);
        const legacyBudget = firstFinite(snapshot?.budget_millions);

        // Older official snapshots stored F1's `teambal` cash field under the
        // legacy budget name. A value below the seven-pick squad value is cash,
        // not total spending power. New snapshots carry bank_millions explicitly.
        if (bank === null && spendingPower === null && legacyBudget !== null) {
            if (squadValue !== null && legacyBudget < squadValue) bank = legacyBudget;
            else spendingPower = legacyBudget;
        }
        if (spendingPower === null && squadValue !== null) spendingPower = squadValue + (bank ?? 0);
        if (bank === null && spendingPower !== null && squadValue !== null) bank = Math.max(0, spendingPower - squadValue);
        return { squadValue, bank, spendingPower };
    }

    function clone(value) {
        if (value === undefined) return undefined;
        if (typeof structuredClone === 'function') {
            try { return structuredClone(value); } catch (_) { /* use JSON below */ }
        }
        try { return JSON.parse(JSON.stringify(value)); } catch (_) { return value; }
    }

    function slotOf(team, fallback = 1) {
        const slot = Number(team?.team_slot ?? team?.slot ?? fallback);
        return Number.isInteger(slot) && slot >= 1 && slot <= SLOT_COUNT ? slot : fallback;
    }

    function normalizeAsset(asset) {
        if (!asset) return null;
        return {
            asset_type: asset.asset_type === 'constructor' ? 'constructor' : 'driver',
            asset_id: String(asset.asset_id ?? asset.id ?? '').trim().slice(0, 40),
            slot: numberOr(asset.slot, null),
            is_boosted: asset.is_boosted === true,
        };
    }

    function normalizeChips(chips) {
        const normalized = Object.fromEntries(CHIP_KEYS.map(key => [key, unknownChipState()]));
        const assign = (rawKey, rawValue = true) => {
            const key = canonicalChipKey(rawKey);
            if (!CHIP_KEYS.includes(key)) return;
            normalized[key] = parseChipState(rawValue);
        };
        if (Array.isArray(chips)) {
            const candidates = new Map();
            chips.forEach(item => {
                if (typeof item === 'string') {
                    const key = canonicalChipKey(item);
                    if (CHIP_KEYS.includes(key) && !candidates.has(key)) candidates.set(key, [{ value: true, season: null }]);
                } else if (item && typeof item === 'object') {
                    const key = canonicalChipKey(item.chip_code ?? item.code ?? item.key ?? item.name);
                    if (!CHIP_KEYS.includes(key)) return;
                    const season = Number(item.season ?? item.year ?? item.season_year);
                    const values = candidates.get(key) || [];
                    values.push({ value: item, season: Number.isFinite(season) ? season : null });
                    candidates.set(key, values);
                }
            });
            candidates.forEach((values, key) => {
                const current = values.find(candidate => candidate.season === 2026)
                    || values.filter(candidate => candidate.season !== null).sort((left, right) => right.season - left.season)[0]
                    || values[0];
                assign(key, current.value);
            });
            return normalized;
        }
        if (!chips || typeof chips !== 'object') return normalized;
        const seasonKeys = Object.keys(chips).filter(key => /^\d{4}$/.test(key));
        if (seasonKeys.length === Object.keys(chips).length && seasonKeys.length) {
            const season = chips['2026'] || chips[seasonKeys.sort((left, right) => Number(right) - Number(left))[0]];
            return normalizeChips(season);
        }
        if (chips.chip_code || chips.code || chips.key) {
            assign(chips.chip_code ?? chips.code ?? chips.key, chips);
            return normalized;
        }
        Object.entries(chips).forEach(([key, value]) => assign(key, value));
        return normalized;
    }

    function normalizeTeam(input, fallbackSlot = 1) {
        const source = input && typeof input === 'object' ? input : {};
        const slot = slotOf(source, fallbackSlot);
        const assets = Array.isArray(source.assets)
            ? source.assets.map(normalizeAsset).filter(Boolean)
            : [];
        return {
            id: source.id ? String(source.id) : null,
            team_slot: slot,
            slot,
            name: String(source.name || `Team ${slot}`).trim().slice(0, 60) || `Team ${slot}`,
            is_primary: source.is_primary === true || source.is_default === true,
            is_default: source.is_default === true || source.is_primary === true,
            source: String(source.source || source.source_type || (source.f1_link || source.f1_snapshot ? 'official' : 'manual')),
            assets,
            // budget_millions is the legacy spending-power alias. Preserve the
            // explicit field when the newer contract supplies both values.
            spending_power_millions: numberOr(source.spending_power_millions, numberOr(source.budget_millions, null)),
            budget_millions: numberOr(source.budget_millions, numberOr(source.spending_power_millions, null)),
            squad_value_millions: numberOr(source.squad_value_millions, null),
            bank_millions: numberOr(source.bank_millions, null),
            free_transfers: numberOr(source.free_transfers, null),
            chips: normalizeChips(source.chips),
            history: Array.isArray(source.history) ? clone(source.history) : [],
            updated_at: source.updated_at || null,
            f1_link: source.f1_link ? clone(source.f1_link) : null,
            f1_snapshot: source.f1_snapshot ? clone(source.f1_snapshot) : null,
        };
    }

    function emptyTeam(slot) {
        return normalizeTeam({ team_slot: slot, name: `Team ${slot}`, is_primary: slot === 1 }, slot);
    }

    function normalizeTeams(payload) {
        const source = Array.isArray(payload) ? { teams: payload } : (payload || {});
        const incoming = Array.isArray(source.teams) && source.teams.length
            ? source.teams
            : source.team ? [{ ...source.team, team_slot: source.team.team_slot || source.team.slot || 1,
                f1_link: source.f1_link, f1_snapshot: source.f1_snapshot }] : [];
        const bySlot = new Map();
        incoming.forEach((team, index) => {
            const normalized = normalizeTeam(team, index + 1);
            bySlot.set(normalized.slot, normalized);
        });
        const realTeams = Array.from(bySlot.values()).sort((left, right) => left.slot - right.slot);
        const primaryTeam = realTeams.find(team => team.is_primary || team.is_default) || null;
        const primarySlot = primaryTeam?.slot || 1;
        return Array.from({ length: SLOT_COUNT }, (_, index) => {
            const team = bySlot.get(index + 1) || emptyTeam(index + 1);
            return { ...team, is_primary: team.slot === primarySlot, is_default: team.slot === primarySlot };
        });
    }

    function normalizeDashboard(payload) {
        const source = payload || {};
        const teams = normalizeTeams(source);
        const primary = teams.find(team => team.is_primary) || teams[0];
        return {
            ...clone(source),
            teams,
            team: primary,
            selected_slot: slotOf(source.selected_slot ? { slot: source.selected_slot } : primary, primary.slot),
        };
    }

    function snapshotForTeam(team, overrides = {}) {
        const normalized = normalizeTeam({ ...team, ...overrides }, team?.slot || 1);
        return {
            team_slot: normalized.slot,
            slot: normalized.slot,
            name: normalized.name,
            budget_millions: normalized.budget_millions,
            spending_power_millions: normalized.spending_power_millions,
            squad_value_millions: normalized.squad_value_millions,
            bank_millions: normalized.bank_millions,
            free_transfers: normalized.free_transfers,
            chips: clone(normalized.chips),
            history: clone(normalized.history),
            assets: clone(normalized.assets),
            source: normalized.source,
            updated_at: normalized.updated_at,
        };
    }

    function canonicalSnapshot(team) {
        if (!team) return null;
        const snapshot = snapshotForTeam(team);
        snapshot.assets.sort((left, right) => String(left.asset_type).localeCompare(String(right.asset_type)) || Number(left.slot) - Number(right.slot));
        return snapshot;
    }

    function hasCompleteTeam(team) {
        const assets = team?.assets || [];
        const drivers = assets.filter(asset => asset.asset_type === 'driver' && asset.asset_id);
        const constructors = assets.filter(asset => asset.asset_type === 'constructor' && asset.asset_id);
        return drivers.length === 5 && constructors.length === 2;
    }

    function chipState(team, key) {
        const chips = team?.chips || {};
        const canonicalKey = canonicalChipKey(key);
        const rawKey = Object.keys(chips).find(candidate => canonicalChipKey(candidate) === canonicalKey);
        const value = chips[canonicalKey] ?? chips[key] ?? chips[String(canonicalKey).replace(/_/g, '')] ?? (rawKey ? chips[rawKey] : undefined);
        return parseChipState(value);
    }

    function chipRemaining(team, key) {
        return chipState(team, key).remaining;
    }

    function createStore(options = {}) {
        let state = {
            authenticated: false,
            entitlement: { active: false },
            profile: null,
            teams: Array.from({ length: SLOT_COUNT }, (_, index) => emptyTeam(index + 1)),
            selectedSlot: 1,
            loading: false,
            saving: false,
            error: null,
            lastSavedAt: null,
        };
        const listeners = new Set();
        const autosaveTimers = new Map();
        let autosaveQueue = Promise.resolve();
        let saveFingerprint = new Map();

        const emit = (event = 'updated') => {
            const snapshot = getState();
            listeners.forEach(listener => listener(snapshot, event));
            if (root?.dispatchEvent && typeof CustomEvent !== 'undefined') {
                root.dispatchEvent(new CustomEvent(`boxbox:pitwall-${event}`, { detail: snapshot }));
            }
        };
        const setState = (patch, event = 'updated') => {
            state = { ...state, ...patch };
            emit(event);
            return getState();
        };
        const getState = () => ({ ...state, teams: state.teams.map(clone) });
        const getTeam = slot => state.teams[slotOf({ slot }, 1) - 1] || null;
        const selectedTeam = () => getTeam(state.selectedSlot);
        const assertWritable = () => {
            if (state.authenticated !== true) throw new Error('Sign in to manage Pit Wall teams.');
            if (state.entitlement?.active !== true) throw new Error('Your Pit Wall teams are read-only until membership is active.');
        };
        const request = options.request || (async (path, requestOptions = {}) => {
            const response = await fetch(path, {
                method: requestOptions.method || 'GET',
                headers: requestOptions.body ? { 'Content-Type': 'application/json' } : undefined,
                body: requestOptions.body ? JSON.stringify(requestOptions.body) : undefined,
                credentials: 'same-origin',
                cache: 'no-store',
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                const error = new Error(data.message || 'That request did not complete.');
                error.status = response.status;
                throw error;
            }
            return data;
        });

        async function save(slot = state.selectedSlot, extra = {}) {
            assertWritable();
            const team = getTeam(slot);
            if (!team) throw new Error('Choose a team before saving.');
            if (!hasCompleteTeam(team)) throw new Error('Complete all five drivers and both constructors before saving.');
            const payload = {
                action: extra.action || 'save',
                ...snapshotForTeam(team, extra),
                team_slot: slot,
                slot,
                season: numberOr(extra.season, 2026),
                round: numberOr(extra.round ?? root?.BoxBoxTeamMemory?.currentRound?.(), null),
                ...(extra.action === 'rename' ? { name: extra.name } : {}),
            };
            const fingerprint = JSON.stringify(canonicalSnapshot(team));
            if (!extra.force && saveFingerprint.get(slot) === fingerprint) return { ok: true, unchanged: true, team };
            setState({ saving: true, error: null }, 'saving');
            try {
                const result = await request('/api/members/team/', { method: 'POST', body: payload });
                const returned = result.team || result.saved_team || result.teams?.find(item => slotOf(item) === slot);
                if (returned) replaceTeam(returned, 'saved');
                saveFingerprint.set(slot, fingerprint);
                state = { ...state, saving: false, lastSavedAt: new Date().toISOString() };
                emit('saved');
                return { ...result, team: getTeam(slot) };
            } catch (error) {
                setState({ saving: false, error: error.message }, 'error');
                throw error;
            }
        }

        function replaceTeam(team, event = 'updated', options = {}) {
            if (state.entitlement?.active !== true && options.internalHydrate !== true) {
                throw new Error('Your Pit Wall teams are read-only until membership is active.');
            }
            const normalized = normalizeTeam(team, slotOf(team, 1));
            const teams = state.teams.slice();
            teams[normalized.slot - 1] = normalized;
            state = { ...state, teams };
            emit(event);
            return normalized;
        }

        function hydrate(payload, options = {}) {
            const normalized = normalizeDashboard(payload);
            const selected = slotOf({ slot: options.selectedSlot || normalized.selected_slot }, 1);
            state = {
                ...state,
                ...normalized,
                selectedSlot: selected,
                teams: normalized.teams,
                error: null,
            };
            saveFingerprint = new Map(normalized.teams.filter(hasCompleteTeam).map(team => [team.slot, JSON.stringify(canonicalSnapshot(team))]));
            emit('loaded');
            return getState();
        }

        function select(slot, options = {}) {
            const next = slotOf({ slot }, 1);
            state = { ...state, selectedSlot: next };
            emit('selected');
            if (options.applyMemory !== false) applyToMemory(next, options.memory);
            return getTeam(next);
        }

        function applyToMemory(slot = state.selectedSlot, memory = root?.BoxBoxTeamMemory) {
            const team = getTeam(slot);
            if (!team || !memory) return false;
            const apply = typeof memory.apply === 'function' ? memory.apply : memory.applySnapshot;
            if (typeof apply !== 'function') return false;
            const result = apply.call(memory, snapshotForTeam(team));
            if (result === false) return false;
            return true;
        }

        function pullFromMemory(slot = state.selectedSlot, memory = root?.BoxBoxTeamMemory) {
            if (state.entitlement?.active !== true) return null;
            if (!memory || typeof memory.getSnapshot !== 'function') return null;
            let snapshot;
            try { snapshot = memory.getSnapshot(); } catch (_) { return null; }
            if (!snapshot) return null;
            replaceTeam({ ...getTeam(slot), ...snapshot, team_slot: slot, slot }, 'draft');
            return getTeam(slot);
        }

        function update(slot, patch, options = {}) {
            if (state.entitlement?.active !== true && options.internalHydrate !== true) {
                throw new Error('Your Pit Wall teams are read-only until membership is active.');
            }
            const team = getTeam(slot);
            if (!team) return null;
            replaceTeam({ ...team, ...clone(patch), team_slot: slot, slot }, options.event || 'updated');
            if (options.autosave) scheduleAutosave(slot, options.autosave);
            return getTeam(slot);
        }

        function scheduleAutosave(slot = state.selectedSlot, options = {}) {
            if (state.authenticated !== true || state.entitlement?.active !== true) return;
            const targetSlot = slotOf({ slot }, state.selectedSlot);
            clearTimeout(autosaveTimers.get(targetSlot));
            const timer = setTimeout(() => {
                autosaveTimers.delete(targetSlot);
                autosaveQueue = autosaveQueue.catch(() => null).then(() => save(targetSlot, options));
            }, Number(options.delayMs) || 800);
            autosaveTimers.set(targetSlot, timer);
        }

        async function rename(slot, name) {
            assertWritable();
            const team = getTeam(slot);
            const clean = String(name || '').trim().slice(0, 60);
            if (!team || !clean) throw new Error('Enter a name for this team.');
            update(slot, { name: clean });
            const result = await request('/api/members/team/', {
                method: 'POST', body: { action: 'rename', team_slot: slot, slot, name: clean },
            });
            if (result.team) replaceTeam({ ...getTeam(slot), ...result.team, team_slot: slot }, 'renamed');
            return result;
        }

        async function setPrimary(slot) {
            assertWritable();
            const target = slotOf({ slot }, 1);
            const teams = state.teams.map(team => ({ ...team, is_primary: team.slot === target, is_default: team.slot === target }));
            state = { ...state, teams };
            emit('primary-changed');
            const result = await request('/api/members/team/', { method: 'POST', body: { action: 'set-primary', team_slot: target, slot: target } });
            if (result.dashboard || Array.isArray(result.teams)) hydrate(result.dashboard || result, { selectedSlot: state.selectedSlot });
            return result;
        }

        async function linkOfficial(slot, selection) {
            assertWritable();
            const target = slotOf({ slot }, state.selectedSlot);
            const body = { action: 'f1-link', team_slot: target, slot: target, ...clone(selection) };
            const result = await request('/api/members/team/', { method: 'POST', body });
            if (result.dashboard || result.teams) hydrate(result.dashboard || result, { selectedSlot: target });
            else {
                const link = result.f1_link || result.link || result.team?.f1_link;
                if (link) replaceTeam({ ...getTeam(target), f1_link: clone(link), team_slot: target }, 'official-linked');
            }
            return result;
        }

        async function syncOfficial(slot, round) {
            assertWritable();
            const target = slotOf({ slot }, state.selectedSlot);
            const result = await request('/api/members/team/', {
                method: 'POST', body: { action: 'f1-sync', team_slot: target, slot: target, round },
            });
            const synced = result.team || result.snapshot || result.f1_snapshot;
            // Sync updates the reference snapshot only. It must never overwrite
            // a member's editable lineup, finances, chips or history implicitly.
            if (synced) replaceTeam({ ...getTeam(target), f1_snapshot: clone(synced), team_slot: target }, 'official-synced');
            return result;
        }

        async function synchronizeOfficial(slot, round, memory = root?.BoxBoxTeamMemory) {
            const target = slotOf({ slot }, state.selectedSlot);
            const result = await syncOfficial(target, round);
            if (!applyOfficialToMemory(target, memory)) {
                throw new Error('The official lineup could not be matched to the current race roster. Your saved team was not changed.');
            }
            const saved = await save(target, { force: true, round });
            return { ...result, saved, team: getTeam(target) };
        }

        function applyOfficialToMemory(slot = state.selectedSlot, memory = root?.BoxBoxTeamMemory) {
            assertWritable();
            const team = getTeam(slot);
            if (!team?.f1_snapshot || !memory?.applyOfficial || memory.applyOfficial(team.f1_snapshot) === false) return false;
            const snapshot = memory.getSnapshot?.();
            if (snapshot) update(slot, { ...snapshot, f1_snapshot: team.f1_snapshot, source: 'official' }, { event: 'official-applied' });
            return Boolean(snapshot);
        }

        function setChip(slot, key, value, options = {}) {
            assertWritable();
            const team = getTeam(slot);
            if (!team) return null;
            const chips = { ...(team.chips || {}), [canonicalChipKey(key)]: parseChipState(value) };
            delete chips.boost;
            return update(slot, { chips }, { autosave: options.autosave !== false });
        }

        function recordWeek(slot, metadata = {}, options = {}) {
            assertWritable();
            const team = getTeam(slot);
            if (!team) return null;
            const round = numberOr(metadata.round ?? metadata.week, null);
            const entry = {
                ...clone(metadata),
                ...(round === null ? {} : { round }),
                recorded_at: metadata.recorded_at || new Date().toISOString(),
                budget_millions: metadata.budget_millions ?? team.budget_millions,
                squad_value_millions: metadata.squad_value_millions ?? team.squad_value_millions,
                bank_millions: metadata.bank_millions ?? team.bank_millions,
                free_transfers: metadata.free_transfers ?? team.free_transfers,
                chips: clone(metadata.chips ?? team.chips),
            };
            const history = team.history.filter(item => round === null || numberOr(item?.round ?? item?.week, null) !== round);
            history.push(entry);
            history.sort((a, b) => numberOr(a.round ?? a.week, 0) - numberOr(b.round ?? b.week, 0));
            return update(slot, { history }, { autosave: options.autosave !== false });
        }

        return {
            getState, getTeam, getSelectedTeam: selectedTeam, getTeams: () => state.teams.map(clone),
            subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
            hydrate, normalizeDashboard, normalizeTeam, select, update, replaceTeam,
            save, scheduleAutosave, rename, setPrimary, linkOfficial, syncOfficial, synchronizeOfficial, applyOfficialToMemory,
            setChip, chipState, chipRemaining, recordWeek, applyToMemory, pullFromMemory,
            snapshotForTeam, canonicalSnapshot, hasCompleteTeam, clearError: () => setState({ error: null }),
            chipKeys: CHIP_KEYS.slice(),
        };
    }

    let singleton = null;
    const getStore = (options = {}) => {
        if (!singleton) singleton = createStore(options);
        return singleton;
    };
    const api = { SLOT_COUNT, CHIP_KEYS: CHIP_KEYS.slice(), normalizeTeam, normalizeTeams, normalizeDashboard,
        snapshotForTeam, canonicalSnapshot, hasCompleteTeam, chipState, chipRemaining, canonicalChipKey,
        resolveOfficialTeamFinance, createStore, getStore,
        resetStore: () => { singleton = null; return getStore(); } };
    if (root && !root.BoxBoxTeamState) root.BoxBoxTeamState = api;
    return api;
}));
