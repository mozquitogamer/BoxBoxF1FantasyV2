# Google AdSense launch checklist

The site has one restrained, responsive display unit at the bottom of the SPA and every crawlable SEO page. It is dormant by default. No Google ad request is made and no empty ad space is shown until valid account and slot IDs are configured.

## What is already prepared

- A literal AdSense account meta tag and loader can be generated inside every page `<head>`.
- A responsive bottom display unit is labelled `Advertisement`, which is one of Google's allowed labels.
- The direct-sponsor banner is a fallback; it will not render when AdSense is active.
- The configurator validates IDs, generates the root `/ads.txt`, rebuilds all static pages, and checks that the files agree.
- The privacy policy contains Google AdSense, cookies, processing, and consent disclosures.

## Google dashboard steps

1. Create or finish the AdSense account and add `boxboxf1fantasy.com` under **Sites**.
2. Copy the 16-digit account ID in the form `ca-pub-1234567890123456`.
3. In **Ads → By ad unit → Display ads**, create one responsive unit for the bottom-of-page placement and copy its 10-digit slot ID.
4. In **Privacy & messaging**, publish Google's European regulations message (a Google-certified TCF CMP) for EEA, UK, and Switzerland traffic before live ads are enabled. Configure the required consent choices and make the privacy-options entry point available.
5. Keep display ads disabled until the site is approved, the consent message is published, and CSP is resolved. Once ads are live, you may view the site normally but must never click your own ads.

## Configure the repository

First publish the account identity and `ads.txt` while leaving the display unit disabled:

```powershell
python pipeline/configure_adsense.py `
  --publisher-id ca-pub-1234567890123456 `
  --account-code `
  --no-display-ads
```

After deployment, confirm these URLs and inspect the bottom of several desktop and mobile pages:

- `https://boxboxf1fantasy.com/ads.txt`
- `https://boxboxf1fantasy.com/`
- `https://boxboxf1fantasy.com/picks/`
- `https://boxboxf1fantasy.com/privacy/`

Validate the repository at any time:

```powershell
python pipeline/configure_adsense.py --check
```

Once the site is approved, the CMP is published, and CSP is compatible, enable the display unit:

```powershell
python pipeline/configure_adsense.py --slot-id 1234567890 --display-ads
```

## CSP activation note

The deployed site currently keeps its existing restrictive Content Security Policy. Google's current AdSense guidance says a strict CSP is supported with per-response random nonces; a fixed list of Google domains is not supported because serving domains change. This static Vercel site does not currently generate nonces, so account/ad flags must remain off until the CSP choice is explicitly approved and implemented. Do not weaken the policy silently just to make the ad load.

## Placement rules

- Keep the unit at the bottom; do not place it over controls, navigation, or content.
- Do not ask users to click ads or describe clicks as a way to support the site.
- Do not add deceptive headings. Use only `Advertisement` or `Sponsored links` immediately above an ad.
- Never use production ads for layout testing and never click your own ads.
