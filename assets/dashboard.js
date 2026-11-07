const C = {
  amber: "#b45309", teal: "#0f766e", green: "#15803d", red: "#b91c1c",
  blue: "#1d4ed8", muted: "#6a7280", border: "#e3e1da", ink: "#1b1f27",
  neutral: "#d8dbe0",
};

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]
  ));
}

function fmt(n) {
  if (n == null) return "—";
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(2) + "M";
  if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return String(n);
}

Chart.defaults.color = C.muted;
Chart.defaults.borderColor = C.border;
Chart.defaults.font.family = "'JetBrains Mono', monospace";
Chart.defaults.font.size = 11;

const charts = {};

function upsertChart(id, config) {
  if (charts[id]) {
    charts[id].data = config.data;
    charts[id].update();
    return charts[id];
  }
  charts[id] = new Chart(document.getElementById(id), config);
  return charts[id];
}

function barConfig(labels, data, color) {
  return {
    type: "bar",
    data: { labels, datasets: [{ data, backgroundColor: color, borderRadius: 2, borderSkipped: false, maxBarThickness: 34 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { color: C.muted } },
        y: { beginAtZero: true, grid: { color: C.border }, ticks: { color: C.muted } },
      },
    },
  };
}

function doughnutConfig(labels, data, colors) {
  return {
    type: "doughnut",
    data: { labels, datasets: [{ data, backgroundColor: colors, borderColor: "#ffffff", borderWidth: 2 }] },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "62%",
      plugins: { legend: { position: "bottom", labels: { color: C.muted, usePointStyle: true, boxWidth: 8, padding: 12 } } },
    },
  };
}

function cmpChart(id, labels, flopArr, viralArr) {
  upsertChart(id, {
    type: "bar",
    data: { labels, datasets: [
      { label: "Flop", data: flopArr, backgroundColor: C.red, borderRadius: 2, borderSkipped: false },
      { label: "Viral", data: viralArr, backgroundColor: C.teal, borderRadius: 2, borderSkipped: false },
    ] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: "top", labels: { color: C.muted, usePointStyle: true, boxWidth: 8, padding: 8 } } },
      scales: {
        x: { grid: { display: false }, ticks: { color: C.muted } },
        y: { beginAtZero: true, grid: { color: C.border }, ticks: { color: C.muted, callback: (v) => v + "%" } },
      },
    },
  });
}

function renderStrip(latest, channels, totals) {
  const el = document.getElementById("strip");
  const total = channels.reduce((s, c) => s + Number(c.videos_count || 0), 0);
  const eligible = channels.reduce((s, c) => s + Number(c.eligible_count || 0), 0);
  const stats = [
    { label: "Videos", value: fmt(totals ? totals.videos : total), icon: "fa-film", cls: "" },
    { label: "Analysis eligible", value: fmt(totals ? totals.eligible : eligible), icon: "fa-check-double", cls: "" },
    { label: "Flops", value: fmt(totals ? totals.flops : null), icon: "fa-arrow-trend-down", cls: "c-red" },
    { label: "Virals", value: fmt(totals ? totals.virals : null), icon: "fa-bolt", cls: "c-teal" },
    { label: "Median virality", value: totals && totals.median_virality != null ? Number(totals.median_virality).toFixed(2) : "—", icon: "fa-gauge", cls: "" },
    { label: "Channels", value: fmt(channels.length), icon: "fa-tower-broadcast", cls: "" },
  ];
  el.innerHTML = stats.map((s) =>
    `<div class="stat"><i class="fa-solid ${s.icon}"></i>` +
    `<div class="stat-v ${s.cls}">${esc(s.value)}</div>` +
    `<div class="stat-l">${s.label}</div></div>`
  ).join("");
}

