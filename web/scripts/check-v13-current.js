'use strict';
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');

function checkV13(webRoot) {
    const read = name => JSON.parse(fs.readFileSync(path.join(webRoot, 'public/data', name), 'utf8'));
    const predictions = read('predictions.json');
    if (predictions.reconstructed || !['pre_fp', 'post_fp'].includes(predictions.phase)) return;
    const manager = read('v13_manager.json');
    // Post-race settlement advances the manager before the next forecast is
    // published. The completed race's normal team must stay frozen then.
    if (Number(manager.current_state?.as_of_round) >= Number(predictions.round)) return;
    const decision = manager.current_state?.[predictions.phase === 'pre_fp' ? 'early_thoughts' : 'post_fp_final'];
    assert.ok(decision, 'V13 has no choice for the current simulation');
    assert.equal(decision.round, predictions.round, 'V13 round is stale');
    assert.equal(decision.phase, predictions.phase, 'V13 phase is stale');
    const generated = Date.parse(predictions.generated_at);
    const lock = Date.parse(decision.lock_deadline);
    assert.ok(Number.isFinite(generated) && Number.isFinite(lock), 'Missing valid forecast or lock time');
    if (generated >= lock) return; // Post-lock sims cannot revise the locked normal team.
    assert.equal(decision.source_generated_at, predictions.generated_at, 'Refresh V13 after the latest simulation before deploying');
    const archive = path.resolve(webRoot, '..', decision.archive);
    assert.ok(archive.startsWith(path.resolve(webRoot, 'public/data') + path.sep), 'Invalid V13 forecast archive');
    const bytes = fs.readFileSync(archive);
    assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'), decision.archive_sha256, 'V13 forecast proof does not match');
    assert.deepEqual(JSON.parse(bytes), predictions, 'V13 was chosen from a different forecast');
    assert.ok(decision.team_cost <= manager.current_state.budget + 1e-6 || decision.chip === 'limitless', 'V13 choice exceeds its budget');
    console.log(`V13 matches R${predictions.round} ${predictions.phase} ${predictions.generated_at}`);
}

module.exports = { checkV13 };
if (require.main === module) checkV13(path.resolve(__dirname, '..'));
