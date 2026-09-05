'use strict';

const crypto = require('node:crypto');

const RESEND_API = 'https://api.resend.com';
const DEFAULT_SITE_ORIGIN = 'https://boxboxf1fantasy.com';
const DEFAULT_TTL_HOURS = 48;
const BEAT_V13_REGISTRATION_DEADLINE = '2026-11-21T04:00:00Z';
const BEAT_V13_REGISTRATION_DEADLINE_MS = Date.parse(BEAT_V13_REGISTRATION_DEADLINE);
const BEAT_V13_BROWSER_COOKIE = '__Host-boxbox_beat_v13';

const {
    beatV13SessionCookie,
    parseBeatV13Session,
    sessionSecret,
    verifyBeatV13SessionCookie,
} = require('./beat-v13-entries');

function isBeatV13RegistrationOpen(now = Date.now()) {
    return Number.isFinite(now) && now < BEAT_V13_REGISTRATION_DEADLINE_MS;
}

function beatV13BrowserCookie(maxAgeSeconds = 365 * 24 * 60 * 60) {
    return `${BEAT_V13_BROWSER_COOKIE}=confirmed; Path=/; Max-Age=${Math.max(0, Math.floor(maxAgeSeconds))}; Secure; SameSite=Strict`;
}

function normalizeEmail(value) {
    if (typeof value !== 'string') return '';
    return value.trim().toLowerCase();
}

