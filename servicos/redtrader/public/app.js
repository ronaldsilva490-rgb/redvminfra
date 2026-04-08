const APP_BASE_PATH = location.pathname === "/trader" || location.pathname.startsWith("/trader/") ? "/trader" : "";
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const roles = [
  ["fast_filter", "Scout rápido"],
  ["decision", "Decisor"],
  ["critic", "Crítico"],
  ["premium_4", "Premium 4"],
  ["premium_5", "Premium 5"],
  ["learning", "Aprendizado"],
];

const committeeRoles = roles.filter(([role]) => role !== "learning");

const state = {
  status: null,
  models: [],
  selectedSymbol: "",
  zoom: 32,
  pan: 0,
  socket: null,
  formDirty: false,
  lastDraw: 0,
};

function appPath(path) {
  return `${APP_BASE_PATH}${path}`;
}

function api(path, options = {}) {
  return fetch(appPath(path), {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  }).then(async (response) => {
    if (response.status === 401) {
      location.href = appPath("/login");
      return null;
    }
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
  });
}

function money(value) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value || 0));
}

function pct(value, digits = 1) {
  return `${Number(value || 0).toFixed(digits)}%`;
}

function formatPrice(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return "0.00000";
  if (Math.abs(num) >= 100) return num.toLocaleString("pt-BR", { maximumFractionDigits: 3 });
  return num.toLocaleString("pt-BR", { minimumFractionDigits: 5, maximumFractionDigits: 6 });
}

function timeLabel(ts) {
  if (!ts) return "-";
  return new Date(Number(ts) * 1000).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.remove("hidden");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => el.classList.add("hidden"), 3200);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[ch]));
}

function splitSymbols(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
}

function getPath(obj, path) {
  return path.split(".").reduce((acc, key) => (acc ? acc[key] : undefined), obj);
}

function directionLabel(value) {
  const text = String(value || "").toUpperCase();
  if (["CALL", "BUY", "LONG", "ENTER_LONG", "ACIMA"].includes(text)) return "CALL";
  if (["PUT", "SELL", "SHORT", "ENTER_SHORT", "ABAIXO"].includes(text)) return "PUT";
  return text || "WAIT";
}

function shortModel(model) {
  return String(model || "")
    .replace(" (NVIDIA)", "")
    .replace(" (GROQ)", "")
    .replace("mistralai/", "")
    .replace("qwen/", "")
    .replace("openai/", "")
    .replace("meta/", "")
    .replace("nvidia/", "");
}

async function refresh() {
  const payload = await api("/api/status");
  if (!payload) return;
  receiveStatus(payload);
}

async function refreshModels() {
  try {
    const payload = await api("/api/models");
    state.models = payload.models || [];
    renderModelSelects();
  } catch (err) {
    toast(`Modelos indisponíveis: ${err.message}`);
  }
}

function receiveStatus(payload) {
  state.status = payload;
  if (payload.models?.length) state.models = payload.models;
  const symbols = Object.keys(payload.snapshots || {});
  if (!state.selectedSymbol || !symbols.includes(state.selectedSymbol)) {
    state.selectedSymbol = symbols[0] || (payload.config?.symbols || ["EURUSD-OTC"])[0] || "EURUSD-OTC";
  }
  renderStatus();
}

function renderStatus() {
  const data = state.status;
  if (!data) return;
  renderHeader(data);
  renderSymbols(data);
  renderForms(data.config || {});
  renderCommitteeProgress(data);
  renderConsensusBanner(data);
  renderModelCards(data);
  renderTrades(data);
  renderEvents(data);
}

function renderHeader(data) {
  const wallet = data.wallet || {};
  const recovery = data.iq_recovery || {};
  const openTrades = (data.trades || []).filter((item) => item.status === "OPEN");
  const snapshot = data.snapshots?.[state.selectedSymbol] || {};
  const age = snapshot.ts ? Math.max(0, Date.now() / 1000 - Number(snapshot.ts)) : null;
  $("#balanceValue").textContent = money(wallet.equity_brl);
  $("#pnlValue").textContent = money(wallet.realized_pnl_brl);
  $("#pnlValue").className = Number(wallet.realized_pnl_brl || 0) >= 0 ? "good" : "bad";
  $("#winRateValue").textContent = pct(wallet.win_rate_pct);
  $("#nextStakeValue").textContent = money(recovery.next_amount || data.config?.iqoption_amount || 0);
  $("#runtimeState").textContent = data.running ? "rodando" : "pausado";
  $("#botState").textContent = data.config?.auto_enabled ? "ligado" : "pausado";
  $("#openTradeState").textContent = openTrades.length
    ? `#${openTrades[0].id} ${openTrades[0].symbol} ${openTrades[0].side} · ${money(openTrades[0].position_brl)}`
    : "sem posição aberta";
  $("#feedAge").textContent = age === null ? "feed --" : `feed ${age.toFixed(2)}s`;
  $("#selectedSymbol").textContent = state.selectedSymbol;
  const lastPrice = (snapshot.features || {}).last_price || (snapshot.ticker || {}).last_price;
  $("#terminalPrice").textContent = formatPrice(lastPrice);
  $("#terminalTitle").textContent = `${state.selectedSymbol} · IA operando demo`;
}

