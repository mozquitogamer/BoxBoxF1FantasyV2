'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const {
    BEAT_V13_REGISTRATION_DEADLINE,
    createSubscriptionToken,
    isBeatV13RegistrationOpen,
    isValidEmail,
    normalizeEmail,
    verifySubscriptionToken,
} = require('../lib/email-subscriptions');
const subscribeHandler = require('../api/email/subscribe');
const confirmHandler = require('../api/email/confirm');
const statusHandler = require('../api/email/status');
const { ensureSegment } = require('../lib/resend-segments');

function mockResponse() {
    return {
        headers: {},
        statusCode: 200,
        body: null,
        setHeader(name, value) { this.headers[name] = value; },
        status(code) { this.statusCode = code; return this; },
        json(value) { this.body = value; return this; },
        send(value) { this.body = value; return this; },
    };
}

function withEmailEnv() {
    const previous = {};
    const values = {
        RESEND_API_KEY: 're_test',
        RESEND_FROM: 'BoxBox Updates <updates@example.com>',
        RESEND_SIM_UPDATES_SEGMENT_ID: 'segment_test',
        SUBSCRIPTION_SIGNING_SECRET: 'test-secret',
        SITE_ORIGIN: 'https://boxboxf1fantasy.com',
        VERCEL_ENV: 'production',
    };
    for (const [key, value] of Object.entries(values)) {
        previous[key] = process.env[key];
        process.env[key] = value;
    }
    return () => {
        for (const [key, value] of Object.entries(previous)) {
            if (value === undefined) delete process.env[key];
            else process.env[key] = value;
        }
    };
}

test('normalizes and validates subscriber addresses', () => {
    assert.equal(normalizeEmail('  FAN@Example.COM '), 'fan@example.com');
    assert.equal(isValidEmail('fan@example.com'), true);
    assert.equal(isValidEmail('not-an-email'), false);
});

