'use strict';

const {
    authPublicRequest,
    clearSessionCookies,
    getMemberConfig,
    isAllowedOrigin,
    isEntitlementActive,
    isValidEmail,
    normalizeEmail,
    parseBody,
    restRequest,
    setSessionCookies,
} = require('../../lib/member-system');
const { consumeRateLimit, rateLimited } = require('../../lib/rate-limit');

const GENERIC_ERROR = 'That email or password was not accepted.';

module.exports = async function signIn(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'POST');
    if (req.method !== 'POST') return res.status(405).json({ ok: false, message: 'Method not allowed.' });

    let config;
    try {
        config = getMemberConfig();
    } catch (error) {
        console.error('Member sign-in is not configured:', error.message);
        return res.status(503).json({ ok: false, message: 'Pit Wall sign-in is not available yet.' });
    }
    if (!isAllowedOrigin(req, config.siteOrigin)) {
        return res.status(403).json({ ok: false, message: 'Request origin was not accepted.' });
    }

    const body = parseBody(req);
    const email = normalizeEmail(body.email);
    const password = typeof body.password === 'string' ? body.password : '';
    if (!isValidEmail(email) || password.length < 8 || password.length > 128) {
        return res.status(401).json({ ok: false, message: GENERIC_ERROR });
    }
    const throttle = consumeRateLimit(req, 'member-sign-in', { limit: 10, windowMs: 10 * 60 * 1000 });
    if (!throttle.allowed) return rateLimited(res, throttle, GENERIC_ERROR);

    try {
        const session = await authPublicRequest('/token?grant_type=password', {
            method: 'POST',
            body: { email, password },
        });
        if (!session?.access_token || !session?.refresh_token || !session?.user?.id) {
            throw new Error('Supabase returned no password session');
        }
        const entitlements = await restRequest(
            `member_entitlements?user_id=eq.${encodeURIComponent(session.user.id)}&select=status,current_period_end`,
            { accessToken: session.access_token },
        );
        if (!(entitlements || []).some(item => isEntitlementActive(item))) {
            await authPublicRequest('/logout', { method: 'POST', accessToken: session.access_token }).catch(() => null);
            clearSessionCookies(res);
            return res.status(403).json({ ok: false, message: 'This Pit Wall membership is not currently active.' });
        }
        setSessionCookies(res, session);
        return res.status(200).json({ ok: true, message: 'Signed in.' });
    } catch (error) {
        clearSessionCookies(res);
        console.error('Pit Wall password sign-in failed:', error.message);
        return res.status(401).json({ ok: false, message: GENERIC_ERROR });
    }
};