function renderSymbols(data) {
  const symbols = Object.keys(data.snapshots || {});
  $("#symbolTabs").innerHTML = symbols.map((symbol) => `
    <button type="button" class="${symbol === state.selectedSymbol ? "active" : ""}" data-symbol="${escapeHtml(symbol)}">
      ${escapeHtml(symbol)}
    </button>
  `).join("");
  $$("#symbolTabs [data-symbol]").forEach((button) => {
    button.onclick = () => {
      state.selectedSymbol = button.dataset.symbol;
      state.pan = 0;
      renderStatus();
    };
  });
}

function renderForms(config) {
  const active = document.activeElement;
  const basic = $("#basicForm");
  const advanced = $("#advancedForm");
  if (!state.formDirty && basic && !basic.contains(active)) {
    const consensus = config.iqoption_consensus_stakes || {};
    const fixed = consensus.tiers || {};
    const pctTiers = consensus.pct_tiers || {};
    basic.elements.auto_enabled.value = String(Boolean(config.auto_enabled));
    basic.elements.risk_profile.value = config.risk_profile || "full_aggressive";
    basic.elements.symbols.value = (config.symbols || []).join(",");
    basic.elements.iqoption_expiration_minutes.value = String(config.iqoption_expiration_minutes || 1);
    basic.elements.cooldown_minutes.value = String(config.cooldown_minutes ?? 0.5);
    basic.elements.stake_mode.value = consensus.mode || config.iqoption_stake_mode || "fixed";
    basic.elements.iqoption_amount.value = config.iqoption_amount ?? 10;
    basic.elements.iqoption_gale_max_steps.value = config.iqoption_gale_max_steps ?? 2;
    basic.elements.iqoption_gale_max_amount.value = config.iqoption_gale_max_amount ?? 100;
    for (const tier of ["2", "3", "4", "5"]) {
      basic.elements[`tier_fixed_${tier}`].value = fixed[tier] ?? ({ "2": 10, "3": 25, "4": 50, "5": 100 }[tier]);
      basic.elements[`tier_pct_${tier}`].value = pctTiers[tier] ?? ({ "2": 1, "3": 2.5, "4": 5, "5": 10 }[tier]);
    }
    const techniques = config.iqoption_techniques || {};
    for (const [name, key] of Object.entries(techniqueFieldMap())) {
      if (basic.elements[name]) basic.elements[name].checked = techniques[key] !== false;
    }
  }
  if (advanced && !advanced.contains(active)) {
    const consensus = config.iqoption_consensus_stakes || {};
    const learning = config.iqoption_learning || {};
    advanced.elements.min_votes.value = consensus.min_votes ?? 2;
    advanced.elements.recovery_min_votes.value = consensus.recovery_min_votes ?? 3;
    advanced.elements.learning_enabled.value = String(learning.enabled !== false);
    advanced.elements.learning_reflection.value = String(learning.use_model_reflection !== false);
    advanced.elements.learning_interval_seconds.value = learning.interval_seconds ?? 150;
    advanced.elements.learning_min_new_closed.value = learning.min_new_closed ?? 5;
    advanced.elements.min_technical_score.value = config.min_technical_score ?? 55;
    advanced.elements.min_ai_confidence.value = config.min_ai_confidence ?? 55;
    advanced.elements.max_decision_latency_ms.value = config.max_decision_latency_ms ?? 8000;
    advanced.elements.max_signal_age_seconds.value = config.max_signal_age_seconds ?? 4;
    renderModelSelects();
  }
}

