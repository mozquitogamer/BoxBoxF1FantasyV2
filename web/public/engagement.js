/* ============================================================
   BoxBoxF1Fantasy — email updates and restrained monetization UI
   ============================================================ */

window.BoxBoxFreeAccess = Object.freeze({
    isBeatV13Confirmed() {
        return document.cookie.split(';').some(cookie => cookie.trim() === '__Host-boxbox_beat_v13=confirmed');
    },
    renderConfirmedPanel(panel) {
        if (!panel || !this.isBeatV13Confirmed()) return false;
        panel.classList.add('is-confirmed');
        const eyebrow = panel.querySelector('.email-updates-eyebrow');
        const title = panel.querySelector('.email-updates-copy h2');
        const body = panel.querySelector('.email-updates-copy p');
        const form = panel.querySelector('.email-updates-form');
        if (eyebrow) eyebrow.textContent = 'Free Beat V13 entry · Confirmed';
        if (title) title.textContent = "You're officially entered";
        if (body) body.textContent = 'Your Beat V13 email is confirmed and this browser remembers the non-sensitive confirmation state. Watch V13’s score and decisions now; final submission instructions arrive by email.';
        if (form) form.hidden = true;
        if (!panel.querySelector('.email-updates-confirmed-action')) {
            const link = document.createElement('a');
            link.className = 'email-updates-confirmed-action';
            link.href = '/?v13=dashboard#beatbot';
            link.textContent = panel.dataset.registrationLocation === 'beat_v13' ? 'Open my dashboard' : 'View challenge standings';
            panel.appendChild(link);
        }
        return true;
    },
    showRegistrationDialog({ state = 'pending', message = '', form = null } = {}) {
        const previousFocus = document.activeElement;
        document.getElementById('beatV13RegistrationDialog')?.remove();

        const backdrop = document.createElement('div');
        backdrop.id = 'beatV13RegistrationDialog';
        backdrop.className = 'beat-v13-registration-modal';
        backdrop.setAttribute('role', 'presentation');

        const dialog = document.createElement('section');
        dialog.className = 'beat-v13-registration-dialog';
        dialog.setAttribute('role', 'dialog');
        dialog.setAttribute('aria-modal', 'true');
        dialog.setAttribute('aria-labelledby', 'beatV13RegistrationDialogTitle');
        dialog.setAttribute('aria-describedby', 'beatV13RegistrationDialogBody');
        dialog.tabIndex = -1;

        const close = document.createElement('button');
        close.type = 'button';
        close.className = 'beat-v13-registration-close';
        close.setAttribute('aria-label', 'Close Beat V13 registration message');
        close.textContent = '×';

        const title = document.createElement('h2');
        title.id = 'beatV13RegistrationDialogTitle';
        title.textContent = state === 'confirmed'
            ? "You're officially entered"
            : state === 'error' ? "Registration couldn't be completed" : 'Confirmation email sent';

        const body = document.createElement('p');
        body.id = 'beatV13RegistrationDialogBody';
        body.textContent = message || (state === 'confirmed'
            ? 'Your email address is confirmed. You may now follow Beat V13.'
            : state === 'error'
                ? 'Please try again.'
                : 'One more step is required: open the email and confirm your address before the Round 22 lock.');

        const actions = document.createElement('div');
        actions.className = 'beat-v13-registration-dialog-actions';

        const dismiss = document.createElement('button');
        dismiss.type = 'button';
        dismiss.className = 'beat-v13-registration-dialog-primary';
        dismiss.textContent = state === 'error' ? 'Try again' : 'Close';
        actions.appendChild(dismiss);

        if (state === 'pending') {
            const note = document.createElement('p');
            note.className = 'beat-v13-registration-dialog-note';
            note.textContent = 'Your entry is not active until you use the confirmation link.';
            dialog.append(close, title, body, note, actions);
        } else {
            dialog.append(close, title, body, actions);
        }
        backdrop.appendChild(dialog);
        document.body.appendChild(backdrop);
        document.body.classList.add('beat-v13-registration-modal-open');

        const hide = () => {
            backdrop.remove();
            document.body.classList.remove('beat-v13-registration-modal-open');
            if (previousFocus && typeof previousFocus.focus === 'function') previousFocus.focus();
        };
        close.addEventListener('click', hide);
        backdrop.addEventListener('click', event => { if (event.target === backdrop) hide(); });
        dismiss.addEventListener('click', () => {
            hide();
            if (state === 'error') form?.querySelector('input[name="email"]')?.focus();
        });
        dialog.addEventListener('keydown', event => {
            if (event.key === 'Escape') { event.preventDefault(); hide(); }
        });
        dialog.focus();
        return { hide };
    },
    showRegistrationPending(message, form) {
        return this.showRegistrationDialog({ state: 'pending', message, form });
    },
    showRegistrationError(message, form) {
        return this.showRegistrationDialog({ state: 'error', message, form });
    },
    showRegistrationConfirmed(message, form) {
        return this.showRegistrationDialog({ state: 'confirmed', message, form });
    },
});

