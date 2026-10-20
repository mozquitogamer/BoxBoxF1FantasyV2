/* Simulation explanations must never borrow values from the live forecast. */
(function (root) {
    'use strict';
    function sourceTime(value) {
        const time = typeof value === 'string' ? Date.parse(value) : NaN;
        return Number.isFinite(time) ? time : null;
    }
    function dateLabel(value) {
        const time = sourceTime(value);
        return time === null ? 'date unavailable' : new Date(time).toLocaleString('en-GB', {
            timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric',
            hour: '2-digit', minute: '2-digit', hour12: false,
        }) + ' UTC';
    }
    function describe(prediction, forecast) {
        const used = prediction?.weather_adjustments;
        const source = sourceTime(used?.source);
        const latest = sourceTime(forecast?.last_updated);
        const sameRound = prediction?.round != null && forecast?.round != null
            && Number(prediction.round) === Number(forecast.round);
        const usedRoundMatches = used?.round == null || Number(used.round) === Number(prediction?.round);
        let status = 'unknown';
        if (!sameRound || !usedRoundMatches) status = 'different-round';
        else if (source !== null && latest !== null) {
            const idsMatch = !used?.forecast_snapshot_id || !forecast?.forecast_snapshot_id
                || used.forecast_snapshot_id === forecast.forecast_snapshot_id;
            status = source === latest && idsMatch ? 'matched' : latest > source ? 'newer' : 'different';
        }
        const notes = [];
        if (used && usedRoundMatches) {
            if (used.is_active && ['LOW', 'MEDIUM', 'HIGH'].includes(used.rain_risk)) {
                const probability = Number.isFinite(used.race_rain_probability)
                    ? ` (${used.race_rain_probability}% chance)` : '';
                notes.push(`Race rain risk used: ${used.rain_risk}${probability}.`);
                if (Number.isFinite(used.noise_mult) && used.noise_mult > 1)
                    notes.push(`Simulation uncertainty setting +${Math.round((used.noise_mult - 1) * 100)}%.`);
                if (Number.isFinite(used.dnf_mult) && used.dnf_mult > 1)
                    notes.push(`DNF probability multiplier ×${Number(used.dnf_mult.toFixed(2))} (+${Math.round((used.dnf_mult - 1) * 100)}%, subject to the model's cap).`);
                if (used.wet_weight > 0) notes.push('Small wet-weather driver adjustments applied.');
            }
            if (used.is_active && used.cold_weight > 0) {
                const temperature = Number.isFinite(used.race_air_temp_C) ? ` (${used.race_air_temp_C.toFixed(1)}°C air)` : '';
                notes.push(`Cool-weather team adjustments applied${temperature}.`);
            }
            if (!used.is_active && source !== null)
                notes.push('No extra rain or cool-weather simulation adjustments were applied.');
        }
        let notice = '';
        if (status === 'newer') notice = `The forecast was updated on ${dateLabel(forecast.last_updated)}. That newer weather has not been applied to these predictions.`;
        else if (status === 'different-round') notice = 'The displayed forecast and predictions are for different rounds, or their weather record does not match. Do not combine them.';
        else if (status === 'different') notice = 'The displayed forecast and simulation use different weather versions. The adjustments below describe the simulation only.';
        else if (status === 'unknown') notice = 'The weather version used by this simulation cannot be verified against the displayed forecast.';
        return { status, title: `Weather used in this simulation: ${dateLabel(used?.source)}`, notes, notice };
    }
    const api = { describe, dateLabel };
    root.BoxBoxWeatherContext = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
