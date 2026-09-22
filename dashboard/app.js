/**
 * CER-Intent Dashboard — Frontend Application
 * Socket.IO + D3.js topology + REST API integration
 */
"use strict";

// ── Config ────────────────────────────────────────────────────────────────────
const API = "";  // Same origin
const EXAMPLES = [
  "Increase capacity on link-A-B to 5 Gbps for eMBB slice",
  "Enable 1+1 HSB protection on sector-north",
  "Set minimum modulation to 256QAM on all links",
  "Ensure latency < 5ms on link-D-E for URLLC traffic",
  "Allocate 30% bandwidth to eMBB slice on link-E-H",
  "Enable space diversity on link-A-C",
  "Set ACM range 64QAM to 2048QAM on sector-south links",
  "Enable deep sleep mode during night hours for Sector-North",
  "Turn on MACsec payload encryption on link-D-E",
  "Configure PTP SyncE timing profile G.8275.1 on node-A",
];
const MODEL_COLORS = {
  "IP-50FX": "#00d4ff",
  "IP-20N":  "#7c3aed",
  "IP-20C":  "#ff6b35",
  "IP-20S":  "#00e676",
  "IP-50C":  "#f59e0b",
  "Universal-SDR": "#ff4757",
  "Generic": "#7a91a8"
};

// ── State ─────────────────────────────────────────────────────────────────────
let topology = { nodes: [], links: [] };
let intents = {};
let telemetry = {};
let statusFilter = "";

// ── Socket.IO ─────────────────────────────────────────────────────────────────
// Handle cases where the library might be missing in offline mode
let socket;
if (typeof io !== "undefined") {
  socket = io(window.location.origin, { transports: ["websocket", "polling"] });
} else {
  console.error("Socket.IO library failed to load. Connectivity disabled.");
}

if (socket) {
  socket.on("connect", () => {
    document.getElementById("conn-status").classList.add("connected");
    document.getElementById("conn-label").textContent = "Connected";
    document.getElementById("topology-offline")?.classList.remove("active");
    fetchHealth();
  });
  socket.on("disconnect", () => {
    document.getElementById("conn-status").classList.remove("connected");
    document.getElementById("conn-label").textContent = "Disconnected";
    document.getElementById("topology-offline")?.classList.add("active");
  });
  socket.on("initial_state", (data) => {
    if (data.topology) setTopology(data.topology);
    if (data.intents) data.intents.forEach(i => (intents[i.intent_id] = i));
    if (data.telemetry) {
      data.telemetry.forEach(l => (telemetry[l.link_id] = l));
      updateTelemetryTable();
    }
    renderIntents();
  });
  socket.on("telemetry_update", (data) => {
    data.links.forEach(l => (telemetry[l.link_id] = l));
    updateTelemetryTable();
    updateTopologyLinkColors();
    fetchAuditLog();
  });
  socket.on("intent_update", (intent) => {
    intents[intent.intent_id] = intent;
    renderIntents();
  });
  socket.on("intent_drift", (data) => {
    appendAuditEntry({
      event_type: "INTENT_DRIFT", level: "WARN",
      timestamp: data.timestamp,
      detail: `Drift on ${data.target}: ${data.drift}`,
    });
    if (intents[data.intent_id]) {
      intents[data.intent_id].status = "drift";
      renderIntents();
    }
  });
}

async function approveIntent(id) {
  const btn = document.getElementById("btn-approve-intent");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="spin">⬡</span> Processing…`;
  }
  
  try {
    const res = await fetch(`${API}/api/v1/intents/${id}/approve`, {
      method: "POST"
    });
    if (res.ok) {
      document.getElementById("modal-overlay").classList.add("hidden");
    } else {
      const contentType = res.headers.get("content-type");
      if (contentType && contentType.includes("application/json")) {
        const err = await res.json();
        alert(`Approval failed: ${err.error || res.statusText}`);
      } else {
        alert(`Approval failed: Server returned ${res.statusText} (Likely offline)`);
      }
    }
  } catch (err) {
    alert(`Network Error: ${err.message}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "🚀 Approve & Execute Strategy";
    }
  }
}

// ── Initial Load ──────────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", () => {
  loadExamples();
  fetchTopology();
  fetchAuditLog();
  setupSubmitForm();
  setupFilters();
  setupModal();

  // Periodic audit log refresh
  setInterval(fetchAuditLog, 8000);
});

