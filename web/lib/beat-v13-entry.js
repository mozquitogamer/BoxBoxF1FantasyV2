'use strict';

const crypto = require('node:crypto');

const { findLeagueTeams, getPublicLeagueLeaderboard } = require('./f1-fantasy');
const emailAuth = require('./email-subscriptions');
const entryStore = require('./beat-v13-entries');

const BEAT_V13_SESSION_COOKIE = '__Host-boxbox_beat_v13_session';
const BEAT_V13_BROWSER_COOKIE = '__Host-boxbox_beat_v13';
const F1_SYNC_LEAGUE_CODE = 'P1JZAGNMP04';
const F1_SYNC_LEAGUE_ID = Number(process.env.F1_FANTASY_LEAGUE_ID || 160604);
const TEAM_SELECTION_TTL_MS = 10 * 60 * 1000;

function firstValue(row, keys) {
    if (!row || typeof row !== 'object') return null;
    for (const key of keys) {
        const value = row[key];
        if (value !== undefined && value !== null && value !== '') return value;
    }
    return null;
}

function normalizeEntry(entry) {
    const row = entry && typeof entry === 'object' ? entry : {};
    const status = String(firstValue(row, ['status', 'entry_status', 'registration_status']) || '').toLowerCase();
    const confirmed = Boolean(firstValue(row, ['confirmed_at', 'confirmedAt', 'email_confirmed_at', 'verified_at']))
        || ['confirmed', 'verified'].includes(status);
    const teamId = String(firstValue(row, ['official_team_id', 'officialTeamId', 'f1_team_id', 'f1TeamId', 'team_id', 'teamId']) || '').trim();
    const teamName = String(firstValue(row, ['official_team_name', 'officialTeamName', 'f1_team_name', 'f1TeamName', 'team_name', 'teamName']) || '').replace(/\s+/g, ' ').trim().slice(0, 100);
    const teamSlot = Number(firstValue(row, ['official_team_slot', 'officialTeamSlot', 'f1_team_slot', 'f1TeamSlot', 'team_slot', 'teamSlot', 'slot']));
    const teamStatus = String(firstValue(row, ['team_link_status', 'teamLinkStatus', 'f1_team_status', 'f1TeamStatus']) || 'active').toLowerCase();
    return {
        ...row,
        id: String(firstValue(row, ['id', 'entry_id', 'entryId']) || '').trim(),
        confirmed,
        linked: Boolean(teamId && teamName && Number.isInteger(teamSlot) && teamSlot >= 1 && teamSlot <= 3 && teamStatus === 'active'),
        official_team_id: teamId,
        official_team_name: teamName,
        team_slot: Number.isInteger(teamSlot) ? teamSlot : null,
    };
}

function helper(...names) {
    const modules = [emailAuth, entryStore];
    for (const modulePath of ['./beat-v13-session', './beat-v13-auth']) {
        try { modules.push(require(modulePath)); } catch (_) { /* optional registration helper */ }
    }
    for (const name of names) {
        for (const module of modules) {
            if (typeof module?.[name] === 'function') return module[name].bind(module);
        }
    }
    return null;
}

async function getBeatV13Session(req, res) {
    const read = helper(
        'getBeatV13Session',
        'readBeatV13Session',
        'getBeatV13RegistrationSession',
        'readBeatV13RegistrationSession',
    );
    if (read) return read(req, res);
    // The registration workstream's helper intentionally exposes a signed
    // entrant ID parser rather than a browser-readable session object. Resolve
    // that ID through the service-role entry store before any handler uses it.
    const parse = helper('parseBeatV13Session');
    const findById = helper('findBeatV13EntryById');
    if (!parse || !findById) return null;
    const id = parse(req);
    if (!id) return null;
    const entry = await findById(id);
    return entry ? { entry_id: id, entry } : null;
}

function sessionEntryId(session) {
    return String(firstValue(session, ['entry_id', 'entryId', 'entrant_id', 'entrantId', 'user_id', 'userId'])
        || firstValue(session?.entry, ['id', 'entry_id', 'entryId'])
        || firstValue(session?.record, ['id', 'entry_id', 'entryId']) || '').trim();
}

