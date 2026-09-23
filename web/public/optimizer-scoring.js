(function (root, factory) {
    const api = factory();
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else root.BoxBoxOptimizerScoring = api;
}(typeof window !== 'undefined' ? window : globalThis, function () {
    'use strict';

    function adjustmentDelta(item) {
        const delta = Number(item?.points_delta);
        return Number.isFinite(delta) ? delta : 0;
    }

    function adjustedRiskPoints(item) {
        const adjusted = Number(item?.expected_points_adjusted);
        if (Number.isFinite(adjusted)) return adjusted;
        const baseline = Number(item?.expected_points);
        return Number.isFinite(baseline) ? baseline + adjustmentDelta(item) : 0;
    }

    function adjustedProjectedPoints(item) {
        const baseline = Number(item?.projected_points);
        if (Number.isFinite(baseline)) return baseline + adjustmentDelta(item);
        return adjustedRiskPoints(item);
    }

    function basisPointsFor(item, basis = 'balanced') {
        const risk = adjustedRiskPoints(item);
        const proj = adjustedProjectedPoints(item);
        if (basis === 'projected') return proj;
        if (basis === 'risk_adjusted') return risk;
        return (proj + risk) / 2;
    }

    function adjustedBasisPoints(item, chip, basis = 'balanced') {
        let pts = basisPointsFor(item, basis);
        if (chip === 'no_negative' && pts < 0) pts = 0;
        return pts;
    }

    function intervalPoints(item, key, chip) {
        let pts;
        if (key === 'p5') pts = item.mc_total_p5;
        else if (key === 'p95') pts = item.mc_total_p95;
        else pts = item.mc_total_mean;
        if (typeof pts !== 'number') pts = (typeof item.expected_points === 'number') ? item.expected_points : 0;
        if (chip === 'no_negative' && pts < 0) pts = 0;
        return pts;
    }

    function getBoostTargets(drivers, chip, basis) {
        const sorted = [...drivers].sort((a, b) => adjustedBasisPoints(b, chip, basis) - adjustedBasisPoints(a, chip, basis));
        return {
            primary: sorted[0] || null,
            secondary: (chip === '3x_boost' && sorted.length > 1) ? sorted[1] : null,
        };
    }

    function scoreTeamPicks(drivers, constructorsList, chip, basis = 'balanced') {
        const { primary, secondary } = getBoostTargets(drivers, chip, basis);
        const primaryId = primary ? primary.driver_id : null;
        const secondaryId = secondary ? secondary.driver_id : null;

        function totalFor(kind) {
            let total = 0;
            for (const d of drivers) {
                total += kind === 'basis' ? adjustedBasisPoints(d, chip, basis) : intervalPoints(d, kind, chip);
            }
            for (const c of constructorsList) {
                total += kind === 'basis' ? adjustedBasisPoints(c, chip, basis) : intervalPoints(c, kind, chip);
            }
            if (primary) {
                const p = kind === 'basis' ? adjustedBasisPoints(primary, chip, basis) : intervalPoints(primary, kind, chip);
                total += p * (chip === '3x_boost' ? 2 : 1);
            }
            if (secondary) {
                const p = kind === 'basis' ? adjustedBasisPoints(secondary, chip, basis) : intervalPoints(secondary, kind, chip);
                total += p;
            }
            return total;
        }

        return {
            expected: totalFor('basis'),
            floor: totalFor('p5'),
            ceiling: totalFor('p95'),
            boostedDriverId: primaryId,
            secondBoostedDriverId: secondaryId,
        };
    }

    return Object.freeze({ basisPointsFor, adjustedBasisPoints, intervalPoints, scoreTeamPicks });
}));
