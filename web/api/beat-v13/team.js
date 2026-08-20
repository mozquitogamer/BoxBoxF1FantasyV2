'use strict';

const {
    getMemberConfig,
    isAllowedOrigin,
    parseBody,
} = require('../../lib/member-system');
const { consumeRateLimit, rateLimited } = require('../../lib/rate-limit');
const { loadV13Record } = require('../../lib/beat-v13-leaderboard');
const {
    F1_SYNC_LEAGUE_CODE,
    F1_SYNC_LEAGUE_ID,
    getBeatV13Session,
    getEntryForSession,
    loadPublicTeamForEntry,
    persistTeamLink,
    publicEntryState,
    searchOfficialTeams,
    verifyPublicTeamSelection,
    verifyTeamSelectionToken,
} = require('../../lib/beat-v13-entry');

function queryParam(req, name) {
    let value = req.query?.[name];
    if (value === undefined) {
        try { value = new URL(req.url || '/', 'https://boxboxf1fantasy.com').searchParams.get(name); }
        catch (_) { value = ''; }
    }
    return String(value || '').trim();
}

function requestOrigin(req) {
    try {
        return getMemberConfig().siteOrigin;
    } catch (_) {
        return (process.env.SITE_ORIGIN || 'https://boxboxf1fantasy.com').replace(/\/$/, '');
    }
}

function allowed(req) {
    return isAllowedOrigin(req, requestOrigin(req));
}

function unauthorized(res) {
    return res.status(401).json({ ok: false, message: 'Confirm your free Beat V13 entry before connecting a team.' });
}

module.exports = async function beatV13Team(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'GET, POST');
    if (!['GET', 'POST'].includes(req.method)) return res.status(405).json({ ok: false, message: 'Method not allowed.' });
    // Team search is read-only and same-origin browsers may omit Origin on a
    // GET. The link mutation remains origin-checked like the member endpoint.
    if (req.method === 'POST' && !allowed(req)) return res.status(403).json({ ok: false, message: 'Request origin was not accepted.' });

    try {
        const session = await getBeatV13Session(req, res);
        const entry = await getEntryForSession(session);
        if (!session || !entry?.confirmed) return unauthorized(res);

        if (req.method === 'GET') {
            const action = queryParam(req, 'action') || 'search';
            if (action !== 'search') return res.status(400).json({ ok: false, message: 'Unknown team action.' });
            const query = queryParam(req, 'q');
            if (query.length < 2) return res.status(400).json({ ok: false, message: 'Enter at least two characters from your exact official team name.' });
            const throttle = consumeRateLimit(req, `beat-v13-team-search:${entry.id}`, { limit: 12, windowMs: 5 * 60 * 1000 });
            if (!throttle.allowed) return rateLimited(res, throttle, 'Too many team searches. Please wait a few minutes and try again.');
            const teams = await searchOfficialTeams(query, entry.id);
            return res.status(200).json({
                ok: true,
                league_code: F1_SYNC_LEAGUE_CODE,
                league_id: F1_SYNC_LEAGUE_ID,
                teams,
            });
        }

        const body = parseBody(req);
        if (body.action !== 'link' && body.action !== 'f1-link') {
            return res.status(400).json({ ok: false, message: 'Choose an official team from the search results first.' });
        }
        let selected = verifyTeamSelectionToken(body.selection_token || body.link_token, entry.id);
        if (!selected) {
            const id = String(body.official_team_id || body.team_id || '').trim();
            const name = String(body.official_team_name || body.team_name || '').replace(/\s+/g, ' ').trim();
            const slot = Number(body.team_slot || body.slot);
            if (!id || !name || !Number.isInteger(slot) || slot < 1 || slot > 3) {
                return res.status(400).json({ ok: false, message: 'That team selection expired or could not be verified. Search again.' });
            }
            selected = { id, name, slot };
        }

        const official = await verifyPublicTeamSelection(selected);
        if (!official) {
            return res.status(409).json({ ok: false, message: `That team is not visible in the Box Box league yet. Join with code ${F1_SYNC_LEAGUE_CODE}, then search again.` });
        }
        const linked = await persistTeamLink(entry, {
            id: String(official.id),
            name: String(official.name).replace(/\s+/g, ' ').trim().slice(0, 100),
            slot: Number(official.slot),
        });
        let feedTeam = official;
        try { feedTeam = await loadPublicTeamForEntry(linked) || official; } catch (_) { /* public feed was already verified */ }
        return res.status(200).json({
            ok: true,
            message: `${feedTeam.name} is connected for Beat V13 live tracking.`,
            entry: publicEntryState(linked, loadV13Record().points, feedTeam),
        });
    } catch (error) {
        console.error('Could not complete Beat V13 team request:', error.message);
        if (error?.status === 409 || /duplicate key|unique constraint|already linked/i.test(String(error?.message || ''))) {
            return res.status(409).json({ ok: false, message: 'That official team is already linked to another Beat V13 entrant. Choose your own T1/T2/T3 team.' });
        }
        if (error?.code === 'F1_SESSION_EXPIRED' || /public Box Box league feed|temporarily unavailable/i.test(String(error?.message || ''))) {
            return res.status(503).json({ ok: false, message: 'The official Box Box league feed is temporarily unavailable. Please try again shortly.' });
        }
        return res.status(500).json({ ok: false, message: 'We could not connect that team. Please search again and retry.' });
    }
};
