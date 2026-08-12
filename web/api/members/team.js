'use strict';

const {
    getMemberConfig,
    getMemberDashboard,
    getMemberSession,
    isAllowedOrigin,
    parseBody,
    restRequest,
    isEntitlementActive,
} = require('../../lib/member-system');
const { findTeams, getLeagueLeaderboard, getOpponentSnapshot } = require('../../lib/f1-fantasy');

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

async function requirePaidMember(memberSession) {
    const rows = await restRequest(
        `member_entitlements?user_id=eq.${encodeURIComponent(memberSession.user.id)}&select=status,current_period_end`,
        { accessToken: memberSession.accessToken },
    );
    return (rows || []).some(item => isEntitlementActive(item));
}

async function syncOfficialLink(link, round) {
    try {
        const snapshot = await getOpponentSnapshot(link, round);
        await restRequest('f1_team_snapshots?on_conflict=user_id,season,round', {
            service: true,
            method: 'POST',
            prefer: 'resolution=merge-duplicates,return=representation',
            body: snapshot,
        });
        await restRequest(`f1_team_links?user_id=eq.${encodeURIComponent(link.user_id)}`, {
            service: true,
            method: 'PATCH',
            body: { status: 'active', last_synced_at: new Date().toISOString(), last_error: null },
        });
        return snapshot;
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
            const query = queryParam(req, 'q');
            if (query.length < 2) return res.status(400).json({ ok: false, message: 'Enter at least two characters from your official team name.' });
            const { teams, settings } = await getLeagueLeaderboard();
            return res.status(200).json({
                ok: true,
                league: { id: settings.leagueId, type: settings.leagueType, name: 'Box Box F1 Fantasy' },
                teams: findTeams(teams, query),
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
            const { teams, settings } = await getLeagueLeaderboard();
            const selected = teams.find(item => item.id === String(body.official_team_id || '') && item.slot === Number(body.team_slot));
            if (!selected) return res.status(400).json({ ok: false, message: 'That team was not found in the Box Box F1 Fantasy league. Search again.' });
            await restRequest('f1_team_links?on_conflict=user_id', {
                service: true,
                method: 'POST',
                prefer: 'resolution=merge-duplicates,return=representation',
                body: {
                    user_id: memberSession.user.id,
                    league_id: settings.leagueId,
                    league_type: settings.leagueType,
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
            const snapshot = await syncOfficialLink(links[0], round);
            return res.status(200).json({ ok: true, message: `Official team synced for Round ${round}.`, snapshot });
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
        const status = /active Pit Wall membership/i.test(error.message) ? 403 : 500;
        return res.status(status).json({ ok: false, message: status === 403 ? error.message : 'We could not save your team. Please try again.' });
    }
};

module.exports.syncOfficialLink = syncOfficialLink;
module.exports.normalizeRound = normalizeRound;
