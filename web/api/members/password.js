'use strict';

const crypto = require('node:crypto');
const {
    authAdminRequest,
    authPublicRequest,
    clearSessionCookies,
    getMemberConfig,
    getMemberSession,
    hasRecentAuthMethod,
    isAllowedOrigin,
    isEntitlementActive,
    isValidEmail,
    normalizeEmail,
    parseBody,
    restRequest,
} = require('../../lib/member-system');
const { resendRequest } = require('../../lib/email-subscriptions');
const { consumeRateLimit, rateLimited } = require('../../lib/rate-limit');

const GENERIC_MESSAGE = 'If that address has an active Pit Wall membership, a password setup email is on its way.';
const RESET_INTERVAL_MS = 15 * 60 * 1000;

async function requestReset(req, res, config, body) {
    const email = normalizeEmail(body.email);
    if (!isValidEmail(email)) return res.status(202).json({ ok: true, message: GENERIC_MESSAGE });
    const throttle = consumeRateLimit(req, 'member-password-reset', { limit: 5, windowMs: 60 * 60 * 1000 });
    if (!throttle.allowed) return rateLimited(res, throttle, GENERIC_MESSAGE);

    try {
        const profiles = await restRequest(
            `member_profiles?email=eq.${encodeURIComponent(email)}&select=user_id,email,magic_link_sent_at&limit=1`,
            { service: true },
        );
        const profile = profiles?.[0];
        if (!profile) return res.status(202).json({ ok: true, message: GENERIC_MESSAGE });
        const entitlements = await restRequest(
            `member_entitlements?user_id=eq.${encodeURIComponent(profile.user_id)}&select=status,current_period_end`,
            { service: true },
        );
        if (!(entitlements || []).some(item => isEntitlementActive(item))) {
            return res.status(202).json({ ok: true, message: GENERIC_MESSAGE });
        }
        const lastSent = Date.parse(profile.magic_link_sent_at || '');
        if (Number.isFinite(lastSent) && Date.now() - lastSent < RESET_INTERVAL_MS) {
            return res.status(202).json({ ok: true, message: GENERIC_MESSAGE });
        }

        const link = await authAdminRequest('/admin/generate_link', {
            method: 'POST',
            body: { type: 'recovery', email, redirect_to: `${config.siteOrigin}/api/members/callback` },
        });
        const properties = link?.properties || link || {};
        const tokenHash = properties.hashed_token || properties.token_hash;
        if (!tokenHash) throw new Error('Supabase did not return a recovery token');
        const recoveryUrl = `${config.siteOrigin}/api/members/callback?token_hash=${encodeURIComponent(tokenHash)}&type=recovery`;
        const emailKey = crypto.createHash('sha256').update(email).digest('hex').slice(0, 32);
        const intervalBucket = Math.floor(Date.now() / RESET_INTERVAL_MS);
        await resendRequest('/emails', process.env.RESEND_API_KEY, {
            method: 'POST',
            headers: { 'Idempotency-Key': `pit-wall-password-${emailKey}-${intervalBucket}` },
            body: {
                from: process.env.RESEND_FROM,
                to: [email],
                subject: 'Create or reset your BoxBox Pit Wall password',
                html: `<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;color:#141821"><p style="font-weight:700">BoxBox<span style="color:#e10600">F1</span>Fantasy · Pit Wall</p><h1 style="font-size:24px">Create your password</h1><p>Use this secure link once to create or replace your Pit Wall password. After that, sign in directly with your email and password.</p><p><a href="${recoveryUrl}" style="display:inline-block;background:#e10600;color:#fff;text-decoration:none;padding:12px 18px;border-radius:7px;font-weight:700">Create or reset password</a></p><p style="color:#667085;font-size:13px">If you did not request this, ignore the email. Your current password will not change.</p></div>`,
                text: `Create or reset your BoxBox Pit Wall password:\n\n${recoveryUrl}\n\nIf you did not request this, ignore the email. Your current password will not change.`,
            },
        });
        await restRequest(`member_profiles?user_id=eq.${encodeURIComponent(profile.user_id)}`, {
            service: true,
            method: 'PATCH',
            prefer: 'return=minimal',
            body: { magic_link_sent_at: new Date().toISOString() },
        });
    } catch (error) {
        console.error('Could not create Pit Wall password recovery:', error.message);
    }
    return res.status(202).json({ ok: true, message: GENERIC_MESSAGE });
}

async function savePassword(req, res, body) {
    const newPassword = typeof body.password === 'string' ? body.password : '';
    if (newPassword.length < 10 || newPassword.length > 128) {
        return res.status(400).json({ ok: false, message: 'Use at least 10 characters for your password.' });
    }
    try {
        const session = await getMemberSession(req, res);
        if (!session) return res.status(401).json({ ok: false, message: 'Your password setup session expired. Request a new link.' });
        if (!hasRecentAuthMethod(session.accessToken, session.user.id, 'recovery')) {
            return res.status(403).json({ ok: false, message: 'Use a fresh password setup link before changing your password.' });
        }
        await authPublicRequest('/user', {
            method: 'PUT',
            accessToken: session.accessToken,
            body: { password: newPassword },
        });
        try {
            await authPublicRequest('/logout', { method: 'POST', accessToken: session.accessToken });
        } catch (_) {
            // The password is already changed; clearing the local cookies still closes this browser session.
        }
        clearSessionCookies(res);
        return res.status(200).json({ ok: true, message: 'Password saved. Sign in with your new password.' });
    } catch (error) {
        console.error('Could not update Pit Wall password:', error.message);
        return res.status(400).json({ ok: false, message: 'That password could not be saved. Try a stronger password.' });
    }
}

module.exports = async function password(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'POST');
    if (req.method !== 'POST') return res.status(405).json({ ok: false, message: 'Method not allowed.' });
    let config;
    try { config = getMemberConfig(); }
    catch (_) { return res.status(503).json({ ok: false, message: 'Password setup is not available yet.' }); }
    if (!isAllowedOrigin(req, config.siteOrigin)) return res.status(403).json({ ok: false, message: 'Request origin was not accepted.' });
    const body = parseBody(req);
    if (body.action === 'reset') return requestReset(req, res, config, body);
    if (body.action === 'update') return savePassword(req, res, body);
    return res.status(400).json({ ok: false, message: 'Choose a password action.' });
};
