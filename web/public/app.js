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

// -- 2026 F1 Fantasy Lock Deadlines (qualifying/sprint-quali start, UTC) --
// Lock deadline = start of qualifying (or sprint qualifying for sprint weekends)
const LOCK_DEADLINES = [
    { round: 1,  race: 'Australian Grand Prix',      lock: '2026-03-07T05:00:00Z', sprint: false },
    { round: 2,  race: 'Chinese Grand Prix',          lock: '2026-03-13T07:30:00Z', sprint: true  },
    { round: 3,  race: 'Japanese Grand Prix',          lock: '2026-03-28T06:00:00Z', sprint: false },
    { round: 4,  race: 'Bahrain Grand Prix',           lock: '2026-04-11T15:00:00Z', sprint: false, cancelled: true },
    { round: 5,  race: 'Saudi Arabian Grand Prix',     lock: '2026-04-18T17:00:00Z', sprint: false, cancelled: true },
    { round: 6,  race: 'Miami Grand Prix',             lock: '2026-05-01T21:30:00Z', sprint: true  },
    { round: 7,  race: 'Canadian Grand Prix',          lock: '2026-05-23T18:00:00Z', sprint: false },
    { round: 8,  race: 'Monaco Grand Prix',            lock: '2026-06-06T14:00:00Z', sprint: false },
    { round: 9,  race: 'Spanish Grand Prix',           lock: '2026-06-13T13:00:00Z', sprint: false },
    { round: 10, race: 'Austrian Grand Prix',          lock: '2026-06-26T14:30:00Z', sprint: true  },
    { round: 11, race: 'British Grand Prix',           lock: '2026-07-04T14:00:00Z', sprint: false },
    { round: 12, race: 'Belgian Grand Prix',           lock: '2026-07-18T14:00:00Z', sprint: false },
    { round: 13, race: 'Hungarian Grand Prix',         lock: '2026-07-25T14:00:00Z', sprint: false },
    { round: 14, race: 'Dutch Grand Prix',             lock: '2026-08-22T13:00:00Z', sprint: false },
    { round: 15, race: 'Italian Grand Prix',           lock: '2026-09-05T14:00:00Z', sprint: false },
    { round: 16, race: 'Spanish Grand Prix (Madrid)',   lock: '2026-09-12T14:00:00Z', sprint: false },
    { round: 17, race: 'Azerbaijan Grand Prix',        lock: '2026-09-25T12:00:00Z', sprint: false },
    { round: 18, race: 'Singapore Grand Prix',         lock: '2026-10-10T13:00:00Z', sprint: false },
    { round: 19, race: 'United States Grand Prix',     lock: '2026-10-23T21:30:00Z', sprint: true  },
    { round: 20, race: 'Mexican Grand Prix',           lock: '2026-10-31T20:00:00Z', sprint: false },
    { round: 21, race: 'Brazilian Grand Prix',         lock: '2026-11-06T18:30:00Z', sprint: true  },
    { round: 22, race: 'Las Vegas Grand Prix',         lock: '2026-11-21T04:00:00Z', sprint: false },
    { round: 23, race: 'Qatar Grand Prix',             lock: '2026-11-27T16:30:00Z', sprint: true  },
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
let tableSortColumn = null;
let tableSortAsc = true;
let allLineups = [];
let lineupsShown = 0;
const LINEUPS_PER_PAGE = 10;
// My Team state (for Transfer Advisor)
let myTeamDrivers = [null, null, null, null, null];   // 5 driver_id slots
let myTeamConstructors = [null, null];                  // 2 constructor_id slots

// -- F1 Fantasy Price Change Thresholds --
// PPM = cumulative_season_points / current_price
// A-tier: assets priced > $18.5M (smaller price swings)
// B-tier: assets priced <= $18.5M (larger price swings)
const PRICE_TIERS = {
    A_TIER_THRESHOLD: 18.5,
    A_TIER_CHANGES: { great: 0.3, good: 0.1, poor: -0.1, terrible: -0.3 },
    B_TIER_CHANGES: { great: 0.6, good: 0.2, poor: -0.2, terrible: -0.6 },
};
// PPM rating thresholds (rolling avg of last 3 rounds / price)
const PPM_RATINGS = {
    GREAT: 1.2,    // >= 1.2 PPM = Great
    GOOD: 0.9,     // >= 0.9 PPM = Good
    POOR: 0.6,     // >= 0.6 PPM = Poor
    // < 0.6 = Terrible
};

// -- Deferred loading state --
const _deferredLoaded = {};

async function ensureLoaded(key, loadFn) {
    if (_deferredLoaded[key]) return;
    _deferredLoaded[key] = true;
    await loadFn();
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
    // Drivers tab needs official points + actual data for price change predictions
    await ensureLoaded('officialPoints', loadOfficialPoints);
    await ensureLoaded('actualData', preloadActualData);
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

async function renderTabIfNeeded(tabName) {
    if (_tabRendered[tabName]) return;
    const tabId = `tab-${tabName}`;

    switch (tabName) {
        case 'drivers':
            // Already rendered on init
            break;
        case 'constructors':
            showTabSpinner(tabId);
            renderConstructors();
            removeTabSpinner(tabId);
            _tabRendered.constructors = true;
            break;
        case 'optimizer':
            renderMyTeamGrid();
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
        case 'about':
            _tabRendered.about = true;
            break;
    }
}

// -- Init --
document.addEventListener('DOMContentLoaded', async () => {
    // Phase 1: Load only essential data for home page (Drivers tab)
    await loadData();
    await loadSeasonData();
    startCountdown();
    setupTabs();
    setupControls();

    // Phase 2: Render Drivers tab immediately
    renderHero();
    renderDrivers();
    _tabRendered.drivers = true;

    // Phase 3: Load deferred data in background (non-blocking)
    // Official points + actuals needed for price change brackets on driver cards
    ensureDriversData().then(() => {
        showFallbackBanner();
        // Re-render drivers if price change data was missing initially
        renderDrivers();
    });
    ensureWeatherData().then(() => renderWeather());

    // Phase 4: If deep-linked to another tab, render it
    const hash = location.hash.replace('#', '');
    if (hash && hash !== 'drivers') {
        await renderTabIfNeeded(hash);
    }
});

async function preloadActualData() {
    // Preload all available actual round data for price change predictions
    if (!seasonSummary || !seasonSummary.rounds) return;
    const promises = seasonSummary.rounds
        .filter(r => r.has_actual)
        .map(r => loadActualData(r.round));
    await Promise.all(promises);
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
    // Load pit stop stationary times from pitstop JSON files
    window._pitstopData = {};

    if (!seasonSummary || !seasonSummary.rounds) return;
    for (const r of seasonSummary.rounds) {
        if (!r.has_actual) continue;
        // Pitstop data
        try {
            const resp = await fetch(cacheBust(`data/pitstops_round${r.round}.json`));
            if (resp.ok) {
                const psData = await resp.json();
                if (psData && psData.by_constructor) {
                    for (const [cid, times] of Object.entries(psData.by_constructor)) {
                        if (!window._pitstopData[cid]) window._pitstopData[cid] = [];
                        window._pitstopData[cid].push(...times);
                    }
                }
            }
        } catch (e) { /* no pitstop data for this round */ }
    }
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
function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    const btn = document.querySelector(`.tab[data-tab="${tabName}"]`);
    const panel = document.getElementById(`tab-${tabName}`);
    if (btn) btn.classList.add('active');
    if (panel) panel.classList.add('active');

    // Lazy render the tab content on first visit
    renderTabIfNeeded(tabName);
}

function setupTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            switchTab(tab.dataset.tab);
            history.replaceState(null, '', `#${tab.dataset.tab}`);
        });
    });

    // Deep-link: activate tab from URL hash on load
    const hash = location.hash.replace('#', '');
    if (hash && document.getElementById(`tab-${hash}`)) {
        switchTab(hash);
    }

    // Handle browser back/forward
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
}

