'use strict';

const {
    getMemberConfig,
    htmlEscape,
    isEntitlementActive,
    restRequest,
    safeEqual,
} = require('../../lib/member-system');
const { buildRecommendation } = require('../../lib/personalized-recommendations');
const { resendRequest } = require('../../lib/email-subscriptions');
const { ensurePitWallSegment } = require('../../lib/resend-segments');
const { syncOfficialLink } = require('./team');

function inFilter(values) {
    return `in.(${values.map(value => String(value).replace(/[^a-zA-Z0-9_-]/g, '')).join(',')})`;
}

function phaseLabel(phase) {
    return ({ pre_fp: 'Early thoughts', post_fp: 'Post-FP', post_quali: 'Post-qualifying' })[phase]
        || String(phase).replace(/_/g, ' ');
}

function normalizedName(value) {
    return String(value || '').toLowerCase().replace(/[^a-z0-9]/g, '');
}

function officialTeamForRecommendation(snapshot, predictions, fallback) {
    if (!snapshot?.assets?.length) return fallback;
    const drivers = new Map((predictions.drivers || []).flatMap(item => [
        [normalizedName(item.name), String(item.driver_id)],
        [normalizedName(item.driver_id), String(item.driver_id)],
    ]));
    const constructors = new Map((predictions.constructors || []).flatMap(item => [
        [normalizedName(item.name), String(item.constructor_id)],
        [normalizedName(item.full_name), String(item.constructor_id)],
        [normalizedName(item.constructor_id), String(item.constructor_id)],
    ]));
    const assets = snapshot.assets.map(item => {
        const lookup = item.asset_type === 'constructor' ? constructors : drivers;
        const assetId = lookup.get(normalizedName(item.name)) || lookup.get(normalizedName(item.asset_id));
        return assetId ? { ...item, asset_id: assetId } : null;
    }).filter(Boolean);
    const driverCount = assets.filter(item => item.asset_type === 'driver').length;
    const constructorCount = assets.filter(item => item.asset_type === 'constructor').length;
    if (driverCount !== 5 || constructorCount !== 2) return fallback;
    return {
        ...fallback,
        budget_millions: snapshot.budget_millions ?? fallback.budget_millions,
        free_transfers: snapshot.free_transfers ?? fallback.free_transfers,
        assets,
    };
}

function emailBody(profile, recommendation, origin) {
    const name = String(profile.display_name || '').trim();
    const greeting = name ? `Hi ${htmlEscape(name)},` : 'Hi there,';
    const move = recommendation.move;
    const moveBlock = move
        ? `<div style="border-left:4px solid #e10600;background:#f6f7f9;padding:14px 16px;margin:18px 0">
            <strong style="display:block;font-size:18px">${htmlEscape(recommendation.headline)}</strong>
            <span style="display:block;margin-top:5px;color:#475467">${htmlEscape(recommendation.explanation)}</span>
        </div>`
        : `<div style="border-left:4px solid #22c55e;background:#f6f7f9;padding:14px 16px;margin:18px 0">
            <strong style="display:block;font-size:18px">${htmlEscape(recommendation.headline)}</strong>
            <span style="display:block;margin-top:5px;color:#475467">${htmlEscape(recommendation.explanation)}</span>
        </div>`;
    const captainLine = recommendation.captain
        ? `<p><strong>2x check:</strong> ${htmlEscape(recommendation.captain.name)} is the highest-projected driver currently in your saved lineup.</p>`
        : '';
    const lineup = `${recommendation.lineup.drivers.join(', ')} · ${recommendation.lineup.constructors.join(', ')}`;
    const url = `${origin}/?utm_source=pit_wall_email&utm_medium=personalized_sim_alert&utm_campaign=round_${recommendation.round}_${recommendation.phase}#optimizer`;
    const html = `<div style="font-family:Arial,sans-serif;max-width:640px;margin:auto;color:#151922">
        <div style="background:#0a0d12;color:#fff;border-radius:12px 12px 0 0;padding:22px 26px;border-bottom:3px solid #e10600">
            <div style="font-size:13px;color:#aab4c3">BoxBox<span style="color:#e10600">F1</span>Fantasy · Pit Wall · R${recommendation.round}</div>
            <h1 style="margin:7px 0 4px;font-size:25px">Your ${htmlEscape(phaseLabel(recommendation.phase))} team check</h1>
            <p style="margin:0;color:#c7d0dc">${htmlEscape(recommendation.race)}</p>
        </div>
        <div style="border:1px solid #e4e7ec;border-top:0;border-radius:0 0 12px 12px;padding:22px 26px">
            <p>${greeting}</p>
            <p>The latest simulations are live. Against the team you saved, the model’s clearest action is:</p>
            ${moveBlock}
            ${captainLine}
            <p><strong>Saved lineup:</strong> ${htmlEscape(lineup)}</p>
            <p><strong>Projected team score:</strong> ${recommendation.projected_team_points.toFixed(1)} points, including the model’s best 2x choice.</p>
            <p><a href="${url}" style="display:inline-block;background:#e10600;color:#fff;text-decoration:none;padding:12px 17px;border-radius:7px;font-weight:700">Open Transfer Advisor</a></p>
            <p style="color:#667085;font-size:12px;line-height:1.5">This is model-based guidance, not a guarantee. You receive it because personalized simulation updates are enabled in your Pit Wall account. Sign in on the site to change that setting.</p>
        </div>
    </div>`;
    const text = `BoxBoxF1Fantasy Pit Wall — ${recommendation.race}\n\n${greeting.replace(/<[^>]+>/g, '')}\n\n${recommendation.headline}\n${recommendation.explanation}\n\n${recommendation.captain ? `2x check: ${recommendation.captain.name}\n` : ''}Projected team score: ${recommendation.projected_team_points.toFixed(1)} points.\n\nOpen Transfer Advisor: ${url}\n\nThis is model-based guidance, not a guarantee. Sign in on the site to manage personalized simulation emails.`;
    return { html, text, url };
}

