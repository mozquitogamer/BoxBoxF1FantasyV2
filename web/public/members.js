(function () {
    'use strict';

    let dashboard = null;
    let panel = null;
    let autosaveTimer = null;
    let autosaveQueue = Promise.resolve();
    let lastSavedFingerprint = '';

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
        const assets = team.assets.map(asset => ({
            asset_type: asset.asset_type === 'constructor' ? 'constructor' : 'driver',
            asset_id: String(asset.asset_id || ''),
            slot: Number(asset.slot),
            is_boosted: asset.is_boosted === true,
        })).sort((left, right) => left.asset_type.localeCompare(right.asset_type) || left.slot - right.slot);
        return {
            budget_millions: Number(team.budget_millions),
            free_transfers: Number(team.free_transfers),
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
        const saved = dashboard.team;
        const latest = dashboard.recommendation?.recommendation;
        const f1Link = dashboard.f1_link;
        const f1Snapshot = dashboard.f1_snapshot;
        const savedText = saved
            ? `Saved ${friendlyDate(saved.updated_at)} · ${saved.assets?.length || 0}/7 picks remembered`
            : 'No team saved yet. Complete all seven slots, then save.';
        const latestHtml = latest?.headline
            ? `<div class="pit-wall-latest"><span>Latest personal check</span><strong>${escapeHtml(latest.headline)}</strong></div>`
            : '';

        const officialHtml = f1Link
            ? `<div class="pit-wall-official linked"><div><span>Official F1 team</span><strong>${escapeHtml(f1Link.official_team_name)} · T${f1Link.team_slot}</strong><small>${f1Link.last_synced_at ? `Last synced ${friendlyDate(f1Link.last_synced_at)}` : 'Linked · waiting for first sync'}${f1Snapshot?.round ? ` · Round ${f1Snapshot.round}` : ''}</small></div><div class="pit-wall-actions"><button type="button" class="pit-wall-secondary" id="pitWallSyncF1">Sync now</button><button type="button" class="pit-wall-link-danger" id="pitWallDisconnectF1">Disconnect</button></div></div>`
            : `<div class="pit-wall-official"><span>Official F1 Fantasy sync</span><p>Join the <strong>Box Box F1 Fantasy</strong> league, then link one official team. We never ask for your F1 password.</p><form id="pitWallF1Search"><div><input name="team_name" type="search" placeholder="Search your official team name" minlength="2" required><button type="submit">Find team</button></div></form><div class="pit-wall-search-results" id="pitWallF1Results"></div></div>`;
        const resetButton = hasCompleteTeam(f1Snapshot)
            ? '<button type="button" class="pit-wall-secondary" id="pitWallResetOfficial">Reset to official team</button>'
            : '';

        panel.innerHTML = `<div class="pit-wall-signed-in"><strong>✓ Signed in to Pit Wall</strong><span>Your saved team and personalized suggestions are connected to this account.</span></div>
        <div class="pit-wall-heading">
            <div><span>Pit Wall account</span><h4>${escapeHtml(dashboard.email)}</h4></div>
            <span class="pit-wall-badge ${active ? 'active' : 'inactive'}">${active ? `Active${ending ? ` to ${ending}` : ''}` : 'Membership inactive'}</span>
        </div>
        ${active ? `<p>Your Transfer Advisor edits save automatically. The latest official sync stays separate, so you can always reset back to it.</p>
            <div class="pit-wall-actions"><button type="button" class="pit-wall-save" id="pitWallSaveTeam">Save current team</button>${resetButton}<button type="button" class="pit-wall-secondary" id="pitWallSignOut">Sign out</button></div>
            <label class="pit-wall-pref"><input type="checkbox" id="pitWallSimEmails" ${dashboard.profile?.email_simulation_updates !== false ? 'checked' : ''}> Email me personalized simulation updates</label>
            <p class="pit-wall-saved">${escapeHtml(savedText)}</p>${officialHtml}${latestHtml}` : `<p>Your Ko-fi entitlement is no longer active. Your saved data is retained and returns when you renew.</p>
            <div class="pit-wall-actions"><a class="pit-wall-save" href="https://ko-fi.com/boxboxf1fantasy/tiers" target="_blank" rel="noopener">Renew on Ko-fi</a><button type="button" class="pit-wall-secondary" id="pitWallSignOut">Sign out</button></div>`}
        <p class="pit-wall-status" id="pitWallStatus" role="status" aria-live="polite"></p>`;

        panel.querySelector('#pitWallSaveTeam')?.addEventListener('click', async event => {
            const button = event.currentTarget;
            try {
                const snapshot = window.BoxBoxTeamMemory?.getSnapshot();
                button.disabled = true;
                status('Saving your lineup…');
                await persistWorkingTeam(snapshot, 'Your Transfer Advisor team is saved.');
            } catch (error) {
                status(error.message, 'error');
            } finally {
                button.disabled = false;
            }
        });

        panel.querySelector('#pitWallResetOfficial')?.addEventListener('click', async event => {
            if (!hasCompleteTeam(dashboard.f1_snapshot)) {
                status('Sync an official F1 team before using reset.', 'error');
                return;
            }
            if (!window.confirm('Reset your saved Transfer Advisor lineup to the latest official F1 team?')) return;
            const button = event.currentTarget;
            button.disabled = true;
            try {
                if (!window.BoxBoxTeamMemory?.applyOfficial(dashboard.f1_snapshot)) {
                    throw new Error('The official lineup could not be matched to the current driver list.');
                }
                const snapshot = window.BoxBoxTeamMemory.getSnapshot();
                await persistWorkingTeam(snapshot, 'Reset complete. Your official synced team is now the saved Transfer Advisor team.');
            } catch (error) {
                status(error.message, 'error');
            } finally {
                button.disabled = false;
            }
        });

        panel.querySelector('#pitWallSimEmails')?.addEventListener('change', async event => {
            const input = event.currentTarget;
            input.disabled = true;
            try {
                await request('/api/members/preferences/', {
                    method: 'POST',
                    body: { email_simulation_updates: input.checked },
                });
                if (dashboard.profile) dashboard.profile.email_simulation_updates = input.checked;
                status(input.checked ? 'Personalized simulation emails are on.' : 'Personalized simulation emails are off.', 'success');
            } catch (error) {
                input.checked = !input.checked;
                status(error.message, 'error');
            } finally {
                input.disabled = false;
            }
        });

        panel.querySelector('#pitWallF1Search')?.addEventListener('submit', async event => {
            event.preventDefault();
            const form = event.currentTarget;
            const button = form.querySelector('button');
            const results = panel.querySelector('#pitWallF1Results');
            button.disabled = true;
            results.innerHTML = '<span>Searching the BoxBox league…</span>';
            try {
                const data = await request(`/api/members/team/?action=f1-search&q=${encodeURIComponent(form.elements.team_name.value.trim())}`);
                results.innerHTML = data.teams.length ? data.teams.map(team => `<button type="button" data-team-id="${escapeHtml(team.id)}" data-team-slot="${team.slot}"><strong>${escapeHtml(team.name)} · T${team.slot}</strong><small>${escapeHtml(team.manager || '')}${team.rank ? ` · League rank ${team.rank}` : ''}</small></button>`).join('') : '<span>No matching team found. Check the spelling and confirm you joined our league.</span>';
                results.querySelectorAll('button').forEach(resultButton => resultButton.addEventListener('click', async () => {
                    resultButton.disabled = true;
                    try {
                        const linked = await request('/api/members/team/', { method: 'POST', body: { action: 'f1-link', official_team_id: resultButton.dataset.teamId, team_slot: Number(resultButton.dataset.teamSlot) } });
                        status(linked.message, 'success');
                        await loadSession(false);
                    } catch (error) { status(error.message, 'error'); resultButton.disabled = false; }
                }));
            } catch (error) { results.innerHTML = `<span>${escapeHtml(error.message)}</span>`; }
            finally { button.disabled = false; }
        });

        panel.querySelector('#pitWallSyncF1')?.addEventListener('click', async event => {
            const button = event.currentTarget;
            const hadWorkingTeam = hasCompleteTeam(dashboard.team);
            button.disabled = true;
            status('Syncing your official lineup…');
            try {
                const result = await request('/api/members/team/', { method: 'POST', body: { action: 'f1-sync', round: window.BoxBoxTeamMemory?.currentRound() } });
                await loadSession(true);
                if (!hadWorkingTeam && !hasCompleteTeam(dashboard.team)) {
                    const snapshot = window.BoxBoxTeamMemory?.getSnapshot();
                    await persistWorkingTeam(snapshot, `${result.message} It is now your saved Transfer Advisor team.`);
                } else {
                    status(`${result.message} Your saved Transfer Advisor changes were kept; use Reset to official team whenever you want the synced baseline.`, 'success');
                }
            } catch (error) { status(error.message, 'error'); }
            finally { button.disabled = false; }
        });

        panel.querySelector('#pitWallDisconnectF1')?.addEventListener('click', async event => {
            event.currentTarget.disabled = true;
            try {
                const result = await request('/api/members/team/', { method: 'POST', body: { action: 'f1-unlink' } });
                status(result.message, 'success');
                await loadSession(false);
            } catch (error) { status(error.message, 'error'); event.currentTarget.disabled = false; }
        });

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
            lastSavedFingerprint = hasCompleteTeam(dashboard.team) ? snapshotFingerprint(dashboard.team) : '';
            renderSignedIn();
            const preferred = preferredMemberTeam(dashboard);
            if (applySavedTeam && dashboard.entitlement?.active && preferred?.source === 'saved') {
                window.BoxBoxTeamMemory?.apply(preferred.team);
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
        module.exports = { canonicalTeamSnapshot, hasCompleteTeam, preferredMemberTeam, snapshotFingerprint };
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
