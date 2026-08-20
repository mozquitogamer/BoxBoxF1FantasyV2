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

function queryParam(req, name) {
    return String(req.query?.[name] || new URL(req.url || '/', 'https://boxboxf1fantasy.com').searchParams.get(name) || '').trim();
}

function normalizeRound(value) {
    const round = Number(value);
    return Number.isInteger(round) && round >= 1 && round <= 24 ? round : null;
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
        await restRequest('f1_team_snapshots?on_conflict=user_id,season,round', {
            service: true,
            method: 'POST',
            prefer: 'resolution=merge-duplicates,return=representation',
            body: snapshot,
        });
        await restRequest(`f1_team_links?user_id=eq.${encodeURIComponent(link.user_id)}`, {
            service: true,
            method: 'PATCH',
            body: {
                status: 'active',
                last_synced_at: new Date().toISOString(),
                last_error: null,
            },
        });
        return { snapshot, requestedRound: round, syncedRound: round, usedPreviousRound: false, source: snapshotResult.source };
    } catch (error) {
        await restRequest(`f1_team_links?user_id=eq.${encodeURIComponent(link.user_id)}`, {
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
        if (body.action === 'f1-unlink') {
            await restRequest(`f1_team_links?user_id=eq.${encodeURIComponent(memberSession.user.id)}`, { service: true, method: 'DELETE' });
            return res.status(200).json({ ok: true, message: 'Official-team sync disconnected. Your manually saved team is unchanged.' });
        }
        if (body.action === 'f1-link') {
            if (!await requirePaidMember(memberSession)) return res.status(403).json({ ok: false, message: 'An active Pit Wall membership is required.' });
            const selected = verifyTeamLinkToken(body.link_token, memberSession.user.id);
            if (!selected) return res.status(400).json({ ok: false, message: 'That team selection expired or could not be verified. Search again.' });
            await restRequest('f1_team_links?on_conflict=user_id', {
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
            return res.status(200).json({ ok: true, message: `${selected.name} is connected. Official league updates can now refresh your Transfer Advisor.`, team: selected });
        }
        if (body.action === 'f1-sync') {
            const round = normalizeRound(body.round);
            if (!round) return res.status(400).json({ ok: false, message: 'The current round could not be determined.' });
            const links = await restRequest(`f1_team_links?user_id=eq.${encodeURIComponent(memberSession.user.id)}&status=eq.active&select=*`, { service: true });
            if (!links?.[0]) return res.status(404).json({ ok: false, message: 'Link an official team first.' });
            const result = await syncOfficialLink(links[0], round);
            const message = `Your latest locked official lineup has been refreshed for Round ${round}.`;
            return res.status(200).json({ ok: true, message, ...result });
        }
        const assets = normalizeAssets(body.assets);
        if (assets.length !== 7 || assets.some(item => !item.asset_id || !Number.isInteger(item.slot))) {
            return res.status(400).json({ ok: false, message: 'Select all 5 drivers and both constructors before saving.' });
        }
        const budget = Number(body.budget_millions);
        const freeTransfers = Number(body.free_transfers);
        await restRequest('rpc/save_member_team', {
            accessToken: memberSession.accessToken,
            method: 'POST',
            prefer: 'return=representation',
            body: {
                p_name: 'My Team',
                p_budget_millions: budget,
                p_free_transfers: freeTransfers,
                p_assets: assets,
            },
        });
        return res.status(200).json({ ok: true, message: 'Team saved. Future simulation emails will use this lineup.' });
    } catch (error) {
        console.error('Could not complete Pit Wall team request:', error.message);
        const status = /active Pit Wall membership/i.test(error.message)
            ? 403
            : error.code === 'F1_SESSION_EXPIRED'
                ? 503
                : error.code === 'F1_INCOMPLETE_LINEUP'
                    ? 502
                    : error.code === 'F1_TEAM_NOT_IN_LEAGUE'
                        ? 409
                    : 500;
        const message = status === 403 || error.code === 'F1_SESSION_EXPIRED' || error.code === 'F1_INCOMPLETE_LINEUP' || error.code === 'F1_TEAM_NOT_IN_LEAGUE'
            ? error.message
            : 'We could not save your team. Please try again.';
        return res.status(status).json({ ok: false, message });
    }
};

module.exports.syncOfficialLink = syncOfficialLink;
module.exports.normalizeRound = normalizeRound;
module.exports.createTeamLinkToken = createTeamLinkToken;
module.exports.verifyTeamLinkToken = verifyTeamLinkToken;