// ── Topology ──────────────────────────────────────────────────────────────────
async function fetchTopology() {
  try {
    const res = await fetch(`${API}/api/v1/topology`);
    const data = await res.json();
    setTopology(data);
  } catch (e) {
    console.warn("Topology fetch failed:", e);
  }
}

function setTopology(data) {
  topology = data;
  document.getElementById("stat-devices").textContent = (data.nodes || []).length;
  document.getElementById("stat-links").textContent   = (data.links  || []).length;
  initTopologySVG();
}

let simulation, svg, linkEls, nodeEls, linkTooltip;

// Navigation State
let svgViewBox = { x: -50, y: -50, w: 1100, h: 900 };
let isDraggingMap = false;
let startPanPos = { x: 0, y: 0 };

function initTopologySVG() {
  const container = document.getElementById("topology-svg-container");
  const svgEl = document.getElementById("topology-svg");
  if (!svgEl) return;
  svgEl.innerHTML = "";

  const W = container.clientWidth  || 700;
  const H = container.clientHeight || 340;

  // Set viewBox for scaling
  svgEl.setAttribute("viewBox", `${svgViewBox.x} ${svgViewBox.y} ${svgViewBox.w} ${svgViewBox.h}`); 
  svgEl.style.width  = "100%";
  svgEl.style.height = "100%";
  svgEl.style.cursor = "grab";

  // Prevent duplicate bindings if re-inited
  svgEl.onwheel = null;
  svgEl.onmousedown = null;
  svgEl.onmousemove = null;
  svgEl.onmouseup = null;
  svgEl.onmouseleave = null;

  svgEl.onwheel = (e) => {
    e.preventDefault();
    const zoomFactor = e.deltaY > 0 ? 1.1 : 0.9;
    svgViewBox.w *= zoomFactor;
    svgViewBox.h *= zoomFactor;
    // Zoom toward center roughly
    svgViewBox.x += (svgViewBox.w / zoomFactor - svgViewBox.w) / 2;
    svgViewBox.y += (svgViewBox.h / zoomFactor - svgViewBox.h) / 2;
    svgEl.setAttribute("viewBox", `${svgViewBox.x} ${svgViewBox.y} ${svgViewBox.w} ${svgViewBox.h}`);
  };

  svgEl.onmousedown = (e) => {
    isDraggingMap = true;
    svgEl.style.cursor = "grabbing";
    startPanPos = { x: e.clientX, y: e.clientY };
  };

  svgEl.onmousemove = (e) => {
    if (!isDraggingMap) return;
    const dx = e.clientX - startPanPos.x;
    const dy = e.clientY - startPanPos.y;
    startPanPos = { x: e.clientX, y: e.clientY };
    
    // Scale movement by viewBox ratio
    const rect = svgEl.getBoundingClientRect();
    const scaleX = svgViewBox.w / rect.width;
    const scaleY = svgViewBox.h / rect.height;
    
    svgViewBox.x -= dx * scaleX;
    svgViewBox.y -= dy * scaleY;
    svgEl.setAttribute("viewBox", `${svgViewBox.x} ${svgViewBox.y} ${svgViewBox.w} ${svgViewBox.h}`);
  };

  const stopDrag = () => { isDraggingMap = false; svgEl.style.cursor = "grab"; };
  svgEl.onmouseup = stopDrag;
  svgEl.onmouseleave = stopDrag;

  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  const marker = document.createElementNS("http://www.w3.org/2000/svg", "marker");
  marker.setAttribute("id", "arrow");
  marker.setAttribute("viewBox", "0 -5 10 10");
  marker.setAttribute("refX", "20");
  marker.setAttribute("refY", "0");
  marker.setAttribute("markerWidth", "6");
  marker.setAttribute("markerHeight", "6");
  marker.setAttribute("orient", "auto");
  const arrowPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
  arrowPath.setAttribute("d", "M0,-5L10,0L0,5");
  arrowPath.setAttribute("fill", "#00d4ff80");
  marker.appendChild(arrowPath);
  defs.appendChild(marker);
  svgEl.appendChild(defs);

  const mainG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  svgEl.appendChild(mainG);

  // Map nodes for link lookup
  const nodeMap = {};
  topology.nodes.forEach(n => { nodeMap[n.id] = n; });

  // Draw Links
  topology.links.forEach(l => {
    const s = nodeMap[l.src];
    const d = nodeMap[l.dst];
    if (!s || !d) return;

    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", s.x);
    line.setAttribute("y1", s.y);
    line.setAttribute("x2", d.x);
    line.setAttribute("y2", d.y);
    line.setAttribute("class", `topo-link topo-link-${l.status} ${l.role || 'mw'}`);
    line.setAttribute("id", `link-el-${l.id}`);
    
    line.addEventListener("mouseover", (e) => showLinkTooltip(e, l));
    line.addEventListener("mousemove", (e) => moveLinkTooltip(e));
    line.addEventListener("mouseleave", hideLinkTooltip);
    
    mainG.appendChild(line);
  });

  // Draw Nodes
  topology.nodes.forEach(n => {
    const nodeG = document.createElementNS("http://www.w3.org/2000/svg", "g");
    nodeG.setAttribute("class", `topo-node ${n.role || 'transport'}`);
    nodeG.setAttribute("transform", `translate(${n.x},${n.y})`);
    nodeG.setAttribute("id", `node-el-${n.id}`);

    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("r", "20");
    const color = MODEL_COLORS[n.model] || "#00d4ff";
    circle.setAttribute("fill", color + "33");
    circle.setAttribute("stroke", color);
    circle.style.filter = `drop-shadow(0 0 8px ${color}aa)`;
    
    const textId = document.createElementNS("http://www.w3.org/2000/svg", "text");
    textId.setAttribute("class", "node-name");
    textId.setAttribute("dy", "-30");
    textId.setAttribute("text-anchor", "middle");
    textId.textContent = n.id.replace("node-", "");

    const textModel = document.createElementNS("http://www.w3.org/2000/svg", "text");
    textModel.setAttribute("class", "node-model");
    textModel.setAttribute("dy", "40");
    textModel.setAttribute("text-anchor", "middle");
    textModel.textContent = n.model;

    nodeG.appendChild(circle);
    nodeG.appendChild(textId);
    nodeG.appendChild(textModel);
    
    if (n.role !== 'oran') {
      nodeG.addEventListener("click", () => showDeviceModal(n));
      nodeG.style.cursor = "pointer";
    }

    mainG.appendChild(nodeG);
  });

  // Tooltip setup
  if (!linkTooltip) {
    linkTooltip = document.createElement("div");
    linkTooltip.className = "link-tooltip";
    container.appendChild(linkTooltip);
  }
}

