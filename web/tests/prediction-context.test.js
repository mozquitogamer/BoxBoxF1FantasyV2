const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { phaseLabel, context } = require('../public/prediction-context');

const forecast = { round: 18, race: 'Bahrain Grand Prix in Malaysia', season: 2026,
    date: '2026-10-04', phase: 'post_fp', fp_sessions_included: ['FP1', 'FP2', 'FP3'],
    generated_at: '2026-10-06T09:00:00Z', simulation_generated_at: '2026-10-03T06:10:00Z' };
const rounds = [{ round: 18, date: '2026-10-04', has_actual: true },
    { round: 19, name: 'Singapore Grand Prix', date: '2026-10-11' }];

test('FP versions use recorded session evidence, including partial weekends', () => {
    assert.equal(phaseLabel(forecast), 'Post FP3');
    assert.equal(phaseLabel({ ...forecast, fp_sessions_included: ['FP1', 'FP2'] }), 'Post FP2');
    assert.equal(phaseLabel({ ...forecast, fp_sessions_included: ['FP1'], is_sprint_weekend: true }), 'Post FP1');
    assert.equal(phaseLabel({ ...forecast, fp_sessions_included: [] }), 'Post practice');
    assert.equal(phaseLabel({ phase: 'post_quali' }), 'Post qualifying');
    assert.equal(phaseLabel({ phase: 'pre_fp' }), 'Pre-practice');
    assert.equal(phaseLabel({}), 'Version unavailable');
});

test('a completed Bahrain forecast stays labelled Bahrain while Singapore is pending', () => {
    const result = context(forecast, rounds, new Date('2026-10-06T10:00:00Z'));
    assert.equal(result.archived, true);
    assert.match(result.notice, /Round 18/);
    assert.match(result.notice, /Singapore Grand Prix \(Round 19\) simulations are pending/);
    assert.equal(result.generatedAt, forecast.simulation_generated_at);
});

test('passing the Fantasy deadline does not label a pre-race forecast complete', () => {
    const result = context(forecast, [], new Date('2026-10-03T10:00:00Z'));
    assert.equal(result.archived, false);
    assert.equal(result.notice, '');
});

test('both tabs and a mismatched weather widget preserve their race identities', () => {
    const { sandbox } = require('../../tests/app_js_harness');
    const elements = new Map();
    sandbox.document.getElementById = id => {
        if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '' });
        return elements.get(id);
    };
    sandbox.__forecast = forecast;
    sandbox.__rounds = rounds;
    sandbox.__weather = { round: 19, race: 'Singapore Grand Prix', sessions: [],
        overall_rain_risk: 'HIGH', last_updated: '2026-10-06T06:00:00Z', next_update: '2026-10-06T12:00:00Z' };
    forecast.weather_adjustments = { is_active: true, rain_risk: 'HIGH', noise_mult: 1.15, dnf_mult: 1.25 };
    vm.runInContext('data = __forecast; seasonSummary = { rounds: __rounds }; weatherData = __weather; renderPredictionContext(); renderWeather();', sandbox);
    assert.equal(elements.get('raceName').textContent, forecast.race);
    for (const id of ['driverPredictionContext', 'constructorPredictionContext']) {
        assert.match(elements.get(id).innerHTML, /Bahrain Grand Prix in Malaysia · Round 18/);
        assert.match(elements.get(id).innerHTML, /Post FP3/);
    }
    assert.match(elements.get('weatherSection').innerHTML, /Singapore Grand Prix · Round 19/);
    assert.match(elements.get('weatherSection').innerHTML, /simulations shown here are for Bahrain/);
    assert.doesNotMatch(elements.get('weatherSection').innerHTML, /confidence intervals widened/);
});

test('the page loads the version helper before the app and includes both labels', () => {
    const html = fs.readFileSync(path.join(__dirname, '../public/index.html'), 'utf8');
    assert.ok(html.indexOf('src="prediction-context.js') < html.indexOf('src="app.js'));
    assert.match(html, /id="driverPredictionContext"/);
    assert.match(html, /id="constructorPredictionContext"/);
});
