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
    if (!tokenHash || type !== 'magiclink') {
        clearSessionCookies(res);
        return res.status(400).send(htmlPage('Sign-in link not accepted', 'Request a fresh Pit Wall sign-in link and try again.', false));
    }

    try {
        const session = await authPublicRequest('/verify', {
            method: 'POST',
            body: { token_hash: tokenHash, type: 'magiclink' },
        });
        if (!session?.access_token || !session?.refresh_token) throw new Error('Supabase returned no session');
        setSessionCookies(res, session);
        const origin = getMemberConfig().siteOrigin;
        res.setHeader('Location', `${origin}/?member=welcome#optimizer`);
        return res.status(302).send('Signed in.');
    } catch (error) {
        clearSessionCookies(res);
        console.error('Pit Wall callback failed:', error.message);
        return res.status(400).send(htmlPage('Sign-in link expired', 'Request a fresh Pit Wall sign-in link from the Transfer Advisor.', false));
    }
};
