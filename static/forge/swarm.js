/* CodeMonkeys swarm visualizer — extracted from swarm.html's inline <script>
   so the CSP can be script-src 'self' (Tailwind phase 2). Logic unchanged. */
"use strict";
const token = localStorage.getItem("cm_token") || "";
const cv = document.getElementById("c"), hud = document.getElementById("hud");
const W = 320, H = 180;
const buf = document.createElement("canvas"); buf.width = W; buf.height = H;
const b = buf.getContext("2d"), ctx = cv.getContext("2d");
const TIER = { t0:"#39d353", t1:"#58a6ff", t2:"#bc8cff", t3:"#f0c75e" };
let st = { agents: [], activity: [], stats: {} }, t = 0;

async function fetchState() {
  try {
    const r = await fetch("/api/swarm/state", { headers: { Authorization: "Bearer " + token } });
    if (r.ok) st = await r.json();
    const s = st.stats || {};
    hud.textContent = `sessions ${s.sessions ?? 0}  running ${s.running ?? 0}\nspend $${s.spend_today_usd ?? 0}`;
  } catch (e) {}
}
function draw() {
  t++;
  b.fillStyle = "#04040a"; b.fillRect(0, 0, W, H);
  const cx = W / 2, cy = H / 2;
  // core
  b.fillStyle = "#d4af37";
  b.beginPath(); b.arc(cx, cy, 7 + Math.sin(t / 14) * 1.5, 0, 7); b.fill();
  b.fillStyle = "#f0c75e"; b.fillText("CODEMONKEYS", cx - 32, cy - 14);
  const agents = (st.agents || []).slice(0, 12);
  agents.forEach((a, i) => {
    const ang = (i / Math.max(agents.length, 1)) * Math.PI * 2 + t / 200;
    const x = cx + Math.cos(ang) * 58, y = cy + Math.sin(ang) * 42;
    b.strokeStyle = "rgba(34,211,238,.35)";
    b.beginPath(); b.moveTo(cx, cy); b.lineTo(x, y); b.stroke();
    b.fillStyle = TIER[a.tier] || "#58a6ff";
    b.beginPath(); b.arc(x, y, a.status === "running" ? 4 + Math.sin(t / 6 + i) : 3, 0, 7); b.fill();
    b.fillStyle = "#94a3b8"; b.font = "6px monospace";
    b.fillText(a.name.slice(0, 12), x - 18, y + 10);
  });
  // activity packets
  (st.activity || []).slice(-6).forEach((a, i) => {
    const p = ((t + i * 17) % 60) / 60;
    b.fillStyle = "#ff7ad9";
    b.fillRect(cx + (p - 0.5) * 90, cy + 30 + i * 4, 2, 2);
  });
  ctx.imageSmoothingEnabled = false;
  cv.width = innerWidth; cv.height = innerHeight;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(buf, 0, 0, cv.width, cv.height);
  requestAnimationFrame(draw);
}
fetchState(); setInterval(fetchState, 4000); draw();
