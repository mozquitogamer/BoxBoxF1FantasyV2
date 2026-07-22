/* ============================================================
   BoxBoxF1Fantasy — email updates and restrained monetization UI
   ============================================================ */

(function () {
    'use strict';

    const CONFIG_URL = '/data/site_features.json';

    function track(eventName, params = {}) {
        if (typeof window.gtag === 'function') {
            window.gtag('event', eventName, params);
        }
    }

    function setStatus(element, message, state) {
        element.textContent = message;
        element.dataset.state = state || '';
    }

    function initEmailUpdates(config) {
        const panel = document.getElementById('emailUpdatesPanel');
        const form = document.getElementById('emailUpdatesForm');
        const status = document.getElementById('emailUpdatesStatus');
        const submit = form?.querySelector('button[type="submit"]');

        if (!config?.enabled || !panel || !form || !status || !submit) return;

        panel.hidden = false;
        form.addEventListener('submit', async (event) => {
            event.preventDefault();

            const email = form.elements.email.value.trim();
            const consent = form.elements.consent.checked;
            const website = form.elements.website.value;

            if (!email || !consent) {
                setStatus(status, 'Enter your email and confirm that you want update alerts.', 'error');
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
                    result.message || 'Check your inbox and confirm your subscription.',
                    'success'
                );
                track('email_updates_signup_started', { location: 'site_footer' });
            } catch (error) {
                setStatus(
                    status,
                    error.message || 'Something went wrong. Please try again in a moment.',
                    'error'
                );
            } finally {
                submit.disabled = false;
                submit.textContent = 'Notify me';
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
            initEmailUpdates(config.email_updates);
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
