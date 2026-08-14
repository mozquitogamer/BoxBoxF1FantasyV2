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
        if (title) title.textContent = "You're on the grid";
        if (body) body.textContent = 'This browser remembers that your Beat V13 entry is confirmed. Watch V13’s score and decisions now; final submission instructions arrive by email.';
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
        const panel = document.getElementById('emailUpdatesPanel');
        const form = document.getElementById('emailUpdatesForm');
        const status = document.getElementById('emailUpdatesStatus');
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
                track('beat_v13_registration_started', { location: 'site_footer' });
            } catch (error) {
                setStatus(
                    status,
                    error.message || 'Something went wrong. Please try again in a moment.',
                    'error'
                );
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

/* Registration forms placed at the top of high-intent tabs. */
(function () {
    'use strict';
    const deadline = Date.parse('2026-11-21T04:00:00Z');

    async function initInlineRegistrations() {
        const panels = [...document.querySelectorAll('[data-email-updates]')];
        if (!panels.length) return;
        let config;
        try {
            const configResponse = await fetch('/data/site_features.json', { cache: 'no-store' });
            config = (await configResponse.json()).email_updates;
            if (!config?.enabled) return;
        } catch (_) { return; }

        try {
            const statusResponse = await fetch(config.status_endpoint || '/api/email/status', { cache: 'no-store' });
            const availability = await statusResponse.json().catch(() => ({}));
            if (statusResponse.ok && availability.available === false) return;
        } catch (_) {
            // Static previews do not run the serverless API. Keep the configured
            // form visible so its layout can still be reviewed locally.
        }

        panels.forEach(panel => {
            const form = panel.querySelector('.email-updates-form');
            const status = panel.querySelector('.email-updates-status');
            const submit = form?.querySelector('button[type="submit"]');
            if (!form || !status || !submit) return;
            const submitLabel = submit.textContent;
            panel.hidden = false;
            if (window.BoxBoxFreeAccess.renderConfirmedPanel(panel)) return;
            if (Date.now() >= deadline) {
                form.hidden = true;
                panel.querySelector('.email-updates-eyebrow').textContent = 'Beat V13 registration · Closed';
                panel.querySelector('.email-updates-copy h2').textContent = 'The grid is locked';
                panel.querySelector('.email-updates-copy p').textContent = 'Registered entrants will receive the final submission instructions after the season.';
                return;
            }
            form.addEventListener('submit', async event => {
                event.preventDefault();
                const email = form.elements.email.value.trim();
                const consent = form.elements.consent.checked;
                if (!email || !consent) {
                    status.textContent = 'Enter your email and confirm your free Beat V13 registration.';
                    status.dataset.state = 'error';
                    return;
                }
                submit.disabled = true;
                submit.textContent = 'Sending…';
                status.textContent = '';
                try {
                    const response = await fetch(config.endpoint || '/api/email/subscribe', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ email, consent, website: form.elements.website.value }),
                    });
                    const result = await response.json().catch(() => ({}));
                    if (!response.ok) throw new Error(result.message || 'Sign-up could not be started.');
                    form.reset();
                    status.textContent = result.message || 'Check your inbox and confirm your registration.';
                    status.dataset.state = 'success';
                    if (typeof window.gtag === 'function') window.gtag('event', 'beat_v13_registration_started', { location: panel.dataset.registrationLocation });
                } catch (error) {
                    status.textContent = error.message || 'Something went wrong. Please try again.';
                    status.dataset.state = 'error';
                } finally {
                    submit.disabled = false;
                    submit.textContent = submitLabel;
                }
            });
        });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initInlineRegistrations, { once: true });
    else initInlineRegistrations();
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
        button.textContent = 'My access';
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
        const close = () => { modal.hidden = true; button.focus(); };
        modal.querySelectorAll('[data-pit-wall-close]').forEach(node => node.addEventListener('click', close));
        document.addEventListener('keydown', event => { if (event.key === 'Escape' && !modal.hidden) close(); });

        function beatConfirmed() {
            return window.BoxBoxFreeAccess?.isBeatV13Confirmed() === true;
        }

        function freeAccessCard() {
            const confirmed = beatConfirmed();
            return `<section class="access-hub-card free-access-card">
                <div class="access-hub-card-head"><div><span class="access-tier-label free">Always free</span><h3>Free BoxBox access</h3></div><strong class="access-state active">Active</strong></div>
                <p>No password or payment is needed for predictions, simulations, V13’s score, the optimizer, Transfer Advisor, planners or the accuracy record.</p>
                <ul><li>Use every public fantasy tool</li><li>Follow every V13 decision and score</li><li>Enter Beat V13 and receive general updates by email</li></ul>
                <div class="access-entry-state ${confirmed ? 'confirmed' : ''}"><span>Beat V13 entry</span><strong>${confirmed ? '✓ Confirmed on this browser' : 'Free email confirmation'}</strong></div>
                <a class="access-hub-action secondary" href="/?v13=dashboard#beatbot">${confirmed ? 'Open my challenge dashboard' : 'View challenge &amp; standings'}</a>
            </section>`;
        }

        function pitWallBenefits() {
            return `<ul class="pit-wall-benefit-list"><li>Your official F1 team remembered and synced</li><li>Personalized transfer suggestions for your lineup</li><li>Early-thoughts and post-FP updates delivered automatically</li></ul>`;
        }

        function accessHeader(pitState) {
            const confirmed = beatConfirmed();
            return `<span class="pit-wall-login-eyebrow">Your BoxBox access</span><h2 id="pitWallLoginTitle">Free tools first. Pit Wall when you want convenience.</h2><p class="access-hub-intro">Beat V13 registration is a free email entry. Pit Wall is the separate $5/month account with a password and personalized member tools.</p><div class="access-status-strip"><span><small>Public tools</small><strong>Active</strong></span><span><small>Beat V13</small><strong>${confirmed ? 'Registered' : 'Status not saved here'}</strong></span><span><small>Pit Wall</small><strong>${pitState}</strong></span></div>`;
        }

        function updateHeaderButton(session) {
            const active = session?.authenticated && session.entitlement?.active === true;
            button.classList.toggle('active', active);
            if (active) button.textContent = 'Pit Wall active';
            else if (session?.authenticated) button.textContent = 'Pit Wall · Signed in';
            else if (beatConfirmed()) button.textContent = 'Beat V13 ✓ · My access';
            else button.textContent = 'My access';
            button.setAttribute('aria-label', `${button.textContent}. Open access details.`);
        }

        function renderLoggedOut(message = '') {
            updateHeaderButton(null);
            content.innerHTML = `${accessHeader('Not signed in')}<div class="access-hub-grid">${freeAccessCard()}<section class="access-hub-card pit-wall-access-card"><div class="access-hub-card-head"><div><span class="access-tier-label paid">$5/month · Ko-fi</span><h3>Pit Wall membership</h3></div><strong class="access-state">Optional upgrade</strong></div><p>Everything free stays free. Pit Wall removes the weekly admin by remembering your real team and bringing the relevant advice to you.</p>${pitWallBenefits()}<details class="pit-wall-member-signin"${message ? ' open' : ''}><summary><span>Already a member?</span><strong>Sign in</strong></summary><div class="pit-wall-member-signin-body"><form id="sitePitWallSignIn"><label for="sitePitWallEmail">Ko-fi membership email</label><input id="sitePitWallEmail" name="email" type="email" autocomplete="email" placeholder="you@example.com" required><label for="sitePitWallPassword">Pit Wall password</label><input id="sitePitWallPassword" name="password" type="password" autocomplete="current-password" minlength="8" maxlength="128" required><button type="submit">Sign in to Pit Wall</button></form><p class="pit-wall-login-status" role="status" aria-live="polite">${escapeHtml(message)}</p><div class="pit-wall-login-links"><button type="button" class="pit-wall-login-reset" id="sitePitWallReset">Create or reset password</button><a class="pit-wall-login-kofi" href="https://ko-fi.com/boxboxf1fantasy/tiers" target="_blank" rel="noopener">Join Pit Wall on Ko-fi</a></div></div></details></section></div>`;
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
            content.innerHTML = `${accessHeader(pitState)}<div class="access-hub-grid">${freeAccessCard()}<section class="access-hub-card pit-wall-access-card ${active ? 'is-active' : ''}"><div class="access-hub-card-head"><div><span class="access-tier-label paid">Pit Wall account</span><h3>${escapeHtml(session.email || 'Signed in')}</h3></div><strong class="access-state ${active ? 'active' : ''}">${active ? '✓ Active' : 'Membership inactive'}</strong></div><p>${active ? 'Your paid convenience tools are unlocked and connected to this account.' : 'Your login works, but the Ko-fi membership linked to it is not currently active.'}</p>${pitWallBenefits()}<div class="pit-wall-login-actions">${active ? '<a href="/?pitwall=1#optimizer">Open Transfer Advisor</a>' : '<a href="https://ko-fi.com/boxboxf1fantasy/tiers" target="_blank" rel="noopener">Renew on Ko-fi</a>'}<button type="button" id="sitePitWallSignOut">Sign out</button></div></section></div>`;
            content.querySelector('#sitePitWallSignOut')?.addEventListener('click', async () => {
                await memberRequest('/api/members/sign-out/', { method: 'POST' }).catch(() => null);
                renderLoggedOut('Signed out.');
                window.dispatchEvent(new CustomEvent('boxbox:member-auth-changed', { detail: { source: 'site-header' } }));
            });
        }

        async function refresh() {
            try {
                const session = await memberRequest('/api/members/session/');
                if (session.authenticated) renderSignedIn(session);
                else renderLoggedOut();
            } catch (_) { renderLoggedOut('Pit Wall sign-in is temporarily unavailable.'); }
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
