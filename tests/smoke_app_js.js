const { S, src, fail } = require('./app_js_harness');

// 1) Tunable blocks must be defined objects with numeric members.
for (const name of ['TA_TUNABLES', 'MW_TUNABLES']) {
  const t = S[name];
  if (!t || typeof t !== 'object') fail(`${name} is not defined as an object`);
}
const ta = S.TA_TUNABLES;
for (const k of ['poolByScore', 'poolByPpm', 'poolByCheapest', 'maxIterations', 'maxResults', 'transferPenalty']) {
  if (typeof ta[k] !== 'number') fail(`TA_TUNABLES.${k} missing or non-numeric`);
}
if (typeof S.MW_TUNABLES.budgetBuilderOptionMultiplier !== 'number') {
  fail('MW_TUNABLES.budgetBuilderOptionMultiplier missing or non-numeric');
}
if ('budgetGainWeight' in S.MW_TUNABLES) {
  fail('legacy cumulative MW_TUNABLES.budgetGainWeight is still present');
}

if (/const freeTransfersNext = \(activeChip ===/.test(src)) {
  fail('multi-week planner still references out-of-scope activeChip');
}

// Transfer Advisor may use the current team as a points baseline, but an
// excluded current pick must make "Keep Current Team" ineligible.
try {
  const excludedDrivers = new Set(['NOR']);
  const excludedConstructors = new Set(['mclaren']);
  if (!S.teamContainsExcludedPick(['NOR', 'LEC'], ['ferrari'], excludedDrivers, new Set())) {
    fail('Transfer Advisor did not detect an excluded current driver');
  }
  if (!S.teamContainsExcludedPick(['LEC'], ['mclaren'], new Set(), excludedConstructors)) {
    fail('Transfer Advisor did not detect an excluded current constructor');
  }
  if (S.teamContainsExcludedPick(['LEC'], ['ferrari'], excludedDrivers, excludedConstructors)) {
    fail('Transfer Advisor rejected a current team with no excluded picks');
  }
  if (!/if \(l\.transfersNeeded === 0\) return currentTeamIsEligible;/.test(src)
      || !/if \(currentTeamIsEligible && keepCurrentResult/.test(src)) {
    fail('Transfer Advisor can still display an excluded hold baseline');
  }
} catch (e) {
  fail('Transfer Advisor exclusion regression test threw: ' + e.message);
}
if (!/const freeTransfersNext = \(usedChip === 'wild_card' \|\| usedChip === 'limitless'\)/.test(src)) {
  fail('multi-week planner chip transfer reset is not keyed to usedChip');
}

// 2) Key functions must exist.
for (const [k, label] of [
  ['hasRenderSwapRow', 'renderSwapRow'],
  ['hasRunTransferAdvisor', 'runTransferAdvisor'],
  ['hasPredictPriceChange', 'predictPriceChange'],
  ['hasRenderTransferCard', 'renderTransferCard'],
  ['hasRunTeamCompare', 'runTeamCompare'],
  ['hasScoreTeamPicks', 'scoreTeamPicks'],
  ['hasFinalFixRacePoints', 'calculateFinalFixRacePoints'],
  ['hasOfficialRoundCoverageCheck', 'officialRoundHasCompleteScores'],
  ['hasBudgetFuturePointValue', 'budgetFuturePointValue'],
  ['hasOpenPitWallTransferAdvisor', 'openPitWallTransferAdvisor'],
  ['hasLoadV13Session', 'loadV13Session'],
  ['hasHandleV13TeamSearch', 'handleV13TeamSearch'],
]) {
  if (!S[k]) fail(`${label} is not defined as a function`);
}

console.log('PASS: app.js loads and core bindings resolve.');
