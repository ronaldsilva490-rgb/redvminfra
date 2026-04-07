const state = {
  status: null,
  models: [],
  riskProfiles: {},
  selectedSymbol: "BTCUSDT",
  socket: null,
};

const APP_BASE_PATH = location.pathname === "/trader" || location.pathname.startsWith("/trader/") ? "/trader" : "";
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function appPath(path) {
  return `${APP_BASE_PATH}${path}`;
}

function money(value) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Number(value || 0));
}

function pct(value) {
  return `${Number(value || 0).toFixed(2)}%`;
}

function timeLabel(ts) {
  if (!ts) return "-";
  return new Date(Number(ts) * 1000).toLocaleString("pt-BR");
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 3200);
}

async function api(path, options = {}) {
  const response = await fetch(appPath(path), {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (response.status === 401) {
    location.href = appPath("/login");
    return null;
  }
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

async function refresh() {
  const payload = await api("/api/status");
  if (!payload) return;
  state.status = payload;
  if (!state.models.length && payload.models) state.models = payload.models;
  if (payload.risk_profiles) state.riskProfiles = payload.risk_profiles;
  renderAll();
}

async function refreshModels() {
  try {
    const payload = await api("/api/models");
    state.models = payload.models || [];
    renderModelSelects(state.status?.config || {});
  } catch (err) {
    toast(`Modelos indisponíveis: ${err.message}`);
  }
}

function renderAll() {
  const data = state.status;
  if (!data) return;
  renderStats(data);
  renderTabs(data);
  renderMarketCards(data);
  renderChart(data);
  renderAnalyses(data);
  renderNews(data);
  renderTrades(data);
  renderEvents(data.events || []);
  renderConfig(data.config || {});
}

function renderStats(data) {
  const wallet = data.wallet || {};
  $("#equity").textContent = money(wallet.equity_brl);
  $("#realized").textContent = money(wallet.realized_pnl_brl);
  $("#realized").className = Number(wallet.realized_pnl_brl || 0) >= 0 ? "good" : "bad";
  $("#wins").textContent = wallet.wins || 0;
  $("#losses").textContent = wallet.losses || 0;
  $("#winRate").textContent = pct(wallet.win_rate_pct);
  $("#runtime").textContent = data.running ? "rodando" : "parado";
}

function renderTabs(data) {
  const symbols = Object.keys(data.snapshots || {});
  if (!symbols.includes(state.selectedSymbol)) state.selectedSymbol = symbols[0] || "BTCUSDT";
  $("#symbolTabs").innerHTML = symbols
    .map((symbol) => `<button type="button" data-symbol="${symbol}" class="${symbol === state.selectedSymbol ? "active" : ""}">${symbol}</button>`)
    .join("");
  $$("#symbolTabs button").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedSymbol = button.dataset.symbol;
      renderAll();
    });
  });
}

function renderMarketCards(data) {
  const snapshot = data.snapshots?.[state.selectedSymbol] || {};
  const f = snapshot.features || {};
  const frame = snapshot.frames?.["1m"] || {};
  const cards = [
    ["Preço", formatPrice(f.last_price)],
    ["24h", pct(f.change_24h_pct)],
    ["Tendência 1m/5m/15m", `${f.trend_1m || "-"} / ${f.trend_5m || "-"} / ${f.trend_15m || "-"}`],
    ["RSI 1m", Number(f.rsi_1m || 0).toFixed(1)],
    ["Volatilidade 1m", pct(f.ret_std_1m_30)],
    ["Volume vs média", `${Number(f.volume_1m_vs_avg30 || 0).toFixed(2)}x`],
    ["Spread", pct(f.spread_pct)],
    ["Último candle", timeLabel(frame.last_close ? snapshot.ts : 0)],
  ];
  $("#marketCards").innerHTML = cards
    .map(([label, value]) => `<article class="metric-card"><span>${label}</span><strong>${value}</strong></article>`)
    .join("");
}

function formatPrice(value) {
  const num = Number(value || 0);
  if (num > 1000) return num.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
  return num.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 5 });
}

