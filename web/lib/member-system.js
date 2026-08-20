'use strict';

const crypto = require('node:crypto');

const DEFAULT_SITE_ORIGIN = 'https://boxboxf1fantasy.com';
const ACCESS_COOKIE = '__Host-boxbox_member_access';
const REFRESH_COOKIE = '__Host-boxbox_member_refresh';
const RECOVERY_COOKIE = '__Host-boxbox_member_recovery';
const LEGACY_ACCESS_COOKIE = 'boxbox_member_access';
const LEGACY_REFRESH_COOKIE = 'boxbox_member_refresh';
const REFRESH_COOKIE_MAX_AGE = 30 * 24 * 60 * 60;
const RECOVERY_COOKIE_MAX_AGE = 20 * 60;

function required(value, name) {
    const result = String(value || '').trim();
    if (!result) throw new Error(`${name} is not configured`);
    return result;
}

function getMemberConfig() {
    const siteOrigin = (process.env.SITE_ORIGIN || DEFAULT_SITE_ORIGIN).replace(/\/$/, '');
    let parsedOrigin;
    try { parsedOrigin = new URL(siteOrigin); }
    catch (_) { throw new Error('SITE_ORIGIN is not a valid URL'); }
    if (process.env.VERCEL_ENV === 'production' && parsedOrigin.protocol !== 'https:') {
        throw new Error('SITE_ORIGIN must use HTTPS in production');
    }
    return {
        supabaseUrl: required(process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL, 'NEXT_PUBLIC_SUPABASE_URL'),
        publicKey: required(
            process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
            'NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY',
        ),
        serviceKey: required(
            process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SECRET_KEY,
            'SUPABASE_SERVICE_ROLE_KEY',
        ),
        siteOrigin: parsedOrigin.origin,
    };
}

function normalizeEmail(value) {
    return typeof value === 'string' ? value.trim().toLowerCase() : '';
}

