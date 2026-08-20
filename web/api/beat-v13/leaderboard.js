'use strict';

const status = require('../email/status');

module.exports = function beatV13Leaderboard(req, res) {
    const query = { ...(req.query || {}), resource: 'beat-v13-leaderboard' };
    return status({ ...req, query }, res);
};

