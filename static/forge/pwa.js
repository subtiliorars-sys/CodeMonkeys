/* PWA bootstrap — register service worker (CSP script-src 'self' only). */
"use strict";

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
