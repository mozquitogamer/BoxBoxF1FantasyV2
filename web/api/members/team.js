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
const { findGlobalTeams, getOpponentSnapshot } = require('../../lib/f1-fantasy');
const { consumeRateLimit } = require('../../lib/rate-limit');

const TEAM_LINK_TOKEN_TTL_MS = 10 * 60 * 1000;

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
    const payload = Buffer.from(JSON.stringify({
        sub: String(userId || ''),
        id: String(team?.id || '').slice(0, 160),
        name: String(team?.name || '').trim().slice(0, 100),
        manager: String(team?.manager || '').trim().slice(0, 100),
        slot: Number(team?.slot),
        rank: Number(team?.rank),
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
        if (!Number.isInteger(team.rank) || team.rank < 1) return null;
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
        let snapshot;
        let syncedRound = round;
        let currentRoundError = null;
        try {
            snapshot = await getOpponentSnapshot(link, round);
        } catch (error) {
            if (error.code !== 'F1_INCOMPLETE_LINEUP' || round <= 1) throw error;
            currentRoundError = error;
            syncedRound = round - 1;
            snapshot = await getOpponentSnapshot(link, syncedRound);
        }
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
                last_error: currentRoundError ? `Round ${round} is not public yet; using the locked Round ${syncedRound} lineup.` : null,
            },
        });
        return { snapshot, requestedRound: round, syncedRound, usedPreviousRound: syncedRound !== round };
    } catch (error) {
        await restRequest(`f1_team_links?user_id=eq.${encodeURIComponent(link.user_id)}`, {
            service: true,
            method: 'PATCH',
            body: { last_error: String(error.message || error).slice(0, 500) },
        }).catch(() => null);
        throw error;
    }
}

module.exports = async function team(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'GET, POST');
    if (!['GET', 'POST'].includes(req.method)) return res.status(405).json({ ok: false, message: 'Method not allowed.' });

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
            const rank = Number(queryParam(req, 'rank'));
            const slot = Number(queryParam(req, 'slot'));
            if (!Number.isInteger(rank) || rank < 1 || rank > 5_000_000) return res.status(400).json({ ok: false, message: 'Enter the current overall rank shown by F1 Fantasy.' });
            if (!Number.isInteger(slot) || slot < 1 || slot > 3) return res.status(400).json({ ok: false, message: 'Choose Team 1, Team 2 or Team 3.' });
            const teams = await findGlobalTeams(query, rank, slot);
            return res.status(200).json({
                ok: true,
                scope: 'global',
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
                    // The existing schema requires these compatibility fields. Discovery is global;
                    // weekly sync uses only the verified official team ID and slot below.
                    league_id: 0,
                    league_type: 'public',
                    team_slot: selected.slot,
                    official_team_id: selected.id,
                    official_team_name: selected.name,
                    manager_name: selected.manager || null,
                    status: 'active',
                    last_error: null,
                },
            });
            return res.status(200).json({ ok: true, message: `${selected.name} is linked. Official updates can now refresh your Transfer Advisor.`, team: selected });
        }
        if (body.action === 'f1-sync') {
            const round = normalizeRound(body.round);
            if (!round) return res.status(400).json({ ok: false, message: 'The current round could not be determined.' });
            const links = await restRequest(`f1_team_links?user_id=eq.${encodeURIComponent(memberSession.user.id)}&status=eq.active&select=*`, { service: true });
            if (!links?.[0]) return res.status(404).json({ ok: false, message: 'Link an official team first.' });
            const result = await syncOfficialLink(links[0], round);
            const message = result.usedPreviousRound
                ? `Your latest public official lineup (Round ${result.syncedRound}) has been loaded. Round ${round} stays hidden until the F1 deadline.`
                : `Official team synced for Round ${round}.`;
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
        console.error('Could not save Pit Wall team:', error.message);
        const status = /active Pit Wall membership/i.test(error.message) ? 403 : error.code === 'F1_INCOMPLETE_LINEUP' ? 502 : 500;
        const message = status === 403 || error.code === 'F1_INCOMPLETE_LINEUP'
            ? error.message
            : 'We could not save your team. Please try again.';
        return res.status(status).json({ ok: false, message });
    }
};

module.exports.syncOfficialLink = syncOfficialLink;
module.exports.normalizeRound = normalizeRound;
module.exports.createTeamLinkToken = createTeamLinkToken;
module.exports.verifyTeamLinkToken = verifyTeamLinkToken;
