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
    const entrantRows = (Array.isArray(teams) ? teams : [])
        .map(team => ({
            kind: 'entrant',
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
        ...entrantRows,
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
    cleanTeamName,
    loadV13Record,
    teamReference,
};