function isValidEmail(email) {
    return email.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function allowedSiteOrigins(configuredOrigin) {
    const allowed = new Set([String(configuredOrigin || '').replace(/\/$/, '')].filter(Boolean));
    try {
        const parsed = new URL(configuredOrigin);
        if (parsed.protocol === 'https:' && parsed.hostname === 'boxboxf1fantasy.com') {
            parsed.hostname = 'www.boxboxf1fantasy.com';
            allowed.add(parsed.origin);
        } else if (parsed.protocol === 'https:' && parsed.hostname === 'www.boxboxf1fantasy.com') {
            parsed.hostname = 'boxboxf1fantasy.com';
            allowed.add(parsed.origin);
        }
    } catch (_) {
        // Configuration validation happens in getMemberConfig; an invalid URL is never trusted here.
    }
    return allowed;
}

function isAllowedOrigin(req, configuredOrigin) {
    const origin = String(req.headers.origin || '').replace(/\/$/, '');
    if (!origin) return process.env.VERCEL_ENV !== 'production';
    return allowedSiteOrigins(configuredOrigin).has(origin);
}

function parseBody(req) {
    if (!req.body) return {};
    if (typeof req.body === 'object') return req.body;
    try {
        return JSON.parse(req.body);
    } catch (_) {
        return {};
    }
}

function parseCookies(req) {
    const cookies = {};
    for (const part of String(req.headers.cookie || '').split(';')) {
        const separator = part.indexOf('=');
        if (separator < 1) continue;
        const name = part.slice(0, separator).trim();
        const value = part.slice(separator + 1).trim();
        try {
            cookies[name] = decodeURIComponent(value);
        } catch (_) {
            cookies[name] = value;
        }
    }
    return cookies;
}

function cookie(name, value, options = {}) {
    const sameSite = options.sameSite === 'Lax' ? 'Lax' : 'Strict';
    const parts = [`${name}=${encodeURIComponent(value)}`, 'Path=/', 'HttpOnly', 'Secure', `SameSite=${sameSite}`];
    if (Number.isFinite(options.maxAge)) parts.push(`Max-Age=${Math.max(0, Math.floor(options.maxAge))}`);
    return parts.join('; ');
}

function appendCookies(res, values) {
    const previous = res.getHeader?.('Set-Cookie');
    const existing = previous ? (Array.isArray(previous) ? previous : [previous]) : [];
    res.setHeader('Set-Cookie', [...existing, ...values]);
}

function setSessionCookies(res, session, options = {}) {
    appendCookies(res, [
        cookie(ACCESS_COOKIE, session.access_token, { maxAge: Number(session.expires_in || 3600), sameSite: options.sameSite }),
        cookie(REFRESH_COOKIE, session.refresh_token, { maxAge: REFRESH_COOKIE_MAX_AGE, sameSite: options.sameSite }),
        cookie(LEGACY_ACCESS_COOKIE, '', { maxAge: 0 }),
        cookie(LEGACY_REFRESH_COOKIE, '', { maxAge: 0 }),
    ]);
}

function clearSessionCookies(res) {
    appendCookies(res, [
        cookie(ACCESS_COOKIE, '', { maxAge: 0 }),
        cookie(REFRESH_COOKIE, '', { maxAge: 0 }),
        cookie(RECOVERY_COOKIE, '', { maxAge: 0 }),
        cookie(LEGACY_ACCESS_COOKIE, '', { maxAge: 0 }),
        cookie(LEGACY_REFRESH_COOKIE, '', { maxAge: 0 }),
    ]);
}

async function readJson(response) {
    const text = await response.text();
    if (!text) return null;
    try {
        return JSON.parse(text);
    } catch (_) {
        return text;
    }
}

async function apiRequest(url, options = {}) {
    const response = await fetch(url, options);
    const data = await readJson(response);
    if (!response.ok) {
        const message = data?.msg || data?.message || data?.error_description || data?.error || `Request failed (${response.status})`;
        const error = new Error(message);
        error.status = response.status;
        error.details = data;
        throw error;
    }
    return data;
}

function authHeaders(key, bearer = key) {
    return {
        apikey: key,
        Authorization: `Bearer ${bearer}`,
        'Content-Type': 'application/json',
    };
}

async function authAdminRequest(path, options = {}) {
    const config = getMemberConfig();
    return apiRequest(`${config.supabaseUrl}/auth/v1${path}`, {
        method: options.method || 'GET',
        headers: authHeaders(config.serviceKey),
        body: options.body ? JSON.stringify(options.body) : undefined,
    });
}

async function authPublicRequest(path, options = {}) {
    const config = getMemberConfig();
    return apiRequest(`${config.supabaseUrl}/auth/v1${path}`, {
        method: options.method || 'GET',
        headers: authHeaders(config.publicKey, options.accessToken || config.publicKey),
        body: options.body ? JSON.stringify(options.body) : undefined,
    });
}

async function restRequest(path, options = {}) {
    const config = getMemberConfig();
    const key = options.service ? config.serviceKey : config.publicKey;
    const bearer = options.service ? config.serviceKey : options.accessToken;
    if (!bearer) throw new Error('A member access token is required');
    const headers = authHeaders(key, bearer);
    if (options.prefer) headers.Prefer = options.prefer;
    return apiRequest(`${config.supabaseUrl}/rest/v1/${path}`, {
        method: options.method || 'GET',
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
}

async function fetchUser(accessToken) {
    try {
        return await authPublicRequest('/user', { accessToken });
    } catch (error) {
        if (error.status === 401 || error.status === 403) return null;
        throw error;
    }
}

async function refreshSession(refreshToken) {
    if (!refreshToken) return null;
    try {
        return await authPublicRequest('/token?grant_type=refresh_token', {
            method: 'POST',
            body: { refresh_token: refreshToken },
        });
    } catch (error) {
        if (error.status === 400 || error.status === 401) return null;
        throw error;
    }
}

async function getMemberSession(req, res) {
    const cookies = parseCookies(req);
    const legacySession = !cookies[ACCESS_COOKIE] && Boolean(cookies[LEGACY_ACCESS_COOKIE] || cookies[LEGACY_REFRESH_COOKIE]);
    let accessToken = cookies[ACCESS_COOKIE] || cookies[LEGACY_ACCESS_COOKIE] || '';
    let refreshToken = cookies[REFRESH_COOKIE] || cookies[LEGACY_REFRESH_COOKIE] || '';
    let user = accessToken ? await fetchUser(accessToken) : null;

    if (!user && refreshToken) {
        const refreshed = await refreshSession(refreshToken);
        if (refreshed?.access_token && refreshed?.refresh_token) {
            setSessionCookies(res, refreshed);
            accessToken = refreshed.access_token;
            refreshToken = refreshed.refresh_token;
            user = refreshed.user || await fetchUser(accessToken);
        }
    }

    if (!user) {
        if (accessToken || refreshToken) clearSessionCookies(res);
        return null;
    }
    if (legacySession && accessToken && refreshToken) {
        setSessionCookies(res, { access_token: accessToken, refresh_token: refreshToken, expires_in: 3600 });
    }
    return { user, accessToken, refreshToken };
}

function jwtPayload(accessToken) {
    try {
        const parts = String(accessToken || '').split('.');
        if (parts.length !== 3) return null;
        return JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'));
    } catch (_) {
        return null;
    }
}

function recoveryGrantSignature(payload) {
    const secret = getMemberConfig().serviceKey;
    return crypto.createHmac('sha256', secret)
        .update(`boxbox-member-recovery:v1:${payload}`)
        .digest('base64url');
}

function createRecoveryGrant(accessToken, now = Date.now()) {
    const claims = jwtPayload(accessToken);
    if (!claims?.sub || !claims?.session_id) throw new Error('Supabase recovery session is missing required claims');
    const issuedAt = Math.floor(now / 1000);
    const payload = Buffer.from(JSON.stringify({
        v: 1,
        sub: claims.sub,
        sid: claims.session_id,
        iat: issuedAt,
        exp: issuedAt + RECOVERY_COOKIE_MAX_AGE,
    }), 'utf8').toString('base64url');
    return `${payload}.${recoveryGrantSignature(payload)}`;
}

function setRecoveryGrantCookie(res, accessToken, now = Date.now()) {
    const grant = createRecoveryGrant(accessToken, now);
    appendCookies(res, [cookie(RECOVERY_COOKIE, grant, { maxAge: RECOVERY_COOKIE_MAX_AGE, sameSite: 'Lax' })]);
}

function clearRecoveryGrantCookie(res) {
    appendCookies(res, [cookie(RECOVERY_COOKIE, '', { maxAge: 0 })]);
}

function hasValidRecoveryGrant(req, session, now = Date.now()) {
    const token = parseCookies(req)[RECOVERY_COOKIE];
    const [payload, supplied, extra] = String(token || '').split('.');
    if (!payload || !supplied || extra) return false;
    let expected;
    try { expected = recoveryGrantSignature(payload); }
    catch (_) { return false; }
    const suppliedBuffer = Buffer.from(supplied);
    const expectedBuffer = Buffer.from(expected);
    if (suppliedBuffer.length !== expectedBuffer.length || !crypto.timingSafeEqual(suppliedBuffer, expectedBuffer)) return false;
    try {
        const grant = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
        const claims = jwtPayload(session?.accessToken);
        const nowSeconds = Math.floor(now / 1000);
        return grant.v === 1
            && grant.sub === session?.user?.id
            && grant.sub === claims?.sub
            && grant.sid === claims?.session_id
            && Number.isFinite(grant.iat)
            && Number.isFinite(grant.exp)
            && grant.iat >= nowSeconds - RECOVERY_COOKIE_MAX_AGE
            && grant.iat <= nowSeconds + 60
            && grant.exp >= nowSeconds
            && grant.exp <= grant.iat + RECOVERY_COOKIE_MAX_AGE;
    } catch (_) {
        return false;
    }
}

function isEntitlementActive(entitlement, now = Date.now()) {
    if (!entitlement || !['active', 'trialing'].includes(entitlement.status)) return false;
    if (!entitlement.current_period_end) return true;
    return Date.parse(entitlement.current_period_end) > now;
}

function isMissingTable(error) {
    return error?.status === 404 || /relation .* does not exist|schema cache|42P01/i.test(String(error?.message || ''));
}

async function getMemberDashboard(session) {
    const userId = session.user.id;
    const encodedUserId = encodeURIComponent(userId);
    const [profiles, entitlements] = await Promise.all([
        restRequest(`member_profiles?user_id=eq.${encodedUserId}&select=user_id,email,display_name,email_simulation_updates,email_member_newsletter`, { accessToken: session.accessToken }),
        restRequest(`member_entitlements?user_id=eq.${encodedUserId}&select=provider,status,current_period_end,updated_at&order=updated_at.desc`, { accessToken: session.accessToken }),
    ]);
    const entitlement = (entitlements || []).find(item => isEntitlementActive(item)) || entitlements?.[0] || null;
    const active = isEntitlementActive(entitlement);
    let team = null;
    let recommendation = null;
    let f1Link = null;
    let f1Snapshot = null;

    if (active) {
        try {
            const links = await restRequest(
                `f1_team_links?user_id=eq.${encodedUserId}&select=league_id,league_type,team_slot,official_team_id,official_team_name,manager_name,status,last_synced_at,last_error&limit=1`,
                { accessToken: session.accessToken },
            );
            f1Link = links?.[0] || null;
            if (f1Link) {
                const snapshots = await restRequest(
                    `f1_team_snapshots?user_id=eq.${encodedUserId}&select=season,round,official_team_name,fantasy_points,overall_points,league_rank,overall_rank,budget_millions,free_transfers,chip_code,assets,captured_at&order=season.desc,round.desc&limit=1`,
                    { accessToken: session.accessToken },
                );
                f1Snapshot = snapshots?.[0] || null;
            }
        } catch (error) {
            if (!isMissingTable(error)) throw error;
        }
        const teams = await restRequest(
            `saved_teams?user_id=eq.${encodedUserId}&is_default=eq.true&select=id,name,budget_millions,free_transfers,updated_at&limit=1`,
            { accessToken: session.accessToken },
        );
        if (teams?.[0]) {
            team = teams[0];
            team.assets = await restRequest(
                `saved_team_assets?team_id=eq.${encodeURIComponent(team.id)}&select=asset_type,asset_id,slot,is_boosted&order=asset_type.asc,slot.asc`,
                { accessToken: session.accessToken },
            );
            const recommendations = await restRequest(
                `member_recommendations?team_id=eq.${encodeURIComponent(team.id)}&select=recommendation,delivery_status,created_at&order=created_at.desc&limit=1`,
                { accessToken: session.accessToken },
            );
            recommendation = recommendations?.[0] || null;
        }
    }

    return {
        authenticated: true,
        email: session.user.email || profiles?.[0]?.email || '',
        profile: profiles?.[0] || null,
        entitlement: entitlement ? { ...entitlement, active } : { active: false },
        team,
        recommendation,
        f1_link: f1Link,
        f1_snapshot: f1Snapshot,
    };
}

function safeEqual(left, right) {
    const leftBuffer = Buffer.from(String(left || ''));
    const rightBuffer = Buffer.from(String(right || ''));
    return leftBuffer.length === rightBuffer.length && crypto.timingSafeEqual(leftBuffer, rightBuffer);
}

function htmlEscape(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

module.exports = {
    authAdminRequest,
    authPublicRequest,
    clearRecoveryGrantCookie,
    clearSessionCookies,
    getMemberConfig,
    getMemberDashboard,
    getMemberSession,
    hasValidRecoveryGrant,
    htmlEscape,
    isAllowedOrigin,
    isEntitlementActive,
    isValidEmail,
    normalizeEmail,
    parseBody,
    restRequest,
    safeEqual,
    setRecoveryGrantCookie,
    setSessionCookies,
};