function sessionEntryHint(session) {
    const candidate = session?.entry || session?.record || session?.entrant || session;
    return candidate && typeof candidate === 'object' ? normalizeEntry(candidate) : null;
}

async function getEntryForSession(session) {
    if (!session) return null;
    const id = sessionEntryId(session);
    const hint = sessionEntryHint(session);
    try {
        const findById = helper('findBeatV13EntryById');
        if (id && findById) {
            const row = await findById(id);
            if (row) return normalizeEntry(row);
        }
        const findByEmail = helper('findBeatV13Entry');
        const email = String(firstValue(session, ['email']) || firstValue(hint, ['email']) || '').trim().toLowerCase();
        if (email && findByEmail) {
            const row = await findByEmail(email);
            if (row) return normalizeEntry(row);
        }
    } catch (error) {
        if (!isMissingBeatEntryTable(error)) throw error;
    }
    // The signed helper may already have loaded the row. This fallback is
    // useful during the registration migration and does not trust browser
    // input; the row came from the signed session helper.
    return hint;
}

function isMissingBeatEntryTable(error) {
    return error?.status === 404 || /relation .*beat_v13_entries.*does not exist|schema cache/i.test(String(error?.message || ''));
}

function publicEntryState(entry, v13Points = null, feedTeam = null) {
    const row = normalizeEntry(entry);
    const live = feedTeam || null;
    const points = live ? Number(live.points) : null;
    const hasPoints = Number.isFinite(points);
    return {
        authenticated: true,
        confirmed: row.confirmed,
        linked: row.linked,
        scored: Boolean(live),
        official_team_name: row.official_team_name || null,
        team_slot: row.team_slot,
        points: hasPoints ? points : null,
        rank: live?.rank || null,
        margin_vs_v13: hasPoints && Number.isFinite(Number(v13Points)) ? points - Number(v13Points) : null,
        last_linked_at: firstValue(row, ['official_team_linked_at', 'officialTeamLinkedAt', 'team_linked_at', 'teamLinkedAt', 'linked_at', 'linkedAt']) || null,
        last_synced_at: firstValue(row, ['last_synced_at', 'lastSyncedAt']) || null,
    };
}

function signingSecret() {
    const configured = String(process.env.SUBSCRIPTION_SIGNING_SECRET || '').trim();
    if (configured) return configured;
    const read = helper('getBeatV13SigningSecret', 'beatV13SigningSecret', 'sessionSecret');
    if (read) {
        const value = read();
        if (value) return String(value);
    }
    throw new Error('Beat V13 signing is not configured yet.');
}

function selectionSignature(payload, secret = signingSecret()) {
    return crypto.createHmac('sha256', secret)
        .update(`boxbox-beat-v13-team:v1:${payload}`)
        .digest('base64url');
}

function createTeamSelectionToken(team, entryId, now = Date.now()) {
    const payload = Buffer.from(JSON.stringify({
        entry_id: String(entryId || '').slice(0, 160),
        id: String(team?.id || '').slice(0, 160),
        name: String(team?.name || '').trim().slice(0, 100),
        slot: Number(team?.slot),
        exp: now + TEAM_SELECTION_TTL_MS,
    }), 'utf8').toString('base64url');
    return `${payload}.${selectionSignature(payload)}`;
}

function verifyTeamSelectionToken(token, entryId, now = Date.now()) {
    const [payload, supplied, extra] = String(token || '').split('.');
    if (!payload || !supplied || extra) return null;
    let expected;
    try { expected = selectionSignature(payload); } catch (_) { return null; }
    const left = Buffer.from(supplied);
    const right = Buffer.from(expected);
    if (left.length !== right.length || !crypto.timingSafeEqual(left, right)) return null;
    try {
        const value = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
        if (String(value.entry_id) !== String(entryId || '') || !Number.isFinite(value.exp) || value.exp < now) return null;
        if (!value.id || !value.name || !Number.isInteger(value.slot) || value.slot < 1 || value.slot > 3) return null;
        return value;
    } catch (_) {
        return null;
    }
}

async function searchOfficialTeams(query, entryId) {
    const teams = await findLeagueTeams(query);
    return teams.map(team => ({
        name: team.name,
        slot: team.slot,
        points: team.points,
        rank: team.rank,
        selection_token: createTeamSelectionToken(team, entryId),
    }));
}

