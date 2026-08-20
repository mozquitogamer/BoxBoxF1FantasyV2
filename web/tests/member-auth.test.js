'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const signIn = require('../api/members/sign-in');
const password = require('../api/members/password');
const callback = require('../api/members/callback');

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

function testJwt(payload) {
    const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
    const body = Buffer.from(JSON.stringify(payload)).toString('base64url');
    return `${header}.${body}.test-signature`;
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
        assert.match(res.headers['Set-Cookie'][0], /^__Host-boxbox_member_access=access-token;.*HttpOnly.*Secure.*SameSite=Strict/);
        assert.match(res.headers['Set-Cookie'][1], /^__Host-boxbox_member_refresh=refresh-token;.*HttpOnly.*Secure.*SameSite=Strict/);
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
        await password(memberReq({ action: 'reset', email: 'member@example.com' }), res);
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

test('sets a new password using the signed grant from a real-shaped recovery callback', async () => {
    const restoreEnv = configure();
    const originalFetch = global.fetch;
    const calls = [];
    const recoveryAccess = testJwt({
        sub: 'member-1',
        session_id: 'recovery-session-1',
        // Supabase POST /verify currently records this flow as OTP.
        amr: [{ method: 'otp', timestamp: Math.floor(Date.now() / 1000) }],
    });
    global.fetch = async (url, options = {}) => {
        calls.push({ url: String(url), options });
        if (String(url).endsWith('/auth/v1/verify') && options.method === 'POST') {
            return response({
                access_token: recoveryAccess,
                refresh_token: 'recovery-refresh',
                expires_in: 3600,
                user: { id: 'member-1', email: 'member@example.com' },
            });
        }
        if (String(url).endsWith('/auth/v1/user') && (options.method || 'GET') === 'GET') {
            return response({ id: 'member-1', email: 'member@example.com' });
        }
        if (String(url).endsWith('/auth/v1/user') && options.method === 'PUT') {
            return response({ id: 'member-1' });
        }
        if (String(url).endsWith('/auth/v1/logout') && options.method === 'POST') return response({});
        throw new Error(`Unexpected request: ${url}`);
    };
    try {
        const callbackRes = mockRes();
        await callback({ method: 'GET', query: { token_hash: 'recovery-token', type: 'recovery' } }, callbackRes);
        assert.equal(callbackRes.statusCode, 302);
        assert.equal(callbackRes.headers.Location, 'https://boxboxf1fantasy.com/?member=password#optimizer');
        assert.ok(callbackRes.headers['Set-Cookie'].some(value => /^__Host-boxbox_member_access=.*SameSite=Lax/.test(value)));
        assert.ok(callbackRes.headers['Set-Cookie'].some(value => /^__Host-boxbox_member_recovery=.*SameSite=Lax/.test(value)));

        const browserCookie = callbackRes.headers['Set-Cookie']
            .map(value => value.split(';', 1)[0])
            .join('; ');
        const tamperedCookie = browserCookie.split('; ')
            .map(value => value.startsWith('__Host-boxbox_member_recovery=') ? `${value}x` : value)
            .join('; ');
        const rejected = mockRes();
        await password(memberReq(
            { action: 'update', password: 'a new secure password' },
            tamperedCookie,
        ), rejected);
        assert.equal(rejected.statusCode, 403);
        assert.equal(calls.some(call => call.options.method === 'PUT'), false);

        const res = mockRes();
        await password(memberReq(
            { action: 'update', password: 'a new secure password' },
            browserCookie,
        ), res);
        assert.equal(res.statusCode, 200);
        const update = calls.find(call => call.options.method === 'PUT');
        assert.deepEqual(JSON.parse(update.options.body), { password: 'a new secure password' });
        assert.equal(update.options.headers.Authorization, `Bearer ${recoveryAccess}`);
        assert.match(res.body.message, /Sign in/);
        assert.ok(res.headers['Set-Cookie'].some(value => /^__Host-boxbox_member_access=;.*Max-Age=0/.test(value)));
        assert.ok(res.headers['Set-Cookie'].some(value => /^__Host-boxbox_member_recovery=;.*Max-Age=0/.test(value)));
    } finally {
        global.fetch = originalFetch;
        restoreEnv();
    }
});

test('rejects password changes from a normal signed-in session', async () => {
    const restoreEnv = configure();
    const originalFetch = global.fetch;
    const access = testJwt({
        sub: 'member-1',
        session_id: 'password-session-1',
        amr: [{ method: 'password', timestamp: Math.floor(Date.now() / 1000) }],
    });
    global.fetch = async (url, options = {}) => {
        if (String(url).endsWith('/auth/v1/user') && (options.method || 'GET') === 'GET') {
            return response({ id: 'member-1', email: 'member@example.com' });
        }
        throw new Error(`Unexpected request: ${url}`);
    };
    try {
        const res = mockRes();
        await password(memberReq(
            { action: 'update', password: 'a new secure password' },
            `__Host-boxbox_member_access=${access}; __Host-boxbox_member_refresh=refresh-token`,
        ), res);
        assert.equal(res.statusCode, 403);
        assert.match(res.body.message, /fresh password setup link/);
    } finally {
        global.fetch = originalFetch;
        restoreEnv();
    }
});
