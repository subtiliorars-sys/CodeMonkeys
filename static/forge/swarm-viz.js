/* swarm-viz.js — CodeMonkeys Colony Visualizer, Phase 2
   Canvas 2D renderer, self-contained ES module.
   No game engine, no external deps, no build step.

   Public API:
     initSwarmViz(bgCanvasId, agentCanvasId)  → starts rAF loop
     setSwarmState(agents)                    → push new state array
     setTreeState(treeData)                   → push hierarchical tree
     setLayoutMode(\"ring\"|\"tree\")             → switch layout
     destroySwarmViz()                        → tears down loop + listeners
*/
"use strict";

// ── State colours matching GDD §3 ─────────────────────────────────────────
const STATE_COLOR = {
  IDLE:     "#64748b",   // grey
  THINKING: "#3b82f6",   // blue (pulsed)
  RUNNING:  "#22c55e",   // green
  BLOCKED:  "#f97316",   // orange
  DONE:     "#14b8a6",   // teal
  ERROR:    "#ef4444",   // red
};

const MAX_PROJECTILES = 8;
const PROJECTILE_FRAMES = 48;   // ≈ 0.8s at 60fps
const BANANA_HEIGHT = 22;       // arc apex above straight line, canvas px

// ── Module-level mutable state ─────────────────────────────────────────────
let _bgCanvas = null, _agCanvas = null;
let _bgCtx = null, _agCtx = null;
let _rafId = null;
let _frame = 0;

// agents: array of { id, label, state, progress, _x, _y, _pulsePhase }
let _agents = [];
// projectiles: { fromX, fromY, toX, toY, t, color }
let _projectiles = [];
// track previous states to detect handoffs
let _prevStates = {};
// tree mode: hierarchical tree data { id, label, state, children: [...] }
let _treeData = null;
let _layoutMode = \"ring\";   // \"ring\" | \"tree\"
let _hoveredId = null;       // mouse-over agent id for tooltip

// ── Layout helpers ─────────────────────────────────────────────────────────

function _agentPosition(index, total, W, H) {
  // Arrange agents in a ring around the canvas centre.
  // Single agent: centre stage.
  if (total === 1) return { x: W / 2, y: H / 2 };
  const angle = (index / total) * Math.PI * 2 - Math.PI / 2;
  const rx = W * 0.36;
  const ry = H * 0.34;
  return {
    x: W / 2 + Math.cos(angle) * rx,
    y: H / 2 + Math.sin(angle) * ry,
  };
}

// ── Tree layout (Phase 2 — Claude Code-style sub-agent hierarchy) ─────────

/** Recursively compute {x,y} for each node in a hierarchical tree.
 *  Root at top-centre, children fan out below.  Returns a flat array
 *  of positioned nodes with depth info. */
function _treeLayout(node, depth, x, y, W, H) {
  const positions = [];
  const nodeW = 120;  // horizontal spacing per child
  const nodeH = 72;   // vertical spacing per level
  const py = y + (depth === 0 ? 0 : nodeH);

  positions.push({ id: node.id, x: x, y: py, depth: depth,
                   label: node.label, state: node.state,
                   task: node.task, tier: node.tier, progress: node.progress,
                   summary: node.summary, model: node.model,
                   children: node.children });

  if (node.children && node.children.length) {
    const totalW = (node.children.length - 1) * nodeW;
    const startX = x - totalW / 2;
    for (let i = 0; i < node.children.length; i++) {
      const cx = startX + i * nodeW;
      const childPositions = _treeLayout(node.children[i], depth + 1, cx, py, W, H);
      positions.push(...childPositions);
    }
  }

  return positions;
}

/** Flatten tree into the _agents array with computed positions. */
function _applyTreeLayout(W, H) {
  if (!_treeData) { _agents = []; return; }
  const cx = W / 2;
  const rootY = H * 0.10;  // root near top

  const flat = _treeLayout(_treeData, 0, cx, rootY, W, H);
  // Build _agents with position data
  const prevById = {};
  for (const a of _agents) prevById[a.id] = a;

  _agents = flat.map((n, i) => {
    const prev = prevById[n.id] || {};
    return {
      id:          n.id,
      label:       n.label,
      state:       n.state || "IDLE",
      progress:    n.progress || 0,
      task:        n.task || "",
      tier:        n.tier || "t1",
      model:       n.model || "",
      summary:     n.summary || "",
      depth:       n.depth,
      children:    n.children,
      _x:          prev._x !== undefined ? prev._x + (n.x - prev._x) * 0.08 : n.x,
      _y:          prev._y !== undefined ? prev._y + (n.y - prev._y) * 0.08 : n.y,
      _pulsePhase: prev._pulsePhase !== undefined ? prev._pulsePhase : i * 0.7,
    };
  });
}