function renderChart(data) {
  const canvas = $("#priceChart");
  const container = canvas.parentElement;
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(360, container.clientWidth - 24);
  const height = 460;
  canvas.width = Math.floor(width * ratio);
  canvas.height = Math.floor(height * ratio);
  canvas.style.height = `${height}px`;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#070c12";
  ctx.fillRect(0, 0, width, height);

  const candles = data.snapshots?.[state.selectedSymbol]?.candles?.["1m"] || [];
  if (!candles.length) {
    ctx.fillStyle = "#90a0b1";
    ctx.fillText("Sem candles ainda", 24, 32);
    return;
  }
  const pad = { l: 54, r: 18, t: 22, b: 34 };
  const values = candles.flatMap((candle) => [candle.high, candle.low]);
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const plotW = width - pad.l - pad.r;
  const plotH = height - pad.t - pad.b;
  const xStep = plotW / candles.length;
  const y = (value) => pad.t + (max - value) / span * plotH;

  ctx.strokeStyle = "#182636";
  ctx.lineWidth = 1;
  for (let i = 0; i < 5; i++) {
    const gy = pad.t + (plotH / 4) * i;
    ctx.beginPath();
    ctx.moveTo(pad.l, gy);
    ctx.lineTo(width - pad.r, gy);
    ctx.stroke();
  }

  candles.forEach((candle, i) => {
    const x = pad.l + i * xStep + xStep / 2;
    const up = candle.close >= candle.open;
    ctx.strokeStyle = up ? "#34d27d" : "#ff6972";
    ctx.fillStyle = ctx.strokeStyle;
    ctx.beginPath();
    ctx.moveTo(x, y(candle.high));
    ctx.lineTo(x, y(candle.low));
    ctx.stroke();
    const bodyY = Math.min(y(candle.open), y(candle.close));
    const bodyH = Math.max(2, Math.abs(y(candle.open) - y(candle.close)));
    ctx.fillRect(x - Math.max(1, xStep * 0.28), bodyY, Math.max(2, xStep * 0.56), bodyH);
  });

  ctx.fillStyle = "#90a0b1";
  ctx.font = "12px Inter, sans-serif";
  ctx.fillText(formatPrice(max), 8, pad.t + 8);
  ctx.fillText(formatPrice(min), 8, height - pad.b);
  ctx.fillStyle = "#f4f8fb";
  ctx.font = "700 13px Inter, sans-serif";
  ctx.fillText(`${state.selectedSymbol} · 1m`, pad.l, 18);
}

function renderAnalyses(data) {
  const items = (data.analyses || []).slice(0, 8);
  $("#analyses").innerHTML = items.length
    ? items.map((item) => {
        const res = item.response || {};
        return `
          <article class="analysis-item">
            <header>
              <strong>${item.role} · ${item.model}</strong>
              <span class="pill">${res.decision || item.decision || "-"}</span>
            </header>
            <p>${escapeHtml(item.summary || res.reasoning_summary || res.reason || "Sem resumo")}</p>
            <small class="muted">${item.symbol} · ${item.latency_ms || 0}ms · ${timeLabel(item.ts)}</small>
          </article>`;
      }).join("")
    : `<p class="muted">Aguardando primeira análise da IA.</p>`;
}

function renderNews(data) {
  const news = data.news || {};
  const risk = news.risk_hint || {};
  const pill = $("#newsRisk");
  pill.textContent = risk.level || "neutral";
  pill.className = `pill ${risk.level || ""}`;
  const headlines = news.headlines || [];
  $("#newsList").innerHTML = headlines.length
    ? headlines.slice(0, 8).map((item) => `
      <article class="news-item">
        <strong>${escapeHtml(item.source || "Fonte")}</strong>
        <p>${escapeHtml(item.title || "")}</p>
        <small class="muted">${escapeHtml(item.pubDate || "")}</small>
      </article>`).join("")
    : `<p class="muted">Sem manchetes carregadas ainda.</p>`;
}

function renderTrades(data) {
  const trades = data.trades || [];
  $("#tradesBody").innerHTML = trades.length
    ? trades.map((trade) => {
        const pnl = Number(trade.pnl_brl || 0);
        return `
          <tr>
            <td>#${trade.id}</td>
            <td>${trade.symbol}</td>
            <td>${trade.status}</td>
            <td>${formatPrice(trade.entry_price)}<br><small class="muted">${timeLabel(trade.opened_at)}</small></td>
            <td>${trade.exit_price ? formatPrice(trade.exit_price) : "-"}<br><small class="muted">${trade.closed_at ? timeLabel(trade.closed_at) : ""}</small></td>
            <td>${money(trade.position_brl)}</td>
            <td class="${pnl >= 0 ? "good" : "bad"}">${money(pnl)}<br><small>${pct(trade.pnl_pct)}</small></td>
            <td>${escapeHtml(trade.exit_reason || trade.entry_reason || "-")}</td>
          </tr>`;
      }).join("")
    : `<tr><td colspan="8" class="muted">Nenhuma operação paper ainda.</td></tr>`;
}