(function () {
    'use strict';

    const CONFIG_URL = '/data/site_features.json';
    const BEAT_V13_REGISTRATION_DEADLINE = Date.parse('2026-11-21T04:00:00Z');

    function track(eventName, params = {}) {
        if (typeof window.gtag === 'function') {
            window.gtag('event', eventName, params);
        }
    }

    function setStatus(element, message, state) {
        element.textContent = message;
        element.dataset.state = state || '';
    }

    async function initEmailUpdates(config) {
        const panel = document.querySelector('[data-registration-location="beat_v13"]');
        const form = panel?.querySelector('.email-updates-form');
        const status = panel?.querySelector('.email-updates-status');
        const submit = form?.querySelector('button[type="submit"]');

        if (!config?.enabled || !panel || !form || !status || !submit) return;

        if (window.BoxBoxFreeAccess.renderConfirmedPanel(panel)) {
            panel.hidden = false;
            return;
        }

        if (Date.now() >= BEAT_V13_REGISTRATION_DEADLINE) {
            panel.hidden = false;
            if (window.BoxBoxFreeAccess.renderConfirmedPanel(panel)) return;
            form.hidden = true;
            const eyebrow = panel.querySelector('.email-updates-eyebrow');
            const title = panel.querySelector('.email-updates-copy h2');
            const body = panel.querySelector('.email-updates-copy p');
            if (eyebrow) eyebrow.textContent = 'Beat V13 registration · Closed';
            if (title) title.textContent = 'The grid is locked';
            if (body) body.textContent = 'Registration closed at the Round 22 Las Vegas F1 Fantasy team lock. Registered entrants will receive the final submission instructions after the season.';
            return;
        }

        // Ship the public flag independently of private delivery credentials.
        // Do not expose a form that can only fail with a configuration error.
        try {
            const response = await fetch(config.status_endpoint || '/api/email/status', {
                cache: 'no-store',
            });
            const availability = await response.json().catch(() => ({}));
            if (!response.ok || availability.available !== true) return;
        } catch (_) {
            return;
        }

        panel.hidden = false;
        form.addEventListener('submit', async (event) => {
            event.preventDefault();

            const email = form.elements.email.value.trim();
            const consent = form.elements.consent.checked;
            const website = form.elements.website.value;

            if (!email || !consent) {
                setStatus(status, 'Enter your email and confirm your free Beat V13 registration.', 'error');
                return;
            }

            submit.disabled = true;
            submit.textContent = 'Sending…';
            setStatus(status, '', '');

            try {
                const response = await fetch(config.endpoint || '/api/email/subscribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, consent, website }),
                });
                const result = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(result.message || 'Sign-up could not be started.');

                form.reset();
                setStatus(
                    status,
                    result.message || 'Check your inbox and confirm your free Beat V13 registration.',
                    'success'
                );
                if (result.entry_status === 'confirmed') {
                    window.BoxBoxFreeAccess.showRegistrationConfirmed(result.message, form);
                } else {
                    window.BoxBoxFreeAccess.showRegistrationPending(result.message, form);
                }
                track('beat_v13_registration_started', { location: 'beat_v13' });
            } catch (error) {
                setStatus(
                    status,
                    error.message || 'Something went wrong. Please try again in a moment.',
                    'error'
                );
                window.BoxBoxFreeAccess.showRegistrationError(error.message || 'Something went wrong. Please try again in a moment.', form);
            } finally {
                submit.disabled = false;
                submit.textContent = 'Register free';
            }
        });
    }

    function initBottomBanner(config) {
        const banner = document.getElementById('bottomBanner');
        const link = document.getElementById('bottomBannerLink');
        const label = document.getElementById('bottomBannerLabel');
        const headline = document.getElementById('bottomBannerHeadline');
        const body = document.getElementById('bottomBannerBody');
        const cta = document.getElementById('bottomBannerCta');
        const image = document.getElementById('bottomBannerImage');

        if (!config?.enabled || !config.href || !config.headline || !banner || !link) return;

        label.textContent = config.label || 'Sponsored';
        headline.textContent = config.headline;
        body.textContent = config.body || '';
        body.hidden = !config.body;
        cta.textContent = config.cta || 'Learn more';
        link.href = config.href;

        if (/^https?:\/\//i.test(config.href)) {
            link.target = '_blank';
            link.rel = 'sponsored noopener';
        }

        if (config.image_url) {
            image.src = config.image_url;
            image.alt = '';
            image.hidden = false;
        }

        banner.hidden = false;
        link.addEventListener('click', () => {
            track('bottom_banner_click', { label: config.label || 'Sponsored' });
        });
    }

    function isValidPublisherId(value) {
        return /^ca-pub-\d{16}$/.test(String(value || '').trim());
    }

    function isValidSlotId(value) {
        return /^\d{10}$/.test(String(value || '').trim());
    }

    function showConfirmationRedirectMessage() {
        try {
            const params = new URLSearchParams(window.location.search);
            if (params.get('v13') !== 'confirmed') return;
            window.BoxBoxFreeAccess.showRegistrationConfirmed(
                "You're officially entered. Your email address is confirmed, and the non-sensitive confirmation state is saved in this browser.",
                document.querySelector('[data-registration-location="beat_v13"] form'),
            );
        } catch (_) {
            // Older static previews may not provide URLSearchParams. The
            // confirmation panel still renders from the display cookie.
        }
    }

    function initAdSense(config) {
        const banner = document.getElementById('adsenseBanner');
        const unit = document.getElementById('adsenseBottomUnit');
        const publisherId = String(config?.publisher_id || '').trim();
        const slotId = String(config?.bottom_display_slot_id || '').trim();

        if (!config?.display_ads_enabled || !config?.account_code_enabled) return false;
        if (!banner || !unit || !isValidPublisherId(publisherId) || !isValidSlotId(slotId)) {
            console.warn('AdSense display inventory is enabled but its public IDs are invalid.');
            return false;
        }

        unit.dataset.adClient = publisherId;
        unit.dataset.adSlot = slotId;

        banner.hidden = false;
        try {
            (window.adsbygoogle = window.adsbygoogle || []).push({});
            track('adsense_bottom_unit_requested', { location: 'site_footer' });
            return true;
        } catch (error) {
            banner.hidden = true;
            console.warn('The optional AdSense unit could not be requested:', error);
            return false;
        }
    }

    async function initEngagement() {
        showConfirmationRedirectMessage();
        try {
            const response = await fetch(CONFIG_URL, { cache: 'no-store' });
            if (!response.ok) return;
            const config = await response.json();
            await initEmailUpdates(config.email_updates);
            const adSenseActive = initAdSense(config.adsense);
            if (!adSenseActive) initBottomBanner(config.bottom_banner);
        } catch (error) {
            console.warn('Optional engagement features could not be loaded:', error);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initEngagement, { once: true });
    } else {
        initEngagement();
    }
})();

