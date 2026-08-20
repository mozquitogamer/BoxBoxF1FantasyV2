'use strict';

const {
    getConfig,
    htmlPage,
    resendRequest,
    verifySubscriptionToken,
    beatV13BrowserCookie,
} = require('../../lib/email-subscriptions');
const {
    findBeatV13Entry,
    getBeatV13EntryConfig,
    withdrawBeatV13Entry,
} = require('../../lib/beat-v13-entries');

const REGISTER_URL = '/?v13=register#beatbot';
const SESSION_COOKIE_NAME = '__Host-boxbox_beat_v13_session';

function cancellationReviewPage(token) {
    const action = `/api/email/cancel?token=${encodeURIComponent(token)}`;
    return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>Cancel Beat V13 registration | BoxBoxF1Fantasy</title></head>
<body style="margin:0;background:#0a0d12;color:#f5f7fa;font-family:Inter,Arial,sans-serif"><main style="max-width:620px;margin:10vh auto;padding:32px 24px;text-align:center"><div style="border:1px solid #273142;border-top:3px solid #ef4444;border-radius:12px;background:#121821;padding:36px 28px"><p style="margin:0 0 8px;color:#aab4c3;font-size:14px">BoxBox<span style="color:#e10600">F1</span>Fantasy</p><h1 style="margin:0 0 14px;font-size:28px">Cancel this pending registration?</h1><p style="margin:0 0 24px;color:#c7d0dc;line-height:1.6">Only continue if you did not request this Beat V13 entry. This also cancels its one-time confirmation reminder.</p><form method="post" action="${action}"><button type="submit" style="border:0;padding:11px 18px;border-radius:8px;background:#e10600;color:#fff;font:inherit;font-weight:700;cursor:pointer">Cancel pending registration</button></form><p style="margin:18px 0 0"><a href="${REGISTER_URL}" style="color:#9bd8ff">Keep it and return to Beat V13</a></p></div></main></body></html>`;
}

function clearCookies(res) {
    res.setHeader('Set-Cookie', [
        `${SESSION_COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict`,
        `${beatV13BrowserCookie(0)}`,
    ]);
}

async function cancelScheduledReminder(providerMessageId, config) {
    if (!providerMessageId) return;
    try {
        await resendRequest(`/emails/${encodeURIComponent(providerMessageId)}/cancel`, config.apiKey, {
            method: 'POST',
        });
    } catch (error) {
        if (![404, 409].includes(error.status)) throw error;
    }
}

module.exports = async function cancel(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.setHeader('Allow', 'GET, POST');

    if (!['GET', 'POST'].includes(req.method)) {
        return res.status(405).send(htmlPage('Method not allowed', 'Open the cancellation link from your email.', false, REGISTER_URL, 'Return to Beat V13'));
    }

    let config;
    try {
        config = getConfig();
        getBeatV13EntryConfig();
    } catch (error) {
        console.error('Beat V13 cancellation is not configured:', error.message);
        return res.status(503).send(htmlPage('Cancellation is not ready', 'Please try again later.', false, REGISTER_URL, 'Return to Beat V13'));
    }

    const token = typeof req.query?.token === 'string' ? req.query.token : '';
    const subscription = verifySubscriptionToken(token, config.signingSecret);
    if (!subscription) {
        return res.status(400).send(htmlPage('Link expired or invalid', 'This cancellation link has expired or is invalid. No change was made.', false, REGISTER_URL, 'Return to Beat V13'));
    }

    // Email security scanners commonly open every GET link. Never let that
    // passive preview withdraw a real entrant; require the explicit form POST.
    if (req.method === 'GET') {
        return res.status(200).send(cancellationReviewPage(token));
    }

    try {
        const entry = await findBeatV13Entry(subscription.email);
        if (!entry || entry.status === 'withdrawn') {
            clearCookies(res);
            return res.status(200).send(htmlPage('Registration already cancelled', 'No active pending Beat V13 registration remains for this link.', true, REGISTER_URL, 'Return to Beat V13'));
        }
        if (entry.status === 'confirmed') {
            return res.status(200).send(htmlPage('Entry already confirmed', 'This link belongs to an officially entered Beat V13 participant. Use the unsubscribe controls in a future email if you no longer want updates.', true, '/#beatbot', 'View Beat V13'));
        }

        await cancelScheduledReminder(entry.reminder_provider_id, config);
        const withdrawn = await withdrawBeatV13Entry(entry.id);
        if (!withdrawn) {
            const current = await findBeatV13Entry(subscription.email);
            if (current?.status === 'confirmed') {
                return res.status(200).send(htmlPage('Entry already confirmed', 'This link belongs to an officially entered Beat V13 participant.', true, '/#beatbot', 'View Beat V13'));
            }
        }
        clearCookies(res);
        return res.status(200).send(htmlPage('Registration cancelled', 'This pending Beat V13 registration and its one-time reminder have been cancelled. Nothing else is required.', true, REGISTER_URL, 'Return to Beat V13'));
    } catch (error) {
        console.error('Could not cancel Beat V13 registration:', error.message);
        return res.status(502).send(htmlPage('Could not cancel yet', 'We could not cancel this registration right now. Please try the link again in a moment.', false, REGISTER_URL, 'Try again'));
    }
};

module.exports._cancelScheduledReminder = cancelScheduledReminder;