function renderEvents(events) {
  $("#events").innerHTML = events.slice(-120).reverse().map((event) => `
    <article class="event-item">
      <header>
        <span class="event-type">${escapeHtml(event.type)}</span>
        <small class="muted">${timeLabel(event.ts)}</small>
      </header>
      <p>${escapeHtml(event.message)}</p>
    </article>
  `).join("");
}

let configRendered = false;
function renderConfig(config) {
  if (!config || configRendered) return;
  const form = $("#configForm");
  renderRiskProfileSelect(config);
  form.auto_enabled.value = String(Boolean(config.auto_enabled));
  for (const name of [
    "initial_balance_brl",
    "position_pct",
    "cooldown_minutes",
    "max_trades_per_day",
    "max_open_positions",
    "daily_stop_loss_pct",
    "daily_target_pct",
    "min_technical_score",
    "min_ai_confidence",
    "min_risk_reward",
    "max_hold_minutes",
  ]) {
    form.elements[name].value = config[name] ?? "";
  }
  renderRiskProfileInfo(config.risk_profile || "balanced");
  form.symbols.value = (config.symbols || []).join(",");
  form.tradable_symbols.value = (config.tradable_symbols || []).join(",");
  renderModelSelects(config);
  configRendered = true;
}

function renderRiskProfileSelect(config) {
  const form = $("#configForm");
  const select = form.risk_profile;
  const profiles = state.riskProfiles || {};
  const entries = Object.entries(profiles);
  const current = config.risk_profile || "balanced";
  if (entries.length) {
    select.innerHTML = entries
      .map(([key, profile]) => `<option value="${escapeAttr(key)}">${escapeHtml(profile.label || key)}</option>`)
      .join("");
  } else {
    select.innerHTML = `
      <option value="conservative">Conservador</option>
      <option value="balanced">Balanceado</option>
      <option value="aggressive">Agressivo</option>
      <option value="full_aggressive">Full agressivo</option>
    `;
  }
  select.value = [...select.options].some((option) => option.value === current) ? current : "balanced";
}

function renderRiskProfileInfo(profileKey) {
  const profile = state.riskProfiles?.[profileKey];
  const info = $("#riskProfileInfo");
  if (!profile) {
    info.innerHTML = `<strong>Perfil de risco</strong><small>Escolha um preset para recalibrar o paper trading.</small>`;
    return;
  }
  const settings = profile.settings || {};
  info.innerHTML = `
    <strong>${escapeHtml(profile.label || profileKey)}</strong>
    <span>${escapeHtml(profile.description || "")}</span>
    <small>
      posição ${settings.position_pct ?? "-"}% · cooldown ${settings.cooldown_minutes ?? "-"}min ·
      score ${settings.min_technical_score ?? "-"} · confiança ${settings.min_ai_confidence ?? "-"} ·
      RR ${settings.min_risk_reward ?? "-"}
    </small>
  `;
}

function applyRiskProfilePreset(profileKey) {
  const profile = state.riskProfiles?.[profileKey];
  renderRiskProfileInfo(profileKey);
  if (!profile?.settings) return;
  const form = $("#configForm");
  for (const [name, value] of Object.entries(profile.settings)) {
    if (form.elements[name]) form.elements[name].value = value;
  }
  $("#saveState").textContent = "perfil aplicado";
  toast(`Perfil ${profile.label || profileKey} aplicado. Salve para ativar.`);
}

function renderModelSelects(config) {
  const models = state.models || [];
  $$("[data-model-select]").forEach((select) => {
    const current = getPath(config, select.name) || select.value;
    select.innerHTML = models.map((model) => `<option value="${escapeAttr(model)}">${escapeHtml(model)}</option>`).join("");
    if (current && models.includes(current)) select.value = current;
  });
}

