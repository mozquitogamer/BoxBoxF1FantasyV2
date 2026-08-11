'use strict';

const { getConfig } = require('../../lib/email-subscriptions');

module.exports = function status(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'GET');

    if (req.method !== 'GET') {
        return res.status(405).json({ available: false });
    }

    try {
        getConfig();
        return res.status(200).json({ available: true });
    } catch (_) {
        return res.status(200).json({ available: false });
    }
};
