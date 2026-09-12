'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const { createModel, modelFor } = require('../public/long-run-explorer');

function run(session, kept, excluded = [], stint = 1) {
    return { session, compound: 'SOFT', stint, kept_laps: kept, excluded_laps: excluded };
}
function fixture() {
    return {
        season: 2026, round: 16,
        long_run_pace: {
            AAA: { headline_session: 'FP2', runs: [run('FP1', [70, 72]), run('FP2', [90, 110], [150, 110])] },
            BBB: { headline_session: 'FP2', runs: [run('FP2', [102, 104])] },
        },
    };
}
const driver = (model, id) => model.rows().find(row => row.id === id);

test('model defaults include kept laps and expose excluded laps as individual choices', () => {
    const model = createModel(fixture());
    const a = driver(model, 'AAA');
    assert.equal(a.average, 100);
    assert.equal(a.count, 2);
    assert.equal(a.rank, 1);
    assert.equal(driver(model, 'BBB').gap, 3);
    assert.deepEqual(a.runs[1].laps.map(lap => lap.included), [true, true, false, false]);
});

test('excluding a kept lap recalculates run average, driver average, gaps and order', () => {
    const model = createModel(fixture());
    model.toggle(driver(model, 'AAA').runs[1].laps[0].key);
    assert.deepEqual(model.rows().map(row => row.id), ['BBB', 'AAA']);
    assert.equal(driver(model, 'AAA').runs[1].average, 110);
    assert.equal(driver(model, 'AAA').average, 110);
    assert.equal(driver(model, 'AAA').gap, 7);
    assert.equal(driver(model, 'AAA').rank, 2);
    assert.equal(model.changes, 1);
});

test('algorithm-excluded laps can be restored and duplicate times toggle independently', () => {
    const model = createModel(fixture());
    const laps = driver(model, 'AAA').runs[1].laps;
    assert.notEqual(laps[1].key, laps[3].key);
    model.toggle(laps[3].key);
    assert.equal(driver(model, 'AAA').average, 310 / 3);
    model.toggle(laps[1].key);
    assert.deepEqual(driver(model, 'AAA').runs[1].laps.map(lap => lap.included), [true, false, false, true]);
    assert.equal(driver(model, 'AAA').average, 100);
    model.toggle(laps[2].key);
    assert.equal(driver(model, 'AAA').average, 350 / 3);
});

test('headline pace is lap-weighted across runs in one session, never across sessions', () => {
    const model = createModel({ long_run_pace: { AAA: { runs: [
        run('FP1', [50, 50, 50]), run('FP2', [90, 90, 90, 90]), run('FP2', [120], [], 2),
    ] } } });
    assert.equal(driver(model, 'AAA').session, 'FP2');
    assert.equal(driver(model, 'AAA').average, 96);
    assert.equal(driver(model, 'AAA').count, 5);
    model.toggle(driver(model, 'AAA').runs[0].laps[0].key);
    assert.equal(driver(model, 'AAA').average, 96);
    model.setSession('FP1');
    assert.equal(driver(model, 'AAA').average, 50);
    assert.equal(driver(model, 'AAA').count, 2);
});

test('removing every comparison lap leaves an unranked driver without silently changing session', () => {
    const model = createModel(fixture());
    driver(model, 'AAA').runs[1].laps.filter(lap => lap.included).forEach(lap => model.toggle(lap.key));
    const a = driver(model, 'AAA');
    assert.equal(a.session, 'FP2');
    assert.equal(a.average, null);
    assert.equal(a.rank, null);
    assert.equal(a.gap, null);
    assert.equal(a.count, 0);
    assert.equal(model.rows()[1].id, 'AAA');
    model.toggle(a.runs[1].laps[0].key);
    assert.equal(driver(model, 'AAA').average, 90);
    assert.equal(driver(model, 'AAA').count, 1);
});

test('all drivers can be deselected without NaN or infinity leaking into averages and gaps', () => {
    const model = createModel(fixture());
    model.rows().forEach(row => row.runs.flatMap(run => run.laps).filter(lap => lap.included).forEach(lap => model.toggle(lap.key)));
    model.rows().forEach(row => {
        assert.equal(row.average, null);
        assert.equal(row.gap, null);
        assert.equal(row.rank, null);
    });
});

test('per-driver reset and reset-all restore exactly the original selection', () => {
    const model = createModel(fixture());
    const original = model.rows();
    model.toggle(original[0].runs[1].laps[0].key);
    model.toggle(original[1].runs[0].laps[0].key);
    model.reset('AAA');
    assert.equal(driver(model, 'AAA').average, 100);
    assert.equal(model.changes, 1);
    model.reset();
    assert.equal(model.changes, 0);
    assert.deepEqual(model.rows(), original);
});

test('toggling twice restores model state and source data never changes', () => {
    const source = fixture();
    const original = JSON.stringify(source);
    const model = createModel(source);
    const key = driver(model, 'AAA').runs[1].laps[2].key;
    model.toggle(key); model.toggle(key);
    assert.equal(model.changes, 0);
    assert.equal(JSON.stringify(source), original);
    assert.equal(model.toggle('unknown lap'), false);
});

test('selecting a session with missing evidence does not invent pace', () => {
    const model = createModel(fixture());
    model.setSession('FP1');
    assert.equal(driver(model, 'AAA').average, 71);
    assert.equal(driver(model, 'BBB').average, null);
    model.setSession('invalid');
    assert.equal(model.session, 'FP1');
});

test('roster filter keeps practice-only drivers out of comparison', () => {
    const model = createModel(fixture(), ['BBB']);
    assert.deepEqual(model.rows().map(row => row.id), ['BBB']);
    assert.equal(model.rows()[0].gap, 0);
});

test('edits persist on tab remount but reset for new round or changed lap data', () => {
    const source = fixture();
    const model = modelFor(source, []);
    model.toggle(model.rows()[0].runs[1].laps[0].key);
    assert.equal(modelFor(JSON.parse(JSON.stringify(source)), []).changes, 1);
    const refreshed = fixture();
    refreshed.long_run_pace.AAA.runs[1].kept_laps[0] = 91;
    assert.equal(modelFor(refreshed, []).changes, 0);
    modelFor(source, []).toggle(modelFor(source, []).rows()[0].runs[1].laps[0].key);
    assert.equal(modelFor({ ...source, round: 17 }, []).changes, 0);
});
