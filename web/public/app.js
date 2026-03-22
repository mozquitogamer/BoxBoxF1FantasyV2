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
    { round: 4,  race: 'Bahrain Grand Prix',           lock: '2026-04-11T15:00:00Z', sprint: false },
    { round: 5,  race: 'Saudi Arabian Grand Prix',     lock: '2026-04-18T17:00:00Z', sprint: false },
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
let tableSortColumn = null;
let tableSortAsc = true;
let allLineups = [];
let lineupsShown = 0;
const LINEUPS_PER_PAGE = 10;

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

// -- Init --
document.addEventListener('DOMContentLoaded', async () => {
    await loadData();
    await loadSeasonData();
    await preloadActualData();
    await loadPitstopData();
    startCountdown();
    setupTabs();
    setupControls();
    render();
});

async function preloadActualData() {
    // Preload all available actual round data for price change predictions
    if (!seasonSummary || !seasonSummary.rounds) return;
    const promises = seasonSummary.rounds
        .filter(r => r.has_actual)
        .map(r => loadActualData(r.round));
    await Promise.all(promises);
}

async function loadPitstopData() {
    // Load pit stop stationary times from overtakes JSON files
    window._pitstopData = {};
    if (!seasonSummary || !seasonSummary.rounds) return;
    for (const r of seasonSummary.rounds) {
        if (!r.has_actual) continue;
        try {
            const resp = await fetch(cacheBust(`data/pitstops_round${r.round}.json`));
            if (!resp.ok) continue;
            const psData = await resp.json();
            if (psData && psData.by_constructor) {
                for (const [cid, times] of Object.entries(psData.by_constructor)) {
                    if (!window._pitstopData[cid]) window._pitstopData[cid] = [];
                    window._pitstopData[cid].push(...times);
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

    // Update header
    const flag = RACE_FLAGS[data.race] || '🏁';
    document.getElementById('raceFlag').textContent = flag;
    document.getElementById('raceName').textContent = data.race;
    document.getElementById('raceMeta').textContent =
        `Round ${data.round} · ${data.season}${data.is_sprint_weekend ? ' · Sprint Weekend' : ''}`;
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
function setupTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
        });
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
        const strategy = document.getElementById('strategy').value;
        displayLineups(strategy);
    });

    // Analysis panel toggle
    document.querySelectorAll('.analysis-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.analysis-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.analysis-panel').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(`panel-${btn.dataset.panel}`).classList.add('active');
        });
    });

    // Post-race round selector
    document.getElementById('postRaceRound').addEventListener('change', async (e) => {
        const roundNum = e.target.value;
        if (!roundNum) return;
        const postRace = await loadPostRaceData(roundNum);
        const predictions = await loadPredictionsData(roundNum);
        const actual = await loadActualData(roundNum);
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
    { key: 'value_score', label: 'Value' },
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

// -- Render --
function render() {
    if (!data) return;
    renderHero();
    renderDrivers();
    renderConstructors();
    renderLockGrid();
    renderFPAnalysis();
    renderSeason();
    renderH2H();
    renderAccuracy();
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
    const bestValue = (valueCandidates.length > 0 ? valueCandidates : data.drivers)
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
    const darkHorse = (darkHorseCandidates.length > 0 ? darkHorseCandidates : data.drivers)
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
            <div class="hero-card-meta">$${driver.current_price}M \u00b7 ${(driver.value_score||0).toFixed(2)}x value</div>
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
        </div>

        <div class="card-meta">
            <div class="confidence-bar" title="Prediction confidence (0-100%). Higher = more data available and models agree. Based on FP data completeness and model agreement.">
                <span>Conf</span>
                <div class="conf-track">
                    <div class="conf-fill" style="width:${d.confidence}%;background:${confColor}"></div>
                </div>
                <span>${d.confidence}%</span>
            </div>
            <span class="risk-badge ${riskClass}" title="DNF risk based on rolling 5-race DNF probability. LOW = safe pick, HIGH = DNF-prone.">${d.risk}</span>
            <span class="price-tag" title="Current F1 Fantasy price">$${d.current_price.toFixed(1)}M</span>
            <span class="value-tag" style="position:relative;cursor:help" title="Value Score = Expected Fantasy Points / Price ($M). Higher is better. Above 1.0 = good value, above 2.0 = excellent, below 0 = negative expected return.">${d.value_score.toFixed(2)}x<span class="value-tooltip">Value Score = Expected Fantasy Points &divide; Price ($M). Higher is better. Above 1.0 = good value, above 2.0 = excellent, below 0 = negative expected return.</span></span>
        </div>
        ${d.mc_total_p5 != null ? `
        <div class="mc-range" title="Monte Carlo simulation: 90% of outcomes fall within this range (5th to 95th percentile). Shows downside risk and upside potential.">
            <span class="mc-label">MC 90% CI</span>
            <span class="mc-values">${d.mc_total_p5.toFixed(0)} — ${d.mc_total_p95.toFixed(0)} pts</span>
        </div>` : ''}
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
        <td class="num">${d.value_score.toFixed(2)}x</td>
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
            <span class="value-tag" title="Value Score = Expected Points / Price">${c.value_score.toFixed(2)}x</span>
        </div>
        ${pitHtml}
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

    // Collect past scores from actuals
    const pastScores = [];
    let cumulativeTotal = 0;
    for (const [rn, actData] of Object.entries(actualCache)) {
        if (!actData) continue;
        const isDriver = !!item.driver_id;
        const match = isDriver
            ? (actData.drivers || []).find(d => d.driver_id === item.driver_id)
            : (actData.constructors || []).find(c => c.constructor_id === item.constructor_id);
        if (match && match.total_points != null) {
            pastScores.push(match.total_points);
            cumulativeTotal += match.total_points;
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
    // With N past rounds in window: new_avg = (sum_of_last2 + X) / 3
    // For avg/price >= threshold: X >= threshold * price * 3 - sum_of_last2
    const recentWindow = pastScores.slice(-2);
    const recentSum = recentWindow.reduce((a, b) => a + b, 0);
    const windowSize = Math.min(recentWindow.length + 1, 3);
    const ptsForGreat = Math.max(0, PPM_RATINGS.GREAT * price * windowSize - recentSum);
    const ptsForGood = Math.max(0, PPM_RATINGS.GOOD * price * windowSize - recentSum);
    const ptsForPoor = PPM_RATINGS.POOR * price * windowSize - recentSum;

    return {
        avgPpm, rating, expectedChange, avgPts,
        cumulativeTotal, pastScores, isATier, tierChanges,
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

    // Score function
    function score(item) {
        if (strategy === 'max_points') return item.expected_points;
        if (strategy === 'max_value') return item.value_score;
        if (strategy === 'budget_gain') {
            // Favor items likely to increase in price
            const pc = predictPriceChange(item, item.expected_points);
            return pc.expectedChange * 100 + item.value_score * 5;
        }
        // Balanced: weighted combo
        return item.expected_points * 0.6 + item.value_score * 10 * 0.4;
    }

    // Filter out excluded picks
    const drivers = data.drivers
        .filter(d => !excludedDrivers.has(d.driver_id))
        .map(d => ({ ...d, _type: 'driver', _score: score(d) }));
    const constructors = data.constructors
        .filter(c => !excludedConstructors.has(c.constructor_id))
        .map(c => ({ ...c, _type: 'constructor', _score: score(c) }));

    // Sort by score descending
    drivers.sort((a, b) => b._score - a._score);
    constructors.sort((a, b) => b._score - a._score);

    // Brute force all valid lineups: 5 drivers + 2 constructors within budget
    allLineups = [];

    // Generate constructor pairs
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
    const neededDrivers = 5 - lockedDriverList.length;
    const lockedDriverCost = lockedDriverList.reduce((s, d) => s + d.current_price, 0);
    const lockedDriverScore = lockedDriverList.reduce((s, d) => s + d._score, 0);

    if (neededDrivers < 0) {
        alert('You have locked more than 5 drivers. Please unlock some.');
        return;
    }

    // Cap results to avoid freezing on huge searches
    const MAX_LINEUPS = 200;

    for (const cp of cPairs) {
        const remainBudget = budget - cp.cost - lockedDriverCost;
        if (remainBudget < 0) continue;

        const combos = combinations(freeDrivers, neededDrivers);
        for (const combo of combos) {
            const cost = combo.reduce((s, d) => s + d.current_price, 0);
            if (cost > remainBudget) continue;

            const allDrivers = [...lockedDriverList, ...combo];
            const totalCost = cp.cost + lockedDriverCost + cost;

            // Find highest scoring driver for 2x boost
            let boostedDriver = allDrivers[0];
            for (const d of allDrivers) {
                if (d.expected_points > boostedDriver.expected_points) boostedDriver = d;
            }

            // Total points with 2x on best driver
            const driverPoints = allDrivers.reduce((s, d) => s + d.expected_points, 0);
            const constructorPoints = cp.items.reduce((s, c) => s + c.expected_points, 0);
            const totalPoints = driverPoints + boostedDriver.expected_points + constructorPoints; // boosted driver counted twice = 2x
            // For scoring/ranking, also account for the 2x boost
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
                <div class="label" title="Sum of expected fantasy points for all 7 picks, including 2x on ${boostedSummaryName}">Expected Points (incl 2x)</div>
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
                ${lineup.totalPoints.toFixed(1)} pts (incl 2x) \u00b7 $${lineup.totalCost.toFixed(1)}M \u00b7
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
        const displayPts = isBoosted ? (d.expected_points * 2).toFixed(1) : d.expected_points.toFixed(1);
        const boostBadge = isBoosted ? '<span class="boost-badge">2x</span>' : '';
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

function getPitStopStatsHtml(constructorId) {
    // Aggregate pit stop stationary times from all cached actual data
    const stops = [];
    for (const [rn, actData] of Object.entries(actualCache)) {
        if (!actData) continue;
        // Check if we have pitstop data in the overtakes cache
    }
    // Also check global pitstopCache
    if (window._pitstopData && window._pitstopData[constructorId]) {
        const teamStops = window._pitstopData[constructorId];
        stops.push(...teamStops);
    }

    if (stops.length === 0) return '';

    stops.sort((a, b) => a - b);
    const avg = stops.reduce((a, b) => a + b, 0) / stops.length;
    const fastest = stops[0];
    const slowest = stops[stops.length - 1];
    const p10idx = Math.floor(stops.length * 0.1);
    const p90idx = Math.min(Math.floor(stops.length * 0.9), stops.length - 1);
    const p10 = stops[p10idx];
    const p90 = stops[p90idx];

    return `
    <div class="pit-stats" style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border);font-size:0.75rem;color:var(--text-secondary);">
        <div style="font-weight:600;margin-bottom:4px;" title="Stationary pit stop times (wheels up to wheels down)">Pit Stops (stationary)</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:2px 8px;">
            <span>Avg: <strong style="color:var(--text)">${avg.toFixed(2)}s</strong></span>
            <span>Fast: <strong style="color:var(--green)">${fastest.toFixed(2)}s</strong></span>
            <span>Slow: <strong style="color:var(--red, #ef4444)">${slowest.toFixed(2)}s</strong></span>
            <span>P10: ${p10.toFixed(2)}s</span>
            <span>P90: ${p90.toFixed(2)}s</span>
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

    let html = `<div class="analysis-race-header">${fpAnalysis.race} — Round ${fpAnalysis.round}</div>`;

    // Qualifying Pace
    if (fpAnalysis.qualifying_pace && Object.keys(fpAnalysis.qualifying_pace).length > 0) {
        const sorted = Object.entries(fpAnalysis.qualifying_pace)
            .filter(([,v]) => v.best_lap)
            .sort((a,b) => a[1].best_lap - b[1].best_lap);

        html += `
        <div class="analysis-block">
            <h3>Qualifying Pace (Short Runs)</h3>
            <table class="data-table">
                <thead><tr>
                    <th>#</th><th>Driver</th><th class="num">Best Lap</th>
                    <th class="num">Best 3 Avg</th><th class="num">Best 5 Avg</th>
                    <th class="num">Gap</th><th class="num">Laps</th>
                </tr></thead>
                <tbody>${sorted.map(([id, d], i) => `
                    <tr>
                        <td>${i+1}</td>
                        <td><strong>${id}</strong></td>
                        <td class="num">${fmtTime(d.best_lap)}</td>
                        <td class="num">${fmtTime(d.best_3_avg)}</td>
                        <td class="num">${fmtTime(d.best_5_avg)}</td>
                        <td class="num ${d.gap_to_fastest === 0 ? 'text-green' : ''}">${d.gap_to_fastest === 0 ? 'Leader' : '+' + d.gap_to_fastest.toFixed(3)}</td>
                        <td class="num">${d.total_laps}</td>
                    </tr>`).join('')}
                </tbody>
            </table>
        </div>`;
    }

    // Long Run Pace
    if (fpAnalysis.long_run_pace && Object.keys(fpAnalysis.long_run_pace).length > 0) {
        const sorted = Object.entries(fpAnalysis.long_run_pace)
            .sort((a,b) => a[1].avg_long_run_pace - b[1].avg_long_run_pace);

        html += `
        <div class="analysis-block">
            <h3>Long Run Pace (Predicted Race Pace)</h3>
            <table class="data-table">
                <thead><tr>
                    <th>#</th><th>Driver</th><th class="num">Avg Pace</th>
                    <th class="num">Gap</th><th class="num">Laps</th>
                    <th>Runs</th>
                </tr></thead>
                <tbody>${sorted.map(([id, d], i) => `
                    <tr>
                        <td>${i+1}</td>
                        <td><strong>${id}</strong></td>
                        <td class="num">${fmtTime(d.avg_long_run_pace)}</td>
                        <td class="num ${d.gap_to_fastest === 0 ? 'text-green' : ''}">${d.gap_to_fastest === 0 ? 'Leader' : '+' + d.gap_to_fastest.toFixed(3)}</td>
                        <td class="num">${d.total_long_run_laps}</td>
                        <td>${d.runs.map(r => `<span class="compound-badge ${r.compound.toLowerCase()}">${r.compound} (${r.laps}L, ${fmtTime(r.avg_pace)})</span>`).join(' ')}</td>
                    </tr>`).join('')}
                </tbody>
            </table>
        </div>`;
    }

    // Tyre Degradation
    if (fpAnalysis.tyre_degradation && Object.keys(fpAnalysis.tyre_degradation).length > 0) {
        const entries = Object.entries(fpAnalysis.tyre_degradation);
        html += `
        <div class="analysis-block">
            <h3>Tyre Degradation</h3>
            <div class="deg-grid">${entries.map(([id, compounds]) => {
                const compoundEntries = Object.entries(compounds);
                return `
                <div class="deg-card">
                    <div class="deg-driver">${id}</div>
                    ${compoundEntries.map(([comp, data]) => `
                        <div class="deg-compound">
                            <span class="compound-badge ${comp.toLowerCase()}">${comp}</span>
                            <span class="deg-rate ${data.avg_degradation <= 0.03 ? 'deg-good' : data.avg_degradation <= 0.06 ? 'deg-ok' : 'deg-bad'}">
                                ${data.avg_degradation >= 0 ? '+' : ''}${data.avg_degradation.toFixed(4)}s/lap
                            </span>
                        </div>
                    `).join('')}
                </div>`;
            }).join('')}</div>
        </div>`;
    }

    // Consistency
    if (fpAnalysis.consistency && Object.keys(fpAnalysis.consistency).length > 0) {
        const sorted = Object.entries(fpAnalysis.consistency)
            .sort((a,b) => a[1].cv - b[1].cv);

        html += `
        <div class="analysis-block">
            <h3>Consistency</h3>
            <table class="data-table">
                <thead><tr>
                    <th>#</th><th>Driver</th><th class="num">CV</th>
                    <th class="num">Std Dev</th><th class="num">Within 102%</th>
                    <th class="num">Best Lap</th><th class="num">Laps</th>
                </tr></thead>
                <tbody>${sorted.map(([id, d], i) => `
                    <tr>
                        <td>${i+1}</td>
                        <td><strong>${id}</strong></td>
                        <td class="num">${(d.cv * 100).toFixed(2)}%</td>
                        <td class="num">${d.std.toFixed(3)}s</td>
                        <td class="num">${d.laps_within_102pct.toFixed(0)}%</td>
                        <td class="num">${fmtTime(d.best_lap)}</td>
                        <td class="num">${d.total_laps}</td>
                    </tr>`).join('')}
                </tbody>
            </table>
        </div>`;
    }

    // Session Evolution
    if (fpAnalysis.session_evolution && Object.keys(fpAnalysis.session_evolution).length > 0) {
        const sorted = Object.entries(fpAnalysis.session_evolution)
            .sort((a,b) => (b[1].improvement || 0) - (a[1].improvement || 0));

        html += `
        <div class="analysis-block">
            <h3>Session Evolution (FP1 → FP3)</h3>
            <table class="data-table">
                <thead><tr>
                    <th>#</th><th>Driver</th><th class="num">FP1</th>
                    <th class="num">FP2</th><th class="num">FP3</th>
                    <th class="num">Improvement</th>
                </tr></thead>
                <tbody>${sorted.map(([id, d], i) => `
                    <tr>
                        <td>${i+1}</td>
                        <td><strong>${id}</strong></td>
                        <td class="num">${d.sessions.FP1 ? fmtTime(d.sessions.FP1) : '-'}</td>
                        <td class="num">${d.sessions.FP2 ? fmtTime(d.sessions.FP2) : '-'}</td>
                        <td class="num">${d.sessions.FP3 ? fmtTime(d.sessions.FP3) : '-'}</td>
                        <td class="num ${d.improved ? 'text-green' : 'text-red'}">${d.improvement > 0 ? '-' : '+'}${Math.abs(d.improvement).toFixed(3)}s</td>
                    </tr>`).join('')}
                </tbody>
            </table>
        </div>`;
    }

    el.innerHTML = html;
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
    const data = postRaceData;
    if (data) {
        if (!html) {
            html += `<div class="analysis-race-header">${data.race} — Round ${data.round}</div>`;
        }

        // Race Results as driver cards
        if (data.results && data.results.length > 0) {
            html += `
            <div class="analysis-block">
                <h3>Race Results</h3>
                <div class="postrace-cards">
                    ${data.results.map(r => {
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
    if (data.race_pace && Object.keys(data.race_pace).length > 0) {
        const sorted = Object.entries(data.race_pace)
            .sort((a,b) => a[1].avg_race_pace - b[1].avg_race_pace);

        html += `
        <div class="analysis-block">
            <h3>Normalized Race Pace</h3>
            <table class="data-table">
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
        </div>`;
    }

    // Pit Stops by Team
    if (data.pitstops && data.pitstops.by_team && data.pitstops.by_team.length > 0) {
        html += `
        <div class="analysis-block">
            <h3>Pit Stop Performance</h3>
            <table class="data-table">
                <thead><tr>
                    <th>#</th><th>Team</th><th class="num">Avg Time</th>
                    <th class="num">Best Time</th><th class="num">Stops</th>
                </tr></thead>
                <tbody>${data.pitstops.by_team.map((t, i) => `
                    <tr>
                        <td>${i+1}</td>
                        <td><strong>${t.constructor_name}</strong></td>
                        <td class="num">${t.avg_pitstop.toFixed(3)}s</td>
                        <td class="num">${t.best_pitstop.toFixed(3)}s</td>
                        <td class="num">${t.total_stops}</td>
                    </tr>`).join('')}
                </tbody>
            </table>
        </div>`;
    }

    // Tyre Management
    if (data.tyre_management && Object.keys(data.tyre_management).length > 0) {
        const sorted = Object.entries(data.tyre_management)
            .sort((a,b) => b[1].management_score - a[1].management_score);

        html += `
        <div class="analysis-block">
            <h3>Tyre Management</h3>
            <table class="data-table">
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
        </div>`;
    }

    el.innerHTML = html;
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
    <div class="analysis-block">
        <h3>Predicted vs Actual — Driver Comparison</h3>
        <table class="data-table">
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
function renderSeason() {
    // Calendar
    const calEl = document.getElementById('seasonCalendar');
    if (!seasonSummary || !seasonSummary.rounds) {
        calEl.innerHTML = '<p class="no-data">No season data available. Run pipeline/08_export_website_json.py first.</p>';
    } else {
        let html = `<table class="data-table">
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

                // Load and render
                const postRace = await loadPostRaceData(roundNum);
                const predictions = await loadPredictionsData(roundNum);
                const actual = await loadActualData(roundNum);
                renderPostRace(postRace, predictions, actual, roundNum);
            });
        });
    }

    // Price Tracker
    const priceEl = document.getElementById('priceTracker');
    if (!seasonSummary || !seasonSummary.driver_prices || Object.keys(seasonSummary.driver_prices).length === 0) {
        priceEl.innerHTML = '<p class="no-data">No price data available yet.</p>';
    } else {
        const sorted = Object.entries(seasonSummary.driver_prices)
            .sort((a,b) => b[1].price_change - a[1].price_change);

        let html = `<table class="data-table">
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
    }

    // Cumulative Fantasy Standings (from actual data)
    const standingsEl = document.getElementById('fantasyStandings');
    if (standingsEl) {
        const driverTotals = {};
        const constructorTotals = {};
        let roundsWithData = 0;

        for (const [rn, actData] of Object.entries(actualCache)) {
            if (!actData) continue;
            roundsWithData++;
            if (actData.drivers) {
                actData.drivers.forEach(d => {
                    if (!driverTotals[d.driver_id]) {
                        driverTotals[d.driver_id] = { name: d.name, constructor: d.constructor, total: 0, rounds: 0, price: d.price };
                    }
                    driverTotals[d.driver_id].total += d.total_points || 0;
                    driverTotals[d.driver_id].rounds++;
                    driverTotals[d.driver_id].price = d.price;
                });
            }
            if (actData.constructors) {
                actData.constructors.forEach(c => {
                    if (!constructorTotals[c.constructor_id]) {
                        constructorTotals[c.constructor_id] = { name: c.name, total: 0, rounds: 0, price: c.price };
                    }
                    constructorTotals[c.constructor_id].total += c.total_points || 0;
                    constructorTotals[c.constructor_id].rounds++;
                    constructorTotals[c.constructor_id].price = c.price;
                });
            }
        }

        if (roundsWithData > 0) {
            const sortedDrivers = Object.entries(driverTotals).sort((a, b) => b[1].total - a[1].total);
            const sortedConstructors = Object.entries(constructorTotals).sort((a, b) => b[1].total - a[1].total);

            let sHtml = `<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;">`;

            // Driver standings
            sHtml += `<div>
                <h4 style="margin-bottom:12px;">Driver Fantasy Standings (${roundsWithData} rounds)</h4>
                <table class="data-table">
                    <thead><tr>
                        <th>#</th><th>Driver</th><th>Team</th>
                        <th class="num" title="Total fantasy points scored across all completed rounds">Total</th>
                        <th class="num" title="Average fantasy points per race weekend">Avg</th>
                        <th class="num" title="Total points divided by current price">PPM</th>
                    </tr></thead>
                    <tbody>${sortedDrivers.map(([id, d], i) => {
                        const team = TEAMS[d.constructor] || { name: d.constructor, color: '#666' };
                        const avg = d.rounds > 0 ? d.total / d.rounds : 0;
                        const ppm = d.price > 0 ? d.total / d.price : 0;
                        const ppmRating = ppm >= 2.0 ? 'color:var(--green)' : ppm >= 1.0 ? 'color:#22d3ee' : ppm < 0 ? 'color:var(--red, #ef4444)' : '';
                        return `<tr>
                            <td>${i + 1}</td>
                            <td><strong>${d.name || id}</strong></td>
                            <td><span class="team-dot" style="background:${team.color}"></span>${team.name}</td>
                            <td class="num"><strong>${d.total}</strong></td>
                            <td class="num">${avg.toFixed(1)}</td>
                            <td class="num" style="${ppmRating}">${ppm.toFixed(2)}</td>
                        </tr>`;
                    }).join('')}</tbody>
                </table>
            </div>`;

            // Constructor standings
            sHtml += `<div>
                <h4 style="margin-bottom:12px;">Constructor Fantasy Standings</h4>
                <table class="data-table">
                    <thead><tr>
                        <th>#</th><th>Constructor</th>
                        <th class="num">Total</th>
                        <th class="num">Avg</th>
                        <th class="num">PPM</th>
                    </tr></thead>
                    <tbody>${sortedConstructors.map(([id, c], i) => {
                        const team = TEAMS[id] || { name: c.name, color: '#666' };
                        const avg = c.rounds > 0 ? c.total / c.rounds : 0;
                        const ppm = c.price > 0 ? c.total / c.price : 0;
                        const ppmRating = ppm >= 2.0 ? 'color:var(--green)' : ppm >= 1.0 ? 'color:#22d3ee' : ppm < 0 ? 'color:var(--red, #ef4444)' : '';
                        return `<tr>
                            <td>${i + 1}</td>
                            <td><span class="team-dot" style="background:${team.color}"></span><strong>${team.name}</strong></td>
                            <td class="num"><strong>${c.total}</strong></td>
                            <td class="num">${avg.toFixed(1)}</td>
                            <td class="num" style="${ppmRating}">${ppm.toFixed(2)}</td>
                        </tr>`;
                    }).join('')}</tbody>
                </table>
            </div>`;

            sHtml += `</div>`;
            standingsEl.innerHTML = sHtml;
        } else {
            standingsEl.innerHTML = '<p class="no-data">No actual race data available yet.</p>';
        }
    }

    // Populate post-race round selector — show all rounds that have any data
    const selector = document.getElementById('postRaceRound');
    if (seasonSummary && seasonSummary.rounds) {
        selector.innerHTML = '<option value="">Select a round...</option>';
        seasonSummary.rounds
            .filter(r => r.has_post_race || r.has_predictions || r.has_actual || r.round <= (data ? data.round : 0))
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
            const ptsA = actA.total_points || 0;
            const ptsB = actB.total_points || 0;
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
                    <table class="data-table h2h-history-table">
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
            ${statRow('Value Score', dA.value_score, dB.value_score, v => v != null ? v.toFixed(2) + 'x' : '-', true)}
            ${statRow('MC Value', dA.mc_value_score, dB.mc_value_score, v => v != null ? v.toFixed(2) + 'x' : '-', true)}
            ${statRow('Price Change', dA._price_change, dB._price_change, v => (v >= 0 ? '+' : '') + v.toFixed(1), true)}
        </div>

        ${histHTML}

        <div class="h2h-recommendation">
            <div class="h2h-rec-label">Recommendation</div>
            <div class="h2h-rec-text">${recText}</div>
        </div>
    </div>`;
}

// ============================================================
// Model Accuracy Dashboard Tab
// ============================================================

let accuracyRendered = false;

async function renderAccuracy() {
    if (!data || accuracyRendered) return;
    if (!seasonSummary || !seasonSummary.rounds) return;
    const container = document.getElementById('accuracyContent');
    if (!container) return;

    const roundsWithBoth = seasonSummary.rounds.filter(r => r.has_predictions && r.has_actual);
    if (roundsWithBoth.length === 0) {
        container.innerHTML = '<p class="no-data">No rounds with both predictions and actuals available yet. Check back after a completed race weekend.</p>';
        accuracyRendered = true;
        return;
    }

    container.innerHTML = '<p class="no-data">Analyzing prediction accuracy...</p>';

    // Load all prediction/actual pairs
    const pairs = [];
    for (const r of roundsWithBoth) {
        const [pred, act] = await Promise.all([
            loadPredictionsData(r.round),
            loadActualData(r.round)
        ]);
        if (pred && act) pairs.push({ round: r.round, name: r.name, pred, act });
    }

    if (pairs.length === 0) {
        container.innerHTML = '<p class="no-data">Could not load prediction/actual data pairs.</p>';
        accuracyRendered = true;
        return;
    }

    // Compute all metrics
    const scatterPoints = [];
    const roundStats = [];
    const driverAccum = {};
    let totalPtsMAE = 0, totalPosMAE = 0, totalCIHits = 0, totalCITotal = 0, totalComparisons = 0, totalPosComparisons = 0;

    pairs.forEach(({ round, name, pred, act }) => {
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
            const actPts = a.total_points || 0;
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
                driverAccum[id] = { name: p.name || id, constructor: p.constructor || a.constructor, totalPred: 0, totalActual: 0, totalErr: 0, rounds: 0 };
            }
            driverAccum[id].totalPred += predPts;
            driverAccum[id].totalActual += actPts;
            driverAccum[id].totalErr += ptsErr;
            driverAccum[id].rounds++;
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
    const scatterSVG = buildScatterPlot(scatterPoints);

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

    // Per-round table
    const roundTableRows = roundStats.map(r => `<tr>
        <td>R${r.round}</td><td>${r.name}</td><td class="num">${r.ptsMAE}</td>
        <td class="num">${r.posMAE}</td><td class="num">${r.ciCoverage}</td>
        <td>${r.best}</td><td>${r.worst}</td>
    </tr>`).join('');

    // Per-driver table
    const driverRows = Object.values(driverAccum)
        .map(d => ({
            ...d,
            avgPred: d.totalPred / d.rounds,
            avgActual: d.totalActual / d.rounds,
            avgErr: d.totalErr / d.rounds,
            bias: (d.totalPred - d.totalActual) / d.rounds
        }))
        .sort((a, b) => b.avgErr - a.avgErr);

    const driverTableRows = driverRows.map(d => {
        const team = TEAMS[d.constructor] || { name: d.constructor, color: '#666' };
        const biasClass = d.bias > 2 ? 'bias-over' : d.bias < -2 ? 'bias-under' : '';
        const biasSign = d.bias >= 0 ? '+' : '';
        return `<tr>
            <td>${d.name}</td>
            <td style="color:${team.color}">${team.name}</td>
            <td class="num">${d.avgPred.toFixed(1)}</td>
            <td class="num">${d.avgActual.toFixed(1)}</td>
            <td class="num">${d.avgErr.toFixed(1)}</td>
            <td class="num ${biasClass}">${biasSign}${d.bias.toFixed(1)}</td>
            <td class="num">${d.rounds}</td>
        </tr>`;
    }).join('');

    container.innerHTML = `
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
            <div class="accuracy-stat-value">${pairs.length}</div>
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
            <table class="data-table accuracy-round-table">
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
            <table class="data-table accuracy-driver-table">
                <thead><tr>
                    <th>Driver</th><th>Team</th><th class="num">Avg Pred</th>
                    <th class="num">Avg Actual</th><th class="num">Avg Error</th>
                    <th class="num">Bias</th><th class="num">Rounds</th>
                </tr></thead>
                <tbody>${driverTableRows}</tbody>
            </table>
        </div>
    </div>`;

    accuracyRendered = true;
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