// ── Background canvas ──────────────────────────────────────────────────────

function _drawBackground() {
  const W = _bgCanvas.width, H = _bgCanvas.height;
  const c = _bgCtx;

  // Sky gradient
  const sky = c.createLinearGradient(0, 0, 0, H);
  sky.addColorStop(0, "#04040a");
  sky.addColorStop(1, "#0a0d06");
  c.fillStyle = sky;
  c.fillRect(0, 0, W, H);

  // Subtle hex grid (static texture)
  c.strokeStyle = "rgba(34,211,238,0.04)";
  c.lineWidth = 0.5;
  const hexR = 18;
  const hexW = hexR * Math.sqrt(3);
  const hexH = hexR * 2;
  for (let row = -1; row < H / (hexH * 0.75) + 2; row++) {
    for (let col = -1; col < W / hexW + 2; col++) {
      const cx = col * hexW + (row % 2 === 0 ? 0 : hexW / 2);
      const cy = row * hexH * 0.75;
      _hexPath(c, cx, cy, hexR - 1);
      c.stroke();
    }
  }

  // Ground line at bottom 22%
  const gy = H * 0.78;
  const gr = c.createLinearGradient(0, gy, 0, H);
  gr.addColorStop(0, "rgba(30,20,8,0.0)");
  gr.addColorStop(1, "rgba(30,20,8,0.85)");
  c.fillStyle = gr;
  c.fillRect(0, gy, W, H - gy);

  // Central "orchestrator tree" trunk (code-drawn, no art dependency)
  _drawTree(c, W / 2, H * 0.78, H * 0.38, 10);

  // Two satellite trees
  _drawTree(c, W * 0.22, H * 0.78, H * 0.22, 6);
  _drawTree(c, W * 0.78, H * 0.78, H * 0.22, 6);
}

function _hexPath(c, cx, cy, r) {
  c.beginPath();
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 3) * i - Math.PI / 6;
    const x = cx + r * Math.cos(a), y = cy + r * Math.sin(a);
    i === 0 ? c.moveTo(x, y) : c.lineTo(x, y);
  }
  c.closePath();
}

function _drawTree(c, x, groundY, height, trunkW) {
  // Trunk
  c.fillStyle = "#3d2b0f";
  c.fillRect(x - trunkW / 2, groundY - height * 0.4, trunkW, height * 0.4);
  // Canopy — layered circles
  const canopyR = trunkW * 4.5;
  const canopyColors = [
    "rgba(20,28,10,0.80)",
    "rgba(24,34,12,0.65)",
    "rgba(28,40,14,0.50)",
  ];
  for (let layer = 0; layer < 3; layer++) {
    const ly = groundY - height * 0.4 - layer * canopyR * 0.9;
    const lr = canopyR * (1 - layer * 0.25);
    c.fillStyle = canopyColors[layer];
    c.beginPath();
    c.arc(x, ly, lr, 0, Math.PI * 2);
    c.fill();
  }
}

// ── Agent-canvas render ────────────────────────────────────────────────────

