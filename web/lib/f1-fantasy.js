'use strict';

const DEFAULT_ORIGIN = 'https://fantasy.formula1.com';
const DEFAULT_LEAGUE_ID = 160604;
const DEFAULT_LEAGUE_TYPE = 'public';

function required(value, name) {
    const result = String(value || '').trim();
    if (!result) throw new Error(`${name} is not configured`);
    return result;
}

function config() {
    return {
        origin: (process.env.F1_FANTASY_ORIGIN || DEFAULT_ORIGIN).replace(/\/$/, ''),
        sessionCookie: String(process.env.F1_FANTASY_SESSION_COOKIE || '').trim(),
        organiserUserId: required(process.env.F1_FANTASY_ORGANISER_USER_ID, 'F1_FANTASY_ORGANISER_USER_ID'),
        leagueId: Number(process.env.F1_FANTASY_LEAGUE_ID || DEFAULT_LEAGUE_ID),
        leagueType: process.env.F1_FANTASY_LEAGUE_TYPE === 'private' ? 'private' : DEFAULT_LEAGUE_TYPE,
    };
}

async function readResponse(response) {
    const text = await response.text();
    let data = text;
    try { data = text ? JSON.parse(text) : null; } catch (_) { /* keep text */ }
    if (!response.ok) {
        const error = new Error(data?.message || data?.error || `F1 Fantasy request failed (${response.status})`);
        error.status = response.status;
        throw error;
    }
    return data;
}

async function request(path) {
    const settings = config();
    const headers = {
        Accept: 'application/json, text/plain, */*',
        Referer: `${settings.origin}/en/leagues/leaderboard/${settings.leagueType}/${settings.leagueId}`,
        'User-Agent': 'BoxBoxF1Fantasy/1.0 (+https://boxboxf1fantasy.com)',
    };
    if (settings.sessionCookie) headers.Cookie = settings.sessionCookie;
    const response = await fetch(`${settings.origin}${path}`, {
        headers,
        redirect: 'manual',
        signal: AbortSignal.timeout(15000),
    });
    if (response.status >= 300 && response.status < 400) {
        throw new Error('The organiser F1 Fantasy session has expired. Refresh F1_FANTASY_SESSION_COOKIE.');
    }
    return readResponse(response);
}

function arrays(value) {
    if (Array.isArray(value)) return [value, ...value.flatMap(arrays)];
    if (!value || typeof value !== 'object') return [];
    return Object.values(value).flatMap(arrays);
}

function objects(value, found = []) {
    if (Array.isArray(value)) {
        value.forEach(item => objects(item, found));
    } else if (value && typeof value === 'object') {
        found.push(value);
        Object.values(value).forEach(item => objects(item, found));
    }
    return found;
}

function first(object, keys) {
    for (const key of keys) {
        const value = object?.[key];
        if (value !== undefined && value !== null && value !== '') return value;
    }
    return null;
}

function normalizeName(value) {
    return String(value || '').trim().replace(/\s+/g, ' ');
}

function candidateTeam(row) {
    const name = normalizeName(first(row, ['team_name', 'teamName', 'name', 'user_team_name', 'userTeamName', 'teamname', 'userteamname']));
    const id = String(first(row, [
        'user_guid', 'userGuid', 'user_id', 'userId', 'user_global_id', 'userGlobalId',
        'team_id', 'teamId', 'user_team_id', 'userTeamId', 'guid',
    ]) || '').trim();
    const slot = Number(first(row, ['team_no', 'teamNo', 'slot', 'team_slot', 'teamSlot']) || 0);
    const manager = normalizeName(first(row, ['manager_name', 'managerName', 'user_name', 'userName', 'fullname', 'full_name', 'username']));
    const points = Number(first(row, ['total_points', 'totalPoints', 'points', 'score', 'overall_points']) || 0);
    const rank = Number(first(row, ['rank', 'position', 'league_rank', 'leagueRank']) || 0);
    if (!name || !id) return null;
    return { id, name, slot: slot >= 1 && slot <= 3 ? slot : null, manager, points, rank, raw: row };
}

function extractTeams(payload) {
    const seen = new Set();
    const teams = [];
    for (const row of objects(payload)) {
        const team = candidateTeam(row);
        if (!team) continue;
        const key = `${team.id}:${team.slot || ''}`;
        if (seen.has(key)) continue;
        seen.add(key);
        teams.push(team);
    }
    return teams;
}

