'use strict';

const crypto = require('node:crypto');

const RESEND_API = 'https://api.resend.com';
const DEFAULT_SITE_ORIGIN = 'https://boxboxf1fantasy.com';
const DEFAULT_TTL_HOURS = 48;

function normalizeEmail(value) {
    if (typeof value !== 'string') return '';
    return value.trim().toLowerCase();
}

function isValidEmail(email) {
    return email.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function base64urlJson(value) {
    return Buffer.from(JSON.stringify(value), 'utf8').toString('base64url');
}

function signPayload(payload, secret) {
    return crypto.createHmac('sha256', secret).update(payload).digest('base64url');
}

function createSubscriptionToken(email, secret, ttlHours = DEFAULT_TTL_HOURS, now = Date.now()) {
    if (!secret) throw new Error('SUBSCRIPTION_SIGNING_SECRET is not configured');
    const payload = base64urlJson({
        email: normalizeEmail(email),
        exp: now + Number(ttlHours || DEFAULT_TTL_HOURS) * 60 * 60 * 1000,
    });
    return `${payload}.${signPayload(payload, secret)}`;
}

function verifySubscriptionToken(token, secret, now = Date.now()) {
    if (!secret || typeof token !== 'string') return null;
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
    const config = {
        apiKey: process.env.RESEND_API_KEY || '',
        from: process.env.RESEND_FROM || '',
        segmentId: process.env.RESEND_SIM_UPDATES_SEGMENT_ID || '',
        signingSecret: process.env.SUBSCRIPTION_SIGNING_SECRET || '',
        siteOrigin: (process.env.SITE_ORIGIN || DEFAULT_SITE_ORIGIN).replace(/\/$/, ''),
        ttlHours: Number(process.env.SUBSCRIPTION_TOKEN_TTL_HOURS || DEFAULT_TTL_HOURS),
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
    const response = await fetch(`${RESEND_API}${path}`, {
        method: options.method || 'GET',
        headers: {
            Authorization: `Bearer ${apiKey}`,
            'Content-Type': 'application/json',
        },
        body: options.body ? JSON.stringify(options.body) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        const error = new Error(data.message || `Resend request failed with ${response.status}`);
        error.status = response.status;
        error.details = data;
        throw error;
    }
    return data;
}

function requestOrigin(req) {
    const forwardedProto = String(req.headers['x-forwarded-proto'] || 'https').split(',')[0].trim();
    const host = String(req.headers['x-forwarded-host'] || req.headers.host || '').split(',')[0].trim();
    return host ? `${forwardedProto}://${host}` : '';
}

function isAllowedRequestOrigin(req, siteOrigin) {
    const origin = String(req.headers.origin || '').replace(/\/$/, '');
    if (!origin) return process.env.VERCEL_ENV !== 'production';
    return origin === siteOrigin || origin === requestOrigin(req);
}

function htmlPage(title, message, success) {
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
<a href="/" style="display:inline-block;padding:11px 18px;border-radius:8px;background:#e10600;color:#fff;text-decoration:none;font-weight:700">Open predictions</a>
</div></main></body></html>`;
}

module.exports = {
    createSubscriptionToken,
    getConfig,
    htmlPage,
    isAllowedRequestOrigin,
    isValidEmail,
    normalizeEmail,
    resendRequest,
    verifySubscriptionToken,
};
