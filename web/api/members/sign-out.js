'use strict';

const {
    authPublicRequest,
    clearSessionCookies,
    getMemberConfig,
    getMemberSession,
    isAllowedOrigin,
} = require('../../lib/member-system');
const { clearBeatV13SessionCookies } = require('../../lib/beat-v13-entry');

module.exports = async function signOut(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'POST');
    if (req.method !== 'POST') return res.status(405).json({ ok: false });
    let config = null;
    try { config = getMemberConfig(); }
    catch (_) {
        // A free Beat V13 account may use the unified endpoint even when the
        // optional Pit Wall/Supabase configuration is absent in a preview.
        if (!isAllowedOrigin(req, process.env.SITE_ORIGIN || 'https://boxboxf1fantasy.com')) return res.status(403).json({ ok: false });
    }
    if (config && !isAllowedOrigin(req, config.siteOrigin)) return res.status(403).json({ ok: false });

    try {
        if (config) {
            const session = await getMemberSession(req, res);
            if (session) {
                await authPublicRequest('/logout', { method: 'POST', accessToken: session.accessToken }).catch(() => null);
            }
        }
    } finally {
        clearSessionCookies(res);
        clearBeatV13SessionCookies(res);
    }
    return res.status(200).json({ ok: true });
};
