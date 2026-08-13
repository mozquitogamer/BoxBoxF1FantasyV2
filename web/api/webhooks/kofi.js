'use strict';

const {
    authAdminRequest,
    getMemberConfig,
    isValidEmail,
    normalizeEmail,
    restRequest,
    safeEqual,
} = require('../../lib/member-system');
const { resendRequest } = require('../../lib/email-subscriptions');
const { addPitWallContact } = require('../../lib/resend-segments');

const MEMBERSHIP_GRACE_DAYS = 35;

function parseKofiPayload(req) {
    let body = req.body;
    if (typeof body === 'string') {
        const form = new URLSearchParams(body);
        body = form.has('data') ? { data: form.get('data') } : JSON.parse(body);
    }
    if (body?.data && typeof body.data === 'string') return JSON.parse(body.data);
    return body && typeof body === 'object' ? body : {};
}

function sanitizedKofiPayload(payload) {
    return {
        timestamp: payload.timestamp || null,
        amount: payload.amount || null,
        currency: payload.currency || null,
        is_first_subscription_payment: payload.is_first_subscription_payment === true
            || String(payload.is_first_subscription_payment).toLowerCase() === 'true',
        kofi_transaction_id: payload.kofi_transaction_id || null,
    };
}

function paidUntil(timestamp) {
    const paidAt = Date.parse(timestamp || '');
    const start = Number.isFinite(paidAt) ? paidAt : Date.now();
    return new Date(start + MEMBERSHIP_GRACE_DAYS * 24 * 60 * 60 * 1000).toISOString();
}

async function findOrCreateMember(email) {
    const profiles = await restRequest(
        `member_profiles?email=eq.${encodeURIComponent(email)}&select=user_id,email&limit=1`,
        { service: true },
    );
    if (profiles?.[0]) return profiles[0];

    try {
        const user = await authAdminRequest('/admin/users', {
            method: 'POST',
            body: {
                email,
                email_confirm: true,
                user_metadata: { source: 'kofi_pit_wall' },
            },
        });
        return { user_id: user.id, email: user.email || email, created: true };
    } catch (error) {
        // A racing request may have created the account after our first lookup.
        const retry = await restRequest(
            `member_profiles?email=eq.${encodeURIComponent(email)}&select=user_id,email&limit=1`,
            { service: true },
        );
        if (retry?.[0]) return retry[0];
        throw error;
    }
}

async function syncResendMember(email) {
    if (!process.env.RESEND_API_KEY) return;
    await addPitWallContact(email);
}

async function sendWelcome(email, messageId) {
    if (!process.env.RESEND_API_KEY || !process.env.RESEND_FROM) return;
    const origin = getMemberConfig().siteOrigin;
    await resendRequest('/emails', process.env.RESEND_API_KEY, {
        method: 'POST',
        headers: { 'Idempotency-Key': `pit-wall-welcome-${messageId}` },
        body: {
            from: process.env.RESEND_FROM,
            to: [email],
            subject: 'Welcome to the BoxBox Pit Wall',
            html: `<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;color:#141821">
                <p style="font-weight:700">BoxBox<span style="color:#e10600">F1</span>Fantasy · Pit Wall</p>
                <h1 style="font-size:24px">Your member tools are ready</h1>
                <p>Thank you for supporting the channel. Open Pit Wall with this same Ko-fi email, choose <strong>Create or reset password</strong>, then save your current F1 Fantasy team once. Future simulation updates will include a suggestion based on your lineup.</p>
                <p><a href="${origin}/?pitwall=1#optimizer" style="display:inline-block;background:#e10600;color:#fff;text-decoration:none;padding:12px 18px;border-radius:7px;font-weight:700">Create my Pit Wall password</a></p>
                <p style="color:#667085;font-size:13px">All public predictions and tools remain free. Pit Wall membership adds memory, delivery and personalization.</p>
            </div>`,
            text: `Welcome to the BoxBox Pit Wall.\n\nOpen Pit Wall with this same Ko-fi email, choose Create or reset password, then save your team: ${origin}/?pitwall=1#optimizer\n\nFuture simulation updates will include a suggestion based on your lineup.`,
        },
    });
}