function _renderAgents(W, H) {
  const c = _agCtx;
  c.clearRect(0, 0, W, H);

  // Orchestrator core glow (center)
  const cx = W / 2, cy = H / 2;
  const coreGlow = 0.5 + 0.3 * Math.sin(_frame / 20);
  _drawGlow(c, cx, cy, 22, `rgba(212,175,55,${(coreGlow * 0.35).toFixed(2)})`);
  c.fillStyle = `rgba(240,199,94,${(0.7 + coreGlow * 0.25).toFixed(2)})`;
  c.font = "bold 9px ui-monospace,monospace";
  c.textAlign = "center";
  c.fillText("CM", cx, cy + 3);

  const total = _agents.length;

  // ── Tree-mode: draw branch edges before nodes ──────────────────────────
  if (_layoutMode === "tree") {
    const byId = {};
    for (const a of _agents) byId[a.id] = a;
    for (const agent of _agents) {
      if (!agent.children) continue;
      for (const child of agent.children) {
        const childAgent = byId[child.id];
        if (!childAgent) continue;
        c.strokeStyle = "rgba(34,211,238,0.14)";
        c.lineWidth = 1.2;
        c.beginPath();
        c.moveTo(agent._x, agent._y);
        const midY = (agent._y + childAgent._y) / 2;
        c.bezierCurveTo(agent._x, midY, childAgent._x, midY, childAgent._x, childAgent._y);
        c.stroke();
      }
    }
  }

  _agents.forEach((agent, i) => {
    let pos;
    if (_layoutMode === "tree") {
      pos = { x: agent._x !== undefined ? agent._x : W / 2,
              y: agent._y !== undefined ? agent._y : H / 2 };
    } else {
      pos = _agentPosition(i, total, W, H);
    }
    // Smooth position lerp (first frame: snap)
    if (agent._x === undefined) { agent._x = pos.x; agent._y = pos.y; }
    agent._x += (pos.x - agent._x) * 0.08;
    agent._y += (pos.y - agent._y) * 0.08;

    const x = agent._x, y = agent._y;
    const state = (agent.state || "IDLE").toUpperCase();
    const color = STATE_COLOR[state] || STATE_COLOR.IDLE;

    // Phase offset so agents breathe at different rates (GDD §4a)
    if (agent._pulsePhase === undefined) agent._pulsePhase = i * 0.7;
    const pulse = 0.7 + 0.3 * Math.sin(_frame / 40 + agent._pulsePhase);
    const ringR = 10 + (state === "THINKING" ? 2 * pulse : 0);

    // Glow aura
    const glowAlpha = Math.round(pulse * 0.35 * 255).toString(16).padStart(2, "0");
    _drawGlow(c, x, y, ringR + 8, `${color}${glowAlpha}`);

    // Connection line to centre (ring mode only)
    if (_layoutMode !== "tree") {
      c.strokeStyle = "rgba(34,211,238,0.18)";
      c.lineWidth = 0.8;
      c.beginPath(); c.moveTo(cx, cy); c.lineTo(x, y); c.stroke();
    }

    // Outer ring
    c.strokeStyle = color;
    c.lineWidth = state === "THINKING" ? 2 + pulse : 2;
    c.globalAlpha = state === "DONE" ? 0.55 : 1;
    c.beginPath(); c.arc(x, y, ringR, 0, Math.PI * 2); c.stroke();
    c.globalAlpha = 1;

    // Body fill
    c.fillStyle = "rgba(5,5,7,0.88)";
    c.beginPath(); c.arc(x, y, ringR - 2, 0, Math.PI * 2); c.fill();

    // Monkey body (primitive circles — GDD §8c)
    _drawMonkeyBody(c, x, y, state, _frame + i * 7, color);

    // Progress arc (for RUNNING state)
    if (state === "RUNNING" && typeof agent.progress === "number") {
      const prog = Math.max(0, Math.min(1, agent.progress));
      c.strokeStyle = color;
      c.lineWidth = 2.5;
      c.globalAlpha = 0.55;
      c.beginPath();
      c.arc(x, y, ringR + 4, -Math.PI / 2, -Math.PI / 2 + prog * Math.PI * 2);
      c.stroke();
      c.globalAlpha = 1;
    }

    // State badge dot (top-right of ring)
    c.fillStyle = color;
    c.beginPath();
    c.arc(x + ringR * 0.72, y - ringR * 0.72, 3, 0, Math.PI * 2);
    c.fill();

    // Label beneath
    const label = (agent.label || agent.id || "agent").slice(0, 12);
    c.font = "7px ui-monospace,monospace";
    c.textAlign = "center";
    c.fillStyle = state === "DONE" ? "#475569" : "#94a3b8";
    c.fillText(label, x, y + ringR + 11);

    // State text below label
    c.font = "6px ui-monospace,monospace";
    c.fillStyle = color;
    c.globalAlpha = state === "DONE" ? 0.5 : 0.85;
    c.fillText(state, x, y + ringR + 19);
    c.globalAlpha = 1;

    // ── Tooltip on hover (tree mode shows task/model) ──────────────────
    if (_layoutMode === "tree" && _hoveredId === agent.id && agent.task) {
      const tipW = 160, tipH = 42;
      const tipX = Math.min(Math.max(x - tipW / 2, 4), W - tipW - 4);
      const tipY = Math.max(y - ringR - tipH - 12, 4);
      c.fillStyle = "rgba(5,5,7,0.92)";
      c.strokeStyle = "rgba(212,175,55,0.5)";
      c.lineWidth = 1;
      c.beginPath();
      c.roundRect(tipX, tipY, tipW, tipH, 4);
      c.fill();
      c.stroke();
      c.fillStyle = "#a5f3fc";
      c.font = "7px ui-monospace,monospace";
      c.textAlign = "left";
      c.fillText((agent.task || "").slice(0, 48), tipX + 6, tipY + 12);
      c.fillStyle = "#64748b";
      c.font = "6px ui-monospace,monospace";
      c.fillText(agent.model || agent.tier || "", tipX + 6, tipY + 26);
      c.textAlign = "center";
      c.fillStyle = "rgba(5,5,7,0.92)";
      c.beginPath();
      c.moveTo(x - 4, tipY + tipH);
      c.lineTo(x, tipY + tipH + 5);
      c.lineTo(x + 4, tipY + tipH);
      c.fill();
    }
  });

  // Projectiles (banana arcs)
  _renderProjectiles(c);
}

