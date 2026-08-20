'use strict';

const crypto = require('node:crypto');

const SUPABASE_TABLE = 'beat_v13_entries';
const DEFAULT_SESSION_MAX_AGE = 365 * 24 * 60 * 60;
const REMINDER_CLAIM_TIMEOUT_MS = 15 * 60 * 1000;
const SESSION_COOKIE_NAME = '__Host-boxbox_beat_v13_session';

function required(value, name) {
    const result = String(value || '').trim();
    if (!result) throw new Error(`${name} is not configured`);
    return result;
}

function getBeatV13EntryConfig() {
    const supabaseUrl = required(
        process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL,
        'NEXT_PUBLIC_SUPABASE_URL',
    ).replace(/\/$/, '');
    let parsedUrl;
    try { parsedUrl = new URL(supabaseUrl); }
    catch (_) { throw new Error('NEXT_PUBLIC_SUPABASE_URL is not a valid URL'); }
    if (parsedUrl.protocol !== 'https:' && process.env.VERCEL_ENV === 'production') {
        throw new Error('NEXT_PUBLIC_SUPABASE_URL must use HTTPS in production');
    }
    return {
        supabaseUrl: parsedUrl.origin,
        serviceKey: required(
            process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SECRET_KEY,
            'SUPABASE_SERVICE_ROLE_KEY',
        ),
    };
}

async function readJson(response) {
    const text = await response.text();
    if (!text) return null;
    try { return JSON.parse(text); }
    catch (_) { return text; }
}

