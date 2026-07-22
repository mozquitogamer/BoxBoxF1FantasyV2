'use strict';

const {
    createSubscriptionToken,
    getConfig,
    isAllowedRequestOrigin,
    isValidEmail,
    normalizeEmail,
    resendRequest,
} = require('../../lib/email-subscriptions');

module.exports = async function subscribe(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'POST');

    if (req.method !== 'POST') {
        return res.status(405).json({ ok: false, message: 'Method not allowed.' });
    }

    let config;
    try {
        config = getConfig();
    } catch (error) {
        console.error('Email sign-up is not configured:', error.message);
        return res.status(503).json({ ok: false, message: 'Email alerts are not available yet.' });
    }

    if (!isAllowedRequestOrigin(req, config.siteOrigin)) {
        return res.status(403).json({ ok: false, message: 'Request origin was not accepted.' });
    }

    let body = req.body || {};
    if (typeof body === 'string') {
        try {
            body = JSON.parse(body);
        } catch (_) {
            return res.status(400).json({ ok: false, message: 'Invalid request.' });
        }
    }

    // Honeypot fields are intentionally answered as success to avoid teaching bots.
    if (body.website) {
        return res.status(202).json({ ok: true, message: 'Check your inbox to confirm your subscription.' });
    }

    const email = normalizeEmail(body.email);
    if (!isValidEmail(email)) {
        return res.status(400).json({ ok: false, message: 'Enter a valid email address.' });
    }
    if (body.consent !== true) {
        return res.status(400).json({ ok: false, message: 'Please confirm that you want email alerts.' });
    }

    const token = createSubscriptionToken(email, config.signingSecret, config.ttlHours);
    const confirmationUrl = `${config.siteOrigin}/api/email/confirm?token=${encodeURIComponent(token)}`;

    try {
        await resendRequest('/emails', config.apiKey, {
            method: 'POST',
            body: {
                from: config.from,
                to: [email],
                subject: 'Confirm your BoxBox simulation alerts',
                html: `<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;color:#141821">
                    <h1 style="font-size:24px">Confirm your BoxBox alerts</h1>
                    <p>You asked to be notified when BoxBoxF1Fantasy publishes updated race simulations.</p>
                    <p><a href="${confirmationUrl}" style="display:inline-block;background:#e10600;color:#fff;text-decoration:none;padding:12px 18px;border-radius:7px;font-weight:700">Confirm email alerts</a></p>
                    <p style="color:#667085;font-size:13px">This link expires in ${config.ttlHours} hours. If you did not request this, you can ignore this email and no subscription will be created.</p>
                </div>`,
                text: `Confirm your BoxBoxF1Fantasy simulation alerts:\n\n${confirmationUrl}\n\nThis link expires in ${config.ttlHours} hours. If you did not request this, ignore this email.`,
            },
        });
        return res.status(202).json({
            ok: true,
            message: 'Check your inbox and click the confirmation link to finish signing up.',
        });
    } catch (error) {
        console.error('Could not send subscription confirmation:', error.message);
        return res.status(502).json({
            ok: false,
            message: 'We could not send the confirmation email. Please try again shortly.',
        });
    }
};