/* Site-wide access hub. Free entry and paid Pit Wall remain separate systems. */
(function () {
    'use strict';

    async function memberRequest(path, options = {}) {
        const response = await fetch(path, {
            method: options.method || 'GET',
            headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
            body: options.body ? JSON.stringify(options.body) : undefined,
            credentials: 'same-origin',
            cache: 'no-store',
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.message || 'That request did not complete.');
        return data;
    }

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>'"]/g, character => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
        })[character]);
    }

    function initAccessHub() {
        if (document.getElementById('pitWallAccountButton')) return;

        const button = document.createElement('button');
        button.id = 'pitWallAccountButton';
        button.className = 'pit-wall-account-button';
        button.type = 'button';
        button.textContent = 'Account & Pit Wall';
        button.setAttribute('aria-haspopup', 'dialog');
        const host = document.querySelector('.header-right') || document.querySelector('.topbar .wrap');
        if (host) host.appendChild(button);
        else { button.classList.add('floating'); document.body.appendChild(button); }

        const modal = document.createElement('div');
        modal.className = 'pit-wall-login-modal access-hub-modal';
        modal.hidden = true;
        modal.innerHTML = `<div class="pit-wall-login-backdrop" data-pit-wall-close></div><section class="pit-wall-login-dialog access-hub-dialog" role="dialog" aria-modal="true" aria-labelledby="pitWallLoginTitle"><button class="pit-wall-login-close" type="button" data-pit-wall-close aria-label="Close">&times;</button><div id="pitWallLoginContent"><p>Checking your access&hellip;</p></div></section>`;
        document.body.appendChild(modal);
        const content = modal.querySelector('#pitWallLoginContent');
        let beatSession = null;
        const close = () => { modal.hidden = true; button.focus(); };
        modal.querySelectorAll('[data-pit-wall-close]').forEach(node => node.addEventListener('click', close));
        document.addEventListener('keydown', event => { if (event.key === 'Escape' && !modal.hidden) close(); });

        function beatConfirmed() {
            return beatSession?.authenticated === true
                || window.BoxBoxFreeAccess?.isBeatV13Confirmed() === true;
        }

        function freeAccessCard() {
            const confirmed = beatConfirmed();
            const linked = beatSession?.authenticated === true && beatSession?.linked === true;
            const beatStatus = linked
                ? '✓ Official team linked for live scoring'
                : confirmed
                    ? '✓ Confirmed · link your official team'
                    : 'Not entered · free confirmation required';
            const challengeHref = confirmed ? '/?v13=dashboard#beatbot' : '/#beatbot';
            const challengeAction = linked
                ? 'Open my Beat V13 dashboard'
                : confirmed
                    ? 'Open dashboard & link team'
                    : 'Register / confirm Beat V13';
            return `<section class="access-hub-card free-access-card">
                <div class="access-hub-card-head"><div><span class="access-tier-label free">Always free</span><h3>Free BoxBox access</h3></div><strong class="access-state active">Active</strong></div>
                <p>No password or payment is needed for predictions, simulations, V13’s score, the optimizer, Transfer Advisor, planners or the accuracy record. Pit Wall membership does not enter Beat V13 or link an official team automatically.</p>
                <ul><li>Use every public fantasy tool</li><li>Follow every V13 decision and score</li><li>Enter Beat V13 and receive general updates by email</li></ul>
                <div class="access-entry-state ${confirmed ? 'confirmed' : ''}"><span>Beat V13 status</span><strong>${beatStatus}</strong></div>
                <a class="access-hub-action secondary" href="${challengeHref}">${challengeAction}</a>
            </section>`;
        }

        function pitWallBenefits() {
            return `<ul class="pit-wall-benefit-list"><li>Your official F1 team remembered and synced</li><li>Personalized transfer suggestions for your lineup</li><li>Early-thoughts and post-FP updates delivered automatically</li></ul>`;
        }

        function memberTeams(session) {
            const normalized = window.BoxBoxTeamState?.normalizeTeams?.(session);
            if (Array.isArray(normalized) && normalized.length === 3) return normalized;
            if (Array.isArray(session?.teams) && session.teams.length) return session.teams;
            const single = session?.team ? [{ ...session.team, team_slot: session.team.team_slot || session.team.slot || 1 }] : [];
            return Array.from({ length: 3 }, (_, index) => single.find(team => Number(team.team_slot || team.slot) === index + 1)
                || { team_slot: index + 1, slot: index + 1, name: `Team ${index + 1}`, is_primary: index === 0, chips: {} });
        }

        function chipCount(team) {
            const chips = team?.chips && typeof team.chips === 'object' ? team.chips : {};
            const keys = window.BoxBoxTeamState?.CHIP_KEYS || ['limitless', '3x_boost', 'wild_card', 'no_negative', 'autopilot', 'final_fix'];
            return keys.filter(key => window.BoxBoxTeamState?.chipRemaining?.(team, key) === true
                || chips[key] === true
                || chips[key]?.remaining === true
                || chips[key]?.available === true
                || chips[key]?.used === false).length;
        }

        function memberTeamSummaries(session, active) {
            const teams = memberTeams(session);
            return `<div class="pit-wall-team-summaries" aria-label="Saved Pit Wall teams">${teams.map((team, index) => {
                const slot = Number(team.team_slot || team.slot || index + 1);
                const name = escapeHtml(team.name || `Team ${slot}`);
                const bank = Number.isFinite(Number(team.bank_millions)) ? ` · Bank $${Number(team.bank_millions).toFixed(1)}m` : '';
                const squad = Number.isFinite(Number(team.squad_value_millions)) ? `Squad $${Number(team.squad_value_millions).toFixed(1)}m` : 'Squad value pending';
                const chips = chipCount(team);
                return `<article class="pit-wall-team-summary"><div><span>Team ${slot}${team.is_primary || team.is_default ? ' · Primary' : ''}</span><strong>${name}</strong></div><small>${squad}${bank} · ${chips} chips left</small><div class="pit-wall-team-summary-actions"><a href="/?pitwall=1#optimizer" data-team-slot="${slot}">${active ? 'Open team' : 'View team'}</a>${active ? `<a href="/?pitwall=1#optimizer" data-team-compare="${slot}">Compare</a>` : ''}</div></article>`;
            }).join('')}</div>`;
        }

        function accessHeader(pitState) {
            const confirmed = beatConfirmed();
            return `<span class="pit-wall-login-eyebrow">Your BoxBox access</span><h2 id="pitWallLoginTitle">Free tools first. Pit Wall when you want convenience.</h2><p class="access-hub-intro">Beat V13 registration is a free email entry. Pit Wall is the separate $5/month account with a password and personalized member tools.</p><div class="access-status-strip"><span><small>Public tools</small><strong>Active</strong></span><span><small>Beat V13</small><strong>${confirmed ? 'Registered' : 'Needs free confirmation'}</strong></span><span><small>Pit Wall</small><strong>${pitState}</strong></span></div>`;
        }

        function updateHeaderButton(session) {
            const active = session?.authenticated && session.entitlement?.active === true;
            button.classList.toggle('active', active);
            if (active) button.textContent = `Pit Wall · ${Math.max(memberTeams(session).length, 3)} teams`;
            else if (session?.authenticated) button.textContent = 'Pit Wall · Signed in';
            else if (beatSession?.authenticated) button.textContent = 'Beat V13 · Signed in';
            else if (beatConfirmed()) button.textContent = 'Beat V13 ✓ · Account';
            else button.textContent = 'Account & Pit Wall';
            button.setAttribute('aria-label', `${button.textContent}. Open access details.`);
        }

        function renderLoggedOut(message = '') {
            updateHeaderButton(null);
            const freeSignOut = beatSession?.authenticated
                ? '<div class="pit-wall-login-actions access-hub-unified-signout"><span>Beat V13 account signed in</span><button type="button" id="siteUnifiedSignOut">Sign out of BoxBox</button></div>'
                : '';
            content.innerHTML = `${accessHeader('Not signed in')}${freeSignOut}<div class="access-hub-grid">${freeAccessCard()}<section class="access-hub-card pit-wall-access-card"><div class="access-hub-card-head"><div><span class="access-tier-label paid">$5/month · Ko-fi</span><h3>Pit Wall membership</h3></div><strong class="access-state">Optional upgrade</strong></div><p>Everything free stays free. Pit Wall removes the weekly admin by remembering your real team and bringing the relevant advice to you.</p>${pitWallBenefits()}<details class="pit-wall-member-signin"${message ? ' open' : ''}><summary><span>Already a member?</span><strong>Sign in</strong></summary><div class="pit-wall-member-signin-body"><form id="sitePitWallSignIn"><label for="sitePitWallEmail">Ko-fi membership email</label><input id="sitePitWallEmail" name="email" type="email" autocomplete="email" placeholder="you@example.com" required><label for="sitePitWallPassword">Pit Wall password</label><input id="sitePitWallPassword" name="password" type="password" autocomplete="current-password" minlength="8" maxlength="128" required><button type="submit">Sign in to Pit Wall</button></form><p class="pit-wall-login-status" role="status" aria-live="polite">${escapeHtml(message)}</p><div class="pit-wall-login-links"><button type="button" class="pit-wall-login-reset" id="sitePitWallReset">Create or reset password</button><a class="pit-wall-login-kofi" href="https://ko-fi.com/boxboxf1fantasy/tiers" target="_blank" rel="noopener">Join Pit Wall on Ko-fi</a></div></div></details></section></div>`;
            content.querySelector('#siteUnifiedSignOut')?.addEventListener('click', signOutEverywhere);
            content.querySelector('#sitePitWallSignIn')?.addEventListener('submit', async event => {
                event.preventDefault();
                const form = event.currentTarget;
                const submit = form.querySelector('button');
                const status = content.querySelector('.pit-wall-login-status');
                submit.disabled = true;
                status.textContent = 'Signing in…';
                status.dataset.state = '';
                try {
                    await memberRequest('/api/members/sign-in/', { method: 'POST', body: { email: form.elements.email.value.trim(), password: form.elements.password.value } });
                    await refresh();
                    window.dispatchEvent(new CustomEvent('boxbox:member-auth-changed', { detail: { source: 'site-header' } }));
                    if (typeof window.BoxBoxOpenPitWall === 'function') {
                        close();
                        window.BoxBoxOpenPitWall();
                    }
                } catch (error) {
                    status.textContent = error.message;
                    status.dataset.state = 'error';
                } finally { submit.disabled = false; }
            });
            content.querySelector('#sitePitWallReset')?.addEventListener('click', async event => {
                const email = content.querySelector('#sitePitWallEmail')?.value.trim();
                const status = content.querySelector('.pit-wall-login-status');
                if (!email) { status.textContent = 'Enter your Ko-fi membership email first.'; status.dataset.state = 'error'; return; }
                event.currentTarget.disabled = true;
                try {
                    const result = await memberRequest('/api/members/password/', { method: 'POST', body: { action: 'reset', email } });
                    status.textContent = result.message;
                    status.dataset.state = 'success';
                } catch (error) { status.textContent = error.message; status.dataset.state = 'error'; }
                finally { event.currentTarget.disabled = false; }
            });
        }

        function renderSignedIn(session) {
            const active = session.entitlement?.active === true;
            updateHeaderButton(session);
            const pitState = active ? 'Active member' : 'Signed in · inactive';
            const teams = memberTeams(session);
            content.innerHTML = `${accessHeader(pitState)}<div class="access-hub-grid">${freeAccessCard()}<section class="access-hub-card pit-wall-access-card ${active ? 'is-active' : ''}"><div class="access-hub-card-head"><div><span class="access-tier-label paid">Pit Wall account</span><h3>Pit Wall workspace</h3></div><strong class="access-state ${active ? 'active' : ''}">${active ? '✓ Active' : 'Membership inactive'}</strong></div><p>${active ? 'Your three saved teams live here. Pick a working team, compare lineups, and keep each budget and chip ledger separate.' : 'Your login works, but the Ko-fi membership linked to it is not currently active. Saved teams remain visible and read-only.'}</p><p class="access-hub-separation-note"><strong>Beat V13 is separate.</strong> Your Pit Wall account does not enroll you in the free challenge or connect its official team. Use the Beat V13 card to confirm entry, then link the exact official team from its dashboard.</p>${memberTeamSummaries(session, active)}<div class="pit-wall-login-actions">${active ? '<a href="/?pitwall=1#optimizer">Open Pit Wall</a>' : '<a href="https://ko-fi.com/boxboxf1fantasy/tiers" target="_blank" rel="noopener">Renew on Ko-fi</a>'}<button type="button" id="sitePitWallSignOut">Sign out of BoxBox</button></div></section></div>`;
            content.querySelector('#sitePitWallSignOut')?.addEventListener('click', signOutEverywhere);
            content.querySelectorAll('[data-team-slot]').forEach(link => link.addEventListener('click', event => {
                event.preventDefault();
                window.BoxBoxTeamState?.getStore?.().select(Number(link.dataset.teamSlot), { applyMemory: false });
                close();
                window.BoxBoxOpenPitWall?.();
                window.location.hash = 'optimizer';
            }));
            content.querySelectorAll('[data-team-compare]').forEach(link => link.addEventListener('click', event => {
                event.preventDefault();
                window.BoxBoxTeamState?.getStore?.().select(Number(link.dataset.teamCompare), { applyMemory: false });
                close();
                window.BoxBoxTeamCompare?.open?.({ slot: Number(link.dataset.teamCompare), source: 'access-hub' });
                window.location.hash = 'optimizer';
            }));
        }

        async function signOutEverywhere() {
            await memberRequest('/api/members/sign-out/', { method: 'POST' }).catch(() => null);
            beatSession = { authenticated: false };
            renderLoggedOut('Signed out of BoxBox.');
            window.dispatchEvent(new CustomEvent('boxbox:member-auth-changed', { detail: { source: 'site-header' } }));
            window.dispatchEvent(new CustomEvent('boxbox:beat-v13-auth-changed', { detail: { source: 'site-header' } }));
        }

        async function refresh() {
            const [memberResult, beatResult] = await Promise.allSettled([
                memberRequest('/api/members/session/'),
                fetch('/api/members/session/?scope=beat-v13', { credentials: 'same-origin', cache: 'no-store' }).then(async response => {
                    const data = await response.json().catch(() => ({}));
                    return response.ok ? data : { authenticated: false };
                }),
            ]);
            beatSession = beatResult.status === 'fulfilled' ? beatResult.value : { authenticated: false };
            if (memberResult.status === 'fulfilled' && memberResult.value.authenticated) renderSignedIn(memberResult.value);
            else renderLoggedOut(memberResult.status === 'rejected' ? 'Pit Wall sign-in is temporarily unavailable.' : '');
        }

        button.addEventListener('click', () => {
            modal.hidden = false;
            refresh().finally(() => window.setTimeout(() => content.querySelector('input, a, button')?.focus(), 0));
            if (typeof window.gtag === 'function') window.gtag('event', 'access_hub_open', { location: 'site_header' });
        });
        window.addEventListener('boxbox:member-auth-changed', event => {
            if (event.detail?.source !== 'site-header') refresh();
        });
        refresh();
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initAccessHub, { once: true });
    else initAccessHub();
})();
