'use strict';

const {
    getConfig,
    htmlPage,
    isBeatV13RegistrationOpen,
    beatV13BrowserCookie,
    isResendEmailCancellationSettled,
    resendRequest,
    verifySubscriptionToken,
} = require('../../lib/email-subscriptions');
const {
    beatV13SessionCookie,
    confirmBeatV13Entry,
    findBeatV13Entry,
    getBeatV13EntryConfig,
    withdrawBeatV13Entry,
} = require('../../lib/beat-v13-entries');
const { ensureBeatV13Segment } = require('../../lib/resend-segments');

const REGISTER_URL = '/?v13=register#beatbot';
const CONFIRMED_URL = '/?v13=confirmed#beatbot';
const SESSION_COOKIE_NAME = '__Host-boxbox_beat_v13_session';

function queryParam(req, name) {
    if (typeof req.query?.[name] === 'string') return req.query[name];
    try { return new URL(req.url || '/', 'https://boxboxf1fantasy.com').searchParams.get(name) || ''; }
    catch (_) { return ''; }
}

async function cancelScheduledReminder(providerMessageId, config) {
    if (!providerMessageId) return;
    try {
        await resendRequest(`/emails/${encodeURIComponent(providerMessageId)}/cancel`, config.apiKey, {
            method: 'POST',
        });
    } catch (error) {
        // A retry can arrive after Resend has already cancelled or delivered
        // the scheduled message. Neither state leaves a scheduled reminder.
        if (!isResendEmailCancellationSettled(error)) throw error;
    }
}

function successResponse(res, entry) {
    // Use the entry helper's canonical secret precedence. Passing the
    // subscription secret explicitly would mint unreadable sessions whenever
    // BEAT_V13_SESSION_SECRET is configured separately in production.
    const sessionCookie = beatV13SessionCookie(entry.id);
    res.setHeader('Set-Cookie', [sessionCookie, beatV13BrowserCookie()]);
    res.setHeader('Location', CONFIRMED_URL);
    // Keep a useful no-JavaScript fallback body; browsers follow the redirect
    // and the main site shows the same wording in its accessible confirmation
    // dialog.
    return res.status(303).send(htmlPage(
        "You're officially entered",
        "Your Beat V13 entry is confirmed. You may now follow V13 and will receive the final official-team submission instructions after the season.",
        true,
        CONFIRMED_URL,
        'Continue to Beat V13',
    ));
}

