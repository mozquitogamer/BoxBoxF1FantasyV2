'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const { normalizeAssets } = require('../api/members/team');
const { normalizeChips, normalizeTeamSlot, requestedTeamSlot, shouldMarkPrimary } = require('../api/members/team');
const teamHandler = require('../api/members/team');

function mockResponse(body, status = 200) {
    return new Response(body === null ? '' : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function mockServerResponse() {
    return {
        statusCode: 200,
        headers: {},
        body: null,
        setHeader(name, value) { this.headers[name] = value; },
        getHeader(name) { return this.headers[name]; },
        status(code) { this.statusCode = code; return this; },
        json(value) { this.body = value; return this; },
    };
}

function memberJwt() {
    const encode = value => Buffer.from(JSON.stringify(value)).toString('base64url');
    return `${encode({ alg: 'HS256' })}.${encode({ sub: 'member-1', email: 'member@example.com' })}.test`;
}

function configureMemberEnv() {
    const names = ['NEXT_PUBLIC_SUPABASE_URL', 'NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY', 'SUPABASE_SERVICE_ROLE_KEY', 'SITE_ORIGIN', 'VERCEL_ENV'];
    const previous = Object.fromEntries(names.map(name => [name, process.env[name]]));
    Object.assign(process.env, {
        NEXT_PUBLIC_SUPABASE_URL: 'https://project.supabase.test',
        NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'public-test-key',
        SUPABASE_SERVICE_ROLE_KEY: 'service-test-key',
        SITE_ORIGIN: 'https://boxboxf1fantasy.com',
        VERCEL_ENV: 'production',
    });
    return () => names.forEach(name => previous[name] === undefined ? delete process.env[name] : process.env[name] = previous[name]);
}

test('normalizes saved-team slots to the three stable Pit Wall slots', () => {
    assert.equal(normalizeTeamSlot(2), 2);
    assert.equal(normalizeTeamSlot('3'), 3);
    assert.equal(normalizeTeamSlot(0), 1);
    assert.equal(normalizeTeamSlot(4, 2), 2);
});

test('normalizes chip state without treating unknown as used', () => {
    assert.deepEqual(normalizeChips([
        { chip_code: 'limitless', available: true },
        { code: 'wild_card', status: 'used', used_round: '7' },
        { chip_code: 'autopilot' },
    ]), [
        { chip_code: 'limitless', status: 'available', available: true, used_round: null },
        { chip_code: 'wild_card', status: 'used', available: false, used_round: 7 },
        { chip_code: 'autopilot', status: 'unknown', available: null, used_round: null },
    ]);
    assert.deepEqual(normalizeChips({ limitless: 'available', wild_card: { status: 'used' }, autopilot: true }), [
        { chip_code: 'limitless', status: 'available', available: true, used_round: null },
        { chip_code: 'wild_card', status: 'used', available: false, used_round: null },
        { chip_code: 'autopilot', status: 'available', available: true, used_round: null },
    ]);
    assert.throws(() => normalizeChips([{ chip_code: 'bad', status: 'available' }]), /Unknown chip code/);
    assert.throws(() => normalizeChips([{ chip_code: 'limitless', status: 'invalid' }]), /Invalid status/);
    assert.throws(() => normalizeChips([{ chip_code: 'limitless', status: 'available', used_round: 4 }]), /Only used chips/);
});

test('slot-aware saves preserve primary while legacy saves may claim Team 1', () => {
    assert.equal(shouldMarkPrimary({ team_slot: 2 }), false);
    assert.equal(shouldMarkPrimary({ team_slot: 1 }), false);
    assert.equal(shouldMarkPrimary({ team_slot: 2, is_primary: true }), true);
    assert.equal(shouldMarkPrimary({}), true);
});

test('explicit invalid slots are rejected while missing slot remains legacy Team 1', () => {
    assert.deepEqual(requestedTeamSlot({}), { slot: 1, legacy: true });
    assert.deepEqual(requestedTeamSlot({ team_slot: '3' }), { slot: 3, legacy: false });
    assert.throws(() => requestedTeamSlot({ team_slot: 0 }), /Team slot must be 1, 2 or 3/);
    assert.throws(() => requestedTeamSlot({ slot: 'three' }), /Team slot must be 1, 2 or 3/);
});

test('migration preserves unknown legacy finances and secures weekly history writes', () => {
    const migration = fs.readFileSync(path.join(__dirname, '..', '..', 'infrastructure', 'supabase', '005_pit_wall_three_team_workspace.sql'), 'utf8');
    assert.match(migration, /spending_power_millions = coalesce\(spending_power_millions, budget_millions\)/);
    assert.doesNotMatch(migration, /bank_millions\s*=\s*budget_millions/);
    assert.match(migration, /p_squad_value_millions numeric[\s\S]*p_bank_millions numeric[\s\S]*p_spending_power_millions numeric/);
    assert.match(migration, /paid members insert own team history/);
    assert.match(migration, /grant select, insert, update on public\.saved_team_history/);
    assert.match(migration, /drop policy if exists "members read own teams"/);
    assert.match(migration, /drop policy if exists "paid members update own team history"/);
    assert.match(migration, /not exists \(\s*select 1 from public\.saved_teams existing[\s\S]*existing\.is_default/);
    const teamApi = fs.readFileSync(path.join(__dirname, '..', 'api', 'members', 'team.js'), 'utf8');
    assert.match(teamApi, /budget_millions: null/);
    const notifyApi = fs.readFileSync(path.join(__dirname, '..', 'api', 'members', 'notify.js'), 'utf8');
    assert.match(notifyApi, /saved_teams\?user_id=\$\{usersFilter\}&is_default=eq\.true&select=id,user_id,team_slot/);
});

test('keeps old seven-asset save payloads compatible', () => {
    const assets = normalizeAssets([
        ...['a', 'b', 'c', 'd', 'e'].map((asset_id, index) => ({ asset_type: 'driver', asset_id, slot: index + 1 })),
        ...['x', 'y'].map((asset_id, index) => ({ asset_type: 'constructor', asset_id, slot: index + 1 })),
    ]);
    assert.equal(assets.length, 7);
    assert.equal(assets.filter(asset => asset.asset_type === 'driver').length, 5);
    assert.equal(assets.filter(asset => asset.asset_type === 'constructor').length, 2);
});

test('rename and set-primary actions are slot-scoped and do not require assets', async () => {
    const restoreEnv = configureMemberEnv();
    const originalFetch = global.fetch;
    const calls = [];
    global.fetch = async (url, options = {}) => {
        const target = String(url);
        calls.push({ target, options });
        if (target.endsWith('/auth/v1/user')) return mockResponse({ id: 'member-1', email: 'member@example.com' });
        if (target.includes('/rest/v1/member_entitlements?')) return mockResponse([{ status: 'active', current_period_end: '2099-01-01T00:00:00Z' }]);
        if (target.includes('/rest/v1/member_profiles?')) return mockResponse([{ user_id: 'member-1', email: 'member@example.com' }]);
        if (target.includes('/rest/v1/f1_team_links?')) return mockResponse([]);
        if (target.includes('/rest/v1/f1_team_snapshots?')) return mockResponse([]);
        if (target.includes('/rest/v1/saved_teams?')) return mockResponse([{ id: 'team-2', team_slot: 2, name: 'Second', is_default: true, budget_millions: 100, spending_power_millions: 100, free_transfers: 2 }]);
        if (target.includes('/rest/v1/saved_team_assets?')) return mockResponse([]);
        if (target.includes('/rest/v1/member_chips?')) return mockResponse([]);
        if (target.includes('/rest/v1/saved_team_history?')) return mockResponse([]);
        if (target.includes('/rest/v1/member_recommendations?')) return mockResponse([]);
        if (target.includes('/rest/v1/rpc/rename_member_team')) return mockResponse('team-2');
        if (target.includes('/rest/v1/rpc/set_member_team_primary')) return mockResponse('team-2');
        throw new Error(`Unexpected request: ${target}`);
    };
    const request = action => ({
        method: 'POST',
        body: { action, team_slot: 2, name: action === 'rename' ? 'Second Updated' : undefined },
        headers: { origin: 'https://boxboxf1fantasy.com', cookie: `__Host-boxbox_member_access=${memberJwt()}` },
        query: { action },
        url: `/api/members/team?action=${action}`,
    });
    try {
        const renameRes = mockServerResponse();
        await teamHandler(request('rename'), renameRes);
        assert.equal(renameRes.statusCode, 200);
        assert.equal(renameRes.body.team_slot, 2);
        assert.ok(calls.some(call => call.target.includes('/rpc/rename_member_team')));
        const primaryRes = mockServerResponse();
        await teamHandler(request('set-primary'), primaryRes);
        assert.equal(primaryRes.statusCode, 200);
        assert.equal(primaryRes.body.team_slot, 2);
        assert.ok(calls.some(call => call.target.includes('/rpc/set_member_team_primary')));
    } finally {
        global.fetch = originalFetch;
        restoreEnv();
    }
});
