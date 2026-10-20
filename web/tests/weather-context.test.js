const test = require('node:test');
const assert = require('node:assert/strict');
const { describe } = require('../public/weather-context');
const old = '2026-10-13T00:03:31Z';
const recent = '2026-10-20T02:42:05Z';
function prediction(extra = {}) {
    return { round: 20, weather_adjustments: { source: old, is_active: true,
        rain_risk: 'LOW', race_air_temp_C: 17.4, noise_mult: 1.02,
        dnf_mult: 1.05, wet_weight: 0.01, cold_weight: 0.03, ...extra } };
}
const latest = { round: 20, last_updated: recent,
    sessions: [{ name: 'Race', rain_probability: 4, avg_temp: 26.4 }] };
test('old simulation with newer dry weather never borrows live rain probability', () => {
    const result = describe(prediction(), latest);
    assert.equal(result.status, 'newer');
    assert.match(result.notice, /has not been applied/);
    assert.match(result.title, /13 Oct 2026/);
    assert.match(result.notes.join(' '), /17.4°C/);
    assert.doesNotMatch(result.notes.join(' '), /4%|26.4|×1.1|confidence intervals/);
    assert.match(result.notes.join(' '), /×1.05 \(\+5%/);
});
test('stored probability is used even when live weather differs', () => {
    assert.match(describe(prediction({ race_rain_probability: 16 }), latest).notes.join(' '), /16% chance/);
});
test('matched neutral forecast has no rain or cold adjustment claims', () => {
    const result = describe(prediction({ source: recent, is_active: false, rain_risk: 'NONE',
        cold_weight: 0, wet_weight: 0, noise_mult: 1, dnf_mult: 1 }), latest);
    assert.equal(result.status, 'matched');
    assert.equal(result.notice, '');
    assert.deepEqual(result.notes, ['No extra rain or cool-weather simulation adjustments were applied.']);
});
test('neutral simulation still warns when its forecast is superseded', () => {
    assert.match(describe(prediction({ is_active: false }), latest).notice, /has not been applied/);
});
test('same-day updates are detected with full timestamps', () => {
    assert.equal(describe(prediction({ source: '2026-10-20T01:42:05Z' }), latest).status, 'newer');
});
test('missing source and different rounds cannot be described as matched', () => {
    assert.equal(describe(prediction({ source: null }), latest).status, 'unknown');
    assert.equal(describe(prediction(), { ...latest, round: 21 }).status, 'different-round');
    assert.deepEqual(describe(prediction({ round: 19 }), latest).notes, []);
});
test('different snapshot IDs and an older displayed forecast remain explicit', () => {
    assert.equal(describe(prediction({ source: recent, forecast_snapshot_id: 'a' }),
        { ...latest, forecast_snapshot_id: 'b' }).status, 'different');
    assert.equal(describe(prediction({ source: recent }), { ...latest, last_updated: old }).status, 'different');
});
test('HTML loads the tested weather module before app.js', () => {
    const fs = require('node:fs');
    const path = require('node:path');
    const html = fs.readFileSync(path.join(__dirname, '../public/index.html'), 'utf8');
    assert.ok(html.indexOf('src="weather-context.js?') < html.indexOf('src="app.js?'));
    assert.ok(html.includes('src="weather-context.js?'));
});

test('rendered widget and card tooltip retain simulation provenance', () => {
    const vm = require('node:vm');
    const { sandbox } = require('../../tests/app_js_harness');
    const container = { innerHTML: '' };
    sandbox.document.getElementById = id => id === 'weatherSection' ? container : null;
    sandbox.fixturePrediction = prediction();
    sandbox.fixtureWeather = { ...latest, race: 'United States Grand Prix', overall_rain_risk: 'NONE',
        next_update: '2026-10-20T08:42:05Z' };
    vm.runInContext('data = fixturePrediction; weatherData = fixtureWeather; renderWeather();', sandbox);
    const notice = container.innerHTML.split('class="weather-adjust-explainer"')[1];
    assert.match(notice, /has not been applied/);
    assert.match(notice, /17.4°C/);
    assert.doesNotMatch(notice, /4%|26.4|×1.1/);
    const badges = vm.runInContext('renderWeatherBadges()', sandbox);
    assert.match(badges, /Simulation weather from 13 Oct 2026/);
    assert.match(badges, /×1.05/);
});
