'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
    extractSnapshot,
    extractTeams,
    findGlobalTeams,
    findLeagueTeams,
    findTeams,
    getOpponentSnapshot,
    getPublicLeagueSnapshot,
    officialGameDay,
} = require('../lib/f1-fantasy');
const { createTeamLinkToken, normalizeRound, verifyTeamLinkToken } = require('../api/members/team');

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

test('extractTeams accepts the compact official overall-points fields', () => {
    const teams = extractTeams({
        leaderboard: [{ user_guid: 'owner-2', teamname: 'Margin Call', team_no: 1, ovpoints: 2548, ovrank: 17 }],
    });
    assert.equal(teams[0].points, 2548);
    assert.equal(teams[0].rank, 17);
});

test('extractTeams accepts the current league points and rank fields', () => {
    const teams = extractTeams({
        leaderboard: [{ user_guid: 'owner-3', team_name: 'Boxed In', team_no: 1, cur_points: 2412, cur_rank: 9 }],
    });
    assert.equal(teams[0].points, 2412);
    assert.equal(teams[0].rank, 9);
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

test('extractSnapshot accepts alternate F1 player IDs used by team responses', () => {
    const playerIds = ['8', '1059', '2', '29', '1051', '5', '3'];
    const payload = { Data: { Value: { userTeam: [{ playerid: playerIds }] } } };
    const roster = {
        Data: {
            Value: [
                ...playerIds.slice(0, 5).map((id, index) => ({
                    PlayerId: `primary-${index}`,
                    F1PlayerId: id,
                    PositionName: 'DRIVER',
                    FUllName: `Driver ${index + 1}`,
                })),
                { PlayerId: '25', F1PlayerId: '5', TeamId: '25', PositionName: 'CONSTRUCTOR', FUllName: 'Ferrari' },
                { PlayerId: '23', F1PlayerId: '3', TeamId: '23', PositionName: 'CONSTRUCTOR', FUllName: 'Alpine' },
            ],
        },
    };
    const link = { user_id: 'user', official_team_id: 'official', official_team_name: 'My Team', team_slot: 1 };
    const snapshot = extractSnapshot(payload, link, 14, roster);
    assert.equal(snapshot.assets.filter(item => item.asset_type === 'driver').length, 5);
    assert.equal(snapshot.assets.filter(item => item.asset_type === 'constructor').length, 2);
});

test('extractSnapshot parses the live F1 player record array and explicit positions', () => {
    const entries = [
        { id: '11032', playerpostion: 2, iscaptain: 0 },
        { id: '11051', playerpostion: 4, iscaptain: 0 },
        { id: '111', playerpostion: 5, iscaptain: 0 },
        { id: '11149', playerpostion: 3, iscaptain: 0 },
        { id: '115', playerpostion: 1, iscaptain: 1 },
        { id: '25', playerpostion: 7, iscaptain: 0 },
        { id: '28', playerpostion: 6, iscaptain: 0 },
    ];
    const roster = {
        Data: {
            Value: [
                ...entries.slice(0, 5).map((entry, index) => ({
                    PlayerId: entry.id,
                    PositionName: 'DRIVER',
                    FUllName: `Driver ${index + 1}`,
                })),
                { PlayerId: '25', PositionName: 'CONSTRUCTOR', FUllName: 'Ferrari' },
                { PlayerId: '28', PositionName: 'CONSTRUCTOR', FUllName: 'McLaren' },
            ],
        },
    };
    const payload = { Data: { Value: { userTeam: [{ playerid: entries }] } } };
    const link = { user_id: 'user', official_team_id: 'official', official_team_name: 'Boxed In', team_slot: 1 };
    const snapshot = extractSnapshot(payload, link, 14, roster);
    assert.equal(snapshot.assets.filter(item => item.asset_type === 'driver').length, 5);
    assert.equal(snapshot.assets.filter(item => item.asset_type === 'constructor').length, 2);
    assert.equal(snapshot.assets.find(item => item.asset_id === '115').slot, 1);
    assert.equal(snapshot.assets.find(item => item.asset_id === '115').is_boosted, true);
    assert.equal(snapshot.assets.find(item => item.asset_id === '28').slot, 1);
});

test('extractSnapshot resolves the public league user_team array and ignores extra feed IDs', () => {
    const lineup = ['115', '11032', '11149', '11051', '111', '28', '25', 'unused'];
    const roster = {
        Data: {
            Value: [
                ...lineup.slice(0, 5).map((id, index) => ({
                    PlayerId: id,
                    PositionName: 'DRIVER',
                    FUllName: `Driver ${index + 1}`,
                })),
                { PlayerId: '28', PositionName: 'CONSTRUCTOR', FUllName: 'McLaren' },
                { PlayerId: '25', PositionName: 'CONSTRUCTOR', FUllName: 'Ferrari' },
                { PlayerId: 'unused', PositionName: 'DRIVER', FUllName: 'Extra Driver' },
            ],
        },
    };
    const payload = {
        leaderboard: [{
            user_guid: 'owner',
            team_name: 'Boxed%20In',
            team_no: 1,
            user_team: lineup,
            cur_points: 2048,
            cur_rank: 12,
        }],
    };
    const link = { user_id: 'member', official_team_id: 'owner', official_team_name: 'Boxed In', team_slot: 1 };
    const snapshot = extractSnapshot(payload, link, 14, roster);
    assert.equal(snapshot.assets.length, 7);
    assert.equal(snapshot.assets.filter(item => item.asset_type === 'driver').length, 5);
    assert.equal(snapshot.assets.filter(item => item.asset_type === 'constructor').length, 2);
    assert.equal(snapshot.overall_points, 2048);
    assert.equal(snapshot.league_rank, 12);
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

test('official-team discovery uses exact name only across public F1 lists', async () => {
    const originalFetch = global.fetch;
    const requested = [];
    global.fetch = async url => {
        requested.push(String(url));
        const leaderboard = String(url).includes('/publicleague/')
            ? [{ user_guid: 'league-user', team_name: 'Boxed%20In', team_no: 1, manager_name: 'League Manager', cur_rank: 12 }]
            : [
                { user_guid: 'global-user', team_name: 'Boxed In', team_no: 2, manager_name: 'Global Manager', ovrank: 8 },
                { user_guid: 'near-user', team_name: 'Boxed Inside', team_no: 1, manager_name: 'Near Match', ovrank: 9 },
            ];
        return new Response(JSON.stringify({ leaderboard }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
        });
    };
    try {
        const teams = await findGlobalTeams('Boxed In');
        assert.deepEqual(teams.map(team => team.id), ['global-user', 'league-user']);
        assert.equal(requested.length, 2);
        assert.ok(requested.every(url => url.includes('/feeds/leaderboard/')));
        assert.ok(requested.every(url => !url.includes('/services/user/leaderboard/')));
    } finally {
        global.fetch = originalFetch;
    }
});

test('league connection and lineup refresh use only unauthenticated public feeds', async () => {
    const originalFetch = global.fetch;
    const previousCookie = process.env.F1_FANTASY_SESSION_COOKIE;
    process.env.F1_FANTASY_SESSION_COOKIE = 'secret-cookie-that-must-not-be-sent';
    const requests = [];
    const playerIds = ['115', '11032', '11149', '11051', '111', '28', '25'];
    global.fetch = async (url, options = {}) => {
        requests.push({ url: String(url), headers: options.headers || {} });
        const payload = String(url).includes('/feeds/drivers/')
            ? {
                Data: {
                    Value: [
                        ...playerIds.slice(0, 5).map((id, index) => ({ PlayerId: id, PositionName: 'DRIVER', FUllName: `Driver ${index + 1}` })),
                        { PlayerId: '28', PositionName: 'CONSTRUCTOR', FUllName: 'McLaren' },
                        { PlayerId: '25', PositionName: 'CONSTRUCTOR', FUllName: 'Ferrari' },
                    ],
                },
            }
            : {
                Value: {
                    leaderboard: [{
                        user_guid: 'league-owner',
                        team_name: 'Boxed%20In',
                        team_no: 1,
                        user_name: 'League Manager',
                        user_team: playerIds,
                        cur_points: 2048,
                        cur_rank: 12,
                    }],
                },
            };
        return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });
    };
    try {
        const found = await findLeagueTeams('Boxed In');
        assert.deepEqual(found.map(team => team.id), ['league-owner']);
        const result = await getPublicLeagueSnapshot({
            user_id: 'member',
            official_team_id: 'league-owner',
            official_team_name: 'Boxed In',
            team_slot: 1,
        }, 14);
        assert.equal(result.source, 'public_league');
        assert.equal(result.snapshot.assets.length, 7);
        assert.ok(requests.every(request => !request.headers.Cookie));
        assert.ok(requests.every(request => request.url.includes('/feeds/')));
    } finally {
        global.fetch = originalFetch;
        if (previousCookie === undefined) delete process.env.F1_FANTASY_SESSION_COOKIE;
        else process.env.F1_FANTASY_SESSION_COOKIE = previousCookie;
    }
});

test('official-team link selections are signed, member-bound and short-lived', () => {
    const previous = process.env.SUBSCRIPTION_SIGNING_SECRET;
    process.env.SUBSCRIPTION_SIGNING_SECRET = 'test-only-team-link-secret';
    try {
        const team = { id: 'official-guid', name: 'Boxed In', manager: 'Example', slot: 1, rank: 102 };
        const token = createTeamLinkToken(team, 'member-one', 1_000);
        assert.equal(verifyTeamLinkToken(token, 'member-one', 2_000).id, 'official-guid');
        assert.equal(verifyTeamLinkToken(token, 'member-two', 2_000), null);
        assert.equal(verifyTeamLinkToken(`${token}x`, 'member-one', 2_000), null);
        assert.equal(verifyTeamLinkToken(token, 'member-one', 1_000 + 11 * 60 * 1000), null);

        const unrankedToken = createTeamLinkToken({ ...team, rank: null }, 'member-one', 1_000);
        assert.equal(verifyTeamLinkToken(unrankedToken, 'member-one', 2_000).rank, null);
    } finally {
        if (previous === undefined) delete process.env.SUBSCRIPTION_SIGNING_SECRET;
        else process.env.SUBSCRIPTION_SIGNING_SECRET = previous;
    }
});

test('expired F1 access is reported as a temporary sync issue without blocking manual advisor use', async () => {
    const originalFetch = global.fetch;
    global.fetch = async () => new Response(JSON.stringify({ message: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
    });
    try {
        await assert.rejects(
            () => getOpponentSnapshot({ official_team_id: 'opponent', official_team_name: 'Boxed In', team_slot: 1, user_id: 'member' }, 14),
            error => error.code === 'F1_SESSION_EXPIRED'
                && /still fill, save and use the Transfer Advisor manually/i.test(error.message),
        );
    } finally {
        global.fetch = originalFetch;
    }
});