function renderRun(latest) {
  const el = document.getElementById("runline");
  const running = latest.status === "running";
  el.innerHTML =
    `<span class="run-tag">RUN ${esc(latest.run_id || "—")}</span>` +
    (running ? `<span class="run-item run-live"><i class="fa-solid fa-circle-notch fa-spin"></i> running</span>` : "") +
    `<span class="run-item">attempted <b>${esc(latest.channels_attempted ?? 0)}</b></span>` +
    `<span class="run-item ok">success <b>${esc(latest.channels_success ?? 0)}</b></span>` +
    `<span class="run-item bad">failed <b>${esc(latest.channels_failed ?? 0)}</b></span>` +
    `<span class="run-item">skipped <b>${esc(latest.channels_skipped ?? 0)}</b></span>` +
    `<span class="run-item">new <b>${esc(latest.videos_new ?? 0)}</b></span>` +
    `<span class="run-time">${esc(latest.started_at || "")}</span>`;
}

function renderHistory(history) {
  const el = document.getElementById("run-history");
  if (!history || !history.length) { el.innerHTML = `<tr><td class="empty">No completed runs yet.</td></tr>`; return; }
  const rows = history.slice().reverse().map((r) =>
    `<tr><td>${esc(r.run_id)}</td><td>${esc(r.started_at)}</td>` +
    `<td class="st-${esc(r.status)}">${esc(r.status)}</td>` +
    `<td>${esc(r.channels_success)}/${esc(r.channels_attempted)}</td>` +
    `<td>${esc(r.videos_new)}</td><td>${esc(r.videos_total)}</td></tr>`
  ).join("");
  el.innerHTML = `<thead><tr><th>Run</th><th>Started</th><th>Status</th><th>Channels</th><th>New</th><th>Total</th></tr></thead><tbody>${rows}</tbody>`;
}

function renderChannels(channels) {
  const el = document.getElementById("channels");
  if (!channels.length) { el.innerHTML = `<tr><td class="empty">No channels yet.</td></tr>`; return; }
  const rows = channels.map((c) =>
    `<tr><td>${esc(c.title)}</td><td>${esc(c.niche)}</td><td>${esc(c.subs)}</td>` +
    `<td>${c.videos_count}</td><td>${c.eligible_count}</td>` +
    `<td class="st-${esc(c.status)}"><i class="fa-solid fa-circle"></i> ${esc(c.status)}</td></tr>`
  ).join("");
  el.innerHTML =
    `<thead><tr><th>Channel</th><th>Niche</th><th>Subs</th><th>Videos</th><th>Eligible</th><th>Status</th></tr></thead>` +
    `<tbody>${rows}</tbody>`;
}

function renderInsights(ins) {
  if (!ins) return;
  const t = ins.totals || {};

  upsertChart("c-virality", doughnutConfig(
    ["Flops", "Virals", "Neutral", "Unknown score"],
    [t.flops || 0, t.virals || 0, t.neutral || 0, t.unknown || 0],
    [C.red, C.teal, C.neutral, C.muted]
  ));

  upsertChart("c-niche", doughnutConfig(
    (ins.by_niche || []).map((n) => n.niche),
    (ins.by_niche || []).map((n) => n.videos),
    [C.amber, C.teal, C.blue, C.green]
  ));

  upsertChart("c-band", barConfig(
    (ins.by_band || []).map((b) => b.band),
    (ins.by_band || []).map((b) => b.videos),
    C.amber
  ));

  upsertChart("c-viral-hist", barConfig(
    (ins.virality_histogram || []).map((b) => b.bucket),
    (ins.virality_histogram || []).map((b) => b.count),
    C.teal
  ));

  upsertChart("c-views", barConfig(
    (ins.view_histogram || []).map((b) => b.bucket),
    (ins.view_histogram || []).map((b) => b.count),
    C.blue
  ));

  upsertChart("c-hour", barConfig(
    (ins.publish_hour || []).map((b) => b.hour),
    (ins.publish_hour || []).map((b) => b.count),
    C.green
  ));

  upsertChart("c-day", barConfig(
    (ins.publish_day || []).map((b) => b.day),
    (ins.publish_day || []).map((b) => b.count),
    C.amber
  ));

  upsertChart("c-duration", barConfig(
    (ins.duration_buckets || []).map((b) => b.bucket),
    (ins.duration_buckets || []).map((b) => b.count),
    C.red
  ));

  const tf = ins.title_features || {};
  document.getElementById("title-feats").innerHTML =
    `<div class="feat"><span>${esc(tf.avg_title_length ?? "—")}</span>avg title length</div>` +
    `<div class="feat"><span>${esc(tf.pct_has_number ?? "—")}%</span>titles with a number</div>` +
    `<div class="feat"><span>${esc(tf.pct_has_question ?? "—")}%</span>titles with a question</div>` +
    `<div class="feat"><span>${esc(tf.avg_caps_ratio ?? "—")}</span>avg caps ratio</div>`;
}

