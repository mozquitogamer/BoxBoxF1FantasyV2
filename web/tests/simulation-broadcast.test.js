'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const {
    activeContactCount,
    auditResendSegments,
    broadcastName,
    buildBroadcast,
    phaseLabel,
} = require('../lib/simulation-broadcast');

function predictions() {
    return {
        race: 'Italian Grand Prix',
        round: 15,
        season: 2026,
        phase: 'pre_fp',
        drivers: [
            { driver_id: 'RUS', name: 'George Russell', expected_points: 22.1, predicted_finish: 2 },
            { driver_id: 'ANT', name: 'Kimi Antonelli', expected_points: 29.4, predicted_finish: 1 },
            { driver_id: 'HAM', name: 'Lewis Hamilton', expected_points: 22.5, predicted_finish: 5 },
            { driver_id: 'NOR', name: 'Lando Norris', expected_points: 20.9, predicted_finish: 3 },
        ],
        constructors: [
            { constructor_id: 'ferrari', name: 'Ferrari', expected_points: 56.7 },
            { constructor_id: 'mercedes', name: 'Mercedes', expected_points: 67.6 },
            { constructor_id: 'mclaren', name: 'McLaren', expected_points: 46.9 },
        ],
    };
}

test('builds the live Monza V13 broadcast with Resend unsubscribe handling', () => {
    const content = buildBroadcast(predictions(), 'https://boxboxf1fantasy.com');
    assert.equal(content.name, 'R15 Pre-practice simulation alert');
    assert.equal(content.subject, 'Italian Grand Prix simulations updated — Pre-practice');
    assert.match(content.html, /Kimi Antonelli/);
    assert.match(content.html, /Lewis Hamilton/);
    assert.match(content.html, /George Russell/);
    assert.match(content.html, /\{\{\{RESEND_UNSUBSCRIBE_URL\}\}\}/);
    assert.doesNotMatch(content.html, /postal address|Add sender/i);
    assert.match(content.text, /round_15_pre_fp/);
});

test('uses a deterministic name for idempotent provider lookup', () => {
    assert.equal(broadcastName(predictions()), 'R15 Pre-practice simulation alert');
    assert.equal(broadcastName(predictions(), 'run_123'), 'R15 Pre-practice simulation alert · resend run_123');
    assert.equal(phaseLabel('post_fp'), 'Post-practice');
});

test('counts only active contacts in the configured V13 segment', async () => {
    const originalFetch = global.fetch;
    global.fetch = async url => {
        assert.equal(url, 'https://api.resend.com/segments/segment_v13/contacts?limit=100');
        return {
            ok: true,
            json: async () => ({
                data: [
                    ...Array.from({ length: 6 }, (_, index) => ({ id: `active_${index}`, unsubscribed: false })),
                    { id: 'unsubscribed', unsubscribed: true },
                ],
            }),
        };
    };
    try {
        assert.equal(await activeContactCount('re_test', 'segment_v13'), 6);
    } finally {
        global.fetch = originalFetch;
    }
});

test('audits Resend segment names and counts without exposing contacts', async () => {
    const originalFetch = global.fetch;
    const previousEnv = { ...process.env };
    process.env.RESEND_API_KEY = 're_test';
    process.env.RESEND_FROM = 'Updates <updates@example.com>';
    process.env.RESEND_SIM_UPDATES_SEGMENT_ID = 'segment_v13';
    process.env.SUBSCRIPTION_SIGNING_SECRET = 'test_secret';
    global.fetch = async url => {
        if (url === 'https://api.resend.com/segments?limit=100') {
            return { ok: true, json: async () => ({ data: [{ id: 'default', name: 'Default' }] }) };
        }
        assert.equal(url, 'https://api.resend.com/segments/default/contacts?limit=100');
        return { ok: true, json: async () => ({ data: Array.from({ length: 6 }, (_, index) => ({ id: `contact_${index}` })) }) };
    };
    const response = {
        statusCode: null,
        payload: null,
        status(code) { this.statusCode = code; return this; },
        json(payload) { this.payload = payload; return this; },
    };
    try {
        await auditResendSegments(response);
        assert.equal(response.statusCode, 200);
        assert.deepEqual(response.payload, {
            ok: true,
            segments: [{ name: 'Default', active_contacts: 6 }],
        });
    } finally {
        global.fetch = originalFetch;
        process.env = previousEnv;
    }
});

test('automatically emails only when master publishes new simulation data', () => {
    const workflow = fs.readFileSync(
        path.join(__dirname, '..', '..', '.github', 'workflows', 'notify-paid-members.yml'),
        'utf8',
    );
    assert.match(workflow, /push:\s*[\s\S]*branches:\s*[\s\S]*- master/);
    assert.match(workflow, /paths:\s*[\s\S]*- web\/public\/data\/predictions\.json/);
    assert.match(workflow, /Wait for the exact simulation to reach production/);
    assert.match(workflow, /p\.season,p\.round,p\.phase,p\.generated_at/);
    assert.match(workflow, /Timed out waiting for the published simulation; no email was sent/);
    assert.match(workflow, /published_simulation/);
    assert.match(workflow, /workflow_dispatch:/);
    assert.match(workflow, /audit_only:/);
    assert.match(workflow, /force_resend:/);
    assert.match(workflow, /resend_token/);
});