// -- Table header sorting --
const TABLE_COLUMNS = [
    { key: null, label: '#' },
    { key: 'name', label: 'Driver' },
    { key: 'constructor', label: 'Team' },
    { key: 'expected_points', label: 'Pts' },
    { key: 'predicted_quali', label: 'Quali' },
    { key: 'predicted_finish', label: 'Race' },
    { key: 'confidence', label: 'Conf' },
    { key: 'risk', label: 'Risk' },
    { key: 'expected_overtakes', label: 'OT' },
    { key: 'current_price', label: 'Price' },
    { key: 'price_change', label: 'Change' },
    { key: 'value_score', label: 'PPM' },
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
                // Default direction: ascending for position-like columns, descending for others
                tableSortAsc = ['predicted_quali', 'predicted_finish', 'current_price', 'starting_price', 'name', 'constructor'].includes(col.key);
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
            <div class="hero-card-pts">${driver.expected_points.toFixed(1)} pts</div>
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
            <div class="weather-source">Data: ${w.data_source || 'Open-Meteo'}</div>
        </div>
    `;
}

// -- Driver rendering --
function renderDrivers() {
    if (!data) return;

    const sortKey = document.getElementById('driverSort').value;
    const teamFilter = document.getElementById('teamFilter').value;
    const searchQuery = (document.getElementById('driverSearch').value || '').trim().toLowerCase();

    let drivers = [...data.drivers];

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
    cardsEl.innerHTML = drivers.map((d, i) => driverCard(d, i)).join('');

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
    const sprintQualiPct = totalPts > 0 ? ((d.expected_points_sprint_quali || 0) / totalPts * 100) : 0;
    const sprintRacePct = totalPts > 0 ? ((d.expected_points_sprint_race || 0) / totalPts * 100) : 0;

    const confColor = d.confidence >= 80 ? 'var(--green)' :
                      d.confidence >= 60 ? 'var(--yellow)' : 'var(--orange)';

    const riskClass = d.risk === 'LOW' ? 'risk-low' :
                      d.risk === 'MEDIUM' ? 'risk-medium' : 'risk-high';

    const posChange = d.expected_positions_gained_lost;
    const posIcon = posChange > 0 ? `+${posChange}` : posChange < 0 ? `${posChange}` : '0';

    const hasSprintPts = d.expected_points_sprint_quali || d.expected_points_sprint_race;

    return `
    <div class="driver-card" style="--team-color:${team.color};--i:${i}">
        <div class="card-header">
            <div class="driver-info">
                <h3>${d.name}</h3>
                <div class="driver-team" style="color:${team.color}">${team.name}</div>
            </div>
            <div class="driver-number">${d.number}</div>
        </div>

        <div class="points-badge">
            ${d.expected_points.toFixed(1)}
            <span class="points-label">pts</span>
        </div>

        <div class="points-breakdown">
            <div class="pb-quali" style="width:${qualiPct}%"></div>
            <div class="pb-race" style="width:${racePct}%"></div>
            ${hasSprintPts ? `
                <div class="pb-sprint-quali" style="width:${sprintQualiPct}%"></div>
                <div class="pb-sprint-race" style="width:${sprintRacePct}%"></div>
            ` : ''}
        </div>
        <div class="points-legend">
            <span><span class="legend-dot" style="background:#7c3aed"></span>Quali ${d.expected_points_quali}</span>
            <span><span class="legend-dot" style="background:var(--accent)"></span>Race ${d.expected_points_race}</span>
            ${hasSprintPts ? `
                <span><span class="legend-dot" style="background:#06b6d4"></span>SQ ${d.expected_points_sprint_quali}</span>
                <span><span class="legend-dot" style="background:#f59e0b"></span>SR ${d.expected_points_sprint_race}</span>
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
            <span class="price-tag" title="Current F1 Fantasy price">$${d.current_price.toFixed(1)}M</span>
            <span class="value-tag" style="position:relative;cursor:help" title="PPM = Points Per Million. Expected Fantasy Points / Price ($M). Higher is better. Above 1.0 = good, above 2.0 = excellent.">${d.value_score.toFixed(2)} ppm<span class="value-tooltip">PPM = Points Per Million (Expected Fantasy Points &divide; Price). Higher is better. Above 1.0 = good, above 2.0 = excellent.</span></span>
        </div>
        ${d.mc_total_p5 != null ? `
        <div class="mc-range" title="Monte Carlo simulation: 90% of outcomes fall within this range (5th to 95th percentile). Shows downside risk and upside potential.">
            <span class="mc-label">MC 90% CI</span>
            <span class="mc-values">${d.mc_total_p5.toFixed(0)} — ${d.mc_total_p95.toFixed(0)} pts</span>
        </div>` : ''}
        ${renderPriceChangeBrackets(d)}
    </div>`;
}

function driverRow(d, i) {
    const team = TEAMS[d.constructor] || { name: d.constructor, color: '#666' };
    const riskClass = d.risk === 'LOW' ? 'risk-low' :
                      d.risk === 'MEDIUM' ? 'risk-medium' : 'risk-high';

    const pc = d._price_change || 0;
    const pcColor = pc > 0 ? 'color:var(--green)' : pc < 0 ? 'color:var(--red, #ef4444)' : '';
    const pcText = pc > 0 ? `+${pc.toFixed(1)}` : pc < 0 ? pc.toFixed(1) : '0.0';

    return `
    <tr>
        <td>${i + 1}</td>
        <td><strong>${d.name}</strong></td>
        <td><span class="team-dot" style="background:${team.color}"></span>${team.name}</td>
        <td class="num"><strong>${d.expected_points.toFixed(1)}</strong></td>
        <td class="num">P${d.predicted_quali}</td>
        <td class="num">P${d.predicted_finish}</td>
        <td class="num">${d.confidence}%</td>
        <td class="num"><span class="risk-badge ${riskClass}">${d.risk}</span></td>
        <td class="num">${d.expected_overtakes}</td>
        <td class="num">$${d.current_price.toFixed(1)}M</td>
        <td class="num" style="${pcColor}">${pcText}</td>
        <td class="num">${d.value_score.toFixed(2)}</td>
    </tr>`;
}

// -- Constructor rendering --
function renderConstructors() {
    if (!data) return;

    const sortKey = document.getElementById('constructorSort').value;
    let constructors = [...data.constructors];

    const ascending = ['current_price'].includes(sortKey);
    constructors.sort((a, b) => ascending ? a[sortKey] - b[sortKey] : b[sortKey] - a[sortKey]);

    const grid = document.getElementById('constructorCards');
    grid.innerHTML = constructors.map((c, i) => constructorCard(c, i)).join('');
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

    return `
    <div class="constructor-card" style="--team-color:${team.color};--i:${i}">
        <div class="constructor-header">
            <div>
                <h3>${c.full_name || c.name}</h3>
                <div class="constructor-drivers">
                    <span class="mini-driver">${c.driver_1}</span>
                    <span class="mini-driver">${c.driver_2}</span>
                </div>
            </div>
            <div class="points-badge">
                ${c.expected_points.toFixed(1)}
                <span class="points-label">pts</span>
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
            <span class="price-tag" title="Current F1 Fantasy price">$${c.current_price.toFixed(1)}M</span>
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
    const changeColor = pc.expectedChange > 0 ? 'var(--green)' : pc.expectedChange < 0 ? 'var(--red, #ef4444)' : 'var(--text-secondary)';
    const changeSign = pc.expectedChange >= 0 ? '+' : '';
    const tierLabel = pc.isATier ? 'A-tier' : 'B-tier';
    const tc = pc.tierChanges;

    // Build bracket rows — show how many points needed for each bracket
    const brackets = [
        { label: `${tc.great >= 0 ? '+' : ''}${tc.great.toFixed(1)}M`, threshold: 'great', pts: pc.ptsForGreat, color: 'var(--green)' },
        { label: `${tc.good >= 0 ? '+' : ''}${tc.good.toFixed(1)}M`, threshold: 'good', pts: pc.ptsForGood, color: '#22d3ee' },
        { label: `${tc.poor >= 0 ? '+' : ''}${tc.poor.toFixed(1)}M`, threshold: 'poor', pts: pc.ptsForPoor, color: 'var(--orange)' },
        { label: `${tc.terrible >= 0 ? '+' : ''}${tc.terrible.toFixed(1)}M`, threshold: 'terrible', pts: null, color: 'var(--red, #ef4444)' },
    ];

    // Determine which bracket the predicted score falls into
    const predicted = item.expected_points;
    let activeBracket = 'terrible';
    if (predicted >= pc.ptsForGreat) activeBracket = 'great';
    else if (predicted >= pc.ptsForGood) activeBracket = 'good';
    else if (predicted >= pc.ptsForPoor) activeBracket = 'poor';

    const sourceLabel = pc.hasOfficialData ? 'Official pts' : 'Calculated pts';
    const pastDisplay = pc.pastScores.length > 0
        ? pc.pastScores.map(s => s.toFixed(0)).join(', ')
        : 'No data';

    let bracketRows = brackets.map(b => {
        const isActive = b.threshold === activeBracket;
        const ptsText = b.pts != null ? `${Math.ceil(b.pts)} pts or more` : `< ${Math.ceil(pc.ptsForPoor)} pts`;
        return `<div class="bracket-row ${isActive ? 'bracket-active' : ''}" style="--bracket-color:${b.color}">
            <span class="bracket-change">${b.label}</span>
            <span class="bracket-pts">${ptsText}</span>
        </div>`;
    }).join('');

    return `
    <div class="price-change-section">
        <div class="price-change-header">
            <span class="price-change-title">Price Change (${tierLabel})</span>
            <span class="price-change-predicted" style="color:${changeColor}">${changeSign}${pc.expectedChange.toFixed(1)}M</span>
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
        avgPpm, rating, expectedChange, avgPts,
        cumulativeTotal, pastScores, isATier, tierChanges, hasOfficialData,
        tier: isATier ? 'A' : 'B',
        ptsForGreat, ptsForGood, ptsForPoor,
        // Compat aliases
        projectedPpm: avgPpm, projectedTotal: cumulativeTotal + predictedPts,
    };
}

