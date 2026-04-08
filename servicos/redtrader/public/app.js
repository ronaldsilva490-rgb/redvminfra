const state = {
  status: null,
  models: [],
  riskProfiles: {},
  selectedSymbol: "BTCUSDT",
  selectedPlatformConfig: null,
  terminalZoom: 20,
  terminalPan: 0,
  terminalDrag: null,
  stakeSaveTimer: null,
  stakeSaving: false,
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

function usd(value) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value || 0));
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
  renderTerminal(data);
  renderQuickConfig(data.config || {});
  renderAudit(data.demo_audit || {});
  renderPlatforms(data);
  renderPlatformConfigHelp(state.selectedPlatformConfig);
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
  const platforms = data.platforms || [];
  const online = platforms.filter((item) => item.connected).length;
  $("#platformsOnline").textContent = `${online}/${platforms.length}`;
}

function renderAudit(audit) {
  $("#auditStatus").textContent = audit.eligible_for_real_review ? "elegível para revisão" : "bloqueada";
  $("#auditStatus").className = `audit-status ${audit.eligible_for_real_review ? "good" : "bad"}`;
  $("#auditLevel").textContent = audit.level || 0;
  $("#auditXp").textContent = audit.xp || 0;
  $("#auditStreak").textContent = audit.consecutive_wins || 0;
  $("#auditProfitFactor").textContent = Number(audit.profit_factor || 0).toFixed(2);
  $("#auditDrawdown").textContent = pct(audit.max_drawdown_pct);
  $("#auditNote").textContent = audit.note || "Ainda em auditoria demo.";
  const req = audit.requirements || {};
  const checks = audit.checks || {};
  const rows = [
    ["Operações fechadas", audit.closed_trades || 0, req.min_closed_trades || 0, checks.closed_trades],
    ["Sequência 100%", audit.consecutive_wins || 0, req.min_consecutive_wins || 0, checks.consecutive_wins],
    ["Win rate", pct(audit.win_rate_pct), pct(req.min_win_rate_pct), checks.win_rate],
    ["Profit factor", Number(audit.profit_factor || 0).toFixed(2), Number(req.min_profit_factor || 0).toFixed(2), checks.profit_factor],
    ["Max drawdown", pct(audit.max_drawdown_pct), `<= ${pct(req.max_drawdown_pct)}`, checks.drawdown],
  ];
  $("#auditChecks").innerHTML = rows.map(([label, value, target, ok]) => `
    <span class="${ok ? "good" : "bad"}">${ok ? "OK" : "LOCK"}</span>
    <strong>${escapeHtml(label)}</strong>
    <small>${escapeHtml(value)} / ${escapeHtml(target)}</small>
  `).join("");
}

function renderPlatforms(data) {
  const platforms = data.platforms || [];
  $("#platformGrid").innerHTML = platforms.length
    ? platforms.map((item) => `
      <article class="platform-card ${escapeAttr(item.status || "")}">
        <header>
          <div>
            <h3>${escapeHtml(item.label || item.id)}</h3>
            <small class="muted">${escapeHtml(item.kind || "-")} · ${escapeHtml(item.mode || "-")}</small>
          </div>
          ${platformStatusAction(item)}
        </header>
        <p>${escapeHtml(item.message || item.docs_note || "")}</p>
        <div class="platform-meta">
          <span>Dados: ${escapeHtml(item.data_scope || "-")}</span>
          <span>Execução: ${escapeHtml(item.execution_scope || "-")}</span>
          <span>Base: ${escapeHtml(item.base_url || "interno")}</span>
          <span>Latência: ${item.latency_ms ? `${item.latency_ms}ms` : "-"}</span>
        </div>
      </article>
    `).join("")
    : `<p class="muted">Sincronizando conexões das plataformas...</p>`;
}

function platformStatusAction(item) {
  const status = platformStatusLabel(item.status);
  const className = platformPillClass(item);
  if (["needs_config", "configured", "disabled", "error"].includes(item.status)) {
    const label = item.status === "disabled" ? "detalhes" : status;
    return `<button type="button" class="platform-action ${className}" data-platform-config="${escapeAttr(item.id)}">${escapeHtml(label)}</button>`;
  }
  return `<span class="pill ${className}">${escapeHtml(status)}</span>`;
}

function platformStatusLabel(status) {
  return {
    connected: "conectada",
    configured: "configurada",
    needs_config: "configurar",
    disabled: "desligada",
    error: "erro",
  }[status] || status || "desconhecida";
}

function platformPillClass(item) {
  if (item.connected) return "green";
  if (item.status === "needs_config" || item.status === "error") return "red";
  if (item.status === "configured") return "yellow";
  return "";
}