function renderComparison(cmp) {
  if (!cmp) return;
  document.getElementById("cmp-totals").innerHTML =
    `<div class="cmp-num red">${fmt(cmp.totals.flops)}<span>flops</span></div>` +
    `<div class="cmp-vs">vs</div>` +
    `<div class="cmp-num teal">${fmt(cmp.totals.virals)}<span>virals</span></div>`;
  let note = document.getElementById("comparison-scope");
  if (!note) {
    note = document.createElement("p"); note.id = "comparison-scope";
    document.getElementById("cmp-totals").after(note);
  }
  note.textContent = `${cmp.scope || "Legacy data"} Sample: ${cmp.sample_videos ?? "?"} videos, ${cmp.sample_channels ?? "?"} channels. Each colour is normalized within its outcome group; percentages are not success probabilities.`;
  cmpChart("c-cmp-hour", cmp.publish_hour.labels, cmp.publish_hour.flop, cmp.publish_hour.viral);
  cmpChart("c-cmp-day", cmp.publish_day.labels, cmp.publish_day.flop, cmp.publish_day.viral);
  cmpChart("c-cmp-duration", cmp.duration_buckets.labels, cmp.duration_buckets.flop, cmp.duration_buckets.viral);
  cmpChart("c-cmp-titlelen", cmp.title_length_buckets.labels, cmp.title_length_buckets.flop, cmp.title_length_buckets.viral);
  cmpChart("c-cmp-flags", cmp.title_flags.labels, cmp.title_flags.flop, cmp.title_flags.viral);
}

function showTab(id) {
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.getElementById(id).classList.add("active");
  document.querySelectorAll(".topnav-tab").forEach((t) => t.classList.remove("active"));
  document.querySelector(`.topnav-tab[data-tab="${id}"]`).classList.add("active");
  if (id === "view-insights" || id === "view-comparison") {
    setTimeout(() => Object.values(charts).forEach((c) => c.resize()), 60);
  }
}

document.querySelectorAll(".topnav-tab[data-tab]").forEach((t) => {
  t.addEventListener("click", (e) => { e.preventDefault(); showTab(t.dataset.tab); });
});

async function refresh() {
  const dot = document.getElementById("status-dot");
  const stxt = document.getElementById("status-text");
  try {
    const [pRes, iRes, cRes] = await Promise.all([
      fetch("data/progress.json"), fetch("data/insights.json"), fetch("data/comparison.json"),
    ]);
    const progress = pRes.ok ? await pRes.json() : {};
    const insights = iRes.ok ? await iRes.json() : null;
    const comparison = cRes.ok ? await cRes.json() : null;
    renderStrip(progress.latest_run || {}, progress.channels || [], insights ? insights.totals : null);
    renderRun(progress.latest_run || {});
    renderHistory(progress.run_history || []);
    renderChannels(progress.channels || []);
    renderInsights(insights);
    renderComparison(comparison);
    dot.className = "dot ok";
    stxt.textContent = "data loaded";
  } catch (e) {
    dot.className = "dot bad";
    stxt.textContent = "no data";
  }
}