// -- Lineup Optimizer --
// F1 Fantasy rules: 5 drivers + 2 constructors within budget
function runOptimizer() {
    if (!data) return;

    const budget = parseFloat(document.getElementById('budget').value);
    const strategy = document.getElementById('strategy').value;
    const chip = document.getElementById('chipSelect').value;
    const numDriverSlots = chip === 'extra_drs' ? 6 : 5;
    const effectiveBudget = chip === 'limitless' ? 999 : budget;

    // Score function
    function score(item) {
        if (strategy === 'max_points') return item.expected_points;
        if (strategy === 'max_value') return item.value_score;
        if (strategy === 'budget_gain') {
            const pc = predictPriceChange(item, item.expected_points);
            return pc.expectedChange * 100 + item.value_score * 5;
        }
        return item.expected_points * 0.6 + item.value_score * 10 * 0.4;
    }

    // Filter out excluded picks
    const drivers = data.drivers
        .filter(d => !excludedDrivers.has(d.driver_id))
        .map(d => ({ ...d, _type: 'driver', _score: score(d) }));
    const constructors = data.constructors
        .filter(c => !excludedConstructors.has(c.constructor_id))
        .map(c => ({ ...c, _type: 'constructor', _score: score(c) }));

    drivers.sort((a, b) => b._score - a._score);
    constructors.sort((a, b) => b._score - a._score);

    allLineups = [];

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
                score: constructors[i]._score + constructors[j]._score,
            });
        }
    }

    const lockedDriverList = drivers.filter(d => lockedDrivers.has(d.driver_id));
    const freeDrivers = drivers.filter(d => !lockedDrivers.has(d.driver_id));
    const neededDrivers = numDriverSlots - lockedDriverList.length;
    const lockedDriverCost = lockedDriverList.reduce((s, d) => s + d.current_price, 0);
    const lockedDriverScore = lockedDriverList.reduce((s, d) => s + d._score, 0);

    if (neededDrivers < 0) {
        alert(`You have locked more than ${numDriverSlots} drivers. Please unlock some.`);
        return;
    }

    // Cap results to avoid freezing on huge searches
    const MAX_LINEUPS = 200;

    for (const cp of cPairs) {
        const remainBudget = effectiveBudget - cp.cost - lockedDriverCost;
        if (remainBudget < 0) continue;

        const combos = combinations(freeDrivers, neededDrivers);
        for (const combo of combos) {
            const cost = combo.reduce((s, d) => s + d.current_price, 0);
            if (cost > remainBudget) continue;

            const allDrivers = [...lockedDriverList, ...combo];
            const totalCost = cp.cost + lockedDriverCost + cost;

            // Find highest scoring driver for boost
            const boostMultiplier = chip === 'mega_driver' ? 3 : 2;
            let boostedDriver = allDrivers[0];
            for (const d of allDrivers) {
                if (d.expected_points > boostedDriver.expected_points) boostedDriver = d;
            }

            // Total points with chip effects
            let driverPoints = 0;
            for (const d of allDrivers) {
                let pts = d.expected_points;
                if (chip === 'no_negative' && pts < 0) pts = 0;
                driverPoints += pts;
            }
            let constructorPoints = 0;
            for (const c of cp.items) {
                let pts = c.expected_points;
                if (chip === 'no_negative' && pts < 0) pts = 0;
                constructorPoints += pts;
            }
            let boostedPts = boostedDriver.expected_points;
            if (chip === 'no_negative' && boostedPts < 0) boostedPts = 0;
            const totalPoints = driverPoints + constructorPoints + boostedPts * (boostMultiplier - 1);

            const baseScore = cp.score + lockedDriverScore + combo.reduce((s, d) => s + d._score, 0);
            const totalScore = (strategy === 'max_points') ? totalPoints : baseScore;

            allLineups.push({
                drivers: allDrivers,
                constructors: cp.items,
                totalCost,
                totalPoints,
                totalScore,
                boostedDriverId: boostedDriver.driver_id,
            });
        }
    }

    // Sort by total score descending
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

