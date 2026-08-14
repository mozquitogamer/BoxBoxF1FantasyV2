'use strict';

const { getLeagueLeaderboard } = require('../../lib/f1-fantasy');
const { buildLeaderboard, loadV13Record } = require('../../lib/beat-v13-leaderboard');

const CACHE_MS = 5 * 60 * 1000;
let cachedPayload = null;
let cachedAt = 0;

module.exports = async function leaderboard(req, res) {
    res.setHeader('Allow', 'GET');
    res.setHeader('Cache-Control', 'public, max-age=60, s-maxage=300, stale-while-revalidate=600');
    if (req.method !== 'GET') {
        return res.status(405).json({ ok: false, message: 'Method not allowed.' });
    }

    if (cachedPayload && Date.now() - cachedAt < CACHE_MS) {
        return res.status(200).json(cachedPayload);
    }

    try {
        const [{ teams, settings }, v13] = await Promise.all([
            getLeagueLeaderboard(),
            Promise.resolve(loadV13Record()),
        ]);
        const rows = buildLeaderboard(teams, v13);
        const v13Row = rows.find(row => row.kind === 'v13');
        const leader = rows[0] || null;
        cachedPayload = {
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
        cachedAt = Date.now();
        return res.status(200).json(cachedPayload);
    } catch (error) {
        console.error('Could not load the Beat V13 leaderboard:', error.message);
        return res.status(503).json({
            ok: false,
            message: 'Live community standings are temporarily unavailable. V13\'s public decision record is still available below.',
        });
    }
};

module.exports._resetCache = () => {
    cachedPayload = null;
    cachedAt = 0;
};
