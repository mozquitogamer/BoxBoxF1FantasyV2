'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { extractSnapshot, extractTeams, findTeams, officialGameDay } = require('../lib/f1-fantasy');
const { normalizeRound } = require('../api/members/team');

test('extractTeams accepts current-style leaderboard fields and de-duplicates teams', () => {
    const payload = {
        data: {
            users: [
                { user_guid: 'abc-123', team_name: 'Box Box Bot Beater', team_no: 2, manager_name: 'Example Person', total_points: 1234, rank: 9 },
                { user_guid: 'abc-123', team_name: 'Box Box Bot Beater', team_no: 2, manager_name: 'Example Person' },
            ],
        },
    };
    const teams = extractTeams(payload);
    assert.equal(teams.length, 1);
    assert.deepEqual(findTeams(teams, 'bot beat')[0], {
        id: 'abc-123', name: 'Box Box Bot Beater', slot: 2, manager: 'Example Person', points: 1234, rank: 9,
    });
});

test('extractSnapshot finds five drivers and two constructors', () => {
    const assets = [
        ...['A', 'B', 'C', 'D', 'E'].map((name, index) => ({ player_id: `d${index}`, player_name: name, player_type: 'driver', slot: index + 1 })),
        { team_id: 'c1', team_name: 'Ferrari', asset_type: 'constructor', slot: 1 },
        { team_id: 'c2', team_name: 'Mercedes', asset_type: 'constructor', slot: 2 },
    ];
    const link = { user_id: 'user', official_team_id: 'official', official_team_name: 'My Team', team_slot: 1 };
    const snapshot = extractSnapshot({ team_id: 'official', points: 240, lineup: assets }, link, 11);
    assert.equal(snapshot.round, 11);
    assert.equal(snapshot.assets.filter(item => item.asset_type === 'driver').length, 5);
    assert.equal(snapshot.assets.filter(item => item.asset_type === 'constructor').length, 2);
});

test('round validation rejects unsafe values', () => {
    assert.equal(normalizeRound(12), 12);
    assert.equal(normalizeRound('24'), 24);
    assert.equal(normalizeRound(0), null);
    assert.equal(normalizeRound('x'), null);
});

test('maps internal rounds around the two cancelled races', () => {
    assert.equal(officialGameDay(3), 3);
    assert.equal(officialGameDay(6), 4);
    assert.equal(officialGameDay(13), 11);
});
