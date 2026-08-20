'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');

const subscribe = require('../api/email/subscribe');
const confirm = require('../api/email/confirm');
const {
    beatV13SessionCookie,
    verifyBeatV13SessionCookie,
} = require('../lib/beat-v13-entries');
const { createSubscriptionToken } = require('../lib/email-subscriptions');

const ENTRY_ID = '11111111-1111-4111-8111-111111111111';

function mockResponse() {
    return {
        headers: {},
        statusCode: 200,
        body: null,
        setHeader(name, value) { this.headers[name] = value; },
        getHeader(name) { return this.headers[name]; },
        status(code) { this.statusCode = code; return this; },
        json(value) { this.body = value; return this; },
        send(value) { this.body = value; return this; },
    };
}

function clone(value) {
    return JSON.parse(JSON.stringify(value));
}

function makeFakeProvider(initialEntry = null) {
    const entries = new Map();
    if (initialEntry) entries.set(initialEntry.email_normalized, clone(initialEntry));
    const resendCalls = [];
    const cancellations = [];
    let nextId = 1;

    function response(value, status = 200) {
        return new Response(JSON.stringify(value), {
            status,
            headers: { 'Content-Type': 'application/json' },
        });
    }

    function filterRows(url) {
        const parsed = new URL(url);
        const query = parsed.searchParams;
        let rows = [...entries.values()];
        const email = query.get('email_normalized');
        const id = query.get('id');
        if (email?.startsWith('eq.')) rows = rows.filter(row => row.email_normalized === email.slice(3));
        if (id?.startsWith('eq.')) rows = rows.filter(row => row.id === id.slice(3));
        return { parsed, query, rows };
    }

    function matches(row, key, expression) {
        if (expression === 'is.null') return row[key] === null || row[key] === undefined;
        if (expression?.startsWith('eq.')) return String(row[key] ?? '') === expression.slice(3);
        return true;
    }

    async function fetchMock(url, options = {}) {
        if (url.startsWith('https://project.supabase.test/rest/v1/beat_v13_entries')) {
            const method = options.method || 'GET';
            const { parsed, query, rows } = filterRows(url);
            if (method === 'GET') return response(rows.map(clone));
            const body = options.body ? JSON.parse(options.body) : {};
            if (method === 'POST') {
                if (entries.has(body.email_normalized)) return response([]);
                const entry = {
                    id: ENTRY_ID,
                    email_normalized: body.email_normalized,
                    status: body.status || 'pending',
                    confirmation_sent_at: null,
                    confirmation_provider_id: null,
                    confirmed_at: null,
                    reminder_claimed_at: null,
                    reminder_scheduled_at: null,
                    reminder_provider_id: null,
                    reminder_sent_at: null,
                    withdrawn_at: null,
                    updated_at: new Date().toISOString(),
                };
                entries.set(entry.email_normalized, entry);
                return response([clone(entry)]);
            }
            if (method === 'PATCH') {
                const row = rows[0];
                if (!row) return response([]);
                for (const [key, value] of query.entries()) {
                    if (['select', 'limit', 'order'].includes(key)) continue;
                    if (!matches(row, key, value)) return response([]);
                }
                Object.assign(row, body, { updated_at: new Date().toISOString() });
                entries.set(row.email_normalized, row);
                return response([clone(row)]);
            }
        }

        if (url.startsWith('https://api.resend.com')) {
            const method = options.method || 'GET';
            const parsed = new URL(url);
            const body = options.body ? JSON.parse(options.body) : {};
            resendCalls.push({ url, method, body, headers: options.headers || {} });
            if (parsed.pathname === '/segments/segment_test') return response({ id: 'segment_test' });
            if (parsed.pathname === '/contacts') return response({ id: 'contact_test' });
            if (parsed.pathname.includes('/segments/')) return response({ id: 'segment_test' });
            if (parsed.pathname.endsWith('/cancel')) {
                cancellations.push(parsed.pathname.split('/').at(-2));
                return response({ id: parsed.pathname.split('/').at(-2) });
            }
            if (parsed.pathname === '/emails') {
                return response({ id: `email_${nextId++}` });
            }
        }
        throw new Error(`Unexpected provider request: ${url}`);
    }

    return {
        entries,
        resendCalls,
        cancellations,
        fetchMock,
        get entry() { return [...entries.values()][0] || null; },
    };
}

