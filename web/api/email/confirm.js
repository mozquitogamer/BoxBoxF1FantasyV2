'use strict';

const {
    getConfig,
    htmlPage,
    isBeatV13RegistrationOpen,
    beatV13BrowserCookie,
    resendRequest,
    verifySubscriptionToken,
} = require('../../lib/email-subscriptions');
const {
    beatV13SessionCookie,
    confirmBeatV13Entry,
    findBeatV13Entry,
    getBeatV13EntryConfig,
} = require('../../lib/beat-v13-entries');
const { ensureBeatV13Segment } = require('../../lib/resend-segments');

const REGISTER_URL = '/?v13=register#beatbot';
const CONFIRMED_URL = '/?v13=confirmed#beatbot';

async function cancelScheduledReminder(providerMessageId, config) {
    if (!providerMessageId) return;
    try {
        await resendRequest(`/emails/${encodeURIComponent(providerMessageId)}/cancel`, config.apiKey, {
            method: 'POST',
        });
    } catch (error) {
        // A retry can arrive after Resend has already cancelled or delivered
        // the scheduled message. Neither state leaves a scheduled reminder.
        if (![404, 409].includes(error.status)) throw error;
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

module.exports = async function confirm(req, res) {
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

    const token = typeof req.query?.token === 'string' ? req.query.token : '';
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