function renderModelSelects() {
  const config = state.status?.config || {};
  $$("[data-model-select]").forEach((select) => {
    const current = getPath(config, select.name) || select.value || "";
    const values = [...new Set([current, ...state.models].filter(Boolean))];
    select.innerHTML = values.map((model) => `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`).join("");
    select.value = current;
  });
}

function techniqueFieldMap() {
  return {
    tech_multi_timeframe_confluence: "multi_timeframe_confluence",
    tech_momentum_continuation: "momentum_continuation",
    tech_trend_pullback: "trend_pullback",
    tech_reversal_exhaustion: "reversal_exhaustion",
    tech_volatility_filter: "volatility_filter",
    tech_anti_repeat_loss: "anti_repeat_loss",
    tech_adaptive_recovery: "adaptive_recovery",
  };
}

function learningSummary(role, data) {
  if (role !== "learning") return "";
  const learning = data.iq_learning || {};
  const lessons = learning.lessons || [];
  const avoids = (learning.avoid_patterns || []).filter((item) => Number(item.expires_at || 0) > Date.now() / 1000);
  if (lessons.length) return lessons.slice(-3).join(" · ");
  if (avoids.length) return avoids.slice(0, 3).map((item) => `${item.symbol} ${item.direction}: ${item.reason}`).join(" · ");
  return "Memória operacional aguardando perdas/fechamentos suficientes para refletir.";
}

function currentCommittee(data) {
  return data.committee || {};
}

function renderCommitteeProgress(data) {
  const wrap = $("#committeeProgress");
  const fill = $("#committeeProgressFill");
  if (!wrap || !fill) return;
  const committee = currentCommittee(data);
  const progress = committee.progress || {};
  const total = Number(progress.total || 0);
  const completed = Number(progress.completed || 0);
  const running = Number(progress.running || 0);
  const percent = Number(progress.percent || 0);
  const symbol = committee.symbol || "-";
  if (!total) {
    wrap.className = "committee-progress idle";
    fill.style.width = "0%";
    fill.textContent = "Aguardando o proximo comite";
    return;
  }
  wrap.className = `committee-progress ${committee.active ? "active" : "done"}`;
  fill.style.width = `${Math.max(4, Math.min(100, percent))}%`;
  fill.textContent = committee.active
    ? `${symbol} · ${completed}/${total} concluidos · ${running} em andamento`
    : `${symbol} · ${completed}/${total} concluidos`;
}

function latestCommitteeEvent(data) {
  const events = data.events || [];
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const event = events[i];
    if (event.type === "trade:skipped" || event.type === "trade:opened") return event;
  }
  return null;
}

function renderConsensusBanner(data) {
  const el = $("#consensusBanner");
  if (!el) return;
  const event = latestCommitteeEvent(data);
  if (!event) {
    el.innerHTML = `<span>Aguardando o próximo consenso do comitê.</span>`;
    return;
  }
  const payload = event.data || {};
  const consensus = payload.consensus || {};
  const votes = consensus.votes || [];
  const validVotes = votes.filter((vote) => vote.valid && (vote.direction === "CALL" || vote.direction === "PUT"));
  const direction = consensus.direction || "-";
  const tier = Number(consensus.tier || validVotes.length || 0);
  const minVotes = Number(consensus.required_recovery_votes || consensus.min_votes || data.config?.iqoption_consensus_stakes?.min_votes || 3);
  const invalidCount = Number(consensus.invalid_vote_count ?? Math.max(0, votes.length - validVotes.length));
  const profile = consensus.profile_gate?.key || data.config?.risk_profile || "-";
  const css = event.type === "trade:opened" ? "ok" : "blocked";
  const validText = validVotes.length
    ? validVotes.map((vote) => `${vote.role}:${vote.direction}`).join(" · ")
    : "nenhum voto CALL/PUT válido";
  el.className = `consensus-banner ${css}`;
  el.innerHTML = `
    <strong>${event.type === "trade:opened" ? "Entrada liberada" : "Entrada bloqueada"}</strong>
    <span>${escapeHtml(profile)} · ${escapeHtml(direction)} · ${tier}/${votes.length || 5} votos válidos · mínimo ${minVotes} · nulos/WAIT ${invalidCount}</span>
    <small>${escapeHtml(payload.reason || event.message || "-")} · ${escapeHtml(validText)}</small>
  `;
}