function withEnv() {
    const keys = [
        'RESEND_API_KEY', 'RESEND_FROM', 'RESEND_SIM_UPDATES_SEGMENT_ID',
        'SUBSCRIPTION_SIGNING_SECRET', 'BEAT_V13_SESSION_SECRET',
        'NEXT_PUBLIC_SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY',
        'SITE_ORIGIN', 'VERCEL_ENV',
    ];
    const previous = Object.fromEntries(keys.map(key => [key, process.env[key]]));
    Object.assign(process.env, {
        RESEND_API_KEY: 're_test',
        RESEND_FROM: 'BoxBox Updates <updates@example.com>',
        RESEND_SIM_UPDATES_SEGMENT_ID: 'segment_test',
        SUBSCRIPTION_SIGNING_SECRET: 'test-secret',
        BEAT_V13_SESSION_SECRET: 'session-test-secret',
        NEXT_PUBLIC_SUPABASE_URL: 'https://project.supabase.test',
        SUPABASE_SERVICE_ROLE_KEY: 'service-test-key',
        SITE_ORIGIN: 'https://boxboxf1fantasy.com',
        VERCEL_ENV: 'production',
    });
    return () => {
        for (const [key, value] of Object.entries(previous)) {
            if (value === undefined) delete process.env[key];
            else process.env[key] = value;
        }
    };
}

function request(email, ip = '127.0.0.1') {
    return {
        method: 'POST',
        headers: { origin: 'https://boxboxf1fantasy.com', host: 'boxboxf1fantasy.com', 'x-real-ip': ip },
        body: { email, consent: true, website: '' },
    };
}

function tokenFromCall(provider) {
    const first = provider.resendCalls.find(call => call.url.endsWith('/emails') && !call.body.scheduled_at);
    const match = String(first?.body?.text || '').match(/https:\/\/[^\s]+\/api\/email\/confirm\?token=([^\s]+)/);
    assert.ok(match, 'confirmation email should include a token URL');
    return decodeURIComponent(match[1]);
}

