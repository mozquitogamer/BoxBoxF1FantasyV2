const assert = require('node:assert/strict');
const vm = require('node:vm');
const { sandbox } = require('./app_js_harness');

vm.runInContext(`v13Data = {current_state: {next_round: 22}, labels: {drivers: {VER: 'Max Verstappen', ANT: 'Kimi Antonelli'}}}`, sandbox);
const html = vm.runInContext(`v13SnapshotCard('Current choice', {
    round: 22, phase: 'post_fp', status: 'corrected_before_lock', lock_deadline: '2099-11-07T18:00:00Z',
    drivers: ['VER', 'ANT'], constructors: [], captain: 'VER', second_boost: 'ANT', chip: '3x_boost'
}, '')`, sandbox);
assert.match(html, /Max Verstappen<b>3x<\/b>/);
assert.match(html, /Kimi Antonelli<b>2x<\/b>/);
assert.match(html, /Provisional until team lock/);
const history = vm.runInContext(`v13RoundHistory({round: 21, race: 'Mexico', provenance: 'corrected_replay', post_fp_final: {drivers: [], constructors: []}}, false)`, sandbox);
assert.match(history, /Corrected replay/);
console.log('V13 boost badges, provisional choice and correction labels passed');
