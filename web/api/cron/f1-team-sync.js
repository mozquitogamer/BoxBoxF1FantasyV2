'use strict';

const { restRequest, safeEqual } = require('../../lib/member-system');
const { syncLink } = require('../members/f1-sync');

function normalizeRound(value) {
    const round = Number(value);
    return Number.isInteger(round) && round >= 1 && round <= 24 ? round : null;
}

async function currentRound() {
    const origin = (process.env.SITE_ORIGIN || 'https://boxboxf1fantasy.com').replace(/\/$/, '');
    const response = await fetch(`${origin}/data/predictions.json?f1_team_cron=${Date.now()}`, { signal: AbortSignal.timeout(7000) });
    if (!response.ok) throw new Error(`Predictions request failed (${response.status})`);
    const data = await response.json();
    const round = normalizeRound(data.round || data.metadata?.round);
    if (!round) throw new Error('The current round was not found in predictions.json.');
    return round;
}

module.exports = async function cronF1TeamSync(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'GET');
    if (req.method !== 'GET') return res.status(405).json({ ok: false, message: 'Method not allowed.' });
    const secret = String(process.env.CRON_SECRET || '');
    const supplied = String(req.headers.authorization || '').replace(/^Bearer\s+/i, '');
    if (!secret || !safeEqual(secret, supplied)) return res.status(401).json({ ok: false, message: 'Unauthorized.' });

    try {
        const round = await currentRound();
        const links = await restRequest('f1_team_links?status=eq.active&select=*', { service: true });
        const results = [];
        for (const link of links || []) {
            const result = await syncLink(link, round);
            results.push({ user_id: link.user_id, ok: result.ok, error: result.ok ? null : String(result.error?.message || result.error) });
        }
        const synced = results.filter(item => item.ok).length;
        return res.status(200).json({ ok: synced === results.length, round, linked: results.length, synced, failed: results.length - synced });
    } catch (error) {
        console.error('F1 team cron failed:', error.message);
        return res.status(500).json({ ok: false, message: 'F1 team synchronization failed.' });
    }
};

module.exports.currentRound = currentRound;
