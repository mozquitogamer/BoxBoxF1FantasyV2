'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const {
    createSubscriptionToken,
    isValidEmail,
    normalizeEmail,
    verifySubscriptionToken,
} = require('../lib/email-subscriptions');
const subscribeHandler = require('../api/email/subscribe');
const confirmHandler = require('../api/email/confirm');

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
        const payload = JSON.parse(calls[0].options.body);
        assert.deepEqual(payload.to, ['fan@example.com']);
        assert.match(payload.text, /\/api\/email\/confirm\?token=/);
    } finally {
        global.fetch = originalFetch;
        restoreEnv();
    }
});

test('confirm handler adds a verified address to the alert segment', async () => {
    const restoreEnv = withEmailEnv();
    const originalFetch = global.fetch;
    const calls = [];
    global.fetch = async (url, options) => {
        calls.push({ url, options });
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
        assert.match(res.body, /on the grid/);
        assert.equal(calls.length, 1);
        assert.equal(calls[0].url, 'https://api.resend.com/contacts');
        const payload = JSON.parse(calls[0].options.body);
        assert.equal(payload.email, 'fan@example.com');
        assert.deepEqual(payload.segments, [{ id: 'segment_test' }]);
    } finally {
        global.fetch = originalFetch;
        restoreEnv();
    }
});
