'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const signIn = require('../api/members/sign-in');
const passwordReset = require('../api/members/password-reset');
const updatePassword = require('../api/members/password');

function response(body, status = 200) {
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function mockRes() {
    return {
        statusCode: 200,
        headers: {},
        body: null,
        setHeader(name, value) { this.headers[name] = value; },
        getHeader(name) { return this.headers[name]; },
        status(code) { this.statusCode = code; return this; },
        json(value) { this.body = value; return this; },
        send(value) { this.body = value; return this; },
    };
}

function memberReq(body, cookie = '') {
    return {
        method: 'POST',
        body,
        headers: {
            origin: 'https://boxboxf1fantasy.com',
            host: 'boxboxf1fantasy.com',
            'x-forwarded-proto': 'https',
            cookie,
        },
    };
}

function configure() {
    const names = [
        'NEXT_PUBLIC_SUPABASE_URL', 'NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY',
        'SUPABASE_SERVICE_ROLE_KEY', 'SITE_ORIGIN', 'VERCEL_ENV',
        'RESEND_API_KEY', 'RESEND_FROM',
    ];
    const previous = Object.fromEntries(names.map(name => [name, process.env[name]]));
    Object.assign(process.env, {
        NEXT_PUBLIC_SUPABASE_URL: 'https://project.supabase.test',
        NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'public-test-key',
        SUPABASE_SERVICE_ROLE_KEY: 'service-test-key',
        SITE_ORIGIN: 'https://boxboxf1fantasy.com',
        VERCEL_ENV: 'production',
        RESEND_API_KEY: 'resend-test-key',
        RESEND_FROM: 'Pit Wall <members@example.com>',
    });
    return () => {
        for (const [name, value] of Object.entries(previous)) {
            if (value === undefined) delete process.env[name];
            else process.env[name] = value;
        }
    };
}

test('signs an active member in with a password and secure session cookies', async () => {
    const restoreEnv = configure();
    const originalFetch = global.fetch;
    const calls = [];
    global.fetch = async (url, options = {}) => {
        calls.push({ url: String(url), options });
        if (String(url).endsWith('/auth/v1/token?grant_type=password')) {
            return response({
                access_token: 'access-token', refresh_token: 'refresh-token', expires_in: 3600,
                user: { id: 'member-1', email: 'member@example.com' },
            });
        }
        if (String(url).includes('/rest/v1/member_entitlements?')) {
            return response([{ status: 'active', current_period_end: '2099-01-01T00:00:00Z' }]);
        }
        throw new Error(`Unexpected request: ${url}`);
    };
    try {
        const res = mockRes();
        await signIn(memberReq({ email: 'Member@Example.com', password: 'correct horse battery staple' }), res);
        assert.equal(res.statusCode, 200);
        assert.equal(res.body.ok, true);
        assert.match(res.headers['Set-Cookie'][0], /^boxbox_member_access=access-token;.*HttpOnly.*Secure.*SameSite=Lax/);
        assert.match(res.headers['Set-Cookie'][1], /^boxbox_member_refresh=refresh-token;.*HttpOnly.*Secure.*SameSite=Lax/);
        const credentials = JSON.parse(calls[0].options.body);
        assert.deepEqual(credentials, { email: 'member@example.com', password: 'correct horse battery staple' });
    } finally {
        global.fetch = originalFetch;
        restoreEnv();
    }
});

test('creates a recovery email only for an active member', async () => {
    const restoreEnv = configure();
    const originalFetch = global.fetch;
    const calls = [];
    global.fetch = async (url, options = {}) => {
        const target = String(url);
        calls.push({ url: target, options });
        if (target.includes('/rest/v1/member_profiles?') && (options.method || 'GET') === 'GET') {
            return response([{ user_id: 'member-1', email: 'member@example.com', magic_link_sent_at: null }]);
        }
        if (target.includes('/rest/v1/member_entitlements?')) {
            return response([{ status: 'active', current_period_end: '2099-01-01T00:00:00Z' }]);
        }
        if (target.endsWith('/auth/v1/admin/generate_link')) {
            return response({ properties: { hashed_token: 'recovery-token' } });
        }
        if (target === 'https://api.resend.com/emails') return response({ id: 'email-1' });
        if (target.includes('/rest/v1/member_profiles?') && options.method === 'PATCH') return response(null);
        throw new Error(`Unexpected request: ${url}`);
    };
    try {
        const res = mockRes();
        await passwordReset(memberReq({ email: 'member@example.com' }), res);
        assert.equal(res.statusCode, 202);
        assert.equal(res.body.ok, true);
        const generate = calls.find(call => call.url.endsWith('/auth/v1/admin/generate_link'));
        assert.equal(JSON.parse(generate.options.body).type, 'recovery');
        const email = calls.find(call => call.url === 'https://api.resend.com/emails');
        assert.match(JSON.parse(email.options.body).text, /type=recovery/);
        assert.ok(email.options.headers['Idempotency-Key'].startsWith('pit-wall-password-'));
    } finally {
        global.fetch = originalFetch;
        restoreEnv();
    }
});

test('sets a new password from an authenticated recovery session', async () => {
    const restoreEnv = configure();
    const originalFetch = global.fetch;
    const calls = [];
    global.fetch = async (url, options = {}) => {
        calls.push({ url: String(url), options });
        if (String(url).endsWith('/auth/v1/user') && (options.method || 'GET') === 'GET') {
            return response({ id: 'member-1', email: 'member@example.com' });
        }
        if (String(url).endsWith('/auth/v1/user') && options.method === 'PUT') {
            return response({ id: 'member-1' });
        }
        throw new Error(`Unexpected request: ${url}`);
    };
    try {
        const res = mockRes();
        await updatePassword(memberReq(
            { password: 'a new secure password' },
            'boxbox_member_access=recovery-access; boxbox_member_refresh=recovery-refresh',
        ), res);
        assert.equal(res.statusCode, 200);
        const update = calls.find(call => call.options.method === 'PUT');
        assert.deepEqual(JSON.parse(update.options.body), { password: 'a new secure password' });
        assert.equal(update.options.headers.Authorization, 'Bearer recovery-access');
    } finally {
        global.fetch = originalFetch;
        restoreEnv();
    }
});
