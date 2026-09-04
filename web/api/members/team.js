'use strict';

const crypto = require('node:crypto');

const {
    getMemberConfig,
    getMemberDashboard,
    getMemberSession,
    isAllowedOrigin,
    parseBody,
    restRequest,
    isEntitlementActive,
} = require('../../lib/member-system');
const { findLeagueTeams, getOpponentSnapshot, getPublicLeagueSnapshot } = require('../../lib/f1-fantasy');
const { consumeRateLimit, rateLimited } = require('../../lib/rate-limit');
const { loadV13Record } = require('../../lib/beat-v13-leaderboard');
const {
    getBeatV13Session,
    getEntryForSession,
    loadPublicTeamForEntry,
    persistTeamLink,
    publicEntryState,
    searchOfficialTeams,
    verifyPublicTeamSelection,
    verifyTeamSelectionToken,
} = require('../../lib/beat-v13-entry');

const TEAM_LINK_TOKEN_TTL_MS = 10 * 60 * 1000;
const F1_SYNC_LEAGUE_CODE = 'P1JZAGNMP04';
const F1_SYNC_LEAGUE_URL = `https://fantasy.formula1.com/en/leagues/join/${F1_SYNC_LEAGUE_CODE}`;

function normalizeAssets(items) {
    if (!Array.isArray(items)) return [];
    return items.map(item => ({
        asset_type: item.asset_type === 'constructor' ? 'constructor' : 'driver',
        asset_id: String(item.asset_id || '').trim().slice(0, 40),
        slot: Number(item.slot),
        is_boosted: item.is_boosted === true,
    }));
}

const CHIP_CODES = Object.freeze(['limitless', '3x_boost', 'wild_card', 'no_negative', 'autopilot', 'final_fix']);

function normalizeTeamSlot(value, fallback = 1) {
    const slot = Number(value);
    return Number.isInteger(slot) && slot >= 1 && slot <= 3 ? slot : fallback;
}

function shouldMarkPrimary(body) {
    return body?.is_primary === true || body?.primary === true
        || (body?.team_slot === undefined && body?.slot === undefined);
}

function requestedTeamSlot(body) {
    const hasSlot = body && (Object.prototype.hasOwnProperty.call(body, 'team_slot') || Object.prototype.hasOwnProperty.call(body, 'slot'));
    if (!hasSlot) return { slot: 1, legacy: true };
    const raw = body.team_slot ?? body.slot;
    const slot = Number(raw);
    if (!Number.isInteger(slot) || slot < 1 || slot > 3) {
        const error = new Error('Team slot must be 1, 2 or 3.');
        error.code = 'INVALID_TEAM_SLOT';
        throw error;
    }
    return { slot, legacy: false };
}

function normalizeChips(items) {
    let entries;
    if (Array.isArray(items)) {
        entries = items;
    } else if (items && typeof items === 'object') {
        entries = Object.entries(items).map(([chip_code, value]) => ({
            ...(value && typeof value === 'object' ? value : typeof value === 'boolean' ? { available: value } : { status: value }),
            chip_code,
        }));
    } else if (items == null) {
        return null;
    } else {
        const error = new Error('Chip state must be an array or object map.');
        error.code = 'INVALID_CHIP_STATE';
        throw error;
    }
    const seen = new Set();
    return entries.map(item => {
        const chipCode = String(item?.chip_code || item?.code || '').trim().toLowerCase();
        const status = String(item?.status || (item?.available === true ? 'available' : item?.available === false ? 'used' : 'unknown')).toLowerCase();
        if (!CHIP_CODES.includes(chipCode)) {
            const error = new Error(`Unknown chip code: ${chipCode || 'empty'}.`);
            error.code = 'INVALID_CHIP_STATE';
            throw error;
        }
        if (seen.has(chipCode)) {
            const error = new Error(`Chip ${chipCode} was supplied more than once.`);
            error.code = 'INVALID_CHIP_STATE';
            throw error;
        }
        seen.add(chipCode);
        if (!['unknown', 'available', 'used'].includes(status)) {
            const error = new Error(`Invalid status for chip ${chipCode}.`);
            error.code = 'INVALID_CHIP_STATE';
            throw error;
        }
        const usedRound = item?.used_round == null || item.used_round === '' ? null : normalizeRound(item.used_round);
        if (item?.used_round != null && item.used_round !== '' && usedRound === null) {
            const error = new Error(`Invalid used round for chip ${chipCode}.`);
            error.code = 'INVALID_CHIP_STATE';
            throw error;
        }
        if (status !== 'used' && usedRound !== null) {
            const error = new Error(`Only used chips may have a used round (${chipCode}).`);
            error.code = 'INVALID_CHIP_STATE';
            throw error;
        }
        return {
            chip_code: chipCode,
            status,
            available: status === 'available' ? true : status === 'used' ? false : null,
            used_round: usedRound,
        };
    });
}

