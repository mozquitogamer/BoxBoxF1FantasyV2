'use strict';

const {
    authPublicRequest,
    clearSessionCookies,
    getMemberConfig,
    getMemberSession,
    isAllowedOrigin,
} = require('../../lib/member-system');

module.exports = async function signOut(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'POST');
    if (req.method !== 'POST') return res.status(405).json({ ok: false });
    const config = getMemberConfig();
    if (!isAllowedOrigin(req, config.siteOrigin)) return res.status(403).json({ ok: false });

    try {
        const session = await getMemberSession(req, res);
        if (session) {
            await authPublicRequest('/logout', { method: 'POST', accessToken: session.accessToken }).catch(() => null);
        }
    } finally {
        clearSessionCookies(res);
    }
    return res.status(200).json({ ok: true });
};