function showLinkTooltip(e, d) {
  const tel = telemetry[d.id] || {};
  linkTooltip.innerHTML = `
    <div style="font-weight:600;color:#00d4ff;margin-bottom:4px">${d.id}</div>
    <div>${d.src} ↔ ${d.dst}</div>
    <div style="color:#7a91a8">Distance: ${d.distance_km || 0} km</div>
    <div style="margin-top:6px">
      SNR: <b>${tel.snr_db ?? '—'} dB</b> · Mod: <b>${tel.current_modulation ?? '—'}</b><br>
      Throughput: <b>${tel.throughput_gbps ?? '—'} Gbps</b> · Loss: <b>${tel.packet_loss_pct ?? 0}%</b>
    </div>`;
  linkTooltip.classList.add("visible");
  moveLinkTooltip(e);
}
function moveLinkTooltip(e) {
  const r = linkTooltip.parentElement.getBoundingClientRect();
  let x = e.clientX - r.left + 12, y = e.clientY - r.top + 12;
  if (x + 200 > r.width) x -= 210;
  linkTooltip.style.left = x + "px";
  linkTooltip.style.top  = y + "px";
}
function hideLinkTooltip() { linkTooltip.classList.remove("visible"); }

function updateTopologyLinkColors() {
  topology.links.forEach(l => {
    const tel = telemetry[l.id];
    if (!tel) return;
    const el = document.getElementById(`link-el-${l.id}`);
    if (!el) return;

    // Remove status classes
    el.classList.remove("topo-link-active", "topo-link-degraded", "topo-link-down");
    // Add correct status class
    el.classList.add(`topo-link-${tel.status}`);

    // Pulse on high utilization
    if (tel.utilization > 0.85) {
      el.style.strokeOpacity = 0.5 + 0.5 * Math.sin(Date.now() / 600);
    } else {
      el.style.strokeOpacity = null;
    }
  });
}