async function getLeagueLeaderboard() {
    const settings = config();
    const path = `/services/user/leaderboard/${encodeURIComponent(settings.organiserUserId)}/userrankgetv1/0/1/${settings.leagueType}/${settings.leagueId}?buster=${Date.now()}`;
    const payload = await request(path);
    return { payload, teams: extractTeams(payload), settings };
}

function safeTeam(team) {
    return {
        id: team.id,
        name: team.name,
        slot: team.slot,
        manager: team.manager,
        points: team.points,
        rank: team.rank,
    };
}

function findTeams(teams, query) {
    const needle = normalizeName(query).toLowerCase();
    if (needle.length < 2) return [];
    return teams.filter(team => `${team.name} ${team.manager}`.toLowerCase().includes(needle)).slice(0, 12).map(safeTeam);
}

function mapAsset(item, index) {
    const typeText = String(first(item, ['asset_type', 'assetType', 'type', 'player_type', 'playerType']) || '').toLowerCase();
    const constructor = /constructor|team/.test(typeText) || first(item, ['is_constructor', 'isConstructor']) === true;
    const name = normalizeName(first(item, ['display_name', 'displayName', 'full_name', 'fullName', 'name', 'player_name', 'playerName', 'team_name', 'teamName']));
    const id = String(first(item, ['asset_id', 'assetId', 'player_id', 'playerId', 'team_id', 'teamId', 'id']) || '').trim();
    if (!name || !id) return null;
    return {
        asset_type: constructor ? 'constructor' : 'driver',
        asset_id: id,
        name,
        slot: Number(first(item, ['slot', 'position', 'sequence']) || index + 1),
        is_boosted: Boolean(first(item, ['is_boosted', 'isBoosted', 'captain', 'is_captain', 'isCaptain'])),
    };
}

function extractSnapshot(payload, link, round) {
    const allObjects = objects(payload);
    const assetArrays = arrays(payload).filter(items => items.length >= 5 && items.length <= 12);
    let assets = [];
    for (const items of assetArrays) {
        const mapped = items.map(mapAsset).filter(Boolean);
        const drivers = mapped.filter(item => item.asset_type === 'driver').length;
        const constructors = mapped.filter(item => item.asset_type === 'constructor').length;
        if (mapped.length >= 7 && drivers >= 5 && constructors >= 2) { assets = mapped.slice(0, 8); break; }
    }
    const summary = allObjects.find(row => String(first(row, ['team_id', 'teamId', 'id']) || '') === String(link.official_team_id)) || allObjects[0] || {};
    return {
        user_id: link.user_id,
        official_team_id: link.official_team_id,
        season: 2026,
        round,
        team_slot: link.team_slot,
        official_team_name: link.official_team_name,
        manager_name: link.manager_name || null,
        fantasy_points: numberOrNull(first(summary, ['gameweek_points', 'gameWeekPoints', 'round_points', 'roundPoints', 'points', 'score'])),
        overall_points: numberOrNull(first(summary, ['overall_points', 'overallPoints', 'total_points', 'totalPoints'])),
        league_rank: numberOrNull(first(summary, ['league_rank', 'leagueRank', 'rank', 'position'])),
        overall_rank: numberOrNull(first(summary, ['overall_rank', 'overallRank', 'global_rank', 'globalRank'])),
        budget_millions: numberOrNull(first(summary, ['budget', 'budget_millions', 'budgetMillions', 'team_value', 'teamValue'])),
        free_transfers: numberOrNull(first(summary, ['free_transfers', 'freeTransfers', 'transfers_available', 'transfersAvailable'])),
        chip_code: normalizeName(first(summary, ['chip', 'chip_code', 'chipCode', 'booster', 'booster_name'])) || null,
        assets,
        captured_at: new Date().toISOString(),
    };
}

function numberOrNull(value) {
    const result = Number(value);
    return Number.isFinite(result) ? result : null;
}

function officialGameDay(internalRound) {
    const round = Number(internalRound);
    if (!Number.isInteger(round) || round < 1 || round > 24) throw new Error('Invalid internal F1 round.');
    return round - (round > 4 ? 1 : 0) - (round > 5 ? 1 : 0);
}

async function getOpponentSnapshot(link, round = 1) {
    const gameDay = officialGameDay(round);
    const payload = await request(`/services/user/opponentteam/opponentgamedayplayerteamget/1/${encodeURIComponent(link.official_team_id)}/${link.team_slot}/${gameDay}/1?buster=${Date.now()}`);
    return extractSnapshot(payload, link, round);
}

module.exports = {
    extractSnapshot,
    extractTeams,
    findTeams,
    getLeagueLeaderboard,
    getOpponentSnapshot,
    officialGameDay,
    safeTeam,
};