function queryParam(req, name) {
    return String(req.query?.[name] || new URL(req.url || '/', 'https://boxboxf1fantasy.com').searchParams.get(name) || '').trim();
}

function normalizeRound(value) {
    const round = Number(value);
    return Number.isInteger(round) && round >= 1 && round <= 24 ? round : null;
}

function normalizeOptionalRound(value) {
    // The original Team 1 client used round 0 as “no weekly history yet”.
    // Keep that legacy sentinel out of saved_team_history, while still
    // rejecting other invalid explicit rounds.
    if (value == null || value === '' || value === 0 || value === '0') return null;
    return normalizeRound(value);
}

function teamLinkSecret() {
    const secret = String(process.env.SUBSCRIPTION_SIGNING_SECRET || '').trim();
    if (!secret) throw new Error('Official-team linking is not configured yet.');
    return secret;
}

function teamLinkSignature(payload, secret) {
    return crypto.createHmac('sha256', secret)
        .update(`boxbox-f1-team-link:v1:${payload}`)
        .digest('base64url');
}

function officialTeamLinkConflict(message) {
    const error = new Error(message);
    error.code = 'F1_TEAM_LINK_CONFLICT';
    error.status = 409;
    return error;
}

async function assertOfficialTeamSlotAvailable(userId, selected) {
    const leagueId = Number(process.env.F1_FANTASY_LEAGUE_ID || 160604);
    const officialId = encodeURIComponent(String(selected?.id || ''));
    const slot = Number(selected?.slot);
    if (!officialId || !Number.isInteger(slot)) return;
    const rows = await restRequest(
        `f1_team_links?league_id=eq.${leagueId}&official_team_id=eq.${officialId}&team_slot=eq.${slot}&select=user_id,team_slot`,
        { service: true },
    );
    const claimedByAnotherMember = (rows || []).some(row => String(row.user_id) !== String(userId));
    if (claimedByAnotherMember) {
        throw officialTeamLinkConflict(`That official team is already linked to another Pit Wall member for Team ${slot}. Choose a different official team.`);
    }
}

function createTeamLinkToken(team, userId, now = Date.now()) {
    const rank = Number(team?.rank);
    const payload = Buffer.from(JSON.stringify({
        sub: String(userId || ''),
        id: String(team?.id || '').slice(0, 160),
        name: String(team?.name || '').trim().slice(0, 100),
        manager: String(team?.manager || '').trim().slice(0, 100),
        slot: Number(team?.slot),
        rank: Number.isInteger(rank) && rank >= 1 ? rank : null,
        exp: now + TEAM_LINK_TOKEN_TTL_MS,
    }), 'utf8').toString('base64url');
    return `${payload}.${teamLinkSignature(payload, teamLinkSecret())}`;
}

function verifyTeamLinkToken(token, userId, now = Date.now()) {
    const [payload, suppliedSignature, extra] = String(token || '').split('.');
    if (!payload || !suppliedSignature || extra) return null;
    const expectedSignature = teamLinkSignature(payload, teamLinkSecret());
    const supplied = Buffer.from(suppliedSignature);
    const expected = Buffer.from(expectedSignature);
    if (supplied.length !== expected.length || !crypto.timingSafeEqual(supplied, expected)) return null;
    try {
        const team = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
        if (team.sub !== String(userId || '') || !Number.isFinite(team.exp) || team.exp < now) return null;
        if (!team.id || !team.name || !Number.isInteger(team.slot) || team.slot < 1 || team.slot > 3) return null;
        if (team.rank !== null && (!Number.isInteger(team.rank) || team.rank < 1)) return null;
        return team;
    } catch (_) {
        return null;
    }
}

async function requirePaidMember(memberSession) {
    const rows = await restRequest(
        `member_entitlements?user_id=eq.${encodeURIComponent(memberSession.user.id)}&select=status,current_period_end`,
        { accessToken: memberSession.accessToken },
    );
    return (rows || []).some(item => isEntitlementActive(item));
}

