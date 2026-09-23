(function (root, factory) {
    const api = factory();
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else root.BoxBoxFinalFix = api;
}(typeof window !== 'undefined' ? window : globalThis, function () {
    'use strict';

    const QUALI_POSITION_POINTS = Object.freeze({
        1: 10, 2: 9, 3: 8, 4: 7, 5: 6,
        6: 5, 7: 4, 8: 3, 9: 2, 10: 1,
    });
    const RACE_POSITION_POINTS = Object.freeze({
        1: 25, 2: 18, 3: 15, 4: 12, 5: 10,
        6: 8, 7: 6, 8: 4, 9: 2, 10: 1,
    });

    function qualifyingPoints(position) {
        return QUALI_POSITION_POINTS[Number(position)] || 0;
    }

    function racePoints({
        gridPosition,
        finishPosition,
        overtakes = 0,
        fastestLap = false,
        dotd = false,
        isDnf = false,
    }) {
        const safeOvertakes = Math.max(0, Math.min(30, Math.round(Number(overtakes) || 0)));
        if (isDnf) {
            return {
                finishPoints: 0,
                positionsGainedLost: 0,
                overtakes: safeOvertakes,
                fastestLapPoints: 0,
                dotdPoints: 0,
                dnfPoints: -20,
                total: -20 + safeOvertakes,
            };
        }

        const grid = Math.max(1, Math.min(22, Number(gridPosition) || 22));
        const finish = Math.max(1, Math.min(22, Number(finishPosition) || 22));
        const finishPoints = RACE_POSITION_POINTS[finish] || 0;
        const positionsGainedLost = grid - finish;
        const fastestLapPoints = fastestLap ? 10 : 0;
        const dotdPoints = dotd ? 10 : 0;
        return {
            finishPoints,
            positionsGainedLost,
            overtakes: safeOvertakes,
            fastestLapPoints,
            dotdPoints,
            dnfPoints: 0,
            total: finishPoints + positionsGainedLost + safeOvertakes + fastestLapPoints + dotdPoints,
        };
    }

    function projectedRacePoints(driver) {
        const explicitRace = Number(driver?.projected_points_race);
        if (Number.isFinite(explicitRace)) return explicitRace;

        // Older payloads briefly lacked the race field. Use the deterministic
        // total only; risk-adjusted expected points are not a Final Fix input.
        const projectedTotal = Number(driver?.projected_points);
        if (!Number.isFinite(projectedTotal)) return 0;
        const projectedQuali = Number.isFinite(Number(driver?.projected_points_quali))
            ? Number(driver.projected_points_quali)
            : qualifyingPoints(driver?.predicted_quali);
        const projectedSprintRace = Number(driver?.projected_points_sprint_race) || 0;
        return projectedTotal - projectedQuali - projectedSprintRace;
    }

    function compare({ outDriver, inDriver, bank, boosted, outgoingPoints, incomingPoints }) {
        const available = Number(outDriver.current_price || 0) + Math.max(0, Number(bank) || 0);
        const incomingPrice = Number(inDriver.current_price || 0);
        const affordable = incomingPrice <= available + 1e-9;
        const shortfall = Math.max(0, incomingPrice - available);
        const multiplier = boosted ? 2 : 1;

        const bankedQuali = qualifyingPoints(outDriver.predicted_quali);
        const holdTotal = bankedQuali + outgoingPoints.total * multiplier;
        const switchTotal = bankedQuali + incomingPoints.total * multiplier;
        const scenarioDelta = switchTotal - holdTotal;

        const modelOutRace = projectedRacePoints(outDriver);
        const modelInRace = projectedRacePoints(inDriver);
        const modelDelta = (modelInRace - modelOutRace) * multiplier;
        const modelHold = bankedQuali + modelOutRace * multiplier;
        const modelSwitch = bankedQuali + modelInRace * multiplier;

        return {
            affordable, shortfall, multiplier, bankedQuali,
            holdTotal, switchTotal, scenarioDelta,
            modelDelta, modelHold, modelSwitch,
        };
    }

    function mount({ document: doc, getData, gridPenaltyText }) {
        function ffDriverById(driverId) {
            return getData()?.drivers?.find(d => d.driver_id === driverId) || null;
        }

        function ffSelectedAward(name) {
            return doc.querySelector(`input[name="${name}"]:checked`)?.value || 'none';
        }

        function ffSigned(value, digits = 0) {
            const n = Number(value) || 0;
            return `${n > 0 ? '+' : ''}${n.toFixed(digits)}`;
        }

        function ffFinishOptions() {
            return [
                ...Array.from({ length: 22 }, (_, i) => `<option value="${i + 1}">P${i + 1}</option>`),
                '<option value="dnf">DNF / DSQ</option>',
            ].join('');
        }

        function ffSetScenarioDriver(side, resetInputs = true) {
            const prefix = side === 'out' ? 'ffOut' : 'ffIn';
            const driver = ffDriverById(doc.getElementById(`${prefix}Driver`)?.value);
            if (!driver) return;

            const isOutgoing = side === 'out';
            const quali = Number(driver.predicted_quali);
            const grid = Number(driver.predicted_grid ?? quali);
            const gridPenalty = gridPenaltyText(driver);
            const qPoints = qualifyingPoints(quali);
            const projectedRace = projectedRacePoints(driver);

            doc.getElementById(`${prefix}Name`).textContent = driver.name;
            doc.getElementById(`${prefix}Price`).textContent = `$${Number(driver.current_price || 0).toFixed(1)}M`;
            const qLabel = isOutgoing ? `${qPoints} pts banked` : 'not counted after switch';
            const gridText = gridPenalty
                ? `P${grid} · ${gridPenalty}`
                : `P${grid}`;
            doc.getElementById(`${prefix}Facts`).innerHTML = `
        <div><span>Qualifying</span><strong>P${quali} · ${qLabel}</strong></div>
        <div><span>Race start</span><strong>${gridText}</strong></div>
        <div><span>Model finish</span><strong>P${driver.predicted_finish}</strong></div>
        <div><span>Projected race points</span><strong>${projectedRace.toFixed(1)}</strong></div>
    `;

            if (resetInputs) {
                doc.getElementById(`${prefix}Finish`).value = String(driver.predicted_finish);
                doc.getElementById(`${prefix}Overtakes`).value = String(
                    Math.max(0, Math.round(Number(driver.mc_overtakes_mean ?? driver.expected_overtakes ?? 0)))
                );
            }
        }

        function ffSyncOvertakesToFinish(side) {
            const prefix = side === 'out' ? 'ffOut' : 'ffIn';
            const driver = ffDriverById(doc.getElementById(`${prefix}Driver`)?.value);
            const finishValue = doc.getElementById(`${prefix}Finish`)?.value;
            if (!driver || !finishValue || finishValue === 'dnf') return;
            const grid = Number(driver.predicted_grid ?? driver.predicted_quali);
            const finish = Number(finishValue);
            // Editable starting assumption: one pass for each net place gained.
            // Users can lower it for positions inherited through pit cycles/DNFs.
            doc.getElementById(`${prefix}Overtakes`).value = String(Math.max(0, grid - finish));
        }

        function ffScenarioFor(side, fastestLapWinner, dotdWinner) {
            const prefix = side === 'out' ? 'ffOut' : 'ffIn';
            const driver = ffDriverById(doc.getElementById(`${prefix}Driver`)?.value);
            const finishValue = doc.getElementById(`${prefix}Finish`)?.value;
            const isDnf = finishValue === 'dnf';
            const finishPosition = isDnf ? 22 : Number(finishValue);
            return {
                driver,
                finishLabel: isDnf ? 'DNF' : `P${finishPosition}`,
                points: racePoints({
                    gridPosition: driver?.predicted_grid ?? driver?.predicted_quali,
                    finishPosition,
                    overtakes: doc.getElementById(`${prefix}Overtakes`)?.value,
                    fastestLap: fastestLapWinner === side,
                    dotd: dotdWinner === side,
                    isDnf,
                }),
            };
        }

        function ffBreakdownRow(label, scenario, multiplier) {
            const p = scenario.points;
            const bonus = p.fastestLapPoints + p.dotdPoints;
            return `<tr>
        <th>${label}<span>${scenario.driver.name}</span></th>
        <td>P${scenario.driver.predicted_grid}</td>
        <td>${scenario.finishLabel}</td>
        <td>${ffSigned(p.finishPoints)}</td>
        <td>${ffSigned(p.positionsGainedLost)}</td>
        <td>${ffSigned(p.overtakes)}</td>
        <td>${ffSigned(bonus)}</td>
        <td><strong>${ffSigned(p.total * multiplier)}</strong></td>
    </tr>`;
        }

        function calculateFinalFixComparison() {
            const resultEl = doc.getElementById('finalFixResult');
            if (!resultEl || !getData()) return;

            const outDriver = ffDriverById(doc.getElementById('ffOutDriver')?.value);
            const inDriver = ffDriverById(doc.getElementById('ffInDriver')?.value);
            if (!outDriver || !inDriver) return;
            resultEl.classList.remove('hidden');

            if (outDriver.driver_id === inDriver.driver_id) {
                resultEl.innerHTML = '<div class="optimizer-warning">Choose two different drivers.</div>';
                return;
            }

            const fastestLapWinner = ffSelectedAward('ffFastestLap');
            const dotdWinner = ffSelectedAward('ffDotd');
            const outgoing = ffScenarioFor('out', fastestLapWinner, dotdWinner);
            const incoming = ffScenarioFor('in', fastestLapWinner, dotdWinner);
            const {
                affordable, shortfall, multiplier, bankedQuali,
                holdTotal, switchTotal, scenarioDelta,
                modelDelta, modelHold, modelSwitch,
            } = compare({
                outDriver,
                inDriver,
                bank: doc.getElementById('ffBank')?.value,
                boosted: doc.getElementById('ffBoosted')?.checked,
                outgoingPoints: outgoing.points,
                incomingPoints: incoming.points,
            });

            const verdictClass = !affordable ? 'unavailable' : scenarioDelta > 0 ? 'positive' : scenarioDelta < 0 ? 'negative' : 'neutral';
            const verdict = !affordable
                ? `Need $${shortfall.toFixed(1)}M more`
                : scenarioDelta > 0
                    ? `Final Fix gains ${ffSigned(scenarioDelta, 1)} pts`
                    : scenarioDelta < 0
                        ? `Hold gains ${ffSigned(Math.abs(scenarioDelta), 1)} pts`
                        : 'Scenario is break-even';
            const boostNote = multiplier === 2
                ? 'The 2x Boost transfers and doubles Grand Prix points only.'
                : 'No Boost transfer applied.';

            resultEl.innerHTML = `
        <div class="ff-verdict ${verdictClass}">
            <span>Your scenario</span>
            <strong>${verdict}</strong>
            <p>Hold ${outDriver.name.split(' ').pop()}: ${holdTotal.toFixed(1)} · Final Fix to ${inDriver.name.split(' ').pop()}: ${switchTotal.toFixed(1)}</p>
        </div>
        <div class="ff-model-result">
            <div>
                <span>Projected points basis</span>
                <strong>${modelDelta >= 0 ? 'Switch' : 'Hold'} by ${Math.abs(modelDelta).toFixed(1)} pts</strong>
            </div>
            <p>Hold ${modelHold.toFixed(1)} · Switch ${modelSwitch.toFixed(1)} · deterministic race projections, not Balanced or Risk-adjusted</p>
        </div>
        <div class="ff-locked-note">
            <strong>${bankedQuali} Qualifying points stay banked from ${outDriver.name}.</strong>
            Grid penalties affect the race start and positions gained/lost, not these points. ${boostNote}
        </div>
        <div class="ff-table-wrap">
            <table class="ff-breakdown-table">
                <thead><tr>
                    <th>Choice</th><th>Start</th><th>Finish</th><th>Finish pts</th>
                    <th>Gained/lost</th><th>Overtakes</th><th>FL + DOTD</th><th>Race total${multiplier === 2 ? ' (2x)' : ''}</th>
                </tr></thead>
                <tbody>
                    ${ffBreakdownRow('Hold', outgoing, multiplier)}
                    ${ffBreakdownRow('Switch', incoming, multiplier)}
                </tbody>
            </table>
        </div>
    `;
        }

        function setupFinalFixTool() {
            const outSelect = doc.getElementById('ffOutDriver');
            const inSelect = doc.getElementById('ffInDriver');
            if (!outSelect || !inSelect || !getData()?.drivers?.length) return;

            const drivers = [...getData().drivers].sort((a, b) =>
                Number(a.predicted_grid ?? 99) - Number(b.predicted_grid ?? 99)
            );
            const options = drivers.map(d =>
                `<option value="${d.driver_id}">${d.name} · $${Number(d.current_price || 0).toFixed(1)}M</option>`
            ).join('');
            outSelect.innerHTML = options;
            inSelect.innerHTML = options;
            doc.getElementById('ffOutFinish').innerHTML = ffFinishOptions();
            doc.getElementById('ffInFinish').innerHTML = ffFinishOptions();

            outSelect.value = drivers.some(d => d.driver_id === 'ANT') ? 'ANT' : drivers[0].driver_id;
            inSelect.value = drivers.some(d => d.driver_id === 'NOR')
                ? 'NOR'
                : drivers.find(d => d.driver_id !== outSelect.value)?.driver_id;

            const locked = Boolean(getData().final_fix?.qualifying_locked);
            const statusEl = doc.getElementById('finalFixStatus');
            statusEl.className = `ff-status ${locked ? 'ready' : 'waiting'}`;
            statusEl.innerHTML = locked
                ? '<strong>Post-qualifying projections ready.</strong> Actual Qualifying and the confirmed starting grid are locked. Comparisons use Projected points.'
                : '<strong>Awaiting post-qualifying projections.</strong> Manual scenarios work, but model numbers still reflect the pre-Qualifying forecast.';

            ffSetScenarioDriver('out');
            ffSetScenarioDriver('in');

            outSelect.addEventListener('change', () => {
                ffSetScenarioDriver('out');
                calculateFinalFixComparison();
            });
            inSelect.addEventListener('change', () => {
                ffSetScenarioDriver('in');
                calculateFinalFixComparison();
            });
            doc.getElementById('ffOutFinish').addEventListener('change', () => {
                ffSyncOvertakesToFinish('out');
                calculateFinalFixComparison();
            });
            doc.getElementById('ffInFinish').addEventListener('change', () => {
                ffSyncOvertakesToFinish('in');
                calculateFinalFixComparison();
            });
            ['ffOutOvertakes', 'ffInOvertakes', 'ffBank', 'ffBoosted'].forEach(id =>
                doc.getElementById(id)?.addEventListener('input', calculateFinalFixComparison)
            );
            doc.querySelectorAll('input[name="ffFastestLap"], input[name="ffDotd"]').forEach(input =>
                input.addEventListener('change', calculateFinalFixComparison)
            );
            doc.getElementById('runFinalFixCompare')?.addEventListener('click', calculateFinalFixComparison);
            calculateFinalFixComparison();
        }

        setupFinalFixTool();
    }

    return Object.freeze({ qualifyingPoints, racePoints, projectedRacePoints, compare, mount });
}));
