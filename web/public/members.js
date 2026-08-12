(function () {
    'use strict';

    let dashboard = null;
    let panel = null;

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

    function renderLoggedOut(message = '') {
        panel.innerHTML = `<div class="pit-wall-heading">
            <div><span>Paid Pit Wall account · $5/month</span><h4>Save and sync your team</h4></div>
            <span class="pit-wall-badge">Ko-fi members</span>
        </div>
        <p>This sign-in is only for active Pit Wall members. It is separate from free Beat V13 email registration.</p>
        <form class="pit-wall-signin" id="pitWallSignInForm">
            <div class="pit-wall-fields"><label for="pitWallEmail">Ko-fi membership email</label><input id="pitWallEmail" name="email" type="email" autocomplete="email" placeholder="you@example.com" required><label for="pitWallPassword">Password</label><input id="pitWallPassword" name="password" type="password" autocomplete="current-password" minlength="8" maxlength="128" required><button type="submit">Sign in</button></div>
        </form>
        <div class="pit-wall-links"><button type="button" class="pit-wall-text-button" id="pitWallResetPassword">Create or reset password</button><a href="https://ko-fi.com/boxboxf1fantasy/tiers" target="_blank" rel="noopener">Join or renew on Ko-fi</a><a href="/#beatbot">Enter Beat V13 free instead</a></div>
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

        panel.innerHTML = `<div class="pit-wall-heading">
            <div><span>Pit Wall account</span><h4>${escapeHtml(dashboard.email)}</h4></div>
            <span class="pit-wall-badge ${active ? 'active' : 'inactive'}">${active ? `Active${ending ? ` to ${ending}` : ''}` : 'Membership inactive'}</span>
        </div>
        ${active ? `<p>Your saved lineup is the source for personalized early-thoughts and post-FP simulation emails.</p>
            <div class="pit-wall-actions"><button type="button" class="pit-wall-save" id="pitWallSaveTeam">Save current team</button><button type="button" class="pit-wall-secondary" id="pitWallSignOut">Sign out</button></div>
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
                const result = await request('/api/members/team/', { method: 'POST', body: snapshot });
                status(result.message, 'success');
                await loadSession(false);
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
            button.disabled = true;
            status('Syncing your official lineup…');
            try {
                const result = await request('/api/members/team/', { method: 'POST', body: { action: 'f1-sync', round: window.BoxBoxTeamMemory?.currentRound() } });
                await loadSession(true);
                status(result.message, 'success');
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
            renderSignedIn();
            if (applySavedTeam && dashboard.entitlement?.active && dashboard.f1_snapshot?.assets?.length >= 7
                && window.BoxBoxTeamMemory?.applyOfficial(dashboard.f1_snapshot)) {
                status('Your latest official F1 Fantasy team has been loaded.', 'success');
            } else if (applySavedTeam && dashboard.entitlement?.active && dashboard.team) {
                window.BoxBoxTeamMemory?.apply(dashboard.team);
                status('Your saved team has been loaded.', 'success');
            } else if (new URLSearchParams(location.search).get('member') === 'welcome') {
                status('Signed in. Complete your team and save it here.', 'success');
            }
        } catch (error) {
            renderLoggedOut();
            status(error.message, 'error');
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        panel = document.getElementById('pitWallMemberPanel');
        if (!panel) return;
        renderLoggedOut();
        loadSession();
        if (new URLSearchParams(location.search).get('pitwall') === '1') {
            document.querySelector('.mode-btn[data-mode="transfers"]')?.click();
            window.setTimeout(() => panel.scrollIntoView({ behavior: 'smooth', block: 'center' }), 250);
        }
    });
})();
