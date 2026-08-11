'use strict';

const {
    authAdminRequest,
    getMemberConfig,
    isAllowedOrigin,
    isEntitlementActive,
    isValidEmail,
    normalizeEmail,
    parseBody,
    restRequest,
} = require('../../lib/member-system');
const { resendRequest } = require('../../lib/email-subscriptions');

const GENERIC_MESSAGE = 'If that address has an active Pit Wall membership, a secure sign-in link is on its way.';
const MIN_LINK_INTERVAL_MS = 60 * 1000;

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

    const email = normalizeEmail(parseBody(req).email);
    if (!isValidEmail(email)) return res.status(400).json({ ok: false, message: 'Enter a valid email address.' });

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
        if (Number.isFinite(lastSent) && Date.now() - lastSent < MIN_LINK_INTERVAL_MS) {
            return res.status(202).json({ ok: true, message: GENERIC_MESSAGE });
        }

        const link = await authAdminRequest('/admin/generate_link', {
            method: 'POST',
            body: {
                type: 'magiclink',
                email,
                redirect_to: `${config.siteOrigin}/api/members/callback`,
            },
        });
        const properties = link?.properties || link || {};
        const tokenHash = properties.hashed_token || properties.token_hash;
        if (!tokenHash) throw new Error('Supabase did not return a hashed sign-in token');

        const callbackUrl = `${config.siteOrigin}/api/members/callback?token_hash=${encodeURIComponent(tokenHash)}&type=magiclink`;
        await resendRequest('/emails', process.env.RESEND_API_KEY, {
            method: 'POST',
            body: {
                from: process.env.RESEND_FROM,
                to: [email],
                subject: 'Your BoxBox Pit Wall sign-in link',
                html: `<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;color:#141821">
                    <p style="font-weight:700">BoxBox<span style="color:#e10600">F1</span>Fantasy · Pit Wall</p>
                    <h1 style="font-size:24px">Sign in to your saved team</h1>
                    <p>Use this secure link to open your Pit Wall account, remember your current F1 Fantasy team and manage personalized simulation alerts.</p>
                    <p><a href="${callbackUrl}" style="display:inline-block;background:#e10600;color:#fff;text-decoration:none;padding:12px 18px;border-radius:7px;font-weight:700">Sign in to the Pit Wall</a></p>
                    <p style="color:#667085;font-size:13px">The link expires automatically and can only be used once. If you did not request it, ignore this email.</p>
                </div>`,
                text: `Sign in to your BoxBox Pit Wall account:\n\n${callbackUrl}\n\nThe link expires automatically and can only be used once. If you did not request it, ignore this email.`,
            },
        });

        await restRequest(`member_profiles?user_id=eq.${encodeURIComponent(profile.user_id)}`, {
            service: true,
            method: 'PATCH',
            prefer: 'return=minimal',
            body: { magic_link_sent_at: new Date().toISOString() },
        });
        return res.status(202).json({ ok: true, message: GENERIC_MESSAGE });
    } catch (error) {
        console.error('Could not create Pit Wall sign-in link:', error.message);
        return res.status(202).json({ ok: true, message: GENERIC_MESSAGE });
    }
};
