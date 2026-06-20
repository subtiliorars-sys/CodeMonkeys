// Mobile-lite route (/m) — add cm-lite before paint when possible.
(function () {
  const p = (location.pathname || "/").replace(/\/$/, "") || "/";
  if (p === "/m") document.documentElement.classList.add("cm-lite");
})();

// PWA — register service worker for Add to Home Screen (Android/iOS).
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}