function _drawMonkeyBody(c, x, y, state, frame, color) {
  // Minimal pixel-art style using primitives only (GDD §8c)
  const brownBody = "rgba(101,67,33,0.9)";
  const brownHead = "rgba(120,82,40,0.9)";

  // Body
  c.fillStyle = brownBody;
  c.beginPath(); c.arc(x, y + 1, 4, 0, Math.PI * 2); c.fill();

  // Head (slightly above body)
  c.fillStyle = brownHead;
  c.beginPath(); c.arc(x, y - 4, 3, 0, Math.PI * 2); c.fill();

  // Eyes
  c.fillStyle = "#1a1204";
  c.fillRect(x - 2, y - 5, 1, 1);
  c.fillRect(x + 1, y - 5, 1, 1);

  // State-specific arm animation
  if (state === "RUNNING" || state === "THINKING") {
    // Arms out with animated swing (typing/working pose)
    const armSwing = Math.sin(frame / 8) * 2;
    c.strokeStyle = brownBody;
    c.lineWidth = 1.5;
    c.beginPath(); c.moveTo(x - 3, y); c.lineTo(x - 6, y + armSwing); c.stroke();
    c.beginPath(); c.moveTo(x + 3, y); c.lineTo(x + 6, y - armSwing); c.stroke();
  } else if (state === "BLOCKED") {
    // Arms crossed
    c.strokeStyle = brownBody;
    c.lineWidth = 1.5;
    c.beginPath(); c.moveTo(x - 3, y - 1); c.lineTo(x + 2, y + 2); c.stroke();
    c.beginPath(); c.moveTo(x + 3, y - 1); c.lineTo(x - 2, y + 2); c.stroke();
  } else if (state === "DONE") {
    // Arms raised (celebrate)
    c.strokeStyle = brownBody;
    c.lineWidth = 1.5;
    c.beginPath(); c.moveTo(x - 3, y); c.lineTo(x - 5, y - 4); c.stroke();
    c.beginPath(); c.moveTo(x + 3, y); c.lineTo(x + 5, y - 4); c.stroke();
  } else if (state === "ERROR") {
    // Shaking exclamation mark
    const shake = Math.sin(frame / 4) * 1.5;
    c.fillStyle = "#ef4444";
    c.font = "bold 8px monospace";
    c.textAlign = "center";
    c.fillText("!", x + shake, y - 10);
  }
}

function _drawGlow(c, x, y, r, colorStr) {
  const g = c.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, colorStr);
  g.addColorStop(1, "transparent");
  c.fillStyle = g;
  c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2); c.fill();
}

