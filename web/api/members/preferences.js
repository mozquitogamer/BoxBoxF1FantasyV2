'use strict';

const {
    getMemberConfig,
    getMemberSession,
    isAllowedOrigin,
    parseBody,
    restRequest,
} = require('../../lib/member-system');

module.exports = async function preferences(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'POST');
    if (req.method !== 'POST') return res.status(405).json({ ok: false, message: 'Method not allowed.' });

    const config = getMemberConfig();
    if (!isAllowedOrigin(req, config.siteOrigin)) return res.status(403).json({ ok: false, message: 'Request origin was not accepted.' });
    const body = parseBody(req);
    if (typeof body.email_simulation_updates !== 'boolean') {
        return res.status(400).json({ ok: false, message: 'Choose whether to receive simulation emails.' });
    }

    try {
        const session = await getMemberSession(req, res);
        if (!session) return res.status(401).json({ ok: false, message: 'Sign in to update email preferences.' });
        await restRequest(`member_profiles?user_id=eq.${encodeURIComponent(session.user.id)}`, {
            accessToken: session.accessToken,
            method: 'PATCH',
            prefer: 'return=minimal',
            body: { email_simulation_updates: body.email_simulation_updates },
        });
        return res.status(200).json({ ok: true });
    } catch (error) {
        console.error('Could not update member preferences:', error.message);
        return res.status(500).json({ ok: false, message: 'We could not update that preference.' });
    }
};
