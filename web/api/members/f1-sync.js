'use strict';

const { getMemberConfig, getMemberSession, isAllowedOrigin, parseBody, restRequest } = require('../../lib/member-system');
const { getOpponentSnapshot } = require('../../lib/f1-fantasy');

function normalizeRound(value) {
    const round = Number(value);
    return Number.isInteger(round) && round >= 1 && round <= 24 ? round : null;
}

async function latestRound() {
    try {
        const response = await fetch('https://boxboxf1fantasy.com/data/predictions.json', { signal: AbortSignal.timeout(5000) });
        const data = await response.json();
        return normalizeRound(data.round || data.metadata?.round);
    } catch (_) { return null; }
}

async function syncLink(link, round) {
    try {
        const snapshot = await getOpponentSnapshot(link, round);
        await restRequest('f1_team_snapshots?on_conflict=user_id,season,round', {
            service: true,
            method: 'POST',
            prefer: 'resolution=merge-duplicates,return=representation',
            body: snapshot,
        });
        await restRequest(`f1_team_links?user_id=eq.${encodeURIComponent(link.user_id)}`, {
            service: true,
            method: 'PATCH',
            body: { status: 'active', last_synced_at: new Date().toISOString(), last_error: null },
        });
        return { ok: true, snapshot };
    } catch (error) {
        await restRequest(`f1_team_links?user_id=eq.${encodeURIComponent(link.user_id)}`, {
            service: true,
            method: 'PATCH',
            body: { last_error: String(error.message || error).slice(0, 500) },
        }).catch(() => null);
        return { ok: false, error };
    }
}

module.exports = async function f1Sync(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'POST');
    if (req.method !== 'POST') return res.status(405).json({ ok: false, message: 'Method not allowed.' });

    let config;
    try { config = getMemberConfig(); } catch (_) {
        return res.status(503).json({ ok: false, message: 'Pit Wall is not configured yet.' });
    }
    if (!isAllowedOrigin(req, config.siteOrigin)) return res.status(403).json({ ok: false, message: 'Request origin was not accepted.' });

    try {
        const session = await getMemberSession(req, res);
        if (!session) return res.status(401).json({ ok: false, message: 'Sign in to sync your official team.' });
        const body = parseBody(req);
        const round = normalizeRound(body.round) || await latestRound();
        if (!round) return res.status(400).json({ ok: false, message: 'The current F1 Fantasy round could not be determined.' });
        const links = await restRequest(`f1_team_links?user_id=eq.${encodeURIComponent(session.user.id)}&status=eq.active&select=*`, { service: true });
        if (!links?.[0]) return res.status(404).json({ ok: false, message: 'Link an official team first.' });
        const result = await syncLink(links[0], round);
        if (!result.ok) throw result.error;
        return res.status(200).json({ ok: true, message: `Official team synced for Round ${round}.`, snapshot: result.snapshot });
    } catch (error) {
        console.error('F1 member sync failed:', error.message);
        return res.status(502).json({ ok: false, message: 'Official sync is temporarily unavailable. Your manually saved team is unchanged.' });
    }
};

module.exports.normalizeRound = normalizeRound;
module.exports.syncLink = syncLink;