function* combinations(arr, k) {
    if (k === 0) { yield []; return; }
    for (let i = 0; i <= arr.length - k; i++) {
        for (const rest of combinations(arr.slice(i + 1), k - 1)) {
            yield [arr[i], ...rest];
        }
    }
}

function displayLineups(strategy) {
    const resultEl = document.getElementById('optimizerResult');
    resultEl.classList.remove('hidden');

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

        // Find boosted driver name for summary
        const boostedSummaryDriver = best.drivers.find(d => d.driver_id === best.boostedDriverId);
        const boostedSummaryName = boostedSummaryDriver ? boostedSummaryDriver.name.split(' ').pop() : '?';

        document.getElementById('lineupSummary').innerHTML = `
            <div class="lineup-stat">
                <div class="big-num">${best.totalPoints.toFixed(1)}</div>
                <div class="label" title="Sum of expected fantasy points including boost on ${boostedSummaryName}">Expected Points (incl boost)</div>
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
        document.getElementById('lineupCounter').textContent = `${total} valid lineup${total !== 1 ? 's' : ''} found`;
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
    const expandedClass = index === 0 ? ' expanded' : '';
    let html = `<div class="lineup-block${expandedClass}" style="margin-bottom:24px;" onclick="this.classList.toggle('expanded')">
        <div class="lineup-block-header">
            <h4><span class="lineup-expand-icon">\u25BC</span> Lineup #${index + 1}</h4>
            <span class="lineup-block-stats">
                ${lineup.totalPoints.toFixed(1)} pts (incl boost) \u00b7 $${lineup.totalCost.toFixed(1)}M \u00b7
                $${(budget - lineup.totalCost).toFixed(1)}M left \u00b7
                <span style="color:${totalExpChange >= 0 ? 'var(--green)' : 'var(--red, #ef4444)'}">${totalExpChange >= 0 ? '+' : ''}${totalExpChange.toFixed(1)}M exp change</span>
            </span>
        </div>
        <div class="lineup-details">
        <div class="lineup-picks-row">`;

    lineup.drivers.sort((a, b) => b.expected_points - a.expected_points);
    lineup.drivers.forEach((d, i) => {
        const team = TEAMS[d.constructor] || { color: '#666', name: d.constructor };
        const locked = lockedDrivers.has(d.driver_id);
        const isBoosted = d.driver_id === boostedId;
        const pc = predictPriceChange(d, d.expected_points);
        const changeColor = pc.expectedChange >= 0 ? 'var(--green)' : 'var(--red, #ef4444)';
        const chipSel = document.getElementById('chipSelect');
        const activeChip = chipSel ? chipSel.value : 'none';
        const boostMult = (isBoosted && activeChip === 'mega_driver') ? 3 : isBoosted ? 2 : 1;
        const displayPts = (d.expected_points * boostMult).toFixed(1);
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
            <div class="pick-h-pts">${c.expected_points.toFixed(1)}<span class="pick-h-pts-label"> pts</span></div>
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

    // Update budget display based on team cost
    const totalCost = getMyTeamCost();
    if (totalCost > 0) {
        document.getElementById('transferBudget').value = totalCost.toFixed(1);
    }

    // Click handlers
    grid.querySelectorAll('.my-team-slot').forEach(slot => {
        slot.addEventListener('click', (e) => {
            // If clicking the remove X, clear the slot
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
            showSlotPicker(type, idx);
        });
    });
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

function showSlotPicker(type, index) {
    const alreadySelected = type === 'driver'
        ? new Set(myTeamDrivers.filter(Boolean))
        : new Set(myTeamConstructors.filter(Boolean));

    const items = type === 'driver' ? data.drivers : data.constructors;

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
        html += `<div class="slot-picker-item${disabled}" data-id="${id}">
            <span class="sp-dot" style="background:${team.color}"></span>
            <span class="sp-name">${name}</span>
            <span class="sp-price">$${item.current_price.toFixed(1)}M</span>
        </div>`;
    });
    html += '</div>';
    overlay.innerHTML = html;
    document.body.appendChild(overlay);

    overlay.querySelectorAll('.slot-picker-item:not(.disabled)').forEach(el => {
        el.addEventListener('click', () => {
            const id = el.dataset.id;
            if (type === 'driver') myTeamDrivers[index] = id;
            else myTeamConstructors[index] = id;
            overlay.remove();
            renderMyTeamGrid();
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

    // Validate team
    const currentDriverIds = myTeamDrivers.filter(Boolean);
    const currentConstructorIds = myTeamConstructors.filter(Boolean);
    if (currentDriverIds.length < 5 || currentConstructorIds.length < 2) {
        alert('Please select your full current team (5 drivers + 2 constructors) before running the transfer advisor.');
        return;
    }

    const isWildcard = chip === 'wildcard';
    const maxTransfers = isWildcard ? 7 : freeTransfers; // Wildcard = unlimited
    const transferPenalty = 10; // -10 pts per extra transfer

    // Score function
    function score(item) {
        if (strategy === 'max_points') return item.expected_points;
        if (strategy === 'max_value') return item.value_score;
        if (strategy === 'budget_gain') {
            const pc = predictPriceChange(item, item.expected_points);
            return pc.expectedChange * 100 + item.value_score * 5;
        }
        return item.expected_points * 0.6 + item.value_score * 10 * 0.4;
    }

    // Apply chip modifiers to scoring
    function chipAdjustedPoints(picks, boostedId) {
        let total = 0;
        for (const p of picks) {
            let pts = p.expected_points;
            if (chip === 'no_negative' && pts < 0) pts = 0;
            if (p.driver_id === boostedId) {
                pts *= (chip === 'mega_driver' ? 3 : 2);
            } else if (p.driver_id) {
                // non-boosted drivers get normal points
            }
            total += pts;
        }
        return total;
    }

    const allDrivers = data.drivers.filter(d => !excludedDrivers.has(d.driver_id));
    const allConstructors = data.constructors.filter(c => !excludedConstructors.has(c.constructor_id));

    const numDriverSlots = chip === 'extra_drs' ? 6 : 5;
    const effectiveBudget = chip === 'limitless' ? 999 : budget;

    // Generate all valid lineups and score them, tracking transfers needed
    const results = [];
    const MAX_RESULTS = 200;

    // Generate constructor pairs
    const cPairs = [];
    for (let i = 0; i < allConstructors.length; i++) {
        for (let j = i + 1; j < allConstructors.length; j++) {
            cPairs.push({
                items: [allConstructors[i], allConstructors[j]],
                cost: allConstructors[i].current_price + allConstructors[j].current_price,
            });
        }
    }

    // Cap total iterations to prevent browser freeze (C(22,5)*C(11,2) = ~1.45M)
    const MAX_ITERATIONS = 500000;
    let iterations = 0;
    let hitCap = false;

    for (const cp of cPairs) {
        if (hitCap) break;
        // Pre-check: skip constructor pairs that don't keep any locked constructors
        const newConIds = new Set(cp.items.map(c => c.constructor_id));
        let conTransfers = 0;
        for (const cid of currentConstructorIds) {
            if (!newConIds.has(cid)) conTransfers++;
        }
        // If constructor transfers alone exceed limit, skip this pair
        if (!isWildcard && conTransfers > maxTransfers + 3) continue;

        const combos = combinations(allDrivers, numDriverSlots);
        for (const combo of combos) {
            if (++iterations > MAX_ITERATIONS) { hitCap = true; break; }

            const driverCost = combo.reduce((s, d) => s + d.current_price, 0);
            const totalCost = cp.cost + driverCost;
            if (totalCost > effectiveBudget) continue;

            // Count transfers needed
            const newDriverIds = new Set(combo.map(d => d.driver_id));
            let transfersNeeded = conTransfers;
            for (const did of currentDriverIds) {
                if (!newDriverIds.has(did)) transfersNeeded++;
            }
            // For extra_drs, the 6th driver is always "new" but doesn't cost a transfer
            if (chip === 'extra_drs') {
                // Only count transfers for the 5 original slots
                const kept = combo.filter(d => currentDriverIds.includes(d.driver_id)).length;
                transfersNeeded = currentDriverIds.length - kept + conTransfers;
            }

            if (!isWildcard && transfersNeeded > maxTransfers + 3) continue; // cap search space

            // Find best boost driver
            let boostedDriver = combo[0];
            for (const d of combo) {
                const bpts = chip === 'mega_driver' ? d.expected_points * 3 : d.expected_points * 2;
                const cpts = chip === 'mega_driver' ? boostedDriver.expected_points * 3 : boostedDriver.expected_points * 2;
                if (bpts > cpts) boostedDriver = d;
            }

            const allPicks = [...combo, ...cp.items];
            const totalPoints = chipAdjustedPoints(allPicks, boostedDriver.driver_id);

            // Penalty for extra transfers
            const extraTransfers = Math.max(0, transfersNeeded - freeTransfers);
            const penalty = isWildcard ? 0 : extraTransfers * transferPenalty;
            const netPoints = totalPoints - penalty;

            // Final score
            const baseScore = [...combo, ...cp.items].reduce((s, x) => s + score(x), 0);
            const finalScore = (strategy === 'max_points') ? netPoints : baseScore - penalty;

            results.push({
                drivers: combo,
                constructors: cp.items,
                totalCost,
                totalPoints,
                netPoints,
                transfersNeeded,
                extraTransfers,
                penalty,
                boostedDriverId: boostedDriver.driver_id,
                totalScore: finalScore,
            });
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

    // Take top results
    allLineups = unique.slice(0, MAX_RESULTS);

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
    displayTransferResults(strategy, chip);
}

function displayTransferResults(strategy, chip) {
    const resultEl = document.getElementById('optimizerResult');
    resultEl.classList.remove('hidden');

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
        document.getElementById('lineupCards').innerHTML = '';
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

    // Build swaps
    const driversOut = currentDriverIds.filter(id => !newDriverIds.includes(id));
    const driversIn = newDriverIds.filter(id => !currentDriverIds.includes(id));
    const consOut = currentConstructorIds.filter(id => !newConIds.includes(id));
    const consIn = newConIds.filter(id => !currentConstructorIds.includes(id));

    const expandedClass = index === 0 ? ' expanded' : '';
    let html = `<div class="lineup-block${expandedClass}" style="margin-bottom:16px;" onclick="this.classList.toggle('expanded')">
        <div class="lineup-block-header">
            <h4><span class="lineup-expand-icon">▼</span> Option #${index + 1}</h4>
            <span class="lineup-block-stats">
                ${lineup.netPoints.toFixed(1)} net pts · ${lineup.transfersNeeded} transfer${lineup.transfersNeeded !== 1 ? 's' : ''}
                ${lineup.penalty > 0 ? ` · <span style="color:var(--red, #ef4444)">-${lineup.penalty} penalty</span>` : ''}
                · $${lineup.totalCost.toFixed(1)}M
            </span>
        </div>
        <div class="lineup-details">`;

    // Show transfer swaps
    if (driversOut.length === 0 && consOut.length === 0) {
        html += '<p style="color:var(--green);font-weight:600;margin-bottom:12px;">No transfers needed — keep your current team!</p>';
    } else {
        html += '<div style="margin-bottom:12px;">';
        for (let i = 0; i < Math.max(driversOut.length, driversIn.length); i++) {
            const outId = driversOut[i];
            const inId = driversIn[i];
            const outDriver = outId ? data.drivers.find(d => d.driver_id === outId) : null;
            const inDriver = inId ? data.drivers.find(d => d.driver_id === inId) : null;
            html += renderSwapRow(outDriver, inDriver, 'driver');
        }
        for (let i = 0; i < Math.max(consOut.length, consIn.length); i++) {
            const outId = consOut[i];
            const inId = consIn[i];
            const outCon = outId ? data.constructors.find(c => c.constructor_id === outId) : null;
            const inCon = inId ? data.constructors.find(c => c.constructor_id === inId) : null;
            html += renderSwapRow(outCon, inCon, 'constructor');
        }
        html += '</div>';
    }

    // Show resulting lineup
    html += '<div class="lineup-picks-row">';
    const sorted = [...lineup.drivers].sort((a, b) => b.expected_points - a.expected_points);
    sorted.forEach(d => {
        const team = TEAMS[d.constructor] || { color: '#666', name: d.constructor };
        const isBoosted = d.driver_id === lineup.boostedDriverId;
        const multiplier = isBoosted ? (chip === 'mega_driver' ? 3 : 2) : 1;
        const displayPts = (d.expected_points * multiplier).toFixed(1);
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
                <span>$${d.current_price.toFixed(1)}M</span>
                <span>P${d.predicted_quali}→P${d.predicted_finish}</span>
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
            <div class="pick-h-pts">${c.expected_points.toFixed(1)}<span class="pick-h-pts-label"> pts</span></div>
            <div class="pick-h-meta">
                <span>$${c.current_price.toFixed(1)}M</span>
            </div>
        </div>`;
    });
    html += '</div></div></div>';
    return html;
}

