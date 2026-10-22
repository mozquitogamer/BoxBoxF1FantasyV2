const assert = require('node:assert/strict');
const vm = require('node:vm');
const { S, sandbox, fs, path } = require('./app_js_harness');

S.setPriceLoaderState({ round: 20 }, null, { rounds: [] });

// Every rating and both asset types respect the bounds, including partial moves.
for (const identity of [{ driver_id: 'TEST' }, { constructor_id: 'test' }]) {
    for (const [price, points, change] of [
        [34, 100, 0], [33.9, 100, 0.1], [33.8, 100, 0.2],
        [34, 0, -0.3], [33, 100, 0.3], [10, 100, 0.6],
        [3, 0, 0], [3.1, 0, -0.1], [3.5, 0, -0.5], [3, 100, 0.6],
    ]) {
        const item = { ...identity, current_price: price, expected_points: points };
        const forecast = S.predictPriceChange(item, points);
        assert.equal(forecast.expectedChange, change, JSON.stringify(item));
        for (const delta of Object.values(forecast.tierChanges)) {
            assert.ok(price + delta >= 3 && price + delta <= 34);
        }
    }
}

const mercedes = { constructor_id: 'test', current_price: 34, expected_points: 100 };
const cappedCard = sandbox.renderPriceChangeBrackets(mercedes);
assert.ok(cappedCard.includes('At $34.0M ceiling'));
assert.ok(cappedCard.includes('No rise'));
assert.ok(!cappedCard.includes('+0.3M') && !cappedCard.includes('+0.1M'));
assert.ok(sandbox.renderPriceChangeBrackets({ ...mercedes, expected_points: 0 }).includes('-0.3M'));
assert.ok(sandbox.renderPriceChangeBrackets({ ...mercedes, current_price: 33.8 }).includes('+0.2M'));
assert.equal(sandbox.projectedTeamPriceChange([], [mercedes]), 0);

// A near-ceiling asset can use its remaining headroom only once across a horizon.
const driver = { driver_id: 'TEST', current_price: 33.8, expected_points: 100 };
const team = { constructor_id: 'test', current_price: 33.9, expected_points: 100 };
const rounds = Array.from({ length: 5 }, () => ({ drivers: { TEST: 100 }, constructors: { test: 100 } }));
const changes = sandbox.projectPriceChangesForRounds([driver], [team], rounds);
assert.deepEqual(Array.from(changes, row => row.TEST), [0.2, 0, 0, 0, 0]);
assert.deepEqual(Array.from(changes, row => row.test), [0.1, 0, 0, 0, 0]);
assert.equal(driver.current_price, 33.8, 'projection must not mutate live prices');
assert.equal(team.current_price, 33.9);
const recovery = sandbox.projectPriceChangesForRounds([], [mercedes], [
    { drivers: {}, constructors: { test: 0 } },
    { drivers: {}, constructors: { test: 100 } },
    { drivers: {}, constructors: { test: 100 } },
]);
assert.deepEqual(Array.from(recovery, row => row.test), [-0.3, 0.3, 0]);

// Check the actual published roster and Mercedes using its official score history.
const readData = name => JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'web', 'public', 'data', name), 'utf8'));
const live = readData('predictions.json');
S.setPriceLoaderState(live, readData('official_points.json'), readData('season_summary.json'));
const liveMercedes = live.constructors.find(item => item.constructor_id === 'mercedes');
assert.equal(liveMercedes.current_price, 34);
assert.equal(S.predictPriceChange(liveMercedes, liveMercedes.expected_points).expectedChange, 0);
for (const item of [...live.drivers, ...live.constructors]) {
    const nextPrice = item.current_price + S.predictPriceChange(item, item.expected_points).expectedChange;
    assert.ok(nextPrice >= 3 && nextPrice <= 34, item.driver_id || item.constructor_id);
}

// Exercise the actual beam search, hold comparison and target feasibility paths.
async function checkPlanner() {
    const drivers = ['A', 'B', 'C', 'D', 'E'].map(driver_id => ({
        driver_id, current_price: 33.8, expected_points: 100, projected_points: 100,
    }));
    const constructors = ['x', 'y'].map(constructor_id => ({
        constructor_id, current_price: 34, expected_points: 100, projected_points: 100,
    }));
    S.setTransferRenderState('projected', { round: 20, drivers, constructors }, drivers.map(d => d.driver_id), ['x', 'y']);
    S.setPriceLoaderState({ round: 20, drivers, constructors }, null, {
        rounds: [20, 21, 22].map(round => ({ round, name: 'Test GP' })),
    });
    vm.runInContext(`
        trackData = { sprint_rounds: [], race_circuit_map: {}, track_features: {} };
        targetTeamDrivers = ['A', 'B', 'C', 'D', 'E'];
        targetTeamConstructors = ['x', 'y'];
    `, sandbox);
    const originalGetElement = sandbox.document.getElementById;
    const values = { mwBudget: '237', mwFreeTransfers: '2', mwHorizon: '3', mwStrategy: 'max_points', pointsBasisMW: 'projected' };
    sandbox.document.getElementById = id => ({ ...originalGetElement(id), value: values[id] || '', checked: id === 'mwUseTarget' });
    sandbox.loadMultiWeekData = async () => {};
    let result;
    sandbox.displayMultiWeekResults = (plans, projections, round, feasibility) => { result = { plans, feasibility }; };
    await sandbox.runMultiWeekPlanner();
    assert.ok(result.plans.length > 0);
    assert.equal(result.feasibility.horizonAppreciation, 1);
    for (const plan of result.plans) {
        assert.equal(plan.budget, 238);
        assert.deepEqual(Array.from(plan.roundActions, action => action.appreciation), [1, 0, 0]);
        assert.deepEqual(Array.from(plan.roundActions, action => action.holdBudgetAfter), [238, 238, 238]);
    }
}

checkPlanner().then(() => console.log('PASS: asset price bounds, Mercedes, cards and multi-week budgets.')).catch(error => {
    console.error(error);
    process.exitCode = 1;
});
