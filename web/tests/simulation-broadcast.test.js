'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const { broadcastName, buildBroadcast, phaseLabel } = require('../lib/simulation-broadcast');

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
    assert.equal(phaseLabel('post_fp'), 'Post-practice');
});