function renderModelCards(data) {
  const analyses = data.analyses || [];
  const byRole = {};
  for (const item of analyses) {
    if (!byRole[item.role]) byRole[item.role] = item;
  }
  $("#modelCards").innerHTML = roles.map(([role, label]) => {
    const item = byRole[role] || {};
    const response = item.response || {};
    const vote = directionLabel(response.decision || response.preferred_decision || item.decision);
    const valid = vote === "CALL" || vote === "PUT";
    const summary = response.reasoning_summary || response.reason || item.summary || learningSummary(role, data) || "Aguardando o próximo ciclo.";
    const latency = item.latency_ms ? `${item.latency_ms}ms` : "--";
    const configuredModel = role === "learning"
      ? data.config?.iqoption_learning?.model
      : data.config?.models?.[role];
    return `
      <article class="model-card ${valid ? vote.toLowerCase() : "wait"}">
        <header>
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(vote)}</strong>
        </header>
        <p>${escapeHtml(shortModel(item.model || configuredModel || role))}</p>
        <small>${escapeHtml(item.symbol || "-")} · conf ${Number(item.confidence || response.confidence || 0).toFixed(0)} · ${latency}</small>
        <em>${escapeHtml(summary).slice(0, 230)}</em>
      </article>
    `;
  }).join("");
}

function renderTrades(data) {
  const trades = data.trades || [];
  $("#tradesList").innerHTML = trades.slice(0, 14).map((trade) => {
    const pnl = Number(trade.pnl_brl || 0);
    const meta = trade.metadata || {};
    const status = trade.status === "OPEN" ? "OPEN" : pnl >= 0 ? "WIN" : "LOSS";
    return `
      <article class="trade-row ${status.toLowerCase()}">
        <strong>#${trade.id} ${escapeHtml(trade.symbol)} ${escapeHtml(trade.side)}</strong>
        <span>${escapeHtml(status)} · ${money(trade.position_brl)} · ${money(pnl)}</span>
        <small>G${meta.gale_stage || 0} · ${timeLabel(trade.opened_at)} · ${escapeHtml(trade.exit_reason || "ao vivo")}</small>
      </article>
    `;
  }).join("") || `<p class="muted">Ainda sem operações.</p>`;
}

function renderEvents(data) {
  const events = data.events || [];
  $("#eventsList").innerHTML = events.slice(-80).reverse().map((event) => `
    <article>
      <strong>${escapeHtml(event.type)}</strong>
      <span>${escapeHtml(event.message)}</span>
      <small>${timeLabel(event.ts)}</small>
    </article>
  `).join("");
}

function renderConsensusBanner(data) {
  const el = $("#consensusBanner");
  if (!el) return;
  const committee = currentCommittee(data);
  const progress = committee.progress || {};
  const result = committee.result || {};
  if (committee.symbol) {
    const css = committee.active ? "active" : result.approved ? "ok" : result.reason ? "blocked" : "";
    const direction = result.direction || committee.candidate?.direction || "-";
    const profile = committee.profile || data.config?.risk_profile || "-";
    const minVotes = Number(result.min_votes || 0);
    const validVotes = Number(result.valid_votes || progress.completed || 0);
    const invalidVotes = Number(result.invalid_votes || 0);
    const statusLine = committee.active
      ? `Analisando ${committee.symbol}`
      : result.approved
        ? "Entrada liberada"
        : result.reason
          ? "Entrada bloqueada"
          : "Ultimo comite concluido";
    const reasonLine = committee.active
      ? "Todos os cards abaixo pertencem ao mesmo ciclo e ao mesmo par."
      : result.reason || "Aguardando o proximo consenso.";
    el.className = `consensus-banner ${css}`.trim();
    el.innerHTML = `
      <strong>${statusLine}</strong>
      <span>${escapeHtml(profile)} · ${escapeHtml(direction)} · validos ${validVotes} · minimo ${minVotes || "-"} · nulos/WAIT ${invalidVotes}</span>
      <small>${escapeHtml(reasonLine)}</small>
    `;
    return;
  }
  const event = latestCommitteeEvent(data);
  if (!event) {
    el.className = "consensus-banner";
    el.innerHTML = `<span>Aguardando o proximo consenso do comite.</span>`;
    return;
  }
  const payload = event.data || {};
  el.className = `consensus-banner ${event.type === "trade:opened" ? "ok" : "blocked"}`;
  el.innerHTML = `
    <strong>${event.type === "trade:opened" ? "Entrada liberada" : "Entrada bloqueada"}</strong>
    <span>${escapeHtml(payload.reason || event.message || "-")}</span>
  `;
}

