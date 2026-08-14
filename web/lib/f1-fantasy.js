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

function arrayEntries(value, path = [], found = []) {
    if (Array.isArray(value)) {
        found.push({ items: value, path });
        value.forEach((item, index) => arrayEntries(item, [...path, String(index)], found));
    } else if (value && typeof value === 'object') {
        Object.entries(value).forEach(([key, item]) => arrayEntries(item, [...path, key], found));
    }
    return found;
}

function payloadShape(value, path = 'root', found = [], depth = 0) {
    if (depth > 5 || found.length >= 80) return found;
    if (Array.isArray(value)) {
        found.push({ path, kind: 'array', length: value.length });
        value.slice(0, 2).forEach((item, index) => payloadShape(item, `${path}[${index}]`, found, depth + 1));
    } else if (value && typeof value === 'object') {
        const keys = Object.keys(value).slice(0, 40);
        found.push({ path, kind: 'object', keys });
        keys.forEach(key => payloadShape(value[key], `${path}.${key}`, found, depth + 1));
    }
    return found;
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
    if (!object || typeof object !== 'object') return null;
    const wanted = new Set(keys.map(key => String(key).toLowerCase().replace(/[^a-z0-9]/g, '')));
    for (const [key, value] of Object.entries(object)) {
        const canonical = key.toLowerCase().replace(/[^a-z0-9]/g, '');
        if (wanted.has(canonical) && value !== undefined && value !== null && value !== '') return value;
    }
    return null;
}

function normalizeName(value) {
    let text = String(value || '').trim();
    try {
        text = decodeURIComponent(text);
    } catch (_) {
        // Keep malformed third-party text readable instead of rejecting the row.
    }
    return text.replace(/\s+/g, ' ');
}