// ── Telemetry Table ───────────────────────────────────────────────────────────
function updateTelemetryTable() {
  const tbody = document.getElementById("tel-tbody");
  const rows = Object.values(telemetry);
  rows.sort((a, b) => a.link_id.localeCompare(b.link_id));

  tbody.innerHTML = rows.map(t => {
    const utilPct = Math.round(t.utilization * 100);
    const utilColor = utilPct > 85 ? "#ff4757" : utilPct > 65 ? "#ffa726" : "#00e676";
    const modClass = modCssClass(t.current_modulation);
    return `
      <tr class="${t.status === "degraded" ? "degraded" : ""}">
        <td><b>${t.link_id.replace("link-","")}</b></td>
        <td><span style="color:${t.status==="active"?"#00e676":t.status==="degraded"?"#ffa726":"#ff4757"}">${t.status}</span></td>
        <td>${t.snr_db}</td>
        <td><span class="${modClass}">${t.current_modulation}</span></td>
        <td>${t.throughput_gbps} / ${t.capacity_gbps} G</td>
        <td>
          <div class="util-bar">
            <div class="util-track"><div class="util-fill" style="width:${utilPct}%;background:${utilColor}"></div></div>
            ${utilPct}%
          </div>
        </td>
        <td>${t.latency_ms} ms</td>
        <td style="color:${t.packet_loss_pct > 0.5 ? "#ff4757":"#7a91a8"}">${t.packet_loss_pct}%</td>
      </tr>`;
  }).join("");
}

function modCssClass(mod) {
  const map = {
    "QPSK":"mod-qpsk","16QAM":"mod-16qam","32QAM":"mod-32qam","64QAM":"mod-64qam",
    "128QAM":"mod-128qam","256QAM":"mod-256qam","512QAM":"mod-512qam",
    "1024QAM":"mod-1024qam","2048QAM":"mod-2048qam"
  };
  return map[mod] || "mod-256qam";
}

// ── Intent Submission ─────────────────────────────────────────────────────────
function loadExamples() {
  const row = document.getElementById("examples-row");
  EXAMPLES.forEach(ex => {
    const chip = document.createElement("div");
    chip.className = "example-chip";
    chip.textContent = ex.length > 40 ? ex.slice(0, 40) + "…" : ex;
    chip.title = ex;
    chip.addEventListener("click", () => {
      document.getElementById("nl-input").value = ex;
      document.getElementById("tab-nl").click();
    });
    row.appendChild(chip);
  });
}

function setupSubmitForm() {
  // Mode tabs
  document.getElementById("tab-nl").addEventListener("click", () => setMode("nl"));
  document.getElementById("tab-json").addEventListener("click", () => setMode("json"));

  document.getElementById("btn-submit").addEventListener("click", submitIntent);
  document.getElementById("nl-input").addEventListener("keydown", e => {
    if (e.ctrlKey && e.key === "Enter") submitIntent();
  });

  // Open/close intent form
  document.getElementById("btn-open-intent").addEventListener("click", () => {
    document.getElementById("nl-input").focus();
    document.getElementById("panel-intent-input").scrollIntoView({ behavior: "smooth" });
  });

  document.getElementById("btn-clear-intents").addEventListener("click", async () => {
    if (!confirm("Clear all intents from this session?")) return;
    Object.keys(intents).forEach(id => delete intents[id]);
    renderIntents();
  });
}

function setMode(mode) {
  document.getElementById("mode-nl").classList.toggle("hidden", mode !== "nl");
  document.getElementById("mode-json").classList.toggle("hidden", mode !== "json");
  document.getElementById("tab-nl").classList.toggle("active", mode === "nl");
  document.getElementById("tab-json").classList.toggle("active", mode !== "nl");
}

