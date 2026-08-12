'use strict';

const {
    getMemberConfig,
    getMemberSession,
    isAllowedOrigin,
    isEntitlementActive,
    parseBody,
    restRequest,
} = require('../../lib/member-system');
const { findTeams, getLeagueLeaderboard } = require('../../lib/f1-fantasy');

async function requirePaidMember(req, res) {
    const session = await getMemberSession(req, res);
    if (!session) return { error: [401, 'Sign in to link an official F1 Fantasy team.'] };
    const rows = await restRequest(
        `member_entitlements?user_id=eq.${encodeURIComponent(session.user.id)}&select=status,current_period_end`,
        { accessToken: session.accessToken },
    );
    if (!(rows || []).some(item => isEntitlementActive(item))) {
        return { error: [403, 'An active Pit Wall membership is required to sync an official team.'] };
    }
    return { session };
}

module.exports = async function f1Link(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'GET, POST, DELETE');
    if (!['GET', 'POST', 'DELETE'].includes(req.method)) return res.status(405).json({ ok: false, message: 'Method not allowed.' });

    let memberConfig;
    try { memberConfig = getMemberConfig(); } catch (_) {
        return res.status(503).json({ ok: false, message: 'Pit Wall is not configured yet.' });
    }
    if (req.method !== 'GET' && !isAllowedOrigin(req, memberConfig.siteOrigin)) {
        return res.status(403).json({ ok: false, message: 'Request origin was not accepted.' });
    }

    try {
        const auth = await requirePaidMember(req, res);
        if (auth.error) return res.status(auth.error[0]).json({ ok: false, message: auth.error[1] });
        const { session } = auth;

        if (req.method === 'DELETE') {
            await restRequest(`f1_team_links?user_id=eq.${encodeURIComponent(session.user.id)}`, {
                service: true,
                method: 'DELETE',
            });
            return res.status(200).json({ ok: true, message: 'Official-team sync disconnected. Your manually saved team is unchanged.' });
        }

        const { teams, settings } = await getLeagueLeaderboard();
        if (req.method === 'GET') {
            const query = String(req.query?.q || new URL(req.url || '/', 'https://boxboxf1fantasy.com').searchParams.get('q') || '').trim();
            if (query.length < 2) return res.status(400).json({ ok: false, message: 'Enter at least two characters from your official team name.' });
            return res.status(200).json({
                ok: true,
                league: { id: settings.leagueId, type: settings.leagueType, name: 'Box Box F1 Fantasy' },
                teams: findTeams(teams, query),
            });
        }

        const body = parseBody(req);
        const selected = teams.find(team => team.id === String(body.official_team_id || '') && team.slot === Number(body.team_slot));
        if (!selected) return res.status(400).json({ ok: false, message: 'That team was not found in the Box Box F1 Fantasy league. Search again.' });

        const link = {
            user_id: session.user.id,
            league_id: settings.leagueId,
            league_type: settings.leagueType,
            team_slot: selected.slot,
            official_team_id: selected.id,
            official_team_name: selected.name,
            manager_name: selected.manager || null,
            status: 'active',
            last_error: null,
        };
        await restRequest('f1_team_links?on_conflict=user_id', {
            service: true,
            method: 'POST',
            prefer: 'resolution=merge-duplicates,return=representation',
            body: link,
        });
        return res.status(200).json({ ok: true, message: `${selected.name} is linked. Official updates can now refresh your Transfer Advisor.`, team: selected });
    } catch (error) {
        console.error('F1 team link failed:', error.message);
        const duplicate = error.status === 409 || /duplicate|unique/i.test(error.message);
        return res.status(duplicate ? 409 : 502).json({
            ok: false,
            message: duplicate ? 'That official team is already linked to another BoxBox account.' : 'The official F1 Fantasy service could not be reached. Your manual team remains available.',
        });
    }
};

module.exports.requirePaidMember = requirePaidMember;