function collectConfig() {
  const form = $("#configForm");
  return {
    auto_enabled: form.auto_enabled.value === "true",
    risk_profile: form.risk_profile.value,
    initial_balance_brl: Number(form.initial_balance_brl.value),
    position_pct: Number(form.position_pct.value),
    cooldown_minutes: Number(form.cooldown_minutes.value),
    max_trades_per_day: Number(form.max_trades_per_day.value),
    max_open_positions: Number(form.max_open_positions.value),
    daily_stop_loss_pct: Number(form.daily_stop_loss_pct.value),
    daily_target_pct: Number(form.daily_target_pct.value),
    min_technical_score: Number(form.min_technical_score.value),
    min_ai_confidence: Number(form.min_ai_confidence.value),
    min_risk_reward: Number(form.min_risk_reward.value),
    max_hold_minutes: Number(form.max_hold_minutes.value),
    symbols: splitSymbols(form.symbols.value),
    tradable_symbols: splitSymbols(form.tradable_symbols.value),
    models: {
      fast_filter: form.elements["models.fast_filter"].value,
      decision: form.elements["models.decision"].value,
      critic: form.elements["models.critic"].value,
      report: form.elements["models.report"].value,
    },
  };
}

function splitSymbols(value) {
  return String(value || "").split(",").map((item) => item.trim().toUpperCase()).filter(Boolean);
}

function getPath(obj, path) {
  return path.split(".").reduce((acc, key) => (acc ? acc[key] : undefined), obj);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[ch]));
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/`/g, "&#096;");
}

function connectSocket() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${location.host}${APP_BASE_PATH}/ws`);
  state.socket = ws;
  ws.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "status") {
      state.status = payload.data;
      if (payload.data.models) state.models = payload.data.models;
      if (payload.data.risk_profiles) state.riskProfiles = payload.data.risk_profiles;
      renderAll();
    } else if (payload.type === "event") {
      if (!state.status) return;
      state.status.events = [...(state.status.events || []), payload.data].slice(-140);
      renderEvents(state.status.events);
      if (["trade:opened", "trade:closed", "config", "market", "paper:reset"].includes(payload.data.type)) {
        setTimeout(refresh, 350);
      }
    }
  };
  ws.onclose = () => setTimeout(connectSocket, 3000);
}

function bindActions() {
  $("#riskProfileSelect").addEventListener("change", (event) => {
    applyRiskProfilePreset(event.target.value);
  });

  $("#configForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    $("#saveState").textContent = "salvando";
    try {
      const payload = collectConfig();
      await api("/api/config", { method: "POST", body: JSON.stringify(payload) });
      configRendered = false;
      await refresh();
      $("#saveState").textContent = "salvo";
      toast("Configuração salva");
    } catch (err) {
      $("#saveState").textContent = "erro";
      toast(err.message || "Falha ao salvar");
    }
  });

  $("#runOnceBtn").addEventListener("click", async () => {
    const button = $("#runOnceBtn");
    button.disabled = true;
    button.textContent = "Analisando...";
    try {
      const payload = await api("/api/run-once", { method: "POST", body: "{}" });
      state.status = payload.status;
      renderAll();
      toast("Análise rodada");
    } catch (err) {
      toast(err.message || "Falha ao rodar");
    } finally {
      button.disabled = false;
      button.textContent = "Rodar análise agora";
    }
  });

  $("#resetBtn").addEventListener("click", async () => {
    const current = state.status?.config?.initial_balance_brl || 50;
    const raw = prompt("Novo saldo paper em BRL:", current);
    if (raw === null) return;
    const balance = Number(raw);
    if (!Number.isFinite(balance) || balance <= 0) return toast("Saldo inválido");
    await api("/api/paper/reset", { method: "POST", body: JSON.stringify({ balance_brl: balance }) });
    configRendered = false;
    await refresh();
    toast("Saldo paper reiniciado");
  });

  $("#logoutBtn").addEventListener("click", async () => {
    await api("/api/logout", { method: "POST", body: "{}" });
    location.href = appPath("/login");
  });
}

window.addEventListener("resize", () => renderChart(state.status || {}));

(async function boot() {
  bindActions();
  await refresh();
  await refreshModels();
  connectSocket();
  setInterval(refresh, 30000);
})();