async function verifyPublicTeamSelection(selected) {
    const result = await getPublicLeagueLeaderboard();
    const teams = result?.teams || [];
    return teams.find(team => String(team.id) === String(selected.id) && Number(team.slot) === Number(selected.slot)
        && String(team.name || '').trim().toLowerCase() === String(selected.name || '').trim().toLowerCase()) || null;
}

async function persistTeamLink(entry, selected) {
    const id = String(entry?.id || '').trim();
    if (!id) throw new Error('Your Beat V13 account could not be identified. Sign in again and retry.');
    const now = new Date().toISOString();
    const helperFn = helper('linkBeatV13Team', 'saveBeatV13TeamLink', 'updateBeatV13TeamLink');
    if (helperFn) {
        return helperFn({ entry: normalizeEntry(entry), team: selected, leagueCode: F1_SYNC_LEAGUE_CODE, leagueId: F1_SYNC_LEAGUE_ID });
    }

    // The first payload is the registration migration's public contract. The
    // aliases below keep this endpoint compatible with a short-lived staging
    // table that used team_* names before the final migration landed.
    const payloads = [
        {
            official_team_id: selected.id,
            official_team_name: selected.name,
            official_team_slot: Number(selected.slot),
            official_league_id: F1_SYNC_LEAGUE_ID,
            official_league_code: F1_SYNC_LEAGUE_CODE,
            official_team_linked_at: now,
            team_link_status: 'active',
            team_linked_at: now,
            last_synced_at: now,
        },
        {
            team_id: selected.id,
            team_name: selected.name,
            team_slot: Number(selected.slot),
            league_id: F1_SYNC_LEAGUE_ID,
            league_code: F1_SYNC_LEAGUE_CODE,
            team_link_status: 'active',
            team_linked_at: now,
        },
    ];
    let lastError;
    for (const payload of payloads) {
        try {
            const update = helper('updateBeatV13Entry');
            if (!update) throw new Error('Beat V13 entry storage is not configured yet.');
            const updated = await update(id, payload);
            return normalizeEntry(updated || { ...entry, ...payload });
        } catch (error) {
            lastError = error;
            if (!/column .* does not exist|schema cache/i.test(String(error?.message || ''))) throw error;
        }
    }
    throw lastError || new Error('The official team link could not be saved.');
}

function appendCookie(res, value) {
    const previous = res.getHeader?.('Set-Cookie');
    const existing = previous ? (Array.isArray(previous) ? previous : [previous]) : [];
    res.setHeader('Set-Cookie', [...existing, value]);
}

function clearBeatV13SessionCookies(res) {
    const clear = helper('clearBeatV13SessionCookies', 'clearBeatV13SessionCookie');
    if (clear) {
        clear(res);
    }
    // Keep this local expiration as defense-in-depth and to clear the old
    // non-HttpOnly confirmation marker during the unified sign-out flow.
    appendCookie(res, `${BEAT_V13_SESSION_COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0`);
    appendCookie(res, `${BEAT_V13_BROWSER_COOKIE}=; Path=/; Secure; SameSite=Strict; Max-Age=0`);
}

async function loadPublicTeamForEntry(entry) {
    const row = normalizeEntry(entry);
    if (!row.linked) return null;
    const result = await getPublicLeagueLeaderboard();
    return (result?.teams || []).find(team => String(team.id) === row.official_team_id && Number(team.slot) === row.team_slot)
        || (result?.teams || []).find(team => String(team.name || '').trim().toLowerCase() === row.official_team_name.toLowerCase() && Number(team.slot) === row.team_slot)
        || null;
}

module.exports = {
    BEAT_V13_BROWSER_COOKIE,
    BEAT_V13_SESSION_COOKIE,
    F1_SYNC_LEAGUE_CODE,
    F1_SYNC_LEAGUE_ID,
    TEAM_SELECTION_TTL_MS,
    clearBeatV13SessionCookies,
    createTeamSelectionToken,
    getBeatV13Session,
    getEntryForSession,
    loadPublicTeamForEntry,
    normalizeEntry,
    persistTeamLink,
    publicEntryState,
    searchOfficialTeams,
    verifyPublicTeamSelection,
    verifyTeamSelectionToken,
};
