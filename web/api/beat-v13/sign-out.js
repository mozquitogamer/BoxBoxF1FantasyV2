'use strict';

const { getMemberConfig, isAllowedOrigin, clearSessionCookies } = require('../../lib/member-system');
const { clearBeatV13SessionCookies } = require('../../lib/beat-v13-entry');

function origin(req) {
    try { return getMemberConfig().siteOrigin; }
    catch (_) { return (process.env.SITE_ORIGIN || 'https://boxboxf1fantasy.com').replace(/\/$/, ''); }
}

module.exports = async function beatV13SignOut(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'POST');
    if (req.method !== 'POST') return res.status(405).json({ ok: false });
    if (!isAllowedOrigin(req, origin(req))) return res.status(403).json({ ok: false });
    clearBeatV13SessionCookies(res);
    // One visible sign-out should end both first-party website sessions. This
    // only expires the member cookies; the existing endpoint remains the one
    // that asks Supabase to revoke the upstream token when configured.
    clearSessionCookies(res);
    return res.status(200).json({ ok: true });
};

