'use strict';

document.documentElement.classList.add('js-enabled');
window.setTimeout(() => {
    document.getElementById('driverLiveRegion')?.classList.remove('is-hydrating');
}, 8000);

window.dataLayer = window.dataLayer || [];
window.gtag = window.gtag || function gtag() {
    window.dataLayer.push(arguments);
};
window.gtag('js', new Date());

const mode = document.currentScript?.dataset.gaMode || 'page';
window.gtag('config', 'G-T3HS76FJ7W', mode === 'spa' ? { send_page_view: false } : {});
