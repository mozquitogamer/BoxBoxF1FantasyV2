'use strict';

const { getConfig } = require('../../lib/email-subscriptions');
const { getLeagueLeaderboard } = require('../../lib/f1-fantasy');
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
        const [{ teams, settings }, v13] = await Promise.all([
            getLeagueLeaderboard(),
            Promise.resolve(loadV13Record()),
        ]);
        console.info('[beat-v13-shape]', JSON.stringify({
            team_count: teams.length,
            first_team_keys: Object.keys(teams[0]?.raw || {}).sort(),
        }));
        const rows = buildLeaderboard(teams, v13);
        const v13Row = rows.find(row => row.kind === 'v13');
        const leader = rows[0] || null;
        cachedLeaderboard = {
            ok: true,
            season: 2026,
            through_round: v13.through_round,
            generated_at: new Date().toISOString(),
            provisional: true,
            league: {
                id: settings.leagueId,
                type: settings.leagueType,
                name: 'Box Box F1 Fantasy',
            },
            field_size: rows.filter(row => row.kind === 'entrant').length,
            v13: v13Row,
            leader: leader ? { rank: leader.rank, team_name: leader.team_name, points: leader.points, kind: leader.kind } : null,
            leaderboard: rows,
            eligibility_note: 'Live community standings are a progress view, not the final prize table. A confirmed Beat V13 email entry and end-of-season official score verification are still required.',
        };
        cachedLeaderboardAt = Date.now();
        return res.status(200).json(cachedLeaderboard);
    } catch (error) {
        console.error('Could not load the Beat V13 leaderboard:', error.message);
        return res.status(503).json({
            ok: false,
            message: 'Live community standings are temporarily unavailable. V13\'s public decision record is still available below.',
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
