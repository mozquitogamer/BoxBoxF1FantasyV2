'use strict';

const {
    authPublicRequest,
    clearSessionCookies,
    getMemberConfig,
    setSessionCookies,
} = require('../../lib/member-system');
const { htmlPage } = require('../../lib/email-subscriptions');

module.exports = async function callback(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'GET');
    if (req.method !== 'GET') return res.status(405).send('Method not allowed.');

    const tokenHash = String(req.query?.token_hash || '');
    const type = String(req.query?.type || '');
    if (!tokenHash || !['magiclink', 'recovery'].includes(type)) {
        clearSessionCookies(res);
        return res.status(400).send(htmlPage('Account link not accepted', 'Return to Pit Wall and request a fresh password setup link.', false));
    }

    try {
        const session = await authPublicRequest('/verify', {
            method: 'POST',
            body: { token_hash: tokenHash, type },
        });
        if (!session?.access_token || !session?.refresh_token) throw new Error('Supabase returned no session');
        setSessionCookies(res, session);
        const origin = getMemberConfig().siteOrigin;
        res.setHeader('Location', `${origin}/?member=${type === 'recovery' ? 'password' : 'welcome'}#optimizer`);
        return res.status(302).send('Signed in.');
    } catch (error) {
        clearSessionCookies(res);
        console.error('Pit Wall callback failed:', error.message);
        return res.status(400).send(htmlPage('Account link expired', 'Return to Pit Wall and request a fresh password setup link.', false));
    }
};
