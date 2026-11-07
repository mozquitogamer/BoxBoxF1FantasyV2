'use strict';

document.documentElement.classList.add('js-enabled');
window.setTimeout(() => {
    document.getElementById('driverLiveRegion')?.classList.remove('is-hydrating');
}, 8000);

(function () {
    const measurementId = 'G-T3HS76FJ7W';
    const mode = document.currentScript?.dataset.gaMode || 'page';
    const params = new URLSearchParams(location.search);
    let excluded = /bot\b|crawler|spider|HeadlessChrome|Lighthouse|PageSpeed/i.test(navigator.userAgent || '');
    try {
        if (params.get('analytics') === 'off') localStorage.setItem('boxbox_analytics_disabled', '1');
        if (params.get('analytics') === 'on') localStorage.removeItem('boxbox_analytics_disabled');
        excluded = excluded || localStorage.getItem('boxbox_analytics_disabled') === '1';
    } catch (_) {
        excluded = excluded || params.get('analytics') === 'off';
    }
    window[`ga-disable-${measurementId}`] = excluded;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function gtag() {
        if (!window[`ga-disable-${measurementId}`]) window.dataLayer.push(arguments);
    };

    // Preserve campaigns without sending private team links or authentication tokens.
    const campaign = new URLSearchParams();
    for (const key of ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term']) {
        if (params.has(key)) campaign.set(key, params.get(key));
    }
    const titles = {
        drivers: 'Drivers', constructors: 'Constructors', optimizer: 'Lineup Optimizer',
        beatbot: 'Beat V13', analysis: 'Analysis', season: 'Season', h2h: 'H2H',
        accuracy: 'Accuracy', deepdive: 'Race Deep Dive', videos: 'Videos',
        articles: 'Articles', changelog: 'Changelog', about: 'About',
    };
    let previousLocation = '';
    try {
        const referrer = new URL(document.referrer);
        previousLocation = referrer.origin + referrer.pathname;
    } catch (_) { /* Direct arrivals have no referrer. */ }
    let previousTab = null;
    let firstView = true;

    function pageView(path, title, screen) {
        const query = firstView && campaign.size ? `?${campaign}` : '';
        const pageLocation = location.origin + path + query;
        const fields = {
            page_location: pageLocation,
            page_referrer: previousLocation,
            page_title: title,
            content_group: mode === 'spa' ? 'app' : 'content',
        };
        // Automatic engagement and form events inherit the current screen.
        window.gtag('set', fields);
        window.gtag('event', 'page_view', { ...fields, screen_name: screen });
        previousLocation = pageLocation;
        firstView = false;
    }

    function trackTabView(tabName) {
        if (!Object.hasOwn(titles, tabName) || previousTab === tabName) return;
        pageView(`/${tabName}/`, `${titles[tabName]} | BoxBoxF1Fantasy`, tabName);
        previousTab = tabName;
    }

    window.BoxBoxAnalytics = Object.freeze({ trackTabView });
    window.gtag('js', new Date());
    window.gtag('config', measurementId, { send_page_view: false });
    if (mode === 'spa') {
        const tab = location.hash.slice(1);
        trackTabView(Object.hasOwn(titles, tab) ? tab : 'drivers');
    } else {
        const path = location.pathname.replace(/\/+$/, '') + '/';
        pageView(path, document.title, path);
    }

    // The server sets this once after the first successful email confirmation.
    // Consume it before slower app initialization or another page load.
    if (document.cookie.split(';').some(cookie => cookie.trim() === '__Host-boxbox_signup_success=1')) {
        document.cookie = '__Host-boxbox_signup_success=; Path=/; Max-Age=0; Secure; SameSite=Lax';
        window.gtag('event', 'signup_success', { method: 'email', signup_type: 'beat_v13' });
    }

    // A long-lived background tab can start a new session without a navigation.
    // Give it a landing view when it returns after GA4's default inactivity window.
    let backgroundAt = null;
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') {
            backgroundAt = Date.now();
            return;
        }
        if (document.visibilityState !== 'visible' || backgroundAt === null) return;
        const sessionExpired = Date.now() - backgroundAt >= 30 * 60 * 1000;
        backgroundAt = null;
        if (!sessionExpired) return;
        if (mode === 'spa') {
            pageView(`/${previousTab}/`, `${titles[previousTab]} | BoxBoxF1Fantasy`, previousTab);
        } else {
            const path = location.pathname.replace(/\/+$/, '') + '/';
            pageView(path, document.title, path);
        }
    });

    // Delegation also measures support links rendered later in member panels.
    document.addEventListener('click', event => {
        const link = event.target.closest?.('a[href]');
        if (!link) return;
        const url = new URL(link.href, location.href);
        if (url.hostname !== 'ko-fi.com' || !/^\/boxboxf1fantasy(?:\/|$)/.test(url.pathname)) return;
        const join = /^\/boxboxf1fantasy\/tiers(?:\/|$)/.test(url.pathname);
        window.gtag('event', join ? 'pit_wall_join_click' : 'beat_v13_kofi_click', {
            location: previousTab || location.pathname,
            link_type: join ? 'membership' : 'support',
            transport_type: 'beacon',
        });
    });
})();
