'use strict';

const {
    getMemberConfig,
    getMemberDashboard,
    getMemberSession,
    isAllowedOrigin,
    parseBody,
    restRequest,
} = require('../../lib/member-system');

function normalizeAssets(items) {
    if (!Array.isArray(items)) return [];
    return items.map(item => ({
        asset_type: item.asset_type === 'constructor' ? 'constructor' : 'driver',
        asset_id: String(item.asset_id || '').trim().slice(0, 40),
        slot: Number(item.slot),
        is_boosted: item.is_boosted === true,
    }));
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
        if (req.method === 'GET') return res.status(200).json(await getMemberDashboard(memberSession));

        const body = parseBody(req);
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
