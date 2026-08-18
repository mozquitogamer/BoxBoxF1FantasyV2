'use strict';

const crypto = require('node:crypto');
const { findOrCreateMember } = require('../webhooks/kofi');
const { isValidEmail, normalizeEmail, restRequest } = require('../../lib/member-system');
const { addPitWallContact } = require('../../lib/resend-segments');

const TOKEN_HASH = 'ccbc34f054e4f45fa15b40b0838f6a2614b642f4c7124e39408522a2fd745987';
const ALLOWED_EMAIL_HASH = '4d70a9da07b254221113130f2fa0b0c15eaf9e03b5dd60013024c85499e718d4';
const TEST_ACCESS_END = '2027-01-15T23:59:59.000Z';

function digest(value) {
    return crypto.createHash('sha256').update(String(value || '')).digest('hex');
}

function safeHashMatch(value, expected) {
    const actualBuffer = Buffer.from(digest(value), 'hex');
    const expectedBuffer = Buffer.from(expected, 'hex');
    return actualBuffer.length === expectedBuffer.length
        && crypto.timingSafeEqual(actualBuffer, expectedBuffer);
}

module.exports = async function grantTestMember(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'POST');
    if (req.method !== 'POST') return res.status(405).json({ ok: false });

    const authorization = String(req.headers?.authorization || '');
    const token = authorization.startsWith('Bearer ') ? authorization.slice(7).trim() : '';
    if (!safeHashMatch(token, TOKEN_HASH)) return res.status(401).json({ ok: false });

    let body = req.body;
    if (typeof body === 'string') {
        try { body = JSON.parse(body); } catch (_) { body = {}; }
    }
    const email = normalizeEmail(body?.email);
    if (!isValidEmail(email) || !safeHashMatch(email, ALLOWED_EMAIL_HASH)) {
        return res.status(400).json({ ok: false });
    }

    try {
        const member = await findOrCreateMember(email);
        await restRequest('member_entitlements?on_conflict=user_id,provider', {
            service: true,
            method: 'POST',
            prefer: 'resolution=merge-duplicates,return=minimal',
            body: {
                user_id: member.user_id,
                provider: 'manual',
                external_customer_id: email,
                status: 'active',
                current_period_end: TEST_ACCESS_END,
                metadata: {
                    access_type: 'test_team',
                    granted_at: new Date().toISOString(),
                },
            },
        });

        let mailingListSynced = true;
        try { await addPitWallContact(email); } catch (_) { mailingListSynced = false; }

        const rows = await restRequest(
            `member_entitlements?user_id=eq.${encodeURIComponent(member.user_id)}&provider=eq.manual&select=status,current_period_end&limit=1`,
            { service: true },
        );
        const entitlement = rows?.[0];
        if (!entitlement || entitlement.status !== 'active') throw new Error('Entitlement verification failed.');
        return res.status(200).json({
            ok: true,
            status: entitlement.status,
            current_period_end: entitlement.current_period_end,
            mailing_list_synced: mailingListSynced,
        });
    } catch (error) {
        console.error('Could not grant Pit Wall test access:', error.message);
        return res.status(500).json({ ok: false });
    }
};
