/* ============================================================
   BoxBoxF1Fantasy — email updates and restrained monetization UI
   ============================================================ */

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

        if (Date.now() >= BEAT_V13_REGISTRATION_DEADLINE) {
            panel.hidden = false;
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
            panel.hidden = false;
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
                    submit.textContent = 'Register free';
                }
            });
        });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initInlineRegistrations, { once: true });
    else initInlineRegistrations();
})();

/* Site-wide Pit Wall account entry point. Shared by the SPA and SEO pages. */
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
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            "'": '&#39;',
            '"': '&quot;',
        })[character]);
    }

    function initPitWallAccount() {
        if (document.getElementById('pitWallAccountButton')) return;

        const button = document.createElement('button');
        button.id = 'pitWallAccountButton';
        button.className = 'pit-wall-account-button';
        button.type = 'button';
        button.textContent = 'Pit Wall login';
        button.setAttribute('aria-haspopup', 'dialog');
        const host = document.querySelector('.header-right') || document.querySelector('.topbar .wrap');
        if (host) host.appendChild(button);
        else { button.classList.add('floating'); document.body.appendChild(button); }

        const modal = document.createElement('div');
        modal.className = 'pit-wall-login-modal';
        modal.hidden = true;
        modal.innerHTML = `<div class="pit-wall-login-backdrop" data-pit-wall-close></div><section class="pit-wall-login-dialog" role="dialog" aria-modal="true" aria-labelledby="pitWallLoginTitle"><button class="pit-wall-login-close" type="button" data-pit-wall-close aria-label="Close">&times;</button><div id="pitWallLoginContent"><p>Loading Pit Wall&hellip;</p></div></section>`;
        document.body.appendChild(modal);
        const content = modal.querySelector('#pitWallLoginContent');
        const close = () => { modal.hidden = true; button.focus(); };
        modal.querySelectorAll('[data-pit-wall-close]').forEach(node => node.addEventListener('click', close));
        document.addEventListener('keydown', event => { if (event.key === 'Escape' && !modal.hidden) close(); });

        function renderLoggedOut(message = '') {
            button.textContent = 'Pit Wall login';
            content.innerHTML = `<span class="pit-wall-login-eyebrow">Member convenience</span><h2 id="pitWallLoginTitle">Sign in to the Pit Wall</h2><p>Use the email connected to your Ko-fi membership or complimentary account. We will send a secure, one-use sign-in link.</p><form id="sitePitWallSignIn"><label for="sitePitWallEmail">Email address</label><div><input id="sitePitWallEmail" name="email" type="email" autocomplete="email" placeholder="you@example.com" required><button type="submit">Email my sign-in link</button></div></form><p class="pit-wall-login-status" role="status" aria-live="polite">${escapeHtml(message)}</p><a class="pit-wall-login-kofi" href="https://ko-fi.com/boxboxf1fantasy/tiers" target="_blank" rel="noopener">Join the Pit Wall on Ko-fi</a>`;
            content.querySelector('#sitePitWallSignIn')?.addEventListener('submit', async event => {
                event.preventDefault();
                const form = event.currentTarget;
                const submit = form.querySelector('button');
                const status = content.querySelector('.pit-wall-login-status');
                submit.disabled = true;
                status.textContent = 'Preparing your secure link…';
                try {
                    const result = await memberRequest('/api/members/sign-in/', { method: 'POST', body: { email: form.elements.email.value.trim() } });
                    status.textContent = result.message;
                    status.dataset.state = 'success';
                    form.reset();
                } catch (error) {
                    status.textContent = error.message;
                    status.dataset.state = 'error';
                } finally { submit.disabled = false; }
            });
        }

        function renderSignedIn(session) {
            button.textContent = 'Pit Wall';
            const active = session.entitlement?.active === true;
            content.innerHTML = `<span class="pit-wall-login-eyebrow">Pit Wall account</span><h2 id="pitWallLoginTitle">${escapeHtml(session.email || 'Signed in')}</h2><p>${active ? 'Your membership is active. Open the Transfer Advisor to manage your saved and official F1 Fantasy teams.' : 'You are signed in, but this membership is not currently active.'}</p><div class="pit-wall-login-actions"><a href="/?pitwall=1#optimizer">Open my Pit Wall</a><button type="button" id="sitePitWallSignOut">Sign out</button></div>`;
            content.querySelector('#sitePitWallSignOut')?.addEventListener('click', async () => {
                await memberRequest('/api/members/sign-out/', { method: 'POST' }).catch(() => null);
                renderLoggedOut('Signed out.');
            });
        }

        async function refresh() {
            try {
                const session = await memberRequest('/api/members/session/');
                if (session.authenticated) renderSignedIn(session);
                else renderLoggedOut();
            } catch (_) { renderLoggedOut('Sign-in is temporarily unavailable.'); }
        }

        button.addEventListener('click', () => {
            modal.hidden = false;
            refresh().finally(() => window.setTimeout(() => content.querySelector('input, a, button')?.focus(), 0));
            if (typeof window.gtag === 'function') window.gtag('event', 'pit_wall_signin_click', { location: 'site_header' });
        });
        refresh();
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initPitWallAccount, { once: true });
    else initPitWallAccount();
})();
