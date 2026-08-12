'use strict';

const {
    authPublicRequest,
    getMemberConfig,
    getMemberSession,
    isAllowedOrigin,
    parseBody,
} = require('../../lib/member-system');

module.exports = async function password(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'POST');
    if (req.method !== 'POST') return res.status(405).json({ ok: false, message: 'Method not allowed.' });
    const config = getMemberConfig();
    if (!isAllowedOrigin(req, config.siteOrigin)) return res.status(403).json({ ok: false, message: 'Request origin was not accepted.' });
    const body = parseBody(req);
    const newPassword = typeof body.password === 'string' ? body.password : '';
    if (newPassword.length < 10 || newPassword.length > 128) {
        return res.status(400).json({ ok: false, message: 'Use at least 10 characters for your password.' });
    }
    try {
        const session = await getMemberSession(req, res);
        if (!session) return res.status(401).json({ ok: false, message: 'Your password setup session expired. Request a new link.' });
        await authPublicRequest('/user', {
            method: 'PUT',
            accessToken: session.accessToken,
            body: { password: newPassword },
        });
        return res.status(200).json({ ok: true, message: 'Password saved. You are signed in.' });
    } catch (error) {
        console.error('Could not update Pit Wall password:', error.message);
        return res.status(400).json({ ok: false, message: 'That password could not be saved. Try a stronger password.' });
    }
};
