/* Personal lap selections for the FP long-run comparison. */
(function (root) {
    'use strict';

    const PRIORITY = { FP2: 3, FP1: 2, FP3: 1 };
    const mean = laps => laps.length ? laps.reduce((sum, lap) => sum + lap.time, 0) / laps.length : null;
    const median = laps => {
        if (!laps.length) return null;
        const ordered = laps.map(lap => lap.time).sort((a, b) => a - b);
        const middle = Math.floor(ordered.length / 2);
        return ordered.length % 2 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2;
    };
    const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    function time(value) {
        if (value == null || !Number.isFinite(value)) return '—';
        const ms = Math.round(value * 1000);
        return `${Math.floor(ms / 60000)}:${((ms % 60000) / 1000).toFixed(3).padStart(6, '0')}`;
    }

    function createComparableModel(analysis, roster = []) {
        const source = analysis.long_run_comparisons;
        const allowed = new Set(roster);
        const overrides = new Map();
        const lapIndex = new Map();
        const groups = source.groups || [];
        const drivers = Object.entries(source.drivers || {})
            .filter(([id]) => !allowed.size || allowed.has(id))
            .map(([id, record]) => {
                const runs = (record.runs || []).map((run, runIndex) => {
                    const laps = (run.lap_sequence || []).map((lap, index) => ({
                        key: JSON.stringify([id, runIndex, index]),
                        driver: id,
                        time: Number(lap.time),
                        original: !!lap.selected,
                        ordinal: lap.lap_number ?? index + 1,
                        bucket: lap.selected ? 'kept' : 'excluded',
                    })).filter(lap => Number.isFinite(lap.time) && lap.time > 0);
                    laps.forEach(lap => lapIndex.set(lap.key, lap));
                    return {
                        session: run.session || '?', compound: run.compound || 'UNKNOWN',
                        stint: run.stint ?? runIndex + 1, quality: run.quality || 'interrupted', laps,
                    };
                });
                return { id, runs };
            });
        let session = source.default_group || groups[0]?.id || '';
        const included = lap => overrides.has(lap.key) ? overrides.get(lap.key) : lap.original;
        return {
            comparable: true,
            groups,
            get session() { return session; },
            get changes() { return overrides.size; },
            get sessions() { return groups.map(group => group.id); },
            setSession(value) { if (groups.some(group => group.id === value)) session = value; },
            toggle(key) {
                const lap = lapIndex.get(key);
                if (!lap) return false;
                const next = !included(lap);
                if (next === lap.original) overrides.delete(key);
                else overrides.set(key, next);
                return true;
            },
            reset(driver) {
                for (const key of overrides.keys()) {
                    if (!driver || lapIndex.get(key).driver === driver) overrides.delete(key);
                }
            },
            rows() {
                const rows = drivers.map(driver => {
                    const runs = driver.runs.map(run => {
                        const laps = run.laps.map(lap => ({ ...lap, included: included(lap), modified: overrides.has(lap.key) }));
                        const selected = laps.filter(lap => lap.included);
                        const comparison = run.session === session &&
                            (run.quality === 'clean' || run.quality === 'partial');
                        return { ...run, laps, count: selected.length, average: median(selected), comparison };
                    });
                    const comparisonRuns = runs.filter(run => run.comparison);
                    return {
                        id: driver.id, session, runs, comparisonRuns: comparisonRuns.length,
                        count: comparisonRuns.reduce((sum, run) => sum + run.count, 0),
                        changes: runs.flatMap(run => run.laps).filter(lap => lap.modified).length,
                    };
                });
                return rows.sort((a, b) => a.id.localeCompare(b.id));
            },
            runRows() {
                const rows = this.rows().flatMap(driver => driver.runs
                    .filter(run => run.comparison && run.average != null)
                    .map(run => ({
                        id: driver.id, compound: run.compound, stint: run.stint,
                        average: run.average, quality: run.quality, count: run.count,
                        changes: run.laps.filter(lap => lap.modified).length,
                    })));
                const fastestByTyre = new Map();
                rows.forEach(row => fastestByTyre.set(row.compound,
                    Math.min(fastestByTyre.get(row.compound) ?? Infinity, row.average)));
                rows.forEach(row => {
                    const peers = rows.filter(peer => peer.compound === row.compound);
                    row.gap = row.compound !== 'UNKNOWN' && peers.length > 1
                        ? row.average - fastestByTyre.get(row.compound) : null;
                });
                return rows;
            },
        };
    }

    function createModel(analysis, roster = []) {
        if (analysis.long_run_comparisons) return createComparableModel(analysis, roster);
        const allowed = new Set(roster);
        const overrides = new Map();
        const lapIndex = new Map();
        const drivers = Object.entries(analysis.long_run_pace || {})
            .filter(([id]) => !allowed.size || allowed.has(id))
            .map(([id, source]) => {
                const runs = (source.runs || []).map((run, index) => {
                    const laps = ['kept', 'excluded'].flatMap(bucket => (run[`${bucket}_laps`] || []).map((value, lap) => ({
                        key: JSON.stringify([id, index, bucket, lap]),
                        driver: id,
                        time: Number(value),
                        original: bucket === 'kept',
                        ordinal: lap + 1,
                        bucket,
                    }))).filter(lap => Number.isFinite(lap.time) && lap.time > 0);
                    laps.forEach(lap => lapIndex.set(lap.key, lap));
                    return { session: run.session || '?', compound: run.compound || 'UNKNOWN', stint: run.stint ?? index + 1, laps };
                });
                const sessions = [...new Set(runs.map(run => run.session))];
                const preferred = source.headline_session || sessions.sort((a, b) => (PRIORITY[b] || 0) - (PRIORITY[a] || 0))[0] || '';
                return { id, runs, preferred };
            });
        let session = 'auto';
        const included = lap => overrides.has(lap.key) ? overrides.get(lap.key) : lap.original;
        return {
            get session() { return session; },
            get changes() { return overrides.size; },
            get sessions() { return [...new Set(drivers.flatMap(d => d.runs.map(r => r.session)))].sort(); },
            setSession(value) { if (value === 'auto' || this.sessions.includes(value)) session = value; },
            toggle(key) {
                const lap = lapIndex.get(key);
                if (!lap) return false;
                const next = !included(lap);
                if (next === lap.original) overrides.delete(key);
                else overrides.set(key, next);
                return true;
            },
            reset(driver) {
                for (const key of overrides.keys()) {
                    if (!driver || lapIndex.get(key).driver === driver) overrides.delete(key);
                }
            },
            rows() {
                const rows = drivers.map(driver => {
                    const comparison = session === 'auto' ? driver.preferred : session;
                    const runs = driver.runs.map(run => {
                        const laps = run.laps.map(lap => ({ ...lap, included: included(lap), modified: overrides.has(lap.key) }));
                        const selected = laps.filter(lap => lap.included);
                        return { ...run, laps, count: selected.length, average: mean(selected), comparison: run.session === comparison };
                    });
                    const comparisonLaps = runs.filter(r => r.comparison).flatMap(r => r.laps);
                    const selected = comparisonLaps.filter(lap => lap.included);
                    return {
                        id: driver.id, session: comparison, runs,
                        average: mean(selected), originalAverage: mean(comparisonLaps.filter(lap => lap.original)),
                        count: selected.length, changes: runs.flatMap(r => r.laps).filter(lap => lap.modified).length,
                    };
                }).sort((a, b) => (a.average ?? Infinity) - (b.average ?? Infinity) || a.id.localeCompare(b.id));
                const leader = rows.find(row => row.average != null)?.average;
                rows.forEach((row, index) => {
                    row.rank = row.average == null ? null : index + 1;
                    row.gap = row.average == null ? null : row.average - leader;
                });
                return rows;
            },
        };
    }

    // Keep edits when switching tabs, but never apply old selections to a new export.
    let cachedKey, cachedModel;
    function modelFor(analysis, roster) {
        const key = JSON.stringify([analysis.season, analysis.round, analysis.long_run_comparisons || analysis.long_run_pace, roster]);
        if (key !== cachedKey) {
            cachedKey = key;
            cachedModel = createModel(analysis, roster);
        }
        return cachedModel;
    }

    function mount(host, analysis, roster = []) {
        const model = modelFor(analysis, roster);
        let sortKey = 'average', ascending = true, query = '';
        const doc = host.ownerDocument;
        const gap = row => row.gap == null ? '—' : row.gap === 0 ? `<span class="text-green">${model.comparable ? 'Fastest on tyre' : 'Leader'}</span>` : `+${row.gap.toFixed(3)}`;
        const columns = model.comparable
            ? [['id', 'Driver'], ['compound', 'Tyre'], ['stint', 'Stint'], ['average', 'Median Lap'], ['gap', 'Gap on Tyre'], ['quality', 'Evidence'], ['count', 'Laps']]
            : [['rank', '#'], ['id', 'Driver'], ['average', 'Race Pace'], ['gap', 'Gap'], ['session', 'Session'], ['count', 'Laps']];
        function filter(value) {
            query = value.toUpperCase().trim();
            host.querySelectorAll('[data-lr-driver]').forEach(el => {
                el.hidden = !el.dataset.lrDriver.toUpperCase().includes(query);
            });
        }
        function render() {
            const rows = model.rows();
            const sourceRows = model.comparable ? model.runRows() : rows;
            const sorted = [...sourceRows].sort((a, b) => {
                const av = a[sortKey], bv = b[sortKey];
                if (av == null) return bv == null ? a.id.localeCompare(b.id) : 1;
                if (bv == null) return -1;
                return (av < bv ? -1 : av > bv ? 1 : a.id.localeCompare(b.id)) * (ascending ? 1 : -1);
            });
            const tableRows = sorted;
            const groupOptions = model.comparable
                ? (model.groups.length
                    ? model.groups.map(group => `<option value="${escape(group.id)}" ${model.session === group.id ? 'selected' : ''}>${escape(group.session)} · ${group.drivers} driver${group.drivers === 1 ? '' : 's'}</option>`).join('')
                    : '<option value="">No comparable runs yet</option>')
                : `<option value="auto" ${model.session === 'auto' ? 'selected' : ''}>Preferred (FP2 → FP1 → FP3)</option>
                   ${model.sessions.map(s => `<option value="${escape(s)}" ${model.session === s ? 'selected' : ''}>${escape(s)}</option>`).join('')}`;
            host.innerHTML = `<div class="analysis-block">
                <h3>${model.comparable ? 'Practice Long Runs (Observed Runs)' : 'Long Run Pace (Predicted Race Pace)'}</h3>
                <p class="analysis-note">${model.comparable
                    ? 'Race-run evidence is identified by a sustained lap pattern on any tyre. Each valid run in the selected practice session appears separately. Median laps are observed pace; gaps compare runs on the same tyre only. Fuel loads remain unknown. Partial runs have limited evidence; interrupted push/cool patterns appear below. Click laps to try your own selection.'
                    : 'Click any lap below to include or exclude it from your comparison. Averages, gaps and pace order update immediately. These personal selections affect this long-run comparison only.'}</p>
                <div class="lr-controls">
                    <label for="lrComparisonSession">Compare session
                        <select id="lrComparisonSession" data-lr-action="session" data-lr-focus="session">
                            ${groupOptions}
                        </select>
                    </label>
                    <button type="button" class="lr-reset" data-lr-action="reset" data-lr-focus="reset" ${model.changes ? '' : 'disabled'}>Reset all laps</button>
                    <span class="lr-status" role="status" aria-live="polite">${model.changes ? `${model.changes} lap selection${model.changes === 1 ? '' : 's'} changed · personal comparison` : 'Model lap selection'}</span>
                </div>
                <div class="lr-table-wrap"><table class="data-table" id="fpLongRunTable">
                    <thead><tr>${columns.map(([key, label]) => `<th aria-sort="${sortKey === key ? (ascending ? 'ascending' : 'descending') : 'none'}"><button type="button" data-lr-sort="${key}" data-lr-focus="sort-${key}">${label}${sortKey === key ? (ascending ? ' ▲' : ' ▼') : ''}</button></th>`).join('')}</tr></thead>
                    <tbody>${tableRows.map(row => model.comparable ? `<tr data-lr-driver="${escape(row.id)}">
                        <td><strong>${escape(row.id)}</strong>${row.changes ? '<span class="lr-edited">Edited</span>' : ''}</td>
                        <td>${escape(row.compound)}</td><td class="num">${escape(row.stint)}</td><td class="num">${time(row.average)}</td>
                        <td class="num">${gap(row)}</td><td>${row.quality === 'clean' ? 'Clean' : 'Partial'}</td><td class="num">${row.count}</td>
                    </tr>` : `<tr data-lr-driver="${escape(row.id)}">
                        <td class="num">${row.rank ?? '—'}</td><td><strong>${escape(row.id)}</strong>${row.changes ? '<span class="lr-edited">Edited</span>' : ''}</td>
                        <td class="num">${time(row.average)}</td><td class="num">${gap(row)}</td><td class="num">${escape(row.session)}</td><td class="num">${row.count}</td>
                    </tr>`).join('')}</tbody>
                </table></div>${model.comparable ? `<p class="analysis-note">${tableRows.length} runs across ${new Set(tableRows.map(row => row.id)).size} drivers in ${escape(model.session)}. Other evidence is in Long Run Detail below.</p>` : ''}
            </div>
            <div class="analysis-block">
                <h3>Long Run Detail</h3>
                <p class="analysis-note">Green laps are included; crossed-out laps are excluded. Click again to undo. ${model.comparable ? 'Laps appear in their original order. Clean or partial runs on the selected session enter the table regardless of tyre.' : 'Runs marked In comparison supply the headline average. Other sessions keep their own run averages.'} Edits stay while switching tabs and reset on reload or new practice data.</p>
                <div class="lr-detail-grid">${rows.map(row => `<div class="lr-card" data-lr-driver="${escape(row.id)}">
                    <div class="lr-head"><strong>${escape(row.id)}</strong>${model.comparable ? '' : `<span class="lr-headavg">${time(row.average)}</span><span class="lr-headgap">${gap(row)}</span>`}</div>
                    <div class="lr-card-summary">${escape(row.session)} comparison · ${model.comparable ? `${row.comparisonRuns} race run${row.comparisonRuns === 1 ? '' : 's'}` : `${row.count} selected lap${row.count === 1 ? '' : 's'}${row.average == null ? ' · No comparable pace' : ''}${row.count > 0 && row.count < 4 ? ' · Small sample' : ''}`}</div>
                    ${row.changes ? `<div class="lr-edit-summary">${model.comparable ? 'Lap selection edited' : `Model average: ${time(row.originalAverage)}`} <button type="button" class="lr-reset" data-lr-action="reset" data-lr-reset-driver="${escape(row.id)}" data-lr-focus="reset-${escape(row.id)}">Reset ${escape(row.id)}</button></div>` : ''}
                    ${row.runs.map((run, index) => `<div class="lr-run ${run.comparison ? 'lr-comparison-run' : ''}" data-lr-run="${index}">
                        <div class="lr-run-heading"><span class="compound-badge ${escape(run.compound.toLowerCase())}">${escape(run.session)} ${escape(run.compound)}</span><span class="lr-ctx">Stint ${escape(run.stint)} · ${escape(run.quality || 'legacy')}${run.comparison ? ' · In comparison' : ''}</span></div>
                        <span class="lr-laps">${run.laps.map(lap => `<button type="button" class="lr-lap ${lap.included ? 'kept' : 'excl'}${lap.modified ? ' lr-modified' : ''}" data-lr-lap="${escape(lap.key)}" data-lr-focus="${escape(lap.key)}" aria-pressed="${lap.included}" aria-label="${escape(`${row.id} ${run.session} ${run.compound} stint ${run.stint}, ${lap.bucket === 'kept' ? 'model-kept' : 'model-excluded'} lap ${lap.ordinal}, ${time(lap.time)}. ${lap.included ? 'Included; click to exclude' : 'Excluded; click to include'}`)}" title="Lap ${escape(lap.ordinal)} · ${lap.included ? 'Click to exclude' : 'Click to include'} · Model ${lap.original ? 'included' : 'excluded'} this lap">${time(lap.time)}</button>`).join('')}</span>
                        <span class="lr-avg">${time(run.average)} <span class="lr-ctx">${run.count}L</span></span>
                    </div>`).join('')}
                </div>`).join('')}</div>
            </div>`;
            filter(query);
        }
        function redraw(control, anchor) {
            const focus = control.dataset.lrFocus;
            const top = anchor ? control.getBoundingClientRect().top : null;
            render();
            const next = [...host.querySelectorAll('[data-lr-focus]')].find(el => el.dataset.lrFocus === focus);
            if (next && !next.disabled) {
                next.focus({ preventScroll: true });
                if (top != null) doc.defaultView.scrollBy(0, next.getBoundingClientRect().top - top);
            }
        }
        host.onclick = event => {
            const control = event.target.closest('button');
            if (!control || !host.contains(control)) return;
            if (control.hasAttribute('data-lr-lap')) {
                model.toggle(control.dataset.lrLap);
                sortKey = 'average'; ascending = true;
                redraw(control, true);
            } else if (control.dataset.lrAction === 'reset') {
                model.reset(control.dataset.lrResetDriver);
                sortKey = 'average'; ascending = true;
                redraw(control, false);
            } else if (control.dataset.lrSort) {
                ascending = sortKey === control.dataset.lrSort ? !ascending : true;
                sortKey = control.dataset.lrSort;
                redraw(control, false);
            }
        };
        host.onchange = event => {
            if (event.target.dataset.lrAction !== 'session') return;
            model.setSession(event.target.value);
            sortKey = 'average'; ascending = true;
            redraw(event.target, false);
        };
        render();
        return { filter };
    }

    const api = { createModel, modelFor, mount };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else root.LongRunExplorer = api;
})(typeof window !== 'undefined' ? window : globalThis);
