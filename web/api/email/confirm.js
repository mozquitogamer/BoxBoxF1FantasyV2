'use strict';

const {
    getConfig,
    htmlPage,
    resendRequest,
    verifySubscriptionToken,
} = require('../../lib/email-subscriptions');

module.exports = async function confirm(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.setHeader('Allow', 'GET');

    if (req.method !== 'GET') {
        return res.status(405).send(htmlPage('Method not allowed', 'Open the confirmation link from your email.', false));
    }

    let config;
    try {
        config = getConfig();
    } catch (error) {
        console.error('Email confirmation is not configured:', error.message);
        return res.status(503).send(htmlPage('Alerts are not ready', 'Please try again later.', false));
    }

    const token = typeof req.query?.token === 'string' ? req.query.token : '';
    const subscription = verifySubscriptionToken(token, config.signingSecret);
    if (!subscription) {
        return res.status(400).send(htmlPage('Link expired or invalid', 'Return to the site and request a new confirmation email.', false));
    }

    const encodedEmail = encodeURIComponent(subscription.email);
    try {
        try {
            await resendRequest('/contacts', config.apiKey, {
                method: 'POST',
                body: {
                    email: subscription.email,
                    unsubscribed: false,
                    segments: [{ id: config.segmentId }],
                },
            });
        } catch (error) {
            if (error.status !== 409) throw error;
            await resendRequest(`/contacts/${encodedEmail}`, config.apiKey, {
                method: 'PATCH',
                body: { unsubscribed: false },
            });
            try {
                await resendRequest(`/contacts/${encodedEmail}/segments/${config.segmentId}`, config.apiKey, {
                    method: 'POST',
                });
            } catch (segmentError) {
                if (segmentError.status !== 409) throw segmentError;
            }
        }

        return res.status(200).send(htmlPage(
            'You’re on the grid',
            'Your email is confirmed. You’ll get a concise alert when the race simulations are updated, with an unsubscribe link in every alert.',
            true
        ));
    } catch (error) {
        console.error('Could not confirm subscription:', error.message);
        return res.status(502).send(htmlPage('Could not confirm', 'Please try the confirmation link again in a moment.', false));
    }
};