function renderModelCards(data) {
  const committee = currentCommittee(data);
  const roleMap = committee.roles || {};
  $("#modelCards").innerHTML = roles.map(([role, label]) => {
    if (role === "learning") {
      const learning = data.iq_learning || {};
      const learningModel = data.config?.iqoption_learning?.model || learning.model || role;
      return `
        <article class="model-card wait">
          <header>
            <span>${escapeHtml(label)}</span>
            <strong>MEMORIA</strong>
          </header>
          <p>${escapeHtml(shortModel(learningModel))}</p>
          <small>${escapeHtml(committee.symbol || state.selectedSymbol || "-")} · regras ${Number((learning.lessons || []).length || 0)} · bloqueios ${Number((learning.avoid_patterns || []).length || 0)}</small>
          <em>${escapeHtml(learningSummary(role, data)).slice(0, 230)}</em>
        </article>
      `;
    }
    const item = roleMap[role] || {};
    const vote = directionLabel(item.decision || "WAIT");
    const valid = vote === "CALL" || vote === "PUT";
    const status = String(item.status || (item.model ? "queued" : "missing")).toLowerCase();
    const stateLabel = {
      queued: "NA FILA",
      running: "ANALISANDO",
      done: vote,
      timeout: "TIMEOUT",
      error: "ERRO",
      missing: "SEM MODELO",
      reused: "REAPROVEITADO",
    }[status] || vote;
    const summary = item.summary || "Aguardando o proximo ciclo.";
    const latency = item.latency_ms ? `${item.latency_ms}ms` : "--";
    const configuredModel = data.config?.models?.[role];
    const css = valid ? vote.toLowerCase() : status === "running" ? "running" : status === "error" || status === "timeout" ? "error" : "wait";
    return `
      <article class="model-card ${css}">
        <header>
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(stateLabel)}</strong>
        </header>
        <p>${escapeHtml(shortModel(item.model || configuredModel || role))}</p>
        <small>${escapeHtml(item.symbol || committee.symbol || "-")} · conf ${Number(item.confidence || 0).toFixed(0)} · ${latency}</small>
        <em>${escapeHtml(summary).slice(0, 230)}</em>
      </article>
    `;
  }).join("");
}

function collectBasicConfig() {
  const form = $("#basicForm");
  const current = state.status?.config || {};
  const consensus = current.iqoption_consensus_stakes || {};
  const techniques = {};
  for (const [name, key] of Object.entries(techniqueFieldMap())) {
    techniques[key] = Boolean(form.elements[name]?.checked);
  }
  const symbols = splitSymbols(form.elements.symbols.value || "EURUSD-OTC");
  const activeSymbols = symbols.length ? symbols : ["EURUSD-OTC"];
  const mode = form.elements.stake_mode.value;
  const riskProfile = form.elements.risk_profile.value;
  const decisionPollByProfile = {
    conservative: 4,
    balanced: 3,
    aggressive: 1.5,
    full_aggressive: 1,
  };
  const marketPollByProfile = {
    conservative: 0.5,
    balanced: 0.35,
    aggressive: 0.25,
    full_aggressive: 0.25,
  };
  const tiers = {};
  const pctTiers = {};
  for (const tier of ["2", "3", "4", "5"]) {
    tiers[tier] = Number(form.elements[`tier_fixed_${tier}`].value || 0);
    pctTiers[tier] = Number(form.elements[`tier_pct_${tier}`].value || 0);
  }
  return {
    ...current,
    auto_enabled: form.elements.auto_enabled.value === "true",
    risk_profile: riskProfile,
    market_provider: "iqoption_demo",
    execution_provider: "iqoption_demo",
    symbols: activeSymbols,
    tradable_symbols: activeSymbols,
    iqoption_stake_mode: mode,
    iqoption_amount: Number(form.elements.iqoption_amount.value || 1),
    iqoption_expiration_minutes: Number(form.elements.iqoption_expiration_minutes.value || 1),
    iqoption_gale_enabled: true,
    iqoption_gale_max_steps: Number(form.elements.iqoption_gale_max_steps.value || 0),
    iqoption_gale_max_amount: Number(form.elements.iqoption_gale_max_amount.value || 100),
    cooldown_minutes: Number(form.elements.cooldown_minutes.value || 0.5),
    market_poll_seconds: marketPollByProfile[riskProfile] || 0.25,
    decision_poll_seconds: decisionPollByProfile[riskProfile] || 2,
    max_open_positions: 1,
    iqoption_consensus_stakes: {
      ...consensus,
      enabled: true,
      mode,
      tiers,
      pct_tiers: pctTiers,
    },
    iqoption_learning: {
      ...(current.iqoption_learning || {}),
      enabled: true,
      apply_code_memory: true,
    },
    iqoption_techniques: techniques,
    platforms: {
      ...(current.platforms || {}),
      binance_spot: { enabled: false, mode: "market_data_paper", label: "Binance Spot" },
      tastytrade_sandbox: { enabled: false, mode: "sandbox", label: "tastytrade Sandbox" },
      webull_paper: { enabled: false, mode: "paper", label: "Webull Paper" },
      iqoption_experimental: { enabled: true, mode: "demo", label: "IQ Option Demo" },
    },
  };
}

