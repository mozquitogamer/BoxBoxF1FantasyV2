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

test('decodes official F1 team names before display and exact-name search', () => {
    const payload = {
        leaderboard: [
            { user_guid: 'owner-1', team_name: 'Boxed%20In', team_no: 1, manager_name: 'Quintin%20Engelbrecht' },
        ],
    };
    const teams = extractTeams(payload);
    assert.equal(teams[0].name, 'Boxed In');
    assert.equal(teams[0].manager, 'Quintin Engelbrecht');
    assert.deepEqual(findTeams(teams, 'Boxed In').map(team => team.name), ['Boxed In']);
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

test('extractSnapshot accepts PascalCase drivers and constructors in separate sections', () => {
    const payload = {
        Data: {
            PlayerTeam: {
                Drivers: ['A', 'B', 'C', 'D', 'E'].map((name, index) => ({
                    PlayerId: `driver-${index}`,
                    PlayerName: name,
                    PositionName: 'Driver',
                    Position: index + 1,
                })),
                Constructors: [
                    { TeamId: 'team-1', TeamName: 'Ferrari', PositionName: 'Constructor', Position: 1 },
                    { TeamId: 'team-2', TeamName: 'Mercedes', PositionName: 'Constructor', Position: 2 },
                ],
            },
        },
    };
    const link = { user_id: 'user', official_team_id: 'official', official_team_name: 'My Team', team_slot: 1 };
    const snapshot = extractSnapshot(payload, link, 14);
    assert.equal(snapshot.assets.length, 7);
    assert.equal(snapshot.assets.filter(item => item.asset_type === 'driver').length, 5);
    assert.equal(snapshot.assets.filter(item => item.asset_type === 'constructor').length, 2);
});

test('extractSnapshot resolves the official seven-ID lineup through the public round roster', () => {
    const playerIds = ['18', '11059', '12', '129', '11051', '25', '23'];
    const payload = {
        Data: {
            Value: {
                userTeam: [{
                    teamname: 'Boxed%20In',
                    playerid: playerIds,
                    capplayerid: '18',
                    gdpoints: '123',
                    ovpoints: '987',
                    gdrank: '45',
                    ovrank: '6789',
                    teambal: '3.4',
                    usersubsleft: '2',
                }],
            },
        },
    };
    const roster = {
        Data: {
            Value: [
                ...playerIds.slice(0, 5).map((id, index) => ({
                    PlayerId: id,
                    PositionName: 'DRIVER',
                    FUllName: `Driver ${index + 1}`,
                })),
                { PlayerId: '25', PositionName: 'CONSTRUCTOR', FUllName: 'Ferrari' },
                { PlayerId: '23', PositionName: 'CONSTRUCTOR', FUllName: 'Alpine' },
            ],
        },
    };
    const link = { user_id: 'user', official_team_id: 'official', official_team_name: 'Boxed In', team_slot: 1 };
    const snapshot = extractSnapshot(payload, link, 14, roster);
    assert.equal(snapshot.assets.filter(item => item.asset_type === 'driver').length, 5);
    assert.equal(snapshot.assets.filter(item => item.asset_type === 'constructor').length, 2);
    assert.equal(snapshot.assets.find(item => item.asset_id === '18').is_boosted, true);
    assert.equal(snapshot.fantasy_points, 123);
    assert.equal(snapshot.overall_points, 987);
    assert.equal(snapshot.budget_millions, 3.4);
    assert.equal(snapshot.free_transfers, 2);
});

test('extractSnapshot refuses to turn an empty F1 response into a saved lineup', () => {
    const link = { user_id: 'user', official_team_id: 'official', official_team_name: 'My Team', team_slot: 1 };
    assert.throws(
        () => extractSnapshot({ Data: { PlayerTeam: [] } }, link, 14),
        error => error.code === 'F1_INCOMPLETE_LINEUP' && /saved team was not changed/i.test(error.message),
    );
});

test('extractSnapshot unwraps nested player records and recognizes constructor names', () => {
    const picked = [
        ...['A', 'B', 'C', 'D', 'E'].map((name, index) => ({ player: { id: `d${index}`, displayName: name } })),
        { player: { id: 'c1', displayName: 'Visa Cash App Racing Bulls' } },
        { player: { id: 'c2', displayName: 'Aston Martin Aramco F1 Team' } },
    ];
    const link = { user_id: 'user', official_team_id: 'official', official_team_name: 'My Team', team_slot: 1 };
    const snapshot = extractSnapshot({ PlayerTeam: { PickedPlayers: picked } }, link, 13);
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
