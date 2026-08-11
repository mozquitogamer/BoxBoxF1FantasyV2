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
            <div><span>Pit Wall · $5/month</span><h4>Remember this team</h4></div>
            <span class="pit-wall-badge">Member convenience</span>
        </div>
        <p>Paid members can sign in with their Ko-fi email, save this lineup once, and receive a tailored suggestion whenever fresh simulations go live.</p>
        <form class="pit-wall-signin" id="pitWallSignInForm">
            <label for="pitWallEmail">Ko-fi membership email</label>
            <div><input id="pitWallEmail" name="email" type="email" autocomplete="email" placeholder="you@example.com" required><button type="submit">Email me a sign-in link</button></div>
        </form>
        <div class="pit-wall-links"><a href="https://ko-fi.com/boxboxf1fantasy/tiers" target="_blank" rel="noopener">Join or renew on Ko-fi</a><span>Use the same email as your Ko-fi payment.</span></div>
        <p class="pit-wall-status${message ? ' success' : ''}" id="pitWallStatus" role="status" aria-live="polite">${escapeHtml(message)}</p>`;

        panel.querySelector('#pitWallSignInForm')?.addEventListener('submit', async event => {
            event.preventDefault();
            const form = event.currentTarget;
            const button = form.querySelector('button');
            const email = form.elements.email.value.trim();
            button.disabled = true;
            status('Preparing your secure link…');
            try {
                const result = await request('/api/members/sign-in', { method: 'POST', body: { email } });
                status(result.message, 'success');
                form.elements.email.value = '';
            } catch (error) {
                status(error.message, 'error');
            } finally {
                button.disabled = false;
            }
        });
    }

    function renderSignedIn() {
        const active = dashboard.entitlement?.active === true;
        const ending = friendlyDate(dashboard.entitlement?.current_period_end);
        const saved = dashboard.team;
        const latest = dashboard.recommendation?.recommendation;
        const savedText = saved
            ? `Saved ${friendlyDate(saved.updated_at)} · ${saved.assets?.length || 0}/7 picks remembered`
            : 'No team saved yet. Complete all seven slots, then save.';
        const latestHtml = latest?.headline
            ? `<div class="pit-wall-latest"><span>Latest personal check</span><strong>${escapeHtml(latest.headline)}</strong></div>`
            : '';

        panel.innerHTML = `<div class="pit-wall-heading">
            <div><span>Pit Wall account</span><h4>${escapeHtml(dashboard.email)}</h4></div>
            <span class="pit-wall-badge ${active ? 'active' : 'inactive'}">${active ? `Active${ending ? ` to ${ending}` : ''}` : 'Membership inactive'}</span>
        </div>
        ${active ? `<p>Your saved lineup is the source for personalized early-thoughts and post-FP simulation emails.</p>
            <div class="pit-wall-actions"><button type="button" class="pit-wall-save" id="pitWallSaveTeam">Save current team</button><button type="button" class="pit-wall-secondary" id="pitWallSignOut">Sign out</button></div>
            <label class="pit-wall-pref"><input type="checkbox" id="pitWallSimEmails" ${dashboard.profile?.email_simulation_updates !== false ? 'checked' : ''}> Email me personalized simulation updates</label>
            <p class="pit-wall-saved">${escapeHtml(savedText)}</p>${latestHtml}` : `<p>Your Ko-fi entitlement is no longer active. Your saved data is retained and returns when you renew.</p>
            <div class="pit-wall-actions"><a class="pit-wall-save" href="https://ko-fi.com/boxboxf1fantasy/tiers" target="_blank" rel="noopener">Renew on Ko-fi</a><button type="button" class="pit-wall-secondary" id="pitWallSignOut">Sign out</button></div>`}
        <p class="pit-wall-status" id="pitWallStatus" role="status" aria-live="polite"></p>`;

        panel.querySelector('#pitWallSaveTeam')?.addEventListener('click', async event => {
            const button = event.currentTarget;
            try {
                const snapshot = window.BoxBoxTeamMemory?.getSnapshot();
                button.disabled = true;
                status('Saving your lineup…');
                const result = await request('/api/members/team', { method: 'POST', body: snapshot });
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
                await request('/api/members/preferences', {
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

        panel.querySelector('#pitWallSignOut')?.addEventListener('click', async () => {
            await request('/api/members/sign-out', { method: 'POST' }).catch(() => null);
            dashboard = null;
            renderLoggedOut('Signed out.');
        });
    }

    async function loadSession(applySavedTeam = true) {
        try {
            dashboard = await request('/api/members/session');
            if (!dashboard.authenticated) {
                const welcome = new URLSearchParams(location.search).get('member') === 'welcome';
                renderLoggedOut(welcome ? 'That sign-in link is no longer valid. Request a fresh one.' : '');
                return;
            }
            renderSignedIn();
            if (applySavedTeam && dashboard.entitlement?.active && dashboard.team) {
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
    });
})();
