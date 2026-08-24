'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
    buildConfirmedLeaderboardEntries,
    buildLeaderboard,
    cleanTeamName,
    loadV13Record,
    teamReference,
    v13RecordFromData,
} = require('../lib/beat-v13-leaderboard');

test('only confirmed entrants with a live linked team become public rows', () => {
    const result = buildConfirmedLeaderboardEntries([
        {
            id: 'pending', email_normalized: 'pending@example.com', status: 'pending',
            official_team_id: 'not-yet', official_team_name: 'Not Yet', official_team_slot: 1,
        },
        {
            id: 'confirmed-unlinked', email_normalized: 'private@example.com', status: 'confirmed',
        },
        {
            id: 'confirmed-linked', email_normalized: 'hidden@example.com', status: 'confirmed',
            official_team_id: 'official-1', official_team_name: 'Fast Team', official_team_slot: 2,
            manager_name: 'Private Manager',
        },
        {
            id: 'confirmed-not-visible', status: 'confirmed',
            official_team_id: 'official-2', official_team_name: 'Missing Feed Team', official_team_slot: 1,
        },
    ], [
        { id: 'official-1', slot: 2, name: 'Fast Team', points: 2700, rank: 4, manager: 'Private Manager' },
    ]);

    assert.equal(result.confirmed_count, 3);
    assert.equal(result.linked_count, 2);
    assert.equal(result.scored_count, 1);
    assert.deepEqual(result.teams, [{ id: 'official-1', slot: 2, name: 'Fast Team', points: 2700, rank: 4 }]);
    const publicRows = buildLeaderboard(result.teams, { points: 2541 });
    assert.equal(publicRows.some(row => row.team_name === 'Not Yet'), false);
    assert.equal(publicRows.some(row => row.team_name === 'Missing Feed Team'), false);
    assert.equal(JSON.stringify(publicRows).includes('@example.com'), false);
    assert.equal(JSON.stringify(publicRows).includes('Private Manager'), false);
});

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
    assert.equal(record.points, 2840);
    assert.equal(record.through_round, 14);
});

test('V13 leaderboard prefers scored live history over the research replay', () => {
    const record = v13RecordFromData({
        generated_at: '2026-08-24T12:00:00Z',
        research_replay: { total_points: 2594, end_round: 13 },
        live_status: { status: 'live', total_points: 2840, through_round: 14 },
        current_state: { as_of_round: 14 },
    });

    assert.deepEqual(record, {
        points: 2840,
        through_round: 14,
        updated_at: '2026-08-24T12:00:00Z',
    });
});

test('V13 leaderboard falls back to replay data before live scoring starts', () => {
    const record = v13RecordFromData({
        research_replay: { total_points: 2594, end_round: 13 },
        current_state: { as_of_round: 13 },
    });

    assert.equal(record.points, 2594);
    assert.equal(record.through_round, 13);
});