async function syncOfficialLink(link, round) {
    try {
        let snapshotResult;
        try {
            snapshotResult = await getPublicLeagueSnapshot(link, round);
        } catch (publicError) {
            // Compatibility fallback for teams linked before the public league-feed flow shipped.
            // Normal member syncs never need the private F1 session cookie.
            try {
                const snapshot = await getOpponentSnapshot(link, round);
                snapshotResult = { snapshot, source: 'authenticated_fallback' };
            } catch (fallbackError) {
                if (publicError.code === 'F1_TEAM_NOT_IN_LEAGUE') throw publicError;
                throw fallbackError;
            }
        }
        const snapshot = snapshotResult.snapshot;
        const storedSnapshot = {
            ...snapshot,
            // `teambal` is cash remaining, not total spending power. Keep the
            // legacy extractor field out of the new budget aliases so a
            // sync cannot make a £3.4m bank look like a £3.4m team budget.
            budget_millions: null,
            // The official feed's `teambal` field is the current cash balance.
            bank_millions: snapshot.bank_millions ?? snapshot.budget_millions ?? null,
            spending_power_millions: snapshot.spending_power_millions ?? null,
            squad_value_millions: snapshot.squad_value_millions ?? null,
        };
        await restRequest('f1_team_snapshots?on_conflict=user_id,season,round,team_slot', {
            service: true,
            method: 'POST',
            prefer: 'resolution=merge-duplicates,return=representation',
            body: storedSnapshot,
        });
        await restRequest(`f1_team_links?user_id=eq.${encodeURIComponent(link.user_id)}&team_slot=eq.${Number(link.team_slot)}`, {
            service: true,
            method: 'PATCH',
            body: {
                status: 'active',
                last_synced_at: new Date().toISOString(),
                last_error: null,
            },
        });
        return { snapshot: storedSnapshot, requestedRound: round, syncedRound: round, usedPreviousRound: false, source: snapshotResult.source };
    } catch (error) {
        await restRequest(`f1_team_links?user_id=eq.${encodeURIComponent(link.user_id)}&team_slot=eq.${Number(link.team_slot)}`, {
            service: true,
            method: 'PATCH',
            body: { last_error: String(error.message || error).slice(0, 500) },
        }).catch(() => null);
        throw error;
    }
}

function beatV13RequestOrigin(req) {
    try { return getMemberConfig().siteOrigin; }
    catch (_) { return (process.env.SITE_ORIGIN || 'https://boxboxf1fantasy.com').replace(/\/$/, ''); }
}

async function handleBeatV13Team(req, res) {
    if (req.method === 'POST' && !isAllowedOrigin(req, beatV13RequestOrigin(req))) {
        return res.status(403).json({ ok: false, message: 'Request origin was not accepted.' });
    }

    try {
        const session = await getBeatV13Session(req, res);
        const entry = await getEntryForSession(session);
        if (!session || !entry?.confirmed) {
            return res.status(401).json({ ok: false, message: 'Confirm your free Beat V13 entry before connecting a team.' });
        }

        if (req.method === 'GET') {
            const action = queryParam(req, 'action') || 'search';
            if (action !== 'search') return res.status(400).json({ ok: false, message: 'Unknown team action.' });
            const query = queryParam(req, 'q');
            if (query.length < 2) return res.status(400).json({ ok: false, message: 'Enter at least two characters from your exact official team name.' });
            const throttle = consumeRateLimit(req, `beat-v13-team-search:${entry.id}`, { limit: 12, windowMs: 5 * 60 * 1000 });
            if (!throttle.allowed) return rateLimited(res, throttle, 'Too many team searches. Please wait a few minutes and try again.');
            const teams = await searchOfficialTeams(query, entry.id);
            return res.status(200).json({
                ok: true,
                league_code: F1_SYNC_LEAGUE_CODE,
                league_id: Number(process.env.F1_FANTASY_LEAGUE_ID || 160604),
                teams,
            });
        }

        const body = parseBody(req);
        if (body.action !== 'link' && body.action !== 'f1-link') {
            return res.status(400).json({ ok: false, message: 'Choose an official team from the search results first.' });
        }
        let selected = verifyTeamSelectionToken(body.selection_token || body.link_token, entry.id);
        if (!selected) {
            const id = String(body.official_team_id || body.team_id || '').trim();
            const name = String(body.official_team_name || body.team_name || '').replace(/\s+/g, ' ').trim();
            const slot = Number(body.team_slot || body.slot);
            if (!id || !name || !Number.isInteger(slot) || slot < 1 || slot > 3) {
                return res.status(400).json({ ok: false, message: 'That team selection expired or could not be verified. Search again.' });
            }
            selected = { id, name, slot };
        }

        const official = await verifyPublicTeamSelection(selected);
        if (!official) {
            return res.status(409).json({ ok: false, message: `That team is not visible in the Box Box league yet. Join with code ${F1_SYNC_LEAGUE_CODE}, then search again.` });
        }
        const linked = await persistTeamLink(entry, {
            id: String(official.id),
            name: String(official.name).replace(/\s+/g, ' ').trim().slice(0, 100),
            slot: Number(official.slot),
        });
        let feedTeam = official;
        try { feedTeam = await loadPublicTeamForEntry(linked) || official; } catch (_) { /* already verified */ }
        return res.status(200).json({
            ok: true,
            message: `${feedTeam.name} is connected for Beat V13 live tracking.`,
            entry: publicEntryState(linked, loadV13Record().points, feedTeam),
        });
    } catch (error) {
        console.error('Could not complete Beat V13 team request:', error.message);
        if (error?.status === 409 || /duplicate key|unique constraint|already linked/i.test(String(error?.message || ''))) {
            return res.status(409).json({ ok: false, message: 'That official team is already linked to another Beat V13 entrant. Choose your own T1/T2/T3 team.' });
        }
        if (error?.code === 'F1_SESSION_EXPIRED' || /public Box Box league feed|temporarily unavailable/i.test(String(error?.message || ''))) {
            return res.status(503).json({ ok: false, message: 'The official Box Box league feed is temporarily unavailable. Please try again shortly.' });
        }
        return res.status(500).json({ ok: false, message: 'We could not connect that team. Please search again and retry.' });
    }
}

