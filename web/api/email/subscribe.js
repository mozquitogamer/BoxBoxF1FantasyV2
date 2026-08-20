'use strict';

const crypto = require('node:crypto');

const {
    createSubscriptionToken,
    getConfig,
    isBeatV13RegistrationOpen,
    isAllowedRequestOrigin,
    isValidEmail,
    normalizeEmail,
    resendRequest,
} = require('../../lib/email-subscriptions');
const {
    claimBeatV13Reminder,
    ensurePendingBeatV13Entry,
    findBeatV13Entry,
    getBeatV13EntryConfig,
    markBeatV13ConfirmationSent,
    markBeatV13ReminderScheduled,
    releaseBeatV13ReminderClaim,
} = require('../../lib/beat-v13-entries');
const { consumeRateLimit, rateLimited } = require('../../lib/rate-limit');

const REMINDER_DELAY_MS = 24 * 60 * 60 * 1000;

function providerId(result) {
    return result?.id || result?.data?.id || '';
}

function isConfigError(error) {
    return /is not configured|must use HTTPS|not a valid URL/i.test(String(error?.message || ''));
}

function isFreshConfirmation(entry, now, ttlHours) {
    if (!entry?.confirmation_provider_id || !entry.confirmation_sent_at) return false;
    const sentAt = Date.parse(entry.confirmation_sent_at);
    const ttlMs = Number(ttlHours || 48) * 60 * 60 * 1000;
    return Number.isFinite(sentAt) && now - sentAt < ttlMs;
}

async function cancelScheduledReminder(providerMessageId, config) {
    if (!providerMessageId) return;
    try {
        await resendRequest(`/emails/${encodeURIComponent(providerMessageId)}/cancel`, config.apiKey, {
            method: 'POST',
        });
    } catch (error) {
        // A duplicate confirmation or a retry can encounter a reminder that
        // Resend has already cancelled or delivered. In either case there is
        // no remaining scheduled message to cancel.
        if (![404, 409].includes(error.status)) throw error;
    }
}

async function sendConfirmation(entry, email, config, now) {
    const token = createSubscriptionToken(email, config.signingSecret, config.ttlHours, now);
    const confirmationUrl = `${config.siteOrigin}/api/email/confirm?token=${encodeURIComponent(token)}`;
    const cancelUrl = `${config.siteOrigin}/api/email/confirm?action=cancel&token=${encodeURIComponent(token)}`;
    const emailKey = crypto.createHash('sha256').update(email).digest('hex').slice(0, 32);
    const result = await resendRequest('/emails', config.apiKey, {
        method: 'POST',
        headers: { 'Idempotency-Key': `beat-v13-confirm-${emailKey}` },
        body: {
            from: config.from,
            to: [email],
            subject: 'Confirm your free Beat V13 registration',
            html: `<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;color:#141821">
                <h1 style="font-size:24px">Confirm your Beat V13 entry</h1>
                <p>Beat V13 entry is free, but one more step is required: confirm this email address before the Round 22 Las Vegas F1 Fantasy team lock on 21 November 2026 at 04:00 UTC.</p>
                <p><a href="${confirmationUrl}" style="display:inline-block;background:#e10600;color:#fff;text-decoration:none;padding:12px 18px;border-radius:7px;font-weight:700">Confirm free registration</a></p>
                <p>You will receive concise V13 early thoughts, post-FP simulation updates and competition instructions after confirming.</p>
                <p style="color:#667085;font-size:13px">This link expires in ${config.ttlHours} hours. If you did not request this, <a href="${cancelUrl}">cancel this registration</a> and no entry will be created.</p>
            </div>`,
            text: `Confirm your free Beat V13 registration:\n\n${confirmationUrl}\n\nOne more step is required: confirm this address before the Round 22 Las Vegas F1 Fantasy team lock on 21 November 2026 at 04:00 UTC. You will receive concise V13 early thoughts, post-FP simulation updates and competition instructions after confirming. This link expires in ${config.ttlHours} hours. If you did not request this, cancel this registration here: ${cancelUrl}`,
        },
    });
    const id = providerId(result);
    if (!id) throw new Error('Resend did not return a confirmation email ID');
    const marked = await markBeatV13ConfirmationSent(entry.id, id, new Date(now));
    if (!marked) throw new Error('The pending Beat V13 entry changed while sending confirmation');
    return { id, token };
}

