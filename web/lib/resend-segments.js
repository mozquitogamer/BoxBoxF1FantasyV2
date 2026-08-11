'use strict';

const { resendRequest } = require('./email-subscriptions');

const PIT_WALL_SEGMENT_NAME = 'Pit Wall Members';

async function ensurePitWallSegment() {
    const configured = String(process.env.RESEND_PIT_WALL_SEGMENT_ID || '').trim();
    if (configured) return configured;
    const apiKey = String(process.env.RESEND_API_KEY || '').trim();
    if (!apiKey) throw new Error('RESEND_API_KEY is not configured');

    const listed = await resendRequest('/segments', apiKey);
    const existing = (listed?.data || []).find(segment => segment.name === PIT_WALL_SEGMENT_NAME);
    if (existing?.id) return existing.id;
    const created = await resendRequest('/segments', apiKey, {
        method: 'POST',
        body: { name: PIT_WALL_SEGMENT_NAME },
    });
    if (!created?.id) throw new Error('Resend did not return a Pit Wall segment id');
    return created.id;
}

async function addPitWallContact(email) {
    const apiKey = String(process.env.RESEND_API_KEY || '').trim();
    const segmentId = await ensurePitWallSegment();
    try {
        await resendRequest('/contacts', apiKey, {
            method: 'POST',
            body: { email, unsubscribed: false, segments: [{ id: segmentId }] },
        });
    } catch (error) {
        // Existing contacts can be attached to the segment by email.
        await resendRequest(
            `/contacts/${encodeURIComponent(email)}/segments/${encodeURIComponent(segmentId)}`,
            apiKey,
            { method: 'POST' },
        );
    }
    return segmentId;
}

module.exports = { PIT_WALL_SEGMENT_NAME, addPitWallContact, ensurePitWallSegment };