test('registration status is pending until confirmation, then confirms and cancels its reminder', async () => {
    const restore = withEnv();
    const originalFetch = global.fetch;
    const provider = makeFakeProvider();
    global.fetch = provider.fetchMock;
    try {
        const firstResponse = mockResponse();
        await subscribe(request('Fan@Example.com', '127.0.0.11'), firstResponse);
        assert.equal(firstResponse.statusCode, 202);
        assert.equal(firstResponse.body.entry_status, 'pending');
        assert.match(firstResponse.body.message, /Confirmation email sent/);
        assert.match(firstResponse.body.message, /One more step is required/);
        assert.equal(provider.entry.status, 'pending');
        assert.equal(provider.resendCalls.filter(call => call.url.endsWith('/emails')).length, 2);
        const reminder = provider.resendCalls.find(call => call.body.scheduled_at);
        assert.ok(reminder, 'one reminder should be scheduled');
        assert.equal(reminder.body.scheduled_at, provider.entry.reminder_scheduled_at);
        assert.equal(reminder.body.scheduledAt, undefined, 'raw REST payload must not use the SDK-only camelCase key');
        assert.match(reminder.headers['Idempotency-Key'], /^beat-v13-reminder-/);

        const token = tokenFromCall(provider);
        const confirmationResponse = mockResponse();
        await confirm({ method: 'GET', headers: {}, query: { token } }, confirmationResponse);
        assert.equal(confirmationResponse.statusCode, 303);
        assert.equal(confirmationResponse.headers.Location, '/?v13=confirmed#beatbot');
        assert.match(confirmationResponse.body, /You're officially entered/);
        assert.equal(provider.entry.status, 'confirmed');
        assert.ok(provider.entry.confirmed_at);
        assert.deepEqual(provider.cancellations, [provider.entry.reminder_provider_id.replace('email_', 'email_')]);
        const cookies = confirmationResponse.headers['Set-Cookie'];
        assert.ok(Array.isArray(cookies));
        assert.match(cookies[0], /^__Host-boxbox_beat_v13_session=/);
        assert.match(cookies[0], /HttpOnly/);
        assert.match(cookies[1], /^__Host-boxbox_beat_v13=confirmed/);
    } finally {
        global.fetch = originalFetch;
        restore();
    }
});

test('duplicate submissions reuse the pending row and never schedule a reminder storm', async () => {
    const restore = withEnv();
    const originalFetch = global.fetch;
    const provider = makeFakeProvider();
    global.fetch = provider.fetchMock;
    try {
        const first = mockResponse();
        await subscribe(request('duplicate@example.com', '127.0.0.12'), first);
        const second = mockResponse();
        await subscribe(request('DUPLICATE@example.com', '127.0.0.13'), second);
        assert.equal(first.statusCode, 202);
        assert.equal(second.statusCode, 202);
        assert.equal(provider.resendCalls.filter(call => call.url.endsWith('/emails')).length, 2);
        assert.equal(provider.resendCalls.filter(call => call.body.scheduled_at).length, 1);
        assert.equal(provider.entries.size, 1);
    } finally {
        global.fetch = originalFetch;
        restore();
    }
});

test('not-me cancellation requires an explicit POST, then withdraws and cancels the reminder', async () => {
    const restore = withEnv();
    const originalFetch = global.fetch;
    const provider = makeFakeProvider();
    global.fetch = provider.fetchMock;
    try {
        const registration = mockResponse();
        await subscribe(request('cancel@example.com', '127.0.0.14'), registration);
        const token = tokenFromCall(provider);
        const preview = mockResponse();
        await confirm({ method: 'GET', headers: {}, query: { action: 'cancel', token } }, preview);
        assert.equal(preview.statusCode, 200);
        assert.match(preview.body, /Cancel this pending registration\?/);
        assert.equal(provider.entry.status, 'pending');
        assert.equal(provider.cancellations.length, 0);

        const cancellation = mockResponse();
        await confirm({ method: 'POST', headers: {}, query: { action: 'cancel', token } }, cancellation);
        assert.equal(cancellation.statusCode, 200);
        assert.match(cancellation.body, /Registration cancelled/);
        assert.equal(provider.entry.status, 'withdrawn');
        assert.equal(provider.cancellations.length, 1);
    } finally {
        global.fetch = originalFetch;
        restore();
    }
});

test('entrant session cookie contains only a signed entrant ID', () => {
    const cookie = beatV13SessionCookie(ENTRY_ID, 'session-test-secret', 3600);
    assert.match(cookie, /^__Host-boxbox_beat_v13_session=11111111-1111-4111-8111-111111111111\./);
    assert.match(cookie, /HttpOnly/);
    assert.equal(verifyBeatV13SessionCookie(cookie.split(';')[0].split('=')[1], 'session-test-secret'), ENTRY_ID);
    assert.equal(verifyBeatV13SessionCookie(`${cookie.split(';')[0].split('=')[1]}x`, 'session-test-secret'), null);
    assert.doesNotMatch(cookie, /@/);
});

test('registration UI contains explicit pending, confirmed, retry, and dialog semantics', () => {
    const source = fs.readFileSync(require.resolve('../public/engagement.js'), 'utf8');
    assert.match(source, /Confirmation email sent/);
    assert.match(source, /One more step is required/);
    assert.match(source, /You're officially entered/);
    assert.match(source, /Try again/);
    assert.match(source, /aria-modal/);
});

test('expired confirmation tells the entrant how to request a new link', async () => {
    const restore = withEnv();
    const originalFetch = global.fetch;
    global.fetch = async () => { throw new Error('No provider call should happen for an invalid token'); };
    try {
        const response = mockResponse();
        await confirm({ method: 'GET', headers: {}, query: { token: 'not-a-real-token' } }, response);
        assert.equal(response.statusCode, 400);
        assert.match(response.body, /expired or invalid/);
        assert.match(response.body, /Request a new confirmation link/);
    } finally {
        global.fetch = originalFetch;
        restore();
    }
});