async function entryRequest(path, options = {}) {
    const config = getBeatV13EntryConfig();
    const headers = {
        apikey: config.serviceKey,
        Authorization: `Bearer ${config.serviceKey}`,
        'Content-Type': 'application/json',
        ...(options.headers || {}),
    };
    const response = await fetch(`${config.supabaseUrl}/rest/v1/${path}`, {
        method: options.method || 'GET',
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
    const data = await readJson(response);
    if (!response.ok) {
        const message = data?.message || data?.msg || data?.hint || `Supabase request failed (${response.status})`;
        const error = new Error(message);
        error.status = response.status;
        error.details = data;
        throw error;
    }
    return data;
}

function filterValue(value) {
    return encodeURIComponent(String(value));
}

function selectColumns() {
    return [
        'id',
        'email_normalized',
        'status',
        'confirmation_sent_at',
        'confirmation_provider_id',
        'confirmed_at',
        'reminder_claimed_at',
        'reminder_scheduled_at',
        'reminder_provider_id',
        'reminder_sent_at',
        'withdrawn_at',
        // Private registration helpers need their own delivery fields. The
        // public leaderboard uses publicSelectColumns() below and never
        // selects email_normalized.
        'official_team_id',
        'official_team_name',
        'official_team_slot',
        'official_league_id',
        'official_league_code',
        'official_team_linked_at',
        'team_link_status',
        'team_linked_at',
        'last_synced_at',
        'created_at',
        'updated_at',
    ].join(',');
}

function publicSelectColumns() {
    return [
        'id',
        'status',
        'confirmed_at',
        'official_team_id',
        'official_team_name',
        'official_team_slot',
        'official_league_id',
        'official_league_code',
        'official_team_linked_at',
        'team_link_status',
        'team_linked_at',
        'last_synced_at',
        'updated_at',
    ].join(',');
}

async function listBeatV13Entries() {
    // Public leaderboard route calls this explicit, PII-free projection. The
    // private registration helpers above continue to use selectColumns().
    return entryRequest(`${SUPABASE_TABLE}?select=${publicSelectColumns()}&order=created_at.asc`);
}

async function findBeatV13Entry(email) {
    const rows = await entryRequest(
        `${SUPABASE_TABLE}?email_normalized=eq.${filterValue(email)}&select=${selectColumns()}&limit=1`,
    );
    return Array.isArray(rows) ? (rows[0] || null) : null;
}

async function findBeatV13EntryById(id) {
    const rows = await entryRequest(
        `${SUPABASE_TABLE}?id=eq.${filterValue(id)}&select=${selectColumns()}&limit=1`,
    );
    return Array.isArray(rows) ? (rows[0] || null) : null;
}

async function insertBeatV13Entry(email) {
    const rows = await entryRequest(SUPABASE_TABLE, {
        method: 'POST',
        headers: {
            Prefer: 'resolution=ignore-duplicates,return=representation',
        },
        body: { email_normalized: email, status: 'pending' },
    });
    return Array.isArray(rows) ? (rows[0] || null) : null;
}

async function updateBeatV13Entry(id, values, filters = {}) {
    const query = [
        `id=eq.${filterValue(id)}`,
        ...Object.entries(filters).map(([key, value]) => {
            if (value === null) return `${key}=is.null`;
            return `${key}=eq.${filterValue(value)}`;
        }),
        `select=${selectColumns()}`,
    ].join('&');
    const rows = await entryRequest(`${SUPABASE_TABLE}?${query}`, {
        method: 'PATCH',
        headers: { Prefer: 'return=representation' },
        body: values,
    });
    return Array.isArray(rows) ? (rows[0] || null) : null;
}

async function ensurePendingBeatV13Entry(email) {
    let entry = await findBeatV13Entry(email);
    if (!entry) {
        entry = await insertBeatV13Entry(email);
        if (!entry) entry = await findBeatV13Entry(email);
    }
    if (!entry) throw new Error('Supabase did not return the Beat V13 entry');

    if (entry.status === 'withdrawn') {
        // A withdrawn address may deliberately register again. Reset only the
        // confirmation/reminder delivery state; the generated entrant ID is
        // retained so any private references remain stable.
        if (entry.reminder_provider_id) {
            // The caller will cancel this ID before asking for a fresh reminder.
            // Keep it in the returned row until cancellation is complete.
        }
        entry = await updateBeatV13Entry(entry.id, {
            status: 'pending',
            confirmation_sent_at: null,
            confirmation_provider_id: null,
            confirmed_at: null,
            reminder_claimed_at: null,
            reminder_scheduled_at: null,
            reminder_provider_id: null,
            reminder_sent_at: null,
            withdrawn_at: null,
        }, { status: 'withdrawn' });
        if (!entry) entry = await findBeatV13Entry(email);
    }
    if (!entry) throw new Error('Could not prepare the Beat V13 entry');
    return entry;
}

function isFreshTimestamp(value, now = Date.now(), maxAgeMs = REMINDER_CLAIM_TIMEOUT_MS) {
    const time = Date.parse(value || '');
    return Number.isFinite(time) && now - time < maxAgeMs;
}

async function claimBeatV13Reminder(entry, now = new Date()) {
    if (!entry || entry.status !== 'pending' || entry.reminder_provider_id) return null;
    if (isFreshTimestamp(entry.reminder_claimed_at, now.getTime())) return null;

    const claimedAt = now.toISOString();
    const filters = { status: 'pending', reminder_provider_id: null };
    if (entry.reminder_claimed_at) filters.reminder_claimed_at = entry.reminder_claimed_at;
    else filters.reminder_claimed_at = null;

    return updateBeatV13Entry(entry.id, { reminder_claimed_at: claimedAt }, filters);
}

async function releaseBeatV13ReminderClaim(entryId, claimedAt) {
    if (!entryId || !claimedAt) return;
    await updateBeatV13Entry(entryId, { reminder_claimed_at: null }, { reminder_claimed_at: claimedAt });
}

async function markBeatV13ReminderScheduled(entryId, claimedAt, providerId, scheduledAt, sentAt = new Date()) {
    return updateBeatV13Entry(entryId, {
        reminder_claimed_at: null,
        reminder_provider_id: providerId,
        reminder_scheduled_at: scheduledAt,
        reminder_sent_at: sentAt.toISOString(),
    }, { status: 'pending', reminder_claimed_at: claimedAt, reminder_provider_id: null });
}

async function markBeatV13ConfirmationSent(entryId, providerId, sentAt = new Date()) {
    return updateBeatV13Entry(entryId, {
        confirmation_provider_id: providerId,
        confirmation_sent_at: sentAt.toISOString(),
    });
}

async function confirmBeatV13Entry(entryId, now = new Date()) {
    const existing = await findBeatV13EntryById(entryId);
    if (!existing) return null;
    if (existing.status === 'confirmed') return existing;
    if (existing.status !== 'pending') return null;
    return updateBeatV13Entry(entryId, {
        status: 'confirmed',
        confirmed_at: now.toISOString(),
        reminder_claimed_at: null,
    }, { status: 'pending' });
}

async function withdrawBeatV13Entry(entryId, now = new Date()) {
    return updateBeatV13Entry(entryId, {
        status: 'withdrawn',
        withdrawn_at: now.toISOString(),
        reminder_claimed_at: null,
    }, { status: 'pending' });
}

function sessionSecret() {
    return String(
        process.env.BEAT_V13_SESSION_SECRET
        || process.env.SUBSCRIPTION_SIGNING_SECRET
        || process.env.MEMBER_NOTIFICATION_SECRET
        || '',
    ).trim();
}

function validEntrantId(value) {
    return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(String(value || ''));
}

function signSessionValue(entrantId, secret) {
    return crypto.createHmac('sha256', String(secret)).update(String(entrantId)).digest('base64url');
}

function beatV13SessionCookie(entrantId, secret = sessionSecret(), maxAgeSeconds = DEFAULT_SESSION_MAX_AGE) {
    if (!validEntrantId(entrantId)) throw new Error('A valid entrant ID is required');
    if (!secret) throw new Error('BEAT_V13_SESSION_SECRET is not configured');
    const value = `${entrantId}.${signSessionValue(entrantId, secret)}`;
    return `${SESSION_COOKIE_NAME}=${value}; Path=/; Max-Age=${Math.max(0, Math.floor(maxAgeSeconds))}; HttpOnly; Secure; SameSite=Strict`;
}

function verifyBeatV13SessionCookie(value, secret = sessionSecret()) {
    if (!secret || typeof value !== 'string') return null;
    const [entrantId, suppliedSignature, extra] = value.split('.');
    if (extra || !validEntrantId(entrantId) || !suppliedSignature) return null;
    const expected = Buffer.from(signSessionValue(entrantId, secret));
    const supplied = Buffer.from(suppliedSignature);
    if (expected.length !== supplied.length || !crypto.timingSafeEqual(expected, supplied)) return null;
    return entrantId;
}

function parseBeatV13Session(req, secret = sessionSecret()) {
    const cookies = String(req?.headers?.cookie || '').split(';').reduce((result, part) => {
        const separator = part.indexOf('=');
        if (separator < 1) return result;
        const name = part.slice(0, separator).trim();
        const value = part.slice(separator + 1).trim();
        result[name] = value;
        return result;
    }, {});
    return verifyBeatV13SessionCookie(cookies[SESSION_COOKIE_NAME], secret);
}

module.exports = {
    DEFAULT_SESSION_MAX_AGE,
    REMINDER_CLAIM_TIMEOUT_MS,
    SESSION_COOKIE_NAME,
    beatV13SessionCookie,
    claimBeatV13Reminder,
    confirmBeatV13Entry,
    ensurePendingBeatV13Entry,
    entryRequest,
    findBeatV13Entry,
    findBeatV13EntryById,
    listBeatV13Entries,
    getBeatV13EntryConfig,
    markBeatV13ConfirmationSent,
    markBeatV13ReminderScheduled,
    parseBeatV13Session,
    releaseBeatV13ReminderClaim,
    sessionSecret,
    updateBeatV13Entry,
    verifyBeatV13SessionCookie,
    withdrawBeatV13Entry,
};