function clock() {
  document.getElementById("clock").textContent = new Date().toLocaleTimeString();
}

function schedFormBody() {
  return {
    date: document.getElementById("sched-date").value,
    time: document.getElementById("sched-time").value,
    max_videos: Number(document.getElementById("sched-maxvideos").value) || 200,
    reselect: document.getElementById("sched-reselect").checked,
    per_cell: Number(document.getElementById("sched-percell").value) || 3,
  };
}

function setSchedStatus(msg) {
  document.getElementById("sched-status").textContent = msg;
}

async function submitSchedule(e) {
  e.preventDefault();
  const body = schedFormBody();
  if (!body.date || !body.time) { setSchedStatus("Pick a date and time first."); return; }
  const res = await fetch("/api/schedule", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await res.json();
  setSchedStatus(data.ok ? "Scheduled for " + data.plan.run_at : "Error: " + (data.error || res.status));
  loadSchedule();
}

async function runNow() {
  const body = schedFormBody();
  const res = await fetch("/api/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await res.json();
  setSchedStatus(data.ok ? "Extraction started — watch the Status tab." : "Error: " + (data.error || res.status));
}

async function loadSchedule() {
  try {
    const res = await fetch("/api/schedule");
    const plan = await res.json();
    const el = document.getElementById("sched-current");
    if (plan && plan.run_at) {
      el.innerHTML =
        `<div class="sched-plan">` +
        `<div><span>Run at</span>${esc(plan.run_at)}</div>` +
        `<div><span>Videos/channel</span>${esc(plan.max_videos)}</div>` +
        `<div><span>Per cell</span>${esc(plan.per_cell)}</div>` +
        `<div><span>Re-discover</span>${plan.reselect ? "yes" : "no"}</div>` +
        `</div>`;
    } else {
      el.textContent = "No schedule set.";
    }
  } catch (e) {
    document.getElementById("sched-current").textContent = "—";
  }
}

async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    const cfg = await res.json();
    if (cfg.max_videos) document.getElementById("sched-maxvideos").value = cfg.max_videos;
    if (cfg.per_cell) document.getElementById("sched-percell").value = cfg.per_cell;
  } catch (e) {}
}

function setSyncUI(enabled) {
  document.getElementById("sync-toggle").checked = enabled;
  document.getElementById("sync-sub").textContent = enabled ? "Syncing is on" : "Syncing is off";
}

async function loadSync() {
  try {
    const res = await fetch("/api/sync");
    const data = await res.json();
    setSyncUI(data.enabled);
    if (data.demo) {
      document.querySelectorAll("#sched-form input, #sched-form button, #run-now, #sync-toggle").forEach(el => { el.disabled = true; });
      setSchedStatus("Read-only offline snapshot. Collection and scheduling are disabled.");
      let banner=document.getElementById("snapshot-note");
      if (!banner) { banner=document.createElement("p"); banner.id="snapshot-note"; document.querySelector("main").prepend(banner); }
      const manifest=await (await fetch("data/manifest.json")).json();
      banner.textContent=`Offline snapshot as of ${manifest.as_of}. Status/Insights describe all retained records; Comparison uses ${manifest.qualified_rows} qualified English-tagged videos. Unknown language excluded. Original collection history is preserved.`;
    }
  } catch (e) {}
}

async function toggleSync() {
  const enabled = document.getElementById("sync-toggle").checked;
  try {
    await fetch("/api/sync", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled }) });
    setSyncUI(enabled);
  } catch (e) {}
}

document.getElementById("sched-form").addEventListener("submit", submitSchedule);
document.getElementById("run-now").addEventListener("click", runNow);
document.getElementById("sync-toggle").addEventListener("change", toggleSync);
loadConfig();
loadSchedule();
loadSync();

refresh();
setInterval(refresh, 10000);
setInterval(clock, 1000);
clock();