async function submitIntent() {
  const mode = document.getElementById("mode-json").classList.contains("hidden") ? "nl" : "json";
  const nlInput = document.getElementById("nl-input").value.trim();
  const jsonInput = document.getElementById("json-input").value.trim();
  const raw = mode === "nl" ? nlInput : jsonInput;

  if (!raw) return;

  const priority = document.getElementById("intent-priority").value;
  const source   = document.getElementById("intent-source").value;
  const alwaysApply = document.getElementById("check-auto-apply").checked;

  const btn = document.getElementById("btn-submit");
  const result = document.getElementById("submit-result");
  btn.classList.add("loading");
  btn.textContent = "⟳ Processing…";
  result.className = "submit-result hidden";

  let body;
  if (mode === "json") {
    try { 
      const json = JSON.parse(raw);
      body = { intent: json, source, priority: parseInt(priority), always_apply: alwaysApply }; 
    }
    catch { body = { intent: raw, source, priority: parseInt(priority), always_apply: alwaysApply }; }
  } else {
    body = { 
      intent: nlInput,
      source, 
      priority: parseInt(priority),
      always_apply: alwaysApply 
    };
  }

  try {
    const res = await fetch(`${API}/api/v1/intent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const contentType = res.headers.get("content-type");
    if (!res.ok && (!contentType || !contentType.includes("application/json"))) {
        result.className = "submit-result error fade-in";
        result.innerHTML = `❌ Connection Error: Backend server is offline or proxy returned ${res.status} ${res.statusText}.`;
        return;
    }

    const data = await res.json();

    if (res.ok) {
      result.className = "submit-result success fade-in";
      const targetName = data.target_name || data.target?.identifier || data.target || "Unknown Target";
      const typeLabel = (data.intent_type || "Intent").toUpperCase();
      result.innerHTML = `
        ✅ <b>${typeLabel}</b> intent processed for <b>${targetName}</b><br>
        <small>${data.explanation || ""}</small><br>
        <small style="color:#4a5f72">${data.configs_applied || 0}/${data.configs_total || 0} configs applied · ${data.backend || "AI Architect"}</small>
        ${data.warnings?.length ? `<br><small style="color:#ffa726">⚠ ${data.warnings.join(" · ")}</small>` : ""}
      `;
      document.getElementById("nl-input").value = "";
      // Fetch updated intents
      fetchIntents();
    } else {
      result.className = "submit-result error fade-in";
      result.innerHTML = `❌ <b>${data.status}</b>: ${(data.errors || [data.error]).join(", ")}`;
    }
  } catch (e) {
    result.className = "submit-result error fade-in";
    result.innerHTML = `❌ Network error: ${e.message}`;
  }

  btn.classList.remove("loading");
  btn.textContent = "⚡ Submit Intent";
  result.classList.remove("hidden");
}

// ── Intent List ───────────────────────────────────────────────────────────────
function setupFilters() {
  document.getElementById("intent-status-filter").addEventListener("change", e => {
    statusFilter = e.target.value;
    renderIntents();
  });
}

async function fetchIntents() {
  try {
    const res = await fetch(`${API}/api/v1/intents?limit=50`);
    const data = await res.json();
    data.forEach(i => (intents[i.intent_id] = i));
    renderIntents();
  } catch (e) {}
}

function renderIntents() {
  const list = document.getElementById("intents-list");
  const empty = document.getElementById("intents-empty");
  const badge = document.getElementById("intent-count");

  let items = Object.values(intents).sort((a, b) =>
    new Date(b.submitted_at) - new Date(a.submitted_at)
  );
  if (statusFilter) items = items.filter(i => i.status === statusFilter);

  badge.textContent = Object.keys(intents).length;
  document.getElementById("stat-intents").textContent = Object.keys(intents).length;

  if (items.length === 0) {
    empty.classList.remove("hidden");
    list.querySelectorAll(".intent-card").forEach(el => el.remove());
    return;
  }
  empty.classList.add("hidden");

  list.innerHTML = items.map(i => {
    const type = i.intent_type || "unknown";
    const target = i.target_name || i.target?.identifier || "—";
    const status = (i.status || "pending").toUpperCase();
    return `
    <div class="intent-card status-${i.status || 'pending'} fade-in"
         data-id="${i.intent_id}" id="card-${i.intent_id}" role="button" tabindex="0">
      <div class="intent-card-header">
        <div style="display:flex; align-items:center; gap:0.4rem;">
          <span class="intent-type-badge type-${type}">${type}</span>
          <span class="intent-status st-${i.status || 'pending'}">
            ${i.status === "drift" ? '<span class="drift-icon">⚠</span> ' : ""}
            ${status}
          </span>
        </div>
        ${(i.status === 'applied' || i.status === 'failed' || i.status === 'rejected') ? `<button class="btn-delete-intent" data-id="${i.intent_id}" title="Remove Intent">✕</button>` : ""}
      </div>
      <div class="intent-target">→ ${target}</div>
      <div class="intent-summary">${i.summary || "Processing intent..." }</div>
    </div>
  `}).join("");

  list.querySelectorAll(".intent-card").forEach(card => {
    card.addEventListener("click", (e) => {
      // If delete button clicked, don't show modal
      if (e.target.closest('.btn-delete-intent')) {
        e.stopPropagation();
        deleteIntent(card.dataset.id);
        return;
      }
      showIntentModal(intents[card.dataset.id]);
    });
    card.addEventListener("keydown", e => { if (e.key === "Enter") showIntentModal(intents[card.dataset.id]); });
  });
}

async function deleteIntent(id) {
  try {
    const res = await fetch(`${API}/api/v1/intents/${id}`, { method: 'DELETE' });
    if (res.ok) {
      delete intents[id];
      renderIntents();
    }
  } catch (e) {
    console.error("Failed to delete intent", e);
  }
}


// ── Device Modal ──────────────────────────────────────────────────────────────
async function showDeviceModal(node) {
  const [stateRes, profileRes] = await Promise.all([
    fetch(`${API}/api/v1/devices/${node.id}/state`),
    fetch(`${API}/api/v1/hardware/profiles/${node.model}`)
  ]);
  
  const state = await stateRes.json();
  const profile = await profileRes.json();
  const configs = state.configs || {};

  const body = document.getElementById("modal-body");
  
  // Hardware Capabilities Section
  const caps = profile.capabilities || {};
  const capsHtml = Object.values(caps).map(c => `
    <div class="modal-row" style="font-size:0.75rem">
      <span class="modal-label">${c.name}</span>
      <span class="modal-value">${c.value} ${c.unit}</span>
    </div>
  `).join("");

  body.innerHTML = `
    <div class="modal-row"><span class="modal-label">Device ID</span><span class="modal-value">${node.id}</span></div>
    <div class="modal-row"><span class="modal-label">Name</span><span class="modal-value">${node.name}</span></div>
    <div class="modal-row"><span class="modal-label">Model</span><span class="modal-value" style="color:${MODEL_COLORS[node.model] || MODEL_COLORS.Generic}">${node.model}</span></div>
    <div class="modal-row"><span class="modal-label">Vendor</span><span class="modal-value">${profile.vendor || 'Unknown'}</span></div>
    
    <div class="section-title" style="margin-top:0.5rem">Hardware Capabilities</div>
    ${capsHtml}
    
    <div class="section-title" style="margin-top:0.5rem">API / Configuration Guide</div>
    <p style="font-size:0.75rem; color:var(--text-secondary); line-height:1.4; background:var(--bg-base); padding:0.6rem; border-radius:6px; font-style:italic">
      ${profile.api_guide || 'No specific guide available for this model.'}
    </p>

    <div class="section-title" style="margin-top:0.5rem">Applied Configurations</div>
    ${Object.entries(configs).length === 0
      ? '<div style="color:#4a5f72;font-size:0.8rem">No configurations applied yet</div>'
      : Object.entries(configs).map(([type, cfg]) => `
          <div style="margin-bottom:0.6rem">
            <div style="font-size:0.72rem;color:#7a91a8;margin-bottom:3px;text-transform:uppercase">${type}</div>
            <div class="code-block">${JSON.stringify(cfg.parameters, null, 2)}</div>
            ${cfg.yang_xml_snippet ? `
              <button class="btn btn-ghost" style="margin-top:4px;font-size:0.72rem"
                onclick="showYANG(\`${escapeBacktick(cfg.yang_xml_snippet)}\`, '${type}')">
                📄 View NETCONF XML
              </button>` : ""}
          </div>`).join("")
    }
  `;
  document.getElementById("modal-title").textContent = `Device: ${node.id}`;
  document.getElementById("modal-overlay").classList.remove("hidden");
}

function showIntentModal(intent) {
  if (!intent) return;
  const body = document.getElementById("modal-body");
  const params = intent.parameters || {};
  const applied = intent.applied_config || {};
  const architect = intent.architect_plan || {};

  let strategyHtml = "";
  if (architect.selected_strategy) {
    const s = architect.selected_strategy;
    const cr = architect.conflict_report || {};
    
    strategyHtml = `
      <div class="section-title" style="margin-top:0.8rem; display:flex; justify-content:space-between; align-items:center">
        <span>Intent Architect Selection</span>
        ${cr.level ? `
          <span class="conflict-badge conflict-${cr.level}" title="${cr.message}">
            🛡️ Conflict: ${cr.level.toUpperCase()}
          </span>
        ` : ""}
      </div>
      <div style="background:rgba(0, 212, 255, 0.1); border:1px solid #00d4ff44; border-radius:8px; padding:0.8rem; margin-top:0.4rem">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem">
          <span style="font-weight:700; color:#00d4ff; font-size:0.85rem">${s.name.replace(/_/g,' ')}</span>
          <span class="badge" style="background:#00d4ff; color:black; padding:2px 6px; border-radius:4px; font-size:0.7rem; font-weight:bold">Conf: ${Math.round(s.confidence*100)}%</span>
        </div>
        <div style="font-size:0.75rem; color:#e0e0e0; margin-bottom:0.4rem">${s.description}</div>
        <div style="font-size:0.7rem; color:#7a91a8; font-style:italic">Rationale: ${s.rationale}</div>
      </div>

      ${cr.conflicts?.length > 0 ? `
        <div class="conflict-list">
          ${cr.conflicts.map(c => `
            <div class="conflict-item ${c.severity === 'CRITICAL' ? 'crit' : ''}">
              <span class="conflict-item-title">[${c.severity}] ${c.type}</span>
              <span class="conflict-item-desc">${c.description}</span>
            </div>
          `).join('')}
        </div>
      ` : ""}
      
      <div class="section-title" style="margin-top:1.2rem; margin-bottom:0.8rem; font-size:0.75rem">Intent Architect Engine — Reasoning Process</div>
      <div class="agent-chat-container">
        ${(architect.reasoning_trace || []).map(line => {
           let tag = 'unknown';
           let content = line;
           const match = line.match(/^\[([A-Z]+)\] (.*)$/);
           if (match) {
             tag = match[1].toLowerCase();
             content = match[2];
           } else if (line.startsWith('  > [')) {
             tag = 'conflict';
             content = line.replace('  > ', '');
           }
           let icon = '⚡';
           if (tag === 'thought') icon = '🧠';
           if (tag === 'observation') icon = '🔎';
           if (tag === 'evaluation') icon = '⚖️';
           if (tag === 'decision') icon = '🎯';
           if (tag === 'action') icon = '🚀';
           if (tag === 'conflict') icon = '🛡️';
           
           return `
             <div class="chat-bubble chat-${tag}">
                <div class="chat-icon">${icon}</div>
                <div class="chat-content">
                  <div class="chat-tag">${tag.toUpperCase()}</div>
                  <div class="chat-text">${content}</div>
                </div>
             </div>
           `;
        }).join('')}
      </div>
    `;
  }

  body.innerHTML = `
    <div class="modal-row"><span class="modal-label">ID</span><span class="modal-value modal-badge" style="font-size:0.72rem">${intent.intent_id}</span></div>
    <div class="modal-row"><span class="modal-label">Type</span><span class="modal-value"><span class="intent-type-badge type-${intent.intent_type}">${intent.intent_type}</span></span></div>
    <div class="modal-row"><span class="modal-label">Status</span><span class="modal-value st-${intent.status}">${intent.status?.toUpperCase()}</span></div>
    <div class="modal-row"><span class="modal-label">Target</span><span class="modal-value">${intent.target?.target_type} : ${intent.target?.identifier}</span></div>
    
    ${intent.raw_input ? `<div class="section-title" style="margin-top:0.5rem">Original Input</div>
      <div class="code-block">${escape(intent.raw_input)}</div>` : ""}
    
    ${strategyHtml}

    <div class="section-title" style="margin-top:0.8rem">Effective Parameters</div>
    <div class="code-block">${JSON.stringify(params, null, 2)}</div>
    
    ${applied.explanation ? `<div class="modal-row" style="margin-top:0.5rem"><span class="modal-label">Translator Note</span><span class="modal-value" style="font-size:0.78rem">${applied.explanation}</span></div>` : ""}
    ${applied.configs?.length ? `
      <button class="btn btn-ghost" style="font-size:0.75rem; margin-top:0.5rem"
        onclick="showYANG(\`${escapeBacktick(applied.configs[0]?.yang_xml || "")}\`,'NETCONF Config')">
        📄 View Applied NETCONF XML
      </button>` : ""}
    ${intent.error_message ? `<div class="submit-result error" style="margin-top:0.4rem">❌ ${intent.error_message}</div>` : ""}
    
    ${intent.status === 'awaiting_approval' ? `
      <div style="margin-top:1.2rem; padding-top:1rem; border-top:1px solid var(--border); display:flex; justify-content:flex-end">
        <button class="btn btn-primary" id="btn-approve-intent" 
          onclick="approveIntent('${intent.intent_id}')" style="padding:0.6rem 1.5rem">
          🚀 Approve & Execute Strategy
        </button>
      </div>` : ""}
  `;
  document.getElementById("modal-title").textContent = `${intent.intent_type?.toUpperCase()} Intent Analysis`;
  document.getElementById("modal-overlay").classList.remove("hidden");
}

function showYANG(xml, title) {
  document.getElementById("drawer-title").textContent = title || "NETCONF Config";
  document.getElementById("yang-content").textContent = xml;
  document.getElementById("drawer-overlay").classList.remove("hidden");
}

function setupModal() {
  document.getElementById("modal-close").addEventListener("click", () =>
    document.getElementById("modal-overlay").classList.add("hidden"));
  document.getElementById("modal-overlay").addEventListener("click", e => {
    if (e.target === document.getElementById("modal-overlay"))
      document.getElementById("modal-overlay").classList.add("hidden");
  });
  document.getElementById("drawer-close").addEventListener("click", () =>
    document.getElementById("drawer-overlay").classList.add("hidden"));
  document.getElementById("drawer-overlay").addEventListener("click", e => {
    if (e.target === document.getElementById("drawer-overlay"))
      document.getElementById("drawer-overlay").classList.add("hidden");
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      document.getElementById("modal-overlay").classList.add("hidden");
      document.getElementById("drawer-overlay").classList.add("hidden");
    }
  });
}

// ── Audit Log ─────────────────────────────────────────────────────────────────
async function fetchAuditLog() {
  try {
    const res = await fetch(`${API}/api/v1/audit-log?limit=40`);
    const entries = await res.json();
    const container = document.getElementById("audit-log-container");
    if (!entries.length) return;
    container.innerHTML = entries.reverse().map(e => formatAuditEntry(e)).join("");
  } catch (e) {}
}

function appendAuditEntry(entry) {
  const container = document.getElementById("audit-log-container");
  const el = document.createElement("div");
  el.innerHTML = formatAuditEntry(entry);
  container.insertAdjacentHTML("afterbegin", formatAuditEntry(entry));
  // Trim
  while (container.children.length > 40) container.lastChild.remove();
}

function formatAuditEntry(e) {
  const time = new Date(e.timestamp).toLocaleTimeString("en-US", { hour12: false });
  const type = e.event_type || e.level || "INFO";
  const levelClass = `at-${e.level || "INFO"}`;
  const typeClass  = `at-${type}`;
  const msg = e.message || e.explanation || e.detail ||
    (e.intent_id ? `Intent ${e.intent_id.slice(0,8)} — ${type.replace(/_/g," ")}` : type.replace(/_/g," "));
  return `<div class="audit-entry">
    <span class="audit-time">${time}</span>
    <span class="audit-type ${typeClass}">${type.replace("_"," ").slice(0,12)}</span>
    <span class="audit-msg">${msg}</span>
  </div>`;
}

// ── Health ────────────────────────────────────────────────────────────────────
async function fetchHealth() {
  try {
    const res = await fetch(`${API}/api/v1/health`);
    const data = await res.json();
    document.getElementById("stat-backend").textContent =
      (data.adapter_backend || "—").replace("Adapter","");
  } catch (e) {}
  fetchIntents();
  fetchTopology();
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function escape(str) {
  return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
function escapeBacktick(str) {
  return (str || "").replace(/`/g, "\\`");
}

// Topology filter chips
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".chip[data-filter]").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".chip[data-filter]").forEach(c => c.classList.remove("chip-active"));
      chip.classList.add("chip-active");
      // Filter links in topology
      if (!linkEls) return;
      const f = chip.dataset.filter;
      linkEls.style("opacity", d => f === "all" || d.status === f ? 1 : 0.15);
    });
  });
});