module.exports = async function team(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'GET, POST');
    if (!['GET', 'POST'].includes(req.method)) return res.status(405).json({ ok: false, message: 'Method not allowed.' });

    if (queryParam(req, 'scope') === 'beat-v13') return handleBeatV13Team(req, res);

    let config;
    try {
        config = getMemberConfig();
    } catch (error) {
        return res.status(503).json({ ok: false, message: 'Pit Wall team memory is not configured yet.' });
    }
    if (req.method === 'POST' && !isAllowedOrigin(req, config.siteOrigin)) {
        return res.status(403).json({ ok: false, message: 'Request origin was not accepted.' });
    }

    try {
        const memberSession = await getMemberSession(req, res);
        if (!memberSession) return res.status(401).json({ ok: false, message: 'Sign in to save your team.' });
        const action = queryParam(req, 'action');
        if (req.method === 'GET' && action === 'f1-search') {
            if (!await requirePaidMember(memberSession)) return res.status(403).json({ ok: false, message: 'An active Pit Wall membership is required.' });
            const throttle = consumeRateLimit(req, `f1-global-search:${memberSession.user.id}`, { limit: 12, windowMs: 5 * 60 * 1000 });
            if (!throttle.allowed) return res.status(429).json({ ok: false, message: 'Too many team searches. Please wait a few minutes and try again.' });
            const query = queryParam(req, 'q');
            if (query.length < 2) return res.status(400).json({ ok: false, message: 'Enter at least two characters from your official team name.' });
            const teams = await findLeagueTeams(query);
            return res.status(200).json({
                ok: true,
                scope: 'boxbox_league',
                join_code: F1_SYNC_LEAGUE_CODE,
                join_url: F1_SYNC_LEAGUE_URL,
                teams: teams.map(team => ({
                    name: team.name,
                    slot: team.slot,
                    manager: team.manager,
                    points: team.points,
                    rank: team.rank,
                    link_token: createTeamLinkToken(team, memberSession.user.id),
                })),
            });
        }
        if (req.method === 'GET') return res.status(200).json(await getMemberDashboard(memberSession));

        const body = parseBody(req);
        const slotRequest = requestedTeamSlot(body);
        const hasTeamSlot = !slotRequest.legacy;
        if (body.action === 'rename') {
            if (!await requirePaidMember(memberSession)) return res.status(403).json({ ok: false, message: 'An active Pit Wall membership is required to rename teams.' });
            const slot = slotRequest.slot;
            const name = String(body.name || body.team_name || '').replace(/\s+/g, ' ').trim();
            if (!name || name.length > 60) return res.status(400).json({ ok: false, message: 'Enter a team name between 1 and 60 characters.' });
            await restRequest('rpc/rename_member_team', {
                accessToken: memberSession.accessToken,
                method: 'POST',
                prefer: 'return=representation',
                body: { p_team_slot: slot, p_name: name },
            });
            const dashboard = await getMemberDashboard(memberSession);
            return res.status(200).json({ ok: true, team_slot: slot, team: dashboard.teams?.find(team => team.team_slot === slot) || null, teams: dashboard.teams || [], message: `Team ${slot} renamed.` });
        }
        if (body.action === 'set-primary' || body.action === 'set_primary') {
            if (!await requirePaidMember(memberSession)) return res.status(403).json({ ok: false, message: 'An active Pit Wall membership is required to change the primary team.' });
            const slot = slotRequest.slot;
            await restRequest('rpc/set_member_team_primary', {
                accessToken: memberSession.accessToken,
                method: 'POST',
                prefer: 'return=representation',
                body: { p_team_slot: slot },
            });
            const dashboard = await getMemberDashboard(memberSession);
            return res.status(200).json({ ok: true, team_slot: slot, team: dashboard.teams?.find(team => team.team_slot === slot) || null, teams: dashboard.teams || [], message: `Team ${slot} is now your primary team.` });
        }
        if (body.action === 'f1-unlink') {
            if (!await requirePaidMember(memberSession)) return res.status(403).json({ ok: false, message: 'An active Pit Wall membership is required to change official links.' });
            const slot = slotRequest.slot;
            await restRequest(`f1_team_links?user_id=eq.${encodeURIComponent(memberSession.user.id)}&team_slot=eq.${slot}`, { service: true, method: 'DELETE' });
            return res.status(200).json({ ok: true, team_slot: slot, message: 'Official-team sync disconnected. Your manually saved team is unchanged.' });
        }
        if (body.action === 'f1-link') {
            if (!await requirePaidMember(memberSession)) return res.status(403).json({ ok: false, message: 'An active Pit Wall membership is required.' });
            const selected = verifyTeamLinkToken(body.link_token, memberSession.user.id);
            if (!selected) return res.status(400).json({ ok: false, message: 'That team selection expired or could not be verified. Search again.' });
            if (hasTeamSlot && slotRequest.slot !== selected.slot) {
                return res.status(400).json({ ok: false, message: `That signed selection belongs to Team ${selected.slot}. Search again for the requested slot.` });
            }
            await assertOfficialTeamSlotAvailable(memberSession.user.id, selected);
            await restRequest('f1_team_links?on_conflict=user_id,team_slot', {
                service: true,
                method: 'POST',
                prefer: 'resolution=merge-duplicates,return=representation',
                body: {
                    user_id: memberSession.user.id,
                    league_id: Number(process.env.F1_FANTASY_LEAGUE_ID || 160604),
                    league_type: 'public',
                    team_slot: selected.slot,
                    official_team_id: selected.id,
                    official_team_name: selected.name,
                    manager_name: selected.manager || null,
                    status: 'active',
                    last_error: null,
                },
            });
            return res.status(200).json({ ok: true, message: `${selected.name} is connected. You can now synchronize its latest locked lineup into Team ${selected.slot}.`, f1_link: selected, team_slot: selected.slot });
        }
        if (body.action === 'f1-sync') {
            if (!await requirePaidMember(memberSession)) return res.status(403).json({ ok: false, message: 'An active Pit Wall membership is required to synchronize official teams.' });
            const round = normalizeRound(body.round);
            if (!round) return res.status(400).json({ ok: false, message: 'The current round could not be determined.' });
            const slot = slotRequest.slot;
            const links = await restRequest(`f1_team_links?user_id=eq.${encodeURIComponent(memberSession.user.id)}&team_slot=eq.${slot}&status=eq.active&select=*`, { service: true });
            if (!links?.[0]) return res.status(404).json({ ok: false, message: `Link an official Team ${slot} first.` });
            const result = await syncOfficialLink(links[0], round);
            const message = `Your latest locked official lineup is ready to synchronize into Round ${round}.`;
            return res.status(200).json({ ok: true, message, ...result });
        }
        const assets = normalizeAssets(body.assets);
        if (assets.length !== 7 || assets.some(item => !item.asset_id || !Number.isInteger(item.slot))) {
            return res.status(400).json({ ok: false, message: 'Select all 5 drivers and both constructors before saving.' });
        }
        const teamSlot = slotRequest.slot;
        const squadInput = body.squad_value_millions ?? body.squad_value;
        const bankInput = body.bank_millions ?? body.bank;
        const squadValue = squadInput === undefined || squadInput === null || squadInput === '' ? null : Number(squadInput);
        const bank = bankInput === undefined || bankInput === null || bankInput === '' ? null : Number(bankInput);
        const spendingInput = body.spending_power_millions ?? body.spending_power ?? body.budget_millions;
        const spendingPower = spendingInput === undefined || spendingInput === null || spendingInput === ''
            ? (Number.isFinite(squadValue) && Number.isFinite(bank) ? squadValue + bank : null)
            : Number(spendingInput);
        const freeTransfers = Number(body.free_transfers);
        const chipInput = body.chips ?? body.chip_status ?? body.chip_ledger;
        const chips = chipInput === undefined ? null : normalizeChips(chipInput);
        const season = Number(body.season || 2026);
        const round = normalizeOptionalRound(body.round);
        if (!Number.isInteger(season) || season < 2020 || season > 2026) {
            return res.status(400).json({ ok: false, message: 'The requested season is not supported.' });
        }
        if ((squadValue !== null && !Number.isFinite(squadValue))
            || (bank !== null && !Number.isFinite(bank))
            || !Number.isFinite(spendingPower)
            || !Number.isInteger(freeTransfers)) {
            return res.status(400).json({ ok: false, message: 'Enter valid squad value, bank balance and free transfers.' });
        }
        if (body.round != null && body.round !== '' && body.round !== 0 && body.round !== '0' && !round) {
            return res.status(400).json({ ok: false, message: 'The current round could not be determined.' });
        }
        await restRequest('rpc/save_member_team_v2', {
            accessToken: memberSession.accessToken,
            method: 'POST',
            prefer: 'return=representation',
            body: {
                p_team_slot: teamSlot,
                p_name: String(body.name || body.team_name || (teamSlot === 1 ? 'My Team' : `Team ${teamSlot}`)).trim().slice(0, 60),
                p_source_type: (body.source_type ?? body.source) === 'official' ? 'official' : 'manual',
                p_squad_value_millions: squadValue,
                p_bank_millions: bank,
                p_spending_power_millions: spendingPower,
                p_free_transfers: freeTransfers,
                p_assets: assets,
                p_chips: chips,
                p_season: Number.isInteger(season) ? season : 2026,
                p_round: round,
                p_is_primary: shouldMarkPrimary(body),
            },
        });
        return res.status(200).json({ ok: true, team_slot: teamSlot, message: `Team ${teamSlot} saved. Future simulation emails will use your primary lineup.` });
    } catch (error) {
        console.error('Could not complete Pit Wall team request:', error.message);
        const status = error.code === 'INVALID_CHIP_STATE' || error.code === 'INVALID_TEAM_SLOT'
            ? 400
            : /active Pit Wall membership/i.test(error.message)
                ? 403
            : error.code === 'F1_TEAM_LINK_CONFLICT'
                ? 409
            : /duplicate key|unique constraint|already linked/i.test(String(error?.message || ''))
                ? 409
            : error.code === 'F1_SESSION_EXPIRED'
                ? 503
                : error.code === 'F1_INCOMPLETE_LINEUP'
                    ? 502
                    : error.code === 'F1_TEAM_NOT_IN_LEAGUE'
                        ? 409
                    : 500;
        const message = status === 400 || status === 403 || status === 409 || error.code === 'F1_SESSION_EXPIRED' || error.code === 'F1_INCOMPLETE_LINEUP' || error.code === 'F1_TEAM_NOT_IN_LEAGUE'
            ? error.message
            : 'We could not save your team. Please try again.';
        return res.status(status).json({ ok: false, message });
    }
};

module.exports.syncOfficialLink = syncOfficialLink;
module.exports.normalizeAssets = normalizeAssets;
module.exports.normalizeRound = normalizeRound;
module.exports.normalizeOptionalRound = normalizeOptionalRound;
module.exports.normalizeTeamSlot = normalizeTeamSlot;
module.exports.shouldMarkPrimary = shouldMarkPrimary;
module.exports.requestedTeamSlot = requestedTeamSlot;
module.exports.normalizeChips = normalizeChips;
module.exports.createTeamLinkToken = createTeamLinkToken;
module.exports.verifyTeamLinkToken = verifyTeamLinkToken;
