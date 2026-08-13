'use strict';

const crypto = require('node:crypto');
const net = require('node:net');

const buckets = globalThis.__boxboxRateLimitBuckets || new Map();
globalThis.__boxboxRateLimitBuckets = buckets;

function clientAddress(req) {
    const candidates = [
        req.headers?.['x-real-ip'],
        String(req.headers?.['x-forwarded-for'] || '').split(',').at(-1),
    ];
    return candidates.map(value => String(value || '').trim()).find(value => net.isIP(value)) || 'unknown';
}

function consumeRateLimit(req, scope, options = {}) {
    const now = Number(options.now || Date.now());
    const windowMs = Number(options.windowMs || 10 * 60 * 1000);
    const limit = Number(options.limit || 10);
    const identity = String(options.identity || '');
    const rawKey = `${scope}:${clientAddress(req)}:${identity}`;
    const key = crypto.createHash('sha256').update(rawKey).digest('hex');
    const current = buckets.get(key);
    const bucket = !current || current.resetAt <= now
        ? { count: 0, resetAt: now + windowMs }
        : current;
    bucket.count += 1;
    buckets.set(key, bucket);

    if (buckets.size > 2000) {
        for (const [candidate, value] of buckets) {
            if (value.resetAt <= now) buckets.delete(candidate);
        }
    }
    return {
        allowed: bucket.count <= limit,
        retryAfterSeconds: Math.max(1, Math.ceil((bucket.resetAt - now) / 1000)),
    };
}

function rateLimited(res, result, message = 'Too many attempts. Please wait and try again.') {
    res.setHeader('Retry-After', String(result.retryAfterSeconds));
    return res.status(429).json({ ok: false, message });
}

module.exports = { clientAddress, consumeRateLimit, rateLimited };
