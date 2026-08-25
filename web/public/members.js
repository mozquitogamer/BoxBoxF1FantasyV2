(function () {
    'use strict';

    let dashboard = null;
    let panel = null;
    let autosaveTimer = null;
    let autosaveQueue = Promise.resolve();
    let lastSavedFingerprint = '';
    let teamStore = null;

    function getTeamStore() {
        if (!teamStore && typeof window !== 'undefined' && window.BoxBoxTeamState?.createStore) {
            teamStore = typeof window.BoxBoxTeamState.getStore === 'function'
                ? window.BoxBoxTeamState.getStore()
                : window.BoxBoxTeamState.createStore();
        }
        return teamStore;
    }

    function storeTeam(slot = null) {
        const store = getTeamStore();
        return store ? store.getTeam(slot || store.getState().selectedSlot) : dashboard?.team;
    }

    function teamLabel(team) {
        return escapeHtml(team?.name || `Team ${team?.slot || team?.team_slot || 1}`);
    }

    function chipLabel(key) {
        return String(key || '').replace(/_/g, ' ').replace(/\b\w/g, character => character.toUpperCase());
    }

    function announceAuthChange() {
        window.dispatchEvent(new CustomEvent('boxbox:member-auth-changed', { detail: { source: 'member-panel' } }));
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    async function request(path, options = {}) {
        const response = await fetch(path, {
            method: options.method || 'GET',
            headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
            body: options.body ? JSON.stringify(options.body) : undefined,
            credentials: 'same-origin',
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.message || 'That request did not complete.');
        return data;
    }

    function friendlyDate(value) {
        if (value === null || value === undefined || String(value).trim() === '') return '';
        const date = new Date(value);
        if (!Number.isFinite(date.getTime())) return '';
        return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
    }

    function status(message, kind = '') {
        const node = panel?.querySelector('#pitWallStatus');
        if (!node) return;
        node.textContent = message;
        node.className = `pit-wall-status${kind ? ` ${kind}` : ''}`;
    }

    function canonicalTeamSnapshot(team) {
        if (!team || !Array.isArray(team.assets)) return null;
        const optionalNumber = value => value === null || value === undefined || value === '' ? null : (Number.isFinite(Number(value)) ? Number(value) : null);
        const assets = team.assets.map(asset => ({
            asset_type: asset.asset_type === 'constructor' ? 'constructor' : 'driver',
            asset_id: String(asset.asset_id || ''),
            slot: Number(asset.slot),
            is_boosted: asset.is_boosted === true,
        })).sort((left, right) => left.asset_type.localeCompare(right.asset_type) || left.slot - right.slot);
        return {
            budget_millions: optionalNumber(team.budget_millions),
            spending_power_millions: optionalNumber(team.spending_power_millions),
            squad_value_millions: optionalNumber(team.squad_value_millions),
            bank_millions: optionalNumber(team.bank_millions),
            free_transfers: optionalNumber(team.free_transfers),
            assets,
        };
    }

    function snapshotFingerprint(team) {
        const snapshot = canonicalTeamSnapshot(team);
        return snapshot ? JSON.stringify(snapshot) : '';
    }

    function hasCompleteTeam(team) {
        const assets = canonicalTeamSnapshot(team)?.assets || [];
        return assets.filter(asset => asset.asset_type === 'driver' && asset.asset_id).length === 5
            && assets.filter(asset => asset.asset_type === 'constructor' && asset.asset_id).length === 2;
    }

    function preferredMemberTeam(memberDashboard) {
        if (hasCompleteTeam(memberDashboard?.team)) return { source: 'saved', team: memberDashboard.team };
        if (hasCompleteTeam(memberDashboard?.f1_snapshot)) return { source: 'official', team: memberDashboard.f1_snapshot };
        return null;
    }

    function applySyncedOfficialSnapshot(snapshot, memory = (typeof window !== 'undefined' ? window.BoxBoxTeamMemory : null)) {
        if (!snapshot || !memory?.applyOfficial?.(snapshot)) {
            throw new Error('Your official lineup was refreshed, but one or more picks could not be matched to the current race roster. Your saved team was not changed.');
        }
        return memory.getSnapshot();
    }

    function updateSavedSummary(snapshot) {
        if (!dashboard) return;
        dashboard.team = {
            ...(dashboard.team || {}),
            ...canonicalTeamSnapshot(snapshot),
            updated_at: new Date().toISOString(),
        };
        const summary = panel?.querySelector('.pit-wall-saved');
        if (summary) summary.textContent = 'Saved just now · 7/7 picks remembered';
    }

    async function persistWorkingTeam(snapshot, successMessage = 'Your Transfer Advisor team is saved.') {
        if (!hasCompleteTeam(snapshot)) throw new Error('Complete all five drivers and both constructors before saving.');
        const fingerprint = snapshotFingerprint(snapshot);
        if (fingerprint && fingerprint === lastSavedFingerprint) {
            status('All Transfer Advisor changes are saved.', 'success');
            return { ok: true, unchanged: true };
        }
        const result = await request('/api/members/team/', { method: 'POST', body: snapshot });
        lastSavedFingerprint = fingerprint;
        updateSavedSummary(snapshot);
        status(successMessage || result.message, 'success');
        return result;
    }

    function scheduleWorkingTeamAutosave() {
        if (!dashboard?.authenticated || dashboard.entitlement?.active !== true) return;
        const store = getTeamStore();
        if (store) {
            const slot = store.getState().selectedSlot;
            if (!store.pullFromMemory(slot)) {
                status('Your lineup is incomplete, so there is nothing to autosave yet.');
                return;
            }
            store.scheduleAutosave(slot);
            return;
        }
        clearTimeout(autosaveTimer);
        status('Saving Transfer Advisor changes…');
        autosaveTimer = window.setTimeout(() => {
            let snapshot;
            try {
                snapshot = window.BoxBoxTeamMemory?.getSnapshot();
            } catch (error) {
                status('Complete all five drivers and both constructors to save this change.');
                return;
            }
            if (!snapshot) return;
            autosaveQueue = autosaveQueue
                .catch(() => null)
                .then(() => persistWorkingTeam(snapshot, 'Transfer Advisor changes saved automatically.'))
                .catch(error => status(error.message, 'error'));
        }, 800);
    }

    function flushWorkingTeamOnExit() {
        if (!dashboard?.authenticated || dashboard.entitlement?.active !== true) return;
        const store = getTeamStore();
        if (store) {
            const slot = store.getState().selectedSlot;
            store.pullFromMemory(slot);
            store.save(slot, { force: true }).catch(() => null);
            return;
        }
        let snapshot;
        try {
            snapshot = window.BoxBoxTeamMemory?.getSnapshot();
        } catch (_) {
            return;
        }
        if (!snapshot || snapshotFingerprint(snapshot) === lastSavedFingerprint) return;
        fetch('/api/members/team/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(snapshot),
            credentials: 'same-origin',
            keepalive: true,
        }).catch(() => null);
    }

    function renderLoggedOut(message = '') {
        clearTimeout(autosaveTimer);
        dashboard = null;
        lastSavedFingerprint = '';
        panel.innerHTML = `<div class="pit-wall-heading">
            <div><span>Optional Pit Wall convenience · $5/month</span><h4>Connect your real team to this advisor</h4></div>
            <span class="pit-wall-badge">Members only</span>
        </div>
        <p>The Transfer Advisor itself is free. Pit Wall members can sign in here to remember and sync their official lineup, then receive advice personalized to it.</p>
        <form class="pit-wall-signin" id="pitWallSignInForm">
            <div class="pit-wall-fields"><label for="pitWallEmail">Ko-fi membership email</label><input id="pitWallEmail" name="email" type="email" autocomplete="email" placeholder="you@example.com" required><label for="pitWallPassword">Password</label><input id="pitWallPassword" name="password" type="password" autocomplete="current-password" minlength="8" maxlength="128" required><button type="submit">Sign in</button></div>
        </form>
        <div class="pit-wall-links"><button type="button" class="pit-wall-text-button" id="pitWallResetPassword">Create or reset password</button><a href="https://ko-fi.com/boxboxf1fantasy/tiers" target="_blank" rel="noopener">See Pit Wall benefits on Ko-fi</a><a href="/#beatbot">Beat V13 entry is free</a></div>
        <p class="pit-wall-status${message ? ' success' : ''}" id="pitWallStatus" role="status" aria-live="polite">${escapeHtml(message)}</p>`;

        panel.querySelector('#pitWallSignInForm')?.addEventListener('submit', async event => {
            event.preventDefault();
            const form = event.currentTarget;
            const button = form.querySelector('button');
            const email = form.elements.email.value.trim();
            button.disabled = true;
            status('Signing in…');
            try {
                const result = await request('/api/members/sign-in/', { method: 'POST', body: { email, password: form.elements.password.value } });
                status(result.message, 'success');
                await loadSession();
                announceAuthChange();
                window.BoxBoxOpenPitWall?.();
            } catch (error) {
                status(error.message, 'error');
            } finally {
                button.disabled = false;
            }
        });
        panel.querySelector('#pitWallResetPassword')?.addEventListener('click', async event => {
            const email = panel.querySelector('#pitWallEmail')?.value.trim();
            if (!email) { status('Enter your Ko-fi membership email first.', 'error'); return; }
            event.currentTarget.disabled = true;
            status('Preparing password setup…');
            try {
                const result = await request('/api/members/password/', { method: 'POST', body: { action: 'reset', email } });
                status(result.message, 'success');
            } catch (error) { status(error.message, 'error'); }
            finally { event.currentTarget.disabled = false; }
        });
    }

    function renderPasswordSetup() {
        panel.innerHTML = `<div class="pit-wall-heading"><div><span>Pit Wall account</span><h4>Create your password</h4></div><span class="pit-wall-badge active">Secure setup</span></div><p>Choose a password for future Pit Wall sign-ins. Use at least 10 characters; a password manager is recommended.</p><form class="pit-wall-signin" id="pitWallPasswordForm"><div class="pit-wall-fields"><label for="pitWallNewPassword">New password</label><input id="pitWallNewPassword" name="password" type="password" autocomplete="new-password" minlength="10" maxlength="128" required><label for="pitWallConfirmPassword">Confirm password</label><input id="pitWallConfirmPassword" name="confirmation" type="password" autocomplete="new-password" minlength="10" maxlength="128" required><button type="submit">Save password</button></div></form><p class="pit-wall-status" id="pitWallStatus" role="status" aria-live="polite"></p>`;
        panel.querySelector('#pitWallPasswordForm')?.addEventListener('submit', async event => {
            event.preventDefault();
            const form = event.currentTarget;
            if (form.elements.password.value !== form.elements.confirmation.value) { status('The passwords do not match.', 'error'); return; }
            const button = form.querySelector('button');
            button.disabled = true;
            try {
                const result = await request('/api/members/password/', { method: 'POST', body: { action: 'update', password: form.elements.password.value } });
                history.replaceState(null, '', '/#optimizer');
                await loadSession();
                status(result.message, 'success');
            } catch (error) { status(error.message, 'error'); }
            finally { button.disabled = false; }
        });
    }

    function renderSignedIn() {
        const active = dashboard.entitlement?.active === true;
        const ending = friendlyDate(dashboard.entitlement?.current_period_end);
        const store = getTeamStore();
        const teams = store?.getTeams() || [dashboard.team].filter(Boolean);
        const selectedSlot = store?.getState().selectedSlot || 1;
        const latest = dashboard.recommendation?.recommendation;
        const cardHtml = teams.map(team => {
            const complete = store?.hasCompleteTeam ? store.hasCompleteTeam(team) : hasCompleteTeam(team);
            const selected = team.slot === selectedSlot;
            const chipKeys = store?.chipKeys || Object.keys(team.chips || {});
            const chips = chipKeys.filter(key => store?.chipRemaining(team, key) === true).slice(0, 3);
            const f1 = team.f1_link;
            const officialReady = store?.hasCompleteTeam?.(team.f1_snapshot);
            return `<article class="pit-wall-team-card${selected ? ' selected' : ''}${complete ? ' complete' : ''}" data-team-slot="${team.slot}">
                <div class="pit-wall-team-card-head"><div><span class="pit-wall-team-kicker">Team ${team.slot}${team.is_primary ? ' · Primary' : ''}</span><h5>${teamLabel(team)}</h5></div><span class="pit-wall-team-state">${complete ? '7/7 saved' : 'Set up'}</span></div>
                <p class="pit-wall-team-meta">${team.squad_value_millions != null ? `Squad $${Number(team.squad_value_millions).toFixed(1)}m` : 'Squad value not set'}${team.bank_millions != null ? ` · Bank $${Number(team.bank_millions).toFixed(1)}m` : ''}${team.free_transfers != null ? ` · ${Number(team.free_transfers)} FT` : ''}</p>
                <p class="pit-wall-team-chips">${chips.length ? `Chips left: ${chips.map(escapeHtml).join(', ')}` : 'Chip status not confirmed'}</p>
                <details class="pit-wall-team-chips-editor"><summary>Update chip status</summary><div>${chipKeys.map(key => { const remaining = store?.chipRemaining(team, key); return `<label><input type="checkbox" data-team-chip="${team.slot}:${escapeHtml(key)}"${remaining === true ? ' checked' : ''}${active ? '' : ' disabled'}> ${escapeHtml(chipLabel(key))}</label>`; }).join('')}</div></details>
                <div class="pit-wall-team-card-actions"><button type="button" class="pit-wall-secondary" data-team-select="${team.slot}">${selected ? 'Working here' : 'Work on this team'}</button>${team.is_primary ? '' : `<button type="button" class="pit-wall-text-button" data-team-primary="${team.slot}"${active ? '' : ' disabled'}>Make primary</button>`}</div>
                <div class="pit-wall-team-tools"><input type="text" maxlength="60" value="${escapeHtml(team.name)}" aria-label="Team ${team.slot} name" data-team-name="${team.slot}"${active ? '' : ' disabled'}><button type="button" class="pit-wall-text-button" data-team-rename="${team.slot}"${active ? '' : ' disabled'}>Rename</button>${f1 ? `<span class="pit-wall-team-link">F1 linked · T${escapeHtml(f1.team_slot || team.slot)}</span>${officialReady ? `<button type="button" class="pit-wall-text-button" data-team-reset="${team.slot}"${active ? '' : ' disabled'}>Apply official</button>` : ''}` : '<span class="pit-wall-team-link">Manual team</span>'}</div>
            </article>`;
        }).join('');
        const selected = storeTeam(selectedSlot);
        const selectedOfficial = selected?.f1_link;
        const officialHtml = `<div class="pit-wall-official ${selectedOfficial ? 'linked' : ''}"><div><span>Official F1 team · ${teamLabel(selected)}</span><strong>${selectedOfficial ? `Connected · ${escapeHtml(selectedOfficial.official_team_name || selectedOfficial.name || 'T' + selectedSlot)}` : 'Not connected yet'}</strong><small>${selectedOfficial?.last_synced_at ? `League feed refreshed ${friendlyDate(selectedOfficial.last_synced_at)}` : 'Search the Box Box league to connect this slot.'}</small></div>${selectedOfficial ? `<div class="pit-wall-actions"><button type="button" class="pit-wall-secondary" data-team-sync="${selectedSlot}"${active ? '' : ' disabled'}>Refresh official team</button><button type="button" class="pit-wall-link-danger" data-team-unlink="${selectedSlot}"${active ? '' : ' disabled'}>Disconnect</button></div>` : ''}</div>`;
        panel.innerHTML = `<div class="pit-wall-signed-in"><strong>✓ Signed in to Pit Wall</strong><span>Choose a team below. Saves and official syncs stay isolated to that slot.</span></div>
        <div class="pit-wall-heading"><div><span>Pit Wall account</span><h4 aria-label="Email address hidden for privacy"><span class="pit-wall-account-email" aria-hidden="true">••••••••••••••••</span></h4></div><span class="pit-wall-badge ${active ? 'active' : 'inactive'}">${active ? `Active${ending ? ` to ${ending}` : ''}` : 'Membership inactive'}</span></div>
        ${active ? `<p>Save up to three lineups, keep each team's real budget and chips, and switch the working team whenever strategy changes.</p><div class="pit-wall-team-grid">${cardHtml}</div><div class="pit-wall-actions"><button type="button" class="pit-wall-save" id="pitWallSaveTeam">Save Team ${selectedSlot}</button><button type="button" class="pit-wall-secondary" id="pitWallEditSelectedTeam">Edit selected team in Transfer Advisor</button><button type="button" class="pit-wall-secondary" id="pitWallCompareTeams">Compare teams</button><button type="button" class="pit-wall-secondary" id="pitWallSignOut">Sign out</button></div><label class="pit-wall-pref"><input type="checkbox" id="pitWallSimEmails" ${dashboard.profile?.email_simulation_updates !== false ? 'checked' : ''}> Email me personalized simulation updates</label>${officialHtml}<div class="pit-wall-official"><span>Connect an official team to ${teamLabel(selected)}</span><p>Join the Box Box league first, then search the exact F1 Fantasy team name. The official T1/T2/T3 slot determines which saved Team slot receives the connection.</p><form id="pitWallF1Search"><div class="pit-wall-f1-fields"><label><small>Exact F1 Fantasy team name</small><input name="team_name" type="search" placeholder="e.g. Boxed In" minlength="2" maxlength="100" required></label><button type="submit">Find my team</button></div></form><div class="pit-wall-search-results" id="pitWallF1Results"></div></div>` : `<p>Your Ko-fi entitlement is no longer active. Your saved data is retained and returns when you renew.</p><div class="pit-wall-team-grid">${cardHtml}</div><div class="pit-wall-actions"><a class="pit-wall-save" href="https://ko-fi.com/boxboxf1fantasy/tiers" target="_blank" rel="noopener">Renew on Ko-fi</a><button type="button" class="pit-wall-secondary" id="pitWallSignOut">Sign out</button></div>`}
        ${latest?.headline ? `<div class="pit-wall-latest"><span>Latest personal check</span><strong>${escapeHtml(latest.headline)}</strong></div>` : ''}<p class="pit-wall-status" id="pitWallStatus" role="status" aria-live="polite"></p>`;

        panel.querySelectorAll('[data-team-select]').forEach(button => button.addEventListener('click', () => {
            const slot = Number(button.dataset.teamSelect);
            store?.select(slot);
            status(`Working with Team ${slot}.`, 'success');
            renderSignedIn();
        }));
        panel.querySelectorAll('[data-team-primary]').forEach(button => button.addEventListener('click', async () => {
            try { await store?.setPrimary(Number(button.dataset.teamPrimary)); status('Primary team updated.', 'success'); renderSignedIn(); }
            catch (error) { status(error.message, 'error'); }
        }));
        panel.querySelectorAll('[data-team-chip]').forEach(input => input.addEventListener('change', async () => {
            const [slotText, key] = String(input.dataset.teamChip || '').split(':');
            const slot = Number(slotText); input.disabled = true;
            try { store?.setChip(slot, key, input.checked); await store?.save(slot, { force: true }); status(`Chip status saved for Team ${slot}.`, 'success'); }
            catch (error) { input.checked = !input.checked; status(error.message, 'error'); } finally { input.disabled = false; }
        }));
        panel.querySelectorAll('[data-team-rename]').forEach(button => button.addEventListener('click', async () => {
            const slot = Number(button.dataset.teamRename);
            try { await store?.rename(slot, String(panel.querySelector(`[data-team-name="${slot}"]`)?.value || '').slice(0, 60)); status(`Team ${slot} renamed and saved.`, 'success'); renderSignedIn(); }
            catch (error) { status(error.message, 'error'); }
        }));
        panel.querySelectorAll('[data-team-reset]').forEach(button => button.addEventListener('click', async () => {
            const slot = Number(button.dataset.teamReset);
            if (!window.confirm(`Apply the latest official lineup to Team ${slot}? This replaces its editable picks and finances.`)) return;
            button.disabled = true;
            try { if (!store?.applyOfficialToMemory(slot)) throw new Error('The official lineup could not be matched to the current race roster.'); await store.save(slot, { force: true }); status(`Official lineup applied to Team ${slot}.`, 'success'); renderSignedIn(); }
            catch (error) { status(error.message, 'error'); } finally { button.disabled = false; }
        }));
        panel.querySelector('#pitWallSaveTeam')?.addEventListener('click', async event => {
            const button = event.currentTarget; button.disabled = true;
            try { if (!store?.pullFromMemory(selectedSlot)) throw new Error('Complete all five drivers and both constructors before saving.'); await store?.save(selectedSlot, { force: true }); status(`Team ${selectedSlot} saved.`, 'success'); renderSignedIn(); }
            catch (error) { status(error.message, 'error'); } finally { button.disabled = false; }
        });
        panel.querySelector('#pitWallEditSelectedTeam')?.addEventListener('click', () => window.BoxBoxOpenPitWallTransferAdvisor?.());
        panel.querySelector('#pitWallCompareTeams')?.addEventListener('click', () => window.BoxBoxTeamCompare?.open?.({ source: 'pit-wall' }));
        panel.querySelector('#pitWallSimEmails')?.addEventListener('change', async event => {
            const input = event.currentTarget; input.disabled = true;
            try { await request('/api/members/preferences/', { method: 'POST', body: { email_simulation_updates: input.checked } }); if (dashboard.profile) dashboard.profile.email_simulation_updates = input.checked; status(input.checked ? 'Personalized simulation emails are on.' : 'Personalized simulation emails are off.', 'success'); }
            catch (error) { input.checked = !input.checked; status(error.message, 'error'); } finally { input.disabled = false; }
        });
        panel.querySelector('#pitWallF1Search')?.addEventListener('submit', async event => {
            event.preventDefault(); const form = event.currentTarget; const button = form.querySelector('button'); const results = panel.querySelector('#pitWallF1Results');
            button.disabled = true; results.innerHTML = '<span>Checking the official Box Box league feed…</span>';
            try { const query = encodeURIComponent(form.elements.team_name.value.trim()); const data = await request(`/api/members/team/?action=f1-search&q=${query}`); results.innerHTML = data.teams?.length ? data.teams.map(team => `<button type="button" data-team-link-token="${escapeHtml(team.link_token)}" data-official-slot="${Number(team.slot)}"><strong>${escapeHtml(team.name)} · T${team.slot}</strong><small>${escapeHtml(team.manager || '')}${team.rank ? ` · Rank #${Number(team.rank).toLocaleString()}` : ''} · saves to Team ${Number(team.slot)}</small></button>`).join('') : `<span>No match yet. Join the Box Box league, then search again.</span>`;
                results.querySelectorAll('button').forEach(resultButton => resultButton.addEventListener('click', async () => { resultButton.disabled = true; const slot = Number(resultButton.dataset.officialSlot); try { await store?.linkOfficial(slot, { link_token: resultButton.dataset.teamLinkToken }); await store?.syncOfficial(slot, window.BoxBoxTeamMemory?.currentRound?.()); status(`Official team connected to Team ${slot}.`, 'success'); renderSignedIn(); } catch (error) { status(error.message, 'error'); resultButton.disabled = false; } }));
            } catch (error) { results.innerHTML = `<span>${escapeHtml(error.message)}</span>`; } finally { button.disabled = false; }
        });
        panel.querySelectorAll('[data-team-sync]').forEach(button => button.addEventListener('click', async () => { button.disabled = true; try { await store?.syncOfficial(Number(button.dataset.teamSync), window.BoxBoxTeamMemory?.currentRound?.()); status('Official lineup refreshed. Your manual saved lineup is unchanged.', 'success'); await loadSession(false); } catch (error) { status(error.message, 'error'); } finally { button.disabled = false; } }));
        panel.querySelectorAll('[data-team-unlink]').forEach(button => button.addEventListener('click', async () => { button.disabled = true; try { await request('/api/members/team/', { method: 'POST', body: { action: 'f1-unlink', team_slot: Number(button.dataset.teamUnlink), slot: Number(button.dataset.teamUnlink) } }); status('Official sync disconnected. Your saved lineup is unchanged.', 'success'); await loadSession(false); } catch (error) { status(error.message, 'error'); } finally { button.disabled = false; } }));

        panel.querySelector('#pitWallSignOut')?.addEventListener('click', async () => {
            await request('/api/members/sign-out/', { method: 'POST' }).catch(() => null);
            dashboard = null;
            renderLoggedOut('Signed out.');
            announceAuthChange();
        });
    }

    async function loadSession(applySavedTeam = true) {
        try {
            dashboard = await request('/api/members/session/');
            if (!dashboard.authenticated) {
                const welcome = new URLSearchParams(location.search).get('member') === 'welcome';
                renderLoggedOut(welcome ? 'That account link is no longer valid. Create or reset your password to continue.' : '');
                return;
            }
            if (new URLSearchParams(location.search).get('member') === 'password') {
                renderPasswordSetup();
                return;
            }
            const store = getTeamStore();
            if (store) store.hydrate(dashboard, { selectedSlot: store.getState().selectedSlot });
            lastSavedFingerprint = hasCompleteTeam(dashboard.team) ? snapshotFingerprint(dashboard.team) : '';
            renderSignedIn();
            const preferred = preferredMemberTeam(dashboard);
            if (applySavedTeam && dashboard.entitlement?.active && store?.hasCompleteTeam?.(store.getSelectedTeam?.())) {
                store.applyToMemory(store.getState().selectedSlot);
                status('Your saved Transfer Advisor team has been loaded.', 'success');
            } else if (applySavedTeam && dashboard.entitlement?.active && preferred?.source === 'official'
                && window.BoxBoxTeamMemory?.applyOfficial(preferred.team)) {
                status('Your latest official F1 Fantasy team has been loaded as the starting point.', 'success');
            } else if (new URLSearchParams(location.search).get('member') === 'welcome') {
                status('Signed in. Complete your team and save it here.', 'success');
            }
        } catch (error) {
            renderLoggedOut();
            status(error.message, 'error');
        }
    }

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { applySyncedOfficialSnapshot, canonicalTeamSnapshot, hasCompleteTeam, preferredMemberTeam, snapshotFingerprint };
    }
    if (typeof document === 'undefined' || typeof window === 'undefined') return;

    document.addEventListener('DOMContentLoaded', () => {
        panel = document.getElementById('pitWallMemberPanel');
        if (!panel) return;
        renderLoggedOut();
        loadSession();
        window.addEventListener('boxbox:team-changed', scheduleWorkingTeamAutosave);
        window.addEventListener('pagehide', flushWorkingTeamOnExit);
        window.addEventListener('boxbox:member-auth-changed', event => {
            if (event.detail?.source !== 'member-panel') loadSession(false);
        });
    });
})();