function collectAdvancedConfig() {
  const form = $("#advancedForm");
  const current = state.status?.config || {};
  const consensus = current.iqoption_consensus_stakes || {};
  const learning = current.iqoption_learning || {};
  return {
    ...current,
    min_technical_score: Number(form.elements.min_technical_score.value || 55),
    min_ai_confidence: Number(form.elements.min_ai_confidence.value || 55),
    max_decision_latency_ms: Number(form.elements.max_decision_latency_ms.value || 8000),
    max_signal_age_seconds: Number(form.elements.max_signal_age_seconds.value || 4),
    iqoption_consensus_stakes: {
      ...consensus,
      min_votes: Number(form.elements.min_votes.value || 2),
      recovery_min_votes: Number(form.elements.recovery_min_votes.value || 3),
    },
    iqoption_learning: {
      ...learning,
      enabled: form.elements.learning_enabled.value === "true",
      use_model_reflection: form.elements.learning_reflection.value === "true",
      interval_seconds: Number(form.elements.learning_interval_seconds.value || 150),
      min_new_closed: Number(form.elements.learning_min_new_closed.value || 5),
      model: form.elements["iqoption_learning.model"].value,
    },
    models: {
      ...(current.models || {}),
      fast_filter: form.elements["models.fast_filter"].value,
      decision: form.elements["models.decision"].value,
      critic: form.elements["models.critic"].value,
      premium_4: form.elements["models.premium_4"].value,
      premium_5: form.elements["models.premium_5"].value,
      report: form.elements["models.report"].value,
    },
  };
}

async function saveConfig(payload, message = "Configuração salva") {
  $("#saveState").textContent = "salvando...";
  const saved = await api("/api/config", { method: "POST", body: JSON.stringify(payload) });
  if (state.status && saved?.config) state.status.config = saved.config;
  state.formDirty = false;
  $("#saveState").textContent = "sincronizado";
  toast(message);
  await refresh();
}

