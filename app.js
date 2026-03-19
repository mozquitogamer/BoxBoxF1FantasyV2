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
    audi:           { name: 'Kick Sauber',    color: '#00E701', flag: '' },
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

// -- State --
let data = null;
let lockedDrivers = new Set();
let lockedConstructors = new Set();
let fpAnalysis = null;
let seasonSummary = null;
let postRaceCache = {};

// -- Init --
document.addEventListener('DOMContentLoaded', async () => {
    await loadData();
    await loadSeasonData();
    setupTabs();
    setupControls();
    render();
});

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

    // Optimizer
    document.getElementById('runOptimizer').addEventListener('click', runOptimizer);

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
        const data = await loadPostRaceData(e.target.value);
        renderPostRace(data);
    });
}

// -- Render --
function render() {
    if (!data) return;
    renderDrivers();
    renderConstructors();
    renderLockGrid();
    renderFPAnalysis();
    renderSeason();
}

// -- Driver rendering --
function renderDrivers() {
    if (!data) return;

    const sortKey = document.getElementById('driverSort').value;
    const teamFilter = document.getElementById('teamFilter').value;

    let drivers = [...data.drivers];

    if (teamFilter !== 'all') {
        drivers = drivers.filter(d => d.constructor === teamFilter);
    }

    // Sort
    const ascending = ['predicted_quali', 'predicted_finish', 'current_price'].includes(sortKey);
    drivers.sort((a, b) => ascending ? a[sortKey] - b[sortKey] : b[sortKey] - a[sortKey]);

    // Cards
    const cardsEl = document.getElementById('driverCards');
    cardsEl.innerHTML = drivers.map((d, i) => driverCard(d, i)).join('');

    // Table
    const tbody = document.getElementById('driverTableBody');
    tbody.innerHTML = drivers.map((d, i) => driverRow(d, i)).join('');
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
            <div class="stat">
                <div class="stat-value">P${d.predicted_quali}</div>
                <div class="stat-label">Quali</div>
            </div>
            <div class="stat">
                <div class="stat-value">P${d.predicted_finish}</div>
                <div class="stat-label">Race</div>
            </div>
            <div class="stat">
                <div class="stat-value">${posIcon}</div>
                <div class="stat-label">Pos +/-</div>
            </div>
        </div>

        <div class="card-meta">
            <div class="confidence-bar">
                <span>Conf</span>
                <div class="conf-track">
                    <div class="conf-fill" style="width:${d.confidence}%;background:${confColor}"></div>
                </div>
                <span>${d.confidence}%</span>
            </div>
            <span class="risk-badge ${riskClass}">${d.risk}</span>
            <span class="price-tag">$${d.current_price.toFixed(1)}M</span>
            <span class="value-tag">${d.value_score.toFixed(2)}x</span>
        </div>
    </div>`;
}

function driverRow(d, i) {
    const team = TEAMS[d.constructor] || { name: d.constructor, color: '#666' };
    const riskClass = d.risk === 'LOW' ? 'risk-low' :
                      d.risk === 'MEDIUM' ? 'risk-medium' : 'risk-high';

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
            <span class="risk-badge ${riskClass}">${c.risk}</span>
            <span class="price-tag">$${c.current_price.toFixed(1)}M</span>
            <span class="value-tag">${c.value_score.toFixed(2)}x</span>
        </div>
    </div>`;
}