function renderPlatformConfigHelp(platformId) {
  const panel = $("#platformConfigHelp");
  if (!panel) return;
  if (!platformId) {
    panel.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }

  const platform = (state.status?.platforms || []).find((item) => item.id === platformId);
  if (!platform) {
    state.selectedPlatformConfig = null;
    panel.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }

  const help = platformConfigHelp(platform);
  panel.innerHTML = `
    <header>
      <div>
        <p class="eyebrow">Configuração</p>
        <h3>${escapeHtml(help.title)}</h3>
      </div>
      <button type="button" class="secondary compact" data-platform-config-close>Fechar</button>
    </header>
    <p>${escapeHtml(help.description)}</p>
    <pre>${escapeHtml(help.env)}</pre>
    <div class="platform-config-steps">
      ${help.steps.map((step) => `<span>${escapeHtml(step)}</span>`).join("")}
    </div>
  `;
  panel.classList.remove("hidden");
}

function platformConfigHelp(platform) {
  const commonSteps = [
    "1. Edite /etc/redtrader.env na VM do RED Trader.",
    "2. Preencha as variáveis sem aspas e sem espaços extras.",
    "3. Rode systemctl restart redtrader.",
    "4. Volte aqui e clique em Atualizar conexões.",
  ];
  const helpers = {
    tastytrade_sandbox: {
      title: "Configurar tastytrade Sandbox",
      description: "Use o OAuth personal grant do sandbox. O core continua em pesquisa e paper; este adapter valida a conexão oficial sem ordem real.",
      env: [
        "TASTYTRADE_BASE_URL=https://api.cert.tastyworks.com",
        "TASTYTRADE_CLIENT_ID=seu_client_id",
        "TASTYTRADE_CLIENT_SECRET=seu_client_secret",
        "TASTYTRADE_REFRESH_TOKEN=seu_refresh_token",
        "TASTYTRADE_ACCOUNT_NUMBER=sua_conta_sandbox",
      ].join("\n"),
      steps: commonSteps,
    },
    webull_paper: {
      title: "Configurar Webull Paper",
      description: "Use as credenciais da aplicação OpenAPI/Paper. Sem app key e secret, o painel mantém a plataforma como pendente.",
      env: [
        "WEBULL_BASE_URL=https://openapi.webull.com",
        "WEBULL_APP_KEY=sua_app_key",
        "WEBULL_APP_SECRET=seu_app_secret",
      ].join("\n"),
      steps: commonSteps,
    },
    iqoption_experimental: {
      title: "Configurar IQ Option Demo",
      description: "Conecta a conta demo/PRACTICE via adapter comunitário. O RED Trader não libera conta real neste fluxo.",
      env: [
        "IQOPTION_ENABLED=true",
        "IQOPTION_HOST=iqoption.com",
        "IQOPTION_USERNAME=seu_email",
        "IQOPTION_PASSWORD=sua_senha",
        "IQOPTION_FORCE_PRACTICE=true",
      ].join("\n"),
      steps: commonSteps,
    },
    binance_spot: {
      title: "Binance Spot",
      description: "Market data público já funciona sem credenciais. No MVP, a execução fica no paper ledger interno do RED Trader.",
      env: "BINANCE_BASE_URL=https://api.binance.com",
      steps: [
        "Nenhuma credencial é necessária para market data público.",
        "Se cair, clique em Atualizar conexões e confira os logs do redtrader.service.",
      ],
    },
  };

  return helpers[platform.id] || {
    title: platform.label || platform.id,
    description: platform.message || "Sem instruções específicas para este adapter.",
    env: "# Nenhuma variável documentada para este adapter.",
    steps: commonSteps,
  };
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

function renderTerminal(data) {
  const canvas = $("#terminalChart");
  if (!canvas) return;

  const snapshot = data.snapshots?.[state.selectedSymbol] || {};
  const candles = snapshot.candles?.["1s"]?.length ? snapshot.candles["1s"] : snapshot.candles?.["1m"] || [];
  const frameLabel = snapshot.candles?.["1s"]?.length ? "1s" : "1m";
  const features = snapshot.features || {};
  const wallet = data.wallet || {};
  const recovery = data.iq_recovery || {};
  const iq = (data.platforms || []).find((item) => item.id === "iqoption_experimental");
  const practiceBalance = Number(iq?.practice_balance || 0);
  const latestAnalysis = (data.analyses || []).find((item) => item.symbol === state.selectedSymbol) || {};
  const analysisResponse = latestAnalysis.response || {};
  const last = candles[candles.length - 1] || {};
  const change = last.open ? ((Number(last.close) / Number(last.open) - 1) * 100) : 0;
  const bookBias = (Number(features.bid_ask_ratio || 1) - 1) * 8;
  const trendBias = features.trend_1m === "up" ? 7 : features.trend_1m === "down" ? -7 : 0;
  const above = Math.max(5, Math.min(95, 50 + change * 500 + bookBias + trendBias));
  const below = 100 - above;
  const stake = Number($("#terminalStake")?.value || 1);
  const payout = 86;
  const decision = formatTerminalDecision(analysisResponse.decision || latestAnalysis.decision || (above > 60 ? "ACIMA" : below > 60 ? "ABAIXO" : "NO_TRADE"));
  const reason = analysisResponse.reasoning_summary || analysisResponse.reason || latestAnalysis.summary || "Aguardando o comitê de modelos.";
  const balanceFormatter = practiceBalance ? usd : money;

  $("#terminalAssetTab").textContent = state.selectedSymbol || "mercado";
  $("#terminalAsset").textContent = state.selectedSymbol || "mercado";
  $("#terminalSub").textContent = `${iq?.connected ? "IQ Option PRACTICE" : "Paper interno"} · ${features.trend_1m || "sem tendência"} · feed ${frameLabel}`;
  $("#terminalMode").textContent = iq?.connected ? "IQ PRACTICE" : "PAPER";
  $("#terminalBalance").textContent = balanceFormatter(practiceBalance || wallet.equity_brl);
  $("#terminalAbove").textContent = `${above.toFixed(0)}%`;
  $("#terminalBelow").textContent = `${below.toFixed(0)}%`;
  $("#terminalProfit").textContent = `+${payout}%`;
  $("#terminalProfitValue").textContent = `+${balanceFormatter(stake * payout / 100)}`;
  $("#terminalGale").textContent = Number(recovery.stage || 0) > 0 ? `GALE ${recovery.stage}` : "BASE";
  $("#terminalGaleDetail").textContent = `proxima entrada ${balanceFormatter(recovery.next_amount || stake)} · perda a recuperar ${balanceFormatter(recovery.loss_total || 0)}`;
  $("#terminalDecision").textContent = decision;
  $("#terminalDecisionReason").textContent = reason;
  $("#terminalAiBadge").textContent = latestAnalysis.model ? `${latestAnalysis.model} · ${decision}` : "IA aguardando setup";
  $("#terminalPriceTag").textContent = formatPrice(features.last_price || last.close);
  $("#terminalZoomLabel").textContent = `zoom ${Number(state.terminalZoom || 1).toFixed(0)}x ${Number(state.terminalPan || 0) ? "· replay" : "· ao vivo"}`;
  const zoomRange = $("#terminalZoomRange");
  if (zoomRange && zoomRange !== document.activeElement) zoomRange.value = String(state.terminalZoom || 20);
  renderTerminalEntries(data);
  renderTerminalModelVotes(data);

  renderTerminalChart(data, above);
}

function formatTerminalDecision(value) {
  const text = String(value || "NO_TRADE").toUpperCase();
  if (["ENTER_LONG", "LONG", "CALL", "BUY", "ACIMA"].includes(text)) return "ACIMA";
  if (["ENTER_SHORT", "SHORT", "PUT", "SELL", "ABAIXO"].includes(text)) return "ABAIXO";
  return "NO_TRADE";
}

function renderTerminalModelVotes(data) {
  const analyses = data.analyses || [];
  const byRole = (role) => analyses.find((item) => item.symbol === state.selectedSymbol && item.role === role) || {};
  const cards = [
    ["terminalFastVote", "terminalFastReason", "fast_filter", "Scout"],
    ["terminalDecisionVote", "terminalDecisionVoteReason", "decision", "Decisor"],
    ["terminalCriticVote", "terminalCriticVoteReason", "critic", "Critico"],
    ["terminalPremium4Vote", "terminalPremium4Reason", "premium_4", "Premium 4"],
    ["terminalPremium5Vote", "terminalPremium5Reason", "premium_5", "Premium 5"],
  ];
  cards.forEach(([voteId, reasonId, role, fallback]) => {
    const item = byRole(role);
    const response = item.response || {};
    const vote = role === "critic"
      ? (response.preferred_decision || response.decision || item.decision)
      : (response.decision || item.decision);
    const summary = response.reasoning_summary || response.reason || item.summary || fallback;
    const latency = item.latency_ms ? `${item.latency_ms}ms` : "aguardando";
    const model = item.model ? shortModelName(item.model) : fallback;
    const voteEl = $(`#${voteId}`);
    const reasonEl = $(`#${reasonId}`);
    if (voteEl) voteEl.textContent = formatTerminalDecision(vote || "WAIT");
    if (reasonEl) reasonEl.textContent = `${model} - ${latency} - ${summary}`.slice(0, 150);
  });
}

function shortModelName(model) {
  return String(model || "")
    .replace(" (NVIDIA)", "")
    .replace(" (GROQ)", "")
    .replace("meta/", "")
    .replace("qwen/", "")
    .replace("mistralai/", "")
    .replace("openai/", "");
}

function getTerminalCandles() {
  const snapshot = state.status?.snapshots?.[state.selectedSymbol] || {};
  return snapshot.candles?.["1s"]?.length ? snapshot.candles["1s"] : snapshot.candles?.["1m"] || [];
}

function setTerminalZoom(value) {
  state.terminalZoom = Math.max(1, Math.min(40, Math.round(Number(value || 1))));
  const zoomRange = $("#terminalZoomRange");
  if (zoomRange) zoomRange.value = String(state.terminalZoom);
  renderTerminal(state.status || {});
}

function clampTerminalPan(value) {
  const candles = getTerminalCandles();
  const zoom = Math.max(1, Number(state.terminalZoom || 1));
  const visibleCount = Math.max(12, Math.min(candles.length, Math.round(candles.length / zoom)));
  return Math.max(0, Math.min(Math.max(0, candles.length - visibleCount), Math.round(Number(value || 0))));
}

function renderTerminalEntries(data) {
  const list = $("#terminalEntries");
  if (!list) return;
  const trades = (data.trades || []).filter((trade) => trade.symbol === state.selectedSymbol).slice(0, 6);
  list.innerHTML = trades.length
    ? trades.map((trade) => {
        const pnl = Number(trade.pnl_brl || 0);
        const meta = trade.metadata || {};
        return `
          <article class="${trade.status === "OPEN" ? "open" : pnl >= 0 ? "win" : "loss"}">
            <strong>#${trade.id} ${escapeHtml(trade.side || "-")} · ${escapeHtml(trade.status || "-")}</strong>
            <span>${money(trade.position_brl)} · ${trade.status === "OPEN" ? "ao vivo" : money(pnl)}</span>
            <small>${escapeHtml(meta.iqoption_order_id || "")}</small>
          </article>
        `;
      }).join("")
    : `<p class="muted">Aguardando a primeira entrada da IA.</p>`;
}

function renderTerminalChart(data, aboveBias = 50) {
  const canvas = $("#terminalChart");
  if (!canvas) return;
  const container = canvas.parentElement;
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(620, container.clientWidth);
  const fullscreen = $("#terminal")?.classList.contains("fullscreen");
  const naturalHeight = container.clientHeight || Math.round(width * 0.56);
  const height = fullscreen ? Math.max(600, naturalHeight) : Math.max(600, Math.min(820, naturalHeight));
  canvas.width = Math.floor(width * ratio);
  canvas.height = Math.floor(height * ratio);
  canvas.style.height = `${height}px`;

  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#020304";
  ctx.fillRect(0, 0, width, height);

  const snapshot = data.snapshots?.[state.selectedSymbol] || {};
  const allCandles = snapshot.candles?.["1s"]?.length ? snapshot.candles["1s"] : snapshot.candles?.["1m"] || [];
  const frameLabel = snapshot.candles?.["1s"]?.length ? "1s" : "1m";
  const zoom = Math.max(1, Number(state.terminalZoom || 1));
  const visibleCount = Math.max(12, Math.min(allCandles.length, Math.round(allCandles.length / zoom)));
  const pan = Math.max(0, Math.min(Math.max(0, allCandles.length - visibleCount), Math.round(Number(state.terminalPan || 0))));
  if (pan !== state.terminalPan) state.terminalPan = pan;
  const end = allCandles.length - pan;
  const candles = allCandles.slice(Math.max(0, end - visibleCount), end);
  if (!candles.length) {
    ctx.fillStyle = "#88929c";
    ctx.font = "700 14px Inter, sans-serif";
    ctx.fillText("Aguardando candles do mercado...", 28, 42);
    return;
  }

  const pad = { l: 56, r: 92, t: 58, b: 44 };
  const values = candles.flatMap((candle) => [Number(candle.high), Number(candle.low)]).filter(Number.isFinite);
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const plotW = width - pad.l - pad.r;
  const plotH = height - pad.t - pad.b;
  const openTrades = (data.trades || []).filter((trade) => trade.symbol === state.selectedSymbol && trade.status === "OPEN");
  const firstTime = Number(candles[0]?.time || 0);
  const lastCandleTime = Number(candles[candles.length - 1]?.time || firstTime + 1);
  const maxExpiryTime = Math.max(lastCandleTime, ...openTrades.map((trade) => Number(trade.opened_at || 0) + Number((trade.metadata || {}).expiry_seconds || 60)));
  const rightSpace = pan === 0 ? Math.min(70, Math.max(14, maxExpiryTime - lastCandleTime + 8)) : 2;
  const domainStart = firstTime;
  const domainEnd = Math.max(lastCandleTime + rightSpace, firstTime + 1);
  const xStep = plotW / Math.max(1, domainEnd - domainStart);
  const y = (value) => pad.t + (max - Number(value)) / span * plotH;
  const xTime = (ts) => pad.l + ((Number(ts || domainEnd) - domainStart) / Math.max(1, domainEnd - domainStart)) * plotW;
  const last = candles[candles.length - 1];
  const lastY = y(last.close);
  const nowX = Math.min(width - pad.r - 20, xTime(lastCandleTime));

  ctx.strokeStyle = "#111820";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 10; i++) {
    const gx = pad.l + (plotW / 10) * i;
    ctx.beginPath();
    ctx.moveTo(gx, pad.t);
    ctx.lineTo(gx, height - pad.b);
    ctx.stroke();
  }
  for (let i = 0; i <= 6; i++) {
    const gy = pad.t + (plotH / 6) * i;
    ctx.beginPath();
    ctx.moveTo(pad.l, gy);
    ctx.lineTo(width - pad.r, gy);
    ctx.stroke();
  }

  const gradient = ctx.createLinearGradient(0, pad.t, 0, height - pad.b);
  gradient.addColorStop(0, "rgba(239, 114, 23, 0.32)");
  gradient.addColorStop(0.65, "rgba(239, 114, 23, 0.11)");
  gradient.addColorStop(1, "rgba(239, 114, 23, 0.02)");

  ctx.beginPath();
  candles.forEach((candle, index) => {
    const px = xTime(candle.time);
    const py = y(candle.close);
    if (index === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.lineTo(nowX, height - pad.b);
  ctx.lineTo(pad.l, height - pad.b);
  ctx.closePath();
  ctx.fillStyle = gradient;
  ctx.fill();

  ctx.beginPath();
  candles.forEach((candle, index) => {
    const px = xTime(candle.time);
    const py = y(candle.close);
    if (index === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.strokeStyle = "#f27a1a";
  ctx.lineWidth = 2;
  ctx.shadowColor = "rgba(242, 122, 26, 0.55)";
  ctx.shadowBlur = 10;
  ctx.stroke();
  ctx.shadowBlur = 0;

  ctx.setLineDash([5, 5]);
  ctx.strokeStyle = "rgba(242, 122, 26, 0.85)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.l, lastY);
  ctx.lineTo(width - pad.r + 2, lastY);
  ctx.stroke();
  ctx.setLineDash([2, 4]);
  ctx.strokeStyle = "rgba(255, 255, 255, 0.7)";
  ctx.beginPath();
  ctx.moveTo(nowX, pad.t);
  ctx.lineTo(nowX, height - pad.b);
  ctx.stroke();
  ctx.setLineDash([]);

  const pulse = 3 + Math.sin(Date.now() / 180) * 2;
  ctx.fillStyle = "#25c46b";
  ctx.beginPath();
  ctx.arc(nowX, lastY, 4 + pulse, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#f27a1a";
  ctx.fillRect(width - pad.r + 8, lastY - 14, 74, 28);
  ctx.fillStyle = "#190802";
  ctx.font = "800 12px Inter, sans-serif";
  ctx.fillText(formatPrice(last.close), width - pad.r + 14, lastY + 5);

  drawTerminalTradeMarkers(ctx, data, candles, { pad, width, height, plotW, plotH, min, max, y, nowX, xFromTime: xTime, domainStart, domainEnd });

  ctx.fillStyle = "#7f8791";
  ctx.font = "12px Inter, sans-serif";
  for (let i = 0; i <= 5; i++) {
    const ts = domainStart + ((domainEnd - domainStart) / 5) * i;
    ctx.fillText(new Date(ts * 1000).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }), pad.l + (plotW / 5) * i, height - 16);
  }
  ctx.fillStyle = "#7f8791";
  ctx.font = "900 11px Inter, sans-serif";
  ctx.fillText(`${state.selectedSymbol} · ${frameLabel} · ${visibleCount} velas ${pan ? `· replay -${pan}` : "· ao vivo"}`, pad.l, 22);
  ctx.fillStyle = aboveBias >= 50 ? "rgba(52, 210, 125, 0.24)" : "rgba(255, 105, 114, 0.24)";
  ctx.fillRect(pad.l, pad.t, 9, plotH * (aboveBias / 100));
  ctx.fillStyle = aboveBias >= 50 ? "#34d27d" : "#ff6972";
  ctx.font = "900 12px Inter, sans-serif";
  ctx.fillText(`ACIMA ${aboveBias.toFixed(0)}%`, pad.l + 16, pad.t + 20);
  ctx.fillText(`ABAIXO ${(100 - aboveBias).toFixed(0)}%`, pad.l + 16, height - pad.b - 8);
}

function drawTerminalTradeMarkers(ctx, data, candles, scale) {
  const trades = (data.trades || [])
    .filter((trade) => trade.symbol === state.selectedSymbol)
    .filter((trade) => {
      const opened = Number(trade.opened_at || 0);
      const expires = opened + Number((trade.metadata || {}).expiry_seconds || 60);
      return expires >= scale.domainStart - 5 && opened <= scale.domainEnd + 5;
    })
    .slice(0, 12);
  if (!trades.length) return;
  const xFromTime = (ts) => Math.max(scale.pad.l + 8, Math.min(scale.width - scale.pad.r, scale.xFromTime(ts)));

  ctx.save();
  trades.forEach((trade) => {
    const isOpen = trade.status === "OPEN";
    const pnl = Number(trade.pnl_brl || 0);
    const color = isOpen ? "#35ff93" : pnl >= 0 ? "#35ff93" : "#ff6972";
    const px = xFromTime(trade.opened_at);
    const expiryTs = Number(trade.opened_at || 0) + Number((trade.metadata || {}).expiry_seconds || 60);
    const expiryX = xFromTime(expiryTs);
    const entry = Number(trade.entry_price || 0);
    const py = Number.isFinite(entry) && entry > 0 ? scale.y(entry) : scale.pad.t + scale.plotH / 2;
    const side = String(trade.side || "").toUpperCase();
    const stage = (trade.metadata || {}).gale_stage;
    const label = `#${trade.id} ${side}${stage ? ` G${stage}` : ""}`;

    ctx.setLineDash([3, 5]);
    ctx.strokeStyle = isOpen ? "rgba(53, 255, 147, 0.7)" : "rgba(255, 255, 255, 0.34)";
    ctx.beginPath();
    ctx.moveTo(px, scale.pad.t);
    ctx.lineTo(px, scale.height - scale.pad.b);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = color;
    ctx.beginPath();
    if (side === "PUT" || side === "ABAIXO") {
      ctx.moveTo(px, py + 10);
      ctx.lineTo(px - 8, py - 6);
      ctx.lineTo(px + 8, py - 6);
    } else {
      ctx.moveTo(px, py - 10);
      ctx.lineTo(px - 8, py + 6);
      ctx.lineTo(px + 8, py + 6);
    }
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = "rgba(2, 3, 4, 0.88)";
    ctx.fillRect(px + 8, py - 17, 76, 26);
    ctx.strokeStyle = color;
    ctx.strokeRect(px + 8, py - 17, 76, 26);
    ctx.fillStyle = color;
    ctx.font = "900 11px Inter, sans-serif";
    ctx.fillText(label, px + 14, py);

    if (isOpen) {
      const remaining = Math.max(0, Math.round(expiryTs - Date.now() / 1000));
      ctx.setLineDash([6, 5]);
      ctx.strokeStyle = "rgba(255, 191, 140, 0.75)";
      ctx.beginPath();
      ctx.moveTo(expiryX, scale.pad.t);
      ctx.lineTo(expiryX, scale.height - scale.pad.b);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "rgba(255, 191, 140, 0.95)";
      ctx.font = "900 11px Inter, sans-serif";
      ctx.fillText(`expira ${remaining}s`, Math.max(scale.pad.l + 8, expiryX - 56), scale.pad.t + 38);
    }
  });
  ctx.restore();
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
function renderQuickConfig(config) {
  const form = $("#quickConfigForm");
  if (!form || form.contains(document.activeElement)) return;
  if (state.stakeSaving) return;
  const symbol = (config.symbols || ["EURUSD-OTC"]).join(",") || "EURUSD-OTC";
  form.auto_enabled.value = String(Boolean(config.auto_enabled));
  form.risk_profile.value = config.risk_profile || "full_aggressive";
  form.symbol.value = symbol;
  form.iqoption_amount.value = config.iqoption_amount ?? 1;
  form.iqoption_expiration_minutes.value = String(config.iqoption_expiration_minutes || 1);
  form.cooldown_minutes.value = String(config.cooldown_minutes || 0.5);
  const terminalStake = $("#terminalStake");
  if (terminalStake && terminalStake !== document.activeElement) terminalStake.value = String(config.iqoption_amount ?? 1);
  renderStakePresets(Number(config.iqoption_amount ?? 1));
}

function setStakeValue(value, persist = false) {
  const stake = Math.max(1, Number(value || 1));
  const terminalStake = $("#terminalStake");
  const quickStake = $("#quickConfigForm")?.elements.iqoption_amount;
  if (terminalStake) terminalStake.value = String(stake);
  if (quickStake) quickStake.value = String(stake);
  renderStakePresets(stake);
  renderTerminal(state.status || {});
  if (persist) scheduleStakeSave(stake);
}

function scheduleStakeSave(stake) {
  window.clearTimeout(state.stakeSaveTimer);
  state.stakeSaving = true;
  $("#saveState").textContent = `valor ${stake} pendente`;
  state.stakeSaveTimer = window.setTimeout(() => saveStakeValue(stake), 180);
}

async function saveStakeValue(stake) {
  state.stakeSaving = true;
  $("#saveState").textContent = `valor ${stake} salvando`;
  try {
    const current = state.status?.config || {};
    const symbols = splitSymbols($("#quickConfigForm")?.elements.symbol?.value || (current.symbols || ["EURUSD-OTC"]).join(","));
    const activeSymbols = symbols.length ? symbols : ["EURUSD-OTC"];
    const payload = {
      ...current,
      iqoption_amount: Number(stake),
      market_provider: "iqoption_demo",
      execution_provider: "iqoption_demo",
      symbols: activeSymbols,
      tradable_symbols: activeSymbols,
      max_open_positions: 1,
    };
    const saved = await api("/api/config", { method: "POST", body: JSON.stringify(payload) });
    if (state.status && saved?.config) state.status.config = saved.config;
    $("#saveState").textContent = `valor ${stake} salvo`;
    toast(`Proxima entrada base: $${stake}`);
  } catch (err) {
    $("#saveState").textContent = "erro";
    toast(err.message || "Falha ao salvar valor");
  } finally {
    state.stakeSaving = false;
    renderQuickConfig(state.status?.config || {});
  }
}

function renderStakePresets(value) {
  const stake = Number(value || 0);
  $$("[data-stake-value]").forEach((button) => {
    button.classList.toggle("active", Number(button.dataset.stakeValue) === stake);
  });
}

function renderConfig(config) {
  if (!config || configRendered) return;
  const form = $("#configForm");
  renderRiskProfileSelect(config);
  form.auto_enabled.value = String(Boolean(config.auto_enabled));
  form.market_provider.value = config.market_provider || "binance_spot";
  form.execution_provider.value = config.execution_provider || "internal_paper";
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
    "iqoption_amount",
    "iqoption_expiration_minutes",
  ]) {
    form.elements[name].value = config[name] ?? "";
  }
  renderRiskProfileInfo(config.risk_profile || "balanced");
  form.symbols.value = (config.symbols || []).join(",");
  form.tradable_symbols.value = (config.tradable_symbols || []).join(",");
  renderModelSelects(config);
  configRendered = true;
}

function collectQuickConfig() {
  const form = $("#quickConfigForm");
  const current = state.status?.config || {};
  const symbols = splitSymbols(form.symbol.value || "EURUSD-OTC");
  const activeSymbols = symbols.length ? symbols : ["EURUSD-OTC"];
  return {
    ...current,
    auto_enabled: form.auto_enabled.value === "true",
    risk_profile: form.risk_profile.value,
    market_provider: "iqoption_demo",
    execution_provider: "iqoption_demo",
    symbols: activeSymbols,
    tradable_symbols: activeSymbols,
    iqoption_amount: Number(form.iqoption_amount.value || 1),
    iqoption_expiration_minutes: Number(form.iqoption_expiration_minutes.value || 1),
    iqoption_gale_enabled: true,
    iqoption_gale_max_steps: 2,
    iqoption_gale_multiplier: 2.35,
    iqoption_gale_payout_pct: 85,
    iqoption_gale_max_amount: 100,
    cooldown_minutes: Number(form.cooldown_minutes.value || 0.5),
    market_poll_seconds: 0.35,
    decision_poll_seconds: 3,
    max_open_positions: 1,
    max_trades_per_day: Math.max(Number(current.max_trades_per_day || 200), 200),
    daily_stop_loss_pct: Math.max(Number(current.daily_stop_loss_pct || 50), 50),
    daily_target_pct: Math.max(Number(current.daily_target_pct || 50), 50),
    platforms: {
      ...(current.platforms || {}),
      binance_spot: { enabled: false, mode: "market_data_paper", label: "Binance Spot" },
      tastytrade_sandbox: { enabled: false, mode: "sandbox", label: "tastytrade Sandbox" },
      webull_paper: { enabled: false, mode: "paper", label: "Webull Paper" },
      iqoption_experimental: { enabled: true, mode: "demo", label: "IQ Option Demo" },
    },
  };
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
    market_provider: form.market_provider.value,
    execution_provider: form.execution_provider.value,
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
    iqoption_amount: Number(form.iqoption_amount.value),
    iqoption_expiration_minutes: Number(form.iqoption_expiration_minutes.value),
    symbols: splitSymbols(form.symbols.value),
    tradable_symbols: splitSymbols(form.tradable_symbols.value),
    models: {
      fast_filter: form.elements["models.fast_filter"].value,
      decision: form.elements["models.decision"].value,
      critic: form.elements["models.critic"].value,
      premium_4: form.elements["models.premium_4"].value,
      premium_5: form.elements["models.premium_5"].value,
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
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && $("#terminal")?.classList.contains("fullscreen")) {
      $("#terminal")?.classList.remove("fullscreen");
      document.body.classList.remove("terminal-open");
      renderTerminal(state.status || {});
    }
  });

  document.addEventListener("click", (event) => {
    const configButton = event.target.closest("[data-platform-config]");
    if (configButton) {
      state.selectedPlatformConfig = configButton.dataset.platformConfig;
      renderPlatformConfigHelp(state.selectedPlatformConfig);
      $("#platformConfigHelp")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }

    if (event.target.closest("[data-platform-config-close]")) {
      state.selectedPlatformConfig = null;
      renderPlatformConfigHelp(null);
    }
  });

  $("#riskProfileSelect").addEventListener("change", (event) => {
    applyRiskProfilePreset(event.target.value);
  });

  $("#quickConfigForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    $("#saveState").textContent = "aplicando";
    try {
      const payload = collectQuickConfig();
      await api("/api/config", { method: "POST", body: JSON.stringify(payload) });
      configRendered = false;
      await refresh();
      $("#saveState").textContent = "modo fácil salvo";
      toast("Modo IQ aplicado");
    } catch (err) {
      $("#saveState").textContent = "erro";
      toast(err.message || "Falha ao aplicar modo IQ");
    }
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

  ["terminalUpBtn", "terminalDownBtn"].forEach((id) => {
    const button = $(`#${id}`);
    if (!button) return;
    button.addEventListener("click", async () => {
      toast("Pedido manual em modo demo: rodando auditoria da IA antes de qualquer ação.");
      await saveStakeValue(Number($("#terminalStake")?.value || 1));
      $("#runOnceBtn").click();
    });
  });

  $("#terminalZoomRange")?.addEventListener("input", (event) => {
    setTerminalZoom(event.target.value);
  });

  $("#terminalZoomInBtn")?.addEventListener("click", () => {
    setTerminalZoom(Number(state.terminalZoom || 1) + 1);
  });

  $("#terminalZoomOutBtn")?.addEventListener("click", () => {
    setTerminalZoom(Number(state.terminalZoom || 1) - 1);
  });

  $("#terminalLiveBtn")?.addEventListener("click", () => {
    state.terminalPan = 0;
    renderTerminal(state.status || {});
  });

  $("#terminalFullscreenBtn")?.addEventListener("click", () => {
    const shell = $("#terminal");
    shell?.classList.toggle("fullscreen");
    document.body.classList.toggle("terminal-open", Boolean(shell?.classList.contains("fullscreen")));
    $("#terminalFullscreenBtn").textContent = shell?.classList.contains("fullscreen") ? "SAIR" : "TELA";
    renderTerminal(state.status || {});
  });

  const terminalCanvas = $("#terminalChart");
  terminalCanvas?.addEventListener("wheel", (event) => {
    event.preventDefault();
    setTerminalZoom(Number(state.terminalZoom || 1) + (event.deltaY < 0 ? 1 : -1));
  }, { passive: false });
  terminalCanvas?.addEventListener("pointerdown", (event) => {
    state.terminalDrag = { x: event.clientX, pan: Number(state.terminalPan || 0) };
    terminalCanvas.classList.add("dragging");
    try { terminalCanvas.setPointerCapture(event.pointerId); } catch (_err) {}
  });
  terminalCanvas?.addEventListener("pointermove", (event) => {
    if (!state.terminalDrag) return;
    const candles = getTerminalCandles();
    const zoom = Math.max(1, Number(state.terminalZoom || 1));
    const visibleCount = Math.max(12, Math.min(candles.length, Math.round(candles.length / zoom)));
    const candlesPerPx = visibleCount / Math.max(1, terminalCanvas.clientWidth || 1);
    const delta = (event.clientX - state.terminalDrag.x) * candlesPerPx;
    state.terminalPan = clampTerminalPan(state.terminalDrag.pan + delta);
    renderTerminal(state.status || {});
  });
  ["pointerup", "pointercancel", "pointerleave"].forEach((eventName) => {
    terminalCanvas?.addEventListener(eventName, () => {
      state.terminalDrag = null;
      terminalCanvas.classList.remove("dragging");
    });
  });

  $$("[data-stake-value]").forEach((button) => {
    button.addEventListener("click", () => setStakeValue(button.dataset.stakeValue, true));
  });

  $("#quickConfigForm")?.elements.iqoption_amount?.addEventListener("input", (event) => setStakeValue(event.target.value));
  $("#quickConfigForm")?.elements.iqoption_amount?.addEventListener("change", (event) => setStakeValue(event.target.value, true));

  $("#refreshPlatformsBtn").addEventListener("click", async () => {
    const button = $("#refreshPlatformsBtn");
    button.disabled = true;
    button.textContent = "Atualizando...";
    try {
      const payload = await api("/api/platforms/refresh", { method: "POST", body: "{}" });
      if (state.status) state.status.platforms = payload.platforms || [];
      renderPlatforms(state.status || {});
      renderPlatformConfigHelp(state.selectedPlatformConfig);
      renderStats(state.status || {});
      toast("Conexões de plataformas atualizadas");
    } catch (err) {
      toast(err.message || "Falha ao atualizar plataformas");
    } finally {
      button.disabled = false;
      button.textContent = "Atualizar conexões";
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

  $("#terminalStake")?.addEventListener("input", (event) => {
    const quickStake = $("#quickConfigForm")?.elements.iqoption_amount;
    if (quickStake && quickStake !== document.activeElement) quickStake.value = event.target.value;
    renderStakePresets(Number(event.target.value || 0));
    renderTerminal(state.status || {});
  });
  $("#terminalStake")?.addEventListener("change", (event) => setStakeValue(event.target.value, true));

  $("#logoutBtn").addEventListener("click", async () => {
    await api("/api/logout", { method: "POST", body: "{}" });
    location.href = appPath("/login");
  });
}

window.addEventListener("resize", () => {
  renderChart(state.status || {});
  renderTerminal(state.status || {});
});

(async function boot() {
  bindActions();
  await refresh();
  await refreshModels();
  connectSocket();
  setInterval(() => renderTerminal(state.status || {}), 250);
  setInterval(refresh, 30000);
})();