function cancellationReviewPage(token) {
    const action = `/api/email/confirm?action=cancel&amp;token=${encodeURIComponent(token)}`;
    return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>Cancel Beat V13 registration | BoxBoxF1Fantasy</title></head>
<body style="margin:0;background:#0a0d12;color:#f5f7fa;font-family:Inter,Arial,sans-serif"><main style="max-width:620px;margin:10vh auto;padding:32px 24px;text-align:center"><div style="border:1px solid #273142;border-top:3px solid #ef4444;border-radius:12px;background:#121821;padding:36px 28px"><p style="margin:0 0 8px;color:#aab4c3;font-size:14px">BoxBox<span style="color:#e10600">F1</span>Fantasy</p><h1 style="margin:0 0 14px;font-size:28px">Cancel this pending registration?</h1><p style="margin:0 0 24px;color:#c7d0dc;line-height:1.6">Only continue if you did not request this Beat V13 entry. This also cancels its one-time confirmation reminder.</p><form method="post" action="${action}"><button type="submit" style="border:0;padding:11px 18px;border-radius:8px;background:#e10600;color:#fff;font:inherit;font-weight:700;cursor:pointer">Cancel pending registration</button></form><p style="margin:18px 0 0"><a href="${REGISTER_URL}" style="color:#9bd8ff">Keep it and return to Beat V13</a></p></div></main></body></html>`;
}

function clearRegistrationCookies(res) {
    res.setHeader('Set-Cookie', [
        `${SESSION_COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict`,
        beatV13BrowserCookie(0),
    ]);
}

async function cancelRegistration(req, res) {
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

    const token = queryParam(req, 'token');
    const subscription = verifySubscriptionToken(token, config.signingSecret);
    if (!subscription) {
        return res.status(400).send(htmlPage('Link expired or invalid', 'This cancellation link has expired or is invalid. No change was made.', false, REGISTER_URL, 'Return to Beat V13'));
    }
    if (req.method === 'GET') return res.status(200).send(cancellationReviewPage(token));

    try {
        const entry = await findBeatV13Entry(subscription.email);
        if (!entry || entry.status === 'withdrawn') {
            clearRegistrationCookies(res);
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
        clearRegistrationCookies(res);
        return res.status(200).send(htmlPage('Registration cancelled', 'This pending Beat V13 registration and its one-time reminder have been cancelled. Nothing else is required.', true, REGISTER_URL, 'Return to Beat V13'));
    } catch (error) {
        console.error('Could not cancel Beat V13 registration:', error.message);
        return res.status(502).send(htmlPage('Could not cancel yet', 'We could not cancel this registration right now. Please try the link again in a moment.', false, REGISTER_URL, 'Try again'));
    }
}

module.exports = async function confirm(req, res) {
    if (queryParam(req, 'action') === 'cancel') return cancelRegistration(req, res);

    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.setHeader('Allow', 'GET');

    if (req.method !== 'GET') {
        return res.status(405).send(htmlPage('Method not allowed', 'Open the confirmation link from your email.', false, REGISTER_URL, 'Request a new link'));
    }

    let config;
    try {
        config = getConfig();
        getBeatV13EntryConfig();
    } catch (error) {
        console.error('Email confirmation is not configured:', error.message);
        return res.status(503).send(htmlPage('Confirmation is not ready', 'Beat V13 confirmation is temporarily unavailable. Please try again later.', false, REGISTER_URL, 'Try again'));
    }

    if (!isBeatV13RegistrationOpen()) {
        return res.status(410).send(htmlPage(
            'Registration closed',
            'Beat V13 registration closed at the Round 22 F1 Fantasy team lock.',
            false,
            REGISTER_URL,
            'View Beat V13',
        ));
    }

    const token = queryParam(req, 'token');
    const subscription = verifySubscriptionToken(token, config.signingSecret);
    if (!subscription) {
        return res.status(400).send(htmlPage(
            'Link expired or invalid',
            'This confirmation link has expired or is invalid. Request a new confirmation link to finish your Beat V13 entry.',
            false,
            REGISTER_URL,
            'Request a new confirmation link',
        ));
    }

    try {
        const entry = await findBeatV13Entry(subscription.email);
        if (!entry || entry.status === 'withdrawn') {
            return res.status(400).send(htmlPage(
                'Link expired or cancelled',
                'This confirmation link is no longer active. Request a new confirmation link to enter Beat V13.',
                false,
                REGISTER_URL,
                'Request a new confirmation link',
            ));
        }

        // Confirmed retries are idempotent. If an earlier attempt completed
        // the entry but the cancellation request was interrupted, finish the
        // reminder cancellation before returning the success redirect.
        if (entry.reminder_provider_id) {
            await cancelScheduledReminder(entry.reminder_provider_id, config);
        }

        if (entry.status !== 'confirmed') {
            const segmentId = await ensureBeatV13Segment();
            const encodedEmail = encodeURIComponent(subscription.email);
            try {
                await resendRequest('/contacts', config.apiKey, {
                    method: 'POST',
                    body: {
                        email: subscription.email,
                        unsubscribed: false,
                        segments: [{ id: segmentId }],
                    },
                });
            } catch (error) {
                if (error.status !== 409) throw error;
                await resendRequest(`/contacts/${encodedEmail}`, config.apiKey, {
                    method: 'PATCH',
                    body: { unsubscribed: false },
                });
                try {
                    await resendRequest(`/contacts/${encodedEmail}/segments/${encodeURIComponent(segmentId)}`, config.apiKey, {
                        method: 'POST',
                    });
                } catch (segmentError) {
                    if (segmentError.status !== 409) throw segmentError;
                }
            }

            const confirmed = await confirmBeatV13Entry(entry.id);
            if (!confirmed) {
                const retried = await findBeatV13Entry(subscription.email);
                if (!retried || retried.status !== 'confirmed') {
                    throw new Error('The Beat V13 entry could not be marked confirmed');
                }
            }
        }

        return successResponse(res, { ...entry, id: entry.id });
    } catch (error) {
        console.error('Could not confirm subscription:', error.message);
        return res.status(502).send(htmlPage(
            'Could not confirm yet',
            'We could not finish confirmation right now. Please try the confirmation link again in a moment; if it still fails, request a new confirmation link.',
            false,
            REGISTER_URL,
            'Try again',
        ));
    }
};

module.exports._cancelScheduledReminder = cancelScheduledReminder;
module.exports._cancelRegistration = cancelRegistration;