// -- Lock grid for optimizer --
function renderLockGrid() {
    if (!data) return;

    const grid = document.getElementById('lockGrid');
    let html = '';

    // Drivers
    data.drivers.forEach(d => {
        const team = TEAMS[d.constructor] || { color: '#666' };
        const locked = lockedDrivers.has(d.driver_id);
        html += `
        <div class="lock-chip ${locked ? 'locked' : ''}" data-type="driver" data-id="${d.driver_id}">
            <span class="chip-dot" style="background:${team.color}"></span>
            ${d.name.split(' ').pop()}
            <span class="lock-icon">${locked ? '🔒' : ''}</span>
        </div>`;
    });

    // Constructors
    html += '<div style="width:100%;height:1px;"></div>';
    data.constructors.forEach(c => {
        const team = TEAMS[c.constructor_id] || { color: '#666' };
        const locked = lockedConstructors.has(c.constructor_id);
        html += `
        <div class="lock-chip ${locked ? 'locked' : ''}" data-type="constructor" data-id="${c.constructor_id}">
            <span class="chip-dot" style="background:${team.color}"></span>
            ${c.name}
            <span class="lock-icon">${locked ? '🔒' : ''}</span>
        </div>`;
    });

    grid.innerHTML = html;

    // Click handlers
    grid.querySelectorAll('.lock-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const type = chip.dataset.type;
            const id = chip.dataset.id;
            if (type === 'driver') {
                lockedDrivers.has(id) ? lockedDrivers.delete(id) : lockedDrivers.add(id);
            } else {
                lockedConstructors.has(id) ? lockedConstructors.delete(id) : lockedConstructors.add(id);
            }
            renderLockGrid();
        });
    });
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
        // Balanced: weighted combo
        return item.expected_points * 0.6 + item.value_score * 10 * 0.4;
    }

    const drivers = data.drivers.map(d => ({ ...d, _type: 'driver', _score: score(d) }));
    const constructors = data.constructors.map(c => ({ ...c, _type: 'constructor', _score: score(c) }));

    // Sort by score descending
    drivers.sort((a, b) => b._score - a._score);
    constructors.sort((a, b) => b._score - a._score);

    // Brute force best lineup: 5 drivers + 2 constructors
    // With 22 drivers, C(22,5) = 26,334 and C(11,2) = 55 => ~1.4M combos
    // That's manageable in JS

    let bestLineup = null;
    let bestScore = -Infinity;

    // Generate constructor pairs
    const cPairs = [];
    for (let i = 0; i < constructors.length; i++) {
        for (let j = i + 1; j < constructors.length; j++) {
            // Check locked constructors
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

    // Filter drivers with locked ones
    const lockedDriverList = drivers.filter(d => lockedDrivers.has(d.driver_id));
    const freeDrivers = drivers.filter(d => !lockedDrivers.has(d.driver_id));
    const neededDrivers = 5 - lockedDriverList.length;
    const lockedDriverCost = lockedDriverList.reduce((s, d) => s + d.current_price, 0);
    const lockedDriverScore = lockedDriverList.reduce((s, d) => s + d._score, 0);

    if (neededDrivers < 0) {
        alert('You have locked more than 5 drivers. Please unlock some.');
        return;
    }

    // For large combos, use greedy with pairs
    for (const cp of cPairs) {
        const remainBudget = budget - cp.cost - lockedDriverCost;
        if (remainBudget < 0) continue;

        // Greedy fill for drivers (good enough given sorted order)
        const picked = [];
        let cost = 0;
        for (const d of freeDrivers) {
            if (picked.length >= neededDrivers) break;
            if (cost + d.current_price <= remainBudget) {
                // Check we have enough budget for remaining picks
                picked.push(d);
                cost += d.current_price;
            }
        }

        if (picked.length === neededDrivers) {
            const totalScore = cp.score + lockedDriverScore + picked.reduce((s, d) => s + d._score, 0);
            if (totalScore > bestScore) {
                bestScore = totalScore;
                bestLineup = {
                    drivers: [...lockedDriverList, ...picked],
                    constructors: cp.items,
                    totalCost: cp.cost + lockedDriverCost + cost,
                    totalPoints: cp.items.reduce((s, c) => s + c.expected_points, 0) +
                                 lockedDriverList.reduce((s, d) => s + d.expected_points, 0) +
                                 picked.reduce((s, d) => s + d.expected_points, 0),
                };
            }
        }
    }

    // Also try non-greedy: for each constructor pair, try swapping last picked with next options
    // (Simple improvement pass)
    if (bestLineup && neededDrivers > 0) {
        for (const cp of cPairs) {
            const remainBudget = budget - cp.cost - lockedDriverCost;
            if (remainBudget < 0) continue;

            // Try all combinations of top N drivers
            const topN = freeDrivers.slice(0, Math.min(12, freeDrivers.length));
            const combos = combinations(topN, neededDrivers);

            for (const combo of combos) {
                const cost = combo.reduce((s, d) => s + d.current_price, 0);
                if (cost > remainBudget) continue;

                const totalScore = cp.score + lockedDriverScore + combo.reduce((s, d) => s + d._score, 0);
                if (totalScore > bestScore) {
                    bestScore = totalScore;
                    bestLineup = {
                        drivers: [...lockedDriverList, ...combo],
                        constructors: cp.items,
                        totalCost: cp.cost + lockedDriverCost + cost,
                        totalPoints: cp.items.reduce((s, c) => s + c.expected_points, 0) +
                                     lockedDriverList.reduce((s, d) => s + d.expected_points, 0) +
                                     combo.reduce((s, d) => s + d.expected_points, 0),
                    };
                }
            }
        }
    }

    if (!bestLineup) {
        alert('No valid lineup found within budget. Try increasing the budget.');
        return;
    }

    displayLineup(bestLineup);
}

function combinations(arr, k) {
    const result = [];
    function helper(start, combo) {
        if (combo.length === k) {
            result.push([...combo]);
            return;
        }
        for (let i = start; i < arr.length; i++) {
            combo.push(arr[i]);
            helper(i + 1, combo);
            combo.pop();
        }
    }
    helper(0, []);
    return result;
}

function displayLineup(lineup) {
    const resultEl = document.getElementById('optimizerResult');
    resultEl.classList.remove('hidden');

    // Summary
    document.getElementById('lineupSummary').innerHTML = `
        <div class="lineup-stat">
            <div class="big-num">${lineup.totalPoints.toFixed(1)}</div>
            <div class="label">Expected Points</div>
        </div>
        <div class="lineup-stat">
            <div class="big-num">$${lineup.totalCost.toFixed(1)}M</div>
            <div class="label">Total Cost</div>
        </div>
        <div class="lineup-stat">
            <div class="big-num">$${(parseFloat(document.getElementById('budget').value) - lineup.totalCost).toFixed(1)}M</div>
            <div class="label">Remaining</div>
        </div>
    `;

    // Cards
    let html = '';

    lineup.drivers.sort((a, b) => b.expected_points - a.expected_points);
    lineup.drivers.forEach((d, i) => {
        const team = TEAMS[d.constructor] || { color: '#666' };
        const locked = lockedDrivers.has(d.driver_id);
        html += `
        <div class="lineup-pick" style="--team-color:${team.color}">
            <div class="pick-type">Driver ${i + 1} ${locked ? '🔒' : ''}</div>
            <div class="pick-name">${d.name}</div>
            <div class="pick-points">${d.expected_points.toFixed(1)} pts</div>
            <div class="pick-price">$${d.current_price.toFixed(1)}M</div>
        </div>`;
    });

    lineup.constructors.forEach((c, i) => {
        const team = TEAMS[c.constructor_id] || { color: '#666' };
        const locked = lockedConstructors.has(c.constructor_id);
        html += `
        <div class="lineup-pick" style="--team-color:${team.color}">
            <div class="pick-type">Constructor ${i + 1} ${locked ? '🔒' : ''}</div>
            <div class="pick-name">${c.full_name || c.name}</div>
            <div class="pick-points">${c.expected_points.toFixed(1)} pts</div>
            <div class="pick-price">$${c.current_price.toFixed(1)}M</div>
        </div>`;
    });

    document.getElementById('lineupCards').innerHTML = html;

    // Scroll into view
    resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
function renderPostRace(data) {
    const el = document.getElementById('postRaceContent');
    if (!data) {
        el.innerHTML = '<p class="no-data">No post-race analysis for this round.</p>';
        return;
    }

    let html = `<div class="analysis-race-header">${data.race} — Round ${data.round}</div>`;

    // Race Results
    if (data.results && data.results.length > 0) {
        html += `
        <div class="analysis-block">
            <h3>Race Results</h3>
            <table class="data-table">
                <thead><tr>
                    <th>#</th><th>Driver</th><th class="num">Grid</th>
                    <th class="num">Finish</th><th class="num">+/-</th>
                    <th class="num">Pts</th><th>Status</th>
                </tr></thead>
                <tbody>${data.results.map(r => `
                    <tr>
                        <td>${r.finish_position || '-'}</td>
                        <td><strong>${r.driver_id}</strong></td>
                        <td class="num">${r.grid}</td>
                        <td class="num">${r.finish_position || 'DNF'}</td>
                        <td class="num ${r.positions_gained > 0 ? 'text-green' : r.positions_gained < 0 ? 'text-red' : ''}">${r.positions_gained > 0 ? '+' : ''}${r.positions_gained}</td>
                        <td class="num">${r.points}</td>
                        <td>${r.is_finished ? 'Finished' : r.status}</td>
                    </tr>`).join('')}
                </tbody>
            </table>
        </div>`;
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
            <tbody>${seasonSummary.rounds.map(r => `
                <tr>
                    <td>${r.round}</td>
                    <td><strong>${r.name}</strong></td>
                    <td>${r.circuit}</td>
                    <td>${r.date}</td>
                    <td>${r.has_post_race ? '<span class="status-done">Complete</span>' :
                          r.has_predictions ? '<span class="status-predicted">Predicted</span>' :
                          '<span class="status-upcoming">Upcoming</span>'}</td>
                </tr>`).join('')}
            </tbody>
        </table>`;
        calEl.innerHTML = html;
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

    // Populate post-race round selector
    const selector = document.getElementById('postRaceRound');
    if (seasonSummary && seasonSummary.rounds) {
        selector.innerHTML = '<option value="">Select a round...</option>';
        seasonSummary.rounds.filter(r => r.has_post_race).forEach(r => {
            const opt = document.createElement('option');
            opt.value = r.round;
            opt.textContent = `Round ${r.round}: ${r.name}`;
            selector.appendChild(opt);
        });
        // If no completed rounds, add any round with predictions
        if (selector.options.length === 1) {
            seasonSummary.rounds.filter(r => r.has_predictions).forEach(r => {
                const opt = document.createElement('option');
                opt.value = r.round;
                opt.textContent = `Round ${r.round}: ${r.name}`;
                selector.appendChild(opt);
            });
        }
    }
}
