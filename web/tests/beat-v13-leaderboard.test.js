'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
    buildLeaderboard,
    cleanTeamName,
    loadV13Record,
    teamReference,
} = require('../lib/beat-v13-leaderboard');

test('buildLeaderboard combines official teams with V13 and calculates margins', () => {
    const rows = buildLeaderboard([
        { id: 'alpha', slot: 1, name: 'Fast Team', points: 2700, rank: 1, manager: 'Private Manager' },
        { id: 'beta', slot: 2, name: 'Chasing Team', points: 2500, rank: 2, manager: 'Another Manager' },
    ], { points: 2541 });

    assert.deepEqual(rows.map(row => [row.rank, row.team_name, row.points]), [
        [1, 'Fast Team', 2700],
        [2, 'V13', 2541],
        [3, 'Chasing Team', 2500],
    ]);
    assert.equal(rows[0].margin_vs_v13, 159);
    assert.equal(rows[2].margin_vs_v13, -41);
    assert.equal(rows[0].kind, 'community');
    assert.equal('manager' in rows[0], false);
});

test('buildLeaderboard gives tied scores the same displayed rank', () => {
    const rows = buildLeaderboard([
        { id: 'alpha', slot: 1, name: 'Alpha', points: 2541 },
        { id: 'beta', slot: 1, name: 'Beta', points: 2500 },
    ], { points: 2541 });
    assert.deepEqual(rows.map(row => row.rank), [1, 1, 3]);
});

test('public team references are stable, opaque, and slot-specific', () => {
    const first = teamReference({ id: 'official-id', slot: 1 });
    assert.equal(first, teamReference({ id: 'official-id', slot: 1 }));
    assert.notEqual(first, teamReference({ id: 'official-id', slot: 2 }));
    assert.equal(first.includes('official-id'), false);
});

test('team names are normalized and bounded', () => {
    assert.equal(cleanTeamName('  Boxed   In  '), 'Boxed In');
    assert.equal(cleanTeamName('x'.repeat(140)).length, 100);
});

test('loads the published V13 full-season record', () => {
    const record = loadV13Record();
    assert.ok(record.points > 0);
    assert.ok(record.through_round >= 1);
});