function isValidEmail(email) {
    return email.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function signPayload(payload, secret) {
    return crypto.createHmac('sha256', secret).update(payload).digest('base64url');
}

function createSubscriptionToken(email, secret, ttlHours = DEFAULT_TTL_HOURS, now = Date.now()) {
    if (!secret) throw new Error('SUBSCRIPTION_SIGNING_SECRET is not configured');
    const payload = Buffer.from(JSON.stringify({
        email: normalizeEmail(email),
        exp: now + Number(ttlHours || DEFAULT_TTL_HOURS) * 60 * 60 * 1000,
    }), 'utf8');
    const iv = crypto.randomBytes(12);
    const key = crypto.createHash('sha256').update(String(secret)).digest();
    const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
    cipher.setAAD(Buffer.from('boxbox-beat-v13:v2'));
    const ciphertext = Buffer.concat([cipher.update(payload), cipher.final()]);
    return `v2.${iv.toString('base64url')}.${ciphertext.toString('base64url')}.${cipher.getAuthTag().toString('base64url')}`;
}

function verifySubscriptionToken(token, secret, now = Date.now()) {
    if (!secret || typeof token !== 'string') return null;
    const encrypted = token.split('.');
    if (encrypted.length === 4 && encrypted[0] === 'v2') {
        try {
            const key = crypto.createHash('sha256').update(String(secret)).digest();
            const decipher = crypto.createDecipheriv('aes-256-gcm', key, Buffer.from(encrypted[1], 'base64url'));
            decipher.setAAD(Buffer.from('boxbox-beat-v13:v2'));
            decipher.setAuthTag(Buffer.from(encrypted[3], 'base64url'));
            const cleartext = Buffer.concat([
                decipher.update(Buffer.from(encrypted[2], 'base64url')),
                decipher.final(),
            ]);
            const decoded = JSON.parse(cleartext.toString('utf8'));
            const email = normalizeEmail(decoded.email);
            if (!isValidEmail(email) || !Number.isFinite(decoded.exp) || decoded.exp < now) return null;
            return { email, exp: decoded.exp };
        } catch (_) {
            return null;
        }
    }

    // Accept previously issued signed tokens until their short expiration passes.
    const [payload, suppliedSignature, extra] = token.split('.');
    if (!payload || !suppliedSignature || extra) return null;

    const expectedSignature = signPayload(payload, secret);
    const supplied = Buffer.from(suppliedSignature);
    const expected = Buffer.from(expectedSignature);
    if (supplied.length !== expected.length || !crypto.timingSafeEqual(supplied, expected)) return null;

    try {
        const decoded = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
        const email = normalizeEmail(decoded.email);
        if (!isValidEmail(email) || !Number.isFinite(decoded.exp) || decoded.exp < now) return null;
        return { email, exp: decoded.exp };
    } catch (_) {
        return null;
    }
}

function getConfig() {
    const rawSiteOrigin = (process.env.SITE_ORIGIN || DEFAULT_SITE_ORIGIN).replace(/\/$/, '');
    let siteOrigin;
    try { siteOrigin = new URL(rawSiteOrigin).origin; }
    catch (_) { throw new Error('SITE_ORIGIN is not a valid URL'); }
    if (process.env.VERCEL_ENV === 'production' && !siteOrigin.startsWith('https://')) {
        throw new Error('SITE_ORIGIN must use HTTPS in production');
    }
    const config = {
        apiKey: process.env.RESEND_API_KEY || '',
        from: process.env.RESEND_FROM || '',
        segmentId: process.env.RESEND_SIM_UPDATES_SEGMENT_ID || '',
        signingSecret: process.env.SUBSCRIPTION_SIGNING_SECRET || '',
        siteOrigin,
        ttlHours: Number(process.env.SUBSCRIPTION_TOKEN_TTL_HOURS || DEFAULT_TTL_HOURS),
        sessionSecret: sessionSecret(),
    };

    const missing = [];
    if (!config.apiKey) missing.push('RESEND_API_KEY');
    if (!config.from) missing.push('RESEND_FROM');
    if (!config.segmentId) missing.push('RESEND_SIM_UPDATES_SEGMENT_ID');
    if (!config.signingSecret) missing.push('SUBSCRIPTION_SIGNING_SECRET');
    if (missing.length) throw new Error(`Missing email configuration: ${missing.join(', ')}`);
    return config;
}

async function resendRequest(path, apiKey, options = {}) {
    for (let attempt = 0; attempt < 4; attempt += 1) {
        const response = await fetch(`${RESEND_API}${path}`, {
            method: options.method || 'GET',
            headers: {
                Authorization: `Bearer ${apiKey}`,
                'Content-Type': 'application/json',
                ...(options.headers || {}),
            },
            body: options.body ? JSON.stringify(options.body) : undefined,
        });
        const data = await response.json().catch(() => ({}));
        if (response.status === 429 && attempt < 3) {
            const retryAfter = Number(response.headers?.get?.('retry-after'));
            const waitMs = Number.isFinite(retryAfter) && retryAfter > 0
                ? Math.min(5000, Math.max(250, retryAfter * 1000))
                : 1000 * (attempt + 1);
            await new Promise(resolve => setTimeout(resolve, waitMs));
            continue;
        }
        if (!response.ok) {
            const error = new Error(data.message || `Resend request failed with ${response.status}`);
            error.status = response.status;
            error.details = data;
            throw error;
        }
        return data;
    }
    throw new Error('Resend request exhausted its retry budget');
}

function isResendEmailCancellationSettled(error) {
    const status = Number(error?.status);
    const message = String(error?.message || error?.details?.message || '');
    return [404, 409].includes(status) || /\bnot scheduled\b/i.test(message);
}

function allowedSiteOrigins(siteOrigin) {
    const allowed = new Set([String(siteOrigin || '').replace(/\/$/, '')].filter(Boolean));
    try {
        const parsed = new URL(siteOrigin);
        if (parsed.protocol === 'https:' && parsed.hostname === 'boxboxf1fantasy.com') {
            parsed.hostname = 'www.boxboxf1fantasy.com';
            allowed.add(parsed.origin);
        } else if (parsed.protocol === 'https:' && parsed.hostname === 'www.boxboxf1fantasy.com') {
            parsed.hostname = 'boxboxf1fantasy.com';
            allowed.add(parsed.origin);
        }
    } catch (_) {
        // Invalid origins are never added.
    }
    return allowed;
}

function isAllowedRequestOrigin(req, siteOrigin) {
    const origin = String(req.headers.origin || '').replace(/\/$/, '');
    if (!origin) return process.env.VERCEL_ENV !== 'production';
    return allowedSiteOrigins(siteOrigin).has(origin);
}

function htmlPage(title, message, success, actionHref = '/', actionLabel = 'Open predictions') {
    const accent = success ? '#22c55e' : '#ef4444';
    return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>${title} | BoxBoxF1Fantasy</title></head>
<body style="margin:0;background:#0a0d12;color:#f5f7fa;font-family:Inter,Arial,sans-serif">
<main style="max-width:620px;margin:10vh auto;padding:32px 24px;text-align:center">
<div style="border:1px solid #273142;border-top:3px solid ${accent};border-radius:12px;background:#121821;padding:36px 28px">
<p style="margin:0 0 8px;color:#aab4c3;font-size:14px">BoxBox<span style="color:#e10600">F1</span>Fantasy</p>
<h1 style="margin:0 0 14px;font-size:28px">${title}</h1>
<p style="margin:0 0 24px;color:#c7d0dc;line-height:1.6">${message}</p>
<a href="${actionHref}" style="display:inline-block;padding:11px 18px;border-radius:8px;background:#e10600;color:#fff;text-decoration:none;font-weight:700">${actionLabel}</a>
</div></main></body></html>`;
}

module.exports = {
    BEAT_V13_REGISTRATION_DEADLINE,
    BEAT_V13_BROWSER_COOKIE,
    beatV13BrowserCookie,
    beatV13SessionCookie,
    createSubscriptionToken,
    getConfig,
    htmlPage,
    isBeatV13RegistrationOpen,
    isAllowedRequestOrigin,
    isValidEmail,
    isResendEmailCancellationSettled,
    normalizeEmail,
    parseBeatV13Session,
    resendRequest,
    sessionSecret,
    verifyBeatV13SessionCookie,
    verifySubscriptionToken,
};