function candidateTeam(row) {
    const name = normalizeName(first(row, ['team_name', 'teamName', 'name', 'user_team_name', 'userTeamName', 'teamname', 'userteamname']));
    const id = String(first(row, [
        'user_guid', 'userGuid', 'user_id', 'userId', 'user_global_id', 'userGlobalId',
        'team_id', 'teamId', 'user_team_id', 'userTeamId', 'guid',
    ]) || '').trim();
    const slot = Number(first(row, ['team_no', 'teamNo', 'slot', 'team_slot', 'teamSlot']) || 0);
    const manager = normalizeName(first(row, ['manager_name', 'managerName', 'user_name', 'userName', 'fullname', 'full_name', 'username']));
    const points = Number(first(row, [
        'total_points', 'totalPoints', 'points', 'score', 'overall_points', 'overallPoints',
        'ovpoints', 'ovPoints', 'overallpoints', 'cur_points', 'curPoints',
    ]) || 0);
    const rank = Number(first(row, [
        'rank', 'position', 'league_rank', 'leagueRank', 'ovrank', 'ovRank', 'overall_rank', 'overallRank',
        'cur_rank', 'curRank',
    ]) || 0);
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

const CONSTRUCTOR_NAMES = new Set([
    'alpine', 'aston martin', 'audi', 'cadillac', 'ferrari', 'haas', 'mclaren',
    'mercedes', 'racing bulls', 'red bull', 'red bull racing', 'williams',
]);

function booleanValue(value) {
    if (value === true || value === 1 || value === '1') return true;
    if (value === false || value === 0 || value === '0') return false;
    const text = String(value || '').toLowerCase();
    if (text === 'true' || text === 'yes') return true;
    if (text === 'false' || text === 'no') return false;
    return null;
}

function constructorName(name) {
    const raw = normalizeName(name).toLowerCase();
    if ([...CONSTRUCTOR_NAMES].some(team => raw === team || raw.includes(team))) return true;
    const normalized = raw
        .replace(/\b(f1|formula one|formula 1|racing|team|scuderia|oracle|mastercard|atlassian|revolut|bwt|tgr|visa cash app|aramco|hp)\b/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
    return [...CONSTRUCTOR_NAMES].some(team => normalized === team || normalized.includes(team));
}

function mapAsset(item, index, path = []) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return null;
    const nested = first(item, ['player', 'driver', 'constructor', 'asset', 'details']);
    const detail = nested && typeof nested === 'object' && !Array.isArray(nested) ? nested : {};
    const read = keys => first(item, keys) ?? first(detail, keys);
    const typeText = String(read([
        'asset_type', 'type', 'player_type', 'position_type', 'position_name', 'role', 'category',
    ]) || '').toLowerCase();
    const pathText = path.join(' ').toLowerCase();
    const constructorPath = path.some(segment => /constructor/i.test(segment) || /^teams?$/i.test(segment));
    const driverPath = path.some(segment => /driver/i.test(segment));
    const name = normalizeName(read([
        'player_name', 'driver_name', 'constructor_name', 'display_name', 'full_name', 'short_name', 'name', 'team_name',
    ]));
    const id = String(read([
        'player_id', 'driver_id', 'constructor_id', 'asset_id', 'team_id', 'id',
    ]) || '').trim();
    if (!name || !id) return null;
    const selected = booleanValue(read(['is_selected', 'selected', 'is_picked', 'picked', 'is_in_team', 'in_team']));
    if (selected === false) return null;
    const explicitConstructor = booleanValue(read(['is_constructor'])) === true;
    const explicitDriver = booleanValue(read(['is_driver'])) === true;
    let assetType = null;
    if (/constructor|team/.test(typeText) || explicitConstructor) assetType = 'constructor';
    else if (/driver|racer/.test(typeText) || explicitDriver) assetType = 'driver';
    else if (constructorName(name)) assetType = 'constructor';
    else if (constructorPath) assetType = 'constructor';
    else if (driverPath) assetType = 'driver';
    return {
        asset_type: assetType,
        asset_id: id,
        name,
        slot: Number(read(['slot', 'position', 'sequence']) || index + 1),
        is_boosted: Boolean(read(['is_boosted', 'captain', 'is_captain'])),
    };
}

function uniqueAssets(items) {
    const seen = new Set();
    return items.filter(item => {
        const key = `${item.asset_type}:${item.asset_id}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
    });
}

function extractAssets(payload) {
    const candidates = arrayEntries(payload).map(({ items, path }) => {
        let mapped = items.map((item, index) => mapAsset(item, index, path)).filter(Boolean);
        const known = mapped.filter(item => item.asset_type);
        const knownDrivers = known.filter(item => item.asset_type === 'driver').length;
        const knownConstructors = known.filter(item => item.asset_type === 'constructor').length;
        if (mapped.length === 7 && knownDrivers === 0 && knownConstructors === 2) {
            mapped = mapped.map(item => item.asset_type ? item : { ...item, asset_type: 'driver' });
        }
        if (mapped.length === 7 && knownDrivers === 5 && knownConstructors === 0) {
            mapped = mapped.map(item => item.asset_type ? item : { ...item, asset_type: 'constructor' });
        }
        if (!known.length && mapped.length === 5) mapped = mapped.map(item => ({ ...item, asset_type: 'driver' }));
        if (!known.length && mapped.length === 2) mapped = mapped.map(item => ({ ...item, asset_type: 'constructor' }));

        const pathText = path.join(' ').toLowerCase();
        const score = (/lineup|picked|selection|playerteam|squad/.test(pathText) ? 20 : 0)
            + (mapped.length === 7 ? 10 : 0)
            + mapped.filter(item => item.asset_type).length;
        return { mapped: uniqueAssets(mapped), score };
    }).filter(candidate => candidate.mapped.length);

    const complete = candidates
        .filter(({ mapped }) => mapped.filter(item => item.asset_type === 'driver').length >= 5
            && mapped.filter(item => item.asset_type === 'constructor').length >= 2)
        .sort((a, b) => b.score - a.score)[0];
    if (complete) {
        return [
            ...complete.mapped.filter(item => item.asset_type === 'driver').slice(0, 5),
            ...complete.mapped.filter(item => item.asset_type === 'constructor').slice(0, 2),
        ];
    }

    const driverSet = candidates
        .filter(({ mapped }) => mapped.filter(item => item.asset_type === 'driver').length >= 5)
        .sort((a, b) => b.score - a.score)[0];
    const constructorSet = candidates
        .filter(({ mapped }) => mapped.filter(item => item.asset_type === 'constructor').length >= 2)
        .sort((a, b) => b.score - a.score)[0];
    if (!driverSet || !constructorSet) return [];
    return uniqueAssets([
        ...driverSet.mapped.filter(item => item.asset_type === 'driver').slice(0, 5),
        ...constructorSet.mapped.filter(item => item.asset_type === 'constructor').slice(0, 2),
    ]);
}

function rosterByPlayerId(payload) {
    const byId = new Map();
    for (const row of objects(payload)) {
        const asset = mapAsset(row, 0);
        if (!asset?.asset_type) continue;
        const ids = [
            asset.asset_id,
            first(row, ['F1PlayerId', 'f1_player_id', 'f1PlayerId']),
            first(row, ['TeamId', 'team_id', 'teamId']),
        ].filter(value => value !== null && value !== undefined && value !== '').map(String);
        for (const key of new Set(ids)) {
            const existing = byId.get(key) || [];
            existing.push(asset);
            byId.set(key, existing);
        }
    }
    return byId;
}

function extractIdLineup(payload, rosterPayload) {
    if (!rosterPayload) return [];
    const team = objects(payload).find(row => {
        const ids = first(row, ['playerid', 'player_id', 'playerIds', 'player_ids']);
        return Array.isArray(ids) && ids.length === 7;
    });
    if (!team) return [];

    const entries = first(team, ['playerid', 'player_id', 'playerIds', 'player_ids']);
    const roster = rosterByPlayerId(rosterPayload);
    const captainId = String(first(team, ['capplayerid', 'captainPlayerId', 'captain_id']) || '');
    const typeSlots = { driver: 0, constructor: 0 };
    const assets = entries.map((entry, index) => {
        const record = entry && typeof entry === 'object' ? entry : null;
        const id = record ? first(record, ['id', 'playerid', 'player_id', 'PlayerId']) : entry;
        const position = Number(record ? first(record, ['playerpostion', 'playerposition', 'player_position', 'position']) : index + 1);
        const choices = roster.get(String(id)) || [];
        const expectedType = position >= 6 ? 'constructor' : 'driver';
        const match = choices.find(item => item.asset_type === expectedType) || choices[0];
        if (!match) return null;
        typeSlots[match.asset_type] += 1;
        return {
            ...match,
            slot: expectedType === 'driver' ? position : position - 5,
            is_boosted: booleanValue(record ? first(record, ['iscaptain', 'is_captain', 'captain']) : null) === true
                || String(id) === captainId,
        };
    }).filter(Boolean);
    return uniqueAssets(assets);
}

function extractSnapshot(payload, link, round, rosterPayload = null) {
    const allObjects = objects(payload);
    let assets = extractAssets(payload);
    if (assets.filter(item => item.asset_type === 'driver').length !== 5
        || assets.filter(item => item.asset_type === 'constructor').length !== 2) {
        assets = extractIdLineup(payload, rosterPayload);
    }
    const drivers = assets.filter(item => item.asset_type === 'driver').length;
    const constructors = assets.filter(item => item.asset_type === 'constructor').length;
    if (drivers !== 5 || constructors !== 2) {
        const teamIds = allObjects.find(row => Array.isArray(first(row, ['playerid', 'player_id', 'playerIds', 'player_ids'])));
        const roster = rosterPayload ? rosterByPlayerId(rosterPayload) : new Map();
        console.warn('[f1-sync] lineup ID resolution failed', JSON.stringify({
            teamIdCount: (first(teamIds, ['playerid', 'player_id', 'playerIds', 'player_ids']) || []).length,
            rosterKeyCount: roster.size,
        }));
        const error = new Error(`F1 Fantasy returned an incomplete lineup (${drivers} drivers and ${constructors} constructors). Your saved team was not changed.`);
        error.code = 'F1_INCOMPLETE_LINEUP';
        throw error;
    }
    const summary = allObjects.find(row => Array.isArray(first(row, ['playerid', 'player_id', 'playerIds', 'player_ids'])))
        || allObjects.find(row => String(first(row, ['team_id', 'teamId', 'id']) || '') === String(link.official_team_id))
        || allObjects[0]
        || {};
    return {
        user_id: link.user_id,
        official_team_id: link.official_team_id,
        season: 2026,
        round,
        team_slot: link.team_slot,
        official_team_name: link.official_team_name,
        manager_name: link.manager_name || null,
        fantasy_points: numberOrNull(first(summary, ['gdpoints', 'gameweek_points', 'gameWeekPoints', 'round_points', 'roundPoints', 'points', 'score'])),
        overall_points: numberOrNull(first(summary, ['ovpoints', 'overall_points', 'overallPoints', 'total_points', 'totalPoints'])),
        league_rank: numberOrNull(first(summary, ['gdrank', 'league_rank', 'leagueRank', 'rank', 'position'])),
        overall_rank: numberOrNull(first(summary, ['ovrank', 'overall_rank', 'overallRank', 'global_rank', 'globalRank'])),
        budget_millions: numberOrNull(first(summary, ['teambal', 'budget', 'budget_millions', 'budgetMillions', 'team_value', 'teamValue'])),
        free_transfers: numberOrNull(first(summary, ['usersubsleft', 'userSubsleft', 'free_transfers', 'freeTransfers', 'transfers_available', 'transfersAvailable'])),
        chip_code: normalizeName(first(summary, ['boosterid', 'chip', 'chip_code', 'chipCode', 'booster', 'booster_name'])) || null,
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
    let rosterPayload = null;
    try {
        rosterPayload = await request(`/feeds/drivers/${gameDay}_en.json?buster=${Date.now()}`);
    } catch (error) {
        console.warn('[f1-sync] roster feed unavailable', JSON.stringify({ round, gameDay, message: error.message }));
    }
    try {
        return extractSnapshot(payload, link, round, rosterPayload);
    } catch (error) {
        if (error.code === 'F1_INCOMPLETE_LINEUP') {
            console.warn('[f1-sync] incomplete response shape', JSON.stringify({ round, gameDay, shape: payloadShape(payload) }));
        }
        throw error;
    }
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