// ── Projectile (banana) mechanics ─────────────────────────────────────────

function _spawnBanana(fromAgent, toAgent, color) {
  if (_projectiles.length >= MAX_PROJECTILES) _projectiles.shift();
  _projectiles.push({
    fromX: fromAgent._x || 0,
    fromY: fromAgent._y || 0,
    toX:   typeof toAgent._x === "number" ? toAgent._x : toAgent.x || 0,
    toY:   typeof toAgent._y === "number" ? toAgent._y : toAgent.y || 0,
    t: 0,
    color: color || "#f0c75e",
  });
}

function _renderProjectiles(c) {
  _projectiles = _projectiles.filter(p => p.t <= 1);
  for (const p of _projectiles) {
    const t = p.t;
    // Parabolic arc (GDD §5): x linear, y with arc apex
    const x = p.fromX + (p.toX - p.fromX) * t;
    const y = p.fromY + (p.toY - p.fromY) * t - BANANA_HEIGHT * 4 * t * (1 - t);

    // Banana: yellow oval with slight rotation
    c.save();
    c.translate(x, y);
    const angle = Math.atan2(p.toY - p.fromY, p.toX - p.fromX) + (1 - t) * 0.8;
    c.rotate(angle);
    c.fillStyle = p.color;
    c.globalAlpha = 0.9;
    c.beginPath();
    c.ellipse(0, 0, 5, 2.5, 0, 0, Math.PI * 2);
    c.fill();
    // Tip dots
    c.fillStyle = "#7c5800";
    c.fillRect(-4.5, -0.5, 1, 1);
    c.fillRect(3.5, -0.5, 1, 1);
    c.globalAlpha = 1;
    c.restore();

    // Advance t each render frame
    p.t += 1 / PROJECTILE_FRAMES;
  }
}

// ── State diff → fire handoff bananas ─────────────────────────────────────

function _detectHandoffs(newAgents) {
  for (const a of newAgents) {
    const prev = _prevStates[a.id];
    const cur = (a.state || "IDLE").toUpperCase();
    if (!prev) { _prevStates[a.id] = cur; continue; }

    // Transition to DONE fires a banana toward the orchestrator (canvas centre)
    if (prev !== "DONE" && cur === "DONE") {
      const agObj = _agents.find(ag => ag.id === a.id);
      if (agObj && _agCanvas) {
        _spawnBanana(
          agObj,
          { _x: _agCanvas.width / 2, _y: _agCanvas.height / 2 },
          STATE_COLOR.DONE,
        );
      }
    }

    // Transition to RUNNING from THINKING/BLOCKED fires banana from a neighbour
    if ((prev === "THINKING" || prev === "BLOCKED") && cur === "RUNNING") {
      const agObj = _agents.find(ag => ag.id === a.id);
      const others = _agents.filter(ag => ag.id !== a.id && ag.state !== "DONE");
      if (agObj && others.length > 0) {
        const src = others[Math.floor(Math.random() * others.length)];
        _spawnBanana(src, agObj, STATE_COLOR.RUNNING);
      }
    }

    _prevStates[a.id] = cur;
  }

  // Purge stale ids
  const ids = new Set(newAgents.map(a => a.id));
  for (const k of Object.keys(_prevStates)) {
    if (!ids.has(k)) delete _prevStates[k];
  }
}

// ── Main rAF loop ──────────────────────────────────────────────────────────

function _loop() {
  _frame++;

  // Resize both canvases to match container each frame (cheap when unchanged)
  const container = _agCanvas.parentElement || document.body;
  const dw = container.clientWidth  || window.innerWidth;
  const dh = container.clientHeight || window.innerHeight;
  if (_agCanvas.width !== dw || _agCanvas.height !== dh) {
    _agCanvas.width  = dw; _agCanvas.height = dh;
    _bgCanvas.width  = dw; _bgCanvas.height = dh;
    _drawBackground();   // redraw static bg on resize
    // Re-layout tree on resize
    if (_layoutMode === "tree" && _treeData) {
      _applyTreeLayout(dw, dh);
    }
  }

  _renderAgents(_agCanvas.width, _agCanvas.height);

  _rafId = requestAnimationFrame(_loop);
}