async function getOrCreateEvent(predictions) {
    const generatedAt = predictions.generated_at || predictions.exported_at;
    if (!generatedAt) throw new Error('Predictions do not include generated_at');
    const eventKey = `${predictions.season}:${predictions.round}:${predictions.phase}:${generatedAt}`;
    const existing = await restRequest(
        `notification_events?event_key=eq.${encodeURIComponent(eventKey)}&select=id,event_key,status&limit=1`,
        { service: true },
    );
    if (existing?.[0]) return existing[0];
    const created = await restRequest('notification_events', {
        service: true,
        method: 'POST',
        prefer: 'return=representation',
        body: {
            event_key: eventKey,
            season: predictions.season,
            round: predictions.round,
            phase: predictions.phase,
            predictions_generated_at: generatedAt,
            status: 'draft',
            payload: { race: predictions.race, exported_at: predictions.exported_at || null },
        },
    });
    return created?.[0];
}

async function setEventStatus(eventId, status) {
    await restRequest(`notification_events?id=eq.${encodeURIComponent(eventId)}`, {
        service: true,
        method: 'PATCH',
        prefer: 'return=minimal',
        body: { status, sent_at: status === 'sent' ? new Date().toISOString() : null },
    });
}

module.exports = async function notify(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Allow', 'POST');
    if (req.method !== 'POST') return res.status(405).json({ ok: false });
    const expectedSecret = String(process.env.MEMBER_NOTIFICATION_SECRET || '').trim();
    const suppliedSecret = String(req.headers.authorization || '').replace(/^Bearer\s+/i, '').trim();
    if (!expectedSecret || !safeEqual(suppliedSecret, expectedSecret)) return res.status(401).json({ ok: false });

    let event;
    try {
        const config = getMemberConfig();
        await ensurePitWallSegment();
        const predictionsResponse = await fetch(`${config.siteOrigin}/data/predictions.json?member_worker=${Date.now()}`, {
            headers: { 'Cache-Control': 'no-cache' },
        });
        if (!predictionsResponse.ok) throw new Error(`Could not load live predictions (${predictionsResponse.status})`);
        const predictions = await predictionsResponse.json();
        if (!['pre_fp', 'post_fp', 'post_quali'].includes(predictions.phase)) {
            return res.status(200).json({ ok: true, skipped: 'phase' });
        }
        const generatedAtMs = Date.parse(predictions.generated_at || predictions.exported_at || '');
        if (!Number.isFinite(generatedAtMs) || Date.now() - generatedAtMs > 72 * 60 * 60 * 1000) {
            return res.status(200).json({ ok: true, skipped: 'stale_simulation' });
        }

        event = await getOrCreateEvent(predictions);
        if (!event) throw new Error('Could not create notification event');
        if (event.status === 'sent') return res.status(200).json({ ok: true, duplicate: true });
        await setEventStatus(event.id, 'processing');

        const entitlements = await restRequest(
            'member_entitlements?status=in.(active,trialing)&select=user_id,status,current_period_end',
            { service: true },
        );
        const activeUserIds = [...new Set((entitlements || [])
            .filter(item => isEntitlementActive(item))
            .map(item => item.user_id))];
        if (!activeUserIds.length) {
            await setEventStatus(event.id, 'sent');
            return res.status(200).json({ ok: true, sent: 0, skipped: 0 });
        }

        const usersFilter = inFilter(activeUserIds);
        const officialLinks = await restRequest(`f1_team_links?user_id=${usersFilter}&status=eq.active&select=*`, { service: true }).catch(() => []);
        for (const link of officialLinks || []) {
            await syncOfficialLink(link, predictions.round).catch(error => console.error('Official-team refresh failed:', error.message));
        }
        const [profiles, teams] = await Promise.all([
            restRequest(`member_profiles?user_id=${usersFilter}&email_simulation_updates=eq.true&select=user_id,email,display_name`, { service: true }),
            restRequest(`saved_teams?user_id=${usersFilter}&is_default=eq.true&select=id,user_id,name,budget_millions,free_transfers`, { service: true }),
        ]);
        const teamIds = (teams || []).map(team => team.id);
        const assets = teamIds.length
            ? await restRequest(`saved_team_assets?team_id=${inFilter(teamIds)}&select=team_id,asset_type,asset_id,slot,is_boosted`, { service: true })
            : [];
        const officialSnapshots = await restRequest(
            `f1_team_snapshots?user_id=${usersFilter}&season=eq.${Number(predictions.season || 2026)}&round=eq.${Number(predictions.round)}&select=user_id,budget_millions,free_transfers,assets,captured_at`,
            { service: true },
        ).catch(() => []);
        const profilesByUser = new Map((profiles || []).map(profile => [profile.user_id, profile]));
        const officialByUser = new Map((officialSnapshots || []).map(snapshot => [snapshot.user_id, snapshot]));
        const assetsByTeam = new Map();
        for (const asset of assets || []) {
            if (!assetsByTeam.has(asset.team_id)) assetsByTeam.set(asset.team_id, []);
            assetsByTeam.get(asset.team_id).push(asset);
        }

        let sent = 0;
        let skipped = 0;
        let failed = 0;
        for (const team of teams || []) {
            const profile = profilesByUser.get(team.user_id);
            const teamAssets = assetsByTeam.get(team.id) || [];
            if (!profile || teamAssets.length !== 7) {
                skipped += 1;
                continue;
            }

            const existing = await restRequest(
                `member_recommendations?event_id=eq.${encodeURIComponent(event.id)}&team_id=eq.${encodeURIComponent(team.id)}&select=id,delivery_status&limit=1`,
                { service: true },
            );
            if (existing?.[0]?.delivery_status === 'sent') {
                skipped += 1;
                continue;
            }

            const recommendationTeam = officialTeamForRecommendation(
                officialByUser.get(team.user_id),
                predictions,
                { ...team, assets: teamAssets },
            );
            const recommendation = buildRecommendation(predictions, recommendationTeam);
            const recommendationRows = await restRequest('member_recommendations?on_conflict=event_id,team_id', {
                service: true,
                method: 'POST',
                prefer: 'resolution=merge-duplicates,return=representation',
                body: {
                    event_id: event.id,
                    user_id: team.user_id,
                    team_id: team.id,
                    recommendation,
                    delivery_status: 'pending',
                    provider_message_id: null,
                    delivered_at: null,
                },
            });
            const recommendationId = recommendationRows?.[0]?.id || existing?.[0]?.id;

            try {
                const content = emailBody(profile, recommendation, config.siteOrigin);
                const delivery = await resendRequest('/emails', process.env.RESEND_API_KEY, {
                    method: 'POST',
                    body: {
                        from: process.env.RESEND_FROM,
                        to: [profile.email],
                        subject: `${recommendation.race}: your ${phaseLabel(recommendation.phase)} team check`,
                        html: content.html,
                        text: content.text,
                    },
                });
                await restRequest(`member_recommendations?id=eq.${encodeURIComponent(recommendationId)}`, {
                    service: true,
                    method: 'PATCH',
                    prefer: 'return=minimal',
                    body: {
                        delivery_status: 'sent',
                        provider_message_id: delivery.id || null,
                        delivered_at: new Date().toISOString(),
                    },
                });
                sent += 1;
            } catch (error) {
                failed += 1;
                await restRequest(`member_recommendations?id=eq.${encodeURIComponent(recommendationId)}`, {
                    service: true,
                    method: 'PATCH',
                    prefer: 'return=minimal',
                    body: { delivery_status: 'failed' },
                }).catch(() => null);
                console.error('Personalized member email failed:', error.message);
            }
        }

        await setEventStatus(event.id, failed ? 'failed' : 'sent');
        return res.status(failed ? 502 : 200).json({ ok: failed === 0, sent, skipped, failed });
    } catch (error) {
        console.error('Member notification worker failed:', error.message);
        if (event?.id) await setEventStatus(event.id, 'failed').catch(() => null);
        return res.status(500).json({ ok: false, message: 'Member notification worker failed.' });
    }
};

module.exports.emailBody = emailBody;
module.exports.inFilter = inFilter;
module.exports.officialTeamForRecommendation = officialTeamForRecommendation;
