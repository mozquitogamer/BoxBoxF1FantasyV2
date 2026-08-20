'use strict';

const { getConfig } = require('../../lib/email-subscriptions');
const { getPublicLeagueLeaderboard } = require('../../lib/f1-fantasy');
const { listBeatV13Entries } = require('../../lib/beat-v13-entries');
const {
    buildConfirmedLeaderboardEntries,
    buildLeaderboard,
    loadV13Record,
} = require('../../lib/beat-v13-leaderboard');

const LEADERBOARD_CACHE_MS = 5 * 60 * 1000;
let cachedLeaderboard = null;
let cachedLeaderboardAt = 0;

const F1_SYNC_LEAGUE_CODE = 'P1JZAGNMP04';
const F1_SYNC_LEAGUE_ID = Number(process.env.F1_FANTASY_LEAGUE_ID || 160604);

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
        const { entries, databaseAvailable } = await loadBeatV13Entries();
        const confirmedEntries = entries.filter(entry => isConfirmedEntry(entry));
        const feedTeams = confirmedEntries.some(entry => hasLinkedTeam(entry))
            ? await loadPublicLeagueTeams()
            : [];
        const competition = buildConfirmedLeaderboardEntries(entries, feedTeams);
        const rows = buildLeaderboard(competition.teams, v13);
        const v13Row = rows.find(row => row.kind === 'v13');
        const leader = rows[0] || null;
        cachedLeaderboard = {
            ok: true,
            season: 2026,
            through_round: v13.through_round,
            generated_at: new Date().toISOString(),
            provisional: true,
            league: {
                code: F1_SYNC_LEAGUE_CODE,
                id: F1_SYNC_LEAGUE_ID,
                purpose: 'automated_live_tracking',
            },
            board_scope: 'registered_competition_entries',
            // Keep these as separate values. A confirmed entrant who has not
            // linked an official team is still in the competition, but cannot
            // be scored on the live board yet.
            confirmed_entrant_count: competition.confirmed_count,
            linked_entrant_count: competition.linked_count,
            scored_entrant_count: competition.scored_count,
            field_size: competition.scored_count,
            database_available: databaseAvailable,
            v13: v13Row,
            leader: leader ? { rank: leader.rank, team_name: leader.team_name, points: leader.points, kind: leader.kind } : null,
            leaderboard: rows,
            eligibility_note: 'Provisional live board: only confirmed Beat V13 entrants who have linked an official team in the Box Box F1 Fantasy league and whose current score is visible in that public feed are shown. Confirmed entrants without a linked team are counted above but are not shown until they connect one. Email addresses and manager names remain private. Joining the league is only required for automated live tracking; the original end-season screenshot eligibility still applies.',
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

function isConfirmedEntry(entry) {
    const status = String(entry?.status || entry?.entry_status || entry?.registration_status || '').toLowerCase();
    return Boolean(entry?.confirmed_at || entry?.confirmedAt || entry?.email_confirmed_at || entry?.verified_at)
        || ['confirmed', 'verified'].includes(status);
}

function hasLinkedTeam(entry) {
    const id = String(entry?.official_team_id || entry?.officialTeamId || entry?.f1_team_id || entry?.f1TeamId || entry?.team_id || '').trim();
    const name = String(entry?.official_team_name || entry?.officialTeamName || entry?.f1_team_name || entry?.f1TeamName || entry?.team_name || '').trim();
    const slot = Number(entry?.official_team_slot || entry?.officialTeamSlot || entry?.f1_team_slot || entry?.f1TeamSlot || entry?.team_slot || entry?.teamSlot || entry?.slot);
    const state = String(entry?.team_link_status || entry?.teamLinkStatus || entry?.f1_team_status || 'active').toLowerCase();
    return Boolean(id && name && Number.isInteger(slot) && slot >= 1 && slot <= 3 && state === 'active');
}

async function loadBeatV13Entries() {
    try {
        const rows = await listBeatV13Entries();
        return { entries: Array.isArray(rows) ? rows : [], databaseAvailable: true };
    } catch (error) {
        // A migration can briefly lag a deployment. Empty is safe (and is
        // explicitly marked unavailable in the response); never substitute
        // public-league teams for confirmed competition rows.
        if (error?.status === 404 || /relation .*beat_v13_entries.*does not exist|schema cache|is not configured|valid URL/i.test(String(error?.message || ''))) {
            return { entries: [], databaseAvailable: false };
        }
        throw error;
    }
}

async function loadPublicLeagueTeams() {
    try {
        const result = await getPublicLeagueLeaderboard();
        return result?.teams || [];
    } catch (error) {
        console.error('Could not refresh the public Box Box league feed:', error.message);
        return [];
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

module.exports._loadBeatV13Entries = loadBeatV13Entries;
module.exports._isConfirmedEntry = isConfirmedEntry;
module.exports._hasLinkedTeam = hasLinkedTeam;
