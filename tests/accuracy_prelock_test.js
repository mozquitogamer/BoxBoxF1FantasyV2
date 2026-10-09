const assert = require('node:assert/strict');
const vm = require('node:vm');
const { sandbox, fs, path } = require('./app_js_harness');
const match = (rows, id, actual, drivers=true) => vm.runInContext(`accuracyForecastForAsset(${JSON.stringify(rows)}, ${JSON.stringify(id)}, ${JSON.stringify(actual)}, ${drivers})`, sandbox);
assert.equal(vm.runInContext('accuracyPhase',sandbox),'prelock');
const scoped = {driver_id:'LAW_RED_BULL',asset_legacy_ids:['LAW'],constructor:'red_bull',expected_points:12};
assert.equal(match([scoped],'LAW',{constructor:'red_bull'}).driver_id,'LAW_RED_BULL');
assert.equal(match([scoped],'LAW',{constructor:'racing_bulls'}),null);
assert.equal(match([scoped,{...scoped,driver_id:'duplicate'}],'LAW',{constructor:'red_bull'}),null);
const validate = forecast => vm.runInContext(`validateAccuracyPrelock(${JSON.stringify(forecast)},17)`,sandbox);
const eligible = {round:17,phase:'post_fp',generated_at:'2026-09-25T11:00:00Z',exported_at:'2026-09-25T11:01:00Z'};
assert.ok(validate(eligible));
assert.equal(validate({...eligible,exported_at:'2026-09-25T12:01:00Z'}),null);
assert.equal(validate({...eligible,reconstructed:true}),null);
assert.equal(validate({...eligible,phase:'post_quali'}),null);
const index=JSON.parse(fs.readFileSync(path.join(__dirname,'../web/public/data/accuracy_prelock.json'),'utf8'));
assert.ok([7,8,9,10,11,12,13,14,15,16,17,18].every(round=>index.rounds.some(row=>row.round===round)));
for(const row of index.rounds){
 const actual=JSON.parse(fs.readFileSync(path.join(__dirname,`../web/public/data/actual_round${row.round}.json`),'utf8'));
 assert.equal(actual.drivers.filter(a=>match(row.forecast.drivers,a.driver_id,a)).length,22);
}
console.log('PASS: before-lock selection, deadline/reconstruction rejection and all 22 historical driver joins across 12 rounds.');
