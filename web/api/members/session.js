'use strict';

const { getMemberDashboard, getMemberSession } = require('../../lib/member-system');
const { loadV13Record } = require('../../lib/beat-v13-leaderboard');
const {
    getBeatV13Session,
    getEntryForSession,
    loadPublicTeamForEntry,
    publicEntryState,
} = require('../../lib/beat-v13-entry');

function queryParam(req, name) {
    if (req.query?.[name] !== undefined) return String(req.query[name] || '').trim();
    try { return new URL(req.url || '/', 'https://boxboxf1fantasy.com').searchParams.get(name) || ''; }
    catch (_) { return ''; }
}

async function beatV13Session(req, res) {
    try {
        const session = await getBeatV13Session(req, res);
        if (!session) return res.status(200).json({ authenticated: false });
        const entry = await getEntryForSession(session);
        if (!entry || !entry.confirmed) return res.status(401).json({ authenticated: false });

        let feedTeam = null;
        if (entry.linked) {
            try { feedTeam = await loadPublicTeamForEntry(entry); }
            catch (error) { console.error('Could not refresh free Beat V13 team:', error.message); }
        }
        return res.status(200).json(publicEntryState(entry, loadV13Record().points, feedTeam));
    } catch (error) {
        console.error('Could not load Beat V13 session:', error.message);
        return res.status(503).json({ authenticated: false, message: 'Beat V13 account data is temporarily unavailable.' });
    }
}

module.exports = async function session(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'GET');
    if (req.method !== 'GET') return res.status(405).json({ authenticated: false });

    if (queryParam(req, 'scope') === 'beat-v13') return beatV13Session(req, res);

    try {
        const memberSession = await getMemberSession(req, res);
        if (!memberSession) return res.status(200).json({ authenticated: false });
        return res.status(200).json(await getMemberDashboard(memberSession));
    } catch (error) {
        console.error('Could not load Pit Wall session:', error.message);
        return res.status(503).json({ authenticated: false, message: 'Pit Wall account data is temporarily unavailable.' });
    }
};
