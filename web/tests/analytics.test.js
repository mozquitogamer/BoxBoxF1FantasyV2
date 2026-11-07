'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../public/site-init.js'), 'utf8');

function load({ url = 'https://boxboxf1fantasy.com/', mode = 'spa', cookie = '', storage = new Map(), userAgent = 'Mozilla/5.0' } = {}) {
    const listeners = {};
    const context = {
        URL, URLSearchParams,
        location: new URL(url),
        navigator: { userAgent },
        localStorage: {
            getItem: key => storage.get(key),
            setItem: (key, value) => storage.set(key, value),
            removeItem: key => storage.delete(key),
        },
        document: {
            cookie,
            title: 'Test page',
            referrer: 'https://google.com/search?q=private',
            currentScript: { dataset: { gaMode: mode } },
            documentElement: { classList: { add() {} } },
            getElementById() {},
            addEventListener: (name, callback) => { listeners[name] = callback; },
        },
        setTimeout() {},
    };
    context.window = context;
    vm.runInNewContext(source, context);
    return {
        context,
        events: () => context.dataLayer.filter(args => args[0] === 'event'),
        click: href => listeners.click({ target: { closest: () => ({ href }) } }),
        visibility: state => {
            context.document.visibilityState = state;
            listeners.visibilitychange();
        },
    };
}

test('records the landing view before app loading and deduplicates initialization', () => {
    const page = load({ url: 'https://boxboxf1fantasy.com/?utm_source=email&utm_medium=email&token=secret&team=private#optimizer' });
    const api = page.context.BoxBoxAnalytics;
    api.trackTabView('optimizer');
    assert.equal(page.events().length, 1);
    assert.equal(page.events()[0][2].page_location, 'https://boxboxf1fantasy.com/optimizer/?utm_source=email&utm_medium=email');
    assert.equal(page.events()[0][2].page_referrer, 'https://google.com/search');
    api.trackTabView('constructors');
    api.trackTabView('unknown');
    api.trackTabView('constructors');
    assert.equal(page.events().length, 2);
    assert.equal(page.events()[1][2].page_location, 'https://boxboxf1fantasy.com/constructors/');
    assert.equal(page.events()[1][2].page_referrer, page.events()[0][2].page_location);
    assert.equal(page.context.dataLayer.find(args => args[0] === 'config')[2].send_page_view, false);
    assert.equal(page.context.dataLayer.find(args => args[0] === 'config')[2].page_location, page.events()[0][2].page_location);
});

test('static pages use the canonical slash and retain their real title', () => {
    const page = load({ mode: 'page', url: 'https://boxboxf1fantasy.com/tools/team-compare?utm_medium=email&member=secret' });
    assert.equal(page.events()[0][2].page_location, 'https://boxboxf1fantasy.com/tools/team-compare/?utm_medium=email');
    assert.equal(page.events()[0][2].page_title, 'Test page');
    assert.equal(page.events()[0][2].content_group, 'content');
});

test('a background tab returning after session expiry gets a new landing view', () => {
    const page = load({ url: 'https://boxboxf1fantasy.com/?utm_source=email#optimizer' });
    let now = 1000;
    page.context.Date = { now: () => now };
    page.visibility('hidden');
    now += 60 * 1000;
    page.visibility('visible');
    assert.equal(page.events().length, 1);
    page.visibility('hidden');
    now += 31 * 60 * 1000;
    page.visibility('visible');
    page.visibility('visible');
    assert.equal(page.events().length, 2);
    assert.equal(page.events()[1][2].page_location, 'https://boxboxf1fantasy.com/optimizer/');
});

test('counts confirmation once and clears its transient marker before another load', () => {
    const page = load({ cookie: '__Host-boxbox_signup_success=1; other=value' });
    assert.equal(page.events().filter(args => args[1] === 'signup_success').length, 1);
    assert.match(page.context.document.cookie, /Max-Age=0/);
    const refreshed = load({ cookie: page.context.document.cookie });
    assert.equal(refreshed.events().filter(args => args[1] === 'signup_success').length, 0);
});

test('delegated Ko-fi links distinguish membership and support across placements', () => {
    const page = load();
    page.click('https://ko-fi.com/boxboxf1fantasy/tiers');
    page.click('https://ko-fi.com/boxboxf1fantasy');
    page.click('https://ko-fi.com/another-project/tiers');
    assert.deepEqual(Array.from(page.events(), args => args[1]), ['page_view', 'pit_wall_join_click', 'beat_v13_kofi_click']);
});

test('browser exclusion persists across visits and can be reversed', () => {
    const storage = new Map();
    assert.equal(load({ url: 'https://boxboxf1fantasy.com/?analytics=off', storage }).events().length, 0);
    assert.equal(load({ storage }).events().length, 0);
    assert.equal(load({ url: 'https://boxboxf1fantasy.com/?analytics=on', storage }).events().length, 1);
});

test('identified crawler traffic is excluded without country or browser-family exclusions', () => {
    assert.equal(load({ userAgent: 'Mozilla/5.0 (compatible; Googlebot/2.1)' }).events().length, 0);
    assert.equal(load({ userAgent: 'Mozilla/5.0 HeadlessChrome/130' }).events().length, 0);
    assert.equal(load({ userAgent: 'Mozilla/5.0 Edg/130' }).events().length, 1);
});

test('signup initializes on existing static pages without the newer panel marker', async () => {
    const engagement = fs.readFileSync(path.join(__dirname, '../public/engagement.js'), 'utf8')
        .split('/* Site-wide access hub.')[0];
    const handlers = {};
    const form = { addEventListener: (name, handler) => { handlers[name] = handler; }, querySelector: () => ({}) };
    const panel = { hidden: true, querySelector: selector => selector === '.email-updates-form' ? form : {} };
    const context = {
        console, URLSearchParams,
        location: { search: '' },
        document: {
            cookie: '', readyState: 'complete',
            querySelector: () => null,
            getElementById: id => id === 'emailUpdatesPanel' ? panel : null,
        },
        fetch: async url => ({ ok: true, json: async () => url.includes('site_features')
            ? { email_updates: { enabled: true } } : { available: true } }),
    };
    context.window = context;
    vm.runInNewContext(engagement, context);
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(panel.hidden, false);
    assert.equal(typeof handlers.submit, 'function');
});
