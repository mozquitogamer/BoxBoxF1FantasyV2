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
    hasPredictPriceChange: typeof predictPriceChange === 'function',
    hasRenderTransferCard: typeof renderTransferCard === 'function',
    hasRunTeamCompare: typeof runTeamCompare === 'function',
    hasScoreTeamPicks: typeof scoreTeamPicks === 'function',
    hasFinalFixRacePoints: typeof calculateFinalFixRacePoints === 'function',
    finalFixQualifyingPoints: typeof ffQualifyingPoints === 'function' ? ffQualifyingPoints : null,
    finalFixProjectedRacePoints: typeof ffProjectedRacePoints === 'function' ? ffProjectedRacePoints : null,
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
    finalFixRacePoints: typeof calculateFinalFixRacePoints === 'function' ? calculateFinalFixRacePoints : null,
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
    setPriceLoaderState(nextData, nextOfficialPoints) {
      data = nextData;
      officialPointsData = nextOfficialPoints;
    },
    setBudgetValueData(nextBudgetValueData) {
      budgetValueData = nextBudgetValueData;
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
if (typeof S.MW_TUNABLES.budgetBuilderOptionMultiplier !== 'number') {
  fail('MW_TUNABLES.budgetBuilderOptionMultiplier missing or non-numeric');
}
if ('budgetGainWeight' in S.MW_TUNABLES) {
  fail('legacy cumulative MW_TUNABLES.budgetGainWeight is still present');
}

if (/const freeTransfersNext = \(activeChip ===/.test(src)) {
  fail('multi-week planner still references out-of-scope activeChip');
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

// The account hub is a separate browser script; keep its visible unified
// sign-out copy covered by the same lightweight frontend smoke check.
const engagement = fs.readFileSync(path.join(__dirname, '..', 'web', 'public', 'engagement.js'), 'utf8');
if (!engagement.includes('Sign out of BoxBox') || !engagement.includes('/api/members/sign-out/')) {
  fail('access hub is missing the visible unified sign-out action');
}

// 3) Calibrated budget value observes timing and forecast reliability.
try {
  S.setTransferRenderState('projected', {
    round: 14,
    driver_assets: { override_active: true },
    drivers: [
      { driver_id: 'LAW_RED_BULL', name: 'Liam Lawson', constructor: 'red_bull', current_price: 14.5, expected_points: 20, projected_points: 22 },
      { driver_id: 'TSU_RACING_BULLS', name: 'Yuki Tsunoda', constructor: 'racing_bulls', current_price: 10.3, expected_points: 12, projected_points: 14 },
      { driver_id: 'NOR', name: 'Lando Norris' },
    ],
    constructors: [{ constructor_id: 'red_bull', name: 'Red Bull' }],
  }, [], []);
  const officialCases = [
    [{ asset_type: 'driver', asset_id: '11032', name: 'Isack Hadjar' }, 'HAD'],
    [{ asset_type: 'driver', asset_id: '116', name: 'Liam Lawson' }, 'LAW_RED_BULL'],
    [{ asset_type: 'driver', asset_id: '114', name: 'Liam Lawson' }, 'LAW'],
    [{ asset_type: 'driver', asset_id: '130', name: 'Yuki Tsunoda' }, 'TSU_RACING_BULLS'],
    [{ asset_type: 'driver', asset_id: '117', name: 'Lando Norris' }, 'NOR'],
    [{ asset_type: 'constructor', asset_id: '29', name: 'Red Bull Racing' }, 'red_bull'],
  ];
  for (const [asset, expected] of officialCases) {
    const actual = S.normalizeOfficialAssetId(asset);
    if (actual !== expected) fail(`official sync mapped ${asset.name}/${asset.asset_id} to ${actual}, expected ${expected}`);
  }
  if (S.normalizeSavedDriverAssetId('HAD') !== 'HAD' || S.normalizeSavedDriverAssetId('LAW') !== 'LAW') {
    fail('saved legacy ownership IDs were rewritten');
  }
  const hadjar = S.findDriverAsset('HAD');
  const oldLawson = S.findDriverAsset('LAW');
  if (!hadjar?.held_only || hadjar.name !== 'Isack Hadjar' || hadjar.expected_points !== 0) {
    fail('held Hadjar asset was not preserved as a non-purchasable zero-projection holding');
  }
  if (!oldLawson?.held_only || oldLawson.name !== 'Liam Lawson' || oldLawson.expected_points !== 0) {
    fail('held original Lawson asset was not preserved as a non-purchasable zero-projection holding');
  }
  if (S.findDriverAsset('NOT_OWNED') !== null) fail('unknown driver was synthesized as a held asset');
} catch (e) {
  fail('Round 14 official asset normalization threw: ' + e.message);
}

// 4) Calibrated budget value observes timing and forecast reliability.
try {
  S.setBudgetValueData({
    current_races_remaining: 11,
    curve: {
      ceiling_points_per_million: 8.567,
      tau_races: 1.8,
      points_per_million: { '0': 0, '10': 8.53, '11': 8.55 },
      points_per_million_p25: { '0': 0, '10': 8.04, '11': 8.04 },
      points_per_million_p75: { '0': 0, '10': 8.98, '11': 9.05 },
    },
    calibration: {
      decision_grade_multiplier: 0.625,
      forecast_realization_discount: 0.867,
      forecast_signed_realization_discount: 0.771,
    },
  });
  const forecastValue = S.budgetFuturePointValue(0.3, { racesLeft: 11, status: 'forecast' });
  const securedValue = S.budgetFuturePointValue(0.3, { racesLeft: 11, status: 'secured' });
  const lastRaceForecast = S.budgetFuturePointValue(0.3, { racesLeft: 1, status: 'forecast' });
  if (Math.abs(forecastValue - 1.386) > 0.01) fail(`forecast budget value mismatch: ${forecastValue}`);
  if (Math.abs(securedValue - 1.603) > 0.01) fail(`secured budget value mismatch: ${securedValue}`);
  if (lastRaceForecast !== 0) fail(`last-race forecast should be worthless: ${lastRaceForecast}`);
} catch (e) {
  fail('budgetFuturePointValue threw: ' + e.message);
}

// 4b) Team Compare sources keep saved-team financial state separate from the
// manual budget and expose an incomplete roster without inventing picks.
try {
  const saved = S.normalizeCompareSource({
    slot: 2, name: 'Race Day', drivers: ['A', 'B'], constructors: ['C'],
    bank_millions: 4.2, squad_value_millions: 95.8,
    chips_remaining: { limitless: true, '3x_boost': false },
  }, 1, 'saved');
  if (!saved || saved.source !== 'saved' || saved.drivers.filter(Boolean).length !== 2 || saved.constructors.filter(Boolean).length !== 1) {
    fail('saved compare source did not preserve incomplete roster');
  }
  if (saved.spendingPower !== 100 || saved.bank !== 4.2 || saved.chips.length !== 1) {
    fail(`saved compare source did not preserve bank/spending power/chips: ${JSON.stringify(saved)}`);
  }
} catch (e) {
  fail('Team Compare source normalization threw: ' + e.message);
}

// 4c) Pit Wall store/events, finance separation, entitlement state, and the
// exact chip ledger contract remain safe at the Team Compare boundary.
try {
  for (const eventName of ['boxbox:pitwall-loaded', 'boxbox:pitwall-saved', 'boxbox:pitwall-selected']) {
    if (!S.windowEventNames.includes(eventName)) fail(`Team Compare did not subscribe to ${eventName}`);
  }
  const storeState = {
    authenticated: true,
    entitlement: { active: true },
    selectedSlot: 2,
    teams: [
      { slot: 1, name: 'T1', assets: [], budget_millions: 120, squad_value_millions: 98, bank_millions: null, chips: [] },
        { slot: 2, name: 'T2', assets: [], budget_millions: 115, squad_value_millions: 94, bank_millions: 21, chips: [
        { chip_code: 'limitless', season: 2025, status: 'available' },
        { chip_code: 'limitless', season: 2026, status: 'used' },
        { chip_code: '3x_boost', status: 'used' },
        { chip_code: 'autopilot', season: 2026, status: 'available' },
        { chip_code: 'final_fix', status: 'pending' },
        { chip_code: 'unknown', status: 'available' },
      ] },
      { slot: 3, name: 'T3', assets: [], budget_millions: 110, chips: { wild_card: { status: 'available' }, no_negative: { status: 'used' }, autopilot: true, final_fix: false } },
    ],
  };
  sandbox.BoxBoxTeamState = { getStore: () => ({ getState: () => storeState }) };
  const readState = S.readCompareMemberApi();
  if (readState !== storeState) fail('Team Compare did not read the shared BoxBoxTeamState store');
  const finance = S.normalizeCompareSource(storeState.teams[0], 0, 'saved');
  if (finance.bank !== null || finance.spendingPower !== 120) fail('legacy budget was incorrectly treated as bank');
  const chips = S.normalizeCompareChips(storeState.teams[1].chips);
  if (chips.length !== 1 || chips[0] !== 'autopilot') fail(`chip array normalization mismatch: ${JSON.stringify(chips)}`);
  const objectChips = S.normalizeCompareChips(storeState.teams[2].chips);
  if (objectChips.length !== 2 || !objectChips.includes('wild_card') || !objectChips.includes('autopilot')) fail(`chip object normalization mismatch: ${JSON.stringify(objectChips)}`);
  if (S.compareSourceStatus({ authenticated: true, entitlement: { active: false } }) !== 'inactive') fail('inactive entitlement defaulted to active');
  if (S.compareSourceStatus({ authenticated: false, entitlement: { active: false } }) !== 'signed-out') fail('signed-out state was incorrectly treated as inactive');
  S.setupCompareSources(storeState);
  const selection = S.getCompareSelection();
  if (selection.length !== 2 || selection.some(item => item.source !== 'saved')) fail(`saved source default selection mismatch: ${JSON.stringify(selection)}`);
  const sources = sandbox.BoxBoxTeamCompare?.getSources?.() || [];
  if (sources.length !== 4) fail(`expected three saved sources plus manual source, got ${sources.length}`);
  if ((sandbox.BoxBoxTeamCompare?.selectSources?.(sources.map(source => source.id)) || []).length !== 4) fail('compare source selection did not allow all three saved teams plus manual');
  S.setTransferRenderState('projected', {
    drivers: ['A', 'B', 'C', 'D', 'E'].map((id, index) => ({ driver_id: id, name: id, current_price: 10 + index })),
    constructors: [{ constructor_id: 'X', name: 'X', current_price: 12 }, { constructor_id: 'Y', name: 'Y', current_price: 13 }],
  }, ['A', 'B', 'C', 'D', 'E'], ['X', 'Y']);
  sandbox.document.getElementById = id => ({ value: id === 'transferBudget' ? '100' : id === 'transferBank' ? '5' : id === 'freeTransfers' ? '2' : '', addEventListener: noop });
  const snapshot = S.getMemberTeamSnapshot();
  if (snapshot.squad_value_millions !== 85 || snapshot.bank_millions !== 5 || snapshot.spending_power_millions !== 100 || snapshot.budget_millions !== 100) {
    fail(`member financial snapshot mismatch: ${JSON.stringify(snapshot)}`);
  }
} catch (e) {
  fail('Pit Wall Team Compare integration regression test threw: ' + e.message);
}

// 4d) Static shell contracts: the workspace/menu are present and Beat V13
// has exactly one actual email registration form.
try {
  const index = fs.readFileSync(path.join(__dirname, '..', 'web', 'public', 'index.html'), 'utf8');
  if (!index.includes('id="mode-pitwall"') || !index.includes('id="pitWallMemberPanel"')) fail('Pit Wall workspace shell is missing');
  if ((index.match(/id="pitWallMemberPanel"/g) || []).length !== 1) fail('Pit Wall member panel is duplicated');
  if (!index.includes('id="tabMoreMenu"') || !index.includes('data-tab="season"')) fail('More navigation menu is missing deep links');
  if ((index.match(/class="email-updates-form"/g) || []).length !== 1) fail('Beat V13 registration form is not unique');
  if (index.includes('id="optimizerRegistrationEmail"') || index.includes('id="emailUpdatesForm"')) fail('obsolete registration form remains');
  if (!/styles\.css\?v=\d+/.test(index) || !/engagement\.css\?v=\d+/.test(index) || !/team-state\.js\?v=\d+/.test(index) || !/app\.js\?v=\d+/.test(index) || !/members\.js\?v=\d+/.test(index) || !/engagement\.js\?v=\d+/.test(index)) fail('changed static asset cache versions are missing');
  if (!/team-state\.js\?v=\d+[\s\S]*app\.js\?v=\d+[\s\S]*members\.js\?v=\d+/.test(index)) fail('team-state must load before app and members');
  const members = fs.readFileSync(path.join(__dirname, '..', 'web', 'public', 'members.js'), 'utf8');
  if (!members.includes('data-team-chip') || !members.includes('value="available"') || !members.includes('value="used"')) fail('Pit Wall chip status controls are missing explicit states');
  const engagement = fs.readFileSync(path.join(__dirname, '..', 'web', 'public', 'engagement.js'), 'utf8');
  if (!engagement.includes('Pit Wall membership does not enter Beat V13') || !engagement.includes('Register / confirm Beat V13') || !engagement.includes('Open dashboard & link team')) fail('Pit Wall/Beat V13 separation guidance is missing');
  if (!members.includes('BoxBoxFocusPasswordSetup') || !members.includes('pitWallNewPassword')) fail('recovery password setup focus hook is missing');
  if (!src.includes("memberQuery === 'password'") || !src.includes('openPitWall({ scroll: false, updateHistory: false })')) fail('recovery deep link does not open the Pit Wall password workspace');
  const styles = fs.readFileSync(path.join(__dirname, '..', 'web', 'public', 'styles.css'), 'utf8');
  if (!styles.includes('overflow-x: clip') || !styles.includes('.optimizer-mode-toggle') || !styles.includes('max-width: 100%')) fail('mobile overflow containment contract is missing');
  if (!S.hasOpenPitWall || !S.hasOpenTeamCompare || !sandbox.BoxBoxTeamCompare?.open) fail('Pit Wall/Compare open APIs are missing');
} catch (e) {
  fail('frontend shell contract regression test threw: ' + e.message);
}

// 4) renderSwapRow actually runs and produces the swap-delta markup.
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

// 4b) Current-round manual upgrade overlays must flow into optimizer bases,
// while assets without an overlay retain their historical basis values.
try {
  const upgraded = {
    expected_points: 10,
    expected_points_adjusted: 12,
    projected_points: 20,
    points_delta: 2,
  };
  if (S.basisPointsFor(upgraded, 'risk_adjusted') !== 12) {
    fail('risk-adjusted basis ignored expected_points_adjusted');
  }
  if (S.basisPointsFor(upgraded, 'projected') !== 22) {
    fail('projected basis ignored deterministic points_delta');
  }
  if (S.basisPointsFor(upgraded, 'balanced') !== 17) {
    fail('balanced basis did not average adjusted projected/risk points');
  }

  const baseline = { expected_points: 10, projected_points: 20 };
  if (S.basisPointsFor(baseline, 'risk_adjusted') !== 10
      || S.basisPointsFor(baseline, 'projected') !== 20
      || S.basisPointsFor(baseline, 'balanced') !== 15) {
    fail('assets without upgrade overlays changed optimizer basis behavior');
  }

  const deltaOnly = { expected_points: 10, projected_points: 20, points_delta: 2 };
  if (S.basisPointsFor(deltaOnly, 'risk_adjusted') !== 12
      || S.basisPointsFor(deltaOnly, 'projected') !== 22) {
    fail('points_delta fallback was not applied consistently');
  }
} catch (e) {
  fail('upgrade overlay points-basis regression test threw: ' + e.message);
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

// 6) Final Fix race math counts finish, net positions, overtakes and bonuses.
try {
  const hamilton = S.finalFixRacePoints({
    gridPosition: 5,
    finishPosition: 3,
    overtakes: 2,
    fastestLap: true,
    dotd: true,
  });
  if (hamilton.finishPoints !== 15 || hamilton.positionsGainedLost !== 2 || hamilton.total !== 39) {
    fail(`Final Fix Hamilton scenario mismatch: ${JSON.stringify(hamilton)}`);
  }
  const antonelliBankedQuali = S.finalFixQualifyingPoints(4);
  if (antonelliBankedQuali !== 7 || antonelliBankedQuali + hamilton.total !== 46) {
    fail('Final Fix did not retain Antonelli Q4 points while using Hamilton race points');
  }
  const projectedOnly = S.finalFixProjectedRacePoints({
    predicted_quali: 4,
    projected_points: 17.9,
    projected_points_quali: 7,
    projected_points_race: 10.9,
    expected_points: 999,
    expected_points_race: 888,
    mc_race_pts_mean: 777,
  });
  if (projectedOnly !== 10.9) {
    fail(`Final Fix used a non-projected points basis: ${projectedOnly}`);
  }
  const dnf = S.finalFixRacePoints({
    gridPosition: 7,
    finishPosition: 22,
    overtakes: 3,
    fastestLap: true,
    dotd: true,
    isDnf: true,
  });
  if (dnf.total !== -17 || dnf.fastestLapPoints !== 0 || dnf.dotdPoints !== 0) {
    fail(`Final Fix DNF scenario mismatch: ${JSON.stringify(dnf)}`);
  }
} catch (e) {
  fail('Final Fix scoring helper threw: ' + e.message);
}

// 7) Known grid penalties remain distinct from qualifying results.
try {
  if (S.gridPenaltyText({ grid_back_of_grid: true }) !== 'Back-of-grid penalty') {
    fail('back-of-grid penalty label missing');
  }
  if (S.gridPenaltyText({ grid_penalty_places: 10 }) !== '10-place grid penalty') {
    fail('place-drop penalty label missing');
  }
  if (S.gridPenaltyText({}) !== '') fail('unpenalized driver received a penalty label');
} catch (e) {
  fail('grid penalty label helper threw: ' + e.message);
}

// 8) Landing-page price history skips full actual files only when official
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
