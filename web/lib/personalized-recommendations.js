'use strict';

function number(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function assetScore(asset, phase = 'post_fp') {
    if (!asset) return 0;
    if (phase === 'post_quali' && asset.projected_points_race !== undefined) {
        return number(asset.projected_points_race);
    }
    const projected = number(asset.projected_points, number(asset.expected_points));
    const simulated = number(asset.expected_points, projected);
    return (projected + simulated) / 2;
}

function heldDriverAssets(predictions) {
    if (Number(predictions.round) !== 14 || predictions.driver_assets?.override_active !== true) return [];
    const drivers = predictions.drivers || [];
    const definitions = [
        ['HAD', 'Isack Hadjar', 'red_bull', 'LAW_RED_BULL'],
        ['LAW', 'Liam Lawson', 'racing_bulls', 'TSU_RACING_BULLS'],
    ];
    return definitions.map(([driverId, name, constructor, priceSourceId]) => {
        const source = drivers.find(item => String(item.driver_id) === priceSourceId);
        if (!source) return null;
        return {
            ...source,
            driver_id: driverId,
            name,
            constructor,
            projected_points: 0,
            expected_points: 0,
            projected_points_race: 0,
            held_only: true,
        };
    }).filter(Boolean);
}

function indexAssets(predictions) {
    const drivers = [...(predictions.drivers || []), ...heldDriverAssets(predictions)];
    return {
        drivers: new Map(drivers.map(item => [String(item.driver_id), item])),
        constructors: new Map((predictions.constructors || []).map(item => [String(item.constructor_id), item])),
    };
}

function currentIds(team, assetType) {
    return (team.assets || [])
        .filter(item => item.asset_type === assetType)
        .sort((left, right) => number(left.slot) - number(right.slot))
        .map(item => String(item.asset_id));
}

function bestSingleSwap(predictions, team) {
    const phase = String(predictions.phase || 'post_fp');
    const indexed = indexAssets(predictions);
    const driverIds = currentIds(team, 'driver');
    const constructorIds = currentIds(team, 'constructor');
    const budget = number(team.budget_millions, 100);
    const freeTransfers = number(team.free_transfers, 0);
    const currentDrivers = driverIds.map(id => indexed.drivers.get(id)).filter(Boolean);
    const currentConstructors = constructorIds.map(id => indexed.constructors.get(id)).filter(Boolean);
    const currentCost = [...currentDrivers, ...currentConstructors].reduce((total, item) => total + number(item.current_price), 0);
    const penalty = phase === 'post_quali' || freeTransfers > 0 ? 0 : 10;
    let best = null;

    const evaluate = (assetType, outgoing, incoming) => {
        const finalCost = currentCost - number(outgoing.current_price) + number(incoming.current_price);
        if (phase !== 'post_quali' && finalCost > budget + 0.001) return;
        const rawGain = assetScore(incoming, phase) - assetScore(outgoing, phase);
        const netGain = rawGain - penalty;
        const candidate = {
            asset_type: assetType,
            outgoing_id: assetType === 'driver' ? outgoing.driver_id : outgoing.constructor_id,
            outgoing_name: outgoing.name || outgoing.full_name,
            incoming_id: assetType === 'driver' ? incoming.driver_id : incoming.constructor_id,
            incoming_name: incoming.name || incoming.full_name,
            raw_gain: rawGain,
            transfer_penalty: penalty,
            projected_gain: netGain,
            final_cost: finalCost,
        };
        if (!best || candidate.projected_gain > best.projected_gain) best = candidate;
    };

    for (const outgoing of currentDrivers) {
        for (const incoming of predictions.drivers || []) {
            if (!driverIds.includes(String(incoming.driver_id))) evaluate('driver', outgoing, incoming);
        }
    }
    if (phase !== 'post_quali') {
        for (const outgoing of currentConstructors) {
            for (const incoming of predictions.constructors || []) {
                if (!constructorIds.includes(String(incoming.constructor_id))) evaluate('constructor', outgoing, incoming);
            }
        }
    }

    return { best, indexed, driverIds, constructorIds, currentDrivers, currentConstructors, currentCost };
}

function buildRecommendation(predictions, team) {
    const phase = String(predictions.phase || 'post_fp');
    const race = String(predictions.race || 'the next Grand Prix');
    const result = bestSingleSwap(predictions, team);
    const drivers = result.currentDrivers;
    const constructors = result.currentConstructors;
    const captain = [...drivers].sort((left, right) => assetScore(right, phase) - assetScore(left, phase))[0] || null;
    const baseScore = [...drivers, ...constructors].reduce((total, item) => total + assetScore(item, phase), 0);
    const teamScore = baseScore + assetScore(captain, phase);
    const threshold = phase === 'pre_fp' ? 2.5 : phase === 'post_quali' ? 0.5 : 1.0;
    const move = result.best && result.best.projected_gain >= threshold ? result.best : null;

    let headline;
    let explanation;
    if (move && phase === 'post_quali') {
        headline = `Final Fix check: ${move.outgoing_name} → ${move.incoming_name}`;
        explanation = `If you still have Final Fix, the updated race-only model sees about ${move.projected_gain.toFixed(1)} points of upside.`;
    } else if (move) {
        headline = `${move.outgoing_name} → ${move.incoming_name}`;
        const penaltyText = move.transfer_penalty ? ` after the ${move.transfer_penalty}-point extra-transfer cost` : '';
        explanation = `This is the strongest affordable one-move upgrade in the new simulation: about ${move.projected_gain.toFixed(1)} net points${penaltyText}.`;
    } else {
        headline = 'Hold your current lineup';
        explanation = phase === 'pre_fp'
            ? 'The early model does not see a strong enough one-move edge yet. Keep flexibility for the post-FP update.'
            : 'No affordable one-move change clears the model’s action threshold, so the disciplined call is to hold.';
    }

    return {
        race,
        round: number(predictions.round),
        season: number(predictions.season, 2026),
        phase,
        headline,
        explanation,
        move,
        captain: captain ? {
            id: captain.driver_id,
            name: captain.name,
            projected_points: assetScore(captain, phase),
        } : null,
        projected_team_points: teamScore,
        current_cost: result.currentCost,
        budget_millions: number(team.budget_millions, 100),
        lineup: {
            drivers: drivers.map(item => item.name || item.driver_id),
            constructors: constructors.map(item => item.name || item.constructor_id),
        },
        generated_from: predictions.generated_at || predictions.exported_at || null,
    };
}

module.exports = { assetScore, bestSingleSwap, buildRecommendation, heldDriverAssets };