test('passes Resend idempotency headers through to the provider', async () => {
    const { resendRequest } = require('../lib/email-subscriptions');
    const originalFetch = global.fetch;
    let receivedHeaders;
    global.fetch = async (_url, options) => {
        receivedHeaders = options.headers;
        return new Response(JSON.stringify({ id: 'email_test' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
        });
    };
    try {
        await resendRequest('/emails', 're_test', {
            method: 'POST',
            headers: { 'Idempotency-Key': 'stable-email-key' },
            body: { to: ['fan@example.com'] },
        });
        assert.equal(receivedHeaders['Idempotency-Key'], 'stable-email-key');
    } finally {
        global.fetch = originalFetch;
    }
});

test('opens registration before the Round 22 lock and closes it at the deadline', () => {
    const deadline = Date.parse(BEAT_V13_REGISTRATION_DEADLINE);
    assert.equal(isBeatV13RegistrationOpen(deadline - 1), true);
    assert.equal(isBeatV13RegistrationOpen(deadline), false);
});

test('creates and verifies a signed subscription token', () => {
    const now = Date.parse('2026-07-21T10:00:00Z');
    const token = createSubscriptionToken('Fan@Example.com', 'test-secret', 48, now);
    assert.deepEqual(verifySubscriptionToken(token, 'test-secret', now + 1000), {
        email: 'fan@example.com',
        exp: now + 48 * 60 * 60 * 1000,
    });
});

test('rejects tampered and expired subscription tokens', () => {
    const now = Date.parse('2026-07-21T10:00:00Z');
    const token = createSubscriptionToken('fan@example.com', 'test-secret', 1, now);
    assert.equal(verifySubscriptionToken(`${token}x`, 'test-secret', now), null);
    assert.equal(verifySubscriptionToken(token, 'wrong-secret', now), null);
    assert.equal(verifySubscriptionToken(token, 'test-secret', now + 61 * 60 * 1000), null);
});

test('subscribe handler sends only a confirmation email', async () => {
    const restoreEnv = withEmailEnv();
    const originalFetch = global.fetch;
    const calls = [];
    global.fetch = async (url, options) => {
        calls.push({ url, options });
        return new Response(JSON.stringify({ id: 'email_test' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
        });
    };

    try {
        const req = {
            method: 'POST',
            headers: {
                origin: 'https://boxboxf1fantasy.com',
                host: 'boxboxf1fantasy.com',
            },
            body: { email: 'Fan@Example.com', consent: true, website: '' },
        };
        const res = mockResponse();
        await subscribeHandler(req, res);

        assert.equal(res.statusCode, 202);
        assert.equal(res.body.ok, true);
        assert.equal(calls.length, 1);
        assert.equal(calls[0].url, 'https://api.resend.com/emails');
        assert.match(calls[0].options.headers['Idempotency-Key'], /^beat-v13-confirm-[a-f0-9]{32}$/);
        const payload = JSON.parse(calls[0].options.body);
        assert.deepEqual(payload.to, ['fan@example.com']);
        assert.equal(payload.subject, 'Confirm your free Beat V13 registration');
        assert.match(payload.text, /\/api\/email\/confirm\?token=/);
    } finally {
        global.fetch = originalFetch;
        restoreEnv();
    }
});

test('status handler hides sign-up when delivery is not configured', () => {
    const keys = [
        'RESEND_API_KEY',
        'RESEND_FROM',
        'RESEND_SIM_UPDATES_SEGMENT_ID',
        'SUBSCRIPTION_SIGNING_SECRET',
    ];
    const previous = Object.fromEntries(keys.map(key => [key, process.env[key]]));
    for (const key of keys) delete process.env[key];

    try {
        const res = mockResponse();
        statusHandler({ method: 'GET' }, res);
        assert.equal(res.statusCode, 200);
        assert.deepEqual(res.body, { available: false });
    } finally {
        for (const [key, value] of Object.entries(previous)) {
            if (value === undefined) delete process.env[key];
            else process.env[key] = value;
        }
    }
});

test('status handler exposes sign-up after delivery is configured', () => {
    const restoreEnv = withEmailEnv();
    try {
        const res = mockResponse();
        statusHandler({ method: 'GET' }, res);
        assert.equal(res.statusCode, 200);
        assert.deepEqual(res.body, { available: true });
    } finally {
        restoreEnv();
    }
});

test('confirm handler adds a verified address to the alert segment', async () => {
    const restoreEnv = withEmailEnv();
    const originalFetch = global.fetch;
    const calls = [];
    global.fetch = async (url, options = {}) => {
        calls.push({ url, options });
        if (url === 'https://api.resend.com/segments/segment_test') {
            return new Response(JSON.stringify({ id: 'segment_test', name: 'Beat V13 Updates' }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            });
        }
        return new Response(JSON.stringify({ id: 'contact_test' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
        });
    };

    try {
        const token = createSubscriptionToken('fan@example.com', 'test-secret', 48);
        const req = { method: 'GET', headers: {}, query: { token } };
        const res = mockResponse();
        await confirmHandler(req, res);

        assert.equal(res.statusCode, 200);
        assert.match(res.body, /registered/);
        assert.equal(calls.length, 2);
        assert.equal(calls[0].url, 'https://api.resend.com/segments/segment_test');
        assert.equal(calls[1].url, 'https://api.resend.com/contacts');
        const payload = JSON.parse(calls[1].options.body);
        assert.equal(payload.email, 'fan@example.com');
        assert.deepEqual(payload.segments, [{ id: 'segment_test' }]);
    } finally {
        global.fetch = originalFetch;
        restoreEnv();
    }
});

test('recreates a missing configured segment by name', async () => {
    const previousKey = process.env.RESEND_API_KEY;
    process.env.RESEND_API_KEY = 're_test';
    const originalFetch = global.fetch;
    const calls = [];
    global.fetch = async (url, options = {}) => {
        calls.push({ url, options });
        if (url.endsWith('/segments/deleted_segment')) {
            return new Response(JSON.stringify({ message: 'Segment not found' }), {
                status: 404,
                headers: { 'Content-Type': 'application/json' },
            });
        }
        if (url.endsWith('/segments') && (options.method || 'GET') === 'GET') {
            return new Response(JSON.stringify({ data: [] }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            });
        }
        return new Response(JSON.stringify({ id: 'new_segment', name: 'Recovery Test Segment' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
        });
    };

    try {
        assert.equal(await ensureSegment('Recovery Test Segment', 'deleted_segment'), 'new_segment');
        assert.deepEqual(calls.map(call => call.url), [
            'https://api.resend.com/segments/deleted_segment',
            'https://api.resend.com/segments',
            'https://api.resend.com/segments',
        ]);
    } finally {
        global.fetch = originalFetch;
        if (previousKey === undefined) delete process.env.RESEND_API_KEY;
        else process.env.RESEND_API_KEY = previousKey;
    }
});