// ── Poll window.__swarmState ───────────────────────────────────────────────

let _pollInterval = null;

function _applySwarmState(agents) {
  if (!Array.isArray(agents)) return;
  _detectHandoffs(agents);
  // Merge positional/animation data from existing _agents into new list
  const byId = {};
  for (const a of _agents) byId[a.id] = a;
  _agents = agents.map(a => Object.assign({}, byId[a.id] || {}, a));
}

// ── Public API ─────────────────────────────────────────────────────────────

/**
 * initSwarmViz(bgCanvasId, agentCanvasId)
 * Finds both canvas elements, draws the static background once,
 * and starts the animation loop + window.__swarmState poll.
 */
export function initSwarmViz(bgCanvasId, agentCanvasId) {
  _bgCanvas = document.getElementById(bgCanvasId);
  _agCanvas = document.getElementById(agentCanvasId);
  if (!_bgCanvas || !_agCanvas) {
    console.error("swarm-viz: canvas elements not found", bgCanvasId, agentCanvasId);
    return;
  }
  _bgCtx = _bgCanvas.getContext("2d");
  _agCtx = _agCanvas.getContext("2d");

  // Size to container
  const container = _agCanvas.parentElement || document.body;
  _bgCanvas.width = _agCanvas.width = container.clientWidth  || window.innerWidth;
  _bgCanvas.height = _agCanvas.height = container.clientHeight || window.innerHeight;

  _drawBackground();

  // Start rAF loop
  _rafId = requestAnimationFrame(_loop);

  // Register mouse hover for tooltips (tree mode)
  _agCanvas.addEventListener("mousemove", _onMouseMove);

  // Poll window.__swarmState every 500ms (GDD §8b: poll async, render sync)
  _pollInterval = setInterval(() => {
    if (Array.isArray(window.__swarmState)) {
      _applySwarmState(window.__swarmState);
    }
  }, 500);

  // Apply immediately if already set
  if (Array.isArray(window.__swarmState)) {
    _applySwarmState(window.__swarmState);
  }
}

/**
 * setSwarmState(agents)
 * Push a new array of agent objects directly (bypasses __swarmState poll).
 * Each agent: { id, label, state, progress }
 */
export function setSwarmState(agents) {
  _applySwarmState(agents);
}

/**
 * destroySwarmViz()
 * Cancel animation loop and poll interval. Safe to call multiple times.
 */
export function destroySwarmViz() {
  if (_rafId !== null) { cancelAnimationFrame(_rafId); _rafId = null; }
  if (_pollInterval !== null) { clearInterval(_pollInterval); _pollInterval = null; }
  _agents = [];
  _projectiles = [];
  _prevStates = {};
  _treeData = null;
  _hoveredId = null;
  _frame = 0;
  if (_agCanvas) {
    _agCanvas.removeEventListener("mousemove", _onMouseMove);
  }
}

// ── Mouse hover → tooltip on agent nodes ────────────────────────────────────

function _onMouseMove(e) {
  if (!_agCanvas || _layoutMode !== "tree") { _hoveredId = null; return; }
  const rect = _agCanvas.getBoundingClientRect();
  const mx = (e.clientX - rect.left) * (_agCanvas.width / rect.width);
  const my = (e.clientY - rect.top) * (_agCanvas.height / rect.height);

  let found = null;
  for (const agent of _agents) {
    const dx = mx - agent._x, dy = my - agent._y;
    if (dx * dx + dy * dy < 20 * 20) { // 20px hit radius
      found = agent.id;
      break;
    }
  }
  _hoveredId = found;
}

/** Push hierarchical tree data for tree-layout mode.
 *  treeData: { id, label, state, tier, task, progress, children: [...] } */
export function setTreeState(treeData) {
  _treeData = treeData;
  _layoutMode = "tree";
  if (_agCanvas) {
    _applyTreeLayout(_agCanvas.width, _agCanvas.height);
  }
}

/** Switch between ring and tree layout.
 *  mode: "ring" | "tree" */
export function setLayoutMode(mode) {
  _layoutMode = mode === "tree" ? "tree" : "ring";
  if (_layoutMode === "ring") {
    _treeData = null;
    _hoveredId = null;
  }
}