function renderSwapRow(outItem, inItem, type) {
    const outName = outItem
        ? (type === 'driver' ? outItem.name.split(' ').pop() : (outItem.name || outItem.constructor_id).toUpperCase())
        : '—';
    const inName = inItem
        ? (type === 'driver' ? inItem.name.split(' ').pop() : (inItem.name || inItem.constructor_id).toUpperCase())
        : '—';
    const outPts = outItem ? outItem.expected_points.toFixed(1) : '—';
    const inPts = inItem ? inItem.expected_points.toFixed(1) : '—';
    const outPrice = outItem ? `$${outItem.current_price.toFixed(1)}M` : '';
    const inPrice = inItem ? `$${inItem.current_price.toFixed(1)}M` : '';

    return `<div class="transfer-swap">
        <div class="transfer-out" style="flex:1">
            <div class="transfer-pick-name">${outName}</div>
            <div class="transfer-pick-detail">${outPts} pts · ${outPrice}</div>
        </div>
        <div class="transfer-arrow">→</div>
        <div class="transfer-in" style="flex:1">
            <div class="transfer-pick-name">${inName}</div>
            <div class="transfer-pick-detail">${inPts} pts · ${inPrice}</div>
        </div>
    </div>`;
}

// ============================================================

function getPitStopStatsHtml(constructorId) {
    // Aggregate pit stop stationary times from all cached actual data
    const stops = [];
    if (window._pitstopData && window._pitstopData[constructorId]) {
        stops.push(...window._pitstopData[constructorId]);
    }

    if (stops.length === 0) return '';

    stops.sort((a, b) => a - b);

    const median = stops.length % 2 === 0
        ? (stops[stops.length / 2 - 1] + stops[stops.length / 2]) / 2
        : stops[Math.floor(stops.length / 2)];
    const avg = stops.reduce((a, b) => a + b, 0) / stops.length;
    const fastest = stops[0];
    const slowest = stops[stops.length - 1];
    const slowCount = stops.filter(t => t > 3.5).length;

    const slowNote = slowCount > 0
        ? `<span style="color:var(--red, #ef4444);" title="Pit stops over 3.5s stationary">Slow (>3.5s): <strong>${slowCount}</strong></span>`
        : `<span style="color:var(--green);" title="No pit stops over 3.5s">Slow (>3.5s): <strong>0</strong></span>`;

    return `
    <div class="pit-stats" style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border);font-size:0.75rem;color:var(--text-secondary);">
        <div style="font-weight:600;margin-bottom:4px;" title="Stationary pit stop times (wheels up to wheels down). All stops included.">Pit Stops (stationary)</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:2px 8px;">
            <span>Median: <strong style="color:var(--text)">${median.toFixed(2)}s</strong></span>
            <span>Fast: <strong style="color:var(--green)">${fastest.toFixed(2)}s</strong></span>
            <span>Slow: <strong style="color:var(--red, #ef4444)">${slowest.toFixed(2)}s</strong></span>
            <span>Mean: ${avg.toFixed(2)}s</span>
            ${slowNote}
            <span>Count: ${stops.length}</span>
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

    // Long Run Pace
    if (fpAnalysis.long_run_pace && Object.keys(fpAnalysis.long_run_pace).length > 0) {
        const rows = Object.entries(fpAnalysis.long_run_pace).map(([id, d]) => ({
            id, avg_pace: d.avg_long_run_pace, gap: d.gap_to_fastest, laps: d.total_long_run_laps, runs: d.runs || []
        }));
        const tbl = sortableTable('fpLongRunTable', [
            { key: '_rank', label: '#', cls: 'num', fmt: (r, i) => i + 1 },
            { key: 'id', label: 'Driver', fmt: r => `<strong>${r.id}</strong>` },
            { key: 'avg_pace', label: 'Avg Pace', cls: 'num', title: 'Average lap time across all long run stints (5+ laps). Lower = faster race pace.', fmt: r => fmtTime(r.avg_pace) },
            { key: 'gap', label: 'Gap', cls: 'num', title: 'Gap to fastest long-run driver', fmt: r => r.gap === 0 ? '<span class="text-green">Leader</span>' : r.gap != null ? '+' + r.gap.toFixed(3) : '-' },
            { key: 'laps', label: 'Laps', cls: 'num', title: 'Total long-run laps (stints of 5+ laps)' },
            { key: 'runs', label: 'Runs', title: 'Individual stint details: compound, laps, avg pace', fmt: r => r.runs.map(s => `<span class="compound-badge ${s.compound.toLowerCase()}">${s.compound} (${s.laps}L, ${fmtTime(s.avg_pace)})</span>`).join(' ') }
        ], rows, 'avg_pace', true);
        html += `<div class="analysis-block"><h3>Long Run Pace (Predicted Race Pace)</h3><p class="analysis-note">Stints of 5+ laps on the same compound. Best indicator of race-day pace. Click headers to sort.</p>${tbl.getHtml()}</div>`;
        postRenderFns.push(tbl.renderTable);
    }

    // Fuel-Corrected Pace
    if (fpAnalysis.fuel_corrected_pace && Object.keys(fpAnalysis.fuel_corrected_pace).length > 0) {
        const rows = Object.entries(fpAnalysis.fuel_corrected_pace).map(([id, d]) => ({
            id, corrected_pace: d.avg_corrected_pace || d.corrected_pace, raw_pace: d.avg_raw_pace || d.raw_pace,
            fuel_effect: d.fuel_effect || d.correction, laps: d.laps || d.total_laps,
            gap: d.gap_to_fastest || 0
        }));
        const tbl = sortableTable('fpFuelTable', [
            { key: '_rank', label: '#', cls: 'num', fmt: (r, i) => i + 1 },
            { key: 'id', label: 'Driver', fmt: r => `<strong>${r.id}</strong>` },
            { key: 'corrected_pace', label: 'Corrected Pace', cls: 'num', title: 'Lap time adjusted for estimated fuel load (removes fuel weight advantage of late-stint laps)', fmt: r => r.corrected_pace ? fmtTime(r.corrected_pace) : '-' },
            { key: 'raw_pace', label: 'Raw Pace', cls: 'num', title: 'Unadjusted average lap time', fmt: r => r.raw_pace ? fmtTime(r.raw_pace) : '-' },
            { key: 'gap', label: 'Gap', cls: 'num', title: 'Gap to fastest fuel-corrected pace', fmt: r => r.gap === 0 ? '<span class="text-green">Leader</span>' : '+' + (r.gap || 0).toFixed(3) },
            { key: 'laps', label: 'Laps', cls: 'num' }
        ], rows, 'corrected_pace', true);
        html += `<div class="analysis-block"><h3>Fuel-Corrected Pace</h3><p class="analysis-note">Lap times adjusted for estimated fuel load to give a truer picture of underlying pace.</p>${tbl.getHtml()}</div>`;
        postRenderFns.push(tbl.renderTable);
    }

    // Tyre Degradation
    if (fpAnalysis.tyre_degradation && Object.keys(fpAnalysis.tyre_degradation).length > 0) {
        const entries = Object.entries(fpAnalysis.tyre_degradation);
        html += `
        <div class="analysis-block">
            <h3>Tyre Degradation</h3>
            <p class="analysis-note">Seconds lost per additional lap of tyre age. Green = low degradation, red = high. Lower is better for race strategy.</p>
            <div class="deg-grid">${entries.map(([id, compounds]) => {
                const compoundEntries = Object.entries(compounds);
                return `
                <div class="deg-card">
                    <div class="deg-driver">${id}</div>
                    ${compoundEntries.map(([comp, data]) => {
                        const deg = data.avg_degradation;
                        if (deg == null) return '';
                        return `
                        <div class="deg-compound">
                            <span class="compound-badge ${comp.toLowerCase()}">${comp}</span>
                            <span class="deg-rate ${deg <= 0.03 ? 'deg-good' : deg <= 0.06 ? 'deg-ok' : 'deg-bad'}">
                                ${deg >= 0 ? '+' : ''}${deg.toFixed(4)}s/lap
                            </span>
                        </div>`;
                    }).join('')}
                </div>`;
            }).join('')}</div>
        </div>`;
    }

    // Stint Breakdown
    if (fpAnalysis.stint_breakdown && Object.keys(fpAnalysis.stint_breakdown).length > 0) {
        const rows = [];
        Object.entries(fpAnalysis.stint_breakdown).forEach(([id, stints]) => {
            (Array.isArray(stints) ? stints : Object.values(stints)).forEach(s => {
                rows.push({
                    id, stint: s.stint || s.stint_number || 0, compound: s.compound || '?',
                    laps: s.laps || s.lap_count || 0, avg_pace: s.avg_pace || s.avg_time || 0,
                    first_lap: s.first_lap_pace || s.first_lap || 0, last_lap: s.last_lap_pace || s.last_lap || 0,
                    deg: s.degradation || s.deg_rate || 0
                });
            });
        });
        if (rows.length > 0) {
            const tbl = sortableTable('fpStintTable', [
                { key: 'id', label: 'Driver', fmt: r => `<strong>${r.id}</strong>` },
                { key: 'stint', label: 'Stint', cls: 'num', title: 'Stint number within the session' },
                { key: 'compound', label: 'Tyre', title: 'Tyre compound used', fmt: r => `<span class="compound-badge ${r.compound.toLowerCase()}">${r.compound}</span>` },
                { key: 'laps', label: 'Laps', cls: 'num' },
                { key: 'avg_pace', label: 'Avg Pace', cls: 'num', title: 'Average lap time across the stint', fmt: r => r.avg_pace ? fmtTime(r.avg_pace) : '-' },
                { key: 'first_lap', label: 'First Lap', cls: 'num', title: 'Pace of first timed lap in stint', fmt: r => r.first_lap ? fmtTime(r.first_lap) : '-' },
                { key: 'last_lap', label: 'Last Lap', cls: 'num', title: 'Pace of last lap in stint', fmt: r => r.last_lap ? fmtTime(r.last_lap) : '-' },
                { key: 'deg', label: 'Deg (s/lap)', cls: 'num', title: 'Degradation rate: seconds lost per lap of tyre age', fmt: r => r.deg ? (r.deg >= 0 ? '+' : '') + r.deg.toFixed(4) : '-' }
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

    // Session Evolution
    if (fpAnalysis.session_evolution && Object.keys(fpAnalysis.session_evolution).length > 0) {
        const rows = Object.entries(fpAnalysis.session_evolution).map(([id, d]) => ({
            id, fp1: d.sessions.FP1 || null, fp2: d.sessions.FP2 || null, fp3: d.sessions.FP3 || null,
            improvement: d.improvement || 0, improved: d.improved
        }));
        const tbl = sortableTable('fpEvoTable', [
            { key: '_rank', label: '#', cls: 'num', fmt: (r, i) => i + 1 },
            { key: 'id', label: 'Driver', fmt: r => `<strong>${r.id}</strong>` },
            { key: 'fp1', label: 'FP1', cls: 'num', fmt: r => r.fp1 ? fmtTime(r.fp1) : '-' },
            { key: 'fp2', label: 'FP2', cls: 'num', fmt: r => r.fp2 ? fmtTime(r.fp2) : '-' },
            { key: 'fp3', label: 'FP3', cls: 'num', fmt: r => r.fp3 ? fmtTime(r.fp3) : '-' },
            { key: 'improvement', label: 'Improvement', cls: 'num', title: 'Pace gain from first to last session. Negative = got faster.', fmt: r => `<span class="${r.improved ? 'text-green' : 'text-red'}">${r.improvement > 0 ? '-' : '+'}${Math.abs(r.improvement).toFixed(3)}s</span>` }
        ], rows, 'improvement', false);
        html += `<div class="analysis-block"><h3>Session Evolution (FP1 → FP2)</h3><p class="analysis-note">How drivers improved their pace across practice sessions. Larger improvement may indicate setup breakthroughs.</p>${tbl.getHtml()}</div>`;
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

    // Pit Stops by Team
    if (prData && prData.pitstops && prData.pitstops.by_team && prData.pitstops.by_team.length > 0) {
        html += `
        <div class="analysis-block collapsible">
            <h3 class="collapsible-header" onclick="this.parentElement.classList.toggle('collapsed')">Pit Stop Performance <span class="collapse-icon">▼</span></h3>
            <div class="collapsible-content">
            <table class="data-table sortable">
                <thead><tr>
                    <th>#</th><th>Team</th><th class="num">Avg Time</th>
                    <th class="num">Best Time</th><th class="num">Stops</th>
                </tr></thead>
                <tbody>${prData.pitstops.by_team.map((t, i) => `
                    <tr>
                        <td>${i+1}</td>
                        <td><strong>${t.constructor_name}</strong></td>
                        <td class="num">${t.avg_pitstop.toFixed(3)}s</td>
                        <td class="num">${t.best_pitstop.toFixed(3)}s</td>
                        <td class="num">${t.total_stops}</td>
                    </tr>`).join('')}
                </tbody>
            </table>
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
                        <td class="num">${d.avg_degradation.toFixed(4)}s/lap</td>
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
                            <td class="num">${d.avg_degradation.toFixed(4)}s/lap</td>
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
        const mcP95 = pred.mc_total_p95;
        const withinCI = (mcP5 != null && mcP95 != null) ? (actPts >= mcP5 && actPts <= mcP95) : null;

        if (withinCI !== null) {
            ciTotal++;
            if (withinCI) inCI++;
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

async function renderAccuracy() {
    if (!data) return;
    if (!seasonSummary || !seasonSummary.rounds) return;
    const container = document.getElementById('accuracyContent');
    if (!container) return;

    // Load data once, then re-render on filter changes
    if (!accuracyDataLoaded) {
        const roundsWithBoth = seasonSummary.rounds.filter(r => r.has_predictions && r.has_actual);
        const roundsActualOnly = seasonSummary.rounds.filter(r => !r.has_predictions && r.has_actual);
        if (roundsWithBoth.length === 0) {
            container.innerHTML = '<p class="no-data">No rounds with both predictions and actuals available yet. Check back after a completed race weekend.</p>';
            return;
        }

        if (roundsActualOnly.length > 0) {
            const names = roundsActualOnly.map(r => `R${r.round} (${r.name})`).join(', ');
            accuracyMissingNote = `<div style="background:rgba(234,179,8,0.1);border:1px solid rgba(234,179,8,0.25);color:#eab308;padding:8px 14px;border-radius:8px;font-size:0.8rem;margin-bottom:16px;">
                ${names}: Predictions were not generated before the race, so accuracy cannot be measured for ${roundsActualOnly.length === 1 ? 'this round' : 'these rounds'}.
            </div>`;
        }

        container.innerHTML = accuracyMissingNote + '<p class="no-data">Analyzing prediction accuracy...</p>';

        accuracyPairs = [];
        for (const r of roundsWithBoth) {
            const [pred, act] = await Promise.all([
                loadPredictionsData(r.round),
                loadActualData(r.round)
            ]);
            if (pred && act) accuracyPairs.push({ round: r.round, name: r.name, pred, act });
        }

        if (accuracyPairs.length === 0) {
            container.innerHTML = '<p class="no-data">Could not load prediction/actual data pairs.</p>';
            return;
        }

        // Default: all rounds selected
        accuracySelectedRounds = new Set(accuracyPairs.map(p => p.round));
        accuracyDataLoaded = true;
    }

    renderAccuracyWithFilters(container);
}

function renderAccuracyWithFilters(container) {
    const activePairs = accuracyPairs.filter(p => accuracySelectedRounds.has(p.round));

    // Compute all metrics
    const scatterPoints = [];
    const roundStats = [];
    const driverAccum = {};
    let totalPtsMAE = 0, totalPosMAE = 0, totalCIHits = 0, totalCITotal = 0, totalComparisons = 0, totalPosComparisons = 0;

    // Track latest round for per-driver latest race columns
    const latestRound = activePairs.length > 0 ? Math.max(...activePairs.map(p => p.round)) : null;

    activePairs.forEach(({ round, name, pred, act }) => {
        const predMap = {};
        if (pred.drivers) pred.drivers.forEach(d => { predMap[d.driver_id] = d; });
        const actMap = {};
        if (act.drivers) act.drivers.forEach(d => { actMap[d.driver_id] = d; });

        let rPtsMAE = 0, rPosMAE = 0, rCIHits = 0, rCITotal = 0, rCount = 0, rPosCount = 0;
        let bestErr = Infinity, worstErr = 0, bestDriver = '', worstDriver = '';

        const allIds = [...new Set([...Object.keys(predMap), ...Object.keys(actMap)])];
        allIds.forEach(id => {
            const p = predMap[id], a = actMap[id];
            if (!p || !a) return;
            const predPts = p.expected_points || 0;
            const offScore = getOfficialScore(round, id, true);
            const actPts = offScore ? offScore.points : (a.total_points || 0);
            const ptsErr = Math.abs(predPts - actPts);
            rPtsMAE += ptsErr;
            rCount++;
            totalPtsMAE += ptsErr;
            totalComparisons++;

            if (ptsErr < bestErr) { bestErr = ptsErr; bestDriver = p.name || id; }
            if (ptsErr > worstErr) { worstErr = ptsErr; worstDriver = p.name || id; }

            const predFinish = p.predicted_finish;
            const actFinish = a.race_position;
            if (predFinish != null && actFinish != null) {
                const posErr = Math.abs(predFinish - actFinish);
                rPosMAE += posErr;
                rPosCount++;
                totalPosMAE += posErr;
                totalPosComparisons++;
            }

            if (p.mc_total_p5 != null && p.mc_total_p95 != null) {
                rCITotal++;
                totalCITotal++;
                if (actPts >= p.mc_total_p5 && actPts <= p.mc_total_p95) {
                    rCIHits++;
                    totalCIHits++;
                }
            }

            scatterPoints.push({
                pred: predPts, actual: actPts, driver_id: id,
                constructor: p.constructor || a.constructor, round, name: p.name || id
            });

            // Accumulate per-driver
            if (!driverAccum[id]) {
                driverAccum[id] = { name: p.name || id, constructor: p.constructor || a.constructor, totalPred: 0, totalActual: 0, totalErr: 0, rounds: 0, latestPred: null, latestActual: null };
            }
            driverAccum[id].totalPred += predPts;
            driverAccum[id].totalActual += actPts;
            driverAccum[id].totalErr += ptsErr;
            driverAccum[id].rounds++;

            // Track latest race data
            if (round === latestRound) {
                driverAccum[id].latestPred = predPts;
                driverAccum[id].latestActual = actPts;
                driverAccum[id].latestRound = round;
            }
        });

        roundStats.push({
            round, name,
            ptsMAE: rCount > 0 ? (rPtsMAE / rCount).toFixed(1) : '-',
            posMAE: rPosCount > 0 ? (rPosMAE / rPosCount).toFixed(1) : '-',
            ciCoverage: rCITotal > 0 ? ((rCIHits / rCITotal) * 100).toFixed(0) + '%' : '-',
            best: bestDriver + ' (' + bestErr.toFixed(1) + ')',
            worst: worstDriver + ' (' + worstErr.toFixed(1) + ')'
        });
    });

    const overallPtsMAE = totalComparisons > 0 ? (totalPtsMAE / totalComparisons).toFixed(1) : '-';
    const overallPosMAE = totalPosComparisons > 0 ? (totalPosMAE / totalPosComparisons).toFixed(1) : '-';
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

    // Per-round table
    const roundTableRows = roundStats.map(r => `<tr>
        <td>R${r.round}</td><td>${r.name}</td><td class="num">${r.ptsMAE}</td>
        <td class="num">${r.posMAE}</td><td class="num">${r.ciCoverage}</td>
        <td>${r.best}</td><td>${r.worst}</td>
    </tr>`).join('');

    // Per-driver table with latest race columns
    const driverRows = Object.values(driverAccum)
        .map(d => ({
            ...d,
            avgPred: d.totalPred / d.rounds,
            avgActual: d.totalActual / d.rounds,
            avgErr: d.totalErr / d.rounds,
            bias: (d.totalPred - d.totalActual) / d.rounds
        }))
        .sort((a, b) => b.avgErr - a.avgErr);

    const latestRoundLabel = latestRound ? `R${latestRound}` : 'Latest';

    const driverTableRows = driverRows.map(d => {
        const team = TEAMS[d.constructor] || { name: d.constructor, color: '#666' };
        const biasClass = d.bias > 2 ? 'bias-over' : d.bias < -2 ? 'bias-under' : '';
        const biasSign = d.bias >= 0 ? '+' : '';
        const lPred = d.latestPred != null ? d.latestPred.toFixed(1) : '-';
        const lActual = d.latestActual != null ? d.latestActual.toFixed(0) : '-';
        const lErr = (d.latestPred != null && d.latestActual != null) ? Math.abs(d.latestPred - d.latestActual).toFixed(1) : '-';
        return `<tr>
            <td>${d.name}</td>
            <td style="color:${team.color}">${team.name}</td>
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

    container.innerHTML = accuracyMissingNote + `
    ${filterHTML}

    <div class="accuracy-stats">
        <div class="accuracy-stat-card">
            <div class="accuracy-stat-value">${overallPtsMAE}</div>
            <div class="accuracy-stat-label">Points MAE</div>
        </div>
        <div class="accuracy-stat-card">
            <div class="accuracy-stat-value">${overallPosMAE}</div>
            <div class="accuracy-stat-label">Position MAE</div>
        </div>
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
                    <th class="num">Pos MAE</th><th class="num">CI Coverage</th>
                    <th>Best Prediction</th><th>Worst Prediction</th>
                </tr></thead>
                <tbody>${roundTableRows}</tbody>
            </table>
        </div>
    </div>

    <div class="accuracy-section">
        <h3>Per-Driver Accuracy</h3>
        <div class="table-wrapper">
            <table class="data-table accuracy-driver-table sortable">
                <thead><tr>
                    <th>Driver</th><th>Team</th>
                    <th class="num">${latestRoundLabel} Pred</th><th class="num">${latestRoundLabel} Actual</th><th class="num">${latestRoundLabel} Err</th>
                    <th class="num">Avg Pred</th><th class="num">Avg Actual</th><th class="num">Avg Error</th>
                    <th class="num">Bias</th><th class="num">Rounds</th>
                </tr></thead>
                <tbody>${driverTableRows}</tbody>
            </table>
        </div>
    </div>`;

    // Wire up filter buttons
    container.querySelectorAll('.accuracy-filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const round = parseInt(btn.dataset.round);
            if (accuracySelectedRounds.has(round)) {
                accuracySelectedRounds.delete(round);
            } else {
                accuracySelectedRounds.add(round);
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
        svg += `<circle cx="${sx(d.pred)}" cy="${sy(d.actual)}" r="5" fill="${color}" opacity="0.8">
            <title>${d.driver_id} R${d.round}: Pred ${d.pred.toFixed(1)}, Actual ${d.actual}</title>
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
                <td class="num">${ddFix(s.degradation_rate, 4)}</td>
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

    // Render charts
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
