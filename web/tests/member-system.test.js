'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const { buildRecommendation } = require('../lib/personalized-recommendations');
const { isAllowedOrigin, safeEqual } = require('../lib/member-system');
const { inFilter, notificationEventKey } = require('../api/members/notify');
const { paidUntil, parseKofiPayload, sanitizedKofiPayload } = require('../api/webhooks/kofi');
const { consumeRateLimit } = require('../lib/rate-limit');
const { applySyncedOfficialSnapshot, preferredMemberTeam, snapshotFingerprint } = require('../public/members');

function predictions() {
    const drivers = [
        ['A', 'Driver A', 10, 10],
        ['B', 'Driver B', 11, 11],
        ['C', 'Driver C', 12, 12],
        ['D', 'Driver D', 13, 13],
        ['E', 'Driver E', 14, 14],
        ['F', 'Driver F', 18, 14],
        ['G', 'Driver G', 30, 40],
    ].map(([driver_id, name, projected_points, current_price]) => ({
        driver_id, name, projected_points, expected_points: projected_points, current_price,
    }));
    const constructors = [
        ['one', 'One', 30, 20],
        ['two', 'Two', 31, 21],
        ['three', 'Three', 39, 25],
    ].map(([constructor_id, name, projected_points, current_price]) => ({
        constructor_id, name, projected_points, expected_points: projected_points, current_price,
    }));
    return {
        race: 'Test Grand Prix',
        round: 15,
        season: 2026,
        phase: 'post_fp',
        generated_at: '2026-09-01T12:00:00Z',
        drivers,
        constructors,
    };
}

function team(freeTransfers = 1) {
    return {
        budget_millions: 105,
        free_transfers: freeTransfers,
        assets: [
            ...['A', 'B', 'C', 'D', 'E'].map((asset_id, index) => ({ asset_type: 'driver', asset_id, slot: index + 1 })),
            ...['one', 'two'].map((asset_id, index) => ({ asset_type: 'constructor', asset_id, slot: index + 1 })),
        ],
    };
}

test('recommends the strongest affordable one-move upgrade', () => {
    const result = buildRecommendation(predictions(), team());
    assert.equal(result.move.asset_type, 'driver');
    assert.equal(result.move.outgoing_id, 'A');
    assert.equal(result.move.incoming_id, 'F');
    assert.equal(result.move.projected_gain, 8);
    assert.match(result.headline, /Driver A.*Driver F/);
    assert.equal(result.captain.name, 'Driver E');
});

test('accounts for an extra-transfer penalty before recommending action', () => {
    const result = buildRecommendation(predictions(), team(0));
    assert.equal(result.move, null);
    assert.equal(result.headline, 'Hold your current lineup');
});

test('loads a saved Transfer Advisor working team ahead of the official reset snapshot', () => {
    const saved = team(1);
    const official = { ...team(2), round: 14 };
    const preferred = preferredMemberTeam({ team: saved, f1_snapshot: official });
    assert.equal(preferred.source, 'saved');
    assert.equal(preferred.team, saved);
});

test('uses the official snapshot only when no complete working team is saved', () => {
    const official = { ...team(2), round: 14 };
    const preferred = preferredMemberTeam({ team: null, f1_snapshot: official });
    assert.equal(preferred.source, 'official');
    assert.equal(preferred.team, official);
});

test('working-team fingerprints ignore asset order but retain budget and transfers', () => {
    const original = team(1);
    const reordered = { ...original, assets: [...original.assets].reverse() };
    assert.equal(snapshotFingerprint(original), snapshotFingerprint(reordered));
    assert.notEqual(snapshotFingerprint(original), snapshotFingerprint({ ...original, free_transfers: 2 }));
});

test('official sync stops with a roster-specific error instead of trying to save an incomplete grid', () => {
    assert.throws(
        () => applySyncedOfficialSnapshot({ assets: team().assets }, { applyOfficial: () => false }),
        /could not be matched to the current race roster/i,
    );
    const expected = team();
    assert.equal(applySyncedOfficialSnapshot(
        { assets: expected.assets },
        { applyOfficial: () => true, getSnapshot: () => expected },
    ), expected);
});

test('parses Ko-fi form payloads and grants only a bounded paid period', () => {
    const payload = {
        message_id: 'message-1',
        email: 'fan@example.com',
        is_subscription_payment: true,
    };
    const req = { body: new URLSearchParams({ data: JSON.stringify(payload) }).toString() };
    assert.deepEqual(parseKofiPayload(req), payload);
    assert.equal(paidUntil('2026-08-01T00:00:00Z'), '2026-09-05T00:00:00.000Z');
});

test('uses timing-safe secret comparison and safe PostgREST filters', () => {
    assert.equal(safeEqual('same-secret', 'same-secret'), true);
    assert.equal(safeEqual('same-secret', 'different'), false);
    assert.equal(
        inFilter(['21b4f9ba-1bf3-4dd4-a0de-c2af164f8463', 'unsafe),drop table']),
        'in.(21b4f9ba-1bf3-4dd4-a0de-c2af164f8463,unsafedroptable)',
    );
});

test('stores only necessary Ko-fi payment metadata', () => {
    const stored = sanitizedKofiPayload({
        verification_token: 'must-not-be-stored',
        email: 'fan@example.com',
        from_name: 'Private Donor Name',
        message: 'Private supporter message',
        timestamp: '2026-08-01T00:00:00Z',
        amount: '5.00',
        currency: 'USD',
        is_first_subscription_payment: 'true',
        kofi_transaction_id: 'transaction-1',
    });
    assert.deepEqual(stored, {
        timestamp: '2026-08-01T00:00:00Z',
        amount: '5.00',
        currency: 'USD',
        is_first_subscription_payment: true,
        kofi_transaction_id: 'transaction-1',
    });
});

test('production origin checks do not trust a spoofed host header', () => {
    const previous = process.env.VERCEL_ENV;
    process.env.VERCEL_ENV = 'production';
    try {
        const req = { headers: { origin: 'https://attacker.example', host: 'attacker.example' } };
        assert.equal(isAllowedOrigin(req, 'https://boxboxf1fantasy.com'), false);
        assert.equal(isAllowedOrigin({ headers: { origin: 'https://www.boxboxf1fantasy.com' } }, 'https://boxboxf1fantasy.com'), true);
    } finally {
        if (previous === undefined) delete process.env.VERCEL_ENV;
        else process.env.VERCEL_ENV = previous;
    }
});

test('throttles repeated sensitive requests by client address', () => {
    const req = { headers: { 'x-real-ip': '192.0.2.42' } };
    const options = { limit: 2, windowMs: 60_000, now: 1_000 };
    assert.equal(consumeRateLimit(req, 'security-test', options).allowed, true);
    assert.equal(consumeRateLimit(req, 'security-test', options).allowed, true);
    assert.equal(consumeRateLimit(req, 'security-test', options).allowed, false);
});

test('deduplicates member alerts across regenerated timestamps and deployments', () => {
    const first = predictions();
    const regenerated = { ...first, generated_at: '2026-09-01T12:30:00Z' };
    assert.equal(notificationEventKey(first), '2026:15:post_fp');
    assert.equal(notificationEventKey(regenerated), notificationEventKey(first));
});
