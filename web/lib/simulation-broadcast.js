'use strict';

const { htmlEscape } = require('./member-system');
const { getConfig, resendRequest } = require('./email-subscriptions');
const { ensureBeatV13Segment } = require('./resend-segments');

const UNSUBSCRIBE_URL = '{{{RESEND_UNSUBSCRIBE_URL}}}';
const ACTIONABLE_PHASES = new Set(['pre_fp', 'post_fp', 'post_quali']);

function points(item) {
    return Number(item?.expected_points ?? item?.projected_points ?? 0) || 0;
}

function phaseLabel(phase) {
    return ({ pre_fp: 'Pre-practice', post_fp: 'Post-practice', post_quali: 'Post-qualifying' })[phase]
        || String(phase || 'Updated').replace(/_/g, ' ');
}

function top(items, limit = 3) {
    return [...(items || [])].sort((left, right) => points(right) - points(left)).slice(0, limit);
}

function broadcastName(predictions) {
    return `R${Number(predictions.round)} ${phaseLabel(predictions.phase)} simulation alert`;
}

function buildBroadcast(predictions, siteOrigin) {
    const race = String(predictions.race || 'the next Grand Prix');
    const round = Number(predictions.round || 0);
    const phase = String(predictions.phase || 'updated');
    const phaseName = phaseLabel(phase);
    const drivers = top(predictions.drivers);
    const constructors = top(predictions.constructors);
    const url = `${siteOrigin}/?utm_source=email&utm_medium=simulation_alert&utm_campaign=round_${round}_${phase}#drivers`;
    const driverRows = drivers.map(driver => (
        `<li><strong>${htmlEscape(driver.name || driver.driver_id || 'Driver')}</strong>`
        + ` — ${points(driver).toFixed(1)} expected pts, P${htmlEscape(driver.predicted_finish ?? '–')} finish</li>`
    )).join('');
    const constructorRows = constructors.map(constructor => (
        `<li><strong>${htmlEscape(constructor.name || constructor.constructor_id || 'Constructor')}</strong>`
        + ` — ${points(constructor).toFixed(1)} expected pts</li>`
    )).join('');
    const html = `<!doctype html><html><body style="margin:0;background:#f4f6f8;color:#151922;font-family:Arial,sans-serif">
<div style="max-width:640px;margin:0 auto;padding:24px 16px">
  <div style="background:#0a0d12;color:#fff;border-radius:12px;overflow:hidden">
    <div style="padding:22px 26px;border-bottom:3px solid #e10600">
      <div style="font-size:13px;color:#aab4c3">BoxBox<span style="color:#e10600">F1</span>Fantasy · Round ${round}</div>
      <h1 style="margin:7px 0 4px;font-size:25px">Fresh simulations are live</h1>
      <p style="margin:0;color:#c7d0dc">${htmlEscape(race)} · ${htmlEscape(phaseName)}</p>
    </div>
    <div style="padding:22px 26px">
      <h2 style="font-size:17px;margin:0 0 8px">Top driver projections</h2>
      <ol style="padding-left:22px;line-height:1.8;margin:0 0 20px">${driverRows}</ol>
      <h2 style="font-size:17px;margin:0 0 8px">Top constructors</h2>
      <ol style="padding-left:22px;line-height:1.8;margin:0 0 24px">${constructorRows}</ol>
      <p style="margin:0"><a href="${url}" style="display:inline-block;background:#e10600;color:#fff;text-decoration:none;padding:12px 17px;border-radius:7px;font-weight:700">Open the updated predictions</a></p>
    </div>
  </div>
  <p style="font-size:12px;line-height:1.5;color:#667085;text-align:center">You confirmed that you want BoxBox simulation-update alerts. <a href="${UNSUBSCRIBE_URL}" style="color:#667085">Unsubscribe</a>.</p>
</div></body></html>`;
    const driverText = drivers.map((driver, index) => (
        `${index + 1}. ${driver.name || driver.driver_id} — ${points(driver).toFixed(1)} expected pts, P${driver.predicted_finish ?? '–'} finish`
    )).join('\n');
    const constructorText = constructors.map((constructor, index) => (
        `${index + 1}. ${constructor.name || constructor.constructor_id} — ${points(constructor).toFixed(1)} expected pts`
    )).join('\n');
    const text = `BoxBoxF1Fantasy — ${race}\n${phaseName} simulations are live.\n\nTop driver projections\n${driverText}\n\nTop constructors\n${constructorText}\n\nOpen the updated predictions: ${url}\nUnsubscribe: ${UNSUBSCRIBE_URL}\n`;
    return {
        name: broadcastName(predictions),
        subject: `${race} simulations updated — ${phaseName}`,
        html,
        text,
    };
}

async function existingBroadcast(apiKey, name) {
    const listed = await resendRequest('/broadcasts?limit=100', apiKey);
    for (const item of listed?.data || []) {
        if (item.name === name) return item;
        if (!item.id) continue;
        const detail = await resendRequest(`/broadcasts/${encodeURIComponent(item.id)}`, apiKey);
        if (detail?.name === name) return detail;
    }
    return null;
}

async function activeContactCount(apiKey, segmentId) {
    const contacts = await resendRequest(`/segments/${encodeURIComponent(segmentId)}/contacts?limit=100`, apiKey);
    return (contacts?.data || []).filter(contact => contact.unsubscribed !== true).length;
}

async function sendV13Broadcast(res) {
    try {
        const config = getConfig();
        const segmentId = await ensureBeatV13Segment();
        const predictionsResponse = await fetch(`${config.siteOrigin}/data/predictions.json?v13_broadcast=${Date.now()}`, {
            headers: { 'Cache-Control': 'no-cache' },
        });
        if (!predictionsResponse.ok) throw new Error(`Could not load live predictions (${predictionsResponse.status})`);
        const predictions = await predictionsResponse.json();
        if (!ACTIONABLE_PHASES.has(predictions.phase)) return res.status(200).json({ ok: true, skipped: 'phase' });
        const generatedAtMs = Date.parse(predictions.generated_at || predictions.exported_at || '');
        if (!Number.isFinite(generatedAtMs) || Date.now() - generatedAtMs > 72 * 60 * 60 * 1000) {
            return res.status(200).json({ ok: true, skipped: 'stale_simulation' });
        }

        const content = buildBroadcast(predictions, config.siteOrigin);
        const duplicate = await existingBroadcast(config.apiKey, content.name);
        const recipients = await activeContactCount(config.apiKey, segmentId);
        if (duplicate?.status === 'sent' || duplicate?.status === 'scheduled') {
            return res.status(200).json({ ok: true, duplicate: true, recipients, broadcast_id: duplicate.id });
        }
        if (duplicate?.status === 'draft') {
            await resendRequest(`/broadcasts/${encodeURIComponent(duplicate.id)}/send`, config.apiKey, {
                method: 'POST',
                body: {},
            });
            return res.status(200).json({ ok: true, sent: recipients, broadcast_id: duplicate.id });
        }

        const created = await resendRequest('/broadcasts', config.apiKey, {
            method: 'POST',
            body: {
                segment_id: segmentId,
                from: config.from,
                ...content,
                send: true,
            },
        });
        return res.status(200).json({ ok: true, sent: recipients, broadcast_id: created.id || null });
    } catch (error) {
        console.error('V13 broadcast failed:', error.message);
        return res.status(500).json({ ok: false, message: 'V13 broadcast failed.' });
    }
}

module.exports = {
    activeContactCount,
    broadcastName,
    buildBroadcast,
    existingBroadcast,
    phaseLabel,
    sendV13Broadcast,
};
