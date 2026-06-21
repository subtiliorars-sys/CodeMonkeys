// Mobile-lite route (/m) — add cm-lite before paint when possible.
(function () {
  const p = (location.pathname || "/").replace(/\/$/, "") || "/";
  if (p === "/m") document.documentElement.classList.add("cm-lite");
})();
