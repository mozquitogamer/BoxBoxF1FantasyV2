/* ============================================================
   BoxBoxF1Fantasy — App Logic
   ============================================================ */

// -- Team metadata --
const TEAMS = {
    red_bull:       { name: 'Red Bull',       color: '#3671C6', flag: '' },
    ferrari:        { name: 'Ferrari',        color: '#E80020', flag: '' },
    mercedes:       { name: 'Mercedes',       color: '#27F4D2', flag: '' },
    mclaren:        { name: 'McLaren',        color: '#FF8000', flag: '' },
    aston_martin:   { name: 'Aston Martin',   color: '#229971', flag: '' },
    alpine:         { name: 'Alpine',         color: '#FF87BC', flag: '' },
    williams:       { name: 'Williams',       color: '#64C4FF', flag: '' },
    racing_bulls:   { name: 'Racing Bulls',   color: '#6692FF', flag: '' },
    audi:           { name: 'Audi',            color: '#00E701', flag: '' },
    haas:           { name: 'Haas',           color: '#B6BABD', flag: '' },
    cadillac:       { name: 'Cadillac',       color: '#FFD700', flag: '' },
};

const RACE_FLAGS = {
    'Australian Grand Prix': '🇦🇺',
    'Chinese Grand Prix': '🇨🇳',
    'Japanese Grand Prix': '🇯🇵',
    'Bahrain Grand Prix': '🇧🇭',
    'Saudi Arabian Grand Prix': '🇸🇦',
    'Miami Grand Prix': '🇺🇸',
    'Emilia Romagna Grand Prix': '🇮🇹',
    'Monaco Grand Prix': '🇲🇨',
    'Spanish Grand Prix': '🇪🇸',
    'Canadian Grand Prix': '🇨🇦',
    'Austrian Grand Prix': '🇦🇹',
    'British Grand Prix': '🇬🇧',
    'Belgian Grand Prix': '🇧🇪',
    'Hungarian Grand Prix': '🇭🇺',
    'Dutch Grand Prix': '🇳🇱',
    'Italian Grand Prix': '🇮🇹',
    'Azerbaijan Grand Prix': '🇦🇿',
    'Singapore Grand Prix': '🇸🇬',
    'United States Grand Prix': '🇺🇸',
    'Mexico City Grand Prix': '🇲🇽',
    'Brazilian Grand Prix': '🇧🇷',
    'Las Vegas Grand Prix': '🇺🇸',
    'Qatar Grand Prix': '🇶🇦',
    'Abu Dhabi Grand Prix': '🇦🇪',
};

// -- 2026 F1 Fantasy Lock Deadlines (UTC) --
// Lock deadline = start of QUALIFYING on normal weekends, or the start of the
// SPRINT RACE on sprint weekends (standard F1 Fantasy sprint rule — the lock is
// the sprint race, not sprint qualifying). Sprint rounds: 2, 6, 7, 11, 14, 18.
const LOCK_DEADLINES = [
    { round: 1,  race: 'Australian Grand Prix',      lock: '2026-03-07T05:00:00Z', sprint: false },
    { round: 2,  race: 'Chinese Grand Prix',          lock: '2026-03-13T07:30:00Z', sprint: true  },
    { round: 3,  race: 'Japanese Grand Prix',          lock: '2026-03-28T06:00:00Z', sprint: false },
    { round: 4,  race: 'Bahrain Grand Prix',           lock: '2026-04-11T15:00:00Z', sprint: false, cancelled: true },
    { round: 5,  race: 'Saudi Arabian Grand Prix',     lock: '2026-04-18T17:00:00Z', sprint: false, cancelled: true },
    { round: 6,  race: 'Miami Grand Prix',             lock: '2026-05-01T21:30:00Z', sprint: true  },
    { round: 7,  race: 'Canadian Grand Prix',          lock: '2026-05-23T16:00:00Z', sprint: true  },
    { round: 8,  race: 'Monaco Grand Prix',            lock: '2026-06-06T14:00:00Z', sprint: false },
    { round: 9,  race: 'Spanish Grand Prix',           lock: '2026-06-13T13:00:00Z', sprint: false },
    { round: 10, race: 'Austrian Grand Prix',          lock: '2026-06-26T14:30:00Z', sprint: false },
    { round: 11, race: 'British Grand Prix',           lock: '2026-07-04T11:00:00Z', sprint: true  },  // sprint race start (13:00 CEST)
    { round: 12, race: 'Belgian Grand Prix',           lock: '2026-07-18T14:00:00Z', sprint: false },
    { round: 13, race: 'Hungarian Grand Prix',         lock: '2026-07-25T14:00:00Z', sprint: false },
    { round: 14, race: 'Dutch Grand Prix',             lock: '2026-08-22T13:00:00Z', sprint: true  },
    { round: 15, race: 'Italian Grand Prix',           lock: '2026-09-05T14:00:00Z', sprint: false },
    { round: 16, race: 'Spanish Grand Prix (Madrid)',   lock: '2026-09-12T14:00:00Z', sprint: false },
    { round: 17, race: 'Azerbaijan Grand Prix',        lock: '2026-09-25T12:00:00Z', sprint: false },
    { round: 18, race: 'Singapore Grand Prix',         lock: '2026-10-10T13:00:00Z', sprint: true  },
    { round: 19, race: 'United States Grand Prix',     lock: '2026-10-23T21:30:00Z', sprint: false },
    { round: 20, race: 'Mexican Grand Prix',           lock: '2026-10-31T20:00:00Z', sprint: false },
    { round: 21, race: 'Brazilian Grand Prix',         lock: '2026-11-06T18:30:00Z', sprint: false },
    { round: 22, race: 'Las Vegas Grand Prix',         lock: '2026-11-21T04:00:00Z', sprint: false },
    { round: 23, race: 'Qatar Grand Prix',             lock: '2026-11-27T16:30:00Z', sprint: false },
    { round: 24, race: 'Abu Dhabi Grand Prix',         lock: '2026-12-05T13:00:00Z', sprint: false },
];

// -- State --
let data = null;
let lockedDrivers = new Set();
let lockedConstructors = new Set();
let excludedDrivers = new Set();
let excludedConstructors = new Set();
let fpAnalysis = null;
let seasonSummary = null;
let postRaceCache = {};
let predictionsCache = {};
let actualCache = {};
let officialPointsData = null;   // official F1 Fantasy points per round
let weatherData = null;          // weather forecast for current race weekend
let chartJsPromise = null;        // loaded only when Race Deep Dive needs charts
let tableSortColumn = null;
let tableSortAsc = true;
let allLineups = [];
let lineupsShown = 0;
let lineupSearchTotal = 0;
const LINEUPS_PER_PAGE = 10;
// My Team state (for Transfer Advisor + Multi-Week Planner)
let myTeamDrivers = [null, null, null, null, null];   // 5 driver_id slots
let myTeamConstructors = [null, null];                  // 2 constructor_id slots
let transferBudgetTouched = false;
let mwBudgetTouched = false;
let compareTeams = [
    { name: 'Team A', drivers: [null, null, null, null, null], constructors: [null, null] },
    { name: 'Team B', drivers: [null, null, null, null, null], constructors: [null, null] },
    { name: 'Team C', drivers: [null, null, null, null, null], constructors: [null, null] },
];
// Multi-week planner data
let trackData = null;
let driverHistory = null;
// P9: ML-based projections for future rounds, populated by pipeline/predict_horizon.py.
// When present, projectScoresForRound prefers these over the affinity heuristic.
let horizonProjections = null;
// Target team state (for multi-week planner target mode)
let targetTeamDrivers = [null, null, null, null, null];
let targetTeamConstructors = [null, null];
// Slot picker mode: 'myTeam' or 'targetTeam'
let slotPickerTarget = 'myTeam';
let slotPickerCompareIndex = 0;

// -- F1 Fantasy Price Change Thresholds --
// PPM = cumulative_season_points / current_price
// A-tier: assets priced > $18.5M (smaller price swings)
// B-tier: assets priced <= $18.5M (larger price swings)
const PRICE_TIERS = {
    A_TIER_THRESHOLD: 18.5,
    A_TIER_CHANGES: { great: 0.3, good: 0.1, poor: -0.1, terrible: -0.3 },
    B_TIER_CHANGES: { great: 0.6, good: 0.2, poor: -0.2, terrible: -0.6 },
    FLOOR: 3.0,   // F1 Fantasy minimum asset price ($M); an asset at the floor can't drop further
};
// PPM rating thresholds (rolling avg of last 3 rounds / price)
const PPM_RATINGS = {
    GREAT: 1.2,    // >= 1.2 PPM = Great
    GOOD: 0.9,     // >= 0.9 PPM = Good
    POOR: 0.6,     // >= 0.6 PPM = Poor
    // < 0.6 = Terrible
};

function ensureChartJs() {
    if (window.Chart) return Promise.resolve(true);
    if (chartJsPromise) return chartJsPromise;

    chartJsPromise = new Promise(resolve => {
        const script = document.createElement('script');
        const timeout = window.setTimeout(() => {
            chartJsPromise = null;
            resolve(false);
        }, 8000);
        script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js';
        script.integrity = 'sha384-vsrfeLOOY6KuIYKDlmVH5UiBmgIdB1oEf7p01YgWHuqmOHfZr374+odEv96n9tNC';
        script.crossOrigin = 'anonymous';
        script.async = true;
        script.onload = () => {
            window.clearTimeout(timeout);
            resolve(!!window.Chart);
        };
        script.onerror = () => {
            window.clearTimeout(timeout);
            chartJsPromise = null;
            resolve(false);
        };
        document.head.appendChild(script);
    });
    return chartJsPromise;
}

// -- Transfer Advisor tunables --
// All advisor search constants in one place (mirrors MW_TUNABLES). The driver
// candidate pool is the UNION of three sub-pools so the search sees both
// high-ceiling picks AND cheap budget-enablers (a cheap low-points driver
// freed up to afford a star is invisible to a pure top-by-score pool — the old
// FREE_POOL=15 limitation).
const TA_TUNABLES = {
    poolByScore: 15,       // top-N by strategy score (ceiling picks)
    poolByPpm: 6,          // top-M by points-per-$M (value/enabler picks)
    poolByCheapest: 4,     // K cheapest available (pure budget relief)
    maxIterations: 500000, // branch-and-bound backstop
    maxResults: 200,       // cap on stored lineups before display slice
    transferPenalty: 10,   // F1 Fantasy: -10 pts per transfer beyond free count
};

// -- Optimization points basis --
// The optimizer / transfer advisor / multi-week planner RANK picks on a chosen
// "points basis" rather than always using the raw MC mean (expected_points). The
// MC mean compresses predicted winners (a predicted P1 can only shuffle down) and
// inflates cheap high-variance midfielders (Jensen effect on a floored points
// curve), which distorts SELECTION — e.g. it will suggest selling a predicted
// winner for a lower-projected driver. Each tool sets this from its "Points basis"
// dropdown at the start of a run; result renderers must use that same basis so
// their pick values and swap deltas reconcile with the calculated totals.
//   'projected'     -> deterministic finishing-order total (projected_points; no MC compression)
//   'balanced'      -> mean of projected + risk-adjusted (DEFAULT; best expected-value proxy)
//   'risk_adjusted' -> raw MC mean (expected_points; legacy behavior)
let optimizeBasis = 'balanced';
function basisPointsFor(item, basis = optimizeBasis) {
    const risk = (typeof item.expected_points === 'number') ? item.expected_points : 0;
    const proj = (typeof item.projected_points === 'number') ? item.projected_points : risk;
    if (basis === 'projected') return proj;
    if (basis === 'risk_adjusted') return risk;
    return (proj + risk) / 2; // balanced
}
function basisPoints(item) {
    return basisPointsFor(item, optimizeBasis);
}
function basisValue(item) {
    const price = item.current_price || item.price || 0;
    return price > 0 ? basisPoints(item) / price : 0;
}

// -- Deferred loading state --
const _deferredLoaded = {};

async function ensureLoaded(key, loadFn) {
    if (_deferredLoaded[key]) return;
    _deferredLoaded[key] = true;
    return loadFn();
}

function showTabSpinner(tabId) {
    const panel = document.getElementById(tabId);
    if (!panel) return;
    // Only show spinner if tab has no rendered content yet
    const existing = panel.querySelector('.tab-spinner');
    if (existing) return;
    const hasContent = panel.querySelector('.driver-grid, .constructor-grid, .optimizer-header, .analysis-tabs, .season-standings, .h2h-container, .accuracy-stats, .accuracy-filter, .deep-dive-container, .video-grid, .articles-grid, .about-content');
    if (hasContent) return;
    const spinner = document.createElement('div');
    spinner.className = 'tab-spinner';
    spinner.innerHTML = '<div class="spinner-ring"></div><span>Loading...</span>';
    panel.prepend(spinner);
}

function removeTabSpinner(tabId) {
    const panel = document.getElementById(tabId);
    if (!panel) return;
    const spinner = panel.querySelector('.tab-spinner');
    if (spinner) spinner.remove();
}

// -- Tab-specific data loaders (lazy) --
async function ensureDriversData() {
    // Price forecasts normally need only the compact official-points file. Fetch
    // full per-round actuals strictly as a fallback for missing/incomplete rounds.
    await ensureLoaded('officialPoints', loadOfficialPoints);
    await ensureLoaded('priceScoreFallbacks', preloadPriceScoreFallbackData);
}

async function ensureAnalysisData() {
    await ensureLoaded('officialPoints', loadOfficialPoints);
    await ensureLoaded('actualData', preloadActualData);
    await ensureLoaded('fpAnalysis', loadFPAnalysis);
}

async function ensureWeatherData() {
    await ensureLoaded('weather', loadWeatherData);
}

async function ensureSeasonData() {
    await ensureLoaded('pitstops', loadPitstopData);
}

async function ensureAccuracyData() {
    await ensureLoaded('officialPoints', loadOfficialPoints);
    await ensureLoaded('actualData', preloadActualData);
}

async function ensureDeepDiveData() {
    await ensureLoaded('officialPoints', loadOfficialPoints);
    await ensureLoaded('actualData', preloadActualData);
}

// -- Tab render tracking --
const _tabRendered = {};

// -- Scenario-aware data view --
// When the user has any What-If bumps active, the Lineup Optimizer, Transfer
// Advisor, and Multi-Week Planner should score against the overlaid prediction,
// not the baseline. This helper returns the overlay-applied data when scenarios
// are active, or `data` itself when they aren't. Cheap — applyToAll is O(n) per
// session, and we call it once per optimizer run (not per combination).
function getScenarioView() {
    if (!data) return data;
    if (window.scenarios && !window.scenarios.isEmpty()) {
        return window.scenarios.applyToAll(data);
    }
    return data;
}

// Returns "" or a small banner HTML announcing that the lineup/transfer/planner
// results are based on the user's active scenario, not the baseline ML view.
function scenarioBannerHtml() {
    if (!window.scenarios || window.scenarios.isEmpty()) return '';
    const n = window.scenarios.activeCount();
    return `<div class="scenario-active-banner" title="Lineup scoring includes your What-If bumps. Open the floating Scenario pill (top-right) to manage or reset.">
        \u{2728} Results include your active scenario (<strong>${n}</strong> bump${n === 1 ? '' : 's'})
    </div>`;
}

async function renderTabIfNeeded(tabName) {
    if (_tabRendered[tabName]) return;
    const tabId = `tab-${tabName}`;

    switch (tabName) {
        case 'drivers':
            // Already rendered on init
            break;
        case 'constructors':
            showTabSpinner(tabId);
            await ensureLoaded('pitstops', loadPitstopData);
            renderConstructors();
            removeTabSpinner(tabId);
            _tabRendered.constructors = true;
            break;
        case 'optimizer':
            renderMyTeamGrid();
            renderTargetTeamGrid();
            renderTeamCompareGrid();
            renderLockGrid();
            // Optimizer renders on button click, just mark ready
            _tabRendered.optimizer = true;
            break;
        case 'analysis':
            showTabSpinner(tabId);
            await ensureAnalysisData();
            await ensureSeasonData();
            renderFPAnalysis();
            populatePostRaceSelector();
            removeTabSpinner(tabId);
            _tabRendered.analysis = true;
            break;
        case 'season':
            showTabSpinner(tabId);
            await ensureSeasonData();
            renderSeason();
            removeTabSpinner(tabId);
            _tabRendered.season = true;
            break;
        case 'h2h':
            showTabSpinner(tabId);
            renderH2H();
            removeTabSpinner(tabId);
            _tabRendered.h2h = true;
            break;
        case 'accuracy':
            showTabSpinner(tabId);
            await ensureAccuracyData();
            await renderAccuracy();
            removeTabSpinner(tabId);
            _tabRendered.accuracy = true;
            break;
        case 'deepdive':
            showTabSpinner(tabId);
            await ensureDeepDiveData();
            initDeepDiveTab();
            removeTabSpinner(tabId);
            _tabRendered.deepdive = true;
            break;
        case 'videos':
            showTabSpinner(tabId);
            await ensureLoaded('videos', loadVideos);
            renderVideos();
            removeTabSpinner(tabId);
            _tabRendered.videos = true;
            break;
        case 'articles':
            showTabSpinner(tabId);
            await ensureLoaded('articles', loadArticles);
            renderArticles();
            removeTabSpinner(tabId);
            _tabRendered.articles = true;
            break;
        case 'changelog':
            showTabSpinner(tabId);
            await ensureLoaded('changelog', loadChangelog);
            renderChangelog();
            removeTabSpinner(tabId);
            _tabRendered.changelog = true;
            break;
        case 'about':
            _tabRendered.about = true;
            break;
    }
}

let changelogData = null;
async function loadChangelog() {
    try {
        const resp = await fetch(cacheBust('data/changelog.json'));
        if (resp.ok) changelogData = await resp.json();
    } catch(e) { changelogData = null; }
}

function renderChangelog() {
    const el = document.getElementById('changelogContent');
    if (!el) return;
    if (!changelogData || !changelogData.entries) {
        el.innerHTML = '<p class="no-data">Changelog unavailable.</p>';
        return;
    }
    // Sort newest first by date (ISO strings sort lexicographically)
    const entries = [...changelogData.entries].sort((a, b) => (b.date || '').localeCompare(a.date || ''));
    el.innerHTML = entries.map(e => {
        const tags = (e.tags || []).map(t =>
            `<span class="changelog-tag ${t}">${t}</span>`
        ).join('');
        const body = (e.body || []).map(p => `<p>${p}</p>`).join('');
        return `
            <article class="changelog-entry">
                <div class="changelog-entry-header">
                    <h3 class="changelog-entry-title">${e.title}</h3>
                    <span class="changelog-entry-date">${e.date}</span>
                </div>
                ${tags ? `<div class="changelog-tag-row">${tags}</div>` : ''}
                <div class="changelog-entry-body">${body}</div>
            </article>
        `;
    }).join('');
}

// -- Init --
document.addEventListener('DOMContentLoaded', async () => {
    // Phase 1: Fetch the compact home-page inputs in parallel. Official score
    // history and weather are ready before the first live render, allowing the
    // crawlable HTML snapshot to be replaced without an intermediate layout.
    await Promise.all([
        loadData(),
        loadSeasonData(),
        ensureLoaded('officialPoints', loadOfficialPoints),
        ensureLoaded('weather', loadWeatherData),
    ]);

    // User-scenarios overlay: load LocalStorage state (per round, auto-cleared
    // when the round changes). When the user dials a slider, we re-render the
    // affected views.
    if (window.scenarios && data) {
        window.scenarios.init(data);
        window.scenarios.onChange(() => {
            renderDrivers();
            if (_tabRendered.constructors) renderConstructors();
            renderScenarioPill();
        });
        // Allow ?scenario=... share links
        try {
            const params = new URLSearchParams(location.search);
            const s = params.get('scenario');
            if (s) window.scenarios.loadFromShareString(s);
        } catch(e) {}
        injectScenarioPill();
        renderScenarioPill();
    }

    startCountdown();
    setupTabs();
    setupControls();

    // Phase 2: Render Drivers tab immediately
    renderHero();
    renderWeather();
    renderDrivers();
    document.getElementById('driverLiveRegion')?.classList.remove('is-hydrating');

    // Deep links: ?team= pre-fills the Transfer Advisor; ?driver= / ?constructor=
    // jump to and highlight a single prediction card.
    try {
        const qp = new URLSearchParams(location.search);
        const sharedTeam = qp.get('team');
        const sharedDriver = qp.get('driver');
        const sharedConstructor = qp.get('constructor');
        if (sharedTeam) {
            applySharedTeam(sharedTeam);
        } else if (sharedDriver) {
            focusPrediction('driver', sharedDriver);
            history.replaceState(null, '', location.pathname);
        } else if (sharedConstructor) {
            focusPrediction('constructor', sharedConstructor);
            history.replaceState(null, '', location.pathname);
        }
    } catch (e) {}
    _tabRendered.drivers = true;

    // Phase 3: Load full actuals only when an official round is incomplete.
    ensureDriversData().then(fallbackRoundCount => {
        showFallbackBanner();
        if (fallbackRoundCount > 0) renderDrivers();
    });
    // Phase 4: If deep-linked to another tab, render it
    const hash = location.hash.replace('#', '');
    if (hash && hash !== 'drivers') {
        await renderTabIfNeeded(hash);
    }
});

async function preloadActualData() {
    // Full actual results are required by analysis, accuracy, and deep-dive tabs.
    if (!seasonSummary || !seasonSummary.rounds) return;
    const promises = seasonSummary.rounds
        .filter(r => r.has_actual)
        .map(r => loadActualData(r.round));
    await Promise.all(promises);
}

function officialRoundHasCompleteScores(roundNum) {
    const roundData = officialPointsData?.rounds?.[String(roundNum)];
    if (!roundData || !data) return false;

    const hasEveryScore = (items, idField, scores) =>
        !!scores && items.every(item => scores[item[idField]] != null);

    return hasEveryScore(data.drivers || [], 'driver_id', roundData.drivers)
        && hasEveryScore(data.constructors || [], 'constructor_id', roundData.constructors);
}

async function preloadPriceScoreFallbackData() {
    if (!seasonSummary?.rounds) return 0;
    const fallbackRounds = seasonSummary.rounds
        .filter(r => r.has_actual && !officialRoundHasCompleteScores(r.round))
        .map(r => r.round);
    await Promise.all(fallbackRounds.map(loadActualData));
    return fallbackRounds.length;
}

async function loadOfficialPoints() {
    try {
        const resp = await fetch(cacheBust('data/official_points.json'));
        officialPointsData = await resp.json();
    } catch(e) { officialPointsData = null; }
}

async function loadWeatherData() {
    try {
        const resp = await fetch(cacheBust('data/weather.json'));
        if (resp.ok) weatherData = await resp.json();
    } catch(e) { weatherData = null; }
}

// Get the best available score for a driver/constructor in a given round.
// Prefers official F1 Fantasy points when available, falls back to pipeline-calculated actuals.
// Track which rounds fell back to calculated points
const _fallbackRounds = new Set();

function getOfficialScore(roundNum, itemId, isDriver) {
    // Check official points first
    if (officialPointsData && officialPointsData.rounds) {
        const roundData = officialPointsData.rounds[String(roundNum)];
        if (roundData) {
            const bucket = isDriver ? roundData.drivers : roundData.constructors;
            if (bucket && bucket[itemId] != null) {
                return { points: bucket[itemId], source: 'official' };
            }
        }
    }
    // Fall back to pipeline-calculated actuals
    const actData = actualCache[roundNum];
    if (actData) {
        const list = isDriver ? (actData.drivers || []) : (actData.constructors || []);
        const idField = isDriver ? 'driver_id' : 'constructor_id';
        const match = list.find(x => x[idField] === itemId);
        if (match && match.total_points != null) {
            _fallbackRounds.add(Number(roundNum));
            return { points: match.total_points, source: 'calculated' };
        }
    }
    return null;
}

function showFallbackBanner() {
    if (_fallbackRounds.size === 0) return;
    // Remove existing banner if present
    const existing = document.getElementById('fallbackBanner');
    if (existing) existing.remove();
    const rounds = [..._fallbackRounds].sort((a, b) => a - b).map(r => `R${r}`).join(', ');
    const banner = document.createElement('div');
    banner.id = 'fallbackBanner';
    banner.style.cssText = 'background:rgba(234,179,8,0.12);border:1px solid rgba(234,179,8,0.3);color:#eab308;padding:8px 16px;margin:0 auto 16px;max-width:1280px;border-radius:8px;font-size:0.8rem;text-align:center;';
    banner.innerHTML = `⚠️ Official F1 Fantasy points not available for ${rounds}. Some values shown are pipeline-calculated estimates and may differ slightly from official scores.`;
    const main = document.querySelector('.main .container');
    if (main) main.insertBefore(banner, main.firstChild);
}

async function loadPitstopData() {
    // Load pit stop records from pitstop JSON files, keyed by round so we can
    // compute "last race" vs "season" stats separately. Each stop is an object
    // {lap, stationary, lane, stationary_missing} — stationary may be null when
    // OpenF1 didn't record a wheels-up time (SC/VSC, retirements, penalties).
    //
    // Shape: window._pitstopData = {
    //   by_constructor: {
    //     [cid]: [{ round, stops: [{lap, stationary, lane, stationary_missing}, ...] }, ...]
    //   },
    //   rounds: [1, 2, 3, 6],
    //   last_round: 6
    // }
    window._pitstopData = { by_constructor: {}, rounds: [], last_round: null };

    if (!seasonSummary || !seasonSummary.rounds) return;
    for (const r of seasonSummary.rounds) {
        if (!r.has_actual) continue;
        try {
            const resp = await fetch(cacheBust(`data/pitstops_round${r.round}.json`));
            if (resp.ok) {
                const psData = await resp.json();
                if (psData && psData.by_constructor) {
                    let roundHasData = false;
                    for (const [cid, stops] of Object.entries(psData.by_constructor)) {
                        if (!stops || stops.length === 0) continue;
                        // Back-compat: legacy files were arrays of floats.
                        // New shape is array of objects with stationary/lane/lap fields.
                        const normalized = stops.map(s => {
                            if (typeof s === 'number') {
                                return { lap: null, stationary: s, lane: null, stationary_missing: false };
                            }
                            return {
                                lap: s.lap ?? null,
                                stationary: s.stationary ?? null,
                                lane: s.lane ?? null,
                                stationary_missing: !!s.stationary_missing,
                            };
                        });
                        if (!window._pitstopData.by_constructor[cid]) {
                            window._pitstopData.by_constructor[cid] = [];
                        }
                        window._pitstopData.by_constructor[cid].push({
                            round: r.round,
                            stops: normalized,
                        });
                        roundHasData = true;
                    }
                    if (roundHasData) window._pitstopData.rounds.push(r.round);
                }
            }
        } catch (e) { /* no pitstop data for this round */ }
    }
    if (window._pitstopData.rounds.length > 0) {
        window._pitstopData.last_round = Math.max(...window._pitstopData.rounds);
    }

    // DHL official fastest pit stop per round (stationary, 2dp), manually maintained
    // in data/dhl_fastest_pitstop.json from formula1.com. Authoritative fastest-stop
    // figure — more precise than OpenF1's 1dp, and it reliably identifies the true
    // fastest stop (OpenF1's rounding can disagree on who was quickest).
    window._dhlFastest = null;
    try {
        const dhlResp = await fetch(cacheBust('data/dhl_fastest_pitstop.json'));
        if (dhlResp.ok) {
            const dhl = await dhlResp.json();
            window._dhlFastest = (dhl && dhl.rounds) ? dhl.rounds : null;
        }
    } catch (e) { /* DHL fastest-stop file absent — non-fatal */ }

    // Official F1 Fantasy pit-stop points per round (manually recorded in
    // data/pitstop_points.json). The authoritative figure — our OpenF1 stationary
    // computation is too noisy (null SC/VSC stops, 1dp rounding), so actual
    // constructor scoring AND future pit-point predictions now use these.
    window._officialPitPoints = null;
    try {
        const ppResp = await fetch(cacheBust('data/pitstop_points.json'));
        if (ppResp.ok) {
            const pp = await ppResp.json();
            window._officialPitPoints = (pp && pp.rounds) ? pp.rounds : null;
        }
    } catch (e) { /* official pit-points file absent — non-fatal */ }
}

// Compute pit stop stats for one constructor, broken out by scope.
// Returns null if no data available. Stops with missing stationary time are
// counted in totalStops/missingStops but excluded from min/median/mean/slow
// calculations (no time to score against).
function getConstructorPitStats(constructorId) {
    const ps = window._pitstopData;
    if (!ps || !ps.by_constructor || !ps.by_constructor[constructorId]) return null;
    const rounds = ps.by_constructor[constructorId];
    if (rounds.length === 0) return null;

    const allStops = rounds.flatMap(r => r.stops);
    if (allStops.length === 0) return null;

    const allTimes = allStops
        .filter(s => s.stationary != null)
        .map(s => s.stationary);
    const missingStops = allStops.filter(s => s.stationary_missing).length;

    // If literally every stop has a missing stationary, return a degenerate stat
    // bundle so the team still shows up with their stop count.
    if (allTimes.length === 0) {
        const lastRound = rounds[rounds.length - 1];
        return {
            seasonFastest: null, seasonFastestRound: null,
            lastFastest: null, lastRoundNum: lastRound ? lastRound.round : null,
            median: null, mean: null, slowest: null, slowCount: 0,
            totalStops: allStops.length,
            missingStops,
            roundsWithData: rounds.length,
        };
    }

    const sorted = [...allTimes].sort((a, b) => a - b);
    const median = sorted.length % 2 === 0
        ? (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2
        : sorted[Math.floor(sorted.length / 2)];
    const mean = allTimes.reduce((a, b) => a + b, 0) / allTimes.length;
    const seasonFastest = sorted[0];
    const slowest = sorted[sorted.length - 1];
    const slowCount = allTimes.filter(t => t > 3.5).length;

    // Find which round the season-best stop happened in
    let seasonFastestRound = null;
    for (const r of rounds) {
        if (r.stops.some(s => s.stationary === seasonFastest)) {
            seasonFastestRound = r.round;
            break;
        }
    }

    // Last-race-only stats (most recent round this team had a stop)
    const lastRound = rounds[rounds.length - 1];
    const lastTimes = lastRound
        ? lastRound.stops.filter(s => s.stationary != null).map(s => s.stationary)
        : [];
    const lastFastest = lastTimes.length ? Math.min(...lastTimes) : null;
    const lastRoundNum = lastRound ? lastRound.round : null;

    return {
        seasonFastest, seasonFastestRound,
        lastFastest, lastRoundNum,
        median, mean, slowest, slowCount,
        totalStops: allStops.length,
        missingStops,
        roundsWithData: rounds.length,
    };
}

// Per-round wheels-up pit stop summary for the Analysis tab "Pit Stop
// Performance" table. Reads the SAME OpenF1 stationary (wheels-up) service time
// as the Constructors panel — NOT Jolpica's pit-stop "duration", which is the
// full pit-lane transit (~20s) and is the wrong metric for fantasy scoring.
// Stops with no measured stationary time are excluded from avg/best and flagged
// as n/a. Returns null when no wheels-up data exists for the round yet.
function getRoundPitStops(roundNum) {
    const ps = window._pitstopData;
    if (!ps || !ps.by_constructor) return null;
    const rn = Number(roundNum);
    const cons = (data && data.constructors) ? data.constructors : [];
    const rows = [];
    for (const c of cons) {
        const entries = ps.by_constructor[c.constructor_id];
        if (!entries) continue;
        const roundEntry = entries.find(e => Number(e.round) === rn);
        if (!roundEntry || !roundEntry.stops || roundEntry.stops.length === 0) continue;
        const stops = roundEntry.stops;
        const times = stops.filter(s => s.stationary != null).map(s => s.stationary);
        const missing = stops.filter(s => s.stationary_missing).length;
        const team = TEAMS[c.constructor_id] || { name: c.name, color: '#666' };
        rows.push({
            id: c.constructor_id,
            name: c.full_name || c.name || team.name,
            color: team.color,
            avg: times.length ? times.reduce((a, b) => a + b, 0) / times.length : null,
            best: times.length ? Math.min(...times) : null,
            measured: times.length,
            missing,
            totalStops: stops.length,
        });
    }
    if (rows.length === 0) return null;
    // Best (lowest) average stationary first; teams with no measured time last.
    rows.sort((a, b) => (a.avg ?? Infinity) - (b.avg ?? Infinity));
    return rows;
}

function cacheBust(url) {
    return url + (url.includes('?') ? '&' : '?') + '_=' + Date.now();
}

async function loadData() {
    try {
        const resp = await fetch(cacheBust('data/predictions.json'));
        data = await resp.json();
    } catch (e) {
        document.querySelector('.main').innerHTML = `
            <div class="container" style="text-align:center;padding:60px 20px;">
                <h2>No predictions available</h2>
                <p style="color:var(--text-secondary);margin-top:8px;">
                    Run the prediction pipeline first, then export to JSON.
                </p>
            </div>
        `;
        return;
    }

    // Update header — show next upcoming race if the predicted race is already over
    const now = new Date();
    const predRound = LOCK_DEADLINES.find(dl => dl.round === data.round);
    const predRaceOver = predRound && new Date(predRound.lock) < now;

    let headerRace, headerRound, headerSprint, headerMeta;
    if (predRaceOver) {
        // Find next upcoming non-cancelled race
        const nextRace = LOCK_DEADLINES.find(dl => !dl.cancelled && new Date(dl.lock) > now);
        if (nextRace) {
            headerRace = nextRace.race;
            headerRound = nextRace.round;
            headerSprint = nextRace.sprint;
            headerMeta = `Round ${nextRace.round} · ${data.season}${nextRace.sprint ? ' · Sprint Weekend' : ''} · Upcoming`;
        } else {
            headerRace = data.race;
            headerRound = data.round;
            headerMeta = `Round ${data.round} · ${data.season} · Season Complete`;
        }
    } else {
        headerRace = data.race;
        headerRound = data.round;
        headerMeta = `Round ${data.round} · ${data.season}${data.is_sprint_weekend ? ' · Sprint Weekend' : ''}`;
    }

    const flag = RACE_FLAGS[headerRace] || '🏁';
    document.getElementById('raceFlag').textContent = flag;
    document.getElementById('raceName').textContent = headerRace;
    document.getElementById('raceMeta').textContent = headerMeta;
    document.getElementById('generatedAt').textContent =
        `Predictions generated: ${new Date(data.generated_at).toLocaleString()}`;

    // Populate team filter
    const teams = [...new Set(data.drivers.map(d => d.constructor))].sort();
    const teamFilter = document.getElementById('teamFilter');
    teams.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t;
        opt.textContent = TEAMS[t]?.name || t;
        teamFilter.appendChild(opt);
    });
}

async function loadSeasonData() {
    try {
        const resp = await fetch(cacheBust('data/season_summary.json'));
        seasonSummary = await resp.json();
    } catch(e) { /* no season data yet */ }
}

async function loadFPAnalysis() {
    try {
        const resp = await fetch(cacheBust('data/fp_analysis.json'));
        fpAnalysis = await resp.json();
    } catch(e) { /* no fp analysis yet */ }
}

async function loadPostRaceData(roundNum) {
    if (postRaceCache[roundNum]) return postRaceCache[roundNum];
    try {
        const resp = await fetch(cacheBust(`data/post_race_round${roundNum}.json`));
        const data = await resp.json();
        postRaceCache[roundNum] = data;
        return data;
    } catch(e) { return null; }
}

async function loadPredictionsData(roundNum) {
    if (predictionsCache[roundNum]) return predictionsCache[roundNum];
    try {
        const resp = await fetch(cacheBust(`data/predictions_round${roundNum}.json`));
        const d = await resp.json();
        predictionsCache[roundNum] = d;
        return d;
    } catch(e) { return null; }
}

// Load a phase-tagged prediction archive (pre_fp, post_fp, post_quali).
// Returns null if the phase archive doesn't exist for this round.
async function loadPredictionsForPhase(roundNum, phase) {
    if (phase === 'latest' || phase === 'canonical') return loadPredictionsData(roundNum);
    const cacheKey = `${roundNum}__${phase}`;
    if (predictionsCache[cacheKey]) return predictionsCache[cacheKey];
    try {
        const resp = await fetch(cacheBust(`data/predictions_round${roundNum}_${phase}.json`));
        if (!resp.ok) return null;
        const d = await resp.json();
        predictionsCache[cacheKey] = d;
        return d;
    } catch(e) { return null; }
}

async function loadActualData(roundNum) {
    if (actualCache[roundNum]) return actualCache[roundNum];
    try {
        const resp = await fetch(cacheBust(`data/actual_round${roundNum}.json`));
        const d = await resp.json();
        actualCache[roundNum] = d;
        return d;
    } catch(e) { return null; }
}

// -- Countdown Timer --
function startCountdown() {
    const badge = document.getElementById('countdownBadge');
    const timerEl = document.getElementById('countdownTimer');
    const labelEl = document.getElementById('countdownLabel');
    const raceEl = document.getElementById('countdownRace');

    function update() {
        const now = new Date();
        // Find the next upcoming deadline
        let next = null;
        for (const dl of LOCK_DEADLINES) {
            if (dl.cancelled) continue;
            const lockTime = new Date(dl.lock);
            if (lockTime > now) { next = dl; break; }
        }

        if (!next) {
            badge.style.display = 'none';
            return;
        }

        badge.style.display = '';
        const lockTime = new Date(next.lock);
        const diff = lockTime - now;

        const days = Math.floor(diff / 86400000);
        const hrs = Math.floor((diff % 86400000) / 3600000);
        const mins = Math.floor((diff % 3600000) / 60000);
        const secs = Math.floor((diff % 60000) / 1000);

        let timerStr;
        if (days > 0) {
            timerStr = `${days}d ${hrs}h ${mins}m`;
        } else if (hrs > 0) {
            timerStr = `${hrs}h ${mins}m ${secs}s`;
        } else {
            timerStr = `${mins}m ${secs}s`;
        }

        timerEl.textContent = timerStr;
        timerEl.classList.toggle('urgent', diff < 3600000); // < 1 hour

        labelEl.textContent = next.sprint ? 'Sprint lock deadline' : 'Lock deadline';
        const flag = RACE_FLAGS[next.race] || '🏁';
        raceEl.textContent = `${flag} R${next.round} · ${lockTime.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })} · ${lockTime.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}`;
    }

    update();
    setInterval(update, 1000);
}

// -- Tabs --
// GA4 virtual page views. This is a single-page app, so without help GA only
// ever sees one page ("/") and can't tell us where people spend their time.
// Each tab switch fires a synthetic page_view with a distinct virtual path
// (/drivers, /optimizer, …) so every tab shows up as its own row in GA4's
// "Pages and screens" report — with its own view count AND average engagement
// time. The real browser URL is never changed; these paths exist only in GA.
const GA_TAB_TITLES = {
    drivers: 'Drivers', constructors: 'Constructors', optimizer: 'Lineup Optimizer',
    analysis: 'Analysis', season: 'Season', h2h: 'H2H', accuracy: 'Accuracy',
    deepdive: 'Race Deep Dive', videos: 'Videos', articles: 'Articles',
    changelog: 'Changelog', about: 'About',
};
function trackTabView(tabName) {
    if (typeof gtag !== 'function') return;  // GA blocked / not loaded — skip silently
    const label = GA_TAB_TITLES[tabName] || tabName;
    gtag('event', 'page_view', {
        page_title: `${label} | BoxBoxF1Fantasy`,
        page_location: `${location.origin}/${tabName}`,
    });
}

function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    const btn = document.querySelector(`.tab[data-tab="${tabName}"]`);
    const panel = document.getElementById(`tab-${tabName}`);
    if (btn) btn.classList.add('active');
    if (panel) panel.classList.add('active');

    // Lazy render the tab content on first visit
    renderTabIfNeeded(tabName);

    // GA4 virtual page view for this tab
    trackTabView(tabName);
}

function setupTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            switchTab(tab.dataset.tab);
            history.replaceState(null, '', `#${tab.dataset.tab}`);
        });
    });

    // Deep-link visual activation (sets the active class on .tab and
    // .tab-content). The actual data load + render is awaited by Phase 4
    // in DOMContentLoaded — calling switchTab() here would double-trigger
    // renderTabIfNeeded(), which used to race on the accuracy tab and
    // double-populate accuracyByPhase (drivers/rounds showed up twice).
    const hash = location.hash.replace('#', '');
    if (hash && document.getElementById(`tab-${hash}`)) {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        document.querySelector(`.tab[data-tab="${hash}"]`)?.classList.add('active');
        document.getElementById(`tab-${hash}`)?.classList.add('active');
    }

    // Fire the initial GA4 virtual page view for the landing tab (default
    // "drivers", or the deep-linked hash tab). switchTab() isn't called on
    // initial load — see the note above — so track it explicitly here.
    trackTabView((hash && document.getElementById(`tab-${hash}`)) ? hash : 'drivers');

    // Handle browser back/forward — fine to use switchTab here; the page
    // has finished initial load by the time the user navigates.
    window.addEventListener('hashchange', () => {
        const h = location.hash.replace('#', '');
        if (h && document.getElementById(`tab-${h}`)) switchTab(h);
    });
}

// -- Controls --
function setupControls() {
    document.getElementById('driverSort').addEventListener('change', renderDrivers);
    document.getElementById('teamFilter').addEventListener('change', renderDrivers);
    document.getElementById('driverSearch').addEventListener('input', renderDrivers);
    document.getElementById('constructorSort').addEventListener('change', renderConstructors);

    // View toggle
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const view = btn.dataset.view;
            document.getElementById('driverCards').classList.toggle('hidden', view !== 'cards');
            document.getElementById('driverTable').classList.toggle('hidden', view !== 'table');
        });
    });

    // Table header sorting
    setupTableSorting();

    // Optimizer
    document.getElementById('runOptimizer').addEventListener('click', runOptimizer);
    document.getElementById('loadMoreLineups').addEventListener('click', () => {
        const activeMode = document.querySelector('.mode-btn.active');
        const mode = activeMode ? activeMode.dataset.mode : 'fresh';
        if (mode === 'transfers') {
            const strategy = document.getElementById('transferStrategy').value;
            const chip = document.getElementById('transferChip').value;
            displayTransferResults(strategy, chip);
        } else {
            const strategy = document.getElementById('strategy').value;
            displayLineups(strategy);
        }
    });

    // Optimizer mode toggle
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const mode = btn.dataset.mode;
            document.querySelectorAll('.optimizer-mode').forEach(m => m.classList.add('hidden'));
            document.getElementById(`mode-${mode}`).classList.remove('hidden');
        });
    });

    // Transfer advisor
    document.getElementById('runTransferAdvisor').addEventListener('click', runTransferAdvisor);
    const transferBudgetEl = document.getElementById('transferBudget');
    if (transferBudgetEl) {
        transferBudgetEl.addEventListener('input', () => { transferBudgetTouched = true; });
    }
    const shareMyTeamBtn = document.getElementById('shareMyTeam');
    if (shareMyTeamBtn) {
        shareMyTeamBtn.addEventListener('click', () => {
            const dIds = myTeamDrivers.filter(Boolean);
            const cIds = myTeamConstructors.filter(Boolean);
            if (!dIds.length && !cIds.length) { flashBtn(shareMyTeamBtn, 'Pick a team first'); return; }
            shareTeam(dIds, cIds, shareMyTeamBtn);
        });
    }

    // Multi-week planner
    document.getElementById('runMultiWeekPlanner').addEventListener('click', runMultiWeekPlanner);
    const mwBudgetEl = document.getElementById('mwBudget');
    if (mwBudgetEl) {
        mwBudgetEl.addEventListener('input', () => { mwBudgetTouched = true; });
    }

    // Team compare
    const runTeamCompareBtn = document.getElementById('runTeamCompare');
    if (runTeamCompareBtn) runTeamCompareBtn.addEventListener('click', runTeamCompare);
    const compareBudgetEl = document.getElementById('compareBudget');
    if (compareBudgetEl) {
        compareBudgetEl.addEventListener('input', () => renderTeamCompareGrid());
    }
    const compareChipEl = document.getElementById('compareChip');
    if (compareChipEl) {
        compareChipEl.addEventListener('change', () => renderTeamCompareGrid());
    }
    const compareBasisEl = document.getElementById('pointsBasisCompare');
    if (compareBasisEl) {
        compareBasisEl.addEventListener('change', () => renderTeamCompareGrid());
    }
    const clearTeamCompareBtn = document.getElementById('clearTeamCompare');
    if (clearTeamCompareBtn) {
        clearTeamCompareBtn.addEventListener('click', () => {
            compareTeams = compareTeams.map((t, i) => ({
                name: `Team ${String.fromCharCode(65 + i)}`,
                drivers: [null, null, null, null, null],
                constructors: [null, null],
            }));
            renderTeamCompareGrid();
            const resultEl = document.getElementById('teamCompareResult');
            if (resultEl) resultEl.classList.add('hidden');
        });
    }

    // Multi-week target team toggle
    const mwUseTargetCb = document.getElementById('mwUseTarget');
    if (mwUseTargetCb) {
        mwUseTargetCb.addEventListener('change', () => {
            const targetDiv = document.getElementById('mwTargetTeam');
            if (mwUseTargetCb.checked) {
                targetDiv.classList.remove('hidden');
                renderTargetTeamGrid();
            } else {
                targetDiv.classList.add('hidden');
            }
        });
    }

    // Analysis panel toggle
    document.querySelectorAll('.analysis-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.analysis-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.analysis-panel').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(`panel-${btn.dataset.panel}`).classList.add('active');
        });
    });

    // Post-race round selector (with race-condition guard)
    let _postRaceRequestId = 0;
    document.getElementById('postRaceRound').addEventListener('change', async (e) => {
        const roundNum = e.target.value;
        if (!roundNum) return;
        const requestId = ++_postRaceRequestId;
        const [postRace, predictions, actual] = await Promise.all([
            loadPostRaceData(roundNum),
            loadPredictionsData(roundNum),
            loadActualData(roundNum),
            ensureLoaded('pitstops', loadPitstopData),  // wheels-up times for the pit-stop table
        ]);
        if (requestId !== _postRaceRequestId) return; // stale request, discard
        renderPostRace(postRace, predictions, actual, roundNum);
    });
}

// -- Price change helper --
function getDriverPriceChange(driver) {
    if (!seasonSummary || !seasonSummary.driver_prices) return null;
    // Match by driver abbreviation or name
    const prices = seasonSummary.driver_prices;
    // Try to find by driver_id (abbreviation)
    for (const [abbrev, info] of Object.entries(prices)) {
        if (abbrev === driver.driver_id || (info.name && info.name === driver.name)) {
            return {
                starting_price: info.starting_price,
                price_change: info.price_change,
            };
        }
    }
    return null;
}

function computeDriverPriceFields(driver) {
    const info = getDriverPriceChange(driver);
    if (info) {
        driver._starting_price = info.starting_price;
        driver._price_change = info.price_change;
    } else {
        driver._starting_price = driver.current_price;
        driver._price_change = 0;
    }
    // Price-change forecast (mirrors the card brackets via predictPriceChange).
    // Stored on the driver so the table columns are sortable. Each value is the
    // points THIS round (rolling-3 PPM basis) required to reach that price-change
    // tier: score >= _pts_great -> biggest rise; >= _pts_good -> small rise;
    // >= _pts_poor -> only a small drop; below _pts_poor (== _pts_terrible) ->
    // biggest drop. The actual $ change per tier depends on the asset's price
    // tier (A vs B) and is shown in each cell's tooltip.
    // No clamp to 0 — thresholds can be negative (a driver on a hot streak can
    // hold/rise even on a low or negative score), matching the card brackets.
    const fc = predictPriceChange(driver, driver.expected_points);
    driver._pts_great = Math.ceil(fc.ptsForGreat);
    driver._pts_good = Math.ceil(fc.ptsForGood);
    driver._pts_poor = Math.ceil(fc.ptsForPoor);
    driver._pts_terrible = driver._pts_poor; // distinct sort key; same boundary as poor
    driver._price_tier = fc.tier;
    driver._at_floor = fc.atFloor; // at the $3.0M price floor -> can't drop, only rise
}

// -- Table header sorting --
const TABLE_COLUMNS = [
    { key: null, label: '#' },
    { key: 'name', label: 'Driver' },
    { key: 'constructor', label: 'Team' },
    { key: 'projected_points', label: 'Projected' },
    { key: 'expected_points', label: 'Risk-adj' },
    { key: 'predicted_quali', label: 'Quali' },
    { key: 'predicted_finish', label: 'Race' },
    { key: 'confidence', label: 'Conf' },
    { key: 'risk', label: 'Risk' },
    { key: 'expected_overtakes', label: 'OT' },
    { key: 'current_price', label: 'Price' },
    { key: 'price_change', label: 'Change' },
    { key: 'value_score', label: 'PPM' },
    // Per-tier price-change point thresholds (sortable; values precomputed onto
    // each driver by computeDriverPriceFields as _pts_great/_pts_good/_pts_poor/_pts_terrible)
    { key: '_pts_terrible', label: 'Big drop' },
    { key: '_pts_poor', label: 'Sm drop' },
    { key: '_pts_good', label: 'Sm rise' },
    { key: '_pts_great', label: 'Big rise' },
];

function setupTableSorting() {
    const headerRow = document.querySelector('#driverTable thead tr');
    if (!headerRow) return;
    const ths = headerRow.querySelectorAll('th');
    ths.forEach((th, idx) => {
        const col = TABLE_COLUMNS[idx];
        if (!col || !col.key) return;
        th.style.cursor = 'pointer';
        th.style.userSelect = 'none';
        th.addEventListener('click', () => {
            if (tableSortColumn === col.key) {
                tableSortAsc = !tableSortAsc;
            } else {
                tableSortColumn = col.key;
                // Default direction: ascending for position-like / "lower is more
                // interesting" columns, descending for others. The rise-tier
                // thresholds default ascending (fewest points needed = easiest to
                // rise, shown first); the drop tiers default descending.
                tableSortAsc = ['predicted_quali', 'predicted_finish', 'current_price', 'starting_price', 'name', 'constructor', '_pts_great', '_pts_good'].includes(col.key);
            }
            renderDrivers();
            updateSortIndicators();
        });
    });
}

function updateSortIndicators() {
    const headerRow = document.querySelector('#driverTable thead tr');
    if (!headerRow) return;
    const ths = headerRow.querySelectorAll('th');
    ths.forEach((th, idx) => {
        const col = TABLE_COLUMNS[idx];
        if (!col || !col.key) return;
        // Remove existing indicator
        const existing = th.querySelector('.sort-arrow');
        if (existing) existing.remove();
        if (tableSortColumn === col.key) {
            const arrow = document.createElement('span');
            arrow.className = 'sort-arrow';
            arrow.style.marginLeft = '4px';
            arrow.style.fontSize = '0.75em';
            arrow.textContent = tableSortAsc ? '\u25B2' : '\u25BC';
            th.appendChild(arrow);
        }
    });
}

// -- Hero Section --
function renderHero() {
    if (!data || !data.drivers) return;
    const hero = document.getElementById('heroSection');
    if (!hero) return;

    const topPick = data.drivers[0]; // already sorted by expected_points

    // Best Value: highest value_score but must have positive ACTUAL cumulative season points
    // Filters out drivers whose season has been net-negative (sustained poor performance)
    // Also excludes the top pick to show variety
    const valueCandidates = data.drivers.filter(d => {
        const pc = predictPriceChange(d, d.expected_points);
        return d.driver_id !== topPick.driver_id &&
               pc.cumulativeTotal > 0 && d.expected_points > 5 && d.value_score > 0.5;
    });
    const bestValue = [...(valueCandidates.length > 0 ? valueCandidates : data.drivers)]
        .sort((a,b) => (b.value_score||0) - (a.value_score||0))[0];

    // Dark Horse: high upside from a non-top pick, must have non-negative actual season
    const darkHorseCandidates = data.drivers.filter(d => {
        const pc = predictPriceChange(d, d.expected_points);
        return d.driver_id !== topPick.driver_id &&
               d.driver_id !== bestValue.driver_id &&
               d.expected_points > 5 &&
               d.risk !== 'VERY HIGH' &&
               pc.cumulativeTotal >= 0; // not negative actual season
    });
    const darkHorse = [...(darkHorseCandidates.length > 0 ? darkHorseCandidates : data.drivers)]
        .sort((a,b) => {
            const aUp = (a.mc_total_p95||0) - (a.mc_total_mean||a.expected_points);
            const bUp = (b.mc_total_p95||0) - (b.mc_total_mean||b.expected_points);
            return bUp - aUp;
        })[0]; // highest upside

    const flag = RACE_FLAGS[data.race] || '';

    hero.innerHTML = `
        <div class="hero-bg"></div>
        <div class="hero-content">
            <div class="hero-title-area">
                <div class="hero-flag">${flag}</div>
                <div>
                    <h2 class="hero-title">${data.race}</h2>
                    <p class="hero-subtitle">Round ${data.round} \u00b7 ${data.season}${data.is_sprint_weekend ? ' \u00b7 Sprint Weekend' : ''} \u00b7 ML-Powered Predictions</p>
                </div>
            </div>
            <div class="hero-picks">
                ${heroCard('Top Pick', topPick, 'trophy')}
                ${heroCard('Best Value', bestValue, 'value')}
                ${heroCard('Dark Horse', darkHorse, 'rocket')}
            </div>
        </div>
    `;
}

function heroCard(label, driver, type) {
    const team = TEAMS[driver.constructor] || { name: driver.constructor, color: '#666' };
    const icon = type === 'trophy' ? '\u{1F3C6}' : type === 'value' ? '\u{1F48E}' : '\u{1F680}';
    return `
        <div class="hero-card" style="--team-color:${team.color}">
            <div class="hero-card-label">${icon} ${label}</div>
            <div class="hero-card-driver">${driver.name || driver.driver_id}</div>
            <div class="hero-card-team">${team.name}</div>
            <div class="hero-card-pts">${(typeof driver.projected_points === 'number' ? driver.projected_points : driver.expected_points).toFixed(1)} pts <span style="font-size:0.55em;font-weight:600;opacity:0.8;">proj · ${driver.expected_points.toFixed(1)} risk-adj</span></div>
            <div class="hero-card-meta">$${driver.current_price.toFixed(1)}M \u00b7 ${(driver.value_score||0).toFixed(2)} ppm</div>
        </div>
    `;
}

// -- Weather Widget --
function renderWeather() {
    const el = document.getElementById('weatherSection');
    if (!el) return;
    if (!weatherData || !weatherData.sessions) {
        el.innerHTML = '';
        return;
    }

    const w = weatherData;
    const riskColors = {
        'NONE': '#27ae60', 'LOW': '#2ecc71', 'MEDIUM': '#f39c12',
        'HIGH': '#e74c3c', 'UNKNOWN': '#666'
    };
    const riskBg = {
        'NONE': 'rgba(39,174,96,0.12)', 'LOW': 'rgba(46,204,113,0.12)',
        'MEDIUM': 'rgba(243,156,18,0.12)', 'HIGH': 'rgba(231,76,60,0.12)',
        'UNKNOWN': 'rgba(102,102,102,0.12)'
    };

    // Format last/next update times
    const lastUpdate = new Date(w.last_updated);
    const nextUpdate = new Date(w.next_update);
    const now = new Date();
    const formatTime = (d) => {
        const diff = Math.abs(now - d);
        const mins = Math.floor(diff / 60000);
        const hrs = Math.floor(mins / 60);
        if (hrs > 0) return `${hrs}h ${mins % 60}m ago`;
        return `${mins}m ago`;
    };
    const formatUntil = (d) => {
        const diff = d - now;
        if (diff < 0) return 'overdue';
        const mins = Math.floor(diff / 60000);
        const hrs = Math.floor(mins / 60);
        if (hrs > 0) return `in ${hrs}h ${mins % 60}m`;
        return `in ${mins}m`;
    };

    // Group sessions by day
    const days = {};
    w.sessions.forEach(s => {
        if (!days[s.day_label]) days[s.day_label] = [];
        days[s.day_label].push(s);
    });

    // Build session cards
    let sessionsHtml = '';
    for (const [dayLabel, sessions] of Object.entries(days)) {
        sessionsHtml += `<div class="weather-day-group">`;
        sessionsHtml += `<div class="weather-day-label">${dayLabel}</div>`;
        sessions.forEach(s => {
            const rainPct = s.rain_probability !== null ? s.rain_probability : '?';
            const rColor = riskColors[s.rain_risk] || '#666';
            const rBg = riskBg[s.rain_risk] || riskBg['UNKNOWN'];
            const tempStr = s.avg_temp !== null ? `${s.avg_temp}°C` : '--';
            const windStr = s.avg_wind !== null ? `${s.avg_wind} km/h` : '--';
            const isRainSession = s.rain_risk === 'MEDIUM' || s.rain_risk === 'HIGH';

            sessionsHtml += `
                <div class="weather-session ${isRainSession ? 'weather-rain' : ''}" style="--risk-color:${rColor};--risk-bg:${rBg}">
                    <div class="weather-session-header">
                        <span class="weather-session-name">${s.name}</span>
                        <span class="weather-session-icon">${s.weather_icon || ''}</span>
                    </div>
                    <div class="weather-rain-bar">
                        <div class="weather-rain-fill" style="width:${Math.min(rainPct, 100)}%;background:${rColor}"></div>
                    </div>
                    <div class="weather-rain-pct" style="color:${rColor}">${rainPct}% rain</div>
                    <div class="weather-session-details">
                        <span title="Temperature">\ud83c\udf21\ufe0f ${tempStr}</span>
                        <span title="Wind">\ud83d\udca8 ${windStr}</span>
                    </div>
                    <div class="weather-session-desc">${s.weather_description}</div>
                </div>`;
        });
        sessionsHtml += `</div>`;
    }

    const overallColor = riskColors[w.overall_rain_risk] || '#666';

    // Weather-aware modelling explainer: if predictions.json reports
    // weather_adjustments with non-neutral multipliers, show what's actually
    // being adjusted in the Monte Carlo. Honest about the cause.
    const wxAdj = data && data.weather_adjustments;
    let wxExplainer = '';
    if (wxAdj && wxAdj.is_active) {
        const parts = [];
        if (wxAdj.rain_risk && wxAdj.rain_risk !== 'NONE') {
            const widenPct = Math.round((wxAdj.noise_mult - 1) * 100);
            const dnfX = wxAdj.dnf_mult.toFixed(1);
            // Surface the RACE-session rain probability so the widening makes sense:
            // practice/quali can be bone dry while race day carries the risk, and
            // showing only "LOW RAIN RISK" against clear practice days reads as wrong.
            const raceSession = (w.sessions || []).find(s => (s.name || '').toLowerCase() === 'race');
            const racePct = raceSession && raceSession.rain_probability != null
                ? raceSession.rain_probability
                : (w.max_rain_probability != null ? w.max_rain_probability : null);
            const pctStr = racePct != null ? ` (race ~${racePct}% rain)` : '';
            parts.push(`Race rain risk <strong>${wxAdj.rain_risk}</strong>${pctStr} \u2192 confidence intervals widened ~${widenPct}%, DNF risk \u00d7${dnfX}, wet-skilled drivers favoured.`);
        }
        if (wxAdj.cold_weight && wxAdj.cold_weight > 0) {
            const tStr = wxAdj.race_air_temp_C != null ? `${wxAdj.race_air_temp_C.toFixed(1)}\u00b0C` : 'cool';
            parts.push(`Cool race forecast (${tStr}) \u2192 Mercedes &amp; Williams get a small score boost in the simulation.`);
        }
        if (parts.length > 0) {
            wxExplainer = `<div class="weather-adjust-explainer">${parts.join(' ')}</div>`;
        }
    }

    el.innerHTML = `
        <div class="weather-widget">
            <div class="weather-header">
                <div class="weather-title">
                    <span class="weather-title-icon">\u{1F326}\ufe0f</span>
                    <span>Weekend Weather</span>
                    <span class="weather-overall-badge" style="background:${overallColor}">${w.overall_rain_risk} RAIN RISK</span>
                </div>
                <div class="weather-update-info">
                    Updated ${formatTime(lastUpdate)} \u00b7 Next update ${formatUntil(nextUpdate)}
                </div>
            </div>
            <div class="weather-sessions-grid">
                ${sessionsHtml}
            </div>
            ${wxExplainer}
            <div class="weather-source">Data: ${w.data_source || 'Open-Meteo'}</div>
        </div>
    `;
}

// Renders a visual MC band only when a scenario is active for this driver.
// Shows the model's MC 90% CI as a faded bar, the model's baseline mean as
// one marker, and the user's adjusted expected_points as a second marker.
// Makes the "your scenario vs the model" delta visceral.
function renderMcBandVisual(d) {
    // Only render when scenario is meaningfully shifting this driver
    if (typeof d.points_delta !== 'number' || Math.abs(d.points_delta) < 0.5) return '';
    if (d.mc_total_p5 == null || d.mc_total_p95 == null) return '';

    const lo = d.mc_total_p5;
    const hi = d.mc_total_p95;
    const range = hi - lo;
    if (range <= 0) return '';

    const baseline = d.mc_total_mean != null ? d.mc_total_mean : d.expected_points - d.points_delta;
    const adjusted = d.expected_points_adjusted != null ? d.expected_points_adjusted : d.expected_points;

    // Clamp positions to [0, 100] %
    const clamp = (x) => Math.max(0, Math.min(100, x));
    const baselinePct = clamp((baseline - lo) / range * 100);
    const adjustedPct = clamp((adjusted - lo) / range * 100);
    const adjustedOutOfBand = (adjusted < lo - 0.5) || (adjusted > hi + 0.5);

    return `
        <div class="mc-band-overlay" title="Where your scenario puts ${d.name} (purple) vs the model's prediction (white). MC 90% CI band shown faded.">
            <div class="mc-band-track">
                <div class="mc-band-marker baseline" style="left:${baselinePct.toFixed(1)}%" title="Model: ${baseline.toFixed(1)} pts"></div>
                <div class="mc-band-marker adjusted ${adjustedOutOfBand ? 'out-of-band' : ''}" style="left:${adjustedPct.toFixed(1)}%" title="Your scenario: ${adjusted.toFixed(1)} pts"></div>
            </div>
            <div class="mc-band-legend">
                <span><span class="mc-band-dot baseline"></span>Model ${baseline.toFixed(1)}</span>
                <span><span class="mc-band-dot adjusted"></span>You ${adjusted.toFixed(1)} ${adjustedOutOfBand ? ' ⚠' : ''}</span>
            </div>
        </div>
    `;
}

// Returns the wet/cold badge HTML to drop into a driver/constructor card, or "".
// Reads `data.weather_adjustments` (populated by 08_export_website_json from
// the MC sim's weather_adjustments_active block).
function renderWeatherBadges() {
    const w = data && data.weather_adjustments;
    if (!w || !w.is_active) return '';
    const badges = [];
    if (w.rain_risk && w.rain_risk !== 'NONE') {
        const label = w.rain_risk === 'HIGH' ? 'Wet race forecast' :
                      w.rain_risk === 'MEDIUM' ? 'Wet race likely' : 'Light rain risk';
        badges.push(`<span class="card-weather-badge wet" title="Race rain risk: ${w.rain_risk}. Downside widened, DNF risk \u00d7${w.dnf_mult.toFixed(1)}, wet-strong drivers favoured.">\u{1F327} ${label}</span>`);
    }
    if (w.cold_weight && w.cold_weight > 0) {
        const tStr = w.race_air_temp_C != null ? `${w.race_air_temp_C.toFixed(0)}\u00b0C` : 'cool';
        badges.push(`<span class="card-weather-badge cold" title="Cool race forecast (${tStr} air). Cold-strong constructors (Mercedes, Williams) favoured.">\u{1F976} Cool race ${tStr}</span>`);
    }
    if (badges.length === 0) return '';
    return `<div class="card-weather-badges">${badges.join('')}</div>`;
}

// -- Driver rendering --
function renderDrivers() {
    if (!data) return;

    const sortKey = document.getElementById('driverSort').value;
    const teamFilter = document.getElementById('teamFilter').value;
    const searchQuery = (document.getElementById('driverSearch').value || '').trim().toLowerCase();

    // Apply user-scenario overlay (no-op if scenario empty). Returns a shallow
    // copy with overlay fields on each driver — base ML data in `data` untouched.
    const view = (window.scenarios && !window.scenarios.isEmpty())
        ? window.scenarios.applyToAll(data)
        : data;
    let drivers = [...view.drivers];

    // Compute price change fields
    drivers.forEach(d => computeDriverPriceFields(d));

    if (teamFilter !== 'all') {
        drivers = drivers.filter(d => d.constructor === teamFilter);
    }

    if (searchQuery) {
        drivers = drivers.filter(d => d.name.toLowerCase().includes(searchQuery));
    }

    // Sort — map virtual sort keys to computed fields
    let effectiveSortKey = sortKey;
    if (sortKey === 'price_change') effectiveSortKey = '_price_change';
    if (sortKey === 'starting_price') effectiveSortKey = '_starting_price';

    const ascending = ['predicted_quali', 'predicted_finish', 'current_price', 'starting_price'].includes(sortKey);
    drivers.sort((a, b) => ascending ? a[effectiveSortKey] - b[effectiveSortKey] : b[effectiveSortKey] - a[effectiveSortKey]);

    // Cards
    const cardsEl = document.getElementById('driverCards');
    const upgradeBanner = renderUpgradeBanner();
    cardsEl.innerHTML = upgradeBanner + drivers.map((d, i) => driverCard(d, i)).join('');

    // Table - apply column header sort if active, otherwise use dropdown sort
    let tableDrivers = [...drivers];
    if (tableSortColumn) {
        const riskOrder = { 'LOW': 1, 'MEDIUM': 2, 'HIGH': 3, 'VERY HIGH': 4 };
        tableDrivers.sort((a, b) => {
            let col = tableSortColumn;
            // Map virtual column keys
            if (col === 'price_change') col = '_price_change';
            let va = a[col], vb = b[col];
            if (tableSortColumn === 'risk') {
                va = riskOrder[a.risk] || 0;
                vb = riskOrder[b.risk] || 0;
            }
            if (tableSortColumn === 'name' || tableSortColumn === 'constructor') {
                va = String(va).toLowerCase();
                vb = String(vb).toLowerCase();
                return tableSortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
            }
            return tableSortAsc ? va - vb : vb - va;
        });
    }

    const tbody = document.getElementById('driverTableBody');
    tbody.innerHTML = tableDrivers.map((d, i) => driverRow(d, i)).join('');
    updateSortIndicators();
}

function driverCard(d, i) {
    const team = TEAMS[d.constructor] || { name: d.constructor, color: '#666' };
    const totalPts = d.expected_points;
    const qualiPct = totalPts > 0 ? (d.expected_points_quali / totalPts * 100) : 0;
    const racePct = totalPts > 0 ? (d.expected_points_race / totalPts * 100) : 0;
    // Sprint qualifying scores no points in official F1 Fantasy — only the
    // sprint RACE is a scoring event. (SQ segment removed.)
    const sprintRacePct = totalPts > 0 ? ((d.expected_points_sprint_race || 0) / totalPts * 100) : 0;

    const confColor = d.confidence >= 80 ? 'var(--green)' :
                      d.confidence >= 60 ? 'var(--yellow)' : 'var(--orange)';

    const riskClass = d.risk === 'LOW' ? 'risk-low' :
                      d.risk === 'MEDIUM' ? 'risk-medium' : 'risk-high';

    const posChange = d.expected_positions_gained_lost;
    const posIcon = posChange > 0 ? `+${posChange}` : posChange < 0 ? `${posChange}` : '0';

    const hasSprintPts = !!d.expected_points_sprint_race;

    // User-scenario "±" affordance: opens the per-pick slider popup. Shows the
    // active bump if non-zero so users see at a glance which picks they tweaked.
    const driverOnlyBump = window.scenarios ? window.scenarios.getDriverOnlyBump(d.driver_id) : 0;
    const scenBtnActive = Math.abs(driverOnlyBump) > 0.001;
    const scenBtnLabel = scenBtnActive
        ? `${driverOnlyBump > 0 ? '+' : ''}${driverOnlyBump.toFixed(1)}`
        : '±';

    return `
    <div class="driver-card" data-driver-id="${d.driver_id}" style="--team-color:${team.color};--i:${i}">
        <button class="scenario-btn ${scenBtnActive ? 'active' : ''}"
                data-scen-type="driver" data-scen-id="${d.driver_id}"
                title="What-if: bump ${d.name}'s pace by N positions">${scenBtnLabel}</button>
        <button class="card-share-btn" type="button" onclick="sharePrediction('driver','${d.driver_id}', this)" title="Share ${d.name}'s prediction">🔗</button>
        <div class="card-header">
            <div class="driver-info">
                <h3>${d.name}</h3>
                <div class="driver-team" style="color:${team.color}">${team.name}</div>
                <div class="card-cost" title="Current F1 Fantasy price">$${d.current_price.toFixed(1)}M</div>
            </div>
            <div class="driver-number">${d.number}</div>
        </div>
        ${renderWeatherBadges()}

        <div class="points-badge" title="Projected = points if the predicted finishing order holds (the 'if it goes to plan' score). Risk-adj = the Monte-Carlo average over 10,000 sims — it factors in DNFs, chaos and position swings, so it sits lower. The likely outcome is between the two; the P5–P95 range is shown below.">
            ${(typeof d.projected_points === 'number' ? d.projected_points : d.expected_points).toFixed(1)}
            <span class="points-label">proj</span>
            <span class="points-adj">
                <span class="points-adj-val">${d.expected_points.toFixed(1)}</span><span class="points-adj-label">risk-adj</span>
                ${(typeof d.expected_points_adjusted === 'number' && Math.abs(d.points_delta || 0) >= 0.1) ? `
                    <span class="upgrade-delta ${d.points_delta > 0 ? 'pos' : 'neg'}"
                          title="With manual team upgrade (pace bump ${d.pace_bump >= 0 ? '+' : ''}${d.pace_bump}): risk-adjusted to ${d.expected_points_adjusted.toFixed(1)} pts (P${d.predicted_finish_adjusted} race)">
                        ${d.points_delta > 0 ? '+' : ''}${d.points_delta.toFixed(1)}
                    </span>
                ` : ''}
            </span>
        </div>

        <div class="points-breakdown">
            <div class="pb-quali" style="width:${qualiPct}%"></div>
            <div class="pb-race" style="width:${racePct}%"></div>
            ${hasSprintPts ? `
                <div class="pb-sprint-race" style="width:${sprintRacePct}%"></div>
            ` : ''}
        </div>
        <div class="points-legend">
            <span><span class="legend-dot" style="background:#7c3aed"></span>Quali ${d.expected_points_quali}</span>
            <span><span class="legend-dot" style="background:var(--accent)"></span>Race ${d.expected_points_race}</span>
            ${hasSprintPts ? `
                <span><span class="legend-dot" style="background:#f59e0b"></span>Sprint ${d.expected_points_sprint_race}</span>
            ` : ''}
        </div>

        <div class="card-stats">
            <div class="stat" title="Predicted qualifying position">
                <div class="stat-value">P${d.predicted_quali}</div>
                <div class="stat-label">Quali</div>
            </div>
            <div class="stat" title="Predicted race finish position">
                <div class="stat-value">P${d.predicted_finish}</div>
                <div class="stat-label">Race</div>
            </div>
            <div class="stat" title="Expected positions gained (positive) or lost (negative) from grid to finish">
                <div class="stat-value">${posIcon}</div>
                <div class="stat-label">Pos +/-</div>
            </div>
            <div class="stat" title="DNF probability based on historical reliability and current season data">
                <div class="stat-value" style="color:${(d.dnf_probability||0) > 0.08 ? 'var(--red, #ef4444)' : (d.dnf_probability||0) > 0.04 ? 'var(--yellow)' : 'var(--green)'}">${((d.dnf_probability||0) * 100).toFixed(0)}%</div>
                <div class="stat-label">DNF</div>
            </div>
        </div>

        <div class="card-meta">
            <div class="confidence-bar" title="Prediction confidence (0-100%). Higher = more data available and models agree. Based on FP data completeness and model agreement.">
                <span>Conf</span>
                <div class="conf-track">
                    <div class="conf-fill" style="width:${d.confidence}%;background:${confColor}"></div>
                </div>
                <span>${d.confidence}%</span>
            </div>
            <span class="risk-badge ${riskClass}" title="DNF risk: ${((d.dnf_probability||0) * 100).toFixed(0)}% probability based on rolling 5-race DNF rate">${d.risk}</span>
            <span class="value-tag" style="position:relative;cursor:help" title="PPM = Points Per Million. Expected Fantasy Points / Price ($M). Higher is better. Above 1.0 = good, above 2.0 = excellent.">${d.value_score.toFixed(2)} ppm<span class="value-tooltip">PPM = Points Per Million (Expected Fantasy Points &divide; Price). Higher is better. Above 1.0 = good, above 2.0 = excellent.</span></span>
        </div>
        ${d.mc_total_p5 != null ? `
        <div class="mc-range" title="Monte Carlo simulation: 90% of outcomes fall within this range (5th to 95th percentile). Shows downside risk and upside potential.">
            <span class="mc-label">MC 90% CI</span>
            <span class="mc-values">${d.mc_total_p5.toFixed(0)} — ${d.mc_total_p95.toFixed(0)} pts</span>
        </div>
        ${renderMcBandVisual(d)}` : ''}
        ${renderPriceChangeBrackets(d)}
    </div>`;
}

function driverRow(d, i) {
    const team = TEAMS[d.constructor] || { name: d.constructor, color: '#666' };
    const projectedPoints = typeof d.projected_points === 'number'
        ? d.projected_points
        : d.expected_points;
    const riskClass = d.risk === 'LOW' ? 'risk-low' :
                      d.risk === 'MEDIUM' ? 'risk-medium' : 'risk-high';

    const pc = d._price_change || 0;
    const pcColor = pc > 0 ? 'color:var(--green)' : pc < 0 ? 'color:var(--red, #ef4444)' : '';
    const pcText = pc > 0 ? `+${pc.toFixed(1)}` : pc < 0 ? pc.toFixed(1) : '0.0';

    // Price-change forecast — per-tier points thresholds, precomputed onto the
    // driver by computeDriverPriceFields() so the columns are sortable. Each
    // tier shows the points RANGE that lands the asset in that price bracket.
    const G = d._pts_great, Gd = d._pts_good, P = d._pts_poor;
    const tc = d._price_tier === 'A' ? PRICE_TIERS.A_TIER_CHANGES : PRICE_TIERS.B_TIER_CHANGES;
    const fmtChg = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}M`;
    // " to " separator (not an en-dash) so negative ranges like "-25 to -11" read cleanly.
    const greatCell = `${G}+`;
    const goodCell = G > Gd ? `${Gd} to ${G - 1}` : `${Gd}+`;
    const poorCell = d._at_floor ? 'floor' : (Gd > P ? `${P} to ${Gd - 1}` : `${P}+`);
    const terribleCell = d._at_floor ? 'floor' : `<${P}`;

    return `
    <tr>
        <td>${i + 1}</td>
        <td><strong>${d.name}</strong></td>
        <td><span class="team-dot" style="background:${team.color}"></span>${team.name}</td>
        <td class="num"><strong>${projectedPoints.toFixed(1)}</strong></td>
        <td class="num"><strong>${d.expected_points.toFixed(1)}</strong></td>
        <td class="num">P${d.predicted_quali}</td>
        <td class="num">P${d.predicted_finish}</td>
        <td class="num">${d.confidence}%</td>
        <td class="num"><span class="risk-badge ${riskClass}">${d.risk}</span></td>
        <td class="num">${d.expected_overtakes}</td>
        <td class="num">$${d.current_price.toFixed(1)}M</td>
        <td class="num" style="${pcColor}">${pcText}</td>
        <td class="num">${d.value_score.toFixed(2)}</td>
        <td class="num" style="color:var(--red, #ef4444)" title="Score below ${P} pts this round and the price takes its biggest drop (${fmtChg(tc.terrible)})">${terribleCell}</td>
        <td class="num" style="color:var(--orange)" title="Points this round for only a small price drop (${fmtChg(tc.poor)}). Score below this range and the price takes its biggest drop.">${poorCell}</td>
        <td class="num" style="color:#22d3ee" title="Points this round for a small price rise (${fmtChg(tc.good)})">${goodCell}</td>
        <td class="num" style="color:var(--green)" title="Score this many points this round (rolling-3 PPM basis) for the biggest price rise (${fmtChg(tc.great)})">${greatCell}</td>
    </tr>`;
}

// -- Constructor rendering --
function renderConstructors() {
    if (!data) return;

    const sortKey = document.getElementById('constructorSort').value;
    const view = (window.scenarios && !window.scenarios.isEmpty())
        ? window.scenarios.applyToAll(data)
        : data;
    let constructors = [...view.constructors];

    const ascending = ['current_price'].includes(sortKey);
    constructors.sort((a, b) => ascending ? a[sortKey] - b[sortKey] : b[sortKey] - a[sortKey]);

    const grid = document.getElementById('constructorCards');
    const upgradeBanner = renderUpgradeBanner();
    grid.innerHTML = upgradeBanner + constructors.map((c, i) => constructorCard(c, i)).join('');

    renderPitstopPanel();
}

// Renders the "team upgrades active" banner above the drivers/constructors
// grids when data.upgrade_adjustments is present. Returns "" otherwise so it
// can be safely concatenated into innerHTML.
function renderUpgradeBanner() {
    if (!data || !data.upgrade_adjustments) return '';
    const teamMods = data.upgrade_adjustments.modifiers || {};
    const driverMods = data.upgrade_adjustments.driver_modifiers || {};
    const teams = Object.keys(teamMods);
    const drivers = Object.keys(driverMods);
    if (teams.length === 0 && drivers.length === 0) return '';

    const teamList = teams.map(tid => {
        const bump = teamMods[tid];
        const teamName = (TEAMS[tid] && TEAMS[tid].name) || tid;
        const sign = bump > 0 ? '+' : '';
        return `<strong style="color:${(TEAMS[tid] && TEAMS[tid].color) || 'currentColor'}">${teamName}</strong> ${sign}${bump.toFixed(2)}`;
    }).join(' &middot; ');

    const driverList = drivers.map(abbrev => {
        const bump = driverMods[abbrev];
        const sign = bump > 0 ? '+' : '';
        return `<strong>${abbrev}</strong> ${sign}${bump.toFixed(2)}`;
    }).join(' &middot; ');

    const parts = [];
    if (teams.length)   parts.push(`<div><strong>Team:</strong> ${teamList}</div>`);
    if (drivers.length) parts.push(`<div><strong>Driver-only:</strong> ${driverList}</div>`);

    return `<div class="upgrade-banner">
        <strong>Manual upgrade overlay active</strong> (team + driver bumps stack):
        ${parts.join('')}
        <div style="margin-top:6px;opacity:0.8;font-size:0.78rem;">Adjusted points appear next to each card's main number as a colored delta badge. Base ML prediction is unchanged.</div>
    </div>`;
}

/* ============================================================
   User Scenarios — UI plumbing
   ============================================================
   - Floating pill at the top: shows "Scenario: N picks" when any
     bump is active, clicking opens the manager modal.
   - Mini popup: per-card "±" button opens a positions-gained
     slider tied to one driver or one constructor.
   - Manager modal: full list of active bumps + share URL + reset.
   The scenarios.applyToAll() overlay is what makes the cards
   actually reflect these bumps (see renderDrivers / renderConstructors).
   ============================================================ */
function injectScenarioPill() {
    if (document.getElementById('scenarioPill')) return;
    const pill = document.createElement('div');
    pill.id = 'scenarioPill';
    pill.className = 'scenario-pill';
    pill.style.display = 'none';
    pill.innerHTML = `
        <span class="scenario-pill-label">Scenario: <span id="scenarioPillCount">0</span></span>
        <button class="scenario-pill-manage" id="scenarioPillManage" type="button">Manage</button>
        <button class="scenario-pill-reset" id="scenarioPillReset" type="button" title="Clear all bumps">Reset</button>
    `;
    document.body.appendChild(pill);
    document.getElementById('scenarioPillManage').addEventListener('click', openScenarioManager);
    document.getElementById('scenarioPillReset').addEventListener('click', () => {
        if (window.scenarios) window.scenarios.reset();
    });
}

function renderScenarioPill() {
    const pill = document.getElementById('scenarioPill');
    if (!pill || !window.scenarios) return;
    const n = window.scenarios.activeCount();
    if (n === 0) {
        pill.style.display = 'none';
        return;
    }
    pill.style.display = '';
    const lbl = document.getElementById('scenarioPillCount');
    if (lbl) lbl.textContent = `${n} bump${n === 1 ? '' : 's'} active`;
}

// Mini popup for a single pick — lazy-injected once, repositioned each open.
function injectScenarioPopup() {
    if (document.getElementById('scenarioPopup')) return;
    const div = document.createElement('div');
    div.id = 'scenarioPopup';
    div.className = 'scenario-popup';
    div.style.display = 'none';
    div.innerHTML = `
        <div class="scenario-popup-header">
            <strong id="scenarioPopupTitle">Pace bump</strong>
            <button class="scenario-popup-close" id="scenarioPopupClose" type="button">&times;</button>
        </div>
        <div class="scenario-popup-hint">"+2" means: I think this pick will finish 2 positions better than the model says.</div>
        <div class="scenario-popup-slider-row">
            <button class="scenario-popup-step" id="scenarioPopupMinus" type="button" title="-0.5">−</button>
            <input type="range" id="scenarioPopupSlider" min="-5" max="5" step="0.5" value="0">
            <button class="scenario-popup-step" id="scenarioPopupPlus" type="button" title="+0.5">+</button>
        </div>
        <div class="scenario-popup-value-row">
            <span id="scenarioPopupValue">0.0 positions</span>
            <span class="scenario-popup-effect" id="scenarioPopupEffect"></span>
        </div>
        <div id="scenarioPopupSuggestion" class="scenario-popup-suggestion" style="display:none;"></div>
        <div class="scenario-popup-actions">
            <button class="scenario-popup-clear" id="scenarioPopupClear" type="button">Clear</button>
            <button class="scenario-popup-done" id="scenarioPopupDone" type="button">Done</button>
        </div>
    `;
    document.body.appendChild(div);

    document.getElementById('scenarioPopupClose').addEventListener('click', closeScenarioPopup);
    document.getElementById('scenarioPopupDone').addEventListener('click', closeScenarioPopup);
    document.getElementById('scenarioPopupClear').addEventListener('click', () => {
        const slider = document.getElementById('scenarioPopupSlider');
        slider.value = 0;
        slider.dispatchEvent(new Event('input'));
    });
    document.getElementById('scenarioPopupMinus').addEventListener('click', () => {
        const s = document.getElementById('scenarioPopupSlider');
        s.value = Math.max(-5, parseFloat(s.value) - 0.5);
        s.dispatchEvent(new Event('input'));
    });
    document.getElementById('scenarioPopupPlus').addEventListener('click', () => {
        const s = document.getElementById('scenarioPopupSlider');
        s.value = Math.min(5, parseFloat(s.value) + 0.5);
        s.dispatchEvent(new Event('input'));
    });

    // Click-outside-to-close
    document.addEventListener('click', (e) => {
        const popup = document.getElementById('scenarioPopup');
        if (!popup || popup.style.display === 'none') return;
        if (popup.contains(e.target)) return;
        if (e.target.closest('.scenario-btn')) return;
        closeScenarioPopup();
    });
}

let _scenarioPopupTarget = null;  // { type, id }

function openScenarioPopup(type, id, anchorEl) {
    injectScenarioPopup();
    const popup = document.getElementById('scenarioPopup');
    _scenarioPopupTarget = { type, id };

    // Title
    let title = id;
    if (type === 'driver') {
        const d = (data.drivers || []).find(x => x.driver_id === id);
        title = d ? `${d.name} (${id})` : id;
    } else {
        const c = (data.constructors || []).find(x => x.constructor_id === id);
        title = c ? `${c.full_name || c.name} (whole team)` : id;
    }
    document.getElementById('scenarioPopupTitle').textContent = title;

    // Current value
    let cur = 0;
    if (window.scenarios) {
        cur = (type === 'driver')
            ? window.scenarios.getDriverOnlyBump(id)
            : window.scenarios.getTeamBump(id);
    }
    const slider = document.getElementById('scenarioPopupSlider');
    slider.value = cur;
    updateScenarioPopupValue(cur);

    // Wire slider input each open (clean handler)
    slider.oninput = (e) => {
        const v = parseFloat(e.target.value);
        updateScenarioPopupValue(v);
        if (!window.scenarios) return;
        if (type === 'driver') window.scenarios.setDriverBump(id, v);
        else                    window.scenarios.setTeamBump(id, v);
    };

    // Smart suggestion line (Phase 3) — computed from the driver's MC shape.
    // Cleared and rebuilt each open so it reflects the current pick.
    renderPopupSuggestion(type, id);

    // Position popup near the anchor
    popup.style.display = '';
    const rect = anchorEl.getBoundingClientRect();
    const popupRect = popup.getBoundingClientRect();
    let left = rect.left + window.scrollX;
    let top  = rect.bottom + window.scrollY + 6;
    // Keep on-screen
    const vw = window.innerWidth;
    if (left + popupRect.width > vw - 12) {
        left = Math.max(12, vw - popupRect.width - 12);
    }
    popup.style.left = `${left}px`;
    popup.style.top  = `${top}px`;
}

// Heuristic suggestion shown inside the per-card scenario popup.
// Explicitly framed as a HINT, not a recommendation. Reads the MC distribution
// shape — wide upside vs wide downside vs neither — and proposes a starting
// bump for the user to dial from. Click "Apply" to set the slider.
function renderPopupSuggestion(type, id) {
    const el = document.getElementById('scenarioPopupSuggestion');
    if (!el || !data) { return; }
    let bumpHint = null;
    let rationale = '';

    if (type === 'driver') {
        const d = (data.drivers || []).find(x => x.driver_id === id);
        if (!d || d.mc_total_p5 == null || d.mc_total_p95 == null || d.mc_total_mean == null) {
            el.style.display = 'none';
            return;
        }
        const upside = d.mc_total_p95 - d.mc_total_mean;
        const downside = d.mc_total_mean - d.mc_total_p5;
        // Asymmetry: when upside >> downside the MC distribution is right-skewed
        // (rare-but-large positive outcomes). User who's bullish on this pick
        // might lean +1. Symmetric inverse for left-skewed.
        const asym = upside - downside;
        if (Math.abs(asym) >= 8) {
            bumpHint = asym > 0 ? 1.0 : -1.0;
            const dir = asym > 0 ? 'upside' : 'downside';
            rationale = `MC ${dir} is ${Math.abs(asym).toFixed(0)} pts larger than the other tail. Try ${bumpHint > 0 ? '+1' : '-1'} if you trust the ${dir} story.`;
        } else if (d.confidence != null && d.confidence < 70) {
            // Low-confidence pick: hint without a fixed direction
            rationale = `Confidence is ${d.confidence}% (priors-only or thin FP data). Wider bump range is justified — try +/-1.5 if you have a strong view.`;
            // No bumpHint — let the user choose direction
        }
    } else {
        // Constructor: derived from both drivers
        const c = (data.constructors || []).find(x => x.constructor_id === id);
        if (!c || c.mc_total_p5 == null || c.mc_total_p95 == null) {
            el.style.display = 'none';
            return;
        }
        const upside = c.mc_total_p95 - (c.mc_total_mean || 0);
        const downside = (c.mc_total_mean || 0) - c.mc_total_p5;
        const asym = upside - downside;
        if (Math.abs(asym) >= 12) {
            bumpHint = asym > 0 ? 0.5 : -0.5;
            const dir = asym > 0 ? 'upside' : 'downside';
            rationale = `Team-level MC ${dir} skewed by ${Math.abs(asym).toFixed(0)} pts. A ${bumpHint > 0 ? '+0.5' : '-0.5'} team bump nudges both drivers.`;
        }
    }

    if (!rationale) {
        el.style.display = 'none';
        return;
    }

    el.style.display = '';
    el.innerHTML = `
        <span class="suggestion-label">\u{1F4A1} Hint:</span>
        <span>${rationale}</span>
        ${bumpHint != null
            ? `<button type="button" class="suggestion-apply" data-suggest="${bumpHint}">Apply ${bumpHint > 0 ? '+' : ''}${bumpHint}</button>`
            : ''}
    `;
    const applyBtn = el.querySelector('.suggestion-apply');
    if (applyBtn) {
        applyBtn.onclick = () => {
            const v = parseFloat(applyBtn.dataset.suggest);
            const slider = document.getElementById('scenarioPopupSlider');
            slider.value = v;
            slider.dispatchEvent(new Event('input'));
        };
    }
}

function closeScenarioPopup() {
    const popup = document.getElementById('scenarioPopup');
    if (popup) popup.style.display = 'none';
    _scenarioPopupTarget = null;
}

function updateScenarioPopupValue(v) {
    const valEl = document.getElementById('scenarioPopupValue');
    const effEl = document.getElementById('scenarioPopupEffect');
    if (!valEl) return;
    const sign = v > 0 ? '+' : '';
    valEl.textContent = `${sign}${v.toFixed(1)} position${Math.abs(v) === 1 ? '' : 's'}`;
    if (Math.abs(v) < 0.001) {
        effEl.textContent = '';
        return;
    }
    if (!_scenarioPopupTarget || !window.scenarios) { effEl.textContent = ''; return; }
    // Show the resulting points delta for this pick (after re-rank)
    const overlaid = window.scenarios.applyToAll(data);
    if (_scenarioPopupTarget.type === 'driver') {
        const d = overlaid.drivers.find(x => x.driver_id === _scenarioPopupTarget.id);
        if (d && typeof d.points_delta === 'number') {
            const s = d.points_delta > 0 ? '+' : '';
            effEl.textContent = ` → ${s}${d.points_delta.toFixed(1)} pts (P${d.predicted_finish_adjusted || d.predicted_finish})`;
        }
    } else {
        const c = overlaid.constructors.find(x => x.constructor_id === _scenarioPopupTarget.id);
        if (c && typeof c.points_delta === 'number') {
            const s = c.points_delta > 0 ? '+' : '';
            effEl.textContent = ` → ${s}${c.points_delta.toFixed(1)} pts (team total)`;
        }
    }
}

// Full manager modal — lists active bumps, master team sliders, share URL, reset.
function injectScenarioManager() {
    if (document.getElementById('scenarioManager')) return;
    const div = document.createElement('div');
    div.id = 'scenarioManager';
    div.className = 'scenario-modal-backdrop';
    div.style.display = 'none';
    div.innerHTML = `
        <div class="scenario-modal">
            <div class="scenario-modal-header">
                <h3>What-If Scenario</h3>
                <button class="scenario-modal-close" id="scenarioManagerClose" type="button">&times;</button>
            </div>
            <div class="scenario-modal-intro">
                Dial pace bumps for any driver or team. The base ML prediction stays untouched — bumps are your overlay, saved in this browser only.
                Bumps apply to this round only and reset when the round changes.
            </div>

            <div class="scenario-modal-section">
                <h4>Team bumps</h4>
                <div id="scenarioManagerTeams" class="scenario-team-grid"></div>
            </div>

            <div class="scenario-modal-section">
                <h4>Active driver bumps</h4>
                <div id="scenarioManagerDrivers" class="scenario-driver-list">
                    <p class="scenario-empty">No driver bumps active. Click the "±" button on a driver card to add one.</p>
                </div>
            </div>

            <div class="scenario-modal-section">
                <h4>Saved scenarios</h4>
                <p class="scenario-empty" style="margin-bottom:8px;">Save the current bumps as a named scenario so you can flip between alternatives (e.g. "Mercedes upgrade lands" vs "Mercedes upgrade flops").</p>
                <div class="scenario-save-row">
                    <input type="text" id="scenarioSaveName" placeholder="Name this scenario..." maxlength="48">
                    <button id="scenarioSaveBtn" type="button">Save current</button>
                </div>
                <div id="scenarioSavedList" class="scenario-saved-list"></div>
                <div id="scenarioCompareControls" class="scenario-compare-controls hidden">
                    <label>Compare
                        <select id="scenarioCompareA"></select>
                        vs
                        <select id="scenarioCompareB"></select>
                    </label>
                    <button id="scenarioCompareGo" type="button">Compare</button>
                </div>
                <div id="scenarioCompareResult" class="scenario-compare-result"></div>
            </div>

            <div class="scenario-modal-section">
                <h4>Share &amp; reset</h4>
                <div class="scenario-share-row">
                    <input type="text" id="scenarioShareUrl" readonly>
                    <button id="scenarioShareCopy" type="button">Copy</button>
                </div>
                <div class="scenario-share-hint">Send this URL to share your what-if. Loads only if the recipient is on the same round.</div>
                <div class="scenario-modal-actions">
                    <button class="scenario-reset-all" id="scenarioManagerReset" type="button">Reset all</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(div);

    document.getElementById('scenarioManagerClose').addEventListener('click', closeScenarioManager);
    div.addEventListener('click', (e) => {
        if (e.target === div) closeScenarioManager();   // backdrop click
    });
    document.getElementById('scenarioManagerReset').addEventListener('click', () => {
        if (window.scenarios) window.scenarios.reset();
        renderScenarioManagerBody();
    });
    document.getElementById('scenarioShareCopy').addEventListener('click', () => {
        const input = document.getElementById('scenarioShareUrl');
        input.select();
        try { document.execCommand('copy'); } catch(e) {}
        const btn = document.getElementById('scenarioShareCopy');
        const orig = btn.textContent;
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = orig; }, 1200);
    });

    // Saved scenarios — save / load / delete / compare wiring
    document.getElementById('scenarioSaveBtn').addEventListener('click', () => {
        const nameInput = document.getElementById('scenarioSaveName');
        const name = nameInput.value.trim();
        if (!name) {
            nameInput.focus();
            return;
        }
        if (window.scenarios.isEmpty()) {
            alert('No active bumps to save. Adjust a slider first.');
            return;
        }
        const ok = window.scenarios.saveCurrentAs(name);
        if (ok) {
            nameInput.value = '';
            renderScenarioManagerBody();
        }
    });
    document.getElementById('scenarioCompareGo').addEventListener('click', () => {
        const a = document.getElementById('scenarioCompareA').value;
        const b = document.getElementById('scenarioCompareB').value;
        if (!a || !b || a === b) {
            alert('Pick two different saved scenarios to compare.');
            return;
        }
        const result = window.scenarios.compareSavedScenarios(a, b, data);
        renderScenarioCompareResult(result);
    });
    // Delegated handlers for load/delete buttons inside the saved list
    document.getElementById('scenarioSavedList').addEventListener('click', (e) => {
        const loadBtn = e.target.closest('[data-load-saved]');
        const delBtn = e.target.closest('[data-delete-saved]');
        if (loadBtn) {
            window.scenarios.loadSavedScenario(loadBtn.dataset.loadSaved);
            renderScenarioManagerBody();
        } else if (delBtn) {
            if (confirm(`Delete saved scenario "${delBtn.dataset.deleteSaved}"?`)) {
                window.scenarios.deleteSavedScenario(delBtn.dataset.deleteSaved);
                renderScenarioManagerBody();
            }
        }
    });
}

// Render the per-driver delta table when comparing two scenarios. Sorted by
// abs(delta) descending so the biggest disagreements show first.
function renderScenarioCompareResult(result) {
    const el = document.getElementById('scenarioCompareResult');
    if (!el) return;
    if (!result) {
        el.innerHTML = '<p class="scenario-empty">Could not compare — make sure both scenarios are saved.</p>';
        return;
    }
    const rows = result.drivers
        .filter(d => Math.abs(d.delta) > 0.05)
        .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
        .slice(0, 12);
    if (rows.length === 0) {
        el.innerHTML = `<p class="scenario-empty">No meaningful differences between "${result.nameA}" and "${result.nameB}" (deltas all under 0.1 pts).</p>`;
        return;
    }
    const labelA = result.nameA === '__current__' ? 'Current' : result.nameA;
    const labelB = result.nameB === '__current__' ? 'Current' : result.nameB;
    el.innerHTML = `
        <div class="scenario-compare-table-wrap">
            <div class="scenario-compare-header">Top differences (${rows.length} drivers shown, sorted by |delta|)</div>
            <table class="scenario-compare-table">
                <thead><tr><th>Driver</th><th class="num">${labelA}</th><th class="num">${labelB}</th><th class="num">Δ</th></tr></thead>
                <tbody>
                    ${rows.map(r => `
                        <tr>
                            <td><strong>${r.name}</strong></td>
                            <td class="num">${(r.A_pts || 0).toFixed(1)}</td>
                            <td class="num">${(r.B_pts || 0).toFixed(1)}</td>
                            <td class="num" style="color:${r.delta > 0 ? 'var(--green)' : 'var(--red, #ef4444)'}">${r.delta > 0 ? '+' : ''}${r.delta.toFixed(1)}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function openScenarioManager() {
    injectScenarioManager();
    renderScenarioManagerBody();
    document.getElementById('scenarioManager').style.display = '';
}
function closeScenarioManager() {
    const m = document.getElementById('scenarioManager');
    if (m) m.style.display = 'none';
}

function renderScenarioManagerBody() {
    if (!data || !window.scenarios) return;
    const state = window.scenarios.getState();

    // Team sliders — one per constructor on the grid
    const teamsEl = document.getElementById('scenarioManagerTeams');
    if (teamsEl) {
        teamsEl.innerHTML = (data.constructors || []).map(c => {
            const team = TEAMS[c.constructor_id] || { name: c.name, color: '#666' };
            const cur = state.teamModifiers[c.constructor_id] || 0;
            return `
                <div class="scenario-team-row" style="--team-color:${team.color}">
                    <span class="scenario-team-name">${team.name}</span>
                    <input type="range" min="-5" max="5" step="0.5" value="${cur}"
                           data-scen-team="${c.constructor_id}" class="scenario-team-slider">
                    <span class="scenario-team-value">${cur > 0 ? '+' : ''}${cur.toFixed(1)}</span>
                </div>
            `;
        }).join('');
        teamsEl.querySelectorAll('.scenario-team-slider').forEach(input => {
            input.addEventListener('input', (e) => {
                const v = parseFloat(e.target.value);
                const tid = e.target.dataset.scenTeam;
                window.scenarios.setTeamBump(tid, v);
                e.target.parentElement.querySelector('.scenario-team-value').textContent =
                    `${v > 0 ? '+' : ''}${v.toFixed(1)}`;
            });
        });
    }

    // Driver bumps — show only drivers with active driver-level bumps
    const driversEl = document.getElementById('scenarioManagerDrivers');
    if (driversEl) {
        const entries = Object.entries(state.driverModifiers).filter(([_, v]) => Math.abs(v) > 0.001);
        if (entries.length === 0) {
            driversEl.innerHTML = `<p class="scenario-empty">No driver-only bumps active. Click the "±" button on a driver card to add one.</p>`;
        } else {
            driversEl.innerHTML = entries.map(([abbrev, v]) => {
                const d = (data.drivers || []).find(x => x.driver_id === abbrev);
                const name = d ? d.name : abbrev;
                return `
                    <div class="scenario-driver-row">
                        <span class="scenario-driver-name">${name}</span>
                        <input type="range" min="-5" max="5" step="0.5" value="${v}"
                               data-scen-driver="${abbrev}" class="scenario-driver-slider">
                        <span class="scenario-driver-value">${v > 0 ? '+' : ''}${v.toFixed(1)}</span>
                        <button class="scenario-driver-clear" data-clear-driver="${abbrev}" type="button" title="Clear">&times;</button>
                    </div>
                `;
            }).join('');
            driversEl.querySelectorAll('.scenario-driver-slider').forEach(input => {
                input.addEventListener('input', (e) => {
                    const v = parseFloat(e.target.value);
                    const abbrev = e.target.dataset.scenDriver;
                    window.scenarios.setDriverBump(abbrev, v);
                    e.target.parentElement.querySelector('.scenario-driver-value').textContent =
                        `${v > 0 ? '+' : ''}${v.toFixed(1)}`;
                });
            });
            driversEl.querySelectorAll('.scenario-driver-clear').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const abbrev = e.target.dataset.clearDriver;
                    window.scenarios.setDriverBump(abbrev, 0);
                    renderScenarioManagerBody();
                });
            });
        }
    }

    // Share URL
    const shareInput = document.getElementById('scenarioShareUrl');
    if (shareInput && window.scenarios) {
        const code = window.scenarios.encodeForUrl();
        const url = `${location.origin}${location.pathname}?scenario=${code}`;
        shareInput.value = window.scenarios.isEmpty() ? '' : url;
    }

    // Saved scenarios list + compare dropdowns
    const savedListEl = document.getElementById('scenarioSavedList');
    const compareControlsEl = document.getElementById('scenarioCompareControls');
    if (savedListEl && window.scenarios) {
        const saves = window.scenarios.listSavedScenarios();
        if (saves.length === 0) {
            savedListEl.innerHTML = '<p class="scenario-empty">No saved scenarios yet for this round.</p>';
            if (compareControlsEl) compareControlsEl.classList.add('hidden');
        } else {
            savedListEl.innerHTML = saves.map(s => {
                const mods = Object.keys(s.driverModifiers || {}).length + Object.keys(s.teamModifiers || {}).length;
                const date = s.savedAt ? new Date(s.savedAt).toLocaleDateString() : '';
                return `
                    <div class="scenario-saved-row">
                        <span class="scenario-saved-name">${s.name}</span>
                        <span class="scenario-saved-meta">${mods} bumps · ${date}</span>
                        <button data-load-saved="${s.name.replace(/"/g, '&quot;')}" type="button" class="scenario-saved-load">Load</button>
                        <button data-delete-saved="${s.name.replace(/"/g, '&quot;')}" type="button" class="scenario-saved-delete" title="Delete">&times;</button>
                    </div>
                `;
            }).join('');
            // Show compare controls only if we have >= 1 saved (current + 1 saved is enough)
            if (compareControlsEl) {
                compareControlsEl.classList.remove('hidden');
                const opts = ['<option value="__current__">Current (unsaved)</option>']
                    .concat(saves.map(s => `<option value="${s.name.replace(/"/g, '&quot;')}">${s.name}</option>`))
                    .join('');
                document.getElementById('scenarioCompareA').innerHTML = opts;
                document.getElementById('scenarioCompareB').innerHTML = opts;
                // Default selections: current vs first saved
                document.getElementById('scenarioCompareA').value = '__current__';
                document.getElementById('scenarioCompareB').value = saves[0].name;
            }
        }
    }
}

// Global delegation: any click on a "±" button opens the popup for that pick.
document.addEventListener('click', (e) => {
    const btn = e.target.closest('.scenario-btn');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    const type = btn.dataset.scenType;
    const id = btn.dataset.scenId;
    if (!type || !id) return;
    openScenarioPopup(type, id, btn);
});

// One-line summary of the official DHL fastest pit stop (latest round + season best),
// copied from formula1.com into data/dhl_fastest_pitstop.json (2dp). It's the
// authoritative fastest-stop figure, shown above the OpenF1-derived (1dp) per-team
// panel — OpenF1's 1dp rounding can't reliably tell who was actually quickest.
function dhlFastestHtml() {
    const d = window._dhlFastest;
    if (!d || Object.keys(d).length === 0) return '';
    const rounds = Object.keys(d).map(Number).sort((a, b) => a - b);
    const get = rnd => d[String(rnd)] || d[rnd];
    const teamName = cid => (TEAMS[cid] && TEAMS[cid].name) || cid;
    const teamColor = cid => (TEAMS[cid] && TEAMS[cid].color) || 'var(--text)';
    const fmt = rnd => {
        const e = get(rnd);
        return `<strong>${e.time.toFixed(2)}s</strong> <span style="color:${teamColor(e.team)};font-weight:600;">${teamName(e.team)}</span>`;
    };
    const latest = rounds[rounds.length - 1];
    let bestRnd = rounds[0];
    for (const r of rounds) { if (get(r).time < get(bestRnd).time) bestRnd = r; }
    return `<div class="dhl-fastest" style="margin-bottom:8px;font-size:0.8rem;color:var(--text-secondary);">`
        + `&#127942; <strong style="color:var(--text);">DHL official fastest stop</strong> &middot; `
        + `R${latest}: ${fmt(latest)} &middot; Season best: ${fmt(bestRnd)} <span style="color:var(--text-muted);">(R${bestRnd})</span>`
        + `<span style="color:var(--text-muted);font-size:0.92em;"> &middot; F1.com, 2dp</span></div>`;
}

// Render the all-teams pit stop comparison panel above constructor cards.
// Sortable by any column, default sort: season best (fastest first).
function renderPitstopPanel() {
    const body = document.getElementById('pitstopPanelBody');
    if (!body || !data) return;

    const ps = window._pitstopData;
    if (!ps || !ps.last_round) {
        body.innerHTML = '<p class="no-data">No pit stop data yet — comes online after the first race of the season.</p>';
        return;
    }

    // Build per-team rows (only teams with stops)
    const rows = [];
    for (const c of data.constructors) {
        const s = getConstructorPitStats(c.constructor_id);
        if (!s) continue;
        const team = TEAMS[c.constructor_id] || { name: c.name, color: '#666' };
        // Season total of OFFICIAL F1 Fantasy pit-stop points (the figure used
        // for actual scoring), summed across recorded rounds.
        let officialPts = null;
        const pp = window._officialPitPoints;
        if (pp) {
            let t = 0, any = false;
            for (const rnd in pp) {
                const v = pp[rnd][c.constructor_id];
                if (v != null) { t += v; any = true; }
            }
            officialPts = any ? t : null;
        }
        rows.push({
            id: c.constructor_id,
            name: c.full_name || c.name || team.name,
            color: team.color,
            officialPts,
            ...s,
        });
    }

    if (rows.length === 0) {
        body.innerHTML = '<p class="no-data">No pit stop data yet — comes online after the first race of the season.</p>';
        return;
    }

    // Compute global season best for highlighting
    const globalBest = Math.min(...rows.map(r => r.seasonFastest));
    const lastRoundOverall = ps.last_round;
    const lastRoundBest = Math.min(
        ...rows.filter(r => r.lastRoundNum === lastRoundOverall && r.lastFastest != null)
              .map(r => r.lastFastest)
    );

    let sortKey = 'seasonFastest';
    let sortAsc = true;

    function fmtTime(v) { return v != null ? `${v.toFixed(1)}s` : '—'; }

    function render() {
        const sorted = [...rows].sort((a, b) => {
            const av = a[sortKey] ?? Infinity;
            const bv = b[sortKey] ?? Infinity;
            if (typeof av === 'string') {
                return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
            }
            return sortAsc ? av - bv : bv - av;
        });

        const cols = [
            { key: 'name',           label: 'Team',           cls: 'pit-tbl-team' },
            { key: 'lastFastest',    label: `Best in last race (R${lastRoundOverall})`, fmt: r => {
                if (r.lastFastest == null) return '—';
                const isBest = r.lastFastest === lastRoundBest && r.lastRoundNum === lastRoundOverall;
                return `<span style="color:${isBest ? 'var(--green)' : 'var(--text)'};font-weight:${isBest ? '700' : '500'};">${fmtTime(r.lastFastest)}</span>` +
                       (r.lastRoundNum !== lastRoundOverall ? ` <span style="color:var(--text-muted);font-size:0.9em;">(R${r.lastRoundNum})</span>` : '');
            }},
            { key: 'seasonFastest',  label: 'Season best',    fmt: r => {
                if (r.seasonFastest == null) return '—';
                const isBest = r.seasonFastest === globalBest;
                return `<span style="color:${isBest ? 'var(--green)' : 'var(--text)'};font-weight:${isBest ? '700' : '500'};">${fmtTime(r.seasonFastest)}</span> <span style="color:var(--text-muted);font-size:0.9em;">R${r.seasonFastestRound}</span>`;
            }},
            { key: 'median',         label: 'Season median',  fmt: r => fmtTime(r.median) },
            { key: 'mean',           label: 'Season avg',     fmt: r => fmtTime(r.mean) },
            { key: 'slowCount',      label: 'Slow (>3.5s)',   fmt: r => {
                const denom = r.totalStops - (r.missingStops || 0);
                const ratio = `${r.slowCount}/${denom}`;
                if (denom === 0) return '<span style="color:var(--text-muted);">—</span>';
                if (r.slowCount === 0) return `<span style="color:var(--green);">0/${denom}</span>`;
                if (r.slowCount / denom > 0.25) return `<span style="color:var(--red, #ef4444);">${ratio}</span>`;
                return ratio;
            }},
            { key: 'totalStops',     label: 'Stops',          fmt: r => {
                if (!r.missingStops) return r.totalStops;
                return `${r.totalStops} <span style="color:var(--text-muted);font-size:0.9em;" title="${r.missingStops} stop(s) without recorded stationary time — typically during safety car / VSC, retirements, or penalty stops">(${r.missingStops} n/a)</span>`;
            }},
            { key: 'officialPts',    label: 'Official pts',    fmt: r => {
                if (r.officialPts == null) return '<span style="color:var(--text-muted);">—</span>';
                return `<span style="font-weight:700;" title="Official F1 Fantasy pit-stop points this season (bracket + fastest-stop bonus). This is the figure used for actual constructor scoring and future pit-point predictions — our timing-based estimate is too imprecise to trust.">${r.officialPts}</span>`;
            }},
        ];

        const thead = cols.map(c => {
            const arrow = c.key === sortKey ? (sortAsc ? ' ▲' : ' ▼') : '';
            const cls = c.cls ? ` class="${c.cls}"` : '';
            return `<th${cls} data-sortkey="${c.key}" style="cursor:pointer">${c.label}${arrow}</th>`;
        }).join('');

        const tbody = sorted.map(r => {
            const cells = cols.map(c => {
                const cls = c.cls ? ` class="${c.cls}"` : '';
                const val = c.fmt ? c.fmt(r) : (r[c.key] ?? '—');
                return `<td${cls}>${val}</td>`;
            }).join('');
            return `<tr><td class="pit-tbl-color" style="background:${r.color};"></td>${cells}</tr>`;
        }).join('');

        body.innerHTML = `
            ${dhlFastestHtml()}
            <div class="pit-tbl-wrap">
                <table class="pit-tbl">
                    <thead><tr><th class="pit-tbl-color"></th>${thead}</tr></thead>
                    <tbody>${tbody}</tbody>
                </table>
            </div>
            <p class="hint" style="margin-top:8px;">
                <strong>Stationary time</strong> = wheels-up service time, the metric F1 Fantasy uses for constructor pit stop scoring.
                Brackets: <span style="color:var(--green);">&lt;2.0s = 20 pts</span> · 2.0–2.2s = 10 · 2.2–2.5s = 5 · 2.5–3.0s = 2 · <span style="color:var(--red, #ef4444);">&gt;3.0s = 0</span>.
                Fastest stop of the race = +5 bonus, sub-1.80s world record = +15.
                Data refreshes 24–48h post-race when public feeds catch up.
            </p>
        `;

        body.querySelectorAll('thead th[data-sortkey]').forEach(th => {
            th.onclick = () => {
                const k = th.dataset.sortkey;
                if (k === sortKey) sortAsc = !sortAsc;
                else { sortKey = k; sortAsc = (k === 'name'); }
                render();
            };
        });
    }

    render();
}

function constructorCard(c, i) {
    const team = TEAMS[c.constructor_id] || { name: c.name, color: '#666' };
    const totalPts = c.expected_points;
    const qualiPct = totalPts > 0 ? (c.expected_points_quali / totalPts * 100) : 0;
    const racePct = totalPts > 0 ? (c.expected_points_race / totalPts * 100) : 0;

    const riskClass = c.risk === 'LOW' ? 'risk-low' :
                      c.risk === 'MEDIUM' ? 'risk-medium' : 'risk-high';

    const pitHtml = getPitStopStatsHtml(c.constructor_id);

    // Pit stop expected points and DNF impact
    const pitPts = c.expected_pit_stop_pts || c.mc_pit_stop_pts || 0;
    const dnfProb = c.dnf_probability || c.mc_dnf_prob || 0;
    const dnfImpact = c.expected_dnf_impact || 0;

    const scoringBreakdownHtml = (pitPts > 0 || dnfProb > 0) ? `
        <div class="scoring-breakdown" style="margin-top:6px;padding-top:6px;border-top:1px solid var(--border);font-size:0.75rem;color:var(--text-secondary);display:grid;grid-template-columns:1fr 1fr;gap:2px 8px;">
            ${pitPts > 0 ? `<span title="Expected pit stop points from team pit stop speed">Pit stops: <strong style="color:var(--green)">+${pitPts.toFixed(1)}</strong></span>` : ''}
            ${dnfProb > 0 ? `<span title="Average DNF probability across both drivers">DNF risk: <strong style="color:${dnfProb > 0.08 ? 'var(--red, #ef4444)' : 'var(--text)'}">${(dnfProb * 100).toFixed(0)}%</strong></span>` : ''}
            ${dnfImpact < 0 ? `<span title="Expected points lost due to DNF probability (already factored into total)">DNF impact: <strong style="color:var(--red, #ef4444)">${dnfImpact.toFixed(1)}</strong></span>` : ''}
            ${c.quali_bonus ? `<span title="Expected qualifying teamwork bonus">Quali bonus: <strong style="color:${c.quali_bonus > 0 ? 'var(--green)' : 'var(--red, #ef4444)'}">${c.quali_bonus > 0 ? '+' : ''}${typeof c.quali_bonus === 'number' ? c.quali_bonus.toFixed ? c.quali_bonus.toFixed(1) : c.quali_bonus : c.quali_bonus}</strong></span>` : ''}
        </div>` : '';

    const teamBumpVal = window.scenarios ? window.scenarios.getTeamBump(c.constructor_id) : 0;
    const scenBtnActive = Math.abs(teamBumpVal) > 0.001;
    const scenBtnLabel = scenBtnActive
        ? `${teamBumpVal > 0 ? '+' : ''}${teamBumpVal.toFixed(1)}`
        : '±';

    return `
    <div class="constructor-card" data-constructor-id="${c.constructor_id}" style="--team-color:${team.color};--i:${i}">
        <button class="scenario-btn ${scenBtnActive ? 'active' : ''}"
                data-scen-type="team" data-scen-id="${c.constructor_id}"
                title="What-if: bump ${c.name}'s pace by N positions (applies to both drivers)">${scenBtnLabel}</button>
        <button class="card-share-btn" type="button" onclick="sharePrediction('constructor','${c.constructor_id}', this)" title="Share ${c.name}'s prediction">🔗</button>
        ${renderWeatherBadges()}
        <div class="constructor-header">
            <div>
                <h3>${c.full_name || c.name}</h3>
                <div class="constructor-drivers">
                    <span class="mini-driver">${c.driver_1}</span>
                    <span class="mini-driver">${c.driver_2}</span>
                </div>
                <div class="card-cost" title="Current F1 Fantasy price">$${c.current_price.toFixed(1)}M</div>
            </div>
            <div class="points-badge" title="Projected = points if the predicted result holds. Risk-adj = Monte-Carlo average over 10,000 sims (factors in DNFs, chaos and swings), so it sits lower.">
                ${(typeof c.projected_points === 'number' ? c.projected_points : c.expected_points).toFixed(1)}
                <span class="points-label">proj</span>
                <span class="points-adj">
                    <span class="points-adj-val">${c.expected_points.toFixed(1)}</span><span class="points-adj-label">risk-adj</span>
                    ${(typeof c.expected_points_adjusted === 'number' && Math.abs(c.points_delta || 0) >= 0.1) ? `
                        <span class="upgrade-delta ${c.points_delta > 0 ? 'pos' : 'neg'}"
                              title="With manual team upgrade (pace bump ${c.pace_bump >= 0 ? '+' : ''}${c.pace_bump}): risk-adjusted to ${c.expected_points_adjusted.toFixed(1)} pts">
                            ${c.points_delta > 0 ? '+' : ''}${c.points_delta.toFixed(1)}
                        </span>
                    ` : ''}
                </span>
            </div>
        </div>

        <div class="points-breakdown">
            <div class="pb-quali" style="width:${qualiPct}%"></div>
            <div class="pb-race" style="width:${racePct}%"></div>
        </div>
        <div class="points-legend">
            <span><span class="legend-dot" style="background:#7c3aed"></span>Quali ${c.expected_points_quali}</span>
            <span><span class="legend-dot" style="background:var(--accent)"></span>Race ${c.expected_points_race}</span>
        </div>

        <div class="card-meta">
            <span class="risk-badge ${riskClass}" title="DNF risk based on combined driver risk">${c.risk}</span>
            <span class="value-tag" title="PPM = Points Per Million. Expected Points / Price ($M).">${c.value_score.toFixed(2)} ppm</span>
        </div>
        ${scoringBreakdownHtml}
        ${pitHtml}
        ${renderPriceChangeBrackets(c)}
    </div>`;
}

// -- Lock / Exclude grid for optimizer --
function renderLockGrid() {
    if (!data) return;

    const grid = document.getElementById('lockGrid');
    let html = '';

    // Drivers
    data.drivers.forEach(d => {
        const team = TEAMS[d.constructor] || { color: '#666' };
        const locked = lockedDrivers.has(d.driver_id);
        const excluded = excludedDrivers.has(d.driver_id);
        const chipClass = locked ? 'locked' : excluded ? 'excluded' : '';
        const icon = locked ? '🔒' : excluded ? '🚫' : '';
        html += `
        <div class="lock-chip ${chipClass}" data-type="driver" data-id="${d.driver_id}">
            <span class="chip-dot" style="background:${team.color}"></span>
            ${d.name.split(' ').pop()}
            <span class="lock-icon">${icon}</span>
        </div>`;
    });

    // Constructors — ALL CAPS + bold styling
    html += '<div class="lock-grid-separator"></div>';
    data.constructors.forEach(c => {
        const team = TEAMS[c.constructor_id] || { color: '#666' };
        const locked = lockedConstructors.has(c.constructor_id);
        const excluded = excludedConstructors.has(c.constructor_id);
        const chipClass = locked ? 'locked' : excluded ? 'excluded' : '';
        const icon = locked ? '🔒' : excluded ? '🚫' : '';
        html += `
        <div class="lock-chip constructor-chip ${chipClass}" data-type="constructor" data-id="${c.constructor_id}">
            <span class="chip-dot" style="background:${team.color}"></span>
            <strong>${c.name.toUpperCase()}</strong>
            <span class="lock-icon">${icon}</span>
        </div>`;
    });

    grid.innerHTML = html;

    // Click handlers: left click = lock, right click = exclude
    grid.querySelectorAll('.lock-chip').forEach(chip => {
        // Left click: toggle lock (clears exclude if set)
        chip.addEventListener('click', () => {
            const type = chip.dataset.type;
            const id = chip.dataset.id;
            const lockSet = type === 'driver' ? lockedDrivers : lockedConstructors;
            const excludeSet = type === 'driver' ? excludedDrivers : excludedConstructors;
            if (lockSet.has(id)) {
                lockSet.delete(id);
            } else {
                excludeSet.delete(id);
                lockSet.add(id);
            }
            renderLockGrid();
        });
        // Right click: toggle exclude (clears lock if set)
        chip.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            const type = chip.dataset.type;
            const id = chip.dataset.id;
            const lockSet = type === 'driver' ? lockedDrivers : lockedConstructors;
            const excludeSet = type === 'driver' ? excludedDrivers : excludedConstructors;
            if (excludeSet.has(id)) {
                excludeSet.delete(id);
            } else {
                lockSet.delete(id);
                excludeSet.add(id);
            }
            renderLockGrid();
        });
    });
}

// -- Sortable table utility --
function makeTableSortable(tableEl) {
    const headers = tableEl.querySelectorAll('th');
    headers.forEach((th, colIdx) => {
        th.style.cursor = 'pointer';
        th.title = 'Click to sort';
        th.addEventListener('click', () => {
            const tbody = tableEl.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const isAsc = th.dataset.sortDir !== 'asc';

            // Reset other headers
            headers.forEach(h => { h.dataset.sortDir = ''; h.classList.remove('sort-asc', 'sort-desc'); });
            th.dataset.sortDir = isAsc ? 'asc' : 'desc';
            th.classList.add(isAsc ? 'sort-asc' : 'sort-desc');

            rows.sort((a, b) => {
                let va = a.cells[colIdx]?.textContent.trim() || '';
                let vb = b.cells[colIdx]?.textContent.trim() || '';
                // Try numeric sort
                const na = parseFloat(va.replace(/[^0-9.\-]/g, ''));
                const nb = parseFloat(vb.replace(/[^0-9.\-]/g, ''));
                if (!isNaN(na) && !isNaN(nb)) {
                    return isAsc ? na - nb : nb - na;
                }
                return isAsc ? va.localeCompare(vb) : vb.localeCompare(va);
            });

            rows.forEach(r => tbody.appendChild(r));
        });
    });
}

// -- Price change brackets display --
function renderPriceChangeBrackets(item) {
    const pc = predictPriceChange(item, item.expected_points);
    const atFloor = pc.atFloor;
    const floorStr = `$${PRICE_TIERS.FLOOR.toFixed(1)}M`;
    const changeColor = pc.expectedChange > 0 ? 'var(--green)' : pc.expectedChange < 0 ? 'var(--red, #ef4444)' : 'var(--text-secondary)';
    const changeSign = pc.expectedChange >= 0 ? '+' : '';
    const tierLabel = pc.isATier ? 'A-tier' : 'B-tier';
    const tc = pc.tierChanges;

    // Build bracket rows — points needed for each bracket. At the price floor the
    // two drop brackets collapse into a single "won't drop" row (it can't fall
    // below the floor); rise brackets stay since it can still go up.
    const brackets = [
        { label: `${tc.great >= 0 ? '+' : ''}${tc.great.toFixed(1)}M`, threshold: 'great', pts: pc.ptsForGreat, color: 'var(--green)' },
        { label: `${tc.good >= 0 ? '+' : ''}${tc.good.toFixed(1)}M`, threshold: 'good', pts: pc.ptsForGood, color: '#22d3ee' },
    ];
    if (atFloor) {
        brackets.push({ label: 'No drop', threshold: 'floor', pts: null, color: 'var(--text-secondary)', floorRow: true });
    } else {
        brackets.push({ label: `${tc.poor >= 0 ? '+' : ''}${tc.poor.toFixed(1)}M`, threshold: 'poor', pts: pc.ptsForPoor, color: 'var(--orange)' });
        brackets.push({ label: `${tc.terrible >= 0 ? '+' : ''}${tc.terrible.toFixed(1)}M`, threshold: 'terrible', pts: null, color: 'var(--red, #ef4444)' });
    }

    // Determine which bracket the predicted score falls into
    const predicted = item.expected_points;
    let activeBracket = atFloor ? 'floor' : 'terrible';
    if (predicted >= pc.ptsForGreat) activeBracket = 'great';
    else if (predicted >= pc.ptsForGood) activeBracket = 'good';
    else if (!atFloor && predicted >= pc.ptsForPoor) activeBracket = 'poor';

    const sourceLabel = pc.hasOfficialData ? 'Official pts' : 'Calculated pts';
    const pastDisplay = pc.pastScores.length > 0
        ? pc.pastScores.map(s => s.toFixed(0)).join(', ')
        : 'No data';

    let bracketRows = brackets.map(b => {
        const isActive = b.threshold === activeBracket;
        let ptsText;
        if (b.floorRow) ptsText = `won't drop &middot; min ${floorStr}`;
        else if (b.pts != null) ptsText = `${Math.ceil(b.pts)} pts or more`;
        else ptsText = `< ${Math.ceil(pc.ptsForPoor)} pts`;
        return `<div class="bracket-row ${isActive ? 'bracket-active' : ''}" style="--bracket-color:${b.color}">
            <span class="bracket-change">${b.label}</span>
            <span class="bracket-pts">${ptsText}</span>
        </div>`;
    }).join('');

    const predictedHtml = (atFloor && pc.expectedChange <= 0)
        ? `<span class="price-change-predicted" style="color:var(--text-secondary)" title="At the ${floorStr} price floor — can't drop further, only rise">\u{1F512} At ${floorStr} floor</span>`
        : `<span class="price-change-predicted" style="color:${changeColor}">${changeSign}${pc.expectedChange.toFixed(1)}M</span>`;

    return `
    <div class="price-change-section">
        <div class="price-change-header">
            <span class="price-change-title">Price Change (${tierLabel})</span>
            ${predictedHtml}
        </div>
        <div class="price-change-meta">
            <span title="${sourceLabel}: last ${pc.pastScores.length} round(s)">${sourceLabel}: ${pastDisplay}</span>
            <span>PPM: ${pc.avgPpm.toFixed(2)} <span class="ppm-rating ${pc.rating.class}" style="font-size:0.7em">${pc.rating.label}</span></span>
        </div>
        <div class="bracket-grid">
            ${bracketRows}
        </div>
    </div>`;
}

// -- Price change prediction helpers --
function getPpmRating(avgPpm) {
    if (avgPpm >= PPM_RATINGS.GREAT) return { label: 'Great', class: 'rating-great', color: 'var(--green)' };
    if (avgPpm >= PPM_RATINGS.GOOD) return { label: 'Good', class: 'rating-good', color: '#22d3ee' };
    if (avgPpm >= PPM_RATINGS.POOR) return { label: 'Poor', class: 'rating-poor', color: 'var(--orange)' };
    return { label: 'Terrible', class: 'rating-terrible', color: 'var(--red, #ef4444)' };
}

function predictPriceChange(item, predictedPts) {
    const price = item.current_price || 10;
    const isATier = price > PRICE_TIERS.A_TIER_THRESHOLD;
    const tierChanges = isATier ? PRICE_TIERS.A_TIER_CHANGES : PRICE_TIERS.B_TIER_CHANGES;
    const isDriver = !!item.driver_id;
    const itemId = isDriver ? item.driver_id : item.constructor_id;

    // Collect past scores — prefer official F1 Fantasy points over calculated
    const pastScores = [];
    let cumulativeTotal = 0;
    let hasOfficialData = false;
    if (seasonSummary && seasonSummary.rounds) {
        for (const r of seasonSummary.rounds) {
            if (!r.has_actual) continue;
            const result = getOfficialScore(r.round, itemId, isDriver);
            if (result) {
                pastScores.push(result.points);
                cumulativeTotal += result.points;
                if (result.source === 'official') hasOfficialData = true;
            }
        }
    } else {
        // Fallback: iterate actualCache keys in order
        const rounds = Object.keys(actualCache).map(Number).sort((a, b) => a - b);
        for (const rn of rounds) {
            const result = getOfficialScore(rn, itemId, isDriver);
            if (result) {
                pastScores.push(result.points);
                cumulativeTotal += result.points;
                if (result.source === 'official') hasOfficialData = true;
            }
        }
    }

    // PPM = average of last 3 rounds (including predicted this round) / price
    const allScores = [...pastScores, predictedPts];
    const last3 = allScores.slice(-3);
    const avgPts = last3.reduce((a, b) => a + b, 0) / last3.length;
    const avgPpm = avgPts / price;
    const rating = getPpmRating(avgPpm);

    // Determine expected price change based on rating + tier
    let expectedChange = 0;
    if (avgPpm >= PPM_RATINGS.GREAT) expectedChange = tierChanges.great;
    else if (avgPpm >= PPM_RATINGS.GOOD) expectedChange = tierChanges.good;
    else if (avgPpm >= PPM_RATINGS.POOR) expectedChange = tierChanges.poor;
    else expectedChange = tierChanges.terrible;

    // Price floor: the game won't let an asset fall below PRICE_TIERS.FLOOR ($3.0M).
    // An asset already at the floor can't drop, so clamp any predicted negative
    // change to zero. Rises are still possible if it hits the points threshold.
    const atFloor = price <= PRICE_TIERS.FLOOR + 0.001;
    if (atFloor && expectedChange < 0) expectedChange = 0;

    // Points needed this round for each threshold
    // Rolling window = last 2 actual rounds + predicted this round = 3 total
    // new_avg = (sum_of_last2 + X) / windowSize
    // For avg/price >= threshold: X >= threshold * price * windowSize - sum_of_last2
    const recentWindow = pastScores.slice(-2);
    const recentSum = recentWindow.reduce((a, b) => a + b, 0);
    const windowSize = Math.min(recentWindow.length + 1, 3);
    const ptsForGreat = PPM_RATINGS.GREAT * price * windowSize - recentSum;
    const ptsForGood = PPM_RATINGS.GOOD * price * windowSize - recentSum;
    const ptsForPoor = PPM_RATINGS.POOR * price * windowSize - recentSum;

    return {
        avgPpm, rating, expectedChange, avgPts, atFloor,
        cumulativeTotal, pastScores, isATier, tierChanges, hasOfficialData,
        tier: isATier ? 'A' : 'B',
        ptsForGreat, ptsForGood, ptsForPoor,
        // Compat aliases
        projectedPpm: avgPpm, projectedTotal: cumulativeTotal + predictedPts,
    };
}

// -- Lineup Optimizer --
// F1 Fantasy rules: 5 drivers + 2 constructors within budget

// Strategy-aware lineup score. `totalPoints` should already include chip-boost
// effects from the caller, so every strategy benefits from the chip.
// - max_points: just the chip-adjusted total
// - max_value:  lineup-level points-per-dollar (rewards the best ratio across
//               the WHOLE lineup, not the sum of per-pick value scores)
// - budget_gain: projected price appreciation across all picks, weighted with points
// - balanced:   60% points + 40% value, where value = totalPoints/totalCost.
//               The "* 50" scale on value brings it onto the same order of
//               magnitude as totalPoints (typical points 200-400, ratio 2-6,
//               so 50*ratio = 100-300). Tweak only if the strategy starts
//               favoring one signal too strongly.
function lineupScore(strategy, totalPoints, totalCost, allDrivers, constructorsList) {
    if (strategy === 'max_points') return totalPoints;
    if (strategy === 'max_value') {
        return totalCost > 0 ? totalPoints / totalCost : 0;
    }
    if (strategy === 'budget_gain') {
        let priceGain = 0;
        for (const d of allDrivers) {
            const pc = predictPriceChange(d, d.expected_points);
            priceGain += pc.expectedChange;
        }
        for (const c of constructorsList) {
            const pc = predictPriceChange(c, c.expected_points);
            priceGain += pc.expectedChange;
        }
        // Mix price appreciation (heavy) with points (light) so we don't pick
        // a team that gains cash but scores zero.
        return priceGain * 100 + totalPoints * 0.1;
    }
    // balanced — see header comment for weighting rationale
    const value = totalCost > 0 ? totalPoints / totalCost : 0;
    return totalPoints * 0.6 + value * 50;
}

function adjustedBasisPoints(item, chip) {
    let pts = basisPoints(item);
    if (chip === 'no_negative' && pts < 0) pts = 0;
    return pts;
}

function intervalPoints(item, key, chip) {
    let pts;
    if (key === 'p5') pts = item.mc_total_p5;
    else if (key === 'p95') pts = item.mc_total_p95;
    else pts = item.mc_total_mean;
    if (typeof pts !== 'number') pts = (typeof item.expected_points === 'number') ? item.expected_points : 0;
    if (chip === 'no_negative' && pts < 0) pts = 0;
    return pts;
}

function getBoostTargets(drivers, chip) {
    const sorted = [...drivers].sort((a, b) => adjustedBasisPoints(b, chip) - adjustedBasisPoints(a, chip));
    return {
        primary: sorted[0] || null,
        secondary: (chip === '3x_boost' && sorted.length > 1) ? sorted[1] : null,
    };
}

function scoreTeamPicks(drivers, constructorsList, chip) {
    const { primary, secondary } = getBoostTargets(drivers, chip);
    const primaryId = primary ? primary.driver_id : null;
    const secondaryId = secondary ? secondary.driver_id : null;

    function totalFor(kind) {
        let total = 0;
        for (const d of drivers) {
            total += kind === 'basis' ? adjustedBasisPoints(d, chip) : intervalPoints(d, kind, chip);
        }
        for (const c of constructorsList) {
            total += kind === 'basis' ? adjustedBasisPoints(c, chip) : intervalPoints(c, kind, chip);
        }
        if (primary) {
            const p = kind === 'basis' ? adjustedBasisPoints(primary, chip) : intervalPoints(primary, kind, chip);
            total += p * (chip === '3x_boost' ? 2 : 1);
        }
        if (secondary) {
            const p = kind === 'basis' ? adjustedBasisPoints(secondary, chip) : intervalPoints(secondary, kind, chip);
            total += p;
        }
        return total;
    }

    return {
        expected: totalFor('basis'),
        floor: totalFor('p5'),
        ceiling: totalFor('p95'),
        boostedDriverId: primaryId,
        secondBoostedDriverId: secondaryId,
    };
}

// Iterate k-combinations of `freeDrivers` (which MUST be sorted by current_price
// ascending) with branch-and-bound budget pruning. Calls onComplete(comboArr,
// comboCost) for each lineup that fits remainBudget. comboArr is mutated and
// reused across calls — callers must consume it immediately, not store the
// reference.
//
// Replaces the old recursive `combinations(arr, k)` generator that allocated
// O(n²) sub-arrays via `arr.slice(i+1)`. With pruning + price-sort, typically
// cuts work by ~80% at a $100M budget. Limitless mode (effectiveBudget=999)
// gets no benefit from pruning but still avoids the slice allocations.
function searchCombosWithPruning(freeDrivers, priceSum, kLeft, remainBudget, onComplete) {
    const n = freeDrivers.length;
    if (n < kLeft) return;
    const comboArr = [];

    function recurse(start, costSoFar, k) {
        if (k === 0) {
            onComplete(comboArr, costSoFar);
            return;
        }
        const lastIdx = n - k;
        for (let i = start; i <= lastIdx; i++) {
            const d = freeDrivers[i];
            const newCost = costSoFar + d.current_price;
            // Cheapest possible completion of remaining k-1 slots from indices > i
            // (k-1 cheapest available = drivers[i+1 .. i+k-1] since sorted by price).
            const minRest = (k > 1) ? (priceSum[i + k] - priceSum[i + 1]) : 0;
            // Sorted by price → if even the cheapest completion overshoots, all
            // larger i (more expensive primary pick) also overshoot. Break.
            if (newCost + minRest > remainBudget) break;

            comboArr.push(d);
            recurse(i + 1, newCost, k - 1);
            comboArr.pop();
        }
    }

    recurse(0, 0, kLeft);
}

// P5: Find the optimal 5-driver + 2-constructor team within `budget` that
// maximizes projected score for a single round. Replaces the previous greedy
// "sort by score, pick top within budget" heuristic used for Wildcard chip
// candidates in the multi-week planner — that approach picked constructors
// first by score regardless of price, often leaving no room for high-value
// drivers, and missed combinations where a slightly-lower-score driver
// enables a much better complementary pick.
//
// Uses the same brute-force lineup search as the single-round advisor
// (top-N pool sorted by price + branch-and-bound pruning + full constructor
// pair enumeration). Returns the best lineup as { drivers: [ids], constructors:
// [ids], cost, score } or null if nothing fits the budget.
//
// `proj` is { drivers: {id: score}, constructors: {id: score} } for the round.
// `data` is read from outer scope (globals).
function findOptimalWildcardTeam(budget, proj, targetInfo) {
    // Pool of top-N drivers by projected score (matches single-round advisor's
    // FREE_POOL=15). When a target team is set, augment the pool with any
    // target drivers that didn't make the top-N — otherwise the wildcard
    // search couldn't consider them even when target-aware.
    // P10: pulled from MW_TUNABLES.
    const FREE_POOL = MW_TUNABLES.wildcardFreePool;
    const annotated = data.drivers.map(d => ({
        ...d,
        _score: proj.drivers[d.driver_id] || 0,
    }));
    annotated.sort((a, b) => b._score - a._score);
    let pool = annotated.slice(0, FREE_POOL);
    if (targetInfo && targetInfo.driverSet) {
        const poolIds = new Set(pool.map(d => d.driver_id));
        for (const did of targetInfo.driverSet) {
            if (!poolIds.has(did)) {
                const tgt = annotated.find(x => x.driver_id === did);
                if (tgt) pool.push(tgt);
            }
        }
    }
    const driverPool = pool.sort((a, b) => a.current_price - b.current_price); // ascending price for pruning
    const priceSum = [0];
    for (const d of driverPool) priceSum.push(priceSum[priceSum.length - 1] + d.current_price);

    let bestObjective = -Infinity;
    let bestTeam = null;

    const allConstructors = data.constructors;
    for (let i = 0; i < allConstructors.length; i++) {
        for (let j = i + 1; j < allConstructors.length; j++) {
            const c1 = allConstructors[i];
            const c2 = allConstructors[j];
            const conCost = (c1.current_price || 0) + (c2.current_price || 0);
            const conScore = (proj.constructors[c1.constructor_id] || 0) + (proj.constructors[c2.constructor_id] || 0);
            const remainBudget = budget - conCost;
            if (remainBudget < 0) continue;

            searchCombosWithPruning(driverPool, priceSum, 5, remainBudget, (combo, comboCost) => {
                let driverScore = 0;
                for (const d of combo) driverScore += (proj.drivers[d.driver_id] || 0);
                const rawScore = driverScore + conScore;

                // P5b: When target team is set, incorporate the target-distance
                // penalty into the wildcard's objective. Without this, the search
                // picks the max-points team and the planner's later distance
                // penalty has no alternative to fall back to. With it, the
                // wildcard naturally prefers target-aligned teams when the
                // points trade-off is acceptable.
                let targetPenalty = 0;
                if (targetInfo) {
                    let dist = 0;
                    for (const d of combo) if (!targetInfo.driverSet.has(d.driver_id)) dist++;
                    if (!targetInfo.conSet.has(c1.constructor_id)) dist++;
                    if (!targetInfo.conSet.has(c2.constructor_id)) dist++;
                    targetPenalty = dist * targetInfo.distanceWeight;
                }

                const objective = rawScore - targetPenalty;
                if (objective > bestObjective) {
                    bestObjective = objective;
                    // Snapshot ids — comboArr is mutated by the caller after this returns
                    bestTeam = {
                        drivers: combo.map(d => d.driver_id),
                        constructors: [c1.constructor_id, c2.constructor_id],
                        cost: comboCost + conCost,
                        score: rawScore, // raw projected points, NOT penalty-adjusted
                    };
                }
            });
        }
    }

    return bestTeam;
}

// Wrap an expensive sync task with a "Computing…" button state. setTimeout(0)
// gives the browser one paint cycle to update the button before the loop locks
// the main thread, so the user sees feedback instead of an apparent freeze.
function withLoadingButton(buttonId, originalLabel, work) {
    const btn = document.getElementById(buttonId);
    if (!btn) { work(); return; }
    btn.disabled = true;
    btn.textContent = 'Computing…';
    setTimeout(() => {
        try {
            work();
        } finally {
            btn.disabled = false;
            btn.textContent = originalLabel;
        }
    }, 0);
}

function runOptimizer() {
    if (!data) return;
    const budget = parseFloat(document.getElementById('budget').value);
    const strategy = document.getElementById('strategy').value;
    const chip = document.getElementById('chipSelect').value;
    withLoadingButton('runOptimizer', 'Find Best Lineups', () => runOptimizerSync(budget, strategy, chip));
}

function runOptimizerSync(budget, strategy, chip) {
    optimizeBasis = document.getElementById('pointsBasisOpt')?.value || 'balanced';
    const numDriverSlots = 5;
    const effectiveBudget = chip === 'limitless' ? 999 : budget;
    // Search the full free-driver pool. Budget pruning keeps the exhaustive
    // C(22,5) x C(11,2) scan usable without hiding cheap enablers outside a
    // score-ranked top-N list.

    // Per-pick score — used only for initial sort order, not for ranking.
    // Lineup-level ranking goes through lineupScore(...) which is chip-aware.
    function score(item) {
        if (strategy === 'max_points') return basisPoints(item);
        if (strategy === 'max_value') return basisValue(item);
        if (strategy === 'budget_gain') {
            const pc = predictPriceChange(item, item.expected_points);
            return pc.expectedChange * 100 + basisValue(item) * 5;
        }
        return basisPoints(item) * 0.6 + basisValue(item) * 10 * 0.4;
    }

    // Scenario-aware view: when What-If bumps are active, score against the
    // overlay; otherwise the baseline data. Same `drivers` / `constructors`
    // shape, so the rest of this function is unchanged.
    const view = getScenarioView();

    // Filter out excluded picks
    const drivers = view.drivers
        .filter(d => !excludedDrivers.has(d.driver_id))
        .map(d => ({ ...d, _type: 'driver', _score: score(d) }));
    const constructors = view.constructors
        .filter(c => !excludedConstructors.has(c.constructor_id))
        .map(c => ({ ...c, _type: 'constructor', _score: score(c) }));

    drivers.sort((a, b) => b._score - a._score);
    constructors.sort((a, b) => b._score - a._score);

    allLineups = [];
    lineupSearchTotal = 0;

    const cPairs = [];
    for (let i = 0; i < constructors.length; i++) {
        for (let j = i + 1; j < constructors.length; j++) {
            if (lockedConstructors.size > 0) {
                const pair = new Set([constructors[i].constructor_id, constructors[j].constructor_id]);
                let valid = true;
                for (const lc of lockedConstructors) {
                    if (!pair.has(lc)) { valid = false; break; }
                }
                if (!valid) continue;
            }
            cPairs.push({
                items: [constructors[i], constructors[j]],
                cost: constructors[i].current_price + constructors[j].current_price,
            });
        }
    }

    const lockedDriverList = drivers.filter(d => lockedDrivers.has(d.driver_id));
    const lockedDriverIds = new Set(lockedDriverList.map(d => d.driver_id));

    // Full free-driver pool, re-sorted by price ascending for budget pruning.
    let freeDrivers = drivers.filter(d => !lockedDriverIds.has(d.driver_id));
    freeDrivers.sort((a, b) => a.current_price - b.current_price);
    // Prefix sum of prices for cheapest-completion lookups in the pruner.
    const priceSum = [0];
    for (const d of freeDrivers) priceSum.push(priceSum[priceSum.length - 1] + d.current_price);

    const neededDrivers = numDriverSlots - lockedDriverList.length;
    const lockedDriverCost = lockedDriverList.reduce((s, d) => s + d.current_price, 0);

    if (neededDrivers < 0) {
        alert(`You have locked more than ${numDriverSlots} drivers. Please unlock some.`);
        return;
    }

    const MAX_LINEUPS = 200;
    let worstLineupIndex = -1;
    let worstLineupScore = Infinity;

    function refreshWorstLineup() {
        worstLineupIndex = -1;
        worstLineupScore = Infinity;
        for (let i = 0; i < allLineups.length; i++) {
            if (allLineups[i].totalScore < worstLineupScore) {
                worstLineupScore = allLineups[i].totalScore;
                worstLineupIndex = i;
            }
        }
    }

    function keepLineup(lineup) {
        if (allLineups.length < MAX_LINEUPS) {
            allLineups.push(lineup);
            if (lineup.totalScore < worstLineupScore) {
                worstLineupScore = lineup.totalScore;
                worstLineupIndex = allLineups.length - 1;
            }
            return;
        }
        if (lineup.totalScore <= worstLineupScore) return;
        allLineups[worstLineupIndex] = lineup;
        refreshWorstLineup();
    }

    // Per-cPair scoring + emit. Closed over cp via the outer loop.
    function makeOnComplete(cp) {
        return (combo, comboCost) => {
            const allDrivers = [...lockedDriverList, ...combo];
            const totalCost = cp.cost + lockedDriverCost + comboCost;

            lineupSearchTotal++;
            const teamScore = scoreTeamPicks(allDrivers, cp.items, chip);
            const totalPoints = teamScore.expected;

            const totalScore = lineupScore(strategy, totalPoints, totalCost, allDrivers, cp.items);

            keepLineup({
                drivers: allDrivers,
                constructors: cp.items,
                totalCost,
                totalPoints,
                totalScore,
                boostedDriverId: teamScore.boostedDriverId,
                secondBoostedDriverId: teamScore.secondBoostedDriverId,
            });
        };
    }

    for (const cp of cPairs) {
        const remainBudget = effectiveBudget - cp.cost - lockedDriverCost;
        if (remainBudget < 0) continue;

        const onComplete = makeOnComplete(cp);
        if (neededDrivers === 0) {
            onComplete([], 0);
        } else {
            searchCombosWithPruning(freeDrivers, priceSum, neededDrivers, remainBudget, onComplete);
        }
    }

    allLineups.sort((a, b) => b.totalScore - a.totalScore);

    // Deduplicate (same set of driver+constructor IDs)
    const seen = new Set();
    allLineups = allLineups.filter(l => {
        const key = [...l.drivers.map(d => d.driver_id).sort(), ...l.constructors.map(c => c.constructor_id).sort()].join(',');
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
    });

    if (allLineups.length > MAX_LINEUPS) allLineups.length = MAX_LINEUPS;

    if (allLineups.length === 0) {
        const resultEl = document.getElementById('optimizerResult');
        resultEl.classList.remove('hidden');
        document.getElementById('lineupSummary').innerHTML = '';
        document.getElementById('lineupCards').innerHTML = `
            <div class="optimizer-warning" style="background:var(--card);border:2px solid var(--orange, #f59e0b);border-radius:10px;padding:20px;text-align:center;">
                <h3 style="color:var(--orange, #f59e0b);margin-bottom:8px;">No Valid Lineup Found</h3>
                <p style="color:var(--text-secondary);">Could not find a lineup within your $${budget.toFixed(1)}M budget${lockedDrivers.size || lockedConstructors.size ? ' with the current locked/excluded picks' : ''}.</p>
                <p style="color:var(--text-secondary);margin-top:8px;">Try increasing the budget, unlocking some picks, or removing exclusions.</p>
            </div>`;
        document.getElementById('lineupLoadMore').classList.add('hidden');
        resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return;
    }

    lineupsShown = 0;
    displayLineups(strategy);
}

function displayLineups(strategy) {
    const resultEl = document.getElementById('optimizerResult');
    resultEl.classList.remove('hidden');

    // Scenario banner — only shown when What-If bumps influenced the result.
    // Rendered above lineupSummary so it can't be missed.
    const banner = scenarioBannerHtml();
    let bannerEl = resultEl.querySelector('.scenario-active-banner');
    if (bannerEl) bannerEl.remove();
    if (banner) {
        const summaryEl = document.getElementById('lineupSummary');
        summaryEl.insertAdjacentHTML('beforebegin', banner);
    }

    const budget = parseFloat(document.getElementById('budget').value);
    const total = allLineups.length;
    const end = Math.min(lineupsShown + LINEUPS_PER_PAGE, total);

    // Summary for best lineup
    if (lineupsShown === 0) {
        const best = allLineups[0];
        const allPicks = [...best.drivers, ...best.constructors];
        const avgConf = best.drivers.reduce((s, d) => s + (d.confidence || 0), 0) / best.drivers.length;
        const highRiskCount = allPicks.filter(p => p.risk === 'HIGH' || p.risk === 'VERY HIGH').length;
        const riskLevel = highRiskCount === 0 ? 'Low' : highRiskCount <= 2 ? 'Medium' : 'High';
        const riskColor = riskLevel === 'Low' ? 'var(--green)' : riskLevel === 'Medium' ? 'var(--orange)' : 'var(--red, #ef4444)';

        // Expected budget gain from price changes
        let totalExpChange = 0;
        allPicks.forEach(p => {
            const pc = predictPriceChange(p, p.expected_points);
            totalExpChange += pc.expectedChange;
        });

        // Find boosted driver names for summary
        const boostedSummaryDriver = best.drivers.find(d => d.driver_id === best.boostedDriverId);
        const boostedSummaryName = boostedSummaryDriver ? boostedSummaryDriver.name.split(' ').pop() : '?';
        const secondBoostedSummaryDriver = best.secondBoostedDriverId ? best.drivers.find(d => d.driver_id === best.secondBoostedDriverId) : null;
        const boostSummaryText = secondBoostedSummaryDriver
            ? `3x on ${boostedSummaryName}, 2x on ${secondBoostedSummaryDriver.name.split(' ').pop()}`
            : `2x on ${boostedSummaryName}`;

        document.getElementById('lineupSummary').innerHTML = `
            <div class="lineup-stat">
                <div class="big-num">${best.totalPoints.toFixed(1)}</div>
                <div class="label" title="${boostSummaryText}">Expected Points (incl boost)</div>
            </div>
            <div class="lineup-stat">
                <div class="big-num">$${best.totalCost.toFixed(1)}M</div>
                <div class="label">Total Cost</div>
            </div>
            <div class="lineup-stat">
                <div class="big-num">$${(budget - best.totalCost).toFixed(1)}M</div>
                <div class="label">Remaining</div>
            </div>
            <div class="lineup-stat">
                <div class="big-num">${avgConf.toFixed(0)}%</div>
                <div class="label" title="Average prediction confidence across all 5 drivers">Avg Confidence</div>
            </div>
            <div class="lineup-stat">
                <div class="big-num" style="color:${riskColor}">${riskLevel}</div>
                <div class="label" title="Based on number of high-risk picks (DNF probability)">Risk Level</div>
            </div>
            <div class="lineup-stat">
                <div class="big-num" style="color:${totalExpChange >= 0 ? 'var(--green)' : 'var(--red, #ef4444)'}">${totalExpChange >= 0 ? '+' : ''}${totalExpChange.toFixed(1)}M</div>
                <div class="label" title="Expected combined price change for all picks based on predicted PPM ratings">Exp Budget Change</div>
            </div>
        `;

        document.getElementById('lineupCards').innerHTML = '';
        const searched = lineupSearchTotal || total;
        document.getElementById('lineupCounter').textContent =
            searched > total
                ? `Showing top ${total} of ${searched.toLocaleString()} valid lineups`
                : `${total} valid lineup${total !== 1 ? 's' : ''} found`;
    }

    // Render lineups from lineupsShown to end
    let html = '';
    for (let li = lineupsShown; li < end; li++) {
        const lineup = allLineups[li];
        html += renderSingleLineup(lineup, li, strategy, budget);
    }

    document.getElementById('lineupCards').insertAdjacentHTML('beforeend', html);
    lineupsShown = end;

    // Show/hide load more
    const loadMoreEl = document.getElementById('lineupLoadMore');
    if (lineupsShown < total) {
        loadMoreEl.classList.remove('hidden');
        loadMoreEl.querySelector('.load-more-text').textContent = `Show more (${lineupsShown}/${total})`;
    } else {
        loadMoreEl.classList.add('hidden');
    }

    if (lineupsShown === end && lineupsShown <= LINEUPS_PER_PAGE) {
        resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

function renderSingleLineup(lineup, index, strategy, budget) {
    const allPicks = [...lineup.drivers, ...lineup.constructors];
    let totalExpChange = 0;
    allPicks.forEach(p => {
        const pc = predictPriceChange(p, p.expected_points);
        totalExpChange += pc.expectedChange;
    });

    const boostedId = lineup.boostedDriverId;
    const secondBoostedId = lineup.secondBoostedDriverId || null;
    const chipSel = document.getElementById('chipSelect');
    const activeChip = chipSel ? chipSel.value : 'none';
    const expandedClass = index === 0 ? ' expanded' : '';
    const shareDriverIds = lineup.drivers.map(d => d.driver_id).join(',');
    const shareConsIds = lineup.constructors.map(c => c.constructor_id).join(',');
    let html = `<div class="lineup-block${expandedClass}" style="margin-bottom:24px;" onclick="this.classList.toggle('expanded')">
        <div class="lineup-block-header">
            <h4><span class="lineup-expand-icon">\u25BC</span> Lineup #${index + 1}</h4>
            <div class="lineup-header-right">
                <span class="lineup-block-stats">
                    ${lineup.totalPoints.toFixed(1)} pts (incl boost) \u00b7 $${lineup.totalCost.toFixed(1)}M \u00b7
                    $${(budget - lineup.totalCost).toFixed(1)}M left \u00b7
                    <span style="color:${totalExpChange >= 0 ? 'var(--green)' : 'var(--red, #ef4444)'}">${totalExpChange >= 0 ? '+' : ''}${totalExpChange.toFixed(1)}M exp change</span>
                </span>
                <button type="button" class="share-team-btn" onclick="event.stopPropagation(); shareTeamFromIds('${shareDriverIds}','${shareConsIds}', this)">\ud83d\udd17 Share</button>
            </div>
        </div>
        <div class="lineup-details">
        <div class="lineup-picks-row">`;

    lineup.drivers.sort((a, b) => adjustedBasisPoints(b, activeChip) - adjustedBasisPoints(a, activeChip));
    lineup.drivers.forEach((d, i) => {
        const team = TEAMS[d.constructor] || { color: '#666', name: d.constructor };
        const locked = lockedDrivers.has(d.driver_id);
        const isPrimaryBoosted = d.driver_id === boostedId;
        const isSecondBoosted = d.driver_id === secondBoostedId;
        const pc = predictPriceChange(d, d.expected_points);
        const changeColor = pc.expectedChange >= 0 ? 'var(--green)' : 'var(--red, #ef4444)';
        const boostMult = (isPrimaryBoosted && activeChip === '3x_boost') ? 3 : (isPrimaryBoosted || isSecondBoosted) ? 2 : 1;
        const displayPts = (adjustedBasisPoints(d, activeChip) * boostMult).toFixed(1);
        const isBoosted = isPrimaryBoosted || isSecondBoosted;
        const boostBadge = isBoosted ? `<span class="boost-badge">${boostMult}x</span>` : '';
        html += `
        <div class="lineup-pick-h${isBoosted ? ' boosted' : ''}" style="--team-color:${team.color}">
            <div class="pick-h-header">
                <span class="pick-h-name">${d.name.split(' ').pop()}${locked ? ' \uD83D\uDD12' : ''}</span>
                ${boostBadge}
            </div>
            <div class="pick-h-team">${team.name}</div>
            <div class="pick-h-pts">${displayPts}<span class="pick-h-pts-label"> pts</span></div>
            <div class="pick-h-meta">
                <span>$${d.current_price.toFixed(1)}M</span>
                <span>P${d.predicted_quali}\u2192P${d.predicted_finish}</span>
            </div>
            <div class="pick-h-price-change" style="color:${changeColor}">
                ${pc.expectedChange >= 0 ? '+' : ''}${pc.expectedChange.toFixed(1)}M
                <span class="ppm-rating ${pc.rating.class}">${pc.rating.label}</span>
            </div>
        </div>`;
    });

    lineup.constructors.forEach((c, i) => {
        const team = TEAMS[c.constructor_id] || { color: '#666', name: c.name };
        const locked = lockedConstructors.has(c.constructor_id);
        const pc = predictPriceChange(c, c.expected_points);
        const changeColor = pc.expectedChange >= 0 ? 'var(--green)' : 'var(--red, #ef4444)';

        html += `
        <div class="lineup-pick-h constructor-pick-h" style="--team-color:${team.color}">
            <div class="pick-h-header">
                <span class="pick-h-name">${(c.name || c.constructor_id).toUpperCase()}${locked ? ' \uD83D\uDD12' : ''}</span>
            </div>
            <div class="pick-h-team">${c.driver_1} & ${c.driver_2}</div>
            <div class="pick-h-pts">${adjustedBasisPoints(c, activeChip).toFixed(1)}<span class="pick-h-pts-label"> pts</span></div>
            <div class="pick-h-meta">
                <span>$${c.current_price.toFixed(1)}M</span>
                <span>Val: ${(c.value_score||0).toFixed(1)}x</span>
            </div>
            <div class="pick-h-price-change" style="color:${changeColor}">
                ${pc.expectedChange >= 0 ? '+' : ''}${pc.expectedChange.toFixed(1)}M
                <span class="ppm-rating ${pc.rating.class}">${pc.rating.label}</span>
            </div>
        </div>`;
    });

    html += '</div></div></div>';
    return html;
}

// ============================================================
// Share Team — encode a 5+2 lineup into a link, copy/share it, and (on the
// receiving end) pre-fill the Transfer Advisor from ?team=...
// No backend: the whole team lives in the URL. Drivers and constructors share
// one comma list and are told apart by lookup on decode (their IDs never
// collide). Scoring is always against the round currently loaded.
// ============================================================
function buildShareTeamUrl(driverIds, constructorIds) {
    const ids = [...driverIds.filter(Boolean), ...constructorIds.filter(Boolean)];
    return `${location.origin}${location.pathname}?team=${ids.join(',')}`;
}

function buildTeamBlurb(driverIds, constructorIds) {
    if (!data) return 'Check out my BoxBox F1 Fantasy team';
    let pts = 0;
    const names = [];
    driverIds.filter(Boolean).forEach(id => {
        const d = data.drivers.find(x => x.driver_id === id);
        if (d) { pts += d.expected_points || 0; names.push(d.name.split(' ').pop()); }
    });
    constructorIds.filter(Boolean).forEach(id => {
        const c = data.constructors.find(x => x.constructor_id === id);
        if (c) pts += c.expected_points || 0;
    });
    const race = data.race || 'this round';
    const who = names.length ? names.join(', ') : 'my team';
    return `My BoxBox F1 Fantasy team for ${race}: ${who} — ${Math.round(pts)} predicted pts 🏎️`;
}

// Brief button feedback ("Copied!"), then restore the original label.
function flashBtn(btn, msg) {
    if (!btn) return;
    if (!btn.dataset._orig) btn.dataset._orig = btn.textContent;
    btn.textContent = msg;
    btn.disabled = true;
    setTimeout(() => { btn.textContent = btn.dataset._orig; btn.disabled = false; }, 1600);
}

function copyTextToClipboard(text, btn, copiedMsg) {
    const ok = () => flashBtn(btn, copiedMsg || '✓ Copied!');
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(ok).catch(() => fallbackCopyText(text, ok));
    } else {
        fallbackCopyText(text, ok);
    }
}

function fallbackCopyText(text, done) {
    try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.top = '-1000px';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        if (done) done();
    } catch (e) { /* clipboard blocked — nothing we can do */ }
}

// Share or copy. Touch devices get the native share sheet with the points
// blurb (it lands in a message, where the text reads nicely). Desktop copies
// JUST the bare link — that's what you paste into an address bar or chat box.
function shareOrCopy(blurb, url, btn, copiedMsg) {
    let isTouch = false;
    try { isTouch = window.matchMedia && window.matchMedia('(pointer: coarse)').matches; } catch (e) {}
    if (isTouch && navigator.share) {
        navigator.share({ title: 'BoxBox F1 Fantasy', text: blurb, url }).catch(() => {});
        return;
    }
    copyTextToClipboard(url, btn, copiedMsg);
}

function shareTeam(driverIds, constructorIds, btn) {
    shareOrCopy(buildTeamBlurb(driverIds, constructorIds), buildShareTeamUrl(driverIds, constructorIds), btn);
}

// Called from the inline onclick on each optimizer lineup's Share button.
function shareTeamFromIds(driverCsv, consCsv, btn) {
    shareTeam(driverCsv ? driverCsv.split(',') : [], consCsv ? consCsv.split(',') : [], btn);
}

// --- Option D: share a single driver/constructor prediction ---
function buildPredictionBlurb(type, id) {
    if (!data) return 'Check out this BoxBox F1 Fantasy prediction';
    const race = data.race || 'this round';
    if (type === 'constructor') {
        const c = data.constructors.find(x => x.constructor_id === id);
        if (!c) return `BoxBox F1 Fantasy prediction for ${race}`;
        return `${(c.name || c.constructor_id).toUpperCase()} — ${race}: ${Math.round(c.expected_points)} predicted pts on BoxBoxF1Fantasy`;
    }
    const d = data.drivers.find(x => x.driver_id === id);
    if (!d) return `BoxBox F1 Fantasy prediction for ${race}`;
    return `${d.name} — ${race}: P${d.predicted_quali} quali, P${d.predicted_finish} finish, ${Math.round(d.expected_points)} predicted pts on BoxBoxF1Fantasy`;
}

function sharePrediction(type, id, btn) {
    const param = type === 'constructor' ? 'constructor' : 'driver';
    const url = `${location.origin}${location.pathname}?${param}=${encodeURIComponent(id)}`;
    shareOrCopy(buildPredictionBlurb(type, id), url, btn, '✓');
}

// Receiving end: ?driver=ID / ?constructor=ID → open the tab, scroll to and
// briefly highlight that card.
function focusPrediction(type, id) {
    const tab = type === 'constructor' ? 'constructors' : 'drivers';
    switchTab(tab);  // triggers the lazy render if the tab hasn't been opened yet
    const sel = type === 'constructor' ? `[data-constructor-id="${id}"]` : `[data-driver-id="${id}"]`;
    let attempts = 0;
    const tryFocus = () => {
        const card = document.querySelector(sel);
        if (card) {
            card.scrollIntoView({ behavior: 'smooth', block: 'center' });
            card.classList.add('card-highlight');
            setTimeout(() => card.classList.remove('card-highlight'), 2400);
        } else if (attempts++ < 15) {
            setTimeout(tryFocus, 120);  // constructors render async on first open
        }
    };
    tryFocus();
}

// Receiving end: ?team=ID,ID,... → pre-fill the Transfer Advisor with the team.
function applySharedTeam(teamParam) {
    if (!data || !teamParam) return;
    const ids = teamParam.split(',').map(s => s.trim()).filter(Boolean);
    const dIds = [], cIds = [];
    ids.forEach(id => {
        if (data.drivers.some(d => d.driver_id === id)) dIds.push(id);
        else if (data.constructors.some(c => c.constructor_id === id)) cIds.push(id);
    });
    if (!dIds.length && !cIds.length) return;  // nothing recognisable in the link

    myTeamDrivers = [null, null, null, null, null];
    myTeamConstructors = [null, null];
    dIds.slice(0, 5).forEach((id, i) => { myTeamDrivers[i] = id; });
    cIds.slice(0, 2).forEach((id, i) => { myTeamConstructors[i] = id; });

    // Show it in the Transfer Advisor.
    switchTab('optimizer');
    const transfersBtn = document.querySelector('.mode-btn[data-mode="transfers"]');
    if (transfersBtn) transfersBtn.click();
    renderMyTeamGrid();
    showSharedTeamBanner();

    // Tidy the address bar so a refresh doesn't re-trigger the import.
    try { history.replaceState(null, '', location.pathname); } catch (e) {}
}

function showSharedTeamBanner() {
    const section = document.querySelector('#mode-transfers .my-team-section');
    if (!section) return;
    let b = document.getElementById('sharedTeamBanner');
    if (!b) {
        b = document.createElement('div');
        b.id = 'sharedTeamBanner';
        b.className = 'shared-team-banner';
        section.insertBefore(b, section.firstChild);
    }
    b.innerHTML = `👋 You're viewing a <strong>shared team</strong>. Tweak the picks, or hit <strong>Find Best Transfers</strong> for upgrade ideas. <button type="button" class="shared-team-dismiss" aria-label="Dismiss">×</button>`;
    const dismiss = b.querySelector('.shared-team-dismiss');
    if (dismiss) dismiss.addEventListener('click', () => b.remove());
}

// ============================================================
// My Team Grid (Transfer Advisor)
// ============================================================

function renderMyTeamGrid() {
    if (!data) return;
    const grid = document.getElementById('myTeamGrid');
    if (!grid) return;

    let html = '';
    // 5 driver slots
    for (let i = 0; i < 5; i++) {
        const did = myTeamDrivers[i];
        const driver = did ? data.drivers.find(d => d.driver_id === did) : null;
        if (driver) {
            const team = TEAMS[driver.constructor] || { color: '#666' };
            html += `<div class="my-team-slot filled" style="--team-color:${team.color}" data-slot="driver" data-index="${i}">
                <div class="slot-label">Driver ${i + 1}</div>
                <div class="slot-name">${driver.name.split(' ').pop()}</div>
                <div class="slot-price">$${driver.current_price.toFixed(1)}M</div>
                <span class="slot-remove" data-slot="driver" data-index="${i}">&times;</span>
            </div>`;
        } else {
            html += `<div class="my-team-slot" data-slot="driver" data-index="${i}">
                <div class="slot-label">Driver ${i + 1}</div>
                <div class="slot-name" style="color:var(--text-secondary)">+ Select</div>
            </div>`;
        }
    }
    // 2 constructor slots
    for (let i = 0; i < 2; i++) {
        const cid = myTeamConstructors[i];
        const con = cid ? data.constructors.find(c => c.constructor_id === cid) : null;
        if (con) {
            const team = TEAMS[con.constructor_id] || { color: '#666' };
            html += `<div class="my-team-slot filled" style="--team-color:${team.color}" data-slot="constructor" data-index="${i}">
                <div class="slot-label">Constructor ${i + 1}</div>
                <div class="slot-name">${(con.name || con.constructor_id).toUpperCase()}</div>
                <div class="slot-price">$${con.current_price.toFixed(1)}M</div>
                <span class="slot-remove" data-slot="constructor" data-index="${i}">&times;</span>
            </div>`;
        } else {
            html += `<div class="my-team-slot" data-slot="constructor" data-index="${i}">
                <div class="slot-label">Constructor ${i + 1}</div>
                <div class="slot-name" style="color:var(--text-secondary)">+ Select</div>
            </div>`;
        }
    }
    grid.innerHTML = html;

    // Seed budget inputs from team cost until the user edits them. After that,
    // slot changes must not erase bank/unspent budget that was typed manually.
    const totalCost = getMyTeamCost();
    syncBudgetInputsFromTeamCost(totalCost);

    // Click handlers for this grid
    function attachGridHandlers(gridEl) {
        gridEl.querySelectorAll('.my-team-slot').forEach(slot => {
            slot.addEventListener('click', (e) => {
                if (e.target.classList.contains('slot-remove')) {
                    const type = e.target.dataset.slot;
                    const idx = parseInt(e.target.dataset.index);
                    if (type === 'driver') myTeamDrivers[idx] = null;
                    else myTeamConstructors[idx] = null;
                    renderMyTeamGrid();
                    return;
                }
                const type = slot.dataset.slot;
                const idx = parseInt(slot.dataset.index);
                slotPickerTarget = 'myTeam';
                showSlotPicker(type, idx);
            });
        });
    }

    attachGridHandlers(grid);

    // Also render into multi-week planner grid (shared state)
    const mwGrid = document.getElementById('myTeamGridMW');
    if (mwGrid) {
        mwGrid.innerHTML = html;
        attachGridHandlers(mwGrid);
    }
}

function getMyTeamCost() {
    let cost = 0;
    for (const did of myTeamDrivers) {
        if (!did || !data) continue;
        const d = data.drivers.find(x => x.driver_id === did);
        if (d) cost += d.current_price;
    }
    for (const cid of myTeamConstructors) {
        if (!cid || !data) continue;
        const c = data.constructors.find(x => x.constructor_id === cid);
        if (c) cost += c.current_price;
    }
    return cost;
}

function syncBudgetInputsFromTeamCost(totalCost) {
    if (totalCost <= 0) return;
    const formatted = totalCost.toFixed(1);
    const transferBudgetEl = document.getElementById('transferBudget');
    if (transferBudgetEl && (!transferBudgetTouched || transferBudgetEl.value === '')) {
        transferBudgetEl.value = formatted;
    }
    const mwBudgetEl = document.getElementById('mwBudget');
    if (mwBudgetEl && (!mwBudgetTouched || mwBudgetEl.value === '')) {
        mwBudgetEl.value = formatted;
    }
}

function getCompareBudget() {
    const value = parseFloat(document.getElementById('compareBudget')?.value || '100');
    return Number.isFinite(value) ? value : 100;
}

function compareTeamCost(teamState, omit = {}) {
    if (!data || !teamState) return 0;
    let cost = 0;
    teamState.drivers.forEach((id, idx) => {
        if (!id || (omit.type === 'driver' && omit.index === idx)) return;
        const driver = data.drivers.find(d => d.driver_id === id);
        cost += driver?.current_price || 0;
    });
    teamState.constructors.forEach((id, idx) => {
        if (!id || (omit.type === 'constructor' && omit.index === idx)) return;
        const constructor = data.constructors.find(c => c.constructor_id === id);
        cost += constructor?.current_price || 0;
    });
    return cost;
}

function compareTeamBudgetSummary(teamState, budget = getCompareBudget()) {
    const cost = compareTeamCost(teamState);
    const bank = budget - cost;
    const picked = teamState.drivers.filter(Boolean).length + teamState.constructors.filter(Boolean).length;
    return { cost, bank, picked, overBudget: bank < -0.0001 };
}

function comparePointsBasis() {
    return document.getElementById('pointsBasisCompare')?.value || 'balanced';
}

function compareBasisLabel(basis = comparePointsBasis()) {
    if (basis === 'projected') return 'Projected';
    if (basis === 'risk_adjusted') return 'Risk-adj';
    return 'Balanced';
}

function formatComparePts(value) {
    return (typeof value === 'number' && Number.isFinite(value)) ? value.toFixed(1) : '0.0';
}

function comparePickBreakdown(item, type) {
    if (!item) return '';
    const parts = [];
    if (typeof item.expected_points_quali === 'number') parts.push(`Q ${formatComparePts(item.expected_points_quali)}`);
    if (typeof item.expected_points_race === 'number') parts.push(`R ${formatComparePts(item.expected_points_race)}`);
    if (type === 'driver' && typeof item.expected_points_sprint_race === 'number') {
        parts.push(`S ${formatComparePts(item.expected_points_sprint_race)}`);
    }
    if (type === 'constructor' && typeof item.expected_pit_stop_pts === 'number') {
        parts.push(`Pit ${formatComparePts(item.expected_pit_stop_pts)}`);
    }
    return parts.join(' / ');
}

function comparePickPointsHtml(item, type, basis = comparePointsBasis()) {
    const points = basisPointsFor(item, basis);
    const breakdown = comparePickBreakdown(item, type);
    const label = compareBasisLabel(basis);
    return `<div class="slot-points">${formatComparePts(points)} pts <span>${label}</span></div>
        ${breakdown ? `<div class="slot-breakdown">${breakdown}</div>` : ''}`;
}

function compareResultPickRow(item, type, score, chip) {
    const name = type === 'driver'
        ? item.name.split(' ').pop()
        : (item.name || item.constructor_id).toUpperCase();
    const base = adjustedBasisPoints(item, chip);
    let multiplier = 1;
    if (type === 'driver' && item.driver_id === score.boostedDriverId) {
        multiplier = chip === '3x_boost' ? 3 : 2;
    } else if (type === 'driver' && item.driver_id === score.secondBoostedDriverId) {
        multiplier = 2;
    }
    const total = base * multiplier;
    const multiplierHtml = multiplier > 1 ? `<span class="team-compare-multiplier">x${multiplier}</span>` : '';
    const breakdown = comparePickBreakdown(item, type);
    return `<div class="team-compare-pick-row">
        <span>${name}${multiplierHtml}</span>
        <strong>${formatComparePts(total)} pts</strong>
        ${breakdown ? `<em>${breakdown}</em>` : ''}
    </div>`;
}

function renderTeamCompareGrid() {
    if (!data) return;
    const grid = document.getElementById('teamCompareGrid');
    if (!grid) return;
    const budget = getCompareBudget();
    const chip = document.getElementById('compareChip')?.value || 'none';
    const basis = comparePointsBasis();

    grid.innerHTML = compareTeams.map((teamState, teamIdx) => {
        const budgetSummary = compareTeamBudgetSummary(teamState, budget);
        const budgetClass = budgetSummary.overBudget && chip !== 'limitless' ? ' over-budget' : '';
        const budgetText = budgetSummary.bank >= 0
            ? `$${budgetSummary.bank.toFixed(1)}M left`
            : `$${Math.abs(budgetSummary.bank).toFixed(1)}M over`;
        const chipNote = chip === 'limitless' ? '<span>Limitless ignores cap</span>' : '';
        let slots = '';
        for (let i = 0; i < 5; i++) {
            const did = teamState.drivers[i];
            const driver = did ? data.drivers.find(d => d.driver_id === did) : null;
            if (driver) {
                const team = TEAMS[driver.constructor] || { color: '#666' };
                slots += `<div class="my-team-slot filled compare-slot" style="--team-color:${team.color}" data-team="${teamIdx}" data-slot="driver" data-index="${i}">
                    <div class="slot-label">Driver ${i + 1}</div>
                    <div class="slot-name">${driver.name.split(' ').pop()}</div>
                    <div class="slot-price">$${driver.current_price.toFixed(1)}M</div>
                    ${comparePickPointsHtml(driver, 'driver', basis)}
                    <span class="slot-remove" data-team="${teamIdx}" data-slot="driver" data-index="${i}">&times;</span>
                </div>`;
            } else {
                slots += `<div class="my-team-slot compare-slot" data-team="${teamIdx}" data-slot="driver" data-index="${i}">
                    <div class="slot-label">Driver ${i + 1}</div>
                    <div class="slot-name" style="color:var(--text-secondary)">+ Select</div>
                </div>`;
            }
        }
        for (let i = 0; i < 2; i++) {
            const cid = teamState.constructors[i];
            const con = cid ? data.constructors.find(c => c.constructor_id === cid) : null;
            if (con) {
                const team = TEAMS[con.constructor_id] || { color: '#666' };
                slots += `<div class="my-team-slot filled compare-slot" style="--team-color:${team.color}" data-team="${teamIdx}" data-slot="constructor" data-index="${i}">
                    <div class="slot-label">Constructor ${i + 1}</div>
                    <div class="slot-name">${(con.name || con.constructor_id).toUpperCase()}</div>
                    <div class="slot-price">$${con.current_price.toFixed(1)}M</div>
                    ${comparePickPointsHtml(con, 'constructor', basis)}
                    <span class="slot-remove" data-team="${teamIdx}" data-slot="constructor" data-index="${i}">&times;</span>
                </div>`;
            } else {
                slots += `<div class="my-team-slot compare-slot" data-team="${teamIdx}" data-slot="constructor" data-index="${i}">
                    <div class="slot-label">Constructor ${i + 1}</div>
                    <div class="slot-name" style="color:var(--text-secondary)">+ Select</div>
                </div>`;
            }
        }
        return `<div class="team-compare-editor">
            <div class="team-compare-editor-header">
                <h4>${teamState.name}</h4>
                <div class="team-compare-copy-help">
                    <button type="button" class="team-compare-mini-btn" data-copy-current="${teamIdx}" title="Copy the lineup already entered in My Team / Transfer Advisor into this comparison slot." aria-describedby="copyCurrentHint-${teamIdx}" aria-label="Use the current Transfer Advisor team for ${teamState.name}">Use Current <span aria-hidden="true" class="team-compare-hint-dot">?</span></button>
                    <span class="team-compare-tooltip" id="copyCurrentHint-${teamIdx}" role="tooltip">Copies your current My Team / Transfer Advisor picks into this slot: 5 drivers and 2 constructors. It does not optimize, change budget, or affect the other compare teams.</span>
                </div>
            </div>
            <div class="team-compare-budget${budgetClass}">
                <span>${budgetSummary.picked}/7 picked</span>
                <strong>$${budgetSummary.cost.toFixed(1)}M spent</strong>
                <em>${budgetText}</em>
                ${chipNote}
            </div>
            <div class="team-compare-slots">${slots}</div>
        </div>`;
    }).join('');

    grid.querySelectorAll('.compare-slot').forEach(slot => {
        slot.addEventListener('click', (e) => {
            const teamIdx = parseInt(slot.dataset.team);
            const type = slot.dataset.slot;
            const idx = parseInt(slot.dataset.index);
            if (e.target.classList.contains('slot-remove')) {
                if (type === 'driver') compareTeams[teamIdx].drivers[idx] = null;
                else compareTeams[teamIdx].constructors[idx] = null;
                renderTeamCompareGrid();
                return;
            }
            slotPickerTarget = 'compareTeam';
            slotPickerCompareIndex = teamIdx;
            showSlotPicker(type, idx);
        });
    });

    grid.querySelectorAll('[data-copy-current]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const teamIdx = parseInt(e.currentTarget.dataset.copyCurrent);
            compareTeams[teamIdx].drivers = [...myTeamDrivers];
            compareTeams[teamIdx].constructors = [...myTeamConstructors];
            renderTeamCompareGrid();
        });
    });
}

function compareTeamObjects(teamState, view) {
    const drivers = teamState.drivers
        .map(id => view.drivers.find(d => d.driver_id === id))
        .filter(Boolean);
    const constructorsList = teamState.constructors
        .map(id => view.constructors.find(c => c.constructor_id === id))
        .filter(Boolean);
    return { drivers, constructorsList };
}

function analyzeCompareTeam(teamState, view, budget, chip) {
    const { drivers, constructorsList } = compareTeamObjects(teamState, view);
    const complete = drivers.length === 5 && constructorsList.length === 2;
    if (!complete) {
        return {
            name: teamState.name,
            complete: false,
            filled: drivers.length + constructorsList.length,
            drivers,
            constructors: constructorsList,
        };
    }

    const score = scoreTeamPicks(drivers, constructorsList, chip);
    const picks = [...drivers, ...constructorsList];
    const cost = picks.reduce((s, p) => s + (p.current_price || 0), 0);
    const expGain = picks.reduce((s, p) => s + predictPriceChange(p, p.expected_points).expectedChange, 0);
    const avgConfidence = drivers.reduce((s, d) => s + (d.confidence || 0), 0) / drivers.length;
    const riskPicks = picks.filter(p => p.risk === 'HIGH' || p.risk === 'VERY HIGH');
    const avgDnf = drivers.reduce((s, d) => s + (d.dnf_probability || 0), 0) / drivers.length;
    const volatility = score.ceiling - score.floor;
    const ppm = cost > 0 ? score.expected / cost : 0;
    const biggestDownside = [...drivers].sort((a, b) =>
        (intervalPoints(b, 'mean', chip) - intervalPoints(b, 'p5', chip)) -
        (intervalPoints(a, 'mean', chip) - intervalPoints(a, 'p5', chip)))[0];
    const boosted = drivers.find(d => d.driver_id === score.boostedDriverId);
    const secondBoosted = score.secondBoostedDriverId ? drivers.find(d => d.driver_id === score.secondBoostedDriverId) : null;

    return {
        name: teamState.name,
        complete: true,
        drivers,
        constructors: constructorsList,
        cost,
        bank: budget - cost,
        overBudget: chip !== 'limitless' && cost > budget,
        expected: score.expected,
        floor: score.floor,
        ceiling: score.ceiling,
        volatility,
        expGain,
        ppm,
        avgConfidence,
        avgDnf,
        riskCount: riskPicks.length,
        biggestDownside,
        boostedDriverId: score.boostedDriverId,
        secondBoostedDriverId: score.secondBoostedDriverId,
        boosted,
        secondBoosted,
    };
}

function runTeamCompare() {
    if (!data) return;
    optimizeBasis = document.getElementById('pointsBasisCompare')?.value || 'balanced';
    const chip = document.getElementById('compareChip')?.value || 'none';
    const budget = parseFloat(document.getElementById('compareBudget')?.value || '100');
    const view = getScenarioView();
    const results = compareTeams.map(t => analyzeCompareTeam(t, view, budget, chip));
    const complete = results.filter(r => r.complete);
    const resultEl = document.getElementById('teamCompareResult');
    if (!resultEl) return;

    resultEl.classList.remove('hidden');
    if (complete.length === 0) {
        resultEl.innerHTML = `${scenarioBannerHtml()}<div class="optimizer-warning">Select at least one complete team to compare.</div>`;
        return;
    }

    const bestExpected = Math.max(...complete.map(r => r.expected));
    const bestFloor = Math.max(...complete.map(r => r.floor));
    const bestGain = Math.max(...complete.map(r => r.expGain));
    const lowestVol = Math.min(...complete.map(r => r.volatility));

    const cards = results.map(r => {
        if (!r.complete) {
            return `<div class="team-compare-card incomplete">
                <div class="team-compare-card-head"><h4>${r.name}</h4><span>${r.filled}/7 picked</span></div>
                <p class="hint">Complete all 5 drivers and 2 constructors to score this team.</p>
            </div>`;
        }
        const gainColor = r.expGain >= 0 ? 'var(--green)' : 'var(--red, #ef4444)';
        const bankColor = r.overBudget ? 'var(--red, #ef4444)' : 'var(--text)';
        const badges = [
            r.expected === bestExpected ? '<span class="compare-badge">Top score</span>' : '',
            r.floor === bestFloor ? '<span class="compare-badge">Best floor</span>' : '',
            r.expGain === bestGain ? '<span class="compare-badge">Best budget gain</span>' : '',
            r.volatility === lowestVol ? '<span class="compare-badge">Steadiest</span>' : '',
        ].join('');
        const boostText = r.secondBoosted
            ? `3x ${r.boosted.name.split(' ').pop()} + 2x ${r.secondBoosted.name.split(' ').pop()}`
            : `2x ${r.boosted ? r.boosted.name.split(' ').pop() : '?'}`;
        const downsideText = r.biggestDownside
            ? `${r.biggestDownside.name.split(' ').pop()} widest driver downside`
            : 'No downside signal';
        const pickRows = [
            ...r.drivers.map(d => compareResultPickRow(d, 'driver', r, chip)),
            ...r.constructors.map(c => compareResultPickRow(c, 'constructor', r, chip)),
        ].join('');
        return `<div class="team-compare-card ${r.overBudget ? 'over-budget' : ''}">
            <div class="team-compare-card-head">
                <h4>${r.name}</h4>
                <div class="compare-badges">${badges}</div>
            </div>
            <div class="team-compare-main">
                <div>
                    <div class="compare-big">${r.expected.toFixed(1)}</div>
                    <div class="compare-label" title="${boostText}">Expected pts</div>
                </div>
                <div>
                    <div class="compare-big muted">$${r.cost.toFixed(1)}M</div>
                    <div class="compare-label" style="color:${bankColor}">${r.bank >= 0 ? `$${r.bank.toFixed(1)}M left` : `$${Math.abs(r.bank).toFixed(1)}M over`}</div>
                </div>
            </div>
            <div class="team-compare-metrics">
                <div><span>90% floor</span><strong>${r.floor.toFixed(1)}</strong></div>
                <div><span>90% ceiling</span><strong>${r.ceiling.toFixed(1)}</strong></div>
                <div><span>Range</span><strong>${r.volatility.toFixed(1)}</strong></div>
                <div><span>PPM</span><strong>${r.ppm.toFixed(2)}</strong></div>
                <div><span>Exp budget</span><strong style="color:${gainColor}">${r.expGain >= 0 ? '+' : ''}${r.expGain.toFixed(1)}M</strong></div>
                <div><span>Avg conf</span><strong>${r.avgConfidence.toFixed(0)}%</strong></div>
                <div><span>Risk picks</span><strong>${r.riskCount}</strong></div>
                <div><span>Avg DNF</span><strong>${(r.avgDnf * 100).toFixed(1)}%</strong></div>
            </div>
            <div class="team-compare-pick-list" aria-label="${r.name} points breakdown">
                <div class="team-compare-pick-list-title">${compareBasisLabel(optimizeBasis)} contribution</div>
                ${pickRows}
            </div>
            <div class="team-compare-roster">
                <div>${downsideText}</div>
            </div>
        </div>`;
    }).join('');

    resultEl.innerHTML = `${scenarioBannerHtml()}<div class="team-compare-cards">${cards}</div>`;
    resultEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function showSlotPicker(type, index) {
    const isTarget = slotPickerTarget === 'targetTeam';
    const isCompare = slotPickerTarget === 'compareTeam';
    const compareState = compareTeams[slotPickerCompareIndex] || compareTeams[0];
    const driverArr = isCompare ? compareState.drivers : isTarget ? targetTeamDrivers : myTeamDrivers;
    const consArr = isCompare ? compareState.constructors : isTarget ? targetTeamConstructors : myTeamConstructors;

    const alreadySelected = type === 'driver'
        ? new Set(driverArr.filter(Boolean))
        : new Set(consArr.filter(Boolean));

    const items = type === 'driver' ? data.drivers : data.constructors;
    const compareBaseCost = isCompare ? compareTeamCost(compareState, { type, index }) : 0;
    const compareBudget = getCompareBudget();

    const overlay = document.createElement('div');
    overlay.className = 'slot-picker-overlay';
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.remove();
    });

    let html = `<div class="slot-picker"><h4>Select ${type === 'driver' ? 'Driver' : 'Constructor'}</h4>`;
    items.forEach(item => {
        const id = type === 'driver' ? item.driver_id : item.constructor_id;
        const team = TEAMS[type === 'driver' ? item.constructor : item.constructor_id] || { color: '#666' };
        const name = type === 'driver' ? item.name : (item.name || item.constructor_id).toUpperCase();
        const disabled = alreadySelected.has(id) ? ' disabled' : '';
        const price = item.current_price || 0;
        const compareBank = compareBudget - compareBaseCost - price;
        const compareBudgetHtml = isCompare
            ? `<span class="sp-bank${compareBank < -0.0001 ? ' over-budget' : ''}">${compareBank >= 0 ? `Leaves $${compareBank.toFixed(1)}M` : `$${Math.abs(compareBank).toFixed(1)}M over`}</span>`
            : '';
        html += `<div class="slot-picker-item${disabled}" data-id="${id}">
            <span class="sp-dot" style="background:${team.color}"></span>
            <span class="sp-name">${name}</span>
            <span class="sp-price">$${price.toFixed(1)}M</span>
            ${compareBudgetHtml}
        </div>`;
    });
    html += '</div>';
    overlay.innerHTML = html;
    document.body.appendChild(overlay);

    overlay.querySelectorAll('.slot-picker-item:not(.disabled)').forEach(el => {
        el.addEventListener('click', () => {
            const id = el.dataset.id;
            if (type === 'driver') driverArr[index] = id;
            else consArr[index] = id;
            overlay.remove();
            if (isCompare) renderTeamCompareGrid();
            else if (isTarget) renderTargetTeamGrid();
            else renderMyTeamGrid();
        });
    });
}

// ============================================================
// Target Team Grid (Multi-Week Planner target mode)
// ============================================================

function renderTargetTeamGrid() {
    if (!data) return;
    const grid = document.getElementById('myTeamGridTarget');
    if (!grid) return;

    let html = '';
    // 5 driver slots
    for (let i = 0; i < 5; i++) {
        const did = targetTeamDrivers[i];
        const driver = did ? data.drivers.find(d => d.driver_id === did) : null;
        if (driver) {
            const team = TEAMS[driver.constructor] || { color: '#666' };
            html += `<div class="my-team-slot filled" style="--team-color:${team.color}" data-slot="driver" data-index="${i}">
                <div class="slot-label">Driver ${i + 1}</div>
                <div class="slot-name">${driver.name.split(' ').pop()}</div>
                <div class="slot-price">$${driver.current_price.toFixed(1)}M</div>
                <span class="slot-remove" data-slot="driver" data-index="${i}">&times;</span>
            </div>`;
        } else {
            html += `<div class="my-team-slot" data-slot="driver" data-index="${i}">
                <div class="slot-label">Driver ${i + 1}</div>
                <div class="slot-name" style="color:var(--text-secondary)">+ Select</div>
            </div>`;
        }
    }
    // 2 constructor slots
    for (let i = 0; i < 2; i++) {
        const cid = targetTeamConstructors[i];
        const con = cid ? data.constructors.find(c => c.constructor_id === cid) : null;
        if (con) {
            const team = TEAMS[con.constructor_id] || { color: '#666' };
            html += `<div class="my-team-slot filled" style="--team-color:${team.color}" data-slot="constructor" data-index="${i}">
                <div class="slot-label">Constructor ${i + 1}</div>
                <div class="slot-name">${(con.name || con.constructor_id).toUpperCase()}</div>
                <div class="slot-price">$${con.current_price.toFixed(1)}M</div>
                <span class="slot-remove" data-slot="constructor" data-index="${i}">&times;</span>
            </div>`;
        } else {
            html += `<div class="my-team-slot" data-slot="constructor" data-index="${i}">
                <div class="slot-label">Constructor ${i + 1}</div>
                <div class="slot-name" style="color:var(--text-secondary)">+ Select</div>
            </div>`;
        }
    }
    grid.innerHTML = html;

    // Attach handlers
    attachTargetGridHandlers(grid);
}

function attachTargetGridHandlers(gridEl) {
    gridEl.querySelectorAll('.my-team-slot').forEach(slot => {
        slot.addEventListener('click', (e) => {
            if (e.target.classList.contains('slot-remove')) {
                const type = e.target.dataset.slot;
                const idx = parseInt(e.target.dataset.index);
                if (type === 'driver') targetTeamDrivers[idx] = null;
                else targetTeamConstructors[idx] = null;
                renderTargetTeamGrid();
                return;
            }
            const type = slot.dataset.slot;
            const idx = parseInt(slot.dataset.index);
            slotPickerTarget = 'targetTeam';
            showSlotPicker(type, idx);
        });
    });
}

// ============================================================
// Transfer Advisor
// ============================================================

function runTransferAdvisor() {
    if (!data) return;

    const budget = parseFloat(document.getElementById('transferBudget').value);
    const freeTransfers = parseInt(document.getElementById('freeTransfers').value) || 0;
    const strategy = document.getElementById('transferStrategy').value;
    const chip = document.getElementById('transferChip').value;
    const transferPointsBasis = document.getElementById('pointsBasisTransfer')?.value || 'balanced';
    optimizeBasis = transferPointsBasis;

    // Validate team
    const currentDriverIds = myTeamDrivers.filter(Boolean);
    const currentConstructorIds = myTeamConstructors.filter(Boolean);
    if (currentDriverIds.length < 5 || currentConstructorIds.length < 2) {
        alert('Please select your full current team (5 drivers + 2 constructors) before running the transfer advisor.');
        return;
    }

    const isWildcard = chip === 'wild_card';
    const maxExtraTransfers = parseInt(document.getElementById('maxExtraTransfers').value) || 0;
    const showWildcardHint = maxExtraTransfers >= 3 && !isWildcard;
    const maxTransfers = isWildcard ? 7 : freeTransfers + maxExtraTransfers; // Wildcard = unlimited
    const transferPenalty = TA_TUNABLES.transferPenalty; // -10 pts per extra transfer

    withLoadingButton('runTransferAdvisor', 'Find Best Transfers', () => {

    // Score function
    function score(item) {
        if (strategy === 'max_points') return basisPoints(item);
        if (strategy === 'max_value') return basisValue(item);
        if (strategy === 'budget_gain') {
            const pc = predictPriceChange(item, item.expected_points);
            return pc.expectedChange * 100 + basisValue(item) * 5;
        }
        return basisPoints(item) * 0.6 + basisValue(item) * 10 * 0.4;
    }

    // Apply chip modifiers to scoring
    // With 3x_boost: boostedId gets 3x, secondBoostedId gets 2x
    // Without: boostedId gets 2x
    function chipAdjustedPoints(picks, boostedId, secondBoostedId) {
        let total = 0;
        for (const p of picks) {
            let pts = basisPoints(p);
            if (chip === 'no_negative' && pts < 0) pts = 0;
            if (p.driver_id === boostedId) {
                pts *= (chip === '3x_boost' ? 3 : 2);
            } else if (p.driver_id === secondBoostedId) {
                pts *= 2;
            }
            total += pts;
        }
        return total;
    }

    // Scenario-aware view (see runOptimizerSync for rationale).
    const view = getScenarioView();
    const allDrivers = view.drivers.filter(d => !excludedDrivers.has(d.driver_id));
    const allConstructors = view.constructors.filter(c => !excludedConstructors.has(c.constructor_id));

    const numDriverSlots = 5;
    const effectiveBudget = chip === 'limitless' ? 999 : budget;

    // Generate all valid lineups and score them, tracking transfers needed
    const results = [];
    const MAX_RESULTS = TA_TUNABLES.maxResults;

    // ---- Explicit "keep current team" baseline ----
    // We compute and push the current team entry FIRST so it reliably exists
    // as the comparison baseline in the later filter step. Relying on the
    // combinatorial search to regenerate the exact current team is fragile:
    // it can be skipped by the MAX_ITERATIONS cap, or excluded entirely if
    // any current pick is in the excluded set. Without this explicit entry,
    // the filter falls back to -Infinity and every bad transfer passes.
    // Look up driver/constructor objects from full `data` (not `allDrivers`/
    // `allConstructors`) so excluded current picks still count for baseline.
    const currentDriverObjs = currentDriverIds
        .map(id => data.drivers.find(d => d.driver_id === id))
        .filter(Boolean);
    const currentConstructorObjs = currentConstructorIds
        .map(id => data.constructors.find(c => c.constructor_id === id))
        .filter(Boolean);
    if (currentDriverObjs.length === currentDriverIds.length &&
        currentConstructorObjs.length === currentConstructorIds.length) {
        const currentSorted = [...currentDriverObjs].sort((a, b) => basisPoints(b) - basisPoints(a));
        const curBoosted = currentSorted[0];
        const curSecondBoosted = (chip === '3x_boost' && currentSorted.length > 1) ? currentSorted[1] : null;
        const curAllPicks = [...currentDriverObjs, ...currentConstructorObjs];
        const curTotalPoints = chipAdjustedPoints(curAllPicks, curBoosted.driver_id, curSecondBoosted ? curSecondBoosted.driver_id : null);
        const curTotalCost = curAllPicks.reduce((s, x) => s + x.current_price, 0);
        // Strategy-aware lineup-level score (chip-adjusted via curTotalPoints)
        const curFinalScore = lineupScore(strategy, curTotalPoints, curTotalCost, currentDriverObjs, currentConstructorObjs);
        results.push({
            drivers: currentDriverObjs,
            constructors: currentConstructorObjs,
            totalCost: curTotalCost,
            totalPoints: curTotalPoints,
            netPoints: curTotalPoints, // zero transfers = zero penalty
            transfersNeeded: 0,
            extraTransfers: 0,
            penalty: 0,
            boostedDriverId: curBoosted.driver_id,
            secondBoostedDriverId: curSecondBoosted ? curSecondBoosted.driver_id : null,
            pointsBasis: transferPointsBasis,
            totalScore: curFinalScore,
        });
    }

    // Generate constructor pairs (respecting locked constructors)
    const cPairs = [];
    for (let i = 0; i < allConstructors.length; i++) {
        for (let j = i + 1; j < allConstructors.length; j++) {
            if (lockedConstructors.size > 0) {
                const pair = new Set([allConstructors[i].constructor_id, allConstructors[j].constructor_id]);
                let valid = true;
                for (const lc of lockedConstructors) {
                    if (!pair.has(lc)) { valid = false; break; }
                }
                if (!valid) continue;
            }
            cPairs.push({
                items: [allConstructors[i], allConstructors[j]],
                cost: allConstructors[i].current_price + allConstructors[j].current_price,
            });
        }
    }

    // Pre-filter locked drivers — they must always be in the lineup
    const lockedDriverList = allDrivers.filter(d => lockedDrivers.has(d.driver_id));
    const lockedDriverIds = new Set(lockedDriverList.map(d => d.driver_id));
    const neededDrivers = numDriverSlots - lockedDriverList.length;
    const lockedDriverCost = lockedDriverList.reduce((s, d) => s + d.current_price, 0);

    if (neededDrivers < 0) {
        alert(`You have locked more than ${numDriverSlots} drivers. Please unlock some.`);
        return;
    }

    // Free pool = UNION of (top-N by strategy score) ∪ (top-M by PPM) ∪
    // (K cheapest), PLUS the user's current drivers. The PPM and cheapest
    // sub-pools fix the old FREE_POOL=15 gap: a cheap low-points enabler (one
    // you'd transfer in purely to free budget for a star) was invisible to a
    // pure score-ranked pool under the max_points strategy. Always include
    // current drivers so "keep most of current team" recommendations remain
    // reachable. Locked drivers are already excluded.
    let freeBase = allDrivers.filter(d => !lockedDriverIds.has(d.driver_id));
    freeBase.forEach(d => { d._score = score(d); });

    const byScore = [...freeBase].sort((a, b) => b._score - a._score)
        .slice(0, TA_TUNABLES.poolByScore);
    const byPpm = [...freeBase].sort((a, b) =>
            (b._score / (b.current_price || 1e-6)) - (a._score / (a.current_price || 1e-6)))
        .slice(0, TA_TUNABLES.poolByPpm);
    const byCheapest = [...freeBase].sort((a, b) => a.current_price - b.current_price)
        .slice(0, TA_TUNABLES.poolByCheapest);

    const poolIds = new Set();
    const augmented = [];
    for (const d of [...byScore, ...byPpm, ...byCheapest]) {
        if (!poolIds.has(d.driver_id)) { poolIds.add(d.driver_id); augmented.push(d); }
    }
    // Always include current drivers (not locked, not excluded) so the search
    // can hold them.
    for (const did of currentDriverIds) {
        if (!poolIds.has(did) && !lockedDriverIds.has(did) && !excludedDrivers.has(did)) {
            const d = freeBase.find(x => x.driver_id === did);
            if (d) { poolIds.add(did); augmented.push(d); }
        }
    }
    // Re-sort by current_price ascending (prerequisite for branch-and-bound).
    const freeDriverPool = augmented.sort((a, b) => a.current_price - b.current_price);
    const priceSum = [0];
    for (const d of freeDriverPool) priceSum.push(priceSum[priceSum.length - 1] + d.current_price);

    // Safety cap kept as a backstop; with pruning + top-N this is rarely hit.
    const MAX_ITERATIONS = TA_TUNABLES.maxIterations;
    let iterations = 0;
    let hitCap = false;

    function emitLineup(cp, conTransfers, combo, comboCost) {
        if (++iterations > MAX_ITERATIONS) { hitCap = true; return; }

        const allDriversInLineup = [...lockedDriverList, ...combo];
        const totalCost = cp.cost + lockedDriverCost + comboCost;

        // Count transfers needed
        const newDriverIds = new Set(allDriversInLineup.map(d => d.driver_id));
        let transfersNeeded = conTransfers;
        for (const did of currentDriverIds) {
            if (!newDriverIds.has(did)) transfersNeeded++;
        }
        if (!isWildcard && transfersNeeded > maxTransfers) return;

        // Find best boost drivers (sorted by the active points basis)
        const sortedCombo = [...allDriversInLineup].sort((a, b) => basisPoints(b) - basisPoints(a));
        const boostedDriver = sortedCombo[0];
        const secondBoostedDriver = (chip === '3x_boost' && sortedCombo.length > 1) ? sortedCombo[1] : null;

        const allPicks = [...allDriversInLineup, ...cp.items];
        const totalPoints = chipAdjustedPoints(allPicks, boostedDriver.driver_id, secondBoostedDriver ? secondBoostedDriver.driver_id : null);

        const extraTransfers = Math.max(0, transfersNeeded - freeTransfers);
        const penalty = isWildcard ? 0 : extraTransfers * transferPenalty;
        const netPoints = totalPoints - penalty;

        const lineupVal = lineupScore(strategy, totalPoints, totalCost, allDriversInLineup, cp.items);
        const finalScore = lineupVal - penalty;

        results.push({
            drivers: allDriversInLineup,
            constructors: cp.items,
            totalCost,
            totalPoints,
            netPoints,
            transfersNeeded,
            extraTransfers,
            penalty,
            boostedDriverId: boostedDriver.driver_id,
            secondBoostedDriverId: secondBoostedDriver ? secondBoostedDriver.driver_id : null,
            pointsBasis: transferPointsBasis,
            totalScore: finalScore,
        });
    }

    for (const cp of cPairs) {
        if (hitCap) break;
        const newConIds = new Set(cp.items.map(c => c.constructor_id));
        let conTransfers = 0;
        for (const cid of currentConstructorIds) {
            if (!newConIds.has(cid)) conTransfers++;
        }
        if (!isWildcard && conTransfers > maxTransfers) continue;

        const remainBudget = effectiveBudget - cp.cost - lockedDriverCost;
        if (remainBudget < 0) continue;

        if (neededDrivers === 0) {
            emitLineup(cp, conTransfers, [], 0);
        } else {
            searchCombosWithPruning(
                freeDriverPool, priceSum, neededDrivers, remainBudget,
                (combo, comboCost) => emitLineup(cp, conTransfers, combo, comboCost),
            );
            if (hitCap) break;
        }
    }

    // Sort by score
    results.sort((a, b) => b.totalScore - a.totalScore);

    // Deduplicate
    const seen = new Set();
    const unique = results.filter(l => {
        const key = [...l.drivers.map(d => d.driver_id).sort(), ...l.constructors.map(c => c.constructor_id).sort()].join(',');
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
    });

    // Filter out pointless transfers: find the "keep current team" score and remove results that are worse or equal
    const keepCurrentResult = unique.find(l => l.transfersNeeded === 0);
    const keepCurrentPoints = keepCurrentResult ? keepCurrentResult.netPoints : -Infinity;
    const filtered = unique.filter(l => {
        // Always keep the "no transfers" option
        if (l.transfersNeeded === 0) return true;
        // Filter out lineups that don't improve on keeping current team
        return l.netPoints > keepCurrentPoints;
    });

    // Take top results
    allLineups = filtered.slice(0, MAX_RESULTS);

    // If the best option is "keep current team", highlight it
    if (allLineups.length > 0 && allLineups[0].transfersNeeded === 0) {
        allLineups[0]._isKeepCurrent = true;
    }

    if (allLineups.length === 0) {
        const resultEl = document.getElementById('optimizerResult');
        resultEl.classList.remove('hidden');
        document.getElementById('lineupSummary').innerHTML = '';
        document.getElementById('lineupCards').innerHTML = `
            <div class="optimizer-warning" style="background:var(--card);border:2px solid var(--orange, #f59e0b);border-radius:10px;padding:20px;text-align:center;">
                <h3 style="color:var(--orange, #f59e0b);margin-bottom:8px;">No Valid Transfers Found</h3>
                <p style="color:var(--text-secondary);">No lineup improvements found within budget and transfer constraints.</p>
            </div>`;
        document.getElementById('lineupLoadMore').classList.add('hidden');
        resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return;
    }

    lineupsShown = 0;
    displayTransferResults(strategy, chip, showWildcardHint);

    });  // close withLoadingButton
}

function displayTransferResults(strategy, chip, showWildcardHint) {
    const resultEl = document.getElementById('optimizerResult');
    resultEl.classList.remove('hidden');

    // Scenario banner (only when bumps active)
    const banner = scenarioBannerHtml();
    let bannerEl = resultEl.querySelector('.scenario-active-banner');
    if (bannerEl) bannerEl.remove();
    if (banner) {
        const summaryEl = document.getElementById('lineupSummary');
        summaryEl.insertAdjacentHTML('beforebegin', banner);
    }

    const total = allLineups.length;
    const end = Math.min(lineupsShown + LINEUPS_PER_PAGE, total);

    if (lineupsShown === 0) {
        const best = allLineups[0];
        const chipLabel = chip !== 'none' ? ` <span class="chip-badge">${chip.replace('_', ' ').toUpperCase()}</span>` : '';

        document.getElementById('lineupSummary').innerHTML = `
            <div class="lineup-stat">
                <div class="big-num">${best.netPoints.toFixed(1)}</div>
                <div class="label">Net Points${best.penalty > 0 ? ` (-${best.penalty} penalty)` : ''}</div>
            </div>
            <div class="lineup-stat">
                <div class="big-num">${best.transfersNeeded}</div>
                <div class="label">Transfers${chipLabel}</div>
            </div>
            <div class="lineup-stat">
                <div class="big-num">$${best.totalCost.toFixed(1)}M</div>
                <div class="label">Total Cost</div>
            </div>
            <div class="lineup-stat">
                <div class="big-num">${best.totalPoints.toFixed(1)}</div>
                <div class="label">Gross Points (incl boost)</div>
            </div>
        `;
        const hintHtml = showWildcardHint
            ? `<div class="optimizer-hint" style="grid-column:1/-1;background:rgba(245,158,11,0.08);border:1px solid var(--orange,#f59e0b);border-radius:8px;padding:10px 14px;font-size:13px;color:var(--text-secondary);">Tip: Wild Card chip gives unlimited free transfers — consider it instead of taking penalties for 3+ extra transfers.</div>`
            : '';
        document.getElementById('lineupCards').innerHTML = hintHtml;
        document.getElementById('lineupCounter').textContent = `${total} option${total !== 1 ? 's' : ''} found`;
    }

    // Build transfer diff cards
    let html = '';
    for (let li = lineupsShown; li < end; li++) {
        const lineup = allLineups[li];
        html += renderTransferCard(lineup, li, chip);
    }

    document.getElementById('lineupCards').insertAdjacentHTML('beforeend', html);
    lineupsShown = end;

    const loadMoreEl = document.getElementById('lineupLoadMore');
    if (lineupsShown < total) {
        loadMoreEl.classList.remove('hidden');
        loadMoreEl.querySelector('.load-more-text').textContent = `Show more (${lineupsShown}/${total})`;
    } else {
        loadMoreEl.classList.add('hidden');
    }

    if (lineupsShown <= LINEUPS_PER_PAGE) {
        resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

function renderTransferCard(lineup, index, chip) {
    const currentDriverIds = myTeamDrivers.filter(Boolean);
    const currentConstructorIds = myTeamConstructors.filter(Boolean);
    const newDriverIds = lineup.drivers.map(d => d.driver_id);
    const newConIds = lineup.constructors.map(c => c.constructor_id);
    // Keep rendering tied to the basis used for this advisor run. Otherwise,
    // Load More can drift if another optimizer tool changes optimizeBasis.
    const pointsBasis = lineup.pointsBasis || optimizeBasis;
    const displayPoints = item => basisPointsFor(item, pointsBasis);

    // Build swaps
    const driversOut = currentDriverIds.filter(id => !newDriverIds.includes(id));
    const driversIn = newDriverIds.filter(id => !currentDriverIds.includes(id));
    const consOut = currentConstructorIds.filter(id => !newConIds.includes(id));
    const consIn = newConIds.filter(id => !currentConstructorIds.includes(id));

    const expandedClass = index === 0 ? ' expanded' : '';
    const optionLabel = lineup._isKeepCurrent ? 'Keep Current Team' : `Option #${index + 1}`;

    // Efficiency line: net-points gain over keeping the current team, and the
    // gain per transfer spent. This is the key judgement a manager makes when
    // deciding whether extra transfer hits are worth taking. Baseline = the
    // "keep current" lineup (always present in allLineups; transfersNeeded 0).
    let efficiencyHtml = '';
    if (lineup.transfersNeeded > 0) {
        const baseline = (typeof allLineups !== 'undefined' && allLineups)
            ? allLineups.find(l => l.transfersNeeded === 0) : null;
        if (baseline) {
            const gain = lineup.netPoints - baseline.netPoints;
            const perTransfer = gain / lineup.transfersNeeded;
            const gainColor = gain >= 0 ? 'var(--green)' : 'var(--red, #ef4444)';
            efficiencyHtml = `· <span style="color:${gainColor};font-weight:600;" title="Net points gained versus keeping your current team (after transfer penalties), and the gain per transfer used.">${gain >= 0 ? '+' : ''}${gain.toFixed(1)} vs hold · ${perTransfer >= 0 ? '+' : ''}${perTransfer.toFixed(1)}/transfer</span>`;
        }
    }
    let html = `<div class="lineup-block${expandedClass}" style="margin-bottom:16px;" onclick="this.classList.toggle('expanded')">
        <div class="lineup-block-header">
            <h4><span class="lineup-expand-icon">\u25BC</span> ${optionLabel}</h4>
            <span class="lineup-block-stats">
                ${lineup.netPoints.toFixed(1)} net pts \u00b7 ${lineup.transfersNeeded} transfer${lineup.transfersNeeded !== 1 ? 's' : ''}
                ${lineup.penalty > 0 ? ` · <span style="color:var(--red, #ef4444)">-${lineup.penalty} penalty</span>` : ''}
                · $${lineup.totalCost.toFixed(1)}M
                ${efficiencyHtml}
            </span>
        </div>
        <div class="lineup-details">`;

    // Show transfer swaps
    if (driversOut.length === 0 && consOut.length === 0) {
        html += '<p style="color:var(--green);font-weight:600;margin-bottom:12px;">No transfers needed — keep your current team!</p>';
    } else {
        // Pair out↔in deterministically by the selected basis (descending) so the
        // top-impact swap is shown first. The raw filter order is arbitrary,
        // which made multi-swap rows show nonsensical pairings.
        const sortByBasis = (a, b) => displayPoints(b) - displayPoints(a);
        const outDrivers = driversOut.map(id => data.drivers.find(d => d.driver_id === id)).filter(Boolean).sort(sortByBasis);
        const inDrivers  = driversIn.map(id => data.drivers.find(d => d.driver_id === id)).filter(Boolean).sort(sortByBasis);
        const outCons = consOut.map(id => data.constructors.find(c => c.constructor_id === id)).filter(Boolean).sort(sortByBasis);
        const inCons  = consIn.map(id => data.constructors.find(c => c.constructor_id === id)).filter(Boolean).sort(sortByBasis);

        html += '<div style="margin-bottom:12px;">';
        for (let i = 0; i < Math.max(outDrivers.length, inDrivers.length); i++) {
            html += renderSwapRow(outDrivers[i] || null, inDrivers[i] || null, 'driver', pointsBasis);
        }
        for (let i = 0; i < Math.max(outCons.length, inCons.length); i++) {
            html += renderSwapRow(outCons[i] || null, inCons[i] || null, 'constructor', pointsBasis);
        }
        html += '</div>';
    }

    // Show resulting lineup
    html += '<div class="lineup-picks-row">';
    const sorted = [...lineup.drivers].sort((a, b) => displayPoints(b) - displayPoints(a));
    sorted.forEach(d => {
        const team = TEAMS[d.constructor] || { color: '#666', name: d.constructor };
        const isPrimaryBoosted = d.driver_id === lineup.boostedDriverId;
        const isSecondBoosted = d.driver_id === (lineup.secondBoostedDriverId || null);
        const multiplier = (isPrimaryBoosted && chip === '3x_boost') ? 3 : (isPrimaryBoosted || isSecondBoosted) ? 2 : 1;
        const isBoosted = isPrimaryBoosted || isSecondBoosted;
        const displayPts = (displayPoints(d) * multiplier).toFixed(1);
        const boostBadge = isBoosted ? `<span class="boost-badge">${multiplier}x</span>` : '';
        const isNew = !currentDriverIds.includes(d.driver_id);
        html += `<div class="lineup-pick-h${isBoosted ? ' boosted' : ''}" style="--team-color:${team.color}">
            <div class="pick-h-header">
                <span class="pick-h-name">${d.name.split(' ').pop()}${isNew ? ' <span style="color:var(--green);font-size:0.7rem;">NEW</span>' : ''}</span>
                ${boostBadge}
            </div>
            <div class="pick-h-team">${team.name}</div>
            <div class="pick-h-pts">${displayPts}<span class="pick-h-pts-label"> pts</span></div>
            <div class="pick-h-meta">
                <span>$${d.current_price.toFixed(1)}M ${formatPriceChangeBadge(predictPriceChange(d, d.expected_points).expectedChange)}</span>
                <span>P${d.predicted_quali}\u2192P${d.predicted_finish}</span>
            </div>
        </div>`;
    });
    lineup.constructors.forEach(c => {
        const team = TEAMS[c.constructor_id] || { color: '#666', name: c.name };
        const isNew = !currentConstructorIds.includes(c.constructor_id);
        html += `<div class="lineup-pick-h constructor-pick-h" style="--team-color:${team.color}">
            <div class="pick-h-header">
                <span class="pick-h-name">${(c.name || c.constructor_id).toUpperCase()}${isNew ? ' <span style="color:var(--green);font-size:0.7rem;">NEW</span>' : ''}</span>
            </div>
            <div class="pick-h-team">${c.driver_1} & ${c.driver_2}</div>
            <div class="pick-h-pts">${displayPoints(c).toFixed(1)}<span class="pick-h-pts-label"> pts</span></div>
            <div class="pick-h-meta">
                <span>$${c.current_price.toFixed(1)}M ${formatPriceChangeBadge(predictPriceChange(c, c.expected_points).expectedChange)}</span>
            </div>
        </div>`;
    });
    html += '</div></div></div>';
    return html;
}

function renderSwapRow(outItem, inItem, type, pointsBasis = optimizeBasis) {
    const outName = outItem
        ? (type === 'driver' ? outItem.name.split(' ').pop() : (outItem.name || outItem.constructor_id).toUpperCase())
        : '—';
    const inName = inItem
        ? (type === 'driver' ? inItem.name.split(' ').pop() : (inItem.name || inItem.constructor_id).toUpperCase())
        : '—';
    const outPoints = outItem ? basisPointsFor(outItem, pointsBasis) : null;
    const inPoints = inItem ? basisPointsFor(inItem, pointsBasis) : null;
    const outPts = outItem ? outPoints.toFixed(1) : '—';
    const inPts = inItem ? inPoints.toFixed(1) : '—';
    const outPrice = outItem ? `$${outItem.current_price.toFixed(1)}M` : '';
    const inPrice = inItem ? `$${inItem.current_price.toFixed(1)}M` : '';

    // Price change for incoming player
    let inPriceChangeHtml = '';
    if (inItem) {
        const pc = predictPriceChange(inItem, inItem.expected_points);
        inPriceChangeHtml = formatPriceChangeBadge(pc.expectedChange);
    }

    // Net cost + points delta of THIS swap — the two numbers a manager weighs:
    // "does it free budget, and how many points does it add?" Net cost =
    // in price − out price (positive = costs money, negative = frees budget).
    let swapDeltaHtml = '';
    if (outItem && inItem) {
        const netCost = inItem.current_price - outItem.current_price;
        const ptsDelta = inPoints - outPoints;
        const costSign = netCost > 0 ? '+' : (netCost < 0 ? '−' : '');
        const costColor = netCost > 0 ? 'var(--red, #ef4444)' : (netCost < 0 ? 'var(--green)' : 'var(--text-secondary)');
        const ptsSign = ptsDelta >= 0 ? '+' : '';
        const ptsColor = ptsDelta >= 0 ? 'var(--green)' : 'var(--red, #ef4444)';
        swapDeltaHtml = `<div style="font-size:0.65rem;text-align:center;white-space:nowrap;line-height:1.3;">
            <span style="color:${ptsColor};font-weight:600;">${ptsSign}${ptsDelta.toFixed(1)}pts</span>
            <span style="color:${costColor};">${costSign}$${Math.abs(netCost).toFixed(1)}M</span>
        </div>`;
    }

    return `<div class="transfer-swap">
        <div class="transfer-out" style="flex:1">
            <div class="transfer-pick-name">${outName}</div>
            <div class="transfer-pick-detail">${outPts} pts · ${outPrice}</div>
        </div>
        <div class="transfer-arrow" style="display:flex;flex-direction:column;align-items:center;gap:2px;"><span>→</span>${swapDeltaHtml}</div>
        <div class="transfer-in" style="flex:1">
            <div class="transfer-pick-name">${inName} ${inPriceChangeHtml}</div>
            <div class="transfer-pick-detail">${inPts} pts · ${inPrice}</div>
        </div>
    </div>`;
}

function formatPriceChangeBadge(change) {
    if (change > 0) return `<span style="color:var(--green);font-size:0.75rem;font-weight:600;">\u2191 $${change.toFixed(1)}M</span>`;
    if (change < 0) return `<span style="color:var(--red, #ef4444);font-size:0.75rem;font-weight:600;">\u2193 $${Math.abs(change).toFixed(1)}M</span>`;
    return `<span style="color:var(--text-secondary);font-size:0.75rem;">\u2192 $0.0M</span>`;
}

// ============================================================
// Multi-Week Transfer Planner
// ============================================================

// P10: Centralised tunables. All numeric constants used by the multi-week
// planner live here so they can be reviewed, tweaked, and sensitivity-tested
// in one place. Behaviour notes per constant — modify with care, the planner
// is sensitive to relative weightings.
const MW_TUNABLES = {
    // --- Beam search ---
    beamWidth: 60,                  // # of states kept per round. Higher = more thorough but slower (quadratic-ish). Sweet spot 40-80.
    transferPenalty: 10,            // Points deducted per extra (non-banked) transfer. F1 Fantasy official rule = 10.
    maxBankedTransfers: 5,          // Max banked FT. F1 Fantasy official rule = 5.

    // --- Target team ---
    targetWeight: 30,               // Default points-per-off-target-pick penalty (final round). Overridden by intensity dropdown.
    targetIntensity: {              // Maps the Target Intensity dropdown to a TARGET_WEIGHT.
        loose:    10,               // Planner will trade target convergence for ~10 pts/pick.
        balanced: 30,               // Default — won't trade target for <30 pts/pick on final round.
        strict:   80,               // Forces convergence even at significant point cost.
    },

    // --- Candidate pool sizes (generateTransferCandidates) ---
    driverPoolByScore: 8,           // Top-N drivers by raw projected score for 2-swap exploration.
    driverPoolByPpm:   8,           // Top-N drivers by ppm (proj_score / current_price) — adds cheap high-PPM picks to enable budget-relief swaps.
    conPoolByScore:    4,           // Top-N constructors by raw projected score.
    conPoolByPpm:      3,           // Top-N constructors by ppm.

    // --- Wildcard optimiser ---
    wildcardFreePool: 15,           // Top-N drivers fed into the brute-force wildcard search.

    // --- Strategy weighting (beam-search ranking only, not displayed) ---
    budgetGainWeight: 50,           // priceGain * this — added to net points for the budget_gain strategy.
    balancedPointsWeight: 0.7,      // pts coefficient in balanced strategy
    balancedPpmWeight: 30,          // ppm coefficient in balanced strategy

    // --- PPM bracket thresholds (price-change estimation in beam score) ---
    ppmHighThreshold: 1.2,          // PPM ≥ this earns top tier price-gain credit.
    ppmMidThreshold: 0.9,           // PPM ≥ this earns middle tier.
    priceBracketSplit: 18.5,        // A-tier vs B-tier driver price cutoff (matches predictPriceChange brackets).

    // --- Affinity heuristic (computeAffinityWithConfidence) ---
    affinitySimilarityFloor: 0.5,   // Below this cosine sim, a historical race contributes 0 weight.
    affinityFullConfidence: 1.0,    // weightSum ≥ this → confidence = 1.0.
    affinityClampMin: 0.6,
    affinityClampMax: 1.4,
};

async function loadMultiWeekData() {
    if (!trackData) {
        try {
            const res = await fetch('data/track_data.json');
            trackData = await res.json();
        } catch (e) { console.warn('Failed to load track_data.json:', e); }
    }
    if (!driverHistory) {
        try {
            const res = await fetch('data/driver_history.json');
            driverHistory = await res.json();
        } catch (e) { console.warn('Failed to load driver_history.json:', e); }
    }
    // P9: ML-based future-round projections. Optional — falls back to the
    // track-similarity heuristic if the file is missing or stale.
    if (!horizonProjections) {
        try {
            const res = await fetch('data/horizon_projections.json');
            if (res.ok) {
                horizonProjections = await res.json();
            }
        } catch (e) { /* optional file — fail silently */ }
    }
}

function cosineSimilarity(a, b) {
    let dot = 0, magA = 0, magB = 0;
    for (let i = 0; i < a.length; i++) {
        dot += a[i] * b[i];
        magA += a[i] * a[i];
        magB += b[i] * b[i];
    }
    magA = Math.sqrt(magA);
    magB = Math.sqrt(magB);
    return (magA === 0 || magB === 0) ? 0 : dot / (magA * magB);
}

function getFeatureVector(circuitId) {
    if (!trackData || !trackData.track_features[circuitId]) return null;
    const feat = trackData.track_features[circuitId];
    return trackData.feature_names.map(k => feat[k] || 0);
}

// P8a: Compute the affinity multiplier + confidence for one pick at one circuit.
// Replaces the previous all-or-nothing gate (history >= 2 && weightSum > 0.5)
// with a confidence-weighted blend toward 1.0. Low-data drivers get a partial
// signal instead of being silently defaulted to 1.0, but their signal is
// dampened in proportion to how much data is available.
//
// Returns { affinity, confidence } where:
//   - affinity is clamped to [0.6, 1.4]
//   - confidence is in [0, 1]: 0 = no historical signal (affinity defaulted to 1.0),
//     1 = full signal (one very-similar race or several moderately-similar races).
//
// Changes vs old version:
//   - Threshold gates relaxed: hist.length >= 1 (was 2), weightSum > 0.1 (was 0.5).
//   - Similarity cliff softened: w = max(0, sim - 0.5) * 2.0 (was (sim - 0.7) * 3.33)
//     so moderately-similar tracks contribute with lower weight instead of being
//     ignored entirely.
//   - Confidence-weighted blend: affinity = 1.0 + confidence * (rawAffinity - 1.0).
//     A driver with weightSum=0.4 (previously below threshold, would get 1.0)
//     now gets 1.0 + 0.4 * (raw - 1.0). Smooth gradient instead of cliff.
function computeAffinityWithConfidence(hist, targetVec, basePts) {
    if (!hist || hist.length < 1 || !targetVec) return { affinity: 1.0, confidence: 0 };

    // P10: tunables hoisted to MW_TUNABLES.
    const SIM_FLOOR = MW_TUNABLES.affinitySimilarityFloor;
    const FULL_CONF_WEIGHT = MW_TUNABLES.affinityFullConfidence;
    const CLAMP_MIN = MW_TUNABLES.affinityClampMin;
    const CLAMP_MAX = MW_TUNABLES.affinityClampMax;

    let weightedPts = 0, weightSum = 0;
    for (const h of hist) {
        const hVec = getFeatureVector(h.circuit_id);
        if (!hVec) continue;
        const sim = cosineSimilarity(targetVec, hVec);
        // Softened weight: starts contributing at sim > SIM_FLOOR, full weight at sim = 1.0
        // (2.0 = 1 / (1.0 - SIM_FLOOR) when SIM_FLOOR = 0.5)
        const w = Math.max(0, sim - SIM_FLOOR) * (1 / (1 - SIM_FLOOR));
        weightedPts += h.points * w;
        weightSum += w;
    }

    if (weightSum <= 0.1 || basePts === 0) return { affinity: 1.0, confidence: 0 };

    const avgSimilarPts = weightedPts / weightSum;
    const avgAllPts = hist.reduce((s, h) => s + h.points, 0) / hist.length;
    if (avgAllPts === 0) return { affinity: 1.0, confidence: 0 };

    const rawAffinity = avgSimilarPts / avgAllPts;
    const confidence = Math.min(1.0, weightSum / FULL_CONF_WEIGHT);
    const blended = 1.0 + confidence * (rawAffinity - 1.0);
    const affinity = Math.max(CLAMP_MIN, Math.min(CLAMP_MAX, blended));
    return { affinity, confidence };
}

function projectScoresForRound(roundInfo, racesData) {
    // Project fantasy scores for all drivers/constructors at a future round.
    // Preferred source (P9): horizon_projections.json, populated by
    //   pipeline/predict_horizon.py — actual ML predictions converted to
    //   simplified expected fantasy points.
    // Fallback: current form (from predictions.json) × track affinity (P8a).
    if (!data || !trackData) return { drivers: {}, constructors: {}, driverConfidence: {}, constructorConfidence: {} };

    const raceName = roundInfo.name;
    const circuitId = trackData.race_circuit_map[raceName] || 'unknown';
    const targetVec = getFeatureVector(circuitId);
    const isSprint = (trackData.sprint_rounds || []).includes(roundInfo.round);

    const driverScores = {};
    const constructorScores = {};
    const driverConfidence = {};      // P8: per-pick confidence for UI flagging
    const constructorConfidence = {};

    // P9: prefer ML-based projection from horizon_projections.json if it exists
    // for this round. Each driver in our roster has a `driver_id` (abbrev like
    // 'VER'); horizon JSON keys drivers by the same abbreviation.
    const horizonRound = horizonProjections?.rounds?.[String(roundInfo.round)];
    if (horizonRound) {
        for (const d of data.drivers) {
            const hp = horizonRound.drivers?.[d.driver_id];
            if (hp && typeof hp.expected_points === 'number') {
                driverScores[d.driver_id] = hp.expected_points;
                driverConfidence[d.driver_id] = 0.95; // ML pred — full confidence
            } else {
                // Fall through: no ML projection for this driver, use heuristic below.
                driverScores[d.driver_id] = null;
            }
        }
        for (const c of data.constructors) {
            const hp = horizonRound.constructors?.[c.constructor_id];
            if (hp && typeof hp.expected_points === 'number') {
                constructorScores[c.constructor_id] = hp.expected_points;
                constructorConfidence[c.constructor_id] = 0.95;
            } else {
                constructorScores[c.constructor_id] = null;
            }
        }
    }

    // Sprint adjustment factor — same for all picks in this round
    const currentIsSprint = data.is_sprint_weekend;
    let sprintAdj = 1.0;
    if (currentIsSprint && !isSprint) sprintAdj = 1.0 / 1.35;
    else if (!currentIsSprint && isSprint) sprintAdj = 1.35;

    // Project driver scores via affinity heuristic — only for picks not
    // already filled by the P9 ML projection (driverScores[id] === null).
    for (const d of data.drivers) {
        if (driverScores[d.driver_id] != null) continue; // ML projection used
        const basePts = basisPoints(d) || 0;
        const hist = (driverHistory && driverHistory.drivers[d.driver_id])
            ? driverHistory.drivers[d.driver_id].rounds
            : null;
        const { affinity, confidence } = computeAffinityWithConfidence(hist, targetVec, basePts);
        driverScores[d.driver_id] = Math.round(basePts * affinity * sprintAdj * 10) / 10;
        driverConfidence[d.driver_id] = confidence;
    }

    // Project constructor scores — same heuristic fallback rule.
    for (const c of data.constructors) {
        if (constructorScores[c.constructor_id] != null) continue;
        const basePts = basisPoints(c) || 0;
        const hist = (driverHistory && driverHistory.constructors[c.constructor_id])
            ? driverHistory.constructors[c.constructor_id].rounds
            : null;
        const { affinity, confidence } = computeAffinityWithConfidence(hist, targetVec, basePts);
        constructorScores[c.constructor_id] = Math.round(basePts * affinity * sprintAdj * 10) / 10;
        constructorConfidence[c.constructor_id] = confidence;
    }

    return { drivers: driverScores, constructors: constructorScores, isSprint, circuitId, driverConfidence, constructorConfidence };
}

function getUpcomingRounds(currentRound, horizon) {
    if (!seasonSummary || !seasonSummary.rounds) return [];
    return seasonSummary.rounds
        .filter(r => r.round >= currentRound)
        .slice(0, horizon);
}

// Set-diff swap detector. Use whenever the new team can come back in any order
// (wildcard, limitless) — positional comparison reports phantom swaps when slot
// order shifts across rounds.
function computeSwapDetails(prevDrivers, prevCons, newDrivers, newCons) {
    const newDriverSet = new Set(newDrivers);
    const prevDriverSet = new Set(prevDrivers);
    const driversOut = prevDrivers.filter(id => !newDriverSet.has(id));
    const driversIn = newDrivers.filter(id => !prevDriverSet.has(id));
    const newConSet = new Set(newCons);
    const prevConSet = new Set(prevCons);
    const consOut = prevCons.filter(id => !newConSet.has(id));
    const consIn = newCons.filter(id => !prevConSet.has(id));

    const swapDetails = [];
    for (let i = 0; i < Math.max(driversOut.length, driversIn.length); i++) {
        swapDetails.push({ type: 'driver', out: driversOut[i] || null, in: driversIn[i] || null });
    }
    for (let i = 0; i < Math.max(consOut.length, consIn.length); i++) {
        swapDetails.push({ type: 'constructor', out: consOut[i] || null, in: consIn[i] || null });
    }
    return { swaps: swapDetails.length, swapDetails };
}

function generateTransferCandidates(teamDrivers, teamConstructors, projDriverScores, projConScores, budget, maxSwaps) {
    // Generate candidate team changes: 0, 1, or 2 swaps
    const candidates = [];
    const driverPrices = {};
    const conPrices = {};
    for (const d of data.drivers) driverPrices[d.driver_id] = d.current_price;
    for (const c of data.constructors) conPrices[c.constructor_id] = c.current_price;

    const teamDriverSet = new Set(teamDrivers.filter(Boolean));
    const teamConSet = new Set(teamConstructors.filter(Boolean));

    // Calculate current team cost
    let currentCost = 0;
    for (const did of teamDrivers) if (did) currentCost += driverPrices[did] || 0;
    for (const cid of teamConstructors) if (cid) currentCost += conPrices[cid] || 0;

    // Candidate 0: keep team (no changes)
    candidates.push({
        drivers: [...teamDrivers],
        constructors: [...teamConstructors],
        swaps: 0,
        swapDetails: [],
    });

    if (maxSwaps === 0) return candidates;

    // All non-team drivers and constructors
    const availDrivers = data.drivers.filter(d => !teamDriverSet.has(d.driver_id));
    const availCons = data.constructors.filter(c => !teamConSet.has(c.constructor_id));

    // 1-swap candidates: replace one driver or one constructor
    for (let i = 0; i < teamDrivers.length; i++) {
        const outId = teamDrivers[i];
        if (!outId) continue;
        const outPrice = driverPrices[outId] || 0;
        for (const avail of availDrivers) {
            const inPrice = driverPrices[avail.driver_id] || 0;
            const newCost = currentCost - outPrice + inPrice;
            if (newCost > budget) continue;
            const newDrivers = [...teamDrivers];
            newDrivers[i] = avail.driver_id;
            candidates.push({
                drivers: newDrivers,
                constructors: [...teamConstructors],
                swaps: 1,
                swapDetails: [{ type: 'driver', out: outId, in: avail.driver_id }],
            });
        }
    }
    for (let i = 0; i < teamConstructors.length; i++) {
        const outId = teamConstructors[i];
        if (!outId) continue;
        const outPrice = conPrices[outId] || 0;
        for (const avail of availCons) {
            const inPrice = conPrices[avail.constructor_id] || 0;
            const newCost = currentCost - outPrice + inPrice;
            if (newCost > budget) continue;
            const newCons = [...teamConstructors];
            newCons[i] = avail.constructor_id;
            candidates.push({
                drivers: [...teamDrivers],
                constructors: newCons,
                swaps: 1,
                swapDetails: [{ type: 'constructor', out: outId, in: avail.constructor_id }],
            });
        }
    }

    if (maxSwaps < 2) return candidates;

    // 2-swap candidates: replace two drivers, or one driver + one constructor
    // P11: pool the candidates by RAW SCORE ∪ PPM — without PPM-ranked picks
    // the search misses cheap high-value players who'd enable budget-relief
    // swaps (down-trade an expensive driver + up-trade a cheap one). Raw-score
    // pool covers high-ceiling absolute picks; PPM pool covers
    // bang-for-the-buck. Union dedupes via Set, so total candidate count is
    // ≤ poolByScore + poolByPpm.
    const driverPoolByScore = availDrivers
        .slice()
        .sort((a, b) => (projDriverScores[b.driver_id] || 0) - (projDriverScores[a.driver_id] || 0))
        .slice(0, MW_TUNABLES.driverPoolByScore);
    const driverPoolByPpm = availDrivers
        .slice()
        .sort((a, b) => {
            const ppmA = (projDriverScores[a.driver_id] || 0) / (a.current_price || 1e-6);
            const ppmB = (projDriverScores[b.driver_id] || 0) / (b.current_price || 1e-6);
            return ppmB - ppmA;
        })
        .slice(0, MW_TUNABLES.driverPoolByPpm);
    const driverPoolIds = new Set();
    const topAvailDrivers = [];
    for (const d of [...driverPoolByScore, ...driverPoolByPpm]) {
        if (!driverPoolIds.has(d.driver_id)) {
            driverPoolIds.add(d.driver_id);
            topAvailDrivers.push(d);
        }
    }

    const conPoolByScore = availCons
        .slice()
        .sort((a, b) => (projConScores[b.constructor_id] || 0) - (projConScores[a.constructor_id] || 0))
        .slice(0, MW_TUNABLES.conPoolByScore);
    const conPoolByPpm = availCons
        .slice()
        .sort((a, b) => {
            const ppmA = (projConScores[a.constructor_id] || 0) / (a.current_price || 1e-6);
            const ppmB = (projConScores[b.constructor_id] || 0) / (b.current_price || 1e-6);
            return ppmB - ppmA;
        })
        .slice(0, MW_TUNABLES.conPoolByPpm);
    const conPoolIds = new Set();
    const topAvailCons = [];
    for (const c of [...conPoolByScore, ...conPoolByPpm]) {
        if (!conPoolIds.has(c.constructor_id)) {
            conPoolIds.add(c.constructor_id);
            topAvailCons.push(c);
        }
    }

    // Two driver swaps
    for (let i = 0; i < teamDrivers.length; i++) {
        for (let j = i + 1; j < teamDrivers.length; j++) {
            const out1 = teamDrivers[i], out2 = teamDrivers[j];
            if (!out1 || !out2) continue;
            const freed = (driverPrices[out1] || 0) + (driverPrices[out2] || 0);
            for (const a1 of topAvailDrivers) {
                for (const a2 of topAvailDrivers) {
                    if (a1.driver_id === a2.driver_id) continue;
                    const needed = (driverPrices[a1.driver_id] || 0) + (driverPrices[a2.driver_id] || 0);
                    if (currentCost - freed + needed > budget) continue;
                    const newD = [...teamDrivers];
                    newD[i] = a1.driver_id;
                    newD[j] = a2.driver_id;
                    candidates.push({
                        drivers: newD,
                        constructors: [...teamConstructors],
                        swaps: 2,
                        swapDetails: [
                            { type: 'driver', out: out1, in: a1.driver_id },
                            { type: 'driver', out: out2, in: a2.driver_id },
                        ],
                    });
                }
            }
        }
    }
    // One driver + one constructor swap
    for (let i = 0; i < teamDrivers.length; i++) {
        for (let j = 0; j < teamConstructors.length; j++) {
            const outD = teamDrivers[i], outC = teamConstructors[j];
            if (!outD || !outC) continue;
            const freed = (driverPrices[outD] || 0) + (conPrices[outC] || 0);
            for (const aD of topAvailDrivers) {
                for (const aC of topAvailCons) {
                    const needed = (driverPrices[aD.driver_id] || 0) + (conPrices[aC.constructor_id] || 0);
                    if (currentCost - freed + needed > budget) continue;
                    const newD = [...teamDrivers];
                    newD[i] = aD.driver_id;
                    const newC = [...teamConstructors];
                    newC[j] = aC.constructor_id;
                    candidates.push({
                        drivers: newD,
                        constructors: newC,
                        swaps: 2,
                        swapDetails: [
                            { type: 'driver', out: outD, in: aD.driver_id },
                            { type: 'constructor', out: outC, in: aC.constructor_id },
                        ],
                    });
                }
            }
        }
    }

    // P12: Constructor+constructor 2-swap (replace BOTH constructors).
    // Previously absent — the planner could only ever change one constructor
    // per round even with 2 free transfers, even when swapping both was
    // strictly better. Only one unique pair exists (i=0, j=1) since there are
    // exactly 2 constructor slots.
    if (teamConstructors.length >= 2 && teamConstructors[0] && teamConstructors[1]) {
        const out1 = teamConstructors[0], out2 = teamConstructors[1];
        const freed = (conPrices[out1] || 0) + (conPrices[out2] || 0);
        for (const a1 of topAvailCons) {
            for (const a2 of topAvailCons) {
                if (a1.constructor_id === a2.constructor_id) continue;
                const needed = (conPrices[a1.constructor_id] || 0) + (conPrices[a2.constructor_id] || 0);
                if (currentCost - freed + needed > budget) continue;
                candidates.push({
                    drivers: [...teamDrivers],
                    constructors: [a1.constructor_id, a2.constructor_id],
                    swaps: 2,
                    swapDetails: [
                        { type: 'constructor', out: out1, in: a1.constructor_id },
                        { type: 'constructor', out: out2, in: a2.constructor_id },
                    ],
                });
            }
        }
    }

    return candidates;
}

function scoreTeam(drivers, constructors, driverScores, conScores) {
    let total = 0;
    for (const did of drivers) {
        if (did) total += driverScores[did] || 0;
    }
    for (const cid of constructors) {
        if (cid) total += conScores[cid] || 0;
    }
    return total;
}

async function runMultiWeekPlanner() {
    await loadMultiWeekData();

    if (!data || !seasonSummary || !trackData) {
        alert('Data not loaded yet. Please wait for the page to finish loading.');
        return;
    }

    const teamDrivers = [...myTeamDrivers];
    const teamCons = [...myTeamConstructors];
    const filledDrivers = teamDrivers.filter(Boolean).length;
    const filledCons = teamCons.filter(Boolean).length;
    if (filledDrivers < 5 || filledCons < 2) {
        alert('Please select your full current team (5 drivers + 2 constructors) before planning.');
        return;
    }

    const budget = parseFloat(document.getElementById('mwBudget').value);
    const freeTransfers = parseInt(document.getElementById('mwFreeTransfers').value) || 2;
    const horizon = parseInt(document.getElementById('mwHorizon').value) || 3;
    const strategy = document.getElementById('mwStrategy').value;
    optimizeBasis = document.getElementById('pointsBasisMW')?.value || 'balanced';

    // Get available chips
    const availableChips = [];
    document.querySelectorAll('.mw-chips-section input[type=checkbox]:checked').forEach(cb => {
        availableChips.push(cb.value);
    });

    // Target team mode
    const useTargetTeam = document.getElementById('mwUseTarget')?.checked || false;
    let targetDriverSet = null;
    let targetConsSet = null;
    // P13: Target intensity → TARGET_WEIGHT lookup. Defaults to balanced when
    // the dropdown isn't present (legacy support) or target mode is off.
    const intensityValue = document.getElementById('mwTargetIntensity')?.value || 'balanced';
    const targetWeight = MW_TUNABLES.targetIntensity[intensityValue] ?? MW_TUNABLES.targetWeight;
    if (useTargetTeam) {
        const filledTargetD = targetTeamDrivers.filter(Boolean).length;
        const filledTargetC = targetTeamConstructors.filter(Boolean).length;
        if (filledTargetD < 5 || filledTargetC < 2) {
            alert('Please select your full target team (5 drivers + 2 constructors) before planning.');
            return;
        }
        targetDriverSet = new Set(targetTeamDrivers.filter(Boolean));
        targetConsSet = new Set(targetTeamConstructors.filter(Boolean));
    }

    const currentRound = data.round || 0;

    // Scenario-aware view of the CURRENT round only. Scenarios are round-scoped
    // (auto-clear when the round changes), so future rounds use the planner's
    // own track-affinity heuristic / horizon ML and are NOT overlay-adjusted.
    const view = getScenarioView();

    // Load race calendar from seasonSummary (include current round since transfers haven't been made)
    const upcomingRounds = seasonSummary.rounds
        .filter(r => r.round >= currentRound)
        .slice(0, horizon);

    if (upcomingRounds.length === 0) {
        document.getElementById('mwResults').innerHTML = '<p>No upcoming rounds found.</p>';
        document.getElementById('mwResults').classList.remove('hidden');
        return;
    }

    // Project scores for each upcoming round
    // For current round, use actual ML predictions; for future rounds, use track-similarity projections
    const roundProjections = upcomingRounds.map(r => {
        if (r.round === currentRound) {
            // Use actual ML predictions for current round.
            // P8: ML preds are full-confidence (model handled the round directly,
            // no track-affinity heuristic involved). Set all confidences to 1.0
            // so heatmap doesn't flag these cells.
            const driverScores = {};
            const constructorScores = {};
            const driverConfidence = {};
            const constructorConfidence = {};
            for (const d of view.drivers) {
                driverScores[d.driver_id] = basisPoints(d) || 0;
                driverConfidence[d.driver_id] = 1.0;
            }
            for (const c of view.constructors) {
                constructorScores[c.constructor_id] = basisPoints(c) || 0;
                constructorConfidence[c.constructor_id] = 1.0;
            }
            return {
                ...r,
                isSprint: (trackData.sprint_rounds || []).includes(r.round),
                drivers: driverScores,
                constructors: constructorScores,
                driverConfidence,
                constructorConfidence,
            };
        }
        return {
            ...r,
            isSprint: (trackData.sprint_rounds || []).includes(r.round),
            ...projectScoresForRound(r, seasonSummary.rounds),
        };
    });

    // === P2: Target-team feasibility pre-check ===
    // When the user has set a target team, decide BEFORE running beam search
    // whether it's even reachable. Three states:
    //   - reachable now: targetCost <= currentBudget
    //   - possibly reachable: targetCost <= currentBudget + horizonAppreciation
    //   - unreachable: targetCost > both. Plan will be a "best partial match".
    //
    // Horizon appreciation is computed as if the user holds the CURRENT team
    // throughout the horizon (this is the best-case ceiling — they could swap
    // earlier and let target picks appreciate instead, but that requires
    // affording target's transition cost up-front, which is chicken-and-egg).
    // It's an upper bound: if even this estimate falls short of targetCost,
    // target is definitively unreachable.
    let feasibilityInfo = null;
    if (useTargetTeam) {
        const targetDriverObjs = targetTeamDrivers.filter(Boolean)
            .map(id => data.drivers.find(d => d.driver_id === id))
            .filter(Boolean);
        const targetConObjs = targetTeamConstructors.filter(Boolean)
            .map(id => data.constructors.find(c => c.constructor_id === id))
            .filter(Boolean);
        const targetPicks = [...targetDriverObjs, ...targetConObjs];
        const targetCost = targetPicks.reduce((s, p) => s + (p.current_price || 0), 0);

        const currentDriverObjs = teamDrivers
            .map(id => data.drivers.find(d => d.driver_id === id))
            .filter(Boolean);
        const currentConObjs = teamCons
            .map(id => data.constructors.find(c => c.constructor_id === id))
            .filter(Boolean);

        // Sum predicted appreciation across the horizon for currently-held picks.
        // Uses the same per-round projected scores as the beam search (so this is
        // consistent with P1's in-loop budget propagation).
        let horizonAppreciation = 0;
        for (const proj of roundProjections) {
            for (const d of currentDriverObjs) {
                const pc = predictPriceChange(d, proj.drivers[d.driver_id] || 0);
                horizonAppreciation += pc.expectedChange;
            }
            for (const c of currentConObjs) {
                const pc = predictPriceChange(c, proj.constructors[c.constructor_id] || 0);
                horizonAppreciation += pc.expectedChange;
            }
        }

        const projectedCeiling = budget + horizonAppreciation;
        const isReachableNow = targetCost <= budget;
        const isPossiblyReachable = targetCost <= projectedCeiling;
        const shortfall = Math.max(0, targetCost - projectedCeiling);

        // Identify the most expensive target picks (helps the user revise target
        // if it's unreachable). Top 2 by current_price.
        const priciest = [...targetPicks]
            .sort((a, b) => (b.current_price || 0) - (a.current_price || 0))
            .slice(0, 2)
            .map(p => ({
                name: p.name || p.constructor_id || p.driver_id,
                price: p.current_price || 0,
                isDriver: !!p.driver_id,
            }));

        // Identify which target picks the user already owns (held picks) — these
        // don't need to be "acquired" so they don't contribute to transition cost.
        const currentDriverIds = new Set(teamDrivers.filter(Boolean));
        const currentConIds = new Set(teamCons.filter(Boolean));
        const heldTargetCount = targetDriverObjs.filter(d => currentDriverIds.has(d.driver_id)).length +
                                targetConObjs.filter(c => currentConIds.has(c.constructor_id)).length;
        const transfersNeeded = targetPicks.length - heldTargetCount;

        feasibilityInfo = {
            useTargetTeam: true,
            targetCost: Math.round(targetCost * 100) / 100,
            currentBudget: Math.round(budget * 100) / 100,
            horizonAppreciation: Math.round(horizonAppreciation * 100) / 100,
            projectedCeiling: Math.round(projectedCeiling * 100) / 100,
            isReachableNow,
            isPossiblyReachable,
            isUnreachable: !isPossiblyReachable,
            shortfall: Math.round(shortfall * 100) / 100,
            priciestTargetPicks: priciest,
            heldTargetCount,
            transfersNeeded,
            horizonRounds: roundProjections.length,
        };
    }

    // === Beam Search ===
    // P10: pulled from MW_TUNABLES; aliased locally for readability in the loop.
    const BEAM_WIDTH = MW_TUNABLES.beamWidth;
    const TRANSFER_PENALTY = MW_TUNABLES.transferPenalty;

    // P5: Memoize optimal wildcard teams per (budget bucket, round index).
    // The optimal wildcard team depends only on the budget ceiling and the
    // round's projections (it ignores current team — wildcard can swap freely).
    // Beam states with similar budgets converge to the same wildcard team, so
    // bucketing by $0.1M lets all 60 beam states share one search per round.
    // Without this cache, a 60-state × 3-round horizon would run the brute-force
    // search 180 times; with it, ~3-10 times.
    const wildcardCache = new Map();

    let beam = [{
        drivers: [...teamDrivers],
        constructors: [...teamCons],
        budget: budget,
        bankedTransfers: freeTransfers,
        chipsUsed: [],
        chipsAvailable: [...availableChips],
        totalPoints: 0,
        roundActions: [],
    }];

    for (let ri = 0; ri < roundProjections.length; ri++) {
        const proj = roundProjections[ri];
        const nextBeam = [];

        // P5b: Per-round target info for chip-aware optimization (Wildcard uses this).
        // Distance weight matches P3's main-loop calculation so wildcard search and
        // post-search scoring are consistent.
        // P13: TARGET_WEIGHT now driven by the Target Intensity dropdown — see
        // resolution at the top of runMultiWeekPlanner.
        const TARGET_WEIGHT = targetWeight;
        const roundProgress = (ri + 1) / roundProjections.length;
        let roundTargetInfo = null;
        if (useTargetTeam && targetDriverSet && targetConsSet) {
            roundTargetInfo = {
                driverSet: targetDriverSet,
                conSet: targetConsSet,
                distanceWeight: TARGET_WEIGHT * roundProgress,
            };
        }

        for (const state of beam) {
            // Transfers gained this round (1 per round, max 5 banked)
            // For the current round (ri===0), use banked transfers as-is (no +1 since we haven't passed a round yet)
            const transfersThisRound = ri === 0 ? state.bankedTransfers : Math.min(state.bankedTransfers + 1, MW_TUNABLES.maxBankedTransfers);

            // Generate candidates: 0, 1, or 2 swaps
            const maxSwaps = Math.min(2, transfersThisRound);
            const candidates = generateTransferCandidates(
                state.drivers, state.constructors,
                proj.drivers, proj.constructors,
                state.budget, maxSwaps
            );

            // Also try wildcard if available
            if (state.chipsAvailable.includes('wild_card')) {
                // With wildcard: pick best 5 drivers + 2 constructors by projected score within budget
                // P5: Use brute-force optimizer instead of greedy by-score-within-budget.
                // Memoized by (round_index, budget_bucket) so beam states with similar
                // budgets share the search. See wildcardCache declaration above.
                // Cache key includes ri (so per-round target weight is captured) and budget bucket.
                // targetDriverSet/targetConsSet are constants throughout a planner run, so no need to key on them.
                const wcCacheKey = `${ri}|${Math.round(state.budget * 10)}`;
                let wcOptimal;
                if (wildcardCache.has(wcCacheKey)) {
                    wcOptimal = wildcardCache.get(wcCacheKey);
                } else {
                    wcOptimal = findOptimalWildcardTeam(state.budget, proj, roundTargetInfo);
                    wildcardCache.set(wcCacheKey, wcOptimal);
                }
                if (wcOptimal) {
                    candidates.push({
                        drivers: wcOptimal.drivers,
                        constructors: wcOptimal.constructors,
                        ...computeSwapDetails(state.drivers, state.constructors, wcOptimal.drivers, wcOptimal.constructors),
                        useChip: 'wild_card',
                    });
                }
            }

            // Limitless chip: pick best team ignoring budget constraint
            if (state.chipsAvailable.includes('limitless')) {
                const sortedDrivers = data.drivers
                    .map(d => ({ id: d.driver_id, pts: proj.drivers[d.driver_id] || 0, price: d.current_price }))
                    .sort((a, b) => b.pts - a.pts);
                const sortedCons = data.constructors
                    .map(c => ({ id: c.constructor_id, pts: proj.constructors[c.constructor_id] || 0, price: c.current_price }))
                    .sort((a, b) => b.pts - a.pts);
                const llDrivers = sortedDrivers.slice(0, 5).map(d => d.id);
                const llCons = sortedCons.slice(0, 2).map(c => c.id);
                if (llDrivers.length === 5) {
                    candidates.push({
                        drivers: llDrivers,
                        constructors: llCons,
                        ...computeSwapDetails(state.drivers, state.constructors, llDrivers, llCons),
                        useChip: 'limitless',
                    });
                }
            }

            // 3x Boost, No Negative, Autopilot: chips that apply on top of any swap pattern.
            // Augment every swap candidate (including the 0-swap "keep current") with each
            // available chip, so combos like "swap A→B AND fire 3x Boost on the new driver"
            // are explored. The original chip-only-current-team case is just swaps=0+chip.
            const chipOnlyTypes = ['3x_boost', 'no_negative', 'autopilot'];
            const baseSwapCount = candidates.filter(c => !c.useChip).length;
            const chipAugmented = [];
            for (const chipType of chipOnlyTypes) {
                if (!state.chipsAvailable.includes(chipType)) continue;
                for (let bi = 0; bi < baseSwapCount; bi++) {
                    chipAugmented.push({ ...candidates[bi], useChip: chipType });
                }
            }
            candidates.push(...chipAugmented);

            for (const cand of candidates) {
                let pts = scoreTeam(cand.drivers, cand.constructors, proj.drivers, proj.constructors);
                const usedChip = cand.useChip || null;

                // P5b: Limitless is a ONE-ROUND dream team. The user's real team
                // is untouched — no transfers happen, no team change persists,
                // no held-asset appreciation applies (because the dream team is
                // not actually held), and target convergence is measured against
                // the persistent team (not the dream). The dream team is purely
                // a scoring boost for one round.
                //
                // Wildcard, by contrast, IS a permanent set of transfers
                // (unlimited count, no penalty) — its team persists forward.
                const isLimitless = usedChip === 'limitless';
                const persistedDrivers = isLimitless ? state.drivers : cand.drivers;
                const persistedCons = isLimitless ? state.constructors : cand.constructors;

                // Apply chip scoring effects
                if (usedChip === '3x_boost' || usedChip === 'autopilot') {
                    // Find top scorer and apply boost
                    const dScores = cand.drivers.map(did => ({ id: did, pts: proj.drivers[did] || 0 })).sort((a, b) => b.pts - a.pts);
                    if (dScores.length > 0) {
                        // autopilot = 2x on best; 3x_boost = 3x on best + 2x on second
                        const primaryMult = usedChip === '3x_boost' ? 2 : 1; // extra multiplier (3x-1=2 or 2x-1=1)
                        pts += dScores[0].pts * primaryMult;
                        if (usedChip === '3x_boost' && dScores.length > 1) {
                            pts += dScores[1].pts; // 2x-1=1
                        }
                    }
                } else if (usedChip === 'no_negative') {
                    // Recalculate with negative scores floored to 0
                    pts = 0;
                    for (const did of cand.drivers) {
                        pts += Math.max(0, proj.drivers[did] || 0);
                    }
                    for (const cid of cand.constructors) {
                        pts += Math.max(0, proj.constructors[cid] || 0);
                    }
                }

                // Transfer penalty
                let penalty = 0;
                let remainingTransfers = transfersThisRound;
                if (usedChip === 'wild_card') {
                    remainingTransfers = transfersThisRound; // Unlimited transfers, none consumed
                } else if (isLimitless) {
                    // P5b: Limitless reverts after the round — no transfers used,
                    // no penalty regardless of how different the dream team is.
                    // Previously this was treating cand.swaps as real transfers,
                    // which incorrectly consumed banked FTs and could apply a
                    // -10pt penalty per "extra" dream-team-position. Both wrong.
                    penalty = 0;
                    remainingTransfers = transfersThisRound;
                } else {
                    const extraSwaps = Math.max(0, cand.swaps - transfersThisRound);
                    penalty = extraSwaps * TRANSFER_PENALTY;
                    remainingTransfers = Math.max(0, transfersThisRound - cand.swaps);
                }

                const netPts = pts - penalty;

                // Strategy weighting
                // P5b: for Limitless rounds, strategy calcs use the PERSISTED team
                // (not dream team). budget_gain measures appreciation of held
                // assets — dream team isn't held. balanced measures team ppm —
                // dream team isn't the user's actual team.
                const strategyDrivers = isLimitless ? state.drivers : cand.drivers;
                const strategyCons = isLimitless ? state.constructors : cand.constructors;
                let score = netPts;
                if (strategy === 'budget_gain') {
                    // Add projected price appreciation. P10: thresholds/weights from MW_TUNABLES.
                    let priceGain = 0;
                    for (const did of strategyDrivers) {
                        const d = data.drivers.find(x => x.driver_id === did);
                        if (d) {
                            const ppm = (proj.drivers[did] || 0) / d.current_price;
                            if (ppm >= MW_TUNABLES.ppmHighThreshold) priceGain += d.current_price <= MW_TUNABLES.priceBracketSplit ? 0.6 : 0.3;
                            else if (ppm >= MW_TUNABLES.ppmMidThreshold) priceGain += d.current_price <= MW_TUNABLES.priceBracketSplit ? 0.2 : 0.1;
                        }
                    }
                    score = netPts + priceGain * MW_TUNABLES.budgetGainWeight;
                } else if (strategy === 'balanced') {
                    // Mix points + value. P10: weights from MW_TUNABLES.
                    let totalPrice = 0;
                    for (const did of strategyDrivers) {
                        const d = data.drivers.find(x => x.driver_id === did);
                        if (d) totalPrice += d.current_price;
                    }
                    for (const cid of strategyCons) {
                        const c = data.constructors.find(x => x.constructor_id === cid);
                        if (c) totalPrice += c.current_price;
                    }
                    const ppm = totalPrice > 0 ? netPts / totalPrice : 0;
                    score = netPts * MW_TUNABLES.balancedPointsWeight + ppm * MW_TUNABLES.balancedPpmWeight;
                }

                // P3: Continuous target-distance objective.
                // Previously: +100/match bonus only on the LAST round. Intermediate
                // rounds optimized purely for points and ignored the target, then
                // the final-round cliff was supposed to force convergence — but
                // could be outweighed by a points-rich detour. Near-target plans
                // were passed over for slightly-higher-points plans even when the
                // user explicitly asked for target convergence.
                //
                // New: every round contributes a target-distance penalty weighted
                // by recency. Distance = number of target picks NOT in candidate
                // (range 0..7). Per-round penalty = distance * weight * (ri+1) /
                // horizon, so the final round penalizes ~3x as much as the first
                // round in a 3-round horizon. Intermediate rounds actively
                // path-find toward target while still permitting early-round
                // points-chasing when far from the goal.
                //
                // TARGET_WEIGHT calibration: 30 pts per off-target pick on the
                // final round is meaningful versus a typical driver projection
                // of ~25 pts/round (i.e. the planner won't trade a target match
                // for <30 pts of raw points on the last round) but won't force
                // wildly suboptimal swaps when convergence is impossible.
                if (useTargetTeam && targetDriverSet && targetConsSet) {
                    // P5b: For Limitless, measure distance against the PERSISTED
                    // team (state's pre-limitless), not the dream team — the
                    // dream team is temporary so its target-distance doesn't
                    // contribute to actual target convergence across the horizon.
                    let distance = 0;
                    for (const did of persistedDrivers) {
                        if (!targetDriverSet.has(did)) distance++;
                    }
                    for (const cid of persistedCons) {
                        if (!targetConsSet.has(cid)) distance++;
                    }
                    score -= distance * (roundTargetInfo ? roundTargetInfo.distanceWeight : 0);
                }

                const newChipsAvail = usedChip
                    ? state.chipsAvailable.filter(c => c !== usedChip)
                    : [...state.chipsAvailable];

                // --- P1: Propagate budget across rounds ---
                // Each held pick gains/loses its projected price change after this
                // round's race. Their increased sellable value (or decreased value)
                // shifts next round's spending ceiling. Without this, frozen-budget
                // beam search rejects target teams that ARE reachable via held-asset
                // appreciation across the horizon.
                //
                // predictPriceChange uses last-3-round avg PPM vs price thresholds
                // and returns expectedChange in $M. We apply it across drivers AND
                // constructors of the post-transfer team (cand.drivers/constructors)
                // because that's who you hold INTO this round's race.
                // P5b: For Limitless, the dream team is not actually held — the
                // user reverts to their real team. So appreciation must be
                // computed on the PERSISTED team, not the dream team. Without
                // this, firing Limitless would boost next-round budget by the
                // dream team's appreciation (which the user never owned).
                let roundAppreciation = 0;
                for (const did of persistedDrivers) {
                    const d = data.drivers.find(x => x.driver_id === did);
                    if (d) {
                        const projPts = proj.drivers[did] || 0;
                        const pc = predictPriceChange(d, projPts);
                        roundAppreciation += pc.expectedChange;
                    }
                }
                for (const cid of persistedCons) {
                    const c = data.constructors.find(x => x.constructor_id === cid);
                    if (c) {
                        const projPts = proj.constructors[cid] || 0;
                        const pc = predictPriceChange(c, projPts);
                        roundAppreciation += pc.expectedChange;
                    }
                }
                const budgetBefore = state.budget;
                const budgetAfter = Math.round((state.budget + roundAppreciation) * 100) / 100;

                nextBeam.push({
                    // P5b: carry PERSISTED team forward (= state's for limitless,
                    // = cand's for everything else). The dream team is stored in
                    // roundActions[].team for display but doesn't affect state.
                    drivers: persistedDrivers,
                    constructors: persistedCons,
                    budget: budgetAfter, // P1: budget now propagates with projected appreciation
                    bankedTransfers: remainingTransfers,
                    chipsUsed: usedChip ? [...state.chipsUsed, { round: proj.round, chip: usedChip }] : [...state.chipsUsed],
                    chipsAvailable: newChipsAvail,
                    totalPoints: state.totalPoints + netPts,
                    totalScore: (state.totalScore || 0) + score,
                    roundActions: [...state.roundActions, {
                        round: proj.round,
                        name: proj.name,
                        circuit: proj.circuit,
                        isSprint: proj.isSprint,
                        swaps: cand.swapDetails,
                        points: Math.round(pts * 10) / 10,
                        penalty,
                        netPoints: Math.round(netPts * 10) / 10,
                        chip: usedChip,
                        bankedAfter: remainingTransfers,
                        // P1: track budget evolution for later display (P4)
                        budgetBefore: Math.round(budgetBefore * 100) / 100,
                        appreciation: Math.round(roundAppreciation * 100) / 100,
                        budgetAfter,
                        // P5b: 'team' = dream team played THIS round (for display).
                        // 'persistedTeam' = team carried into NEXT round (= team
                        // for non-limitless; = pre-limitless team for limitless).
                        // Rendering uses persistedTeam to detect NEW picks in
                        // the round AFTER a limitless without false positives.
                        team: { drivers: [...cand.drivers], constructors: [...cand.constructors] },
                        persistedTeam: { drivers: [...persistedDrivers], constructors: [...persistedCons] },
                    }],
                });
            }
        }

        // Prune beam: keep top BEAM_WIDTH by cumulative score
        nextBeam.sort((a, b) => (b.totalScore || b.totalPoints) - (a.totalScore || a.totalPoints));

        // P6: Deduplicate by team + chips-available + banked-transfers.
        // Previously the key was just team composition, which collapsed two
        // states with the same persistent team but different remaining chips
        // or different banked-FT counts. The worse one would win first-seen
        // even though the better one represented a strictly better future.
        // Including chipsAvailable and bankedTransfers preserves those
        // strictly-better paths through the horizon.
        const seen = new Set();
        beam = [];
        for (const state of nextBeam) {
            // Don't mutate state.drivers / state.constructors — slot order matters for
            // downstream swap-detection in subsequent rounds and rendering.
            const key = [...state.drivers].sort().join(',') + '|'
                + [...state.constructors].sort().join(',') + '|'
                + [...state.chipsAvailable].sort().join(',') + '|'
                + state.bankedTransfers;
            if (!seen.has(key)) {
                seen.add(key);
                beam.push(state);
            }
            if (beam.length >= BEAM_WIDTH) break;
        }
    }

    // Get top 5 plans — keep ranking by the strategy-weighted totalScore that
    // drove the beam search; sorting by raw totalPoints here would discard the
    // strategy weighting (e.g. budget_gain plans get re-ranked by raw points).
    beam.sort((a, b) => (b.totalScore || b.totalPoints) - (a.totalScore || a.totalPoints));
    const topPlans = beam.slice(0, 5);

    // Render results
    displayMultiWeekResults(topPlans, roundProjections, currentRound, feasibilityInfo);
}

// P2: Render the target-team feasibility report. Surfaces whether the target is
// reachable now, possibly reachable via projected appreciation, or definitively
// unreachable (with shortfall). Always renders the beam-search plans below;
// when unreachable, those plans represent the best partial match given the
// budget constraint.
function renderFeasibilityCard(info) {
    if (!info || !info.useTargetTeam) return '';

    let statusLabel, statusColor, statusIcon, statusDetail;
    if (info.isReachableNow) {
        statusLabel = 'Target team is affordable now';
        statusColor = 'var(--green)';
        statusIcon = '✓';
        statusDetail = `You can buy the full target team this round (cost $${info.targetCost.toFixed(1)}M ≤ budget $${info.currentBudget.toFixed(1)}M). Plans below stage the transfers across the horizon.`;
    } else if (info.isPossiblyReachable) {
        statusLabel = 'Target team possibly reachable via projected appreciation';
        statusColor = 'var(--orange, #f59e0b)';
        statusIcon = '⚠';
        statusDetail = `Target costs $${info.targetCost.toFixed(1)}M but your starting budget is $${info.currentBudget.toFixed(1)}M. Projected horizon appreciation (+$${info.horizonAppreciation.toFixed(1)}M) brings the ceiling to $${info.projectedCeiling.toFixed(1)}M. Reachability depends on the transfer path the planner finds.`;
    } else {
        statusLabel = `Target team unreachable — short by $${info.shortfall.toFixed(1)}M`;
        statusColor = 'var(--red, #ef4444)';
        statusIcon = '✗';
        statusDetail = `Target costs $${info.targetCost.toFixed(1)}M but even with $${info.horizonAppreciation.toFixed(1)}M projected appreciation across ${info.horizonRounds} round${info.horizonRounds !== 1 ? 's' : ''}, the budget ceiling is only $${info.projectedCeiling.toFixed(1)}M. Plans below show the best partial match.`;
    }

    let priciestHtml = '';
    if (info.isUnreachable && info.priciestTargetPicks.length) {
        const picks = info.priciestTargetPicks.map(p =>
            `<strong>${p.name}</strong> ($${p.price.toFixed(1)}M)`
        ).join(', ');
        priciestHtml = `<p style="margin:8px 0 0;font-size:0.88rem;color:var(--text-secondary);">Most expensive target picks: ${picks}. Consider replacing one with a cheaper alternative to bring target within reach.</p>`;
    }

    return `<div class="feasibility-card" style="background:var(--card);border:2px solid ${statusColor};border-radius:10px;padding:16px 20px;margin-bottom:20px;">
        <h3 style="color:${statusColor};margin:0 0 8px;display:flex;align-items:center;gap:8px;">
            <span style="font-size:1.3em;">${statusIcon}</span> ${statusLabel}
        </h3>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:12px 0;font-size:0.92rem;">
            <div><div style="color:var(--text-secondary);font-size:0.78rem;">Target cost</div><div style="font-weight:600;">$${info.targetCost.toFixed(1)}M</div></div>
            <div><div style="color:var(--text-secondary);font-size:0.78rem;">Current budget</div><div style="font-weight:600;">$${info.currentBudget.toFixed(1)}M</div></div>
            <div><div style="color:var(--text-secondary);font-size:0.78rem;">Proj. appreciation</div><div style="font-weight:600;color:${info.horizonAppreciation >= 0 ? 'var(--green)' : 'var(--red, #ef4444)'};">${info.horizonAppreciation >= 0 ? '+' : ''}$${info.horizonAppreciation.toFixed(1)}M</div></div>
            <div><div style="color:var(--text-secondary);font-size:0.78rem;">Horizon ceiling</div><div style="font-weight:600;">$${info.projectedCeiling.toFixed(1)}M</div></div>
            <div><div style="color:var(--text-secondary);font-size:0.78rem;">Picks already held</div><div style="font-weight:600;">${info.heldTargetCount}/7</div></div>
            <div><div style="color:var(--text-secondary);font-size:0.78rem;">Transfers needed</div><div style="font-weight:600;">${info.transfersNeeded}</div></div>
        </div>
        <p style="margin:0;font-size:0.88rem;color:var(--text-secondary);">${statusDetail}</p>
        ${priciestHtml}
    </div>`;
}

function displayMultiWeekResults(plans, roundProjections, currentRound, feasibilityInfo) {
    const container = document.getElementById('mwResults');
    if (!plans.length) {
        // Still show feasibility card if target was set — explains why no plans
        const feasHtml = renderFeasibilityCard(feasibilityInfo);
        container.innerHTML = scenarioBannerHtml() + feasHtml + '<p style="color:var(--text-secondary);">No valid plans found. Check your team selection and budget.</p>';
        container.classList.remove('hidden');
        return;
    }

    let html = '';

    // Scenario banner — only when active. Shown ahead of all plan rendering so
    // users can't miss that the plans reflect their bumps for the current round.
    html += scenarioBannerHtml();

    // P2: Target-team feasibility card (renders only if useTargetTeam was set)
    html += renderFeasibilityCard(feasibilityInfo);

    // Asset projection heatmap
    html += renderProjectionHeatmap(roundProjections);

    // Plan cards
    // P14: Surface that the strategy dropdown influences RANKING only — the
    // displayed total is raw net projected points (transfer penalties applied,
    // chip effects applied, but no strategy-weight bonus). Without this hint,
    // users wonder why Budget Builder shows fewer points than Max Points even
    // though it's "their pick".
    html += '<h3 style="margin:20px 0 4px;">Recommended Plans</h3>';
    html += '<p class="hint" style="margin:0 0 12px;font-size:0.82rem;color:var(--text-secondary);">Totals show raw projected net points (after transfer penalties + chip effects). The Strategy dropdown re-ranks plans but does not alter the displayed totals.</p>';

    for (let pi = 0; pi < plans.length; pi++) {
        const plan = plans[pi];
        const totalSwaps = plan.roundActions.reduce((s, r) => s + r.swaps.length, 0);
        const chipsUsed = plan.chipsUsed.map(c => c.chip.replace(/_/g, ' ')).join(', ') || 'None';

        // P4: Horizon budget summary (initial → final, total appreciation).
        // Pulls from the first/last roundAction's budgetBefore/After (set by P1).
        // Falls back gracefully if a legacy plan lacks these fields.
        let horizonBudgetHtml = '';
        const firstAction = plan.roundActions[0];
        const lastAction = plan.roundActions[plan.roundActions.length - 1];
        if (firstAction && lastAction && typeof firstAction.budgetBefore === 'number' && typeof lastAction.budgetAfter === 'number') {
            const totalAppr = lastAction.budgetAfter - firstAction.budgetBefore;
            const apprColor = totalAppr >= 0 ? 'var(--green)' : 'var(--red, #ef4444)';
            const apprSign = totalAppr >= 0 ? '+' : '';
            horizonBudgetHtml = `<span class="mw-plan-stats" style="margin-left:16px;">
                Budget: $${firstAction.budgetBefore.toFixed(1)}M → $${lastAction.budgetAfter.toFixed(1)}M
                <span style="color:${apprColor};font-weight:600;">(${apprSign}$${totalAppr.toFixed(1)}M)</span>
            </span>`;
        }

        html += `<div class="mw-plan-card">`;
        html += `<div class="mw-plan-header">
            <div>
                <span class="mw-plan-rank">Plan ${pi + 1}</span>
                <span class="mw-plan-stats" style="margin-left:16px;">
                    ${totalSwaps} transfer${totalSwaps !== 1 ? 's' : ''} &middot;
                    Chips: ${chipsUsed}
                </span>
                ${horizonBudgetHtml}
            </div>
            <div class="mw-plan-total">${plan.totalPoints.toFixed(1)} pts</div>
        </div>`;

        // Timeline
        // P7: Track previous round's team so we can compute the "vs hold"
        // counterfactual per round — lets the user audit whether each round's
        // extra-transfer penalty was actually worth taking.
        let prevTeamForTradeoff = {
            drivers: [...myTeamDrivers],
            constructors: [...myTeamConstructors],
        };
        html += '<div class="mw-timeline">';
        for (const action of plan.roundActions) {
            const isSprint = action.isSprint;
            const hasSwaps = action.swaps.length > 0;
            const hasChip = action.chip;
            const actionClass = hasChip ? 'mw-action-chip' : (hasSwaps ? 'mw-action-swap' : 'mw-action-hold');
            const circuitId = trackData?.race_circuit_map?.[action.name] || '';

            html += `<div class="mw-round-col">`;
            html += `<div class="mw-round-header">R${action.round}${isSprint ? '<span class="mw-round-sprint">SPRINT</span>' : ''}</div>`;
            html += `<div class="mw-round-circuit">${action.circuit || action.name}</div>`;

            html += `<div class="mw-round-action ${actionClass}">`;
            if (hasChip) {
                html += `<strong>${action.chip.replace(/_/g, ' ').toUpperCase()}</strong>`;
                // P5b: Limitless is a one-round dream team; team reverts next round.
                // Surfacing this prevents the user from assuming the dream team becomes their new team.
                if (action.chip === 'limitless') {
                    html += ` <span style="font-size:0.65rem;font-weight:400;color:var(--text-secondary);" title="Limitless gives you a dream team for one round only. Your real team is unchanged.">(reverts after round)</span>`;
                }
                html += '<br>';
            }
            if (hasSwaps) {
                for (const swap of action.swaps) {
                    const outName = swap.type === 'driver'
                        ? (data.drivers.find(d => d.driver_id === swap.out)?.name?.split(' ').pop() || swap.out)
                        : (data.constructors.find(c => c.constructor_id === swap.out)?.name || swap.out).toUpperCase();
                    const inName = swap.type === 'driver'
                        ? (data.drivers.find(d => d.driver_id === swap.in)?.name?.split(' ').pop() || swap.in)
                        : (data.constructors.find(c => c.constructor_id === swap.in)?.name || swap.in).toUpperCase();
                    html += `<span style="color:var(--red, #ef4444)">${outName}</span> → <span style="color:var(--green)">${inName}</span><br>`;
                }
            } else {
                html += 'Hold (bank transfer)';
            }
            html += '</div>';

            // P7: Make gross visible when there's a penalty, so user sees
            // both the chip-adjusted gross and the net hit. Without penalty,
            // keep the original compact display.
            if (action.penalty > 0) {
                html += `<div class="mw-round-pts">${action.netPoints.toFixed(1)} <span style="font-size:0.65em;font-weight:400;color:var(--text-secondary);">net</span></div>`;
                html += `<div class="mw-round-meta">${action.points.toFixed(1)} gross · <span style="color:var(--red, #ef4444);">-${action.penalty} pen</span> · ${action.bankedAfter} FT</div>`;
            } else {
                html += `<div class="mw-round-pts">${action.netPoints.toFixed(1)} pts</div>`;
                html += `<div class="mw-round-meta">${action.bankedAfter} FT banked</div>`;
            }

            // P7: Penalty trade-off audit — show what "holding the previous
            // round's team" would have scored against this round's projections.
            // Lets the user answer "was the swap (and any extra-transfer
            // penalty) actually worth it?". Caveat: ignores chip effects in
            // the hold-alternative (treats chip as fired either way). Marked
            // with * + tooltip when a chip was used this round.
            const rpForTradeoff = roundProjections.find(r => r.round === action.round);
            if (rpForTradeoff && action.swaps.length > 0) {
                const holdGross = scoreTeam(prevTeamForTradeoff.drivers, prevTeamForTradeoff.constructors, rpForTradeoff.drivers, rpForTradeoff.constructors);
                const swapGross = scoreTeam(action.team.drivers, action.team.constructors, rpForTradeoff.drivers, rpForTradeoff.constructors);
                const swapDelta = swapGross - holdGross;          // gross gain from swapping (pre-chip, pre-penalty)
                const netTradeoff = swapDelta - action.penalty;   // after penalty
                const tradeoffColor = netTradeoff > 0 ? 'var(--green)' : (netTradeoff < 0 ? 'var(--red, #ef4444)' : 'var(--text-secondary)');
                const sign = netTradeoff > 0 ? '+' : '';
                const chipNote = action.chip ? '*' : '';
                const chipTooltip = action.chip ? ' title="Comparison ignores chip effects — treats chip as fired either way."' : '';
                let labelText;
                if (action.penalty > 0) {
                    // Penalty present — explicitly show whether extra transfer paid off
                    const verdict = netTradeoff > 0
                        ? `worth it`
                        : (netTradeoff < 0 ? `lost vs hold` : `break-even`);
                    labelText = `vs hold: ${sign}${netTradeoff.toFixed(1)} net (${verdict})${chipNote}`;
                } else {
                    // No penalty — just show the swap's gross value
                    labelText = `vs hold: ${sign}${swapDelta.toFixed(1)} pts${chipNote}`;
                }
                html += `<div class="mw-round-tradeoff" style="font-size:0.7rem;color:${tradeoffColor};margin-top:4px;line-height:1.3;font-weight:600;"${chipTooltip}>${labelText}</div>`;
            }

            // P4: Per-round budget evolution. budgetBefore/After/appreciation
            // are populated by P1's beam-search budget propagation. Renders
            // only if those fields exist (legacy plans without them skip).
            if (typeof action.budgetAfter === 'number' && typeof action.budgetBefore === 'number') {
                const apprColor = action.appreciation >= 0 ? 'var(--green)' : 'var(--red, #ef4444)';
                const apprSign = action.appreciation >= 0 ? '+' : '';
                html += `<div class="mw-round-budget" style="font-size:0.7rem;color:var(--text-secondary);margin-top:6px;padding-top:6px;border-top:1px dashed var(--border);line-height:1.4;">
                    <div>$${action.budgetBefore.toFixed(1)}M → $${action.budgetAfter.toFixed(1)}M</div>
                    <div style="color:${apprColor};">${apprSign}$${action.appreciation.toFixed(1)}M apprec</div>
                </div>`;
            }

            html += '</div>';

            // P7: Advance the trade-off baseline so next round compares against
            // THIS round's chosen team, not the original starting team.
            // P5b: For limitless, use persistedTeam (which reverts to pre-limitless),
            // not the dream team. Otherwise the next round's "vs hold" would
            // wrongly compare against the limitless dream team.
            prevTeamForTradeoff = action.persistedTeam || action.team;
        }
        html += '</div>';

        // Team evolution
        html += '<details class="mw-team-evolution"><summary>View Team Evolution</summary>';
        let prevDrivers = [...myTeamDrivers];
        let prevCons = [...myTeamConstructors];
        for (const action of plan.roundActions) {
            const currDrivers = action.team.drivers;
            const currCons = action.team.constructors;
            // Find the matching round projection for per-member scores
            const rp = roundProjections.find(r => r.round === action.round);
            html += `<div class="mw-team-round">`;
            html += `<div class="mw-team-round-header">R${action.round} — ${action.circuit || action.name}</div>`;
            html += `<div class="mw-team-round-roster">`;
            for (const did of currDrivers) {
                const d = data.drivers.find(x => x.driver_id === did);
                if (!d) continue;
                const isNew = !prevDrivers.includes(did);
                const team = TEAMS[d.constructor] || { color: '#666' };
                const projPts = rp ? (rp.drivers[did] || 0) : 0;
                html += `<span class="mw-team-member${isNew ? ' new' : ''}" style="--team-color:${team.color}">
                    ${d.name.split(' ').pop()} <span class="mw-member-pts">${projPts.toFixed(0)}</span>
                </span>`;
            }
            for (const cid of currCons) {
                const c = data.constructors.find(x => x.constructor_id === cid);
                if (!c) continue;
                const isNew = !prevCons.includes(cid);
                const team = TEAMS[cid] || { color: '#666' };
                const projPts = rp ? (rp.constructors[cid] || 0) : 0;
                html += `<span class="mw-team-member constructor${isNew ? ' new' : ''}" style="--team-color:${team.color}">
                    ${(c.name || cid).toUpperCase()} <span class="mw-member-pts">${projPts.toFixed(0)}</span>
                </span>`;
            }
            html += '</div></div>';
            // P5b: advance prev using persistedTeam so the round AFTER a Limitless
            // doesn't paint reverted-back picks as "NEW" (they were already held
            // before the temporary dream team).
            const carriedTeam = action.persistedTeam || action.team;
            prevDrivers = [...carriedTeam.drivers];
            prevCons = [...carriedTeam.constructors];
        }
        html += '</details>';

        html += '</div>';
    }

    container.innerHTML = html;
    container.classList.remove('hidden');
}

function renderProjectionHeatmap(roundProjections) {
    if (!data || !roundProjections.length) return '';

    // Show top 10 drivers and top 5 constructors
    const topDrivers = [...data.drivers]
        .sort((a, b) => (b.expected_points || 0) - (a.expected_points || 0))
        .slice(0, 12);
    const topCons = [...data.constructors]
        .sort((a, b) => (b.expected_points || 0) - (a.expected_points || 0))
        .slice(0, 6);

    // P8: per-cell confidence styling. Cells where the affinity model had little
    // or no historical signal (e.g. rookies at first-of-season tracks, or Cadillac
    // drivers/constructors with no 2026 history) get a visual cue + tooltip so the
    // user knows the projection is naive form-only rather than data-validated.
    function styleCell(score, confidence) {
        const avg = arguments[2]; // not used, kept for sig parity if expanded later
        if (typeof confidence !== 'number') return { extra: '', title: '' };
        if (confidence <= 0.01) {
            // No historical signal at all — naive form-only projection
            return {
                extra: 'font-style:italic;opacity:0.7;border-bottom:1.5px dotted currentColor;',
                title: 'No historical signal at similar tracks — naive form-only projection',
            };
        }
        if (confidence < 0.5) {
            // Partial signal — projection blended toward 1.0 default
            return {
                extra: 'border-bottom:1.5px dotted currentColor;opacity:0.92;',
                title: `Limited historical signal (${Math.round(confidence * 100)}% confidence)`,
            };
        }
        return { extra: '', title: '' };
    }

    let html = '<h3 style="margin-bottom:8px;">Projected Points by Circuit</h3>';
    html += '<p class="hint" style="margin-bottom:12px;">Green = above average for that driver. Red = below. Based on track similarity.</p>';
    html += '<div class="mw-heatmap"><table><thead><tr><th>Driver</th><th>Price</th>';
    for (const rp of roundProjections) {
        const isSprint = (trackData?.sprint_rounds || []).includes(rp.round);
        html += `<th>R${rp.round}${isSprint ? '*' : ''}<br><span style="font-weight:400;font-size:0.65rem;">${rp.circuit || ''}</span></th>`;
    }
    html += '</tr></thead><tbody>';

    // Driver rows
    for (const d of topDrivers) {
        const team = TEAMS[d.constructor] || { color: '#666' };
        const scores = roundProjections.map(rp => rp.drivers[d.driver_id] || 0);
        const confidences = roundProjections.map(rp => rp.driverConfidence?.[d.driver_id]);
        const avg = scores.reduce((s, v) => s + v, 0) / scores.length;

        html += `<tr><td style="text-align:left;white-space:nowrap;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${team.color};margin-right:4px;"></span>${d.name.split(' ').pop()}</td>`;
        html += `<td>$${d.current_price.toFixed(1)}M</td>`;
        for (let i = 0; i < scores.length; i++) {
            const s = scores[i];
            const conf = confidences[i];
            const cls = s > avg * 1.05 ? 'mw-heat-high' : (s < avg * 0.95 ? 'mw-heat-low' : 'mw-heat-mid');
            const { extra, title } = styleCell(s, conf, avg);
            const titleAttr = title ? ` title="${title}"` : '';
            const styleAttr = extra ? ` style="${extra}"` : '';
            html += `<td class="${cls}"${styleAttr}${titleAttr}>${s.toFixed(0)}</td>`;
        }
        html += '</tr>';
    }

    // Separator
    html += '<tr><td colspan="99" style="height:4px;background:var(--border);"></td></tr>';

    // Constructor rows
    for (const c of topCons) {
        const team = TEAMS[c.constructor_id] || { color: '#666' };
        const scores = roundProjections.map(rp => rp.constructors[c.constructor_id] || 0);
        const confidences = roundProjections.map(rp => rp.constructorConfidence?.[c.constructor_id]);
        const avg = scores.reduce((s, v) => s + v, 0) / scores.length;

        html += `<tr><td style="text-align:left;white-space:nowrap;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${team.color};margin-right:4px;"></span>${(c.name || c.constructor_id).toUpperCase()}</td>`;
        html += `<td>$${c.current_price.toFixed(1)}M</td>`;
        for (let i = 0; i < scores.length; i++) {
            const s = scores[i];
            const conf = confidences[i];
            const cls = s > avg * 1.05 ? 'mw-heat-high' : (s < avg * 0.95 ? 'mw-heat-low' : 'mw-heat-mid');
            const { extra, title } = styleCell(s, conf, avg);
            const titleAttr = title ? ` title="${title}"` : '';
            const styleAttr = extra ? ` style="${extra}"` : '';
            html += `<td class="${cls}"${styleAttr}${titleAttr}>${s.toFixed(0)}</td>`;
        }
        html += '</tr>';
    }

    html += '</tbody></table></div>';
    // P8: legend explaining the cell decorations
    html += '<p class="hint" style="margin-top:4px;">* = Sprint weekend &nbsp;·&nbsp; <span style="font-style:italic;opacity:0.7;border-bottom:1.5px dotted currentColor;">italic+dotted</span> = no historical signal (naive form-only) &nbsp;·&nbsp; <span style="border-bottom:1.5px dotted currentColor;">dotted</span> = partial signal (low confidence)</p>';
    return html;
}

// ============================================================

function getPitStopStatsHtml(constructorId) {
    const s = getConstructorPitStats(constructorId);
    if (!s) return '';

    const measuredStops = s.totalStops - (s.missingStops || 0);
    const missingNote = s.missingStops
        ? ` <span style="color:var(--text-muted);" title="${s.missingStops} stop(s) without recorded stationary time — typically during safety car / VSC, retirements, or penalty stops">(${s.missingStops} n/a)</span>`
        : '';

    const lastRaceLine = s.lastFastest != null
        ? `<span title="Fastest stationary stop in the most recent race (R${s.lastRoundNum})">Last race best: <strong style="color:var(--text)">${s.lastFastest.toFixed(1)}s</strong> <span style="color:var(--text-muted);font-size:0.95em;">R${s.lastRoundNum}</span></span>`
        : `<span style="color:var(--text-muted);">Last race best: —</span>`;
    const seasonLine = s.seasonFastest != null
        ? `<span title="Team's fastest stationary stop across all completed rounds this season">Season best: <strong style="color:var(--green)">${s.seasonFastest.toFixed(1)}s</strong> <span style="color:var(--text-muted);font-size:0.95em;">R${s.seasonFastestRound}</span></span>`
        : `<span style="color:var(--text-muted);">Season best: —</span>`;
    const medianLine = s.median != null
        ? `<span title="Median stationary time across this team's measured stops">Season median: <strong>${s.median.toFixed(1)}s</strong></span>`
        : `<span style="color:var(--text-muted);">Season median: —</span>`;
    const slowLine = measuredStops > 0
        ? (s.slowCount > 0
            ? `<span style="color:var(--red, #ef4444);" title="Stops over 3.5s stationary (typically 0 fantasy points)">Slow stops: <strong>${s.slowCount}</strong>/${measuredStops}${missingNote}</span>`
            : `<span style="color:var(--green);" title="No stops over 3.5s stationary this season">Slow stops: <strong>0</strong>/${measuredStops}${missingNote}</span>`)
        : `<span style="color:var(--text-muted);">Stops: <strong>${s.totalStops}</strong>${missingNote}</span>`;

    return `
    <div class="pit-stats" style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border);font-size:0.75rem;color:var(--text-secondary);">
        <div style="font-weight:600;margin-bottom:4px;display:flex;justify-content:space-between;align-items:baseline;">
            <span title="Stationary pit stop time = wheels up to wheels down (the F1 Fantasy scoring metric)">Pit stop performance — stationary times</span>
            <span style="font-weight:400;color:var(--text-muted);font-size:0.95em;">${s.roundsWithData} rounds</span>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:3px 8px;">
            ${lastRaceLine}
            ${seasonLine}
            ${medianLine}
            ${slowLine}
        </div>
    </div>`;
}

// -- FP Analysis --
function fmtTime(seconds) {
    if (!seconds) return '-';
    const mins = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(3);
    return mins > 0 ? `${mins}:${secs.padStart(6, '0')}` : `${secs}`;
}

function renderFPAnalysis() {
    const el = document.getElementById('fpAnalysisContent');
    if (!fpAnalysis || fpAnalysis.error) {
        el.innerHTML = '<p class="no-data">No FP analysis data available yet. Run the FP analysis pipeline after free practice sessions.</p>';
        return;
    }

    // Helper: make sortable table. Each column: { key, label, fmt, title?, cls? }
    // data: array of { id, ...values }
    function sortableTable(tableId, columns, data, defaultSortKey, defaultAsc) {
        let sortKey = defaultSortKey, sortAsc = defaultAsc;
        function renderTable() {
            const sorted = [...data].sort((a, b) => {
                const av = a[sortKey], bv = b[sortKey];
                if (av == null && bv == null) return 0;
                if (av == null) return 1;
                if (bv == null) return -1;
                return sortAsc ? (av < bv ? -1 : av > bv ? 1 : 0) : (av > bv ? -1 : av < bv ? 1 : 0);
            });
            const thead = columns.map(c => {
                const arrow = c.key === sortKey ? (sortAsc ? ' ▲' : ' ▼') : '';
                const cls = c.cls ? ` class="${c.cls}"` : '';
                const ttl = c.title ? ` title="${c.title}"` : '';
                return `<th${cls}${ttl} data-sortkey="${c.key}" style="cursor:pointer">${c.label}${arrow}</th>`;
            }).join('');
            const tbody = sorted.map((row, i) => {
                const cells = columns.map(c => {
                    const cls = c.cls ? ` class="${c.cls}"` : '';
                    const val = c.fmt ? c.fmt(row, i) : (row[c.key] ?? '-');
                    return `<td${cls}>${val}</td>`;
                }).join('');
                return `<tr>${cells}</tr>`;
            }).join('');
            const tbl = document.getElementById(tableId);
            if (tbl) {
                tbl.querySelector('thead tr').innerHTML = thead;
                tbl.querySelector('tbody').innerHTML = tbody;
                tbl.querySelectorAll('thead th[data-sortkey]').forEach(th => {
                    th.onclick = () => {
                        const k = th.dataset.sortkey;
                        if (k === sortKey) sortAsc = !sortAsc;
                        else { sortKey = k; sortAsc = true; }
                        renderTable();
                    };
                });
            }
        }
        return { renderTable, getHtml: () => `<table class="data-table" id="${tableId}"><thead><tr></tr></thead><tbody></tbody></table>` };
    }

    let html = `<div class="analysis-race-header">${fpAnalysis.race} — Round ${fpAnalysis.round}</div>`;
    const postRenderFns = [];

    // Search/filter bar
    html += `<div class="controls" style="margin-bottom:12px;"><div class="control-group"><label>Filter driver</label>
        <input type="text" id="fpDriverFilter" placeholder="Search driver..." style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);font-size:0.85rem;width:140px;">
    </div></div>`;

    // Qualifying Pace
    if (fpAnalysis.qualifying_pace && Object.keys(fpAnalysis.qualifying_pace).length > 0) {
        const rows = Object.entries(fpAnalysis.qualifying_pace).filter(([,v]) => v.best_lap).map(([id, d]) => ({
            id, best_lap: d.best_lap, best_3_avg: d.best_3_avg, best_5_avg: d.best_5_avg,
            gap: d.gap_to_fastest, laps: d.total_laps
        }));
        const tbl = sortableTable('fpQualiTable', [
            { key: '_rank', label: '#', cls: 'num', fmt: (r, i) => i + 1 },
            { key: 'id', label: 'Driver', fmt: r => `<strong>${r.id}</strong>` },
            { key: 'best_lap', label: 'Best Lap', cls: 'num', title: 'Fastest single lap in FP sessions', fmt: r => fmtTime(r.best_lap) },
            { key: 'best_3_avg', label: 'Best 3 Avg', cls: 'num', title: 'Average of 3 fastest laps', fmt: r => fmtTime(r.best_3_avg) },
            { key: 'best_5_avg', label: 'Best 5 Avg', cls: 'num', title: 'Average of 5 fastest laps', fmt: r => fmtTime(r.best_5_avg) },
            { key: 'gap', label: 'Gap', cls: 'num', title: 'Gap to fastest driver', fmt: r => r.gap === 0 ? '<span class="text-green">Leader</span>' : r.gap != null ? '+' + r.gap.toFixed(3) : '-' },
            { key: 'laps', label: 'Laps', cls: 'num', title: 'Total clean laps completed' }
        ], rows, 'best_lap', true);
        html += `<div class="analysis-block"><h3>Qualifying Pace (Short Runs)</h3><p class="analysis-note">Best single-lap and multi-lap averages. Click column headers to sort.</p>${tbl.getHtml()}</div>`;
        postRenderFns.push(tbl.renderTable);
    }

    // Long Run Pace (predicted race pace) — representative race-sim laps only.
    if (fpAnalysis.long_run_pace && Object.keys(fpAnalysis.long_run_pace).length > 0) {
        const SESS_RANK = { FP1: 1, FP2: 2, FP3: 3 };
        // Restrict the race-pace board to fantasy-roster drivers. Practice/test
        // runners (FP1 cameos, usually low-fuel) aren't rateable race pace and
        // would otherwise top the board on a quick FP1 run. Fall back to all
        // drivers only if the roster is unavailable.
        const lrRoster = new Set((data && data.drivers ? data.drivers : []).map(d => d.driver_id));
        let lrEntries = Object.entries(fpAnalysis.long_run_pace);
        if (lrRoster.size) lrEntries = lrEntries.filter(([id]) => lrRoster.has(id));
        const lrLeader = lrEntries.length ? Math.min(...lrEntries.map(([, d]) => d.avg_long_run_pace)) : 0;
        const rows = lrEntries.map(([id, d]) => ({
            id,
            avg_pace: d.avg_long_run_pace,
            gap: +(d.avg_long_run_pace - lrLeader).toFixed(3),
            laps: d.headline_laps ?? d.total_long_run_laps,
            sess: d.headline_session || '',
            runs: d.runs || []
        }));
        const tbl = sortableTable('fpLongRunTable', [
            { key: '_rank', label: '#', cls: 'num', fmt: (r, i) => i + 1 },
            { key: 'id', label: 'Driver', fmt: r => `<strong>${r.id}</strong>` },
            { key: 'avg_pace', label: 'Race Pace', cls: 'num', title: 'Average of the representative long-run laps from the latest session that produced one (FP2 on a normal weekend). In/out laps, traffic and lock-ups are filtered out. Lower = faster race pace.', fmt: r => fmtTime(r.avg_pace) },
            { key: 'gap', label: 'Gap', cls: 'num', title: 'Gap to the fastest driver', fmt: r => r.gap <= 0 ? '<span class="text-green">Leader</span>' : '+' + r.gap.toFixed(3) },
            { key: 'sess', label: 'Session', cls: 'num', title: 'Session the headline pace is taken from' },
            { key: 'laps', label: 'Laps', cls: 'num', title: 'Clean laps behind the headline pace' }
        ], rows, 'avg_pace', true);
        html += `<div class="analysis-block"><h3>Long Run Pace (Predicted Race Pace)</h3><p class="analysis-note">Representative race-sim pace: only the clean long-run laps count &mdash; in/out laps, traffic and lock-ups are filtered out the way a human reads them off a timing screen. Headline is the latest session that produced a long run (usually FP2). Click headers to sort.</p>${tbl.getHtml()}</div>`;
        postRenderFns.push(tbl.renderTable);

        // Long Run Detail — the laps behind each average (kept vs X'd outliers).
        const detailCards = rows.slice().sort((a, b) => a.avg_pace - b.avg_pace).filter(r => r.runs.length).map(r => {
            const runsHtml = r.runs.slice()
                .sort((a, b) => (SESS_RANK[a.session] || 0) - (SESS_RANK[b.session] || 0))
                .map(run => {
                    const kept = (run.kept_laps || []).map(t => `<span class="lr-lap kept">${fmtTime(t)}</span>`).join('');
                    const excl = (run.excluded_laps || []).map(t => `<span class="lr-lap excl" title="Excluded: in/out lap, traffic or lock-up">${fmtTime(t)}</span>`).join('');
                    return `<div class="lr-run">
                        <span class="compound-badge ${run.compound.toLowerCase()}">${run.session} ${run.compound}</span>
                        <span class="lr-laps">${kept}${excl}</span>
                        <span class="lr-avg">${fmtTime(run.avg_pace)} <span class="lr-ctx">${run.laps}L</span></span>
                    </div>`;
                }).join('');
            return `<div class="lr-card">
                <div class="lr-head"><strong>${r.id}</strong><span class="lr-headavg">${fmtTime(r.avg_pace)}</span>${r.gap <= 0 ? '<span class="text-green lr-headgap">Leader</span>' : `<span class="lr-headgap">+${r.gap.toFixed(3)}</span>`}</div>
                ${runsHtml}
            </div>`;
        }).join('');
        html += `<div class="analysis-block"><h3>Long Run Detail</h3><p class="analysis-note">The laps behind each driver's race-pace number. <span class="lr-lap excl" style="vertical-align:baseline">struck-through</span> laps were excluded as in/out laps, traffic or lock-ups; the rest form the run (the natural tyre-degradation tail is kept). The manual "X out the junk laps" long-run read, done automatically.</p><div class="lr-detail-grid">${detailCards}</div></div>`;
    }

    // Fuel-Corrected Pace
    if (fpAnalysis.fuel_corrected_pace && Object.keys(fpAnalysis.fuel_corrected_pace).length > 0) {
        const rows = Object.entries(fpAnalysis.fuel_corrected_pace).map(([id, d]) => ({
            id,
            avg_pace: d.fuel_corrected_avg ?? d.avg_corrected_pace ?? d.corrected_pace,
            best_pace: d.fuel_corrected_best,
            median_pace: d.fuel_corrected_median,
            laps: d.laps_used ?? d.laps ?? d.total_laps,
            correction: d.fuel_correction_per_lap ?? d.fuel_effect ?? d.correction,
            gap: d.gap_to_fastest || 0
        }));
        const tbl = sortableTable('fpFuelTable', [
            { key: '_rank', label: '#', cls: 'num', fmt: (r, i) => i + 1 },
            { key: 'id', label: 'Driver', fmt: r => `<strong>${r.id}</strong>` },
            { key: 'avg_pace', label: 'Avg (Corrected)', cls: 'num', title: 'Average lap time after fuel correction (lower = stronger underlying pace)', fmt: r => r.avg_pace ? fmtTime(r.avg_pace) : '-' },
            { key: 'best_pace', label: 'Best (Corrected)', cls: 'num', title: 'Best fuel-corrected lap', fmt: r => r.best_pace ? fmtTime(r.best_pace) : '-' },
            { key: 'median_pace', label: 'Median', cls: 'num', title: 'Median fuel-corrected lap', fmt: r => r.median_pace ? fmtTime(r.median_pace) : '-' },
            { key: 'gap', label: 'Gap', cls: 'num', title: 'Gap to fastest fuel-corrected average pace', fmt: r => r.gap === 0 ? '<span class="text-green">Leader</span>' : '+' + (r.gap || 0).toFixed(3) },
            { key: 'laps', label: 'Laps', cls: 'num', title: 'Laps used after outlier filtering' },
            { key: 'correction', label: 'Fuel/Lap', cls: 'num', title: 'Estimated seconds of fuel-weight effect removed per lap', fmt: r => r.correction ? r.correction.toFixed(3) + 's' : '-' }
        ], rows, 'avg_pace', true);
        html += `<div class="analysis-block"><h3>Fuel-Corrected Pace</h3><p class="analysis-note">Lap times adjusted for estimated fuel load to give a truer picture of underlying pace.</p>${tbl.getHtml()}</div>`;
        postRenderFns.push(tbl.renderTable);
    }

    // Tyre Degradation — fuel-corrected pace loss per lap of tyre age, from FP
    // long runs. Colour is FIELD-RELATIVE per compound (best third green, worst
    // third red) so it reads fairly whether the weekend is high- or low-deg.
    if (fpAnalysis.tyre_degradation && Object.keys(fpAnalysis.tyre_degradation).length > 0) {
        const roster = new Set((data && data.drivers ? data.drivers : []).map(d => d.driver_id));
        const entries = Object.entries(fpAnalysis.tyre_degradation);

        // Build per-compound sorted lists of fittable (non-null) deg values for
        // field-relative tercile colouring.
        const byCompound = {};
        entries.forEach(([id, compounds]) => {
            Object.entries(compounds).forEach(([comp, d]) => {
                if (d.avg_degradation != null) (byCompound[comp] = byCompound[comp] || []).push(d.avg_degradation);
            });
        });
        Object.values(byCompound).forEach(arr => arr.sort((a, b) => a - b));
        const degClass = (comp, deg) => {
            if (deg == null) return 'deg-none';
            if (deg < 0) return 'deg-none';                 // track evolving / fuel — not real tyre gain
            const arr = byCompound[comp] || [];
            if (arr.length < 3) return 'deg-ok';
            const rank = arr.filter(v => v < deg).length / arr.length;
            return rank < 0.34 ? 'deg-good' : rank < 0.67 ? 'deg-ok' : 'deg-bad';
        };
        // Sort: roster drivers with a real value first (lowest deg = best saver),
        // then roster "short runs only", then non-roster practice runners.
        const repDeg = compounds => {
            const vals = Object.values(compounds).map(d => d.avg_degradation).filter(v => v != null && v >= 0);
            return vals.length ? Math.min(...vals) : Infinity;
        };
        entries.sort((a, b) => {
            const ar = roster.has(a[0]) ? 0 : 1, br = roster.has(b[0]) ? 0 : 1;
            if (ar !== br) return ar - br;
            return repDeg(a[1]) - repDeg(b[1]);
        });

        html += `
        <div class="analysis-block">
            <h3>Tyre Degradation</h3>
            <p class="analysis-note">Fuel-corrected pace lost per lap of tyre age on this weekend's practice long runs &mdash; lower is a better tyre-saver (holds pace late &rarr; positions gained, less likely to be undercut). Colour is relative to the field on each compound. <strong>"track evolving"</strong> = the car got <em>faster</em> through the run (fuel burn / track rubbering in), not real tyre gain. Short, noisy runs (quali sims) are excluded.</p>
            <div class="deg-grid">${entries.map(([id, compounds]) => {
                const isRookie = !roster.has(id);
                const compoundEntries = Object.entries(compounds);
                return `
                <div class="deg-card${isRookie ? ' deg-rookie' : ''}">
                    <div class="deg-driver">${id}${isRookie ? ' <span class="deg-tag" title="Not in the current fantasy roster — practice/test runner">practice</span>' : ''}</div>
                    ${compoundEntries.map(([comp, d]) => {
                        const deg = d.avg_degradation;
                        const laps = d.deg_laps || 0;
                        const perStint = (d.stints || []).filter(s => s.deg_rate != null)
                            .map(s => `${s.session || ''} ${s.deg_rate >= 0 ? '+' : ''}${s.deg_rate.toFixed(2)} (${s.laps}L)`).join(', ');
                        let valHtml;
                        if (deg == null) {
                            valHtml = `<span class="deg-rate deg-none" title="No clean long run (5+ laps) on this compound — quali sims only">short runs only</span>`;
                        } else if (deg < 0) {
                            valHtml = `<span class="deg-rate deg-none" title="Car got faster over the run (fuel/track evolution), not real tyre gain. Based on ${laps} clean laps.">track evolving</span>`;
                        } else {
                            valHtml = `<span class="deg-rate ${degClass(comp, deg)}" title="Over a 10-lap stint that's ~${(deg * 10).toFixed(1)}s lost to tyre wear. Based on ${laps} clean laps${perStint ? ' — ' + perStint : ''}.">+${deg.toFixed(2)}<span class="deg-unit">s/lap</span> <span class="deg-ctx">${laps}L</span></span>`;
                        }
                        return `
                        <div class="deg-compound">
                            <span class="compound-badge ${comp.toLowerCase()}">${comp}</span>
                            ${valHtml}
                        </div>`;
                    }).join('')}
                </div>`;
            }).join('')}</div>
        </div>`;
    }

    // Stint Breakdown
    if (fpAnalysis.stint_breakdown && Object.keys(fpAnalysis.stint_breakdown).length > 0) {
        const sessionLabels = { FP1: 'FP1', FP2: 'FP2', FP3: 'FP3', SPRINT_QUALIFYING: 'Sprint Q' };
        const rows = [];
        Object.entries(fpAnalysis.stint_breakdown).forEach(([id, payload]) => {
            // payload is either { stints: [...], total_stints, avg_degradation } or a raw array (older shape)
            const stints = Array.isArray(payload) ? payload : (payload && Array.isArray(payload.stints) ? payload.stints : []);
            stints.forEach(s => {
                rows.push({
                    id,
                    stint: s.stint || s.stint_number || 0,
                    session: s.session || '',
                    compound: s.compound || '?',
                    laps: s.total_laps ?? s.laps ?? s.lap_count ?? 0,
                    avg_pace: s.avg_pace ?? s.avg_time ?? 0,
                    best_pace: s.best_pace ?? 0,
                    first_lap: s.first_lap_pace ?? s.first_lap ?? 0,
                    last_lap: s.last_lap_pace ?? s.last_lap ?? 0,
                    deg: s.degradation_rate ?? s.degradation ?? s.deg_rate ?? null
                });
            });
        });
        if (rows.length > 0) {
            const tbl = sortableTable('fpStintTable', [
                { key: 'id', label: 'Driver', fmt: r => `<strong>${r.id}</strong>` },
                { key: 'stint', label: 'Stint', cls: 'num', title: 'Stint number within the session' },
                { key: 'session', label: 'Session', title: 'Session this stint was run in', fmt: r => sessionLabels[r.session] || r.session || '-' },
                { key: 'compound', label: 'Tyre', title: 'Tyre compound used', fmt: r => `<span class="compound-badge ${r.compound.toLowerCase()}">${r.compound}</span>` },
                { key: 'laps', label: 'Laps', cls: 'num' },
                { key: 'avg_pace', label: 'Avg Pace', cls: 'num', title: 'Average lap time across the stint', fmt: r => r.avg_pace ? fmtTime(r.avg_pace) : '-' },
                { key: 'best_pace', label: 'Best', cls: 'num', title: 'Best lap in the stint', fmt: r => r.best_pace ? fmtTime(r.best_pace) : '-' },
                { key: 'first_lap', label: 'First Lap', cls: 'num', title: 'Pace of first timed lap in stint', fmt: r => r.first_lap ? fmtTime(r.first_lap) : '-' },
                { key: 'last_lap', label: 'Last Lap', cls: 'num', title: 'Pace of last lap in stint', fmt: r => r.last_lap ? fmtTime(r.last_lap) : '-' },
                { key: 'deg', label: 'Deg (s/lap)', cls: 'num', title: 'Fuel-corrected pace lost per lap of tyre age (robust linear fit). Blank = run too short/noisy to fit.', fmt: r => r.deg != null ? (r.deg >= 0 ? '+' : '') + r.deg.toFixed(2) : '-' }
            ], rows, 'avg_pace', true);
            html += `<div class="analysis-block"><h3>Stint Breakdown</h3><p class="analysis-note">Detailed per-stint data showing pace evolution and tyre degradation within each run.</p>${tbl.getHtml()}</div>`;
            postRenderFns.push(tbl.renderTable);
        }
    }

    // Consistency
    if (fpAnalysis.consistency && Object.keys(fpAnalysis.consistency).length > 0) {
        const rows = Object.entries(fpAnalysis.consistency).map(([id, d]) => ({
            id, cv: d.cv, std: d.std, pct102: d.laps_within_102pct, best_lap: d.best_lap, laps: d.total_laps
        }));
        const tbl = sortableTable('fpConsistencyTable', [
            { key: '_rank', label: '#', cls: 'num', fmt: (r, i) => i + 1 },
            { key: 'id', label: 'Driver', fmt: r => `<strong>${r.id}</strong>` },
            { key: 'cv', label: 'CV%', cls: 'num', title: 'Coefficient of Variation — lower = more consistent lap times', fmt: r => (r.cv * 100).toFixed(2) + '%' },
            { key: 'std', label: 'Std Dev', cls: 'num', title: 'Standard deviation of lap times in seconds', fmt: r => r.std.toFixed(3) + 's' },
            { key: 'pct102', label: 'Within 102%', cls: 'num', title: 'Percentage of laps within 102% of personal best', fmt: r => r.pct102.toFixed(0) + '%' },
            { key: 'best_lap', label: 'Best Lap', cls: 'num', fmt: r => fmtTime(r.best_lap) },
            { key: 'laps', label: 'Laps', cls: 'num' }
        ], rows, 'cv', true);
        html += `<div class="analysis-block"><h3>Consistency</h3><p class="analysis-note">How repeatable a driver's lap times are. Low CV% = consistent, high Within 102% = staying near their best pace.</p>${tbl.getHtml()}</div>`;
        postRenderFns.push(tbl.renderTable);
    }

    // Sector Rankings
    if (fpAnalysis.sector_rankings && Object.keys(fpAnalysis.sector_rankings).length > 0) {
        html += `<div class="analysis-block"><h3>Sector Rankings</h3><p class="analysis-note">Fastest drivers in each sector. Shows raw best sector times.</p>`;
        for (const [sector, rankings] of Object.entries(fpAnalysis.sector_rankings)) {
            const label = sector.replace('sector_', 'Sector ').replace('s1', 'Sector 1').replace('s2', 'Sector 2').replace('s3', 'Sector 3');
            html += `<h4 style="margin:8px 0 4px">${label}</h4><table class="data-table"><thead><tr><th>#</th><th>Driver</th><th class="num">Best</th><th class="num">Gap</th></tr></thead><tbody>`;
            const items = Array.isArray(rankings) ? rankings : Object.entries(rankings).map(([id, d]) => ({driver: id, ...d}));
            items.forEach((r, i) => {
                const id = r.driver || r.driver_id || r.id || '?';
                const best = r.best || r.time || 0;
                const gap = r.gap || r.gap_to_fastest || 0;
                html += `<tr><td>${i+1}</td><td><strong>${id}</strong></td><td class="num">${best.toFixed(3)}s</td><td class="num">${gap === 0 ? '<span class="text-green">Leader</span>' : '+' + gap.toFixed(3)}</td></tr>`;
            });
            html += `</tbody></table>`;
        }
        html += `</div>`;
    }

    // Session Evolution — adapts to whichever sessions are present
    // (FP1/FP2/FP3 on regular weekends, FP1 + Sprint Qualifying on sprint weekends).
    if (fpAnalysis.session_evolution && Object.keys(fpAnalysis.session_evolution).length > 0) {
        const sessionLabels = { FP1: 'FP1', FP2: 'FP2', FP3: 'FP3', SPRINT_QUALIFYING: 'Sprint Quali' };
        const sessionOrder = ['FP1', 'FP2', 'FP3', 'SPRINT_QUALIFYING'];
        const presentSessions = new Set();
        Object.values(fpAnalysis.session_evolution).forEach(d => {
            Object.keys(d.sessions || {}).forEach(s => presentSessions.add(s));
        });
        const cols = sessionOrder.filter(s => presentSessions.has(s));
        const rows = Object.entries(fpAnalysis.session_evolution).map(([id, d]) => {
            const r = { id, improvement: d.improvement || 0, improved: d.improved };
            cols.forEach(s => { r[s] = d.sessions[s] || null; });
            return r;
        });
        const colDefs = [
            { key: '_rank', label: '#', cls: 'num', fmt: (r, i) => i + 1 },
            { key: 'id', label: 'Driver', fmt: r => `<strong>${r.id}</strong>` },
            ...cols.map(s => ({ key: s, label: sessionLabels[s] || s, cls: 'num', fmt: r => r[s] ? fmtTime(r[s]) : '-' })),
            { key: 'improvement', label: 'Improvement', cls: 'num', title: 'Pace gain from first to last session. Negative = got faster.', fmt: r => `<span class="${r.improved ? 'text-green' : 'text-red'}">${r.improvement > 0 ? '-' : '+'}${Math.abs(r.improvement).toFixed(3)}s</span>` }
        ];
        const tbl = sortableTable('fpEvoTable', colDefs, rows, 'improvement', false);
        const headerLabel = cols.map(s => sessionLabels[s] || s).join(' → ');
        html += `<div class="analysis-block"><h3>Session Evolution (${headerLabel})</h3><p class="analysis-note">How drivers improved their pace across on-track sessions. Negative number = got faster.</p>${tbl.getHtml()}</div>`;
        postRenderFns.push(tbl.renderTable);
    }

    el.innerHTML = html;

    // Run all post-render functions to populate sortable tables
    postRenderFns.forEach(fn => fn());

    // Wire up driver filter
    const filterInput = document.getElementById('fpDriverFilter');
    if (filterInput) {
        filterInput.addEventListener('input', () => {
            const q = filterInput.value.toUpperCase().trim();
            el.querySelectorAll('.data-table tbody tr').forEach(tr => {
                const driverCell = tr.querySelector('td:nth-child(1) strong, td:nth-child(2) strong');
                if (!driverCell) { tr.style.display = ''; return; }
                tr.style.display = driverCell.textContent.toUpperCase().includes(q) || !q ? '' : 'none';
            });
            el.querySelectorAll('.deg-card').forEach(card => {
                const name = card.querySelector('.deg-driver')?.textContent?.toUpperCase() || '';
                card.style.display = name.includes(q) || !q ? '' : 'none';
            });
        });
    }
}

// -- Post-Race --
function renderPostRace(postRaceData, predictions, actual, roundNum) {
    const el = document.getElementById('postRaceContent');

    // Handle legacy calls with just one argument
    if (!postRaceData && !predictions && !actual) {
        el.innerHTML = '<p class="no-data">No post-race analysis for this round.</p>';
        return;
    }

    let html = '';

    // --- Predicted vs Actual Comparison ---
    if (predictions && actual && actual.drivers) {
        const raceName = actual.race || predictions.race || `Round ${roundNum}`;
        html += `<div class="analysis-race-header">${raceName} — Predicted vs Actual</div>`;
        html += renderComparison(predictions, actual);
    }

    // --- Original post-race analysis (if available) ---
    const prData = postRaceData;
    if (prData) {
        if (!html) {
            html += `<div class="analysis-race-header">${prData.race} — Round ${prData.round}</div>`;
        }

        // Race Results as driver cards
        if (prData.results && prData.results.length > 0) {
            html += `
            <div class="analysis-block collapsible">
                <h3 class="collapsible-header" onclick="this.parentElement.classList.toggle('collapsed')">Race Results <span class="collapse-icon">▼</span></h3>
                <div class="collapsible-content">
                <div class="postrace-cards">
                    ${prData.results.map(r => {
                        const team = TEAMS[r.constructor_id] || { name: r.constructor_id, color: '#666' };
                        const posChange = r.positions_gained || 0;
                        const changeClass = posChange > 0 ? 'positive' : posChange < 0 ? 'negative' : 'neutral';
                        const changeText = posChange > 0 ? `+${posChange}` : `${posChange}`;
                        const finished = r.is_finished || (r.finish_position != null);
                        return `
                        <div class="postrace-card" style="--team-color:${team.color}">
                            <div class="pr-header">
                                <div>
                                    <div class="pr-driver">${r.driver_id}</div>
                                    <div class="pr-team">${team.name}</div>
                                </div>
                                <div class="pr-position ${!finished ? 'dnf' : ''}">${finished ? 'P' + r.finish_position : r.status || 'DNF'}</div>
                            </div>
                            <div class="pr-stats">
                                <div>Grid: <span class="pr-stat-value">P${r.grid}</span></div>
                                <div>Change: <span class="pr-change ${changeClass}">${changeText}</span></div>
                                <div>Points: <span class="pr-points">${r.points}</span></div>
                                <div>Status: <span class="pr-stat-value">${r.is_finished ? 'Finished' : r.status}</span></div>
                            </div>
                        </div>`;
                    }).join('')}
                </div>
                </div>
            </div>`;
        }
    } else if (!predictions && !actual) {
        el.innerHTML = '<p class="no-data">No post-race analysis for this round.</p>';
        return;
    } else if (!html) {
        // We have predictions but no actual, or actual but no predictions
        const source = predictions || actual;
        const raceName = source.race || `Round ${roundNum}`;
        html += `<div class="analysis-race-header">${raceName} — Round ${roundNum}</div>`;
        if (predictions && !actual) {
            html += '<p class="no-data">Predictions available but no actual results yet. Check back after the race.</p>';
            // Show predictions summary
            if (predictions.drivers) {
                html += renderPredictionsSummary(predictions);
            }
        }
        if (actual && !predictions) {
            html += '<p class="no-data">Actual results available but no predictions were made for this round.</p>';
        }
    }

    // Race Pace
    if (prData && prData.race_pace && Object.keys(prData.race_pace).length > 0) {
        const sorted = Object.entries(prData.race_pace)
            .sort((a,b) => a[1].avg_race_pace - b[1].avg_race_pace);

        html += `
        <div class="analysis-block collapsible">
            <h3 class="collapsible-header" onclick="this.parentElement.classList.toggle('collapsed')">Normalized Race Pace <span class="collapse-icon">▼</span></h3>
            <div class="collapsible-content">
            <table class="data-table sortable">
                <thead><tr>
                    <th>#</th><th>Driver</th><th class="num">Avg Pace</th>
                    <th class="num">Median</th><th class="num">Best Lap</th>
                    <th class="num">Delta</th><th class="num">Consistency</th>
                    <th class="num">Laps</th>
                </tr></thead>
                <tbody>${sorted.map(([id, d], i) => `
                    <tr>
                        <td>${i+1}</td>
                        <td><strong>${id}</strong></td>
                        <td class="num">${fmtTime(d.avg_race_pace)}</td>
                        <td class="num">${fmtTime(d.median_race_pace)}</td>
                        <td class="num">${fmtTime(d.best_race_lap)}</td>
                        <td class="num ${d.pace_delta_to_leader === 0 ? 'text-green' : ''}">${d.pace_delta_to_leader === 0 ? 'Leader' : '+' + d.pace_delta_to_leader.toFixed(3)}</td>
                        <td class="num">${d.consistency_std.toFixed(3)}s</td>
                        <td class="num">${d.laps_analyzed}</td>
                    </tr>`).join('')}
                </tbody>
            </table>
            </div>
        </div>`;
    }

    // Pit Stops by Team — wheels-up (stationary) service time, the metric F1
    // Fantasy scores. Sourced from the same OpenF1 data as the Constructors panel,
    // NOT Jolpica's pit-stop "duration" (full pit-lane transit, ~20s).
    const roundPits = getRoundPitStops(roundNum);
    if (roundPits && roundPits.length > 0) {
        html += `
        <div class="analysis-block collapsible">
            <h3 class="collapsible-header" onclick="this.parentElement.classList.toggle('collapsed')">Pit Stop Performance <span class="collapse-icon">▼</span></h3>
            <div class="collapsible-content">
            <table class="data-table sortable">
                <thead><tr>
                    <th>#</th><th>Team</th><th class="num">Avg Stationary</th>
                    <th class="num">Best Stationary</th><th class="num">Stops</th>
                </tr></thead>
                <tbody>${roundPits.map((t, i) => `
                    <tr>
                        <td>${i+1}</td>
                        <td><strong>${t.name}</strong></td>
                        <td class="num">${t.avg != null ? t.avg.toFixed(1) + 's' : 'n/a'}</td>
                        <td class="num">${t.best != null ? t.best.toFixed(1) + 's' : 'n/a'}</td>
                        <td class="num">${t.totalStops}${t.missing ? ` <span style="color:var(--text-muted);font-size:0.9em;" title="${t.missing} stop(s) without a recorded stationary time — typically safety car / VSC, retirements, or penalty stops">(${t.missing} n/a)</span>` : ''}</td>
                    </tr>`).join('')}
                </tbody>
            </table>
            <p class="analysis-note"><strong>Stationary time</strong> = wheels-up service time (the F1 Fantasy scoring metric), not the full pit-lane time. Refreshes 24–48h post-race as public timing feeds catch up.</p>
            </div>
        </div>`;
    } else if (prData && prData.pitstops && prData.pitstops.by_team && prData.pitstops.by_team.length > 0) {
        // Jolpica has pit data but the OpenF1 wheels-up times aren't in yet — show
        // an honest note rather than the misleading ~20s pit-lane average.
        html += `
        <div class="analysis-block collapsible">
            <h3 class="collapsible-header" onclick="this.parentElement.classList.toggle('collapsed')">Pit Stop Performance <span class="collapse-icon">▼</span></h3>
            <div class="collapsible-content">
            <p class="no-data">Wheels-up (stationary) pit stop times for this round aren't published yet — they land 24–48h after the race as public timing feeds catch up. Season-wide stationary times are on the Constructors tab.</p>
            </div>
        </div>`;
    }

    // Tyre Management
    if (prData && prData.tyre_management && Object.keys(prData.tyre_management).length > 0) {
        const sorted = Object.entries(prData.tyre_management)
            .sort((a,b) => b[1].management_score - a[1].management_score);

        html += `
        <div class="analysis-block collapsible">
            <h3 class="collapsible-header" onclick="this.parentElement.classList.toggle('collapsed')">Tyre Management <span class="collapse-icon">▼</span></h3>
            <div class="collapsible-content">
            <table class="data-table sortable">
                <thead><tr>
                    <th>#</th><th>Driver</th><th class="num">Score</th>
                    <th class="num">Avg Deg</th><th>Stints</th>
                </tr></thead>
                <tbody>${sorted.map(([id, d], i) => `
                    <tr>
                        <td>${i+1}</td>
                        <td><strong>${id}</strong></td>
                        <td class="num"><span class="mgmt-score ${d.management_score >= 70 ? 'score-good' : d.management_score >= 40 ? 'score-ok' : 'score-bad'}">${d.management_score}/100</span></td>
                        <td class="num">${d.avg_degradation != null ? d.avg_degradation.toFixed(2) + 's/lap' : '-'}</td>
                        <td>${d.stints.map(s => `<span class="compound-badge ${s.compound.toLowerCase()}">${s.compound} (${s.laps}L)</span>`).join(' ')}</td>
                    </tr>`).join('')}
                </tbody>
            </table>
            </div>
        </div>`;
    }

    // ── Sprint Weekend sections ──
    if (prData && prData.is_sprint_weekend) {
        html += `<div class="sprint-divider"><span>🏁 Sprint Session</span></div>`;

        // Sprint Results
        if (prData.sprint_results && prData.sprint_results.length > 0) {
            html += `
            <div class="analysis-block collapsible">
                <h3 class="collapsible-header" onclick="this.parentElement.classList.toggle('collapsed')">Sprint Results <span class="collapse-icon">▼</span></h3>
                <div class="collapsible-content">
                <div class="postrace-cards">
                    ${prData.sprint_results.map(r => {
                        const team = TEAMS[r.constructor_id] || { name: r.constructor_id, color: '#666' };
                        const posChange = r.positions_gained || 0;
                        const changeClass = posChange > 0 ? 'positive' : posChange < 0 ? 'negative' : 'neutral';
                        const changeText = posChange > 0 ? '+' + posChange : '' + posChange;
                        const finished = r.is_finished || (r.finish_position != null);
                        return `
                        <div class="postrace-card" style="--team-color:${team.color}">
                            <div class="pr-header">
                                <div>
                                    <div class="pr-driver">${r.driver_id}</div>
                                    <div class="pr-team">${team.name}</div>
                                </div>
                                <div class="pr-position ${!finished ? 'dnf' : ''}">${finished ? 'P' + r.finish_position : r.status || 'DNF'}</div>
                            </div>
                            <div class="pr-stats">
                                <div>Grid: <span class="pr-stat-value">P${r.grid}</span></div>
                                <div>Change: <span class="pr-change ${changeClass}">${changeText}</span></div>
                                <div>Points: <span class="pr-points">${r.points}</span></div>
                                <div>Status: <span class="pr-stat-value">${r.is_finished ? 'Finished' : r.status}</span></div>
                            </div>
                        </div>`;
                    }).join('')}
                </div>
                </div>
            </div>`;
        }

        // Sprint Race Pace
        if (prData.sprint_pace && Object.keys(prData.sprint_pace).length > 0) {
            const sorted = Object.entries(prData.sprint_pace)
                .sort((a,b) => a[1].avg_race_pace - b[1].avg_race_pace);

            html += `
            <div class="analysis-block collapsible">
                <h3 class="collapsible-header" onclick="this.parentElement.classList.toggle('collapsed')">Sprint Race Pace <span class="collapse-icon">▼</span></h3>
                <div class="collapsible-content">
                <table class="data-table sortable">
                    <thead><tr>
                        <th>#</th><th>Driver</th><th class="num">Avg Pace</th>
                        <th class="num">Median</th><th class="num">Best Lap</th>
                        <th class="num">Delta</th><th class="num">Consistency</th>
                        <th class="num">Laps</th>
                    </tr></thead>
                    <tbody>${sorted.map(([id, d], i) => `
                        <tr>
                            <td>${i+1}</td>
                            <td><strong>${id}</strong></td>
                            <td class="num">${fmtTime(d.avg_race_pace)}</td>
                            <td class="num">${fmtTime(d.median_race_pace)}</td>
                            <td class="num">${fmtTime(d.best_race_lap)}</td>
                            <td class="num ${d.pace_delta_to_leader === 0 ? 'text-green' : ''}">${d.pace_delta_to_leader === 0 ? 'Leader' : '+' + d.pace_delta_to_leader.toFixed(3)}</td>
                            <td class="num">${d.consistency_std.toFixed(3)}s</td>
                            <td class="num">${d.laps_analyzed}</td>
                        </tr>`).join('')}
                    </tbody>
                </table>
                </div>
            </div>`;
        }

        // Sprint Tyre Management
        if (prData.sprint_tyre_management && Object.keys(prData.sprint_tyre_management).length > 0) {
            const sorted = Object.entries(prData.sprint_tyre_management)
                .sort((a,b) => b[1].management_score - a[1].management_score);

            html += `
            <div class="analysis-block collapsible">
                <h3 class="collapsible-header" onclick="this.parentElement.classList.toggle('collapsed')">Sprint Tyre Management <span class="collapse-icon">▼</span></h3>
                <div class="collapsible-content">
                <table class="data-table sortable">
                    <thead><tr>
                        <th>#</th><th>Driver</th><th class="num">Score</th>
                        <th class="num">Avg Deg</th><th>Stints</th>
                    </tr></thead>
                    <tbody>${sorted.map(([id, d], i) => `
                        <tr>
                            <td>${i+1}</td>
                            <td><strong>${id}</strong></td>
                            <td class="num"><span class="mgmt-score ${d.management_score >= 70 ? 'score-good' : d.management_score >= 40 ? 'score-ok' : 'score-bad'}">${d.management_score}/100</span></td>
                            <td class="num">${d.avg_degradation != null ? d.avg_degradation.toFixed(2) + 's/lap' : '-'}</td>
                            <td>${d.stints.map(s => `<span class="compound-badge ${s.compound.toLowerCase()}">${s.compound} (${s.laps}L)</span>`).join(' ')}</td>
                        </tr>`).join('')}
                    </tbody>
                </table>
                </div>
            </div>`;
        }
    }

    el.innerHTML = html;

    // Make all sortable tables interactive
    el.querySelectorAll('table.sortable').forEach(makeTableSortable);
}

function renderComparison(predictions, actual) {
    // Build lookup maps
    const predDrivers = {};
    if (predictions.drivers) {
        predictions.drivers.forEach(d => {
            predDrivers[d.driver_id] = d;
        });
    }
    const actualDrivers = {};
    if (actual.drivers) {
        actual.drivers.forEach(d => {
            actualDrivers[d.driver_id] = d;
        });
    }

    // Merge all driver IDs
    const allIds = [...new Set([...Object.keys(predDrivers), ...Object.keys(actualDrivers)])];

    // Build comparison rows
    const rows = [];
    let totalAbsError = 0;
    let countCompared = 0;
    let within1 = 0;
    let totalPredPts = 0;
    let totalActualPts = 0;
    let totalPtsAbsError = 0;
    let ptsCompared = 0;
    let inCI = 0;
    let ciTotal = 0;
    let inCI50 = 0;
    let ciTotal50 = 0;
    let within5pts = 0;
    let within10pts = 0;

    allIds.forEach(id => {
        const pred = predDrivers[id];
        const act = actualDrivers[id];
        if (!pred || !act) return;

        const predQuali = pred.predicted_quali;
        const actQuali = act.quali_position;
        const predRace = pred.predicted_finish;
        const actRace = act.race_position;
        const predPts = pred.expected_points || 0;
        const actPts = act.total_points || 0;
        const ptsDiff = actPts - predPts;

        // MC data if available
        const mcMean = pred.mc_total_mean;
        const mcP5 = pred.mc_total_p5;
        const mcP25 = pred.mc_total_p25;
        const mcP75 = pred.mc_total_p75;
        const mcP95 = pred.mc_total_p95;
        const withinCI = (mcP5 != null && mcP95 != null) ? (actPts >= mcP5 && actPts <= mcP95) : null;
        const withinCI50 = (mcP25 != null && mcP75 != null) ? (actPts >= mcP25 && actPts <= mcP75) : null;

        if (withinCI !== null) {
            ciTotal++;
            if (withinCI) inCI++;
        }
        if (withinCI50 !== null) {
            ciTotal50++;
            if (withinCI50) inCI50++;
        }

        const qualiDiff = actQuali != null && predQuali != null ? Math.abs(actQuali - predQuali) : null;
        const raceDiff = actRace != null && predRace != null ? Math.abs(actRace - predRace) : null;

        if (raceDiff != null) {
            totalAbsError += raceDiff;
            countCompared++;
            if (raceDiff <= 1) within1++;
        }

        totalPredPts += predPts;
        totalActualPts += actPts;
        totalPtsAbsError += Math.abs(ptsDiff);
        ptsCompared++;
        if (Math.abs(ptsDiff) <= 5) within5pts++;
        if (Math.abs(ptsDiff) <= 10) within10pts++;

        rows.push({
            id,
            name: pred.name || id,
            constructor: pred.constructor || '',
            predQuali,
            actQuali,
            qualiDiff,
            predRace,
            actRace,
            raceDiff,
            predPts,
            actPts,
            ptsDiff,
            mcMean,
            mcP5,
            mcP95,
            withinCI,
            actOvertakes: act.overtakes,
            overtakeSource: act.overtake_source,
            predOvertakes: pred.expected_overtakes,
        });
    });

    // Sort by actual total points descending
    rows.sort((a, b) => (b.actPts) - (a.actPts));

    const mae = countCompared > 0 ? (totalAbsError / countCompared) : 0;
    const within1Pct = countCompared > 0 ? (within1 / countCompared * 100) : 0;
    const ptsMae = ptsCompared > 0 ? (totalPtsAbsError / ptsCompared) : 0;
    const within10Pct = ptsCompared > 0 ? (within10pts / ptsCompared * 100) : 0;
    const ciCoverage = ciTotal > 0 ? (inCI / ciTotal * 100) : null;
    const ciCoverage50 = ciTotal50 > 0 ? (inCI50 / ciTotal50 * 100) : null;

    function posColorClass(diff) {
        if (diff == null) return '';
        if (diff <= 2) return 'cmp-green';
        if (diff <= 4) return 'cmp-yellow';
        return 'cmp-red';
    }

    function ptsColorClass(diff) {
        if (diff == null) return '';
        const abs = Math.abs(diff);
        if (abs <= 5) return 'cmp-green';
        if (abs <= 10) return 'cmp-yellow';
        return 'cmp-red';
    }

    let html = '';

    // Model accuracy summary
    html += `
    <div class="analysis-block">
        <h3>Model Accuracy</h3>
        <div class="accuracy-summary">
            <div class="accuracy-stat">
                <div class="accuracy-value">${mae.toFixed(1)}</div>
                <div class="accuracy-label" title="Mean Absolute Error: average number of positions our prediction was off by. Lower is better.">Position MAE</div>
            </div>
            <div class="accuracy-stat">
                <div class="accuracy-value">${within1Pct.toFixed(0)}%</div>
                <div class="accuracy-label" title="Percentage of race finish predictions within 1 position of actual result">Within ±1 position</div>
            </div>
            <div class="accuracy-stat">
                <div class="accuracy-value">${ptsMae.toFixed(1)}</div>
                <div class="accuracy-label" title="Mean Absolute Error for fantasy points prediction. Lower means our point estimates were more accurate.">Fantasy Points MAE</div>
            </div>
            <div class="accuracy-stat">
                <div class="accuracy-value">${within10Pct.toFixed(0)}%</div>
                <div class="accuracy-label" title="Percentage of drivers whose predicted fantasy points were within 10 points of actual">Within ±10 pts</div>
            </div>
            ${ciCoverage !== null ? `
            <div class="accuracy-stat">
                <div class="accuracy-value">${ciCoverage.toFixed(0)}%</div>
                <div class="accuracy-label" title="Percentage of actual results falling within the Monte Carlo 90% confidence interval (p5 to p95). Target: 90%.">90% CI Coverage (${inCI}/${ciTotal})</div>
            </div>` : ''}
            ${ciCoverage50 !== null ? `
            <div class="accuracy-stat">
                <div class="accuracy-value">${ciCoverage50.toFixed(0)}%</div>
                <div class="accuracy-label" title="Percentage of actual results falling within the Monte Carlo 50% confidence interval (p25 to p75). Target: 50%.">50% CI Coverage (${inCI50}/${ciTotal50})</div>
            </div>` : ''}
            <div class="accuracy-stat">
                <div class="accuracy-value" style="font-size:1.2rem">${totalPredPts.toFixed(0)} → ${totalActualPts.toFixed(0)}</div>
                <div class="accuracy-label">Pred vs Actual Total</div>
            </div>
        </div>
    </div>`;

    // Comparison table
    const hasMC = rows.some(r => r.mcMean != null);
    html += `
    <div class="analysis-block collapsible">
        <h3 class="collapsible-header" onclick="this.parentElement.classList.toggle('collapsed')">Predicted vs Actual — Driver Comparison <span class="collapse-icon">▼</span></h3>
        <div class="collapsible-content">
        <table class="data-table sortable">
            <thead><tr>
                <th>Driver</th><th>Team</th>
                <th class="num">Pred Q</th><th class="num">Act Q</th><th class="num">Δ</th>
                <th class="num">Pred R</th><th class="num">Act R</th><th class="num">Δ</th>
                <th class="num" title="Predicted overtakes">Pred OT</th><th class="num" title="Actual overtakes (source: detected from OpenF1 or estimated)">Act OT</th>
                <th class="num">Pred Pts</th>${hasMC ? '<th class="num">MC Mean</th>' : ''}
                <th class="num">Act Pts</th><th class="num">Pts Δ</th>
                ${hasMC ? '<th class="num">90% CI</th><th class="num">In CI</th>' : ''}
            </tr></thead>
            <tbody>${rows.map(r => {
                const team = TEAMS[r.constructor] || { name: r.constructor, color: '#666' };
                const qClass = posColorClass(r.qualiDiff);
                const rClass = posColorClass(r.raceDiff);
                const pClass = ptsColorClass(r.ptsDiff);
                const ciStr = (r.mcP5 != null && r.mcP95 != null) ? `${r.mcP5.toFixed(0)}–${r.mcP95.toFixed(0)}` : '-';
                const ciClass = r.withinCI === true ? 'cmp-green' : r.withinCI === false ? 'cmp-red' : '';
                return `
                <tr>
                    <td><strong>${r.name}</strong></td>
                    <td><span class="team-dot" style="background:${team.color}"></span>${team.name}</td>
                    <td class="num">${r.predQuali != null ? 'P' + r.predQuali : '-'}</td>
                    <td class="num">${r.actQuali != null ? 'P' + r.actQuali : '-'}</td>
                    <td class="num ${qClass}">${r.qualiDiff != null ? r.qualiDiff : '-'}</td>
                    <td class="num">${r.predRace != null ? 'P' + r.predRace : '-'}</td>
                    <td class="num">${r.actRace != null ? 'P' + r.actRace : '-'}</td>
                    <td class="num ${rClass}">${r.raceDiff != null ? r.raceDiff : '-'}</td>
                    <td class="num">${r.predOvertakes != null ? r.predOvertakes : '-'}</td>
                    <td class="num" title="${r.overtakeSource || ''}">${r.actOvertakes != null ? r.actOvertakes : '-'}${r.overtakeSource === 'detected' ? '' : r.overtakeSource === 'estimated' ? '*' : ''}</td>
                    <td class="num">${r.predPts.toFixed(1)}</td>
                    ${hasMC ? `<td class="num">${r.mcMean != null ? r.mcMean.toFixed(1) : '-'}</td>` : ''}
                    <td class="num"><strong>${r.actPts.toFixed(1)}</strong></td>
                    <td class="num ${pClass}">${r.ptsDiff >= 0 ? '+' : ''}${r.ptsDiff.toFixed(1)}</td>
                    ${hasMC ? `<td class="num">${ciStr}</td><td class="num ${ciClass}">${r.withinCI === true ? '✓' : r.withinCI === false ? '✗' : '-'}</td>` : ''}
                </tr>`;
            }).join('')}
            </tbody>
        </table>
        </div>
    </div>`;

    return html;
}

function renderPredictionsSummary(predictions) {
    if (!predictions.drivers || predictions.drivers.length === 0) return '';
    const sorted = [...predictions.drivers].sort((a, b) => a.predicted_finish - b.predicted_finish);

    return `
    <div class="analysis-block">
        <h3>Predictions Summary</h3>
        <table class="data-table">
            <thead><tr>
                <th>#</th><th>Driver</th><th>Team</th>
                <th class="num">Pred Quali</th><th class="num">Pred Race</th><th class="num">Exp Pts</th>
            </tr></thead>
            <tbody>${sorted.map((d, i) => {
                const team = TEAMS[d.constructor] || { name: d.constructor, color: '#666' };
                return `
                <tr>
                    <td>${i + 1}</td>
                    <td><strong>${d.name}</strong></td>
                    <td><span class="team-dot" style="background:${team.color}"></span>${team.name}</td>
                    <td class="num">P${d.predicted_quali}</td>
                    <td class="num">P${d.predicted_finish}</td>
                    <td class="num">${d.expected_points.toFixed(1)}</td>
                </tr>`;
            }).join('')}
            </tbody>
        </table>
    </div>`;
}

// -- Season --
// F1 2026 WDC points: P1=25, P2=18, P3=15, P4=12, P5=10, P6=8, P7=6, P8=4, P9=2, P10=1
// Sprint points: P1=8, P2=7, P3=6, P4=5, P5=4, P6=3, P7=2, P8=1
const WDC_RACE_PTS = { 1:25, 2:18, 3:15, 4:12, 5:10, 6:8, 7:6, 8:4, 9:2, 10:1 };
const WDC_SPRINT_PTS = { 1:8, 2:7, 3:6, 4:5, 5:4, 6:3, 7:2, 8:1 };
// Note: Fastest lap bonus removed from F1 regulations starting 2026

function renderChampionshipStandings() {
    const el = document.getElementById('championshipStandings');
    if (!el) return;

    const driverChamp = {};
    const constructorChamp = {};
    const completedRounds = [];

    // Gather data from all actual rounds
    for (const [rn, actData] of Object.entries(actualCache)) {
        if (!actData || !actData.drivers) continue;
        const roundNum = Number(rn);
        const roundInfo = seasonSummary?.rounds?.find(r => r.round === roundNum);
        const roundName = roundInfo?.name || actData.race || `Round ${roundNum}`;
        completedRounds.push({ round: roundNum, name: roundName, isSprint: !!actData.is_sprint_weekend });

        actData.drivers.forEach(d => {
            if (!driverChamp[d.driver_id]) {
                driverChamp[d.driver_id] = { name: d.name, constructor: d.constructor, total: 0, rounds: {} };
            }
            let rPts = 0;
            // Race points
            if (d.race_position && WDC_RACE_PTS[d.race_position]) {
                rPts += WDC_RACE_PTS[d.race_position];
            }
            // Sprint points
            let sPts = 0;
            if (d.sprint_position && WDC_SPRINT_PTS[d.sprint_position]) {
                sPts = WDC_SPRINT_PTS[d.sprint_position];
            }
            const totalRound = rPts + sPts;
            driverChamp[d.driver_id].total += totalRound;
            driverChamp[d.driver_id].rounds[roundNum] = { race: rPts, sprint: sPts, total: totalRound };

            // Constructor
            const cid = d.constructor;
            if (!constructorChamp[cid]) {
                constructorChamp[cid] = { total: 0, rounds: {} };
            }
            constructorChamp[cid].total += totalRound;
            if (!constructorChamp[cid].rounds[roundNum]) constructorChamp[cid].rounds[roundNum] = 0;
            constructorChamp[cid].rounds[roundNum] += totalRound;
        });
    }

    completedRounds.sort((a, b) => a.round - b.round);

    if (completedRounds.length === 0) {
        el.innerHTML = '<p class="no-data">No race results available yet.</p>';
        return;
    }

    const sortedDrivers = Object.entries(driverChamp).sort((a, b) => b[1].total - a[1].total);
    const sortedConstructors = Object.entries(constructorChamp).sort((a, b) => b[1].total - a[1].total);
    const leader = sortedDrivers.length > 0 ? sortedDrivers[0][1].total : 0;
    const cLeader = sortedConstructors.length > 0 ? sortedConstructors[0][1].total : 0;

    let html = `<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;">`;

    // WDC
    html += `<div>
        <h4 style="margin-bottom:12px;">Drivers' Championship</h4>
        <table class="data-table sortable">
            <thead><tr>
                <th>#</th><th>Driver</th><th>Team</th>`;
    completedRounds.forEach(r => {
        html += `<th class="num" title="${r.name}">R${r.round}</th>`;
    });
    html += `<th class="num">Total</th><th class="num">Gap</th>
            </tr></thead><tbody>`;
    sortedDrivers.forEach(([id, d], i) => {
        const team = TEAMS[d.constructor] || { name: d.constructor, color: '#666' };
        const gap = i === 0 ? '-' : `${d.total - leader}`;
        html += `<tr>
            <td>${i + 1}</td>
            <td><strong>${d.name || id}</strong></td>
            <td><span class="team-dot" style="background:${team.color}"></span>${team.name}</td>`;
        completedRounds.forEach(r => {
            const rData = d.rounds[r.round];
            const pts = rData ? rData.total : 0;
            const cls = pts >= 25 ? 'color:var(--green);font-weight:700' : pts >= 10 ? 'color:var(--text)' : pts > 0 ? '' : 'color:var(--text-muted)';
            html += `<td class="num" style="${cls}" title="R${r.round}: Race ${rData?.race || 0}${rData?.sprint ? ' + Sprint ' + rData.sprint : ''}">${pts}</td>`;
        });
        html += `<td class="num"><strong>${d.total}</strong></td>
            <td class="num" style="color:var(--text-secondary)">${gap}</td>
        </tr>`;
    });
    html += `</tbody></table></div>`;

    // WCC
    html += `<div>
        <h4 style="margin-bottom:12px;">Constructors' Championship</h4>
        <table class="data-table sortable">
            <thead><tr>
                <th>#</th><th>Constructor</th>`;
    completedRounds.forEach(r => {
        html += `<th class="num" title="${r.name}">R${r.round}</th>`;
    });
    html += `<th class="num">Total</th><th class="num">Gap</th>
            </tr></thead><tbody>`;
    sortedConstructors.forEach(([id, c], i) => {
        const team = TEAMS[id] || { name: id, color: '#666' };
        const gap = i === 0 ? '-' : `${c.total - cLeader}`;
        html += `<tr>
            <td>${i + 1}</td>
            <td><span class="team-dot" style="background:${team.color}"></span><strong>${team.name}</strong></td>`;
        completedRounds.forEach(r => {
            const pts = c.rounds[r.round] || 0;
            const cls = pts >= 25 ? 'color:var(--green);font-weight:700' : pts > 0 ? '' : 'color:var(--text-muted)';
            html += `<td class="num" style="${cls}">${pts}</td>`;
        });
        html += `<td class="num"><strong>${c.total}</strong></td>
            <td class="num" style="color:var(--text-secondary)">${gap}</td>
        </tr>`;
    });
    html += `</tbody></table></div></div>`;

    el.innerHTML = html;
    el.querySelectorAll('.data-table').forEach(makeTableSortable);
}

function renderSeason() {
    // Calendar
    const calEl = document.getElementById('seasonCalendar');
    if (!seasonSummary || !seasonSummary.rounds) {
        calEl.innerHTML = '<p class="no-data">No season data available. Run pipeline/08_export_website_json.py first.</p>';
    } else {
        let html = `<table class="data-table sortable">
            <thead><tr>
                <th>Rd</th><th>Race</th><th>Circuit</th><th>Date</th><th>Status</th>
            </tr></thead>
            <tbody>${seasonSummary.rounds.map(r => {
                const clickable = r.has_post_race || r.has_predictions || r.has_actual;
                const rowClass = clickable ? 'class="clickable-row" data-round="' + r.round + '"' : '';
                return `
                <tr ${rowClass} ${clickable ? 'style="cursor:pointer"' : ''}>
                    <td>${r.round}</td>
                    <td><strong>${r.name}</strong></td>
                    <td>${r.circuit}</td>
                    <td>${r.date}</td>
                    <td>${r.has_post_race ? '<span class="status-done">Complete</span>' :
                          r.has_predictions ? '<span class="status-predicted">Predicted</span>' :
                          '<span class="status-upcoming">Upcoming</span>'}</td>
                </tr>`;
            }).join('')}
            </tbody>
        </table>`;
        calEl.innerHTML = html;
        calEl.querySelectorAll('table.sortable').forEach(makeTableSortable);

        // Add click handlers for completed/predicted rounds
        calEl.querySelectorAll('.clickable-row').forEach(row => {
            row.addEventListener('click', async () => {
                const roundNum = row.dataset.round;
                // Switch to Analysis tab, Post-Race panel
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                document.querySelector('[data-tab="analysis"]').classList.add('active');
                document.getElementById('tab-analysis').classList.add('active');
                trackTabView('analysis');  // jumped here from a calendar row — GA4 still counts it

                document.querySelectorAll('.analysis-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.analysis-panel').forEach(p => p.classList.remove('active'));
                document.querySelector('[data-panel="postrace"]').classList.add('active');
                document.getElementById('panel-postrace').classList.add('active');

                // Set selector value
                const selector = document.getElementById('postRaceRound');
                selector.value = roundNum;

                // Load and render (parallel fetch + stale-guard via selector value)
                const [postRace, predictions, actual] = await Promise.all([
                    loadPostRaceData(roundNum),
                    loadPredictionsData(roundNum),
                    loadActualData(roundNum),
                ]);
                if (selector.value !== roundNum) return; // user clicked another row
                renderPostRace(postRace, predictions, actual, roundNum);
            });
        });
    }

    // Championship Standings (WDC / WCC)
    renderChampionshipStandings();

    // Price Tracker
    const priceEl = document.getElementById('priceTracker');
    if (!seasonSummary || !seasonSummary.driver_prices || Object.keys(seasonSummary.driver_prices).length === 0) {
        priceEl.innerHTML = '<p class="no-data">No price data available yet.</p>';
    } else {
        const sorted = Object.entries(seasonSummary.driver_prices)
            .sort((a,b) => b[1].price_change - a[1].price_change);

        let html = `<table class="data-table sortable">
            <thead><tr>
                <th>Driver</th><th>Team</th><th class="num">Current</th>
                <th class="num">Starting</th><th class="num">Change</th><th>Trend</th>
            </tr></thead>
            <tbody>${sorted.map(([abbrev, d]) => {
                const team = TEAMS[d.constructor] || { name: d.constructor, color: '#666' };
                const changeClass = d.price_change > 0 ? 'text-green' : d.price_change < 0 ? 'text-red' : '';
                const trendIcon = d.price_trend === 'up' ? '▲' : d.price_trend === 'down' ? '▼' : '—';
                return `
                <tr>
                    <td><strong>${d.name || abbrev}</strong></td>
                    <td><span class="team-dot" style="background:${team.color}"></span>${team.name}</td>
                    <td class="num">$${d.current_price.toFixed(1)}M</td>
                    <td class="num">$${d.starting_price.toFixed(1)}M</td>
                    <td class="num ${changeClass}">${d.price_change > 0 ? '+' : ''}${d.price_change.toFixed(1)}</td>
                    <td><span class="trend-${d.price_trend}">${trendIcon}</span></td>
                </tr>`;
            }).join('')}
            </tbody>
        </table>`;
        priceEl.innerHTML = html;
        priceEl.querySelectorAll('table.sortable').forEach(makeTableSortable);
    }

    // Constructor Price Tracker
    const cPriceEl = document.getElementById('constructorPriceTracker');
    if (cPriceEl) {
        if (!seasonSummary || !seasonSummary.constructor_prices || Object.keys(seasonSummary.constructor_prices).length === 0) {
            cPriceEl.innerHTML = '<p class="no-data">No constructor price data available yet.</p>';
        } else {
            const sorted = Object.entries(seasonSummary.constructor_prices)
                .sort((a,b) => b[1].price_change - a[1].price_change);

            let cHtml = `<table class="data-table sortable">
                <thead><tr>
                    <th>Constructor</th><th class="num">Current</th>
                    <th class="num">Starting</th><th class="num">Change</th><th>Trend</th>
                </tr></thead>
                <tbody>${sorted.map(([cid, c]) => {
                    const team = TEAMS[cid] || { name: c.name, color: '#666' };
                    const changeClass = c.price_change > 0 ? 'text-green' : c.price_change < 0 ? 'text-red' : '';
                    const trendIcon = c.price_trend === 'up' ? '▲' : c.price_trend === 'down' ? '▼' : '—';
                    return `
                    <tr>
                        <td><span class="team-dot" style="background:${team.color}"></span><strong>${c.name}</strong></td>
                        <td class="num">$${c.current_price.toFixed(1)}M</td>
                        <td class="num">$${c.starting_price.toFixed(1)}M</td>
                        <td class="num ${changeClass}">${c.price_change > 0 ? '+' : ''}${c.price_change.toFixed(1)}</td>
                        <td><span class="trend-${c.price_trend}">${trendIcon}</span></td>
                    </tr>`;
                }).join('')}
                </tbody>
            </table>`;
            cPriceEl.innerHTML = cHtml;
            cPriceEl.querySelectorAll('table.sortable').forEach(makeTableSortable);
        }
    }

    // Cumulative Fantasy Standings (prefers official points when available)
    const standingsEl = document.getElementById('fantasyStandings');
    if (standingsEl) {
        const driverTotals = {};
        const constructorTotals = {};
        const fantasyRounds = [];
        let hasAnyOfficial = false;

        // Collect round numbers that have data, sorted
        const roundNums = Object.keys(actualCache).map(Number).filter(rn => actualCache[rn]).sort((a, b) => a - b);

        for (const rn of roundNums) {
            const actData = actualCache[rn];
            if (!actData) continue;
            const roundInfo = seasonSummary?.rounds?.find(r => r.round === rn);
            fantasyRounds.push({ round: rn, name: roundInfo?.name || `Round ${rn}` });

            if (actData.drivers) {
                actData.drivers.forEach(d => {
                    if (!driverTotals[d.driver_id]) {
                        driverTotals[d.driver_id] = { name: d.name, constructor: d.constructor, total: 0, roundPts: {}, price: d.price };
                    }
                    const result = getOfficialScore(rn, d.driver_id, true);
                    const pts = result ? result.points : (d.total_points || 0);
                    if (result && result.source === 'official') hasAnyOfficial = true;
                    driverTotals[d.driver_id].total += pts;
                    driverTotals[d.driver_id].roundPts[rn] = pts;
                    driverTotals[d.driver_id].price = d.price;
                });
            }
            if (actData.constructors) {
                actData.constructors.forEach(c => {
                    if (!constructorTotals[c.constructor_id]) {
                        constructorTotals[c.constructor_id] = { name: c.name, total: 0, roundPts: {}, price: c.price };
                    }
                    const result = getOfficialScore(rn, c.constructor_id, false);
                    const pts = result ? result.points : (c.total_points || 0);
                    if (result && result.source === 'official') hasAnyOfficial = true;
                    constructorTotals[c.constructor_id].total += pts;
                    constructorTotals[c.constructor_id].roundPts[rn] = pts;
                    constructorTotals[c.constructor_id].price = c.price;
                });
            }
        }

        if (fantasyRounds.length > 0) {
            const sortedDrivers = Object.entries(driverTotals).sort((a, b) => b[1].total - a[1].total);
            const sortedConstructors = Object.entries(constructorTotals).sort((a, b) => b[1].total - a[1].total);

            const sourceTag = hasAnyOfficial ? ' <span style="font-size:0.7em;color:var(--green)">(Official pts)</span>' : ' <span style="font-size:0.7em;color:var(--text-muted)">(Calculated pts)</span>';

            let sHtml = `<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;">`;

            // Driver fantasy standings with per-round columns
            sHtml += `<div>
                <h4 style="margin-bottom:12px;">Driver Fantasy Standings (${fantasyRounds.length} rounds)${sourceTag}</h4>
                <table class="data-table sortable">
                    <thead><tr>
                        <th>#</th><th>Driver</th><th>Team</th>`;
            fantasyRounds.forEach(r => { sHtml += `<th class="num" title="${r.name}">R${r.round}</th>`; });
            sHtml += `<th class="num" title="Total fantasy points scored">Total</th>
                        <th class="num" title="Average fantasy points per round">Avg</th>
                        <th class="num" title="Total points / current price">PPM</th>
                    </tr></thead>
                    <tbody>${sortedDrivers.map(([id, d], i) => {
                        const team = TEAMS[d.constructor] || { name: d.constructor, color: '#666' };
                        const avg = fantasyRounds.length > 0 ? d.total / fantasyRounds.length : 0;
                        const ppm = d.price > 0 ? d.total / d.price : 0;
                        const ppmRating = ppm >= 2.0 ? 'color:var(--green)' : ppm >= 1.0 ? 'color:#22d3ee' : ppm < 0 ? 'color:var(--red, #ef4444)' : '';
                        let row = `<tr>
                            <td>${i + 1}</td>
                            <td><strong>${d.name || id}</strong></td>
                            <td><span class="team-dot" style="background:${team.color}"></span>${team.name}</td>`;
                        fantasyRounds.forEach(r => {
                            const p = d.roundPts[r.round] ?? '-';
                            const cls = typeof p === 'number' ? (p >= 40 ? 'color:var(--green);font-weight:700' : p < 0 ? 'color:var(--red)' : '') : 'color:var(--text-muted)';
                            row += `<td class="num" style="${cls}">${p}</td>`;
                        });
                        row += `<td class="num"><strong>${d.total}</strong></td>
                            <td class="num">${avg.toFixed(1)}</td>
                            <td class="num" style="${ppmRating}">${ppm.toFixed(2)}</td>
                        </tr>`;
                        return row;
                    }).join('')}</tbody>
                </table>
            </div>`;

            // Constructor fantasy standings with per-round columns
            sHtml += `<div>
                <h4 style="margin-bottom:12px;">Constructor Fantasy Standings</h4>
                <table class="data-table sortable">
                    <thead><tr>
                        <th>#</th><th>Constructor</th>`;
            fantasyRounds.forEach(r => { sHtml += `<th class="num" title="${r.name}">R${r.round}</th>`; });
            sHtml += `<th class="num">Total</th>
                        <th class="num">Avg</th>
                        <th class="num">PPM</th>
                    </tr></thead>
                    <tbody>${sortedConstructors.map(([id, c], i) => {
                        const team = TEAMS[id] || { name: c.name, color: '#666' };
                        const avg = fantasyRounds.length > 0 ? c.total / fantasyRounds.length : 0;
                        const ppm = c.price > 0 ? c.total / c.price : 0;
                        const ppmRating = ppm >= 2.0 ? 'color:var(--green)' : ppm >= 1.0 ? 'color:#22d3ee' : ppm < 0 ? 'color:var(--red, #ef4444)' : '';
                        let row = `<tr>
                            <td>${i + 1}</td>
                            <td><span class="team-dot" style="background:${team.color}"></span><strong>${team.name}</strong></td>`;
                        fantasyRounds.forEach(r => {
                            const p = c.roundPts[r.round] ?? '-';
                            const cls = typeof p === 'number' ? (p >= 60 ? 'color:var(--green);font-weight:700' : p < 0 ? 'color:var(--red)' : '') : 'color:var(--text-muted)';
                            row += `<td class="num" style="${cls}">${p}</td>`;
                        });
                        row += `<td class="num"><strong>${c.total}</strong></td>
                            <td class="num">${avg.toFixed(1)}</td>
                            <td class="num" style="${ppmRating}">${ppm.toFixed(2)}</td>
                        </tr>`;
                        return row;
                    }).join('')}</tbody>
                </table>
            </div>`;

            sHtml += `</div>`;
            standingsEl.innerHTML = sHtml;
            standingsEl.querySelectorAll('.data-table').forEach(makeTableSortable);
        } else {
            standingsEl.innerHTML = '<p class="no-data">No actual race data available yet.</p>';
        }
    }

    // Populate post-race round selector
    populatePostRaceSelector();
}

function populatePostRaceSelector() {
    const selector = document.getElementById('postRaceRound');
    if (!selector || !seasonSummary || !seasonSummary.rounds) return;
    // Don't re-populate if already has options beyond the placeholder
    if (selector.options.length > 1) return;
    selector.innerHTML = '<option value="">Select a round...</option>';
    const currentRound = data ? data.round : 0;
    seasonSummary.rounds
        .filter(r => r.has_post_race || r.has_predictions || r.has_actual || r.round <= currentRound)
        .forEach(r => {
            const opt = document.createElement('option');
            opt.value = r.round;
            let label = '';
            if (r.has_actual && r.has_predictions) label = ' ✓ Pred vs Actual';
            else if (r.has_actual || r.has_post_race) label = ' (Complete)';
            else if (r.has_predictions) label = ' (Predicted)';
            opt.textContent = `Round ${r.round}: ${r.name}${label}`;
            selector.appendChild(opt);
        });
}

// ============================================================
// Head-to-Head Matchup Tab
// ============================================================

function normalCDF(x) {
    const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741;
    const a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
    const sign = x < 0 ? -1 : 1;
    x = Math.abs(x) / Math.SQRT2;
    const t = 1.0 / (1.0 + p * x);
    const y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
    return 0.5 * (1.0 + sign * y);
}

let h2hInitialized = false;

function renderH2H() {
    if (!data || !data.drivers) return;
    const selA = document.getElementById('h2hDriverA');
    const selB = document.getElementById('h2hDriverB');
    if (!selA || !selB) return;

    // Only populate dropdowns once
    if (!h2hInitialized) {
        const sorted = [...data.drivers].sort((a, b) => a.name.localeCompare(b.name));
        [selA, selB].forEach(sel => {
            sel.innerHTML = '<option value="">Select a driver...</option>';
            sorted.forEach(d => {
                const team = TEAMS[d.constructor] || { name: d.constructor, color: '#666' };
                const opt = document.createElement('option');
                opt.value = d.driver_id;
                opt.textContent = `${d.name} (${team.name})`;
                opt.style.color = team.color;
                sel.appendChild(opt);
            });
        });
        // Default to first two drivers by expected points
        const byPts = [...data.drivers].sort((a, b) => b.expected_points - a.expected_points);
        if (byPts.length >= 2) {
            selA.value = byPts[0].driver_id;
            selB.value = byPts[1].driver_id;
        }
        selA.addEventListener('change', updateH2HComparison);
        selB.addEventListener('change', updateH2HComparison);
        h2hInitialized = true;
        updateH2HComparison();
    }
}

function updateH2HComparison() {
    const container = document.getElementById('h2hComparison');
    const idA = document.getElementById('h2hDriverA').value;
    const idB = document.getElementById('h2hDriverB').value;

    if (!idA || !idB || idA === idB) {
        container.innerHTML = idA === idB && idA ? '<p class="no-data">Please select two different drivers.</p>' : '<p class="no-data">Select two drivers above to compare.</p>';
        return;
    }

    const dA = data.drivers.find(d => d.driver_id === idA);
    const dB = data.drivers.find(d => d.driver_id === idB);
    if (!dA || !dB) return;

    const teamA = TEAMS[dA.constructor] || { name: dA.constructor, color: '#666' };
    const teamB = TEAMS[dB.constructor] || { name: dB.constructor, color: '#666' };

    // Win probability
    const stdA = dA.mc_total_std || 10;
    const stdB = dB.mc_total_std || 10;
    const meanA = dA.mc_total_mean != null ? dA.mc_total_mean : dA.expected_points;
    const meanB = dB.mc_total_mean != null ? dB.mc_total_mean : dB.expected_points;
    const combinedStd = Math.sqrt(stdA * stdA + stdB * stdB);
    const z = combinedStd > 0 ? (meanA - meanB) / combinedStd : 0;
    const winProbA = normalCDF(z);
    const winProbB = 1 - winProbA;
    const winPctA = (winProbA * 100).toFixed(1);
    const winPctB = (winProbB * 100).toFixed(1);

    // Price fields
    computeDriverPriceFields(dA);
    computeDriverPriceFields(dB);

    // Historical H2H
    let histHTML = '';
    let h2hWinsA = 0, h2hWinsB = 0, totalPtsA = 0, totalPtsB = 0, h2hRounds = 0;
    if (seasonSummary && seasonSummary.rounds) {
        const completedRounds = seasonSummary.rounds.filter(r => r.has_actual);
        const histRows = [];
        completedRounds.forEach(r => {
            const actData = actualCache[r.round];
            if (!actData || !actData.drivers) return;
            const actA = actData.drivers.find(d => d.driver_id === idA);
            const actB = actData.drivers.find(d => d.driver_id === idB);
            if (!actA || !actB) return;
            h2hRounds++;
            const offA = getOfficialScore(r.round, idA, true);
            const offB = getOfficialScore(r.round, idB, true);
            const ptsA = offA ? offA.points : (actA.total_points || 0);
            const ptsB = offB ? offB.points : (actB.total_points || 0);
            totalPtsA += ptsA;
            totalPtsB += ptsB;
            if (ptsA > ptsB) h2hWinsA++;
            else if (ptsB > ptsA) h2hWinsB++;
            const winnerClass = ptsA > ptsB ? 'h2h-winner-a' : ptsB > ptsA ? 'h2h-winner-b' : '';
            histRows.push(`<tr class="${winnerClass}">
                <td>R${r.round}</td>
                <td>${r.name}</td>
                <td class="num" style="color:${teamA.color}">${ptsA}</td>
                <td class="num" style="color:${teamB.color}">${ptsB}</td>
                <td class="num">${ptsA - ptsB > 0 ? '+' : ''}${ptsA - ptsB}</td>
            </tr>`);
        });

        if (histRows.length > 0) {
            const avgA = (totalPtsA / h2hRounds).toFixed(1);
            const avgB = (totalPtsB / h2hRounds).toFixed(1);
            histHTML = `
            <div class="h2h-section">
                <h3>Historical H2H</h3>
                <div class="h2h-record">
                    <span style="color:${teamA.color}">${dA.name} ${h2hWinsA}</span>
                    <span class="h2h-record-sep"> - </span>
                    <span style="color:${teamB.color}">${h2hWinsB} ${dB.name}</span>
                </div>
                <div class="h2h-averages">
                    Avg pts: <span style="color:${teamA.color}">${avgA}</span> vs <span style="color:${teamB.color}">${avgB}</span>
                </div>
                <div class="table-wrapper">
                    <table class="data-table h2h-history-table sortable">
                        <thead><tr><th>Rd</th><th>Race</th><th class="num">${dA.name}</th><th class="num">${dB.name}</th><th class="num">Diff</th></tr></thead>
                        <tbody>${histRows.join('')}</tbody>
                    </table>
                </div>
            </div>`;
        }
    }

    // Recommendation
    let recText = '';
    const ptsDiff = dA.expected_points - dB.expected_points;
    const valueDiff = dA.value_score - dB.value_score;
    const pick = ptsDiff >= 0 ? dA : dB;
    const pickTeam = ptsDiff >= 0 ? teamA : teamB;
    const reasons = [];
    if (Math.abs(ptsDiff) >= 0.5) reasons.push(`${Math.abs(ptsDiff).toFixed(1)} more expected points`);
    if ((ptsDiff >= 0 && valueDiff >= 0.05) || (ptsDiff < 0 && valueDiff < -0.05)) reasons.push('better value');
    if ((ptsDiff >= 0 && stdA < stdB) || (ptsDiff < 0 && stdB < stdA)) reasons.push('lower risk');
    if ((ptsDiff >= 0 && winProbA > 0.5) || (ptsDiff < 0 && winProbB > 0.5)) {
        const wp = ptsDiff >= 0 ? winPctA : winPctB;
        reasons.push(`${wp}% win probability`);
    }
    recText = reasons.length > 0
        ? `Pick <strong style="color:${pickTeam.color}">${pick.name}</strong>: ${reasons.join(', ')}`
        : 'These drivers are very evenly matched. Consider other factors like upcoming schedule and team momentum.';

    // Build stat comparison helper
    function statRow(label, valA, valB, fmt, higherBetter = true) {
        const nA = parseFloat(valA), nB = parseFloat(valB);
        let clsA = '', clsB = '';
        if (!isNaN(nA) && !isNaN(nB) && nA !== nB) {
            const aBetter = higherBetter ? nA > nB : nA < nB;
            clsA = aBetter ? 'h2h-better' : 'h2h-worse';
            clsB = aBetter ? 'h2h-worse' : 'h2h-better';
        }
        const fA = typeof fmt === 'function' ? fmt(valA) : valA;
        const fB = typeof fmt === 'function' ? fmt(valB) : valB;
        return `<div class="h2h-stat-row">
            <span class="h2h-stat-val ${clsA}" style="color:${teamA.color}">${fA}</span>
            <span class="h2h-stat-label">${label}</span>
            <span class="h2h-stat-val ${clsB}" style="color:${teamB.color}">${fB}</span>
        </div>`;
    }

    const fmtPts = v => v != null ? v.toFixed(1) : '-';
    const fmtPos = v => v != null ? 'P' + v : '-';
    const fmtPct = v => v != null ? (v * 100).toFixed(0) + '%' : '-';
    const fmtPrice = v => v != null ? '$' + v.toFixed(1) + 'M' : '-';

    container.innerHTML = `
    <div class="h2h-comparison">
        <div class="h2h-drivers-header">
            <div class="h2h-driver-name" style="color:${teamA.color}">${dA.name}<span class="h2h-driver-team">${teamA.name}</span></div>
            <div class="h2h-driver-name" style="color:${teamB.color}">${dB.name}<span class="h2h-driver-team">${teamB.name}</span></div>
        </div>

        <div class="h2h-section">
            <h3>This Weekend</h3>
            ${statRow('Expected Points', dA.expected_points, dB.expected_points, fmtPts, true)}
            ${statRow('MC Mean', meanA, meanB, fmtPts, true)}
            ${statRow('90% CI Range', dA.mc_total_p5 != null ? `${dA.mc_total_p5.toFixed(0)} - ${dA.mc_total_p95.toFixed(0)}` : '-', dB.mc_total_p5 != null ? `${dB.mc_total_p5.toFixed(0)} - ${dB.mc_total_p95.toFixed(0)}` : '-', v => v)}
            ${statRow('Top 3 Prob', dA.prob_top3, dB.prob_top3, fmtPct, true)}
            ${statRow('Top 5 Prob', dA.prob_top5, dB.prob_top5, fmtPct, true)}
            ${statRow('Top 10 Prob', dA.prob_top10, dB.prob_top10, fmtPct, true)}
            ${statRow('Pred Quali', dA.predicted_quali, dB.predicted_quali, fmtPos, false)}
            ${statRow('Pred Finish', dA.predicted_finish, dB.predicted_finish, fmtPos, false)}
            <div class="h2h-win-bar-container">
                <div class="h2h-win-bar-label">Win Probability</div>
                <div class="h2h-win-bar">
                    <div class="h2h-win-bar-a" style="width:${winPctA}%;background:${teamA.color}">
                        ${winProbA >= 0.15 ? winPctA + '%' : ''}
                    </div>
                    <div class="h2h-win-bar-b" style="width:${winPctB}%;background:${teamB.color}">
                        ${winProbB >= 0.15 ? winPctB + '%' : ''}
                    </div>
                </div>
            </div>
        </div>

        <div class="h2h-section">
            <h3>Value Comparison</h3>
            ${statRow('Price', dA.current_price, dB.current_price, fmtPrice, false)}
            ${statRow('Pts / $M', dA.points_per_million, dB.points_per_million, fmtPts, true)}
            ${statRow('PPM', dA.value_score, dB.value_score, v => v != null ? v.toFixed(2) + ' ppm' : '-', true)}
            ${statRow('MC PPM', dA.mc_value_score, dB.mc_value_score, v => v != null ? v.toFixed(2) + ' ppm' : '-', true)}
            ${statRow('Price Change', dA._price_change, dB._price_change, v => (v >= 0 ? '+' : '') + v.toFixed(1), true)}
        </div>

        ${histHTML}

        <div class="h2h-recommendation">
            <div class="h2h-rec-label">Recommendation</div>
            <div class="h2h-rec-text">${recText}</div>
        </div>
    </div>`;
    container.querySelectorAll('table.sortable').forEach(makeTableSortable);
}

// ============================================================
// Model Accuracy Dashboard Tab
// ============================================================

let accuracyDataLoaded = false;
let accuracyPairs = [];
let accuracyMissingNote = '';
let accuracySelectedRounds = new Set();
let accuracyEntityType = 'drivers'; // 'drivers' | 'constructors'
let accuracyPhase = 'latest';       // 'latest' | 'pre_fp' | 'post_fp' | 'post_quali'
// Cache of all loaded archives, keyed by `${round}__${phase}`. Used to swap phases
// without re-fetching. Built lazily by ensureAccuracyDataForPhase.
let accuracyByPhase = {}; // phase -> [{ round, name, pred, act, archivePhase }]
// In-flight loading promise — shared across concurrent renderAccuracy() calls
// so two deep-link triggers (or any future double-fire) don't both blow away
// accuracyByPhase and re-push, producing 2× entries per phase.
let _accuracyLoadingPromise = null;

async function renderAccuracy() {
    if (!data) return;
    if (!seasonSummary || !seasonSummary.rounds) return;
    const container = document.getElementById('accuracyContent');
    if (!container) return;

    // Load data once for the default phase, then re-render on filter changes.
    if (!accuracyDataLoaded) {
        // If another caller is already loading, await their promise — don't
        // restart the load (the old code did, which races the array resets and
        // doubles every push). Single producer per page load.
        if (_accuracyLoadingPromise) {
            await _accuracyLoadingPromise;
        } else {
            _accuracyLoadingPromise = (async () => {
                const roundsWithBoth = seasonSummary.rounds.filter(r => r.has_predictions && r.has_actual);
                const roundsActualOnly = seasonSummary.rounds.filter(r => !r.has_predictions && r.has_actual);
                if (roundsWithBoth.length === 0) {
                    container.innerHTML = '<p class="no-data">No rounds with both predictions and actuals available yet. Check back after a completed race weekend.</p>';
                    return { aborted: true };
                }

                if (roundsActualOnly.length > 0) {
                    const names = roundsActualOnly.map(r => `R${r.round} (${r.name})`).join(', ');
                    accuracyMissingNote = `<div style="background:rgba(234,179,8,0.1);border:1px solid rgba(234,179,8,0.25);color:#eab308;padding:8px 14px;border-radius:8px;font-size:0.8rem;margin-bottom:16px;">
                        ${names}: Predictions were not generated before the race, so accuracy cannot be measured for ${roundsActualOnly.length === 1 ? 'this round' : 'these rounds'}.
                    </div>`;
                }

                container.innerHTML = accuracyMissingNote + '<p class="no-data">Analyzing prediction accuracy...</p>';

                // Load all phase archives + canonical + actuals in parallel
                const phases = ['latest', 'pre_fp', 'post_fp', 'post_quali'];
                for (const ph of phases) accuracyByPhase[ph] = [];

                for (const r of roundsWithBoth) {
                    const [actual, latestArc, preFp, postFp, postQuali] = await Promise.all([
                        loadActualData(r.round),
                        loadPredictionsForPhase(r.round, 'latest'),
                        loadPredictionsForPhase(r.round, 'pre_fp'),
                        loadPredictionsForPhase(r.round, 'post_fp'),
                        loadPredictionsForPhase(r.round, 'post_quali'),
                    ]);
                    if (!actual) continue;
                    if (latestArc)   accuracyByPhase['latest']    .push({ round: r.round, name: r.name, pred: latestArc, act: actual });
                    if (preFp)       accuracyByPhase['pre_fp']    .push({ round: r.round, name: r.name, pred: preFp,     act: actual });
                    if (postFp)      accuracyByPhase['post_fp']   .push({ round: r.round, name: r.name, pred: postFp,    act: actual });
                    if (postQuali)   accuracyByPhase['post_quali'].push({ round: r.round, name: r.name, pred: postQuali, act: actual });
                }

                // Initial pairs = chosen phase
                accuracyPairs = accuracyByPhase[accuracyPhase] || [];
                if (accuracyPairs.length === 0 && accuracyByPhase['latest'].length > 0) {
                    accuracyPhase = 'latest';
                    accuracyPairs = accuracyByPhase['latest'];
                }

                if (accuracyPairs.length === 0) {
                    container.innerHTML = '<p class="no-data">Could not load prediction/actual data pairs.</p>';
                    return { aborted: true };
                }

                // Default: all rounds selected
                accuracySelectedRounds = new Set(accuracyPairs.map(p => p.round));
                accuracyDataLoaded = true;
                return { aborted: false };
            })();
            const result = await _accuracyLoadingPromise;
            if (result && result.aborted) return;
        }
    }

    renderAccuracyWithFilters(container);
}

function renderAccuracyWithFilters(container) {
    const activePairs = accuracyPairs.filter(p => accuracySelectedRounds.has(p.round));
    const isDrivers = accuracyEntityType === 'drivers';
    const idField = isDrivers ? 'driver_id' : 'constructor_id';
    const listKey = isDrivers ? 'drivers' : 'constructors';

    // Compute all metrics
    const scatterPoints = [];
    const roundStats = [];
    const positionRows = [];
    const entityAccum = {};
    let totalPtsMAE = 0, totalPosMAE = 0, totalCIHits = 0, totalCITotal = 0, totalComparisons = 0, totalPosComparisons = 0;
    let totalQualiMAE = 0, totalQualiComparisons = 0;
    let roundsWithMissingOfficial = [];

    // Track latest round for per-entity latest race columns
    const latestRound = activePairs.length > 0 ? Math.max(...activePairs.map(p => p.round)) : null;

    activePairs.forEach(({ round, name, pred, act }) => {
        const predMap = {};
        const predList = pred[listKey] || [];
        predList.forEach(d => { predMap[d[idField]] = d; });
        const actMap = {};
        const actList = act[listKey] || [];
        actList.forEach(d => { actMap[d[idField]] = d; });

        let rPtsMAE = 0, rPosMAE = 0, rQualiMAE = 0, rCIHits = 0, rCITotal = 0, rCount = 0, rPosCount = 0, rQualiCount = 0;
        let bestErr = Infinity, worstErr = 0, bestName = '', worstName = '';

        // For constructors: track if official exists this round (for accuracy-confidence note)
        let roundHasAnyOfficial = false;

        const allIds = [...new Set([...Object.keys(predMap), ...Object.keys(actMap)])];
        allIds.forEach(id => {
            const p = predMap[id], a = actMap[id];
            if (!p || !a) return;
            const predPts = p.expected_points || 0;
            const offScore = getOfficialScore(round, id, isDrivers);
            if (offScore && offScore.source === 'official') roundHasAnyOfficial = true;
            const actPts = offScore ? offScore.points : (a.total_points || 0);
            const ptsErr = Math.abs(predPts - actPts);
            rPtsMAE += ptsErr;
            rCount++;
            totalPtsMAE += ptsErr;
            totalComparisons++;

            const labelName = p.name || a.name || id;
            if (ptsErr < bestErr) { bestErr = ptsErr; bestName = labelName; }
            if (ptsErr > worstErr) { worstErr = ptsErr; worstName = labelName; }

            // Position MAE applies to drivers only
            if (isDrivers) {
                const predQuali = p.predicted_quali;
                const actQuali = a.quali_position;
                const predFinish = p.predicted_finish;
                const actFinish = a.race_position;
                const qualiErr = predQuali != null && actQuali != null
                    ? Math.abs(predQuali - actQuali)
                    : null;
                const raceErr = predFinish != null && actFinish != null
                    ? Math.abs(predFinish - actFinish)
                    : null;
                if (qualiErr != null) {
                    rQualiMAE += qualiErr;
                    rQualiCount++;
                    totalQualiMAE += qualiErr;
                    totalQualiComparisons++;
                }
                if (raceErr != null) {
                    rPosMAE += raceErr;
                    rPosCount++;
                    totalPosMAE += raceErr;
                    totalPosComparisons++;
                }
                positionRows.push({
                    round, race: name, driver: labelName,
                    constructor: p.constructor || a.constructor || '',
                    predQuali, actQuali, qualiErr,
                    predRace: predFinish, actRace: actFinish, raceErr
                });
            }

            if (p.mc_total_p5 != null && p.mc_total_p95 != null) {
                rCITotal++;
                totalCITotal++;
                if (actPts >= p.mc_total_p5 && actPts <= p.mc_total_p95) {
                    rCIHits++;
                    totalCIHits++;
                }
            }

            // Constructor color resolution: id IS the constructor for the constructors view
            const constructorId = isDrivers ? (p.constructor || a.constructor) : id;
            scatterPoints.push({
                pred: predPts, actual: actPts, entity_id: id,
                constructor: constructorId, round, name: labelName
            });

            if (!entityAccum[id]) {
                entityAccum[id] = { name: labelName, constructor: constructorId, totalPred: 0, totalActual: 0, totalErr: 0, rounds: 0, latestPred: null, latestActual: null };
            }
            entityAccum[id].totalPred += predPts;
            entityAccum[id].totalActual += actPts;
            entityAccum[id].totalErr += ptsErr;
            entityAccum[id].rounds++;

            if (round === latestRound) {
                entityAccum[id].latestPred = predPts;
                entityAccum[id].latestActual = actPts;
                entityAccum[id].latestRound = round;
            }
        });

        if (!isDrivers && !roundHasAnyOfficial && rCount > 0) {
            roundsWithMissingOfficial.push(round);
        }

        roundStats.push({
            round, name,
            ptsMAE: rCount > 0 ? (rPtsMAE / rCount).toFixed(1) : '-',
            qualiMAE: isDrivers ? (rQualiCount > 0 ? (rQualiMAE / rQualiCount).toFixed(1) : '-') : '-',
            raceMAE: isDrivers ? (rPosCount > 0 ? (rPosMAE / rPosCount).toFixed(1) : '-') : '-',
            ciCoverage: rCITotal > 0 ? ((rCIHits / rCITotal) * 100).toFixed(0) + '%' : '-',
            best: bestName + ' (' + bestErr.toFixed(1) + ')',
            worst: worstName + ' (' + worstErr.toFixed(1) + ')'
        });
    });

    const overallPtsMAE = totalComparisons > 0 ? (totalPtsMAE / totalComparisons).toFixed(1) : '-';
    const overallPosMAE = totalPosComparisons > 0 ? (totalPosMAE / totalPosComparisons).toFixed(1) : '-';
    const overallQualiMAE = totalQualiComparisons > 0 ? (totalQualiMAE / totalQualiComparisons).toFixed(1) : '-';
    const overallCICov = totalCITotal > 0 ? ((totalCIHits / totalCITotal) * 100).toFixed(0) : '-';

    // Build scatter plot SVG
    const scatterSVG = activePairs.length > 0 ? buildScatterPlot(scatterPoints) : '<p class="no-data">Select at least one round to see the chart.</p>';

    // CI coverage bar
    const ciPct = totalCITotal > 0 ? (totalCIHits / totalCITotal) * 100 : 0;
    const ciBarHTML = `
    <div class="ci-bar-container">
        <div class="ci-bar-label">90% CI Coverage: ${ciPct.toFixed(0)}% of predictions within confidence interval</div>
        <div class="ci-bar">
            <div class="ci-bar-fill" style="width:${ciPct}%;background:${ciPct >= 80 ? 'var(--green)' : ciPct >= 60 ? 'var(--yellow)' : 'var(--red)'}"></div>
            <div class="ci-bar-target" style="left:90%"><span>90%</span></div>
        </div>
    </div>`;

    // Entity toggle (Drivers / Constructors)
    const entityToggleHTML = `
    <div class="accuracy-filter" style="margin-bottom:8px;">
        <span class="accuracy-filter-label">View:</span>
        <div class="accuracy-filter-buttons">
            <button class="accuracy-filter-btn${isDrivers ? ' active' : ''}" data-entity="drivers">Drivers</button>
            <button class="accuracy-filter-btn${!isDrivers ? ' active' : ''}" data-entity="constructors">Constructors</button>
        </div>
    </div>`;

    // Phase toggle (Latest / Pre-FP / Post-FP / Post-Quali). Buttons for phases
    // with no archives available are disabled with a count badge.
    const phaseDefs = [
        { key: 'latest',     label: 'Latest' },
        { key: 'pre_fp',     label: 'Pre-FP' },
        { key: 'post_fp',    label: 'Post-FP' },
        { key: 'post_quali', label: 'Post-Quali' },
    ];
    const phaseButtons = phaseDefs.map(p => {
        const count = (accuracyByPhase[p.key] || []).length;
        const disabled = count === 0;
        const active = p.key === accuracyPhase;
        return `<button class="accuracy-filter-btn${active ? ' active' : ''}"
                   data-phase="${p.key}" ${disabled ? 'disabled' : ''}
                   title="${disabled ? 'No archives available for this phase' : `${count} round${count===1?'':'s'} have this phase archived`}">
            ${p.label} <span style="opacity:0.6;font-size:0.85em">(${count})</span>
        </button>`;
    }).join('');
    // Count reconstructed archives in the current view
    const reconstructedCount = activePairs.filter(p => p.pred && p.pred.reconstructed).length;
    const reconstructedNote = reconstructedCount > 0
        ? `<div style="background:rgba(99,102,241,0.08);border:1px solid rgba(99,102,241,0.25);color:#a5b4fc;padding:8px 14px;border-radius:8px;font-size:0.78rem;margin:8px 0 12px;">
              ${reconstructedCount} of these archives are <strong>reconstructed</strong> — the model was walk-forward retrained with <code>--exclude-after</code> set to the target round, then used to re-predict on raw pre-race data. These are honest reconstructions, not the original predictions (which were lost when the pipeline re-ran post-race before guards were added).
          </div>`
        : '';
    const phaseToggleHTML = `
    <div class="accuracy-filter" style="margin-bottom:8px;">
        <span class="accuracy-filter-label">Phase:</span>
        <div class="accuracy-filter-buttons">${phaseButtons}</div>
    </div>
    ${reconstructedNote}`;

    // Race filter toggle buttons
    const filterHTML = `
    <div class="accuracy-filter">
        <span class="accuracy-filter-label">Filter by Race:</span>
        <div class="accuracy-filter-buttons">
            ${accuracyPairs.map(p => {
                const active = accuracySelectedRounds.has(p.round);
                return `<button class="accuracy-filter-btn${active ? ' active' : ''}" data-round="${p.round}">R${p.round} ${p.name}</button>`;
            }).join('')}
        </div>
    </div>`;

    // Constructor-specific note when no official points yet for selected rounds
    let constructorNote = '';
    if (!isDrivers && roundsWithMissingOfficial.length > 0) {
        const list = roundsWithMissingOfficial.map(r => 'R' + r).join(', ');
        constructorNote = `<div style="background:rgba(234,179,8,0.1);border:1px solid rgba(234,179,8,0.25);color:#eab308;padding:8px 14px;border-radius:8px;font-size:0.8rem;margin:8px 0 16px;">
            ${list}: Official constructor points not entered yet — using pipeline-calculated actuals (may differ from official).
        </div>`;
    }

    // Per-round table
    const positionMAEHeaders = isDrivers ? '<th class="num">Quali MAE</th><th class="num">Race MAE</th>' : '';
    const roundTableRows = roundStats.map(r => `<tr>
        <td>R${r.round}</td><td>${r.name}</td><td class="num">${r.ptsMAE}</td>
        ${isDrivers ? `<td class="num">${r.qualiMAE}</td><td class="num">${r.raceMAE}</td>` : ''}<td class="num">${r.ciCoverage}</td>
        <td>${r.best}</td><td>${r.worst}</td>
    </tr>`).join('');

    // Per-entity table with latest race columns
    const entityRows = Object.values(entityAccum)
        .map(d => ({
            ...d,
            avgPred: d.totalPred / d.rounds,
            avgActual: d.totalActual / d.rounds,
            avgErr: d.totalErr / d.rounds,
            bias: (d.totalPred - d.totalActual) / d.rounds
        }))
        .sort((a, b) => b.avgErr - a.avgErr);

    const latestRoundLabel = latestRound ? `R${latestRound}` : 'Latest';
    const entityLabel = isDrivers ? 'Driver' : 'Constructor';

    const entityTableRows = entityRows.map(d => {
        const team = TEAMS[d.constructor] || { name: d.constructor, color: '#666' };
        const biasClass = d.bias > 2 ? 'bias-over' : d.bias < -2 ? 'bias-under' : '';
        const biasSign = d.bias >= 0 ? '+' : '';
        const lPred = d.latestPred != null ? d.latestPred.toFixed(1) : '-';
        const lActual = d.latestActual != null ? d.latestActual.toFixed(0) : '-';
        const lErr = (d.latestPred != null && d.latestActual != null) ? Math.abs(d.latestPred - d.latestActual).toFixed(1) : '-';
        // For constructors, the entity name IS the team — collapse the team col
        const teamCell = isDrivers
            ? `<td style="color:${team.color}">${team.name}</td>`
            : `<td style="color:${team.color}">—</td>`;
        return `<tr>
            <td>${d.name}</td>
            ${teamCell}
            <td class="num">${lPred}</td>
            <td class="num">${lActual}</td>
            <td class="num">${lErr}</td>
            <td class="num">${d.avgPred.toFixed(1)}</td>
            <td class="num">${d.avgActual.toFixed(1)}</td>
            <td class="num">${d.avgErr.toFixed(1)}</td>
            <td class="num ${biasClass}">${biasSign}${d.bias.toFixed(1)}</td>
            <td class="num">${d.rounds}</td>
        </tr>`;
    }).join('');

    const positionErrorClass = (error) => {
        if (error == null) return '';
        if (error <= 2) return 'cmp-green';
        if (error <= 4) return 'cmp-yellow';
        return 'cmp-red';
    };
    const formatPosition = (position) => position != null ? `P${position}` : '-';
    const positionTableRows = [...positionRows]
        .sort((a, b) => b.round - a.round || (a.actRace ?? 99) - (b.actRace ?? 99))
        .map(row => {
            const team = TEAMS[row.constructor] || { name: row.constructor, color: '#666' };
            return `<tr>
                <td>R${row.round}</td>
                <td>${row.race}</td>
                <td><strong>${row.driver}</strong></td>
                <td style="color:${team.color}">${team.name}</td>
                <td class="num">${formatPosition(row.predQuali)}</td>
                <td class="num">${formatPosition(row.actQuali)}</td>
                <td class="num ${positionErrorClass(row.qualiErr)}">${row.qualiErr ?? '-'}</td>
                <td class="num">${formatPosition(row.predRace)}</td>
                <td class="num">${formatPosition(row.actRace)}</td>
                <td class="num ${positionErrorClass(row.raceErr)}">${row.raceErr ?? '-'}</td>
            </tr>`;
        }).join('');
    const positionComparisonHTML = isDrivers ? `
    <div class="accuracy-section">
        <h3>Qualifying &amp; Race Position Comparison</h3>
        <p style="margin:-6px 0 12px;color:var(--text-secondary);font-size:0.82rem;">
            Predicted and actual positions for the selected phase and races. Error is the absolute number of positions missed.
        </p>
        <div class="table-wrapper">
            <table class="data-table accuracy-position-table sortable">
                <thead><tr>
                    <th>Rd</th><th>Race</th><th>Driver</th><th>Team</th>
                    <th class="num">Pred Quali</th><th class="num">Actual Quali</th><th class="num">Q Error</th>
                    <th class="num">Pred Race</th><th class="num">Actual Race</th><th class="num">R Error</th>
                </tr></thead>
                <tbody>${positionTableRows}</tbody>
            </table>
        </div>
    </div>` : '';

    container.innerHTML = accuracyMissingNote + `
    ${entityToggleHTML}
    ${phaseToggleHTML}
    ${filterHTML}
    ${constructorNote}

    <div class="accuracy-stats">
        <div class="accuracy-stat-card">
            <div class="accuracy-stat-value">${overallPtsMAE}</div>
            <div class="accuracy-stat-label">Points MAE</div>
        </div>
        ${isDrivers ? `<div class="accuracy-stat-card">
            <div class="accuracy-stat-value">${overallQualiMAE}</div>
            <div class="accuracy-stat-label">Qualifying MAE</div>
        </div>
        <div class="accuracy-stat-card">
            <div class="accuracy-stat-value">${overallPosMAE}</div>
            <div class="accuracy-stat-label">Race MAE</div>
        </div>` : ''}
        <div class="accuracy-stat-card">
            <div class="accuracy-stat-value">${overallCICov}%</div>
            <div class="accuracy-stat-label">90% CI Coverage</div>
        </div>
        <div class="accuracy-stat-card">
            <div class="accuracy-stat-value">${activePairs.length}</div>
            <div class="accuracy-stat-label">Rounds Analyzed</div>
        </div>
    </div>

    <div class="accuracy-section">
        <h3>Predicted vs Actual Points</h3>
        <div class="scatter-container">${scatterSVG}</div>
    </div>

    ${ciBarHTML}

    <div class="accuracy-section">
        <h3>Per-Round Accuracy</h3>
        <div class="table-wrapper">
            <table class="data-table accuracy-round-table sortable">
                <thead><tr>
                    <th>Rd</th><th>Race</th><th class="num">Pts MAE</th>
                    ${positionMAEHeaders}<th class="num">CI Coverage</th>
                    <th>Best Prediction</th><th>Worst Prediction</th>
                </tr></thead>
                <tbody>${roundTableRows}</tbody>
            </table>
        </div>
    </div>

    ${positionComparisonHTML}

    <div class="accuracy-section">
        <h3>Per-${entityLabel} Accuracy</h3>
        <div class="table-wrapper">
            <table class="data-table accuracy-driver-table sortable">
                <thead><tr>
                    <th>${entityLabel}</th><th>Team</th>
                    <th class="num">${latestRoundLabel} Pred</th><th class="num">${latestRoundLabel} Actual</th><th class="num">${latestRoundLabel} Err</th>
                    <th class="num">Avg Pred</th><th class="num">Avg Actual</th><th class="num">Avg Error</th>
                    <th class="num">Bias</th><th class="num">Rounds</th>
                </tr></thead>
                <tbody>${entityTableRows}</tbody>
            </table>
        </div>
    </div>`;

    // Wire up filter buttons (race filter + entity toggle + phase toggle)
    container.querySelectorAll('.accuracy-filter-btn').forEach(btn => {
        if (btn.disabled) return;
        btn.addEventListener('click', () => {
            if (btn.dataset.entity) {
                accuracyEntityType = btn.dataset.entity;
            } else if (btn.dataset.phase) {
                accuracyPhase = btn.dataset.phase;
                accuracyPairs = accuracyByPhase[accuracyPhase] || [];
                // Reset the round filter to "all rounds in this phase"
                accuracySelectedRounds = new Set(accuracyPairs.map(p => p.round));
            } else if (btn.dataset.round != null) {
                const round = parseInt(btn.dataset.round);
                if (accuracySelectedRounds.has(round)) {
                    accuracySelectedRounds.delete(round);
                } else {
                    accuracySelectedRounds.add(round);
                }
            }
            renderAccuracyWithFilters(container);
        });
    });

    container.querySelectorAll('table.sortable').forEach(makeTableSortable);
}

function buildScatterPlot(dataPoints) {
    const width = 500, height = 500, pad = 50;
    const allVals = dataPoints.flatMap(d => [d.pred, d.actual]);
    const min = Math.min(...allVals, 0);
    const max = Math.max(...allVals) * 1.1;
    const range = max - min || 1;

    const sx = (v) => pad + ((v - min) / range) * (width - 2 * pad);
    const sy = (v) => height - pad - ((v - min) / range) * (height - 2 * pad);

    let svg = `<svg viewBox="0 0 ${width} ${height}" class="scatter-svg" preserveAspectRatio="xMidYMid meet">`;
    // Grid lines
    for (let i = 0; i <= 5; i++) {
        const val = min + (range * i / 5);
        svg += `<line x1="${pad}" y1="${sy(val)}" x2="${width - pad}" y2="${sy(val)}" stroke="var(--border)" stroke-dasharray="3"/>`;
        svg += `<text x="${pad - 5}" y="${sy(val) + 4}" text-anchor="end" fill="var(--text-secondary)" font-size="11">${val.toFixed(0)}</text>`;
        svg += `<text x="${sx(val)}" y="${height - pad + 15}" text-anchor="middle" fill="var(--text-secondary)" font-size="11">${val.toFixed(0)}</text>`;
    }
    // Reference line (perfect prediction)
    svg += `<line x1="${sx(min)}" y1="${sy(min)}" x2="${sx(max)}" y2="${sy(max)}" stroke="var(--text-muted)" stroke-dasharray="6" stroke-width="1.5"/>`;
    // Points
    dataPoints.forEach(d => {
        const color = TEAMS[d.constructor]?.color || '#666';
        const label = d.entity_id || d.driver_id || '';
        svg += `<circle cx="${sx(d.pred)}" cy="${sy(d.actual)}" r="5" fill="${color}" opacity="0.8">
            <title>${label} R${d.round}: Pred ${d.pred.toFixed(1)}, Actual ${d.actual}</title>
        </circle>`;
    });
    // Axis labels
    svg += `<text x="${width / 2}" y="${height - 5}" text-anchor="middle" fill="var(--text-secondary)" font-size="12">Predicted Points</text>`;
    svg += `<text x="12" y="${height / 2}" text-anchor="middle" fill="var(--text-secondary)" font-size="12" transform="rotate(-90,12,${height / 2})">Actual Points</text>`;
    svg += '</svg>';
    return svg;
}

// =====================================================================
// RACE DEEP DIVE TAB
// =====================================================================

let deepDiveCache = {};
let deepDiveCharts = [];
let articlesData = null;
function ddFix(v, decimals = 3) { return v != null ? v.toFixed(decimals) : '-'; }

async function loadDeepDiveData(roundNum) {
    if (deepDiveCache[roundNum]) return deepDiveCache[roundNum];
    try {
        const resp = await fetch(cacheBust(`data/deep_dive_round${roundNum}.json`));
        if (!resp.ok) return null;
        const d = await resp.json();
        deepDiveCache[roundNum] = d;
        return d;
    } catch(e) { return null; }
}

function destroyDeepDiveCharts() {
    deepDiveCharts.forEach(c => { try { c.destroy(); } catch(e) {} });
    deepDiveCharts = [];
}

function ddColor(dd, id) {
    const cid = dd.driver_constructors[id];
    return dd.team_colors[cid] || '#888';
}

function initDeepDiveTab() {
    const sel = document.getElementById('deepdiveRoundSelect');
    if (!sel) return;
    sel.innerHTML = '';
    // Use seasonSummary.rounds which has has_actual flags, falling back to checking deep_dive files directly
    const rounds = (seasonSummary && seasonSummary.rounds || [])
        .filter(r => r.has_actual)
        .map(r => ({ round: r.round, name: r.name || r.race_name || `Round ${r.round}` }));
    if (!rounds.length) {
        sel.innerHTML = '<option>No race data yet</option>';
        return;
    }
    rounds.forEach(r => {
        const opt = document.createElement('option');
        opt.value = r.round;
        opt.textContent = `R${r.round} \u2014 ${r.name}`;
        sel.appendChild(opt);
    });
    sel.value = rounds[rounds.length - 1].round;
    sel.addEventListener('change', () => renderDeepDive(parseInt(sel.value)));
    renderDeepDive(parseInt(sel.value));
}

async function renderDeepDive(roundNum) {
    const el = document.getElementById('deepdiveContent');
    if (!el) return;
    el.innerHTML = '<p class="no-data">Loading deep dive data...</p>';

    const chartLoad = ensureChartJs();
    const dd = await loadDeepDiveData(roundNum);
    if (!dd || !dd.driver_metrics) {
        el.innerHTML = '<p class="no-data">No deep dive data available for this round.</p>';
        return;
    }

    destroyDeepDiveCharts();

    const drivers = Object.keys(dd.driver_metrics);
    const metrics = dd.driver_metrics;
    const sorted = [...drivers].sort((a, b) => metrics[a].avg_lap - metrics[b].avg_lap);

    let html = `<h3 class="deepdive-race-title">${dd.race} \u2014 ${dd.season}</h3>`;

    // How it works explainer
    html += `
    <div class="collapsible-section">
        <div class="section-header"><h3>How This Analysis Works</h3><span class="toggle-icon">\u25BC</span></div>
        <div class="section-body">
            <div class="analysis-note" style="font-style:normal; line-height:1.7;">
                <strong>Data Cleaning:</strong> Removes pit in/out laps, lap 1, safety car laps, inaccurate laps, and outliers beyond 107% of a driver's median.<br>
                <strong>Fuel Correction:</strong> Cars burn ~0.035s/lap of fuel. Earlier laps on a full tank are inherently slower. We normalize all laps to low-fuel equivalent so lap 5 and lap 50 are directly comparable.<br>
                <strong>Best N-Lap Avg:</strong> Fastest consecutive N-lap window. 3-lap = quali-style bursts, 10-lap = sustained race pace.<br>
                <strong>Theoretical Best:</strong> Sum of each driver's personal best S1 + S2 + S3 from any lap \u2014 the fastest possible lap if every sector was perfect.<br>
                <strong>Deg Rate:</strong> Linear regression slope of lap time vs tyre age. Higher = tyres wearing faster.<br>
                <strong>Tyre Cliff:</strong> Flagged when the last 3 laps of a stint degrade >2\u00d7 the stint average.
            </div>
        </div>
    </div>`;

    // 1. DRIVER PACE SUMMARY TABLE
    html += `
    <div class="collapsible-section open">
        <div class="section-header"><h3>Driver Pace Summary (Fuel-Corrected)</h3><span class="toggle-icon">\u25BC</span></div>
        <div class="section-body">
        <p class="analysis-note">All times adjusted for fuel load. Gap = seconds slower than the fastest driver. Std Dev measures consistency (lower = steadier).</p>
        <div class="table-wrapper">
        <table class="data-table sortable" id="dd-pace-table">
            <thead><tr>
                <th>#</th><th>Driver</th><th>Team</th>
                <th class="num" title="Average fuel-corrected lap time across all clean laps">Avg Lap</th><th class="num" title="Median fuel-corrected lap time (less affected by outliers than average)">Median</th>
                <th class="num" title="Single fastest fuel-corrected lap">Best Lap</th><th class="num" title="Best consecutive 3-lap average \u2014 shows peak short-burst pace">3-Lap Avg</th>
                <th class="num" title="Best consecutive 5-lap average">5-Lap Avg</th><th class="num" title="Best consecutive 10-lap average \u2014 true race pace indicator">10-Lap Avg</th>
                <th class="num" title="Best S1 + Best S2 + Best S3 from any lap \u2014 theoretical perfect lap">Theo. Best</th><th class="num" title="Gap to fastest driver in seconds (0 = pace leader)">Gap</th>
                <th class="num" title="Standard deviation of lap times \u2014 lower = more consistent">Std Dev</th><th class="num" title="Number of clean laps used in analysis (after filtering)">Laps</th>
            </tr></thead><tbody>`;
    sorted.forEach((d, i) => {
        const m = metrics[d];
        const team = TEAMS[dd.driver_constructors[d]] || { name: dd.driver_constructors[d], color: '#666' };
        const gap = m.pace_delta === 0 ? 'Leader' : `+${ddFix(m.pace_delta)}`;
        html += `<tr>
            <td>${i+1}</td>
            <td><span class="team-dot" style="background:${team.color}"></span>${d}</td>
            <td>${team.name}</td>
            <td class="num">${ddFix(m.avg_lap)}</td>
            <td class="num">${ddFix(m.median_lap)}</td>
            <td class="num">${ddFix(m.best_lap)}</td>
            <td class="num">${ddFix(m.best_3_lap_avg)}</td>
            <td class="num">${ddFix(m.best_5_lap_avg)}</td>
            <td class="num">${ddFix(m.best_10_lap_avg)}</td>
            <td class="num">${ddFix(m.theoretical_best)}</td>
            <td class="num ${m.pace_delta === 0 ? 'positive' : ''}">${gap}</td>
            <td class="num">${ddFix(m.lap_time_std)}</td>
            <td class="num">${m.laps_analyzed}</td>
        </tr>`;
    });
    html += `</tbody></table></div></div></div>`;

    // 2. SECTOR ANALYSIS TABLE
    const bestS1 = Math.min(...drivers.map(d => metrics[d].best_s1));
    const bestS2 = Math.min(...drivers.map(d => metrics[d].best_s2));
    const bestS3 = Math.min(...drivers.map(d => metrics[d].best_s3));
    const sectorSorted = [...drivers].sort((a, b) =>
        (metrics[a].best_s1 + metrics[a].best_s2 + metrics[a].best_s3) -
        (metrics[b].best_s1 + metrics[b].best_s2 + metrics[b].best_s3));
    html += `
    <div class="collapsible-section">
        <div class="section-header"><h3>Sector Performance</h3><span class="toggle-icon">\u25BC</span></div>
        <div class="section-body">
        <p class="analysis-note">Personal best sector times from any lap. Purple = overall fastest in that sector. % = proportion of total lap time spent in each sector.</p>
        <div class="table-wrapper">
        <table class="data-table sortable" id="dd-sector-table">
            <thead><tr>
                <th>#</th><th>Driver</th>
                <th class="num" title="Fastest Sector 1 time from any lap">Best S1</th><th class="num" title="Fastest Sector 2 time from any lap">Best S2</th><th class="num" title="Fastest Sector 3 time from any lap">Best S3</th>
                <th class="num" title="Average Sector 1 time across all clean laps">Avg S1</th><th class="num" title="Average Sector 2 time across all clean laps">Avg S2</th><th class="num" title="Average Sector 3 time across all clean laps">Avg S3</th>
                <th class="num" title="% of total lap time spent in Sector 1">% S1</th><th class="num" title="% of total lap time spent in Sector 2">% S2</th><th class="num" title="% of total lap time spent in Sector 3">% S3</th>
            </tr></thead><tbody>`;
    sectorSorted.forEach((d, i) => {
        const m = metrics[d];
        const team = TEAMS[dd.driver_constructors[d]] || { color: '#666' };
        html += `<tr>
            <td>${i+1}</td>
            <td><span class="team-dot" style="background:${team.color}"></span>${d}</td>
            <td class="num ${m.best_s1 === bestS1 ? 'highlight-purple' : ''}">${ddFix(m.best_s1)}</td>
            <td class="num ${m.best_s2 === bestS2 ? 'highlight-purple' : ''}">${ddFix(m.best_s2)}</td>
            <td class="num ${m.best_s3 === bestS3 ? 'highlight-purple' : ''}">${ddFix(m.best_s3)}</td>
            <td class="num">${ddFix(m.avg_s1)}</td>
            <td class="num">${ddFix(m.avg_s2)}</td>
            <td class="num">${ddFix(m.avg_s3)}</td>
            <td class="num">${ddFix(m.pct_time_s1, 1)}%</td>
            <td class="num">${ddFix(m.pct_time_s2, 1)}%</td>
            <td class="num">${ddFix(m.pct_time_s3, 1)}%</td>
        </tr>`;
    });
    html += `</tbody></table></div></div></div>`;

    // 3. SPEED TRAP TABLE
    const speedSorted = [...drivers].sort((a, b) => (metrics[b].max_speed_trap || 0) - (metrics[a].max_speed_trap || 0));
    html += `
    <div class="collapsible-section">
        <div class="section-header"><h3>Speed Trap Analysis</h3><span class="toggle-icon">\u25BC</span></div>
        <div class="section-body">
        <p class="analysis-note">Top speed at the speed trap point on the main straight. Indicates straight-line performance, low-drag setups, and engine/battery deployment differences.</p>
        <div class="table-wrapper">
        <table class="data-table sortable" id="dd-speed-table">
            <thead><tr>
                <th>#</th><th>Driver</th><th>Team</th>
                <th class="num" title="Highest speed recorded at the speed trap">Max Speed (km/h)</th><th class="num" title="Average speed across all laps at the speed trap">Avg Speed (km/h)</th>
                <th class="num" title="Average speed crossing the finish line">Avg Finish Line</th>
            </tr></thead><tbody>`;
    speedSorted.forEach((d, i) => {
        const m = metrics[d];
        const team = TEAMS[dd.driver_constructors[d]] || { name: dd.driver_constructors[d], color: '#666' };
        html += `<tr>
            <td>${i+1}</td>
            <td><span class="team-dot" style="background:${team.color}"></span>${d}</td>
            <td>${team.name}</td>
            <td class="num">${ddFix(m.max_speed_trap, 1)}</td>
            <td class="num">${ddFix(m.avg_speed_trap, 1)}</td>
            <td class="num">${ddFix(m.avg_finish_line_speed, 1)}</td>
        </tr>`;
    });
    html += `</tbody></table></div></div></div>`;

    // 4. TYRE STINT TABLE
    html += `
    <div class="collapsible-section">
        <div class="section-header"><h3>Tyre Strategy & Degradation</h3><span class="toggle-icon">\u25BC</span></div>
        <div class="section-body">
        <p class="analysis-note">Per-stint breakdown. Deg Rate = seconds lost per lap from tyre wear (linear regression slope). CLIFF = last 3 laps degraded >2\u00d7 the stint average, indicating the tyre hit a performance cliff.</p>
        <div class="table-wrapper">
        <table class="data-table sortable" id="dd-stint-table">
            <thead><tr>
                <th title="Driver abbreviation">Driver</th>
                <th title="Stint number (1 = first set of tyres, 2 = after first pit stop, etc.)">Stint</th>
                <th title="Tyre compound: SOFT (fastest, degrades quickest), MEDIUM (balanced), HARD (slowest, most durable)">Compound</th>
                <th class="num" title="Number of clean laps on this set of tyres (excludes pit in/out laps, safety car laps)">Laps</th>
                <th class="num" title="Average fuel-corrected lap time across the stint. Lower = faster.">Avg Pace</th>
                <th class="num" title="Average of first 3 laps on fresh tyres. Shows initial tyre performance before degradation kicks in.">Start Pace</th>
                <th class="num" title="Average of last 3 laps before pitting or race end. Compare to Start Pace to see total degradation.">End Pace</th>
                <th class="num" title="Degradation rate: seconds lost per additional lap of tyre age, calculated via linear regression. Higher = tyres wearing faster. Negative means getting faster (e.g. track evolution, fuel burn).">Deg Rate (s/lap)</th>
                <th title="CLIFF = tyre performance cliff detected. The last 3 laps of this stint degraded more than 2x the stint average rate, indicating the tyre suddenly lost grip.">Cliff?</th>
            </tr></thead><tbody>`;
    sorted.forEach(d => {
        const stints = dd.stint_analysis[d] || [];
        const cliffs = dd.tyre_cliffs[d] || [];
        const cliffSet = new Set(cliffs.map(c => c.stint));
        const team = TEAMS[dd.driver_constructors[d]] || { color: '#666' };
        stints.forEach(s => {
            const cc = s.compound === 'SOFT' ? 'compound-soft' : s.compound === 'MEDIUM' ? 'compound-medium' : s.compound === 'HARD' ? 'compound-hard' : '';
            html += `<tr>
                <td><span class="team-dot" style="background:${team.color}"></span>${d}</td>
                <td>${s.stint}</td>
                <td><span class="compound-badge ${cc}">${s.compound}</span></td>
                <td class="num">${s.laps}</td>
                <td class="num">${ddFix(s.avg_pace)}</td>
                <td class="num">${ddFix(s.start_pace)}</td>
                <td class="num">${ddFix(s.end_pace)}</td>
                <td class="num">${ddFix(s.degradation_rate, 2)}</td>
                <td>${cliffSet.has(s.stint) ? '<span class="badge badge-red">CLIFF</span>' : ''}</td>
            </tr>`;
        });
    });
    html += `</tbody></table></div></div></div>`;

    // 5. RACE MOMENTUM TABLE
    if (dd.race_momentum && Object.keys(dd.race_momentum).length) {
        const momDrivers = [...drivers].filter(d => dd.race_momentum[d]).sort((a, b) => {
            const am = dd.race_momentum[a], bm = dd.race_momentum[b];
            const aAvg = ((am.opening||{}).rank||99) + ((am.middle||{}).rank||99) + ((am.closing||{}).rank||99);
            const bAvg = ((bm.opening||{}).rank||99) + ((bm.middle||{}).rank||99) + ((bm.closing||{}).rank||99);
            return aAvg - bAvg;
        });
        html += `
        <div class="collapsible-section">
            <div class="section-header"><h3>Race Momentum (Pace by Third)</h3><span class="toggle-icon">\u25BC</span></div>
            <div class="section-body">
            <p class="analysis-note">Race split into 3 equal parts. Rank 1 = fastest driver in that phase. Shows who was strong early (lighter fuel, fresh tyres), mid-race (strategy phase), or had a strong closing stint.</p>
            <div class="table-wrapper">
            <table class="data-table sortable" id="dd-momentum-table">
                <thead><tr>
                    <th>Driver</th>
                    <th class="num" title="Rank by fuel-corrected pace in the first third of the race">Opening Rank</th><th class="num" title="Avg fuel-corrected lap time in the first third">Opening Pace</th>
                    <th class="num" title="Rank by fuel-corrected pace in the middle third">Middle Rank</th><th class="num" title="Avg fuel-corrected lap time in the middle third">Middle Pace</th>
                    <th class="num" title="Rank by fuel-corrected pace in the final third">Closing Rank</th><th class="num" title="Avg fuel-corrected lap time in the final third">Closing Pace</th>
                </tr></thead><tbody>`;
        momDrivers.forEach(d => {
            const m = dd.race_momentum[d];
            const team = TEAMS[dd.driver_constructors[d]] || { color: '#666' };
            const op = m.opening || {}, mi = m.middle || {}, cl = m.closing || {};
            html += `<tr>
                <td><span class="team-dot" style="background:${team.color}"></span>${d}</td>
                <td class="num">${op.rank || '-'}</td><td class="num">${ddFix(op.avg_pace)}</td>
                <td class="num">${mi.rank || '-'}</td><td class="num">${ddFix(mi.avg_pace)}</td>
                <td class="num">${cl.rank || '-'}</td><td class="num">${ddFix(cl.avg_pace)}</td>
            </tr>`;
        });
        html += `</tbody></table></div></div></div>`;
    }

    // 6. TEAM SUMMARY TABLE
    if (dd.team_summary) {
        const teams = Object.keys(dd.team_summary).sort((a, b) => dd.team_summary[a].avg_pace - dd.team_summary[b].avg_pace);
        html += `
        <div class="collapsible-section">
            <div class="section-header"><h3>Team Performance Summary</h3><span class="toggle-icon">\u25BC</span></div>
            <div class="section-body">
            <p class="analysis-note">Average of both drivers' fuel-corrected pace. Best Pace = fastest single lap by either driver. Fastest Sector = which sector the team dominated.</p>
            <div class="table-wrapper">
            <table class="data-table sortable" id="dd-team-table">
                <thead><tr>
                    <th>#</th><th>Team</th><th>Drivers</th>
                    <th class="num">Avg Pace</th><th class="num">Best Pace</th>
                    <th>Fastest Sector</th>
                </tr></thead><tbody>`;
        teams.forEach((t, i) => {
            const ts = dd.team_summary[t];
            const team = TEAMS[t] || { name: t, color: '#666' };
            html += `<tr>
                <td>${i+1}</td>
                <td><span class="team-dot" style="background:${team.color}"></span>${team.name}</td>
                <td>${(ts.drivers || []).join(', ')}</td>
                <td class="num">${ddFix(ts.avg_pace)}</td>
                <td class="num">${ddFix(ts.best_pace)}</td>
                <td>${ts.fastest_sector || '-'}</td>
            </tr>`;
        });
        html += `</tbody></table></div></div></div>`;
    }

    // 8. CHART CONTAINERS — driver selector helper
    function ddDriverSelector(id, maxNote) {
        let opts = sorted.map(d => {
            const team = TEAMS[dd.driver_constructors[d]] || { name: '?' };
            return `<option value="${d}">${d} (${team.name})</option>`;
        }).join('');
        return `<div class="chart-controls">
            <label>Drivers (max ${maxNote}):</label>
            <select id="${id}" class="dd-driver-select" multiple size="1">${opts}</select>
            <button class="btn-small" data-selid="${id}" data-n="4" data-list="top">Top 4</button>
            <button class="btn-small" data-selid="${id}" data-n="10" data-list="top">Top 10</button>
            <button class="btn-small" data-selid="${id}" data-n="0" data-list="all">All</button>
        </div>`;
    }

    html += `
    <div class="collapsible-section open">
        <div class="section-header"><h3>Lap Time Evolution (Fuel-Corrected)</h3><span class="toggle-icon">\u25BC</span></div>
        <div class="section-body">
            <p class="analysis-note">Fuel-corrected lap times lap by lap. Gaps in lines indicate pit stops. Downward trends suggest improving pace or lighter fuel.</p>
            ${ddDriverSelector('dd-sel-laps', 4)}
            <div class="chart-container"><canvas id="chart-laptimes"></canvas></div>
        </div>
    </div>

    <div class="collapsible-section open">
        <div class="section-header"><h3>Position Tracker</h3><span class="toggle-icon">\u25BC</span></div>
        <div class="section-body">
            <p class="analysis-note">On-track position each lap. Line crossovers show overtakes and pit stop position swaps. Lower = better position.</p>
            ${ddDriverSelector('dd-sel-pos', 10)}
            <div class="chart-container"><canvas id="chart-positions"></canvas></div>
        </div>
    </div>

    <div class="collapsible-section">
        <div class="section-header"><h3>Lap-by-Lap Delta to Leader</h3><span class="toggle-icon">\u25BC</span></div>
        <div class="section-body">
            <p class="analysis-note">Per-lap delta to leader: how much slower (+) each driver was vs the fastest driver on that specific lap. Flat near zero = matching leader pace. Spikes = slow laps or traffic.</p>
            ${ddDriverSelector('dd-sel-gap', 8)}
            <div class="chart-container chart-tall"><canvas id="chart-gap"></canvas></div>
        </div>
    </div>

    <div class="collapsible-section">
        <div class="section-header"><h3>Sector Comparison (Best Sectors, Stacked)</h3><span class="toggle-icon">\u25BC</span></div>
        <div class="section-body">
            <p class="analysis-note">Best sector times stacked to show total theoretical lap. Shorter total bar = faster overall. Color segments show where time is gained or lost.</p>
            ${ddDriverSelector('dd-sel-sec', 10)}
            <div class="chart-container"><canvas id="chart-sectors"></canvas></div>
        </div>
    </div>

    <div class="collapsible-section">
        <div class="section-header"><h3>Tyre Degradation Curves</h3><span class="toggle-icon">\u25BC</span></div>
        <div class="section-body">
            <p class="analysis-note">Fuel-corrected lap times colored by tyre compound (Red = Soft, Yellow = Medium, White = Hard). Upward slope within a stint shows tyre degradation. Different point shapes distinguish drivers.</p>
            ${ddDriverSelector('dd-sel-tyre', 4)}
            <div class="chart-container chart-tall"><canvas id="chart-tyredeg"></canvas></div>
        </div>
    </div>

    <div class="collapsible-section">
        <div class="section-header"><h3>Speed Trap Comparison</h3><span class="toggle-icon">\u25BC</span></div>
        <div class="section-body">
            <p class="analysis-note">Maximum speed recorded at the speed trap. Higher bars indicate better straight-line performance, lower drag setup, or more efficient energy deployment.</p>
            <div class="chart-container"><canvas id="chart-speed"></canvas></div>
        </div>
    </div>`;

    el.innerHTML = html;

    // Make tables sortable
    el.querySelectorAll('table.sortable').forEach(makeTableSortable);

    // Collapsible sections
    el.querySelectorAll('.section-header').forEach(h => {
        h.addEventListener('click', () => h.parentElement.classList.toggle('open'));
    });

    // Render charts after the tab-only Chart.js dependency is ready.
    await chartLoad;
    renderDDCharts(dd, sorted);
}

function renderDDCharts(dd, sorted) {
    if (typeof Chart === 'undefined') {
        document.querySelectorAll('#deepdiveContent .chart-container').forEach(c => {
            c.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:40px;">Charts loading... refresh page.</p>';
        });
        return;
    }
    const CC = { SOFT: '#FF3333', MEDIUM: '#FFD700', HARD: '#CCCCCC', INTERMEDIATE: '#39B54A', WET: '#0067FF' };
    const GC = '#333', TC = '#999', LC = '#aaa', LGC = '#ccc';
    const shapes = ['circle', 'rect', 'triangle', 'star', 'crossRot'];

    // --- Driver selector helper ---
    function getSelected(selId, maxDrivers) {
        const sel = document.getElementById(selId);
        if (!sel) return sorted.slice(0, maxDrivers);
        const vals = Array.from(sel.selectedOptions).map(o => o.value);
        return vals.length ? vals.slice(0, maxDrivers) : sorted.slice(0, maxDrivers);
    }
    function setSelected(selId, driverList) {
        const sel = document.getElementById(selId);
        if (!sel) return;
        Array.from(sel.options).forEach(o => { o.selected = driverList.includes(o.value); });
    }
    // Pre-select defaults
    setSelected('dd-sel-laps', sorted.slice(0, 4));
    setSelected('dd-sel-pos', sorted.slice(0, 10));
    setSelected('dd-sel-gap', sorted.slice(0, 8));
    setSelected('dd-sel-sec', sorted.slice(0, 10));
    setSelected('dd-sel-tyre', sorted.slice(0, 4));

    // --- Quick-select buttons ---
    document.querySelectorAll('#deepdiveContent .btn-small[data-selid]').forEach(btn => {
        btn.addEventListener('click', () => {
            const selId = btn.dataset.selid;
            const n = parseInt(btn.dataset.n);
            const list = n === 0 ? sorted : sorted.slice(0, n);
            setSelected(selId, list);
            const sel = document.getElementById(selId);
            if (sel) sel.dispatchEvent(new Event('change'));
        });
    });

    // Linear x-axis base config
    const xLinear = { type: 'linear', title: { display: true, text: 'Lap', color: LC }, ticks: { color: TC }, grid: { color: GC } };

    // ---- LAP TIMES ----
    const lapCtx = document.getElementById('chart-laptimes');
    let lapChart = null;
    if (lapCtx && dd.lap_data) {
        function makeLapDS(drvs) {
            return drvs.filter(d => dd.lap_data[d]).map(d => ({
                label: d,
                data: dd.lap_data[d].map(l => ({ x: l.lap, y: l.fuel_corrected })),
                borderColor: ddColor(dd, d),
                borderWidth: drvs.length > 6 ? 1 : 1.5,
                pointRadius: drvs.length > 6 ? 0.5 : 2,
                pointHoverRadius: 4,
                tension: 0.3, fill: false,
            }));
        }
        lapChart = new Chart(lapCtx, {
            type: 'line',
            data: { datasets: makeLapDS(sorted.slice(0, 4)) },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'nearest', intersect: false },
                plugins: {
                    legend: { position: 'top', labels: { color: LGC, usePointStyle: true, font: { size: 11 } } },
                    tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(3)}s (Lap ${ctx.parsed.x})` } }
                },
                scales: {
                    x: { ...xLinear },
                    y: { title: { display: true, text: 'Lap Time (s)', color: LC }, ticks: { color: TC }, grid: { color: GC } }
                }
            }
        });
        deepDiveCharts.push(lapChart);
        document.getElementById('dd-sel-laps')?.addEventListener('change', () => {
            const drvs = getSelected('dd-sel-laps', 4);
            lapChart.data.datasets = makeLapDS(drvs);
            lapChart.update();
        });
    }

    // ---- POSITION TRACKER ----
    const posCtx = document.getElementById('chart-positions');
    let posChart = null;
    if (posCtx && dd.position_tracker) {
        function makePosDS(drvs) {
            return drvs.filter(d => dd.position_tracker[d]).map(d => ({
                label: d,
                data: dd.position_tracker[d].map(p => ({ x: p.lap, y: p.position })),
                borderColor: ddColor(dd, d),
                borderWidth: 2, pointRadius: 0, tension: 0.1, fill: false,
            }));
        }
        posChart = new Chart(posCtx, {
            type: 'line',
            data: { datasets: makePosDS(sorted.slice(0, 10)) },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top', labels: { color: LGC, usePointStyle: true, font: { size: 11 } } },
                    tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: P${ctx.parsed.y} (Lap ${ctx.parsed.x})` } }
                },
                scales: {
                    x: { ...xLinear },
                    y: { reverse: true, title: { display: true, text: 'Position', color: LC }, ticks: { color: TC, stepSize: 1 }, grid: { color: GC }, min: 1, max: 22 }
                }
            }
        });
        deepDiveCharts.push(posChart);
        document.getElementById('dd-sel-pos')?.addEventListener('change', () => {
            posChart.data.datasets = makePosDS(getSelected('dd-sel-pos', 10));
            posChart.update();
        });
    }

    // ---- GAP TO LEADER ----
    const gapCtx = document.getElementById('chart-gap');
    let gapChart = null;
    if (gapCtx && dd.gap_to_leader) {
        function makeGapDS(drvs) {
            return drvs.filter(d => dd.gap_to_leader[d]).map(d => ({
                label: d,
                data: dd.gap_to_leader[d].map(g => ({ x: g.lap, y: g.gap })),
                borderColor: ddColor(dd, d),
                borderWidth: 1.5, pointRadius: 0, tension: 0.2, fill: false,
            }));
        }
        gapChart = new Chart(gapCtx, {
            type: 'line',
            data: { datasets: makeGapDS(sorted.slice(0, 8)) },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top', labels: { color: LGC, usePointStyle: true, font: { size: 11 } } },
                    tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: +${ctx.parsed.y.toFixed(3)}s (Lap ${ctx.parsed.x})` } }
                },
                scales: {
                    x: { ...xLinear },
                    y: { title: { display: true, text: 'Delta to Leader (s)', color: LC }, ticks: { color: TC }, grid: { color: GC } }
                }
            }
        });
        deepDiveCharts.push(gapChart);
        document.getElementById('dd-sel-gap')?.addEventListener('change', () => {
            gapChart.data.datasets = makeGapDS(getSelected('dd-sel-gap', 8));
            gapChart.update();
        });
    }

    // ---- SECTOR COMPARISON (stacked bar) ----
    const secCtx = document.getElementById('chart-sectors');
    let secChart = null;
    if (secCtx) {
        function makeSecData(drvs) {
            return {
                labels: drvs,
                datasets: [
                    { label: 'S1', data: drvs.map(d => dd.driver_metrics[d]?.best_s1 || 0), backgroundColor: '#E80020CC' },
                    { label: 'S2', data: drvs.map(d => dd.driver_metrics[d]?.best_s2 || 0), backgroundColor: '#FF8000CC' },
                    { label: 'S3', data: drvs.map(d => dd.driver_metrics[d]?.best_s3 || 0), backgroundColor: '#27F4D2CC' },
                ]
            };
        }
        secChart = new Chart(secCtx, {
            type: 'bar',
            data: makeSecData(sorted.slice(0, 10)),
            options: {
                responsive: true, maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: {
                    legend: { position: 'top', labels: { color: LGC } },
                    tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.x.toFixed(3)}s` } }
                },
                scales: {
                    x: { stacked: true, title: { display: true, text: 'Time (s)', color: LC }, ticks: { color: TC }, grid: { color: GC } },
                    y: { stacked: true, ticks: { color: LGC }, grid: { color: GC } }
                }
            }
        });
        deepDiveCharts.push(secChart);
        document.getElementById('dd-sel-sec')?.addEventListener('change', () => {
            const drvs = getSelected('dd-sel-sec', 10);
            secChart.data = makeSecData(drvs);
            secChart.update();
        });
    }

    // ---- TYRE DEGRADATION SCATTER ----
    const tyreCtx = document.getElementById('chart-tyredeg');
    let tyreChart = null;
    if (tyreCtx && dd.lap_data) {
        function makeTyreDS(drvs) {
            const ds = [];
            drvs.forEach((d, di) => {
                const laps = dd.lap_data[d] || [];
                const byComp = {};
                laps.forEach(l => { if (!byComp[l.compound]) byComp[l.compound] = []; byComp[l.compound].push({ x: l.lap, y: l.fuel_corrected }); });
                Object.entries(byComp).forEach(([comp, pts]) => {
                    ds.push({
                        label: `${d} (${comp})`,
                        data: pts,
                        borderColor: CC[comp] || '#888',
                        backgroundColor: (CC[comp] || '#888') + '66',
                        borderWidth: 1, pointRadius: 3,
                        pointStyle: shapes[di % shapes.length],
                        showLine: true, tension: 0.2, fill: false,
                    });
                });
            });
            return ds;
        }
        tyreChart = new Chart(tyreCtx, {
            type: 'scatter',
            data: { datasets: makeTyreDS(sorted.slice(0, 4)) },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top', labels: { color: LGC, usePointStyle: true, font: { size: 10 } } },
                    tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(3)}s (Lap ${ctx.parsed.x})` } }
                },
                scales: {
                    x: { ...xLinear },
                    y: { title: { display: true, text: 'Lap Time (s)', color: LC }, ticks: { color: TC }, grid: { color: GC } }
                }
            }
        });
        deepDiveCharts.push(tyreChart);
        document.getElementById('dd-sel-tyre')?.addEventListener('change', () => {
            tyreChart.data.datasets = makeTyreDS(getSelected('dd-sel-tyre', 4));
            tyreChart.update();
        });
    }

    // ---- SPEED TRAP BAR ----
    const spdCtx = document.getElementById('chart-speed');
    if (spdCtx) {
        const spdSorted = [...sorted].sort((a, b) => (dd.driver_metrics[b].max_speed_trap || 0) - (dd.driver_metrics[a].max_speed_trap || 0)).slice(0, 15);
        const spdChart = new Chart(spdCtx, {
            type: 'bar',
            data: {
                labels: spdSorted,
                datasets: [{
                    label: 'Max Speed (km/h)',
                    data: spdSorted.map(d => dd.driver_metrics[d].max_speed_trap || 0),
                    backgroundColor: spdSorted.map(d => ddColor(dd, d) + 'CC'),
                    borderColor: spdSorted.map(d => ddColor(dd, d)),
                    borderWidth: 1,
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => `${ctx.parsed.y.toFixed(1)} km/h` } } },
                scales: {
                    x: { ticks: { color: LGC }, grid: { color: GC } },
                    y: { title: { display: true, text: 'Speed (km/h)', color: LC }, ticks: { color: TC }, grid: { color: GC },
                        beginAtZero: false, suggestedMin: Math.min(...spdSorted.map(d => dd.driver_metrics[d].max_speed_trap || 280)) - 5 }
                }
            }
        });
        deepDiveCharts.push(spdChart);
    }
}

/* ============================================================
   Articles
   ============================================================ */
async function loadArticles() {
    try {
        const resp = await fetch(cacheBust('data/articles.json'));
        if (resp.ok) articlesData = await resp.json();
    } catch(e) { articlesData = null; }
}

function renderArticles() {
    const container = document.getElementById('articlesContent');
    if (!container) return;
    if (!articlesData || !articlesData.articles || articlesData.articles.length === 0) {
        container.innerHTML = '<p class="no-data">No articles yet. Check back after the next race weekend!</p>';
        return;
    }
    const articles = articlesData.articles;
    // Sort newest first
    articles.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

    let html = '<div class="articles-list">';
    articles.forEach((art, i) => {
        const dateStr = art.date ? new Date(art.date + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : '';
        const roundBadge = art.round ? `<span class="article-round">Round ${art.round}</span>` : '';
        const tagBadges = (art.tags || []).map(t => `<span class="article-tag">${t}</span>`).join('');
        const isOpen = i === 0 ? ' open' : '';
        html += `
        <div class="article-card collapsible-section${isOpen}">
            <div class="section-header" onclick="this.parentElement.classList.toggle('open')">
                <div class="article-header-content">
                    <h3>${art.title || 'Untitled'}</h3>
                    <div class="article-meta">
                        ${roundBadge}${tagBadges}
                        <span class="article-date">${dateStr}</span>
                    </div>
                </div>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="section-body">
                <div class="article-body">${art.content_html || '<p>No content.</p>'}</div>
            </div>
        </div>`;
    });
    html += '</div>';
    container.innerHTML = html;
}

// ============================================================
// Videos Tab
// ============================================================
let videosData = null;

async function loadVideos() {
    try {
        const resp = await fetch(cacheBust('data/youtube_videos.json'));
        if (resp.ok) videosData = await resp.json();
    } catch(e) { videosData = null; }
}

function renderVideos() {
    const container = document.getElementById('videosGrid');
    if (!container) return;
    if (!videosData || !videosData.videos || videosData.videos.length === 0) {
        container.innerHTML = '<p class="no-data">No videos yet. Check back soon!</p>';
        return;
    }
    const videos = videosData.videos.slice(0, 4);
    let html = '';
    videos.forEach(v => {
        const dateStr = v.published ? new Date(v.published + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : '';
        html += `
        <div class="video-card">
            <a href="${v.url}" target="_blank" rel="noopener">
                <div class="video-thumb">
                    <img src="${v.thumbnail}" alt="${v.title}" loading="lazy">
                    <div class="video-play-icon"></div>
                </div>
                <div class="video-info">
                    <h3>${v.title}</h3>
                    <span class="video-date">${dateStr}</span>
                </div>
            </a>
        </div>`;
    });
    container.innerHTML = html;
}
