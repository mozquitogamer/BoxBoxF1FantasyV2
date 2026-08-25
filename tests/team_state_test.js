'use strict';

const assert = require('node:assert/strict');
const { createStore, getStore, resetStore, normalizeTeam, normalizeDashboard, canonicalSnapshot, hasCompleteTeam, chipRemaining, CHIP_KEYS } = require('../web/public/team-state.js');

function team(slot, name, complete = true) {
    return {
        id: `team-${slot}`, team_slot: slot, name, is_primary: slot === 1,
        budget_millions: 100 - slot, squad_value_millions: 90 + slot, bank_millions: 10 - slot,
        free_transfers: slot, chips: { limitless: { remaining: slot !== 2 } },
        assets: complete ? [
            ...[1, 2, 3, 4, 5].map(index => ({ asset_type: 'driver', asset_id: `d${slot}-${index}`, slot: index })),
            ...[1, 2].map(index => ({ asset_type: 'constructor', asset_id: `c${slot}-${index}`, slot: index })),
        ] : [],
    };
}

const dashboard = normalizeDashboard({ authenticated: true, entitlement: { active: true }, teams: [team(1, 'Sunday Strategy'), team(3, 'Rain Plan')] });
assert.equal(dashboard.teams.length, 3);
assert.equal(dashboard.teams[0].name, 'Sunday Strategy');
assert.equal(dashboard.teams[1].name, 'Team 2');
assert.equal(dashboard.teams[2].name, 'Rain Plan');
const spendingTeam = normalizeTeam({ team_slot: 1, budget_millions: 100, spending_power_millions: 96, assets: [] });
assert.equal(spendingTeam.budget_millions, 100);
assert.equal(spendingTeam.spending_power_millions, 96);
assert.equal(spendingTeam.assets.every(asset => String(asset.asset_id || '').length <= 40), true);
assert.equal(hasCompleteTeam(dashboard.teams[0]), true);
assert.equal(chipRemaining(dashboard.teams[0], 'limitless'), true);
assert.equal(chipRemaining(dashboard.teams[2], 'limitless'), true);
assert.deepEqual(CHIP_KEYS, ['limitless', '3x_boost', 'wild_card', 'no_negative', 'autopilot', 'final_fix']);
const chipTeam = normalizeTeam({ source_type: 'official', chips: [
    { chip_code: 'LIMITLESS', status: 'used', season: 2025 },
    { chip_code: 'LIMITLESS', status: 'available', season: 2026 },
    { chip_code: '3X_BOOST', used: true, season: 2026 },
    { chip_code: 'WILD_CARD', status: 'mystery', season: 2026 },
    { chip_code: 'AUTOPILOT', status: 'available', season: 2025 },
    { chip_code: 'AUTOPILOT', status: 'used', season: 2024 },
    { chip_code: 'unknown_chip', status: 'available', season: 2026 },
], team_slot: 1 });
assert.equal(chipTeam.source, 'official');
assert.deepEqual(Object.keys(chipTeam.chips), CHIP_KEYS);
assert.equal(chipRemaining(chipTeam, 'limitless'), true);
assert.equal(chipRemaining(chipTeam, 'boost'), false);
assert.equal(chipRemaining(chipTeam, 'wild_card'), null);
assert.equal(chipRemaining(chipTeam, 'autopilot'), true);
const mappedChips = normalizeTeam({ chips: { LIMITLESS: true, '3X_BOOST': { used: false }, WILD_CARD: { status: 'used' }, FINAL_FIX: { status: 'unconfirmed' } }, team_slot: 1 }).chips;
assert.equal(chipRemaining({ chips: mappedChips }, 'limitless'), true);
assert.equal(chipRemaining({ chips: mappedChips }, '3x_boost'), true);
assert.equal(chipRemaining({ chips: mappedChips }, 'wild_card'), false);
assert.equal(chipRemaining({ chips: mappedChips }, 'final_fix'), null);
const primaryDashboard = normalizeDashboard({ teams: [
    { ...team(2, 'Primary T2'), team_slot: 2, is_primary: true, is_default: true },
    { ...team(3, 'Other T3'), team_slot: 3, is_primary: false },
] });
assert.equal(primaryDashboard.teams.filter(item => item.is_primary).length, 1);
assert.equal(primaryDashboard.teams[1].is_primary, true);
assert.equal(primaryDashboard.teams[0].is_primary, false);
const sharedA = resetStore();
const sharedB = getStore();
assert.equal(sharedA, sharedB);
assert.equal(sharedA.getState().selectedSlot, 1);

const requests = [];
const store = createStore({ request: async (path, options) => {
    requests.push({ path, body: typeof options.body === 'string' ? JSON.parse(options.body) : options.body });
    return { ok: true, message: 'saved' };
} });
store.hydrate(dashboard);
store.select(3, { applyMemory: false });
assert.equal(store.getState().selectedSlot, 3);
assert.equal(store.getSelectedTeam().name, 'Rain Plan');
store.update(3, { bank_millions: 7.5 });
store.save(3, { force: true }).then(() => {
    assert.equal(requests.length, 1);
    assert.equal(requests[0].body.team_slot, 3);
    assert.equal(requests[0].body.slot, 3);
    assert.equal(requests[0].body.bank_millions, 7.5);
    assert.equal(requests[0].body.season, 2026);
    assert.equal(requests[0].body.round, null);
    assert.equal(canonicalSnapshot(store.getTeam(3)).team_slot, 3);
    assert.equal(store.pullFromMemory(3, { getSnapshot: () => { throw new Error('incomplete lineup'); } }), null);

    const autosaveRequests = [];
    const autosaveStore = createStore({ request: async (path, options) => {
        autosaveRequests.push(options.body);
        return { ok: true };
    } });
    autosaveStore.hydrate(dashboard);
    autosaveStore.scheduleAutosave(1, { delayMs: 5, force: true });
    autosaveStore.scheduleAutosave(3, { delayMs: 5, force: true });

    const inactive = createStore({ request: async () => { throw new Error('inactive store attempted a write'); } });
    inactive.hydrate({ authenticated: true, entitlement: { active: false }, teams: [team(1, 'Read only')] });
    assert.throws(() => inactive.setChip(1, 'limitless', false), /read-only/);
    assert.throws(() => inactive.recordWeek(1, { round: 1 }, { autosave: false }), /read-only/);
    assert.rejects(() => inactive.save(1, { force: true }), /read-only/);
    assert.rejects(() => inactive.rename(1, 'No write'), /read-only/);
    assert.rejects(() => inactive.setPrimary(1), /read-only/);
    assert.rejects(() => inactive.linkOfficial(1, { link_token: 'token' }), /read-only/);
    assert.rejects(() => inactive.syncOfficial(1, 10), /read-only/);
    return new Promise(resolve => setTimeout(() => {
        assert.equal(autosaveRequests.length, 2);
        assert.deepEqual(autosaveRequests.map(body => body.team_slot).sort(), [1, 3]);
        console.log('team_state_test: ok');
        resolve();
    }, 40));
}).catch(error => { console.error(error); process.exitCode = 1; });
