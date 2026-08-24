'use strict';

const { resendRequest } = require('./email-subscriptions');

const PIT_WALL_SEGMENT_NAME = 'Pit Wall Members';
// Reuse the original production list. Creating a renamed fourth segment fails
// on Resend's three-segment plan and prevents confirmation from completing.
const BEAT_V13_SEGMENT_NAME = 'V13 Simulation Updates';
const segmentCache = new Map();

async function ensureSegment(name, configuredId = '') {
    const apiKey = String(process.env.RESEND_API_KEY || '').trim();
    if (!apiKey) throw new Error('RESEND_API_KEY is not configured');
    if (segmentCache.has(name)) return segmentCache.get(name);

    const configured = String(configuredId || '').trim();
    if (configured) {
        try {
            const segment = await resendRequest(`/segments/${encodeURIComponent(configured)}`, apiKey);
            if (segment?.id) {
                segmentCache.set(name, segment.id);
                return segment.id;
            }
        } catch (_) {
            // A deleted or rotated segment is recovered by name below.
        }
    }

    const listed = await resendRequest('/segments', apiKey);
    const existing = (listed?.data || []).find(segment => segment.name === name);
    if (existing?.id) {
        segmentCache.set(name, existing.id);
        return existing.id;
    }
    const created = await resendRequest('/segments', apiKey, {
        method: 'POST',
        body: { name },
    });
    if (!created?.id) throw new Error(`Resend did not return a segment id for ${name}`);
    segmentCache.set(name, created.id);
    return created.id;
}

async function ensurePitWallSegment() {
    return ensureSegment(PIT_WALL_SEGMENT_NAME, process.env.RESEND_PIT_WALL_SEGMENT_ID);
}

async function ensureBeatV13Segment() {
    return ensureSegment(BEAT_V13_SEGMENT_NAME, process.env.RESEND_SIM_UPDATES_SEGMENT_ID);
}

async function activeSegmentContacts(segmentId) {
    const apiKey = String(process.env.RESEND_API_KEY || '').trim();
    if (!apiKey) throw new Error('RESEND_API_KEY is not configured');
    const contacts = await resendRequest(
        `/segments/${encodeURIComponent(segmentId)}/contacts?limit=100`,
        apiKey,
    );
    return (contacts?.data || []).filter(contact => contact.unsubscribed !== true && contact.email);
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

module.exports = {
    BEAT_V13_SEGMENT_NAME,
    PIT_WALL_SEGMENT_NAME,
    activeSegmentContacts,
    ensureSegment,
    addPitWallContact,
    ensureBeatV13Segment,
    ensurePitWallSegment,
};
