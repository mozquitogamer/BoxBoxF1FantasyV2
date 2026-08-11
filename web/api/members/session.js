'use strict';

const { getMemberDashboard, getMemberSession } = require('../../lib/member-system');

module.exports = async function session(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'GET');
    if (req.method !== 'GET') return res.status(405).json({ authenticated: false });

    try {
        const memberSession = await getMemberSession(req, res);
        if (!memberSession) return res.status(200).json({ authenticated: false });
        return res.status(200).json(await getMemberDashboard(memberSession));
    } catch (error) {
        console.error('Could not load Pit Wall session:', error.message);
        return res.status(503).json({ authenticated: false, message: 'Pit Wall account data is temporarily unavailable.' });
    }
};