function connectSocket() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${location.host}${APP_BASE_PATH}/ws`);
  state.socket = ws;
  ws.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "status") receiveStatus(payload.data);
    if (payload.type === "event" && state.status) {
      state.status.events = [...(state.status.events || []), payload.data].slice(-140);
      renderEvents(state.status);
      if (["trade:opened", "trade:closed", "config", "gale:state"].includes(payload.data.type)) {
        setTimeout(refresh, 150);
      }
    }
  };
  ws.onclose = () => setTimeout(connectSocket, 1500);
}

function bindActions() {
  $("#basicForm").addEventListener("input", () => {
    state.formDirty = true;
    $("#saveState").textContent = "alterações não salvas";
  });
  $("#basicForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await saveConfig(collectBasicConfig(), "Ajustes básicos aplicados");
    } catch (err) {
      $("#saveState").textContent = "erro";
      toast(err.message || "Falha ao salvar");
    }
  });
  $("#advancedForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await saveConfig(collectAdvancedConfig(), "Ajustes avançados aplicados");
    } catch (err) {
      toast(err.message || "Falha ao salvar avançado");
    }
  });
  $("#runOnceBtn").addEventListener("click", async () => {
    const button = $("#runOnceBtn");
    button.disabled = true;
    button.textContent = "Analisando...";
    try {
      const payload = await api("/api/run-once", { method: "POST", body: "{}" });
      receiveStatus(payload.status);
      toast("Análise rodada");
    } catch (err) {
      toast(err.message || "Falha ao analisar");
    } finally {
      button.disabled = false;
      button.textContent = "Analisar agora";
    }
  });
  $("#refreshBtn").addEventListener("click", () => refresh().catch((err) => toast(err.message)));
  $("#logoutBtn").addEventListener("click", async () => {
    await api("/api/logout", { method: "POST", body: "{}" });
    location.href = appPath("/login");
  });
  $("#zoomRange").addEventListener("input", (event) => {
    state.zoom = Number(event.target.value || 30);
  });
  $("#liveBtn").addEventListener("click", () => {
    state.pan = 0;
    toast("Gráfico no ao vivo");
  });
  const canvas = $("#terminalCanvas");
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    state.zoom = Math.max(1, Math.min(80, state.zoom + (event.deltaY < 0 ? 2 : -2)));
    $("#zoomRange").value = String(state.zoom);
  }, { passive: false });
}

function terminalCandles() {
  const snapshot = state.status?.snapshots?.[state.selectedSymbol] || {};
  return snapshot.candles?.["1s"]?.length ? snapshot.candles["1s"] : snapshot.candles?.["1m"] || [];
}

function drawTerminalChart() {
  const canvas = $("#terminalCanvas");
  const data = state.status;
  if (!canvas || !data) return;
  const container = canvas.parentElement;
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(720, container.clientWidth);
  const height = Math.max(560, Math.min(820, window.innerHeight - 280));
  if (canvas.width !== Math.floor(width * ratio) || canvas.height !== Math.floor(height * ratio)) {
    canvas.width = Math.floor(width * ratio);
    canvas.height = Math.floor(height * ratio);
    canvas.style.height = `${height}px`;
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#020304";
  ctx.fillRect(0, 0, width, height);

  const all = terminalCandles();
  if (!all.length) {
    ctx.fillStyle = "#8d98a6";
    ctx.font = "800 15px Inter, sans-serif";
    ctx.fillText("Aguardando feed da IQ...", 28, 42);
    return;
  }

  const visibleCount = Math.max(16, Math.min(all.length, Math.round(620 / Math.max(1, state.zoom))));
  const end = all.length - Math.max(0, state.pan);
  const candles = all.slice(Math.max(0, end - visibleCount), end);
  const pad = { l: 58, r: 96, t: 36, b: 34 };
  const values = candles.flatMap((candle) => [Number(candle.high), Number(candle.low)]).filter(Number.isFinite);
  const rawMax = Math.max(...values);
  const rawMin = Math.min(...values);
  const spanPad = Math.max((rawMax - rawMin) * 0.18, Math.abs(rawMax || 1) * 0.00008);
  const max = rawMax + spanPad;
  const min = rawMin - spanPad;
  const span = max - min || 1;
  const plotW = width - pad.l - pad.r;
  const plotH = height - pad.t - pad.b;
  const firstTime = Number(candles[0].time || 0);
  const lastTime = Number(candles[candles.length - 1].time || firstTime + 1);
  const domainEnd = lastTime + 7;
  const domainStart = firstTime;
  const xTime = (ts) => pad.l + ((Number(ts || domainEnd) - domainStart) / Math.max(1, domainEnd - domainStart)) * plotW;
  const yPrice = (value) => pad.t + (max - Number(value)) / span * plotH;

  ctx.strokeStyle = "#121922";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 10; i++) {
    const x = pad.l + (plotW / 10) * i;
    ctx.beginPath();
    ctx.moveTo(x, pad.t);
    ctx.lineTo(x, height - pad.b);
    ctx.stroke();
  }
  for (let i = 0; i <= 6; i++) {
    const y = pad.t + (plotH / 6) * i;
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(width - pad.r, y);
    ctx.stroke();
  }

  const gradient = ctx.createLinearGradient(0, pad.t, 0, height - pad.b);
  gradient.addColorStop(0, "rgba(242, 122, 26, 0.34)");
  gradient.addColorStop(1, "rgba(242, 122, 26, 0.02)");
  ctx.beginPath();
  candles.forEach((candle, index) => {
    const x = xTime(candle.time);
    const y = yPrice(candle.close);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.lineTo(xTime(lastTime), height - pad.b);
  ctx.lineTo(pad.l, height - pad.b);
  ctx.closePath();
  ctx.fillStyle = gradient;
  ctx.fill();

  ctx.beginPath();
  candles.forEach((candle, index) => {
    const x = xTime(candle.time);
    const y = yPrice(candle.close);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "#f27a1a";
  ctx.lineWidth = 2.4;
  ctx.shadowColor = "rgba(242, 122, 26, 0.65)";
  ctx.shadowBlur = 12;
  ctx.stroke();
  ctx.shadowBlur = 0;

  drawTradeMarkers(ctx, data, { pad, width, height, yPrice, xTime, domainStart, domainEnd });

  const last = candles[candles.length - 1];
  const lastY = yPrice(last.close);
  const lastX = xTime(last.time);
  ctx.setLineDash([5, 5]);
  ctx.strokeStyle = "rgba(242, 122, 26, 0.78)";
  ctx.beginPath();
  ctx.moveTo(pad.l, lastY);
  ctx.lineTo(width - pad.r + 4, lastY);
  ctx.stroke();
  ctx.setLineDash([]);
  const pulse = 4 + Math.sin(Date.now() / 120) * 2;
  ctx.fillStyle = "#34d27d";
  ctx.beginPath();
  ctx.arc(lastX, lastY, pulse, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#f27a1a";
  ctx.fillRect(width - pad.r + 9, lastY - 15, 78, 30);
  ctx.fillStyle = "#170600";
  ctx.font = "900 12px Inter, sans-serif";
  ctx.fillText(formatPrice(last.close), width - pad.r + 15, lastY + 5);

  ctx.fillStyle = "#77828f";
  ctx.font = "11px Inter, sans-serif";
  for (let i = 0; i <= 4; i++) {
    const ts = domainStart + ((domainEnd - domainStart) / 4) * i;
    ctx.fillText(timeLabel(ts), pad.l + (plotW / 4) * i, height - 12);
  }
  ctx.fillStyle = "#ffbf8c";
  ctx.font = "900 12px Inter, sans-serif";
  ctx.fillText(`${state.selectedSymbol} · ${visibleCount} pontos · zoom ${state.zoom}x`, pad.l, 22);
}

function drawTradeMarkers(ctx, data, scale) {
  const trades = (data.trades || []).filter((trade) => {
    const opened = Number(trade.opened_at || 0);
    const expiry = opened + Number((trade.metadata || {}).expiry_seconds || 60);
    return trade.symbol === state.selectedSymbol && expiry >= scale.domainStart - 5 && opened <= scale.domainEnd + 5;
  });
  for (const trade of trades.slice(0, 18)) {
    const pnl = Number(trade.pnl_brl || 0);
    const isOpen = trade.status === "OPEN";
    const color = isOpen ? "#fff2a6" : pnl >= 0 ? "#35ff93" : "#ff6972";
    const opened = Number(trade.opened_at || 0);
    const expiry = opened + Number((trade.metadata || {}).expiry_seconds || 60);
    const x = Math.max(scale.pad.l, Math.min(scale.width - scale.pad.r, scale.xTime(opened)));
    const ex = Math.max(scale.pad.l, Math.min(scale.width - scale.pad.r, scale.xTime(expiry)));
    const y = scale.yPrice(trade.entry_price);
    const side = directionLabel(trade.side);
    const stage = (trade.metadata || {}).gale_stage || 0;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.setLineDash([3, 6]);
    ctx.beginPath();
    ctx.moveTo(x, scale.pad.t);
    ctx.lineTo(x, scale.height - scale.pad.b);
    ctx.stroke();
    if (isOpen) {
      ctx.beginPath();
      ctx.moveTo(ex, scale.pad.t);
      ctx.lineTo(ex, scale.height - scale.pad.b);
      ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.fillStyle = color;
    ctx.beginPath();
    if (side === "PUT") {
      ctx.moveTo(x, y + 10);
      ctx.lineTo(x - 8, y - 7);
      ctx.lineTo(x + 8, y - 7);
    } else {
      ctx.moveTo(x, y - 10);
      ctx.lineTo(x - 8, y + 7);
      ctx.lineTo(x + 8, y + 7);
    }
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "rgba(2, 3, 4, 0.88)";
    ctx.fillRect(x + 10, y - 18, 86, 28);
    ctx.strokeStyle = color;
    ctx.strokeRect(x + 10, y - 18, 86, 28);
    ctx.fillStyle = color;
    ctx.font = "900 11px Inter, sans-serif";
    ctx.fillText(`#${trade.id} ${side}${stage ? ` G${stage}` : ""}`, x + 16, y);
    ctx.restore();
  }
}

function drawLoop() {
  drawTerminalChart();
  requestAnimationFrame(drawLoop);
}

window.addEventListener("resize", drawTerminalChart);

(async function boot() {
  bindActions();
  await refresh();
  await refreshModels();
  connectSocket();
  requestAnimationFrame(drawLoop);
  setInterval(() => refresh().catch(() => {}), 2500);
})();