async function scheduleReminder(entry, email, config, now) {
    if (!entry || entry.status !== 'pending' || entry.reminder_provider_id) return false;
    const claimed = await claimBeatV13Reminder(entry, new Date(now));
    if (!claimed) return false;

    const claimedAt = claimed.reminder_claimed_at;
    const scheduledAt = new Date(now + REMINDER_DELAY_MS).toISOString();
    const token = createSubscriptionToken(email, config.signingSecret, config.ttlHours, now);
    const confirmationUrl = `${config.siteOrigin}/api/email/confirm?token=${encodeURIComponent(token)}`;
    const cancelUrl = `${config.siteOrigin}/api/email/confirm?action=cancel&token=${encodeURIComponent(token)}`;

    let scheduledProviderId = '';
    try {
        const result = await resendRequest('/emails', config.apiKey, {
            method: 'POST',
            headers: { 'Idempotency-Key': `beat-v13-reminder-${entry.id}` },
            body: {
                from: config.from,
                to: [email],
                subject: 'One more step: confirm your Beat V13 entry',
                // resendRequest talks to the REST API directly; REST uses
                // snake_case (the SDK converts scheduledAt for callers).
                scheduled_at: scheduledAt,
                html: `<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;color:#141821">
                    <h1 style="font-size:24px">Your Beat V13 entry is waiting</h1>
                    <p>One more step is required to enter: confirm your email address before the Round 22 team lock.</p>
                    <p><a href="${confirmationUrl}" style="display:inline-block;background:#e10600;color:#fff;text-decoration:none;padding:12px 18px;border-radius:7px;font-weight:700">Confirm free registration</a></p>
                    <p style="color:#667085;font-size:13px">If you did not request this, <a href="${cancelUrl}">cancel this registration</a>.</p>
                </div>`,
                text: `Your Beat V13 entry is waiting. One more step is required: confirm your email address before the Round 22 team lock. Confirm here: ${confirmationUrl}\n\nIf you did not request this, cancel this registration here: ${cancelUrl}`,
            },
        });
        const id = providerId(result);
        if (!id) throw new Error('Resend did not return a reminder email ID');
        scheduledProviderId = id;
        const marked = await markBeatV13ReminderScheduled(entry.id, claimedAt, id, scheduledAt, new Date(now));
        if (!marked) {
            // Confirmation may have won a race after the claim but before the
            // provider response. Do not leave a reminder scheduled for an
            // already-confirmed entry.
            await cancelScheduledReminder(id, config);
            try { await releaseBeatV13ReminderClaim(entry.id, claimedAt); }
            catch (releaseError) { console.error('Could not release Beat V13 reminder claim:', releaseError.message); }
            return false;
        }
        return true;
    } catch (error) {
        if (scheduledProviderId) {
            try { await cancelScheduledReminder(scheduledProviderId, config); }
            catch (cancelError) { console.error('Could not cancel orphaned Beat V13 reminder:', cancelError.message); }
        }
        try { await releaseBeatV13ReminderClaim(entry.id, claimedAt); }
        catch (releaseError) { console.error('Could not release Beat V13 reminder claim:', releaseError.message); }
        throw error;
    }
}

module.exports = async function subscribe(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'POST');

    if (req.method !== 'POST') {
        return res.status(405).json({ ok: false, message: 'Method not allowed.' });
    }

    let config;
    try {
        config = getConfig();
        getBeatV13EntryConfig();
    } catch (error) {
        console.error('Beat V13 registration is not configured:', error.message);
        return res.status(503).json({ ok: false, message: 'Beat V13 registration is temporarily unavailable. Please try again later.' });
    }

    if (!isAllowedRequestOrigin(req, config.siteOrigin)) {
        return res.status(403).json({ ok: false, message: 'Request origin was not accepted.' });
    }

    if (!isBeatV13RegistrationOpen()) {
        return res.status(410).json({
            ok: false,
            message: 'Beat V13 registration closed at the Round 22 F1 Fantasy team lock.',
        });
    }

    let body = req.body || {};
    if (typeof body === 'string') {
        try { body = JSON.parse(body); }
        catch (_) { return res.status(400).json({ ok: false, message: 'Invalid request. Please try again.' }); }
    }

    // Honeypot fields are intentionally answered as success to avoid teaching bots.
    if (body.website) {
        return res.status(202).json({
            ok: true,
            entry_status: 'pending',
            message: 'Confirmation email sent. One more step is required: open the email and confirm your address before the Round 22 lock.',
        });
    }

    const email = normalizeEmail(body.email);
    if (!isValidEmail(email)) {
        return res.status(400).json({ ok: false, message: 'Enter a valid email address, then try again.' });
    }
    if (body.consent !== true) {
        return res.status(400).json({ ok: false, message: 'Please confirm your free Beat V13 registration, then try again.' });
    }
    const throttle = consumeRateLimit(req, 'beat-v13-subscribe', { limit: 5, windowMs: 60 * 60 * 1000 });
    if (!throttle.allowed) return rateLimited(res, throttle);

    const now = Date.now();
    try {
        const existing = await findBeatV13Entry(email);
        if (existing?.status === 'withdrawn' && existing.reminder_provider_id) {
            await cancelScheduledReminder(existing.reminder_provider_id, config);
        }
        const entry = await ensurePendingBeatV13Entry(email);

        if (entry.status === 'confirmed') {
            return res.status(202).json({
                ok: true,
                entry_status: 'confirmed',
                message: 'This address is already confirmed. You’re officially entered; no new confirmation email was sent.',
            });
        }

        let confirmationSent = isFreshConfirmation(entry, now, config.ttlHours);
        if (!confirmationSent) {
            await sendConfirmation(entry, email, config, now);
            confirmationSent = true;
        }

        try {
            await scheduleReminder(entry, email, config, now);
        } catch (error) {
            console.error('Could not schedule Beat V13 reminder:', error.message);
            return res.status(502).json({
                ok: false,
                message: confirmationSent
                    ? 'The confirmation email was sent, but its one-time 24-hour reminder could not be scheduled. Please try again shortly.'
                    : 'We could not schedule the confirmation reminder. Please try again shortly.',
            });
        }

        return res.status(202).json({
            ok: true,
            entry_status: 'pending',
            message: 'Confirmation email sent. One more step is required: open the email and confirm your address before the Round 22 lock.',
        });
    } catch (error) {
        console.error('Could not start Beat V13 registration:', error.message);
        if (isConfigError(error)) {
            return res.status(503).json({ ok: false, message: 'Beat V13 registration is temporarily unavailable. Please try again later.' });
        }
        return res.status(502).json({
            ok: false,
            message: 'We could not send the confirmation email. Please try again shortly.',
        });
    }
};

module.exports._cancelScheduledReminder = cancelScheduledReminder;
module.exports._scheduleReminder = scheduleReminder;
