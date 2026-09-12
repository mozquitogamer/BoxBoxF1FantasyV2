/* Personal lap selections for the FP long-run comparison. */
(function (root) {
    'use strict';

    const PRIORITY = { FP2: 3, FP1: 2, FP3: 1 };
    const mean = laps => laps.length ? laps.reduce((sum, lap) => sum + lap.time, 0) / laps.length : null;
    const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    function time(value) {
        if (value == null || !Number.isFinite(value)) return '—';
        const ms = Math.round(value * 1000);
        return `${Math.floor(ms / 60000)}:${((ms % 60000) / 1000).toFixed(3).padStart(6, '0')}`;
    }

    function createModel(analysis, roster = []) {
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
        const key = JSON.stringify([analysis.season, analysis.round, analysis.long_run_pace, roster]);
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
        const gap = row => row.gap == null ? '—' : row.gap === 0 ? '<span class="text-green">Leader</span>' : `+${row.gap.toFixed(3)}`;
        const columns = [
            ['rank', '#'], ['id', 'Driver'], ['average', 'Race Pace'], ['gap', 'Gap'], ['session', 'Session'], ['count', 'Laps'],
        ];
        function filter(value) {
            query = value.toUpperCase().trim();
            host.querySelectorAll('[data-lr-driver]').forEach(el => {
                el.hidden = !el.dataset.lrDriver.toUpperCase().includes(query);
            });
        }
        function render() {
            const rows = model.rows();
            const sorted = [...rows].sort((a, b) => {
                const av = a[sortKey], bv = b[sortKey];
                if (av == null) return bv == null ? a.id.localeCompare(b.id) : 1;
                if (bv == null) return -1;
                return (av < bv ? -1 : av > bv ? 1 : a.id.localeCompare(b.id)) * (ascending ? 1 : -1);
            });
            host.innerHTML = `<div class="analysis-block">
                <h3>Long Run Pace (Predicted Race Pace)</h3>
                <p class="analysis-note">Click any lap below to include or exclude it from your comparison. Averages, gaps and pace order update immediately. These personal selections affect this long-run comparison only.</p>
                <div class="lr-controls">
                    <label for="lrComparisonSession">Compare session
                        <select id="lrComparisonSession" data-lr-action="session" data-lr-focus="session">
                            <option value="auto" ${model.session === 'auto' ? 'selected' : ''}>Preferred (FP2 → FP1 → FP3)</option>
                            ${model.sessions.map(s => `<option value="${escape(s)}" ${model.session === s ? 'selected' : ''}>${escape(s)}</option>`).join('')}
                        </select>
                    </label>
                    <button type="button" class="lr-reset" data-lr-action="reset" data-lr-focus="reset" ${model.changes ? '' : 'disabled'}>Reset all laps</button>
                    <span class="lr-status" role="status" aria-live="polite">${model.changes ? `${model.changes} lap selection${model.changes === 1 ? '' : 's'} changed · personal comparison` : 'Model lap selection'}</span>
                </div>
                <div class="lr-table-wrap"><table class="data-table" id="fpLongRunTable">
                    <thead><tr>${columns.map(([key, label]) => `<th aria-sort="${sortKey === key ? (ascending ? 'ascending' : 'descending') : 'none'}"><button type="button" data-lr-sort="${key}" data-lr-focus="sort-${key}">${label}${sortKey === key ? (ascending ? ' ▲' : ' ▼') : ''}</button></th>`).join('')}</tr></thead>
                    <tbody>${sorted.map(row => `<tr data-lr-driver="${escape(row.id)}">
                        <td class="num">${row.rank ?? '—'}</td><td><strong>${escape(row.id)}</strong>${row.changes ? '<span class="lr-edited">Edited</span>' : ''}</td>
                        <td class="num">${time(row.average)}</td><td class="num">${gap(row)}</td><td class="num">${escape(row.session)}</td><td class="num">${row.count}</td>
                    </tr>`).join('')}</tbody>
                </table></div>
            </div>
            <div class="analysis-block">
                <h3>Long Run Detail</h3>
                <p class="analysis-note">Green laps are included; crossed-out laps are excluded. Click again to undo. Runs marked <strong>In comparison</strong> supply the headline average. Other sessions keep their own run averages. Edits stay while switching tabs and reset on reload or new practice data.</p>
                <div class="lr-detail-grid">${rows.map(row => `<div class="lr-card" data-lr-driver="${escape(row.id)}">
                    <div class="lr-head"><strong>${escape(row.id)}</strong><span class="lr-headavg">${time(row.average)}</span><span class="lr-headgap">${gap(row)}</span></div>
                    <div class="lr-card-summary">${escape(row.session)} comparison · ${row.count} selected lap${row.count === 1 ? '' : 's'}${row.average == null ? ' · No pace to rank' : ''}${row.count > 0 && row.count < 4 ? ' · Small sample' : ''}</div>
                    ${row.changes ? `<div class="lr-edit-summary">Model average: ${time(row.originalAverage)} <button type="button" class="lr-reset" data-lr-action="reset" data-lr-reset-driver="${escape(row.id)}" data-lr-focus="reset-${escape(row.id)}">Reset ${escape(row.id)}</button></div>` : ''}
                    ${row.runs.map((run, index) => `<div class="lr-run ${run.comparison ? 'lr-comparison-run' : ''}" data-lr-run="${index}">
                        <div class="lr-run-heading"><span class="compound-badge ${escape(run.compound.toLowerCase())}">${escape(run.session)} ${escape(run.compound)}</span><span class="lr-ctx">Stint ${escape(run.stint)}${run.comparison ? ' · In comparison' : ''}</span></div>
                        <span class="lr-laps">${run.laps.map(lap => `<button type="button" class="lr-lap ${lap.included ? 'kept' : 'excl'}${lap.modified ? ' lr-modified' : ''}" data-lr-lap="${escape(lap.key)}" data-lr-focus="${escape(lap.key)}" aria-pressed="${lap.included}" aria-label="${escape(`${row.id} ${run.session} ${run.compound} stint ${run.stint}, ${lap.bucket === 'kept' ? 'model-kept' : 'model-excluded'} lap ${lap.ordinal}, ${time(lap.time)}. ${lap.included ? 'Included; click to exclude' : 'Excluded; click to include'}`)}" title="${lap.included ? 'Click to exclude' : 'Click to include'} · Model ${lap.original ? 'included' : 'excluded'} this lap">${time(lap.time)}</button>`).join('')}</span>
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
