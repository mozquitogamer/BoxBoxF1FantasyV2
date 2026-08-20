'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const teamHandler = require('../api/members/team');
const signOutHandler = require('../api/members/sign-out');
const sessionHandler = require('../api/members/session');
const statusHandler = require('../api/email/status');
const { beatV13SessionCookie } = require('../lib/beat-v13-entries');

function response(body, status = 200) {
    return new Response(body === null ? '' : JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
    });
}

function mockRes() {
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

function configure() {
    const names = [
        'SUPABASE_URL', 'NEXT_PUBLIC_SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY',
        'BEAT_V13_SESSION_SECRET', 'SITE_ORIGIN', 'VERCEL_ENV', 'F1_FANTASY_ORIGIN',
    ];
    const previous = Object.fromEntries(names.map(name => [name, process.env[name]]));
    Object.assign(process.env, {
        SUPABASE_URL: 'https://project.supabase.test',
        NEXT_PUBLIC_SUPABASE_URL: 'https://project.supabase.test',
        SUPABASE_SERVICE_ROLE_KEY: 'service-test-key',
        BEAT_V13_SESSION_SECRET: 'entry-session-test-secret',
        SITE_ORIGIN: 'https://boxboxf1fantasy.com',
        VERCEL_ENV: 'production',
        F1_FANTASY_ORIGIN: 'https://fantasy.formula1.test',
    });
    return () => {
        for (const [name, value] of Object.entries(previous)) {
            if (value === undefined) delete process.env[name];
            else process.env[name] = value;
        }
    };
}

function request(method, body, cookie) {
    return {
        method,
        body,
        headers: {
            origin: 'https://boxboxf1fantasy.com',
            host: 'boxboxf1fantasy.com',
            cookie,
        },
        query: method === 'GET'
            ? { scope: 'beat-v13', action: 'search', q: 'Exact Team' }
            : { scope: 'beat-v13' },
        url: '/api/members/team/?scope=beat-v13&action=search&q=Exact%20Team',
    };
}

test('free confirmed entrant can search and link an exact public-league team without Pit Wall', async () => {
    const restoreEnv = configure();
    const originalFetch = global.fetch;
    const entrantId = '11111111-1111-4111-8111-111111111111';
    const cookie = beatV13SessionCookie(entrantId);
    const calls = [];
    global.fetch = async (url, options = {}) => {
        const target = String(url);
        calls.push({ target, options });
        if (target.includes('/rest/v1/beat_v13_entries?id=eq.')) {
            if (options.method === 'PATCH') {
                return response({
                    id: entrantId, status: 'confirmed', confirmed_at: '2026-08-01T00:00:00Z',
                    official_team_id: 'official-1', official_team_name: 'Exact Team',
                    official_team_slot: 2, official_league_id: 160604,
                    official_team_linked_at: '2026-08-20T00:00:00Z',
                });
            }
            return response([{
                id: entrantId, status: 'confirmed', confirmed_at: '2026-08-01T00:00:00Z',
            }]);
        }
        if (target.includes('/feeds/leaderboard/publicleague/')) {
            return response({ leaderboard: [{
                team_id: 'official-1', slot: 2, name: 'Exact Team', points: 1234, rank: 7, manager: 'Private Manager',
            }] });
        }
        throw new Error(`Unexpected request: ${target}`);
    };
    try {
        const searchRes = mockRes();
        await teamHandler(request('GET', null, cookie), searchRes);
        assert.equal(searchRes.statusCode, 200);
        assert.equal(searchRes.body.teams.length, 1);
        assert.equal(searchRes.body.teams[0].name, 'Exact Team');
        assert.equal('manager' in searchRes.body.teams[0], false);
        assert.equal('email' in searchRes.body.teams[0], false);
        const linkRes = mockRes();
        await teamHandler(request('POST', {
            action: 'link', selection_token: searchRes.body.teams[0].selection_token,
        }, cookie), linkRes);
        assert.equal(linkRes.statusCode, 200);
        assert.equal(linkRes.body.entry.official_team_name, 'Exact Team');
        assert.equal(linkRes.body.entry.team_slot, 2);
        assert.equal('manager_name' in linkRes.body.entry, false);
        assert.equal(calls.some(call => call.target.includes('/rest/v1/member_entitlements')), false);
    } finally {
        global.fetch = originalFetch;
        restoreEnv();
    }
});

test('unified Beat V13 sign-out expires free and Pit Wall session cookies', async () => {
    const restoreEnv = configure();
    try {
        const res = mockRes();
        await signOutHandler({
            method: 'POST',
            headers: { origin: 'https://boxboxf1fantasy.com' },
        }, res);
        assert.equal(res.statusCode, 200);
        const cookies = res.headers['Set-Cookie'];
        assert.ok(cookies.some(cookie => cookie.startsWith('__Host-boxbox_beat_v13_session=') && cookie.includes('Max-Age=0')));
        assert.ok(cookies.some(cookie => cookie.startsWith('__Host-boxbox_beat_v13=') && cookie.includes('Max-Age=0')));
        assert.ok(cookies.some(cookie => cookie.startsWith('__Host-boxbox_member_access=') && cookie.includes('Max-Age=0')));
        assert.ok(cookies.some(cookie => cookie.startsWith('__Host-boxbox_member_refresh=') && cookie.includes('Max-Age=0')));
    } finally {
        restoreEnv();
    }
});

test('shared session endpoint returns a confirmed free Beat V13 account', async () => {
    const restoreEnv = configure();
    const originalFetch = global.fetch;
    const entrantId = '11111111-1111-4111-8111-111111111111';
    const cookie = beatV13SessionCookie(entrantId);
    global.fetch = async (url) => {
        if (String(url).includes('/rest/v1/beat_v13_entries?id=eq.')) {
            return response([{
                id: entrantId,
                status: 'confirmed',
                confirmed_at: '2026-08-01T00:00:00Z',
            }]);
        }
        throw new Error(`Unexpected request: ${url}`);
    };
    try {
        const res = mockRes();
        await sessionHandler({
            method: 'GET',
            headers: { cookie },
            query: { scope: 'beat-v13' },
            url: '/api/members/session/?scope=beat-v13',
        }, res);
        assert.equal(res.statusCode, 200);
        assert.equal(res.body.authenticated, true);
        assert.equal(res.body.confirmed, true);
        assert.equal(res.body.linked, false);
    } finally {
        global.fetch = originalFetch;
        restoreEnv();
    }
});

test('public leaderboard reports confirmed and scored counts without private fields', async () => {
    const restoreEnv = configure();
    const originalFetch = global.fetch;
    global.fetch = async (url, options = {}) => {
        const target = String(url);
        if (target.includes('/rest/v1/beat_v13_entries?')) {
            assert.match(target, /select=id,status,confirmed_at,official_team_id,official_team_name,official_team_slot/);
            assert.equal(target.includes('email_normalized'), false);
            return response([
                { id: 'one', email_normalized: 'one@example.com', status: 'confirmed', confirmed_at: '2026-08-01T00:00:00Z', official_team_id: 'official-1', official_team_name: 'Exact Team', official_team_slot: 2 },
                { id: 'two', email_normalized: 'two@example.com', status: 'confirmed', confirmed_at: '2026-08-01T00:00:00Z' },
                { id: 'three', email_normalized: 'three@example.com', status: 'pending', official_team_id: 'official-2', official_team_name: 'Not Confirmed', official_team_slot: 1 },
            ]);
        }
        if (target.includes('/feeds/leaderboard/publicleague/')) {
            return response({ leaderboard: [{ team_id: 'official-1', slot: 2, name: 'Exact Team', points: 1234, rank: 7, manager: 'Private Manager' }] });
        }
        throw new Error(`Unexpected request: ${target}`);
    };
    try {
        statusHandler._resetLeaderboardCache();
        const res = mockRes();
        await statusHandler({ method: 'GET', query: { resource: 'beat-v13-leaderboard' }, url: '/api/email/status?resource=beat-v13-leaderboard' }, res);
        assert.equal(res.statusCode, 200);
        assert.equal(res.body.confirmed_entrant_count, 2);
        assert.equal(res.body.linked_entrant_count, 1);
        assert.equal(res.body.scored_entrant_count, 1);
        assert.equal(res.body.leaderboard.some(row => row.team_name === 'Exact Team'), true);
        assert.equal(JSON.stringify(res.body).includes('@example.com'), false);
        assert.equal(JSON.stringify(res.body).includes('Private Manager'), false);
    } finally {
        global.fetch = originalFetch;
        restoreEnv();
    }
});
