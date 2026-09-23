/*
 * Shared mocked-browser harness for the site's frontend checks.
 *
 * `node --check` only validates SYNTAX. It does NOT catch undefined references
 * (e.g. a `const` that was referenced but never defined) — that's exactly the
 * bug class that shipped a crashing Transfer Advisor (TA_TUNABLES referenced 6x,
 * defined 0x). The load and behavior checks evaluate the modules before app.js.
 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const APP = path.join(__dirname, '..', 'web', 'public', 'app.js');
const FINAL_FIX = path.join(__dirname, '..', 'web', 'public', 'final-fix.js');
const OPTIMIZER_SCORING = path.join(__dirname, '..', 'web', 'public', 'optimizer-scoring.js');
let src = fs.readFileSync(APP, 'utf8');

// ---- Mock the browser surface app.js touches at load time ----
const noop = () => {};
const windowEventNames = [];
const elStub = new Proxy({}, { get: () => (() => elStub), set: () => true });
const sandbox = {
  console,
  document: {
    getElementById: () => ({
      value: '', addEventListener: noop,
      classList: { add: noop, remove: noop, toggle: noop },
      querySelector: () => null, scrollIntoView: noop, innerHTML: '', prepend: noop,
    }),
    querySelector: () => null, querySelectorAll: () => [],
    addEventListener: noop, createElement: () => elStub, body: elStub,
  },
  localStorage: { getItem: () => null, setItem: noop, removeItem: noop },
  alert: noop, fetch: () => Promise.resolve({ json: () => ({}) }),
  location: { search: '', href: '' }, navigator: { clipboard: { writeText: noop } },
  setTimeout: noop, setInterval: noop, requestAnimationFrame: noop,
};
sandbox.window = sandbox;
sandbox.addEventListener = (name, listener) => { windowEventNames.push(name); };
sandbox.windowEventNames = windowEventNames;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

// Append an exposure block so we can read top-level lexical bindings (const /
// function) the same way the rest of the script's scope sees them.
src += `
;(function(){
  globalThis.__SMOKE = {
    TA_TUNABLES: typeof TA_TUNABLES !== 'undefined' ? TA_TUNABLES : undefined,
    MW_TUNABLES: typeof MW_TUNABLES !== 'undefined' ? MW_TUNABLES : undefined,
    hasRenderSwapRow: typeof renderSwapRow === 'function',
    hasRunTransferAdvisor: typeof runTransferAdvisor === 'function',
    teamContainsExcludedPick: typeof teamContainsExcludedPick === 'function' ? teamContainsExcludedPick : null,
    hasPredictPriceChange: typeof predictPriceChange === 'function',
    predictPriceChange: typeof predictPriceChange === 'function' ? predictPriceChange : null,
    hasRenderTransferCard: typeof renderTransferCard === 'function',
    hasRunTeamCompare: typeof runTeamCompare === 'function',
    hasScoreTeamPicks: typeof scoreTeamPicks === 'function',
    hasFinalFixRacePoints: typeof window.BoxBoxFinalFix?.racePoints === 'function',
    finalFixQualifyingPoints: window.BoxBoxFinalFix?.qualifyingPoints || null,
    finalFixProjectedRacePoints: window.BoxBoxFinalFix?.projectedRacePoints || null,
    gridPenaltyText: typeof gridPenaltyText === 'function' ? gridPenaltyText : null,
    hasOfficialRoundCoverageCheck: typeof officialRoundHasCompleteScores === 'function',
    hasBudgetFuturePointValue: typeof budgetFuturePointValue === 'function',
    basisPointsFor: typeof basisPointsFor === 'function' ? basisPointsFor : null,
    hasOpenPitWallTransferAdvisor: typeof openPitWallTransferAdvisor === 'function',
    hasOpenPitWall: typeof openPitWall === 'function',
    hasOpenTeamCompare: typeof openTeamCompare === 'function',
    hasLoadV13Session: typeof loadV13Session === 'function',
    hasHandleV13TeamSearch: typeof handleV13TeamSearch === 'function',
    budgetFuturePointValue: typeof budgetFuturePointValue === 'function' ? budgetFuturePointValue : null,
    renderSwapRow: typeof renderSwapRow === 'function' ? renderSwapRow : null,
    renderTransferCard: typeof renderTransferCard === 'function' ? renderTransferCard : null,
    scoreTeamPicks: typeof scoreTeamPicks === 'function' ? scoreTeamPicks : null,
    finalFixRacePoints: window.BoxBoxFinalFix?.racePoints || null,
    finalFixCompare: window.BoxBoxFinalFix?.compare || null,
    officialRoundHasCompleteScores: typeof officialRoundHasCompleteScores === 'function' ? officialRoundHasCompleteScores : null,
    normalizeOfficialAssetId: typeof normalizeOfficialAssetId === 'function' ? normalizeOfficialAssetId : null,
    normalizeSavedDriverAssetId: typeof normalizeSavedDriverAssetId === 'function' ? normalizeSavedDriverAssetId : null,
    normalizeCompareSource: typeof normalizeCompareSource === 'function' ? normalizeCompareSource : null,
    normalizeCompareChips: typeof normalizeCompareChips === 'function' ? normalizeCompareChips : null,
    compareSourceStatus: typeof compareSourceStatus === 'function' ? compareSourceStatus : null,
    setupCompareSources: typeof setupCompareSources === 'function' ? setupCompareSources : null,
    getCompareSelection: () => compareTeams.map(team => ({ id: team.id, source: team.source })),
    readCompareMemberApi: typeof readCompareMemberApi === 'function' ? readCompareMemberApi : null,
    getMemberTeamSnapshot: typeof getMemberTeamSnapshot === 'function' ? getMemberTeamSnapshot : null,
    windowEventNames,
    compareTeamBudgetSummary: typeof compareTeamBudgetSummary === 'function' ? compareTeamBudgetSummary : null,
    findDriverAsset: typeof findDriverAsset === 'function' ? findDriverAsset : null,
    setTransferRenderState(basis, nextData, driverIds, constructorIds) {
      optimizeBasis = basis;
      data = nextData;
      myTeamDrivers = driverIds;
      myTeamConstructors = constructorIds;
    },
    setPriceLoaderState(nextData, nextOfficialPoints, nextSeasonSummary = null) {
      data = nextData;
      officialPointsData = nextOfficialPoints;
      seasonSummary = nextSeasonSummary;
    },
    setBudgetValueData(nextBudgetValueData) {
      budgetValueData = nextBudgetValueData;
    },
  };
})();
`;

const fail = (msg) => { console.error('FAIL: ' + msg); process.exit(1); };

try {
  vm.runInContext(fs.readFileSync(FINAL_FIX, 'utf8'), sandbox, { filename: 'final-fix.js' });
  vm.runInContext(fs.readFileSync(OPTIMIZER_SCORING, 'utf8'), sandbox, { filename: 'optimizer-scoring.js' });
  vm.runInContext(src, sandbox, { filename: 'app.js' });
} catch (e) {
  fail('frontend scripts threw at load: ' + e.message);
}

const S = sandbox.__SMOKE;
if (!S) fail('smoke exposure block did not run');

module.exports = { S, src, sandbox, fail, fs, path, noop };
