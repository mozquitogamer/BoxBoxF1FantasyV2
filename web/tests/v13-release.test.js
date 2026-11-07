'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { checkV13 } = require('../scripts/check-v13-current');

const root = fs.mkdtempSync(path.join(os.tmpdir(), 'v13-release-'));
const web = path.join(root, 'web');
const data = path.join(web, 'public/data');
fs.mkdirSync(data, { recursive: true });
const predictions = { round: 22, phase: 'post_fp', generated_at: '2026-11-07T14:00:00Z' };
const bytes = JSON.stringify(predictions);
fs.writeFileSync(path.join(data, 'forecast.json'), bytes);
const decision = { round: 22, phase: 'post_fp', source_generated_at: predictions.generated_at,
    lock_deadline: '2026-11-07T18:00:00Z', team_cost: 99, archive: 'web/public/data/forecast.json',
    archive_sha256: crypto.createHash('sha256').update(bytes).digest('hex') };
const manager = { current_state: { budget: 100, post_fp_final: decision } };
const save = () => {
    fs.writeFileSync(path.join(data, 'predictions.json'), JSON.stringify(predictions));
    fs.writeFileSync(path.join(data, 'v13_manager.json'), JSON.stringify(manager));
};
try {
    save(); checkV13(web);
    decision.source_generated_at = '2026-11-06T14:00:00Z'; save();
    assert.throws(() => checkV13(web), /Refresh V13/);
    decision.source_generated_at = predictions.generated_at;
    decision.team_cost = 101; save();
    assert.throws(() => checkV13(web), /exceeds its budget/);
    decision.team_cost = 99;
    fs.writeFileSync(path.join(data, 'forecast.json'), JSON.stringify({ ...predictions, different: true })); save();
    assert.throws(() => checkV13(web), /proof does not match/);
    predictions.phase = 'post_quali'; save(); checkV13(web);
    predictions.phase = 'post_fp';
    manager.current_state.as_of_round = 22;
    manager.current_state.post_fp_final = null;
    save(); checkV13(web); // Completed round may roll forward to the next race.
    console.log('V13 deployment freshness checks passed');
} finally {
    for (const name of ['forecast.json', 'predictions.json', 'v13_manager.json']) fs.unlinkSync(path.join(data, name));
    for (const dir of [data, path.dirname(data), web, root]) fs.rmdirSync(dir);
}
