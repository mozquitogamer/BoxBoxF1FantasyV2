/* Labels describe the forecast actually loaded, independently of the calendar. */
(function (root) {
    'use strict';
    function phaseLabel(prediction) {
        if (prediction.phase === 'pre_fp') return 'Pre-practice';
        if (prediction.phase === 'post_quali') return 'Post qualifying';
        if (prediction.phase === 'post_fp') {
            const sessions = prediction.fp_sessions_included || [];
            const latest = ['FP3', 'FP2', 'FP1'].find(session => sessions.includes(session));
            return latest ? `Post ${latest}` : 'Post practice';
        }
        return 'Version unavailable';
    }
    function context(prediction, rounds = [], now = new Date()) {
        const round = rounds.find(race => Number(race.round) === Number(prediction.round));
        const raceDate = prediction.date || round?.date;
        const passed = raceDate && now >= new Date(`${raceDate}T23:59:59Z`);
        const completed = Boolean(round?.has_actual);
        const next = rounds.find(race => !race.cancelled && Number(race.round) > Number(prediction.round)
            && new Date(`${race.date}T23:59:59Z`) > now);
        const archived = completed || Boolean(passed);
        return {
            phase: phaseLabel(prediction),
            archived,
            status: completed ? 'Race complete · saved forecast' : archived ? 'Past race · saved forecast' : 'Current forecast',
            notice: archived
                ? `These are the saved predictions for Round ${prediction.round}. ${next ? `${next.name} (Round ${next.round}) simulations are pending.` : 'No newer simulation is available.'}`
                : '',
            generatedAt: prediction.simulation_generated_at || prediction.generated_at,
            evidence: prediction.phase === 'pre_fp' ? 'Based on historical results; practice is not included.'
                : prediction.phase === 'post_quali' ? 'Official qualifying included; the race is simulated.'
                : prediction.fp_sessions_included?.length ? `Practice included: ${prediction.fp_sessions_included.join(', ')}.`
                : 'Practice session details were not recorded for this version.',
        };
    }
    const api = { phaseLabel, context };
    root.BoxBoxPredictionContext = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
