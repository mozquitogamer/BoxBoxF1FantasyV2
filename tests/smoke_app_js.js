/*
 * Smoke test for web/public/app.js.
 *
 * `node --check` only validates SYNTAX. It does NOT catch undefined references
 * (e.g. a `const` that was referenced but never defined) — that's exactly the
 * bug class that shipped a crashing Transfer Advisor (TA_TUNABLES referenced 6x,
 * defined 0x). This test actually EVALUATES app.js in a mocked-browser sandbox
 * and resolves the key top-level bindings + calls a couple of pure render
 * functions, so an undefined reference throws here instead of in a user's
 * browser.
 *
 * Run:  node tests/smoke_app_js.js
 * Exit: 0 = pass, non-zero = fail (CI-friendly).
 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const APP = path.join(__dirname, '..', 'web', 'public', 'app.js');
let src = fs.readFileSync(APP, 'utf8');

// ---- Mock the browser surface app.js touches at load time ----
const noop = () => {};
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
    hasPredictPriceChange: typeof predictPriceChange === 'function',
    hasRenderTransferCard: typeof renderTransferCard === 'function',
    hasRunTeamCompare: typeof runTeamCompare === 'function',
    hasScoreTeamPicks: typeof scoreTeamPicks === 'function',
    hasOfficialRoundCoverageCheck: typeof officialRoundHasCompleteScores === 'function',
    renderSwapRow: typeof renderSwapRow === 'function' ? renderSwapRow : null,
    renderTransferCard: typeof renderTransferCard === 'function' ? renderTransferCard : null,
    scoreTeamPicks: typeof scoreTeamPicks === 'function' ? scoreTeamPicks : null,
    officialRoundHasCompleteScores: typeof officialRoundHasCompleteScores === 'function' ? officialRoundHasCompleteScores : null,
    setTransferRenderState(basis, nextData, driverIds, constructorIds) {
      optimizeBasis = basis;
      data = nextData;
      myTeamDrivers = driverIds;
      myTeamConstructors = constructorIds;
    },
    setPriceLoaderState(nextData, nextOfficialPoints) {
      data = nextData;
      officialPointsData = nextOfficialPoints;
    },
  };
})();
`;

const fail = (msg) => { console.error('FAIL: ' + msg); process.exit(1); };

try {
  vm.runInContext(src, sandbox, { filename: 'app.js' });
} catch (e) {
  fail('app.js threw at load: ' + e.message);
}

const S = sandbox.__SMOKE;
if (!S) fail('smoke exposure block did not run');

// 1) Tunable blocks must be defined objects with numeric members.
for (const name of ['TA_TUNABLES', 'MW_TUNABLES']) {
  const t = S[name];
  if (!t || typeof t !== 'object') fail(`${name} is not defined as an object`);
}
const ta = S.TA_TUNABLES;
for (const k of ['poolByScore', 'poolByPpm', 'poolByCheapest', 'maxIterations', 'maxResults', 'transferPenalty']) {
  if (typeof ta[k] !== 'number') fail(`TA_TUNABLES.${k} missing or non-numeric`);
}

// 2) Key functions must exist.
for (const [k, label] of [
  ['hasRenderSwapRow', 'renderSwapRow'],
  ['hasRunTransferAdvisor', 'runTransferAdvisor'],
  ['hasPredictPriceChange', 'predictPriceChange'],
  ['hasRenderTransferCard', 'renderTransferCard'],
  ['hasRunTeamCompare', 'runTeamCompare'],
  ['hasScoreTeamPicks', 'scoreTeamPicks'],
  ['hasOfficialRoundCoverageCheck', 'officialRoundHasCompleteScores'],
]) {
  if (!S[k]) fail(`${label} is not defined as a function`);
}

// 3) renderSwapRow actually runs and produces the swap-delta markup.
try {
  const out = S.renderSwapRow(
    { name: 'Max Verstappen', driver_id: 'max_verstappen', expected_points: 20, current_price: 28 },
    { name: 'Lando Norris', driver_id: 'norris', expected_points: 24, current_price: 26 },
    'driver');
  if (typeof out !== 'string' || !out.includes('transfer-swap')) fail('renderSwapRow returned bad markup');
  if (!out.includes('pts') || !out.includes('M')) fail('renderSwapRow missing swap-delta (pts / M) markup');
} catch (e) {
  fail('renderSwapRow threw: ' + e.message);
}

// 4) Transfer Advisor display values must follow its selected points basis.
// Deliberately give each asset very different deterministic and MC values so
// accidentally rendering expected_points (the historical bug) is unambiguous.
try {
  const out = {
    name: 'Outgoing Driver', driver_id: 'OUT', constructor: 'AAA',
    expected_points: 20, projected_points: 30, current_price: 10,
  };
  const incoming = {
    name: 'Incoming Driver', driver_id: 'IN', constructor: 'BBB',
    expected_points: 24, projected_points: 40, current_price: 11,
  };

  // Explicit render basis must win over a later global change (the same drift
  // that can happen when Load More runs after another optimizer tool).
  S.setTransferRenderState('risk_adjusted', { drivers: [out, incoming], constructors: [] }, ['OUT'], []);
  const projectedSwap = S.renderSwapRow(out, incoming, 'driver', 'projected');
  if (!projectedSwap.includes('30.0 pts') || !projectedSwap.includes('40.0 pts') || !projectedSwap.includes('+10.0pts')) {
    fail('Transfer Advisor projected-mode swap row did not display projected points/delta');
  }

  S.setTransferRenderState('projected', { drivers: [out, incoming], constructors: [] }, ['OUT'], []);
  const riskSwap = S.renderSwapRow(out, incoming, 'driver', 'risk_adjusted');
  if (!riskSwap.includes('20.0 pts') || !riskSwap.includes('24.0 pts') || !riskSwap.includes('+4.0pts')) {
    fail('Transfer Advisor risk-adjusted swap row changed basis unexpectedly');
  }

  S.setTransferRenderState('risk_adjusted', { drivers: [out, incoming], constructors: [] }, ['OUT'], []);
  const balancedSwap = S.renderSwapRow(out, incoming, 'driver', 'balanced');
  if (!balancedSwap.includes('25.0 pts') || !balancedSwap.includes('32.0 pts') || !balancedSwap.includes('+7.0pts')) {
    fail('Transfer Advisor balanced swap row changed basis unexpectedly');
  }

  const constructor = {
    name: 'Constructor One', constructor_id: 'CON', driver_1: 'One', driver_2: 'Two',
    expected_points: 25, projected_points: 40, current_price: 15,
  };
  const lineup = {
    drivers: [out], constructors: [constructor], netPoints: 100, totalPoints: 100,
    totalCost: 25, transfersNeeded: 0, penalty: 0, boostedDriverId: 'OUT',
    secondBoostedDriverId: null, _isKeepCurrent: true, pointsBasis: 'projected',
  };

  // The lineup snapshot must also win over the now-risk-adjusted global basis.
  S.setTransferRenderState('risk_adjusted', { drivers: [out], constructors: [constructor] }, ['OUT'], ['CON']);
  const projectedCard = S.renderTransferCard(lineup, 0, 'none');
  if (!projectedCard.includes('<div class="pick-h-pts">60.0') || !projectedCard.includes('<div class="pick-h-pts">40.0')) {
    fail('Transfer Advisor projected-mode lineup card did not display projected pick points');
  }

  S.setTransferRenderState('projected', { drivers: [out], constructors: [constructor] }, ['OUT'], ['CON']);
  const riskCard = S.renderTransferCard({ ...lineup, pointsBasis: 'risk_adjusted' }, 0, 'none');
  if (!riskCard.includes('<div class="pick-h-pts">40.0') || !riskCard.includes('<div class="pick-h-pts">25.0')) {
    fail('Transfer Advisor risk-adjusted lineup card changed basis unexpectedly');
  }

  S.setTransferRenderState('risk_adjusted', { drivers: [out], constructors: [constructor] }, ['OUT'], ['CON']);
  const balancedCard = S.renderTransferCard({ ...lineup, pointsBasis: 'balanced' }, 0, 'none');
  if (!balancedCard.includes('<div class="pick-h-pts">50.0') || !balancedCard.includes('<div class="pick-h-pts">32.5')) {
    fail('Transfer Advisor balanced lineup card changed basis unexpectedly');
  }
} catch (e) {
  fail('Transfer Advisor points-basis display regression test threw: ' + e.message);
}

// 5) Team Compare scoring helper includes normal 2x / 3x boost and CI totals.
try {
  const drivers = [
    { driver_id: 'A', expected_points: 20, projected_points: 20, mc_total_p5: 5, mc_total_p95: 40 },
    { driver_id: 'B', expected_points: 10, projected_points: 10, mc_total_p5: 0, mc_total_p95: 20 },
  ];
  const cons = [{ constructor_id: 'C', expected_points: 15, projected_points: 15, mc_total_p5: 2, mc_total_p95: 25 }];
  const normal = S.scoreTeamPicks(drivers, cons, 'none');
  const triple = S.scoreTeamPicks(drivers, cons, '3x_boost');
  if (normal.boostedDriverId !== 'A') fail('scoreTeamPicks picked the wrong boost target');
  if (normal.expected !== 65) fail(`scoreTeamPicks normal total mismatch: ${normal.expected}`);
  if (triple.expected !== 95 || triple.secondBoostedDriverId !== 'B') fail('scoreTeamPicks 3x total/secondary mismatch');
  if (normal.floor !== 12 || normal.ceiling !== 125) fail('scoreTeamPicks CI totals mismatch');
} catch (e) {
  fail('scoreTeamPicks threw: ' + e.message);
}

// 6) Landing-page price history skips full actual files only when official
// scores cover every current driver and constructor.
try {
  const current = {
    drivers: [{ driver_id: 'A' }, { driver_id: 'B' }],
    constructors: [{ constructor_id: 'C' }],
  };
  S.setPriceLoaderState(current, {
    rounds: { '1': { drivers: { A: 10, B: 0 }, constructors: { C: 20 } } },
  });
  if (!S.officialRoundHasCompleteScores(1)) fail('complete official round was treated as incomplete');

  S.setPriceLoaderState(current, {
    rounds: { '1': { drivers: { A: 10 }, constructors: { C: 20 } } },
  });
  if (S.officialRoundHasCompleteScores(1)) fail('incomplete official round skipped its actual-data fallback');
} catch (e) {
  fail('official score coverage check threw: ' + e.message);
}

console.log('PASS: app.js loads; optimizer helpers, Team Compare scoring, and price-history fallback checks resolve.');
process.exit(0);