module.exports = async function kofiWebhook(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'POST');
    if (req.method !== 'POST') return res.status(405).json({ ok: false });

    let payload;
    try {
        payload = parseKofiPayload(req);
    } catch (_) {
        return res.status(400).json({ ok: false, message: 'Invalid Ko-fi payload.' });
    }

    const expectedToken = String(process.env.KOFI_VERIFICATION_TOKEN || '').trim();
    if (!expectedToken || !safeEqual(payload.verification_token, expectedToken)) {
        return res.status(401).json({ ok: false });
    }

    const isSubscription = payload.is_subscription_payment === true
        || String(payload.is_subscription_payment).toLowerCase() === 'true';
    const tierName = String(payload.tier_name || '').trim();
    const expectedTier = String(process.env.KOFI_PIT_WALL_TIER_NAME || 'Pit Wall').trim();
    if (!isSubscription || tierName.toLowerCase() !== expectedTier.toLowerCase()) {
        return res.status(200).json({ ok: true, ignored: true });
    }

    const messageId = String(payload.message_id || '').trim();
    const email = normalizeEmail(payload.email);
    if (!messageId || !isValidEmail(email)) {
        return res.status(400).json({ ok: false, message: 'Ko-fi membership data was incomplete.' });
    }

    try {
        const existing = await restRequest(
            `kofi_webhook_events?message_id=eq.${encodeURIComponent(messageId)}&select=processed&limit=1`,
            { service: true },
        );
        if (existing?.[0]?.processed) return res.status(200).json({ ok: true, duplicate: true });
        if (!existing?.length) {
            await restRequest('kofi_webhook_events', {
                service: true,
                method: 'POST',
                prefer: 'return=minimal',
                body: {
                    message_id: messageId,
                    event_type: String(payload.type || 'Subscription'),
                    payment_email: email,
                    tier_name: tierName,
                    payload: sanitizedKofiPayload(payload),
                },
            });
        }

        const member = await findOrCreateMember(email);
        await restRequest('member_entitlements?on_conflict=user_id,provider', {
            service: true,
            method: 'POST',
            prefer: 'resolution=merge-duplicates,return=minimal',
            body: {
                user_id: member.user_id,
                provider: 'kofi',
                external_customer_id: email,
                status: 'active',
                current_period_end: paidUntil(payload.timestamp),
                metadata: {
                    tier_name: tierName,
                    last_payment_at: payload.timestamp || new Date().toISOString(),
                    last_message_id: messageId,
                    kofi_transaction_id: payload.kofi_transaction_id || null,
                },
            },
        });

        await Promise.allSettled([
            syncResendMember(email),
            (payload.is_first_subscription_payment === true
                || String(payload.is_first_subscription_payment).toLowerCase() === 'true'
                || member.created)
                ? sendWelcome(email, messageId)
                : Promise.resolve(),
        ]);

        await restRequest(`kofi_webhook_events?message_id=eq.${encodeURIComponent(messageId)}`, {
            service: true,
            method: 'PATCH',
            prefer: 'return=minimal',
            body: {
                user_id: member.user_id,
                processed: true,
                processed_at: new Date().toISOString(),
                last_error: null,
            },
        });
        return res.status(200).json({ ok: true });
    } catch (error) {
        console.error('Ko-fi webhook failed:', error.message);
        await restRequest(`kofi_webhook_events?message_id=eq.${encodeURIComponent(messageId)}`, {
            service: true,
            method: 'PATCH',
            prefer: 'return=minimal',
            body: { last_error: String(error.message).slice(0, 500) },
        }).catch(() => null);
        return res.status(500).json({ ok: false });
    }
};

module.exports.findOrCreateMember = findOrCreateMember;
module.exports.paidUntil = paidUntil;
module.exports.parseKofiPayload = parseKofiPayload;
module.exports.sanitizedKofiPayload = sanitizedKofiPayload;
