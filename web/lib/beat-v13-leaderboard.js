'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const MAX_PUBLIC_TEAMS = 250;

function numberOrZero(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
}

function cleanTeamName(value) {
    return String(value || '').replace(/\s+/g, ' ').trim().slice(0, 100);
}

function firstValue(row, keys) {
    if (!row || typeof row !== 'object') return null;
    for (const key of keys) {
        const value = row[key];
        if (value !== undefined && value !== null && value !== '') return value;
    }
    return null;
}

function integerOrNull(value, minimum = 1) {
    const number = Number(value);
    return Number.isInteger(number) && number >= minimum ? number : null;
}

function normalizeEntrant(entry) {
    const row = entry && typeof entry === 'object' ? entry : {};
    const status = String(firstValue(row, ['status', 'entry_status', 'registration_status']) || '').trim().toLowerCase();
    const confirmedAt = firstValue(row, ['confirmed_at', 'confirmedAt', 'email_confirmed_at', 'verified_at', 'registered_at']);
    const confirmed = Boolean(confirmedAt)
        || ['confirmed', 'verified'].includes(status);

    const officialTeamId = String(firstValue(row, [
        'official_team_id', 'officialTeamId', 'f1_team_id', 'f1TeamId', 'team_id', 'teamId',
    ]) || '').trim();
    const officialTeamName = cleanTeamName(firstValue(row, [
        'official_team_name', 'officialTeamName', 'f1_team_name', 'f1TeamName', 'team_name', 'teamName',
    ]));
    const teamSlot = integerOrNull(firstValue(row, [
        'official_team_slot', 'officialTeamSlot', 'f1_team_slot', 'f1TeamSlot', 'team_slot', 'teamSlot', 'slot',
    ]));
    const linkStatus = String(firstValue(row, ['team_link_status', 'teamLinkStatus', 'f1_team_status', 'f1TeamStatus']) || 'active').toLowerCase();
    const linked = Boolean(officialTeamId && officialTeamName && teamSlot && teamSlot <= 3)
        && ['active'].includes(linkStatus);

    return {
        id: String(firstValue(row, ['id', 'entry_id', 'entryId']) || '').trim(),
        confirmed,
        linked,
        official_team_id: officialTeamId,
        official_team_name: officialTeamName,
        team_slot: teamSlot,
    };
}

function normalizeFeedTeam(team) {
    const row = team && typeof team === 'object' ? team : {};
    const id = String(firstValue(row, ['id', 'team_id', 'teamId', 'official_team_id']) || '').trim();
    const name = cleanTeamName(firstValue(row, ['name', 'team_name', 'teamName', 'official_team_name']));
    const slot = integerOrNull(firstValue(row, ['slot', 'team_slot', 'teamSlot']));
    if (!id || !name || !slot || slot > 3) return null;
    return {
        id,
        name,
        slot,
        points: numberOrZero(firstValue(row, [
            'points', 'overall_points', 'overallPoints', 'total_points', 'totalPoints', 'ovpoints', 'ovPoints',
        ])),
        rank: integerOrNull(firstValue(row, [
            'rank', 'league_rank', 'leagueRank', 'overall_rank', 'overallRank', 'ovrank', 'ovRank',
        ])),
    };
}

function matchFeedTeam(entrant, feedTeams) {
    const normalized = normalizeEntrant(entrant);
    if (!normalized.linked) return null;
    const teams = (Array.isArray(feedTeams) ? feedTeams : []).map(normalizeFeedTeam).filter(Boolean);
    const exactId = teams.find(team => team.id === normalized.official_team_id && team.slot === normalized.team_slot);
    if (exactId) return exactId;
    const normalizedName = normalized.official_team_name.toLowerCase();
    return teams.find(team => team.slot === normalized.team_slot && team.name.toLowerCase() === normalizedName) || null;
}

/**
 * Convert private entrant rows plus the public F1 feed into public board rows.
 * This is deliberately the only place where entry rows become leaderboard
 * rows: email, manager names, and internal user identifiers never cross this
 * boundary. The caller can use the counts to explain the provisional board.
 */
function buildConfirmedLeaderboardEntries(entries, feedTeams) {
    const all = (Array.isArray(entries) ? entries : []).map(normalizeEntrant);
    const confirmed = all.filter(entry => entry.confirmed);
    const linked = confirmed.filter(entry => entry.linked);
    const scored = linked.map(entry => ({ entry, team: matchFeedTeam(entry, feedTeams) })).filter(item => item.team);
    const seenTeams = new Set();
    const teams = scored.map(({ entry, team }) => ({
        id: team.id || entry.official_team_id,
        slot: team.slot || entry.team_slot,
        name: team.name || entry.official_team_name,
        points: team.points,
        rank: team.rank,
    })).filter(team => {
        const key = `${team.id}:${team.slot}`;
        if (seenTeams.has(key)) return false;
        seenTeams.add(key);
        return true;
    });
    return {
        teams,
        confirmed_count: confirmed.length,
        linked_count: linked.length,
        scored_count: scored.length,
    };
}

function teamReference(team) {
    return crypto.createHash('sha256')
        .update(`${String(team.id || '')}:${Number(team.slot || 0)}`)
        .digest('hex')
        .slice(0, 24);
}

function assignRanks(rows) {
    let previousPoints = null;
    let previousRank = 0;
    return rows.map((row, index) => {
        const rank = previousPoints === row.points ? previousRank : index + 1;
        previousPoints = row.points;
        previousRank = rank;
        return { ...row, rank };
    });
}

function buildLeaderboard(teams, v13Record) {
    const v13Points = numberOrZero(v13Record?.points);
    const communityRows = (Array.isArray(teams) ? teams : [])
        .map(team => ({
            kind: 'community',
            team_ref: teamReference(team),
            team_name: cleanTeamName(team.name),
            points: numberOrZero(team.points),
            official_league_rank: Number.isFinite(Number(team.rank)) && Number(team.rank) > 0
                ? Number(team.rank)
                : null,
        }))
        .filter(team => team.team_name)
        .sort((left, right) => right.points - left.points || left.team_name.localeCompare(right.team_name))
        .slice(0, MAX_PUBLIC_TEAMS);

    const ranked = assignRanks([
        ...communityRows,
        {
            kind: 'v13',
            team_ref: 'v13',
            team_name: 'V13',
            points: v13Points,
            official_league_rank: null,
        },
    ].sort((left, right) => right.points - left.points || left.team_name.localeCompare(right.team_name)));

    return ranked.map(row => ({
        ...row,
        margin_vs_v13: row.kind === 'v13' ? 0 : row.points - v13Points,
    }));
}

function loadV13Record() {
    const filePath = path.join(__dirname, '..', 'public', 'data', 'v13_manager.json');
    const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    return {
        points: numberOrZero(data?.research_replay?.total_points),
        through_round: Number(data?.research_replay?.end_round || data?.current_state?.as_of_round || 0),
        updated_at: data?.generated_at || null,
    };
}

module.exports = {
    MAX_PUBLIC_TEAMS,
    buildLeaderboard,
    buildConfirmedLeaderboardEntries,
    cleanTeamName,
    loadV13Record,
    matchFeedTeam,
    normalizeEntrant,
    normalizeFeedTeam,
    teamReference,
};
