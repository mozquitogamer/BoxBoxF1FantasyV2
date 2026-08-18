'use strict';

const { getConfig } = require('../../lib/email-subscriptions');
const { buildLeaderboard, loadV13Record } = require('../../lib/beat-v13-leaderboard');

const LEADERBOARD_CACHE_MS = 5 * 60 * 1000;
let cachedLeaderboard = null;
let cachedLeaderboardAt = 0;

function requestedResource(req) {
    if (typeof req.query?.resource === 'string') return req.query.resource;
    try {
        return new URL(req.url || '', 'https://boxboxf1fantasy.com').searchParams.get('resource') || '';
    } catch (_) {
        return '';
    }
}

async function beatV13Leaderboard(req, res) {
    res.setHeader('Cache-Control', 'public, max-age=60, s-maxage=300, stale-while-revalidate=600');
    if (cachedLeaderboard && Date.now() - cachedLeaderboardAt < LEADERBOARD_CACHE_MS) {
        return res.status(200).json(cachedLeaderboard);
    }

    try {
        const v13 = loadV13Record();
        // Competition rows are intentionally empty until a confirmed entrant
        // submits and verifies the official team they want scored. Public-league
        // membership alone is never treated as competition registration.
        const rows = buildLeaderboard([], v13);
        const v13Row = rows.find(row => row.kind === 'v13');
        const leader = rows[0] || null;
        cachedLeaderboard = {
            ok: true,
            season: 2026,
            through_round: v13.through_round,
            generated_at: new Date().toISOString(),
            provisional: true,
            league: null,
            board_scope: 'registered_competition_entries',
            field_size: rows.filter(row => row.kind === 'community').length,
            v13: v13Row,
            leader: leader ? { rank: leader.rank, team_name: leader.team_name, points: leader.points, kind: leader.kind } : null,
            leaderboard: rows,
            eligibility_note: 'Only confirmed Beat V13 entrants with a submitted and verified official team can appear here. Email addresses remain private. Because team submissions are collected after the season, V13 is the only scored row for now.',
        };
        cachedLeaderboardAt = Date.now();
        return res.status(200).json(cachedLeaderboard);
    } catch (error) {
        console.error('Could not load the Beat V13 leaderboard:', error.message);
        return res.status(503).json({
            ok: false,
            message: 'Registered competition standings are temporarily unavailable. V13\'s public decision record is still available below.',
        });
    }
}

module.exports = function status(req, res) {
    res.setHeader('Allow', 'GET');

    if (req.method !== 'GET') {
        return res.status(405).json({ available: false });
    }

    if (requestedResource(req) === 'beat-v13-leaderboard') {
        return beatV13Leaderboard(req, res);
    }

    res.setHeader('Cache-Control', 'no-store');

    try {
        getConfig();
        return res.status(200).json({ available: true });
    } catch (_) {
        return res.status(200).json({ available: false });
    }
};

module.exports._resetLeaderboardCache = () => {
    cachedLeaderboard = null;
    cachedLeaderboardAt = 0;
};
