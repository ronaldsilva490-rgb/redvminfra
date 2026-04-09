const DEFAULT_CONFIG = {
  enabled: true,
  demoOnly: true,
  sampleIntervalMs: 250,
  maxTicks: 240,
  sendIntervalMs: 500,
  rawSnapshotIntervalMs: 2500,
};

const ROOT_ID = "red-iq-demo-vision-root";
const BRIDGE_SOURCE = "RED_IQ_BRIDGE";
const EXT_VERSION = chrome.runtime.getManifest().version;
const POS_KEY = "rediq.overlay.position";
const MIN_KEY = "rediq.overlay.minimized";
const VALID_ASSET_CODES = new Set([
  "AED", "AUD", "BRL", "CAD", "CHF", "CLP", "CNH", "CNY", "COP", "CZK", "DKK",
  "DZD", "EGP", "EUR", "GBP", "GEL", "HKD", "HUF", "IDR", "ILS", "INR", "JPY",
  "KES", "KWD", "MAD", "MXN", "MYR", "NGN", "NOK", "NZD", "OMR", "PEN", "PHP",
  "PLN", "QAR", "RON", "RUB", "SAR", "SEK", "SGD", "THB", "TRY", "TWD", "UAH",
  "USD", "XAF", "XAU", "XAG", "XPD", "XPT", "ZAR",
]);
const SEEDED_ASSET_MAP = {
  1: "EUR/USD",
  2: "EUR/GBP",
  3: "GBP/JPY",
  4: "EUR/JPY",
  6: "USD/JPY",
  7: "AUD/CAD",
  8: "NZD/USD",
  72: "USD/CHF",
  74: "XAU/USD",
  76: "EUR/USD-OTC",
  77: "EUR/GBP-OTC",
  78: "USD/CHF-OTC",
  79: "EUR/JPY-OTC",
  80: "NZD/USD-OTC",
};

const DEFAULT_CONTROL_ANCHORS = {
  amount_minus: { x: 0.952, y: 0.104 },
  amount_plus: { x: 0.986, y: 0.104 },
  expiry_minus: { x: 0.952, y: 0.192 },
  expiry_plus: { x: 0.986, y: 0.192 },
  trade_call: { x: 0.945, y: 0.405 },
  open_new_option: { x: 0.945, y: 0.49 },
  trade_put: { x: 0.945, y: 0.553 },
};

const state = {
  config: { ...DEFAULT_CONFIG },
  uiReady: false,
  started: false,
  lastSentAt: 0,
  lastFrameSentAt: 0,
  lastDomMutationAt: 0,
  intervalId: 0,
  current: {
    mode: "unknown",
    demoAllowed: false,
    asset: "-",
    marketType: "-",
    payoutPct: null,
    countdown: "-",
    currentPrice: null,
    tickAgeMs: null,
    buyWindowOpen: null,
    suspendedHint: false,
    entryHint: "Aguardando leitura inicial",
    notes: [],
    updatedAt: null,
    debug: {},
  },
  ticks: [],
  ticksByActiveId: {},
  ws: {
    samples: [],
    lastMessageAt: 0,
    lastUrl: "",
  },
  canvasText: {
    samples: [],
    lastMessageAt: 0,
  },
  net: {
    samples: [],
    lastMessageAt: 0,
  },
  storage: {
    samples: [],
    lastReadAt: 0,
  },
  transport: {
    samples: [],
    lastAt: 0,
  },
  ids: {
    selectedAssetId: null,
    selectedAssetType: null,
    selectedAssetAt: 0,
    quoteActiveId: null,
    quoteActiveAt: 0,
  },
  live: {
    currentPrice: null,
    priceSource: "",
    activeId: null,
    payoutPct: null,
    marketType: "",
    countdownLabel: "",
    countdownSeconds: null,
    suspendedHint: false,
    serverTimeMs: null,
    lastAt: 0,
  },
  liveBook: {},
  assetMap: { ...SEEDED_ASSET_MAP },
  assetMeta: {},
  marketCache: {},
  diagnostics: {
    lastKeys: {},
    lastResolutionKey: "",
  },
  raw: {
    lastSnapshotSentAt: 0,
    lastSnapshotKey: "",
  },
  canvasCapture: {
    lastSentAt: 0,
    lastCanvasMeta: null,
    lastError: "",
  },
  overlay: {
    minimized: false,
    dragging: false,
    offsetX: 0,
    offsetY: 0,
    left: null,
    top: null,
  },
  layout: {
    viewport: {
      width: 0,
      height: 0,
      dpr: 1,
    },
    anchors: {},
    clicks: [],
  },
  trade: {
    openPositionsCount: 0,
    lastPortfolioAt: 0,
    lastTradeUiAt: 0,
    lastOpenOptionTemplate: null,
    userBalanceId: null,
  },
  bridgeCommands: {
    seq: 0,
    pending: {},
  },
  runtime: {
    iqResponses: [],
    tradeEvents: [],
  },
};

function now() {
  return Date.now();
}

function normalizeText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function safePreview(value, max = 320) {
  const text = normalizeText(typeof value === "string" ? value : JSON.stringify(value));
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

function toNumber(value) {
  if (value == null) return null;
  const cleaned = String(value)
    .replace(/[^\d,.-]/g, "")
    .replace(/\.(?=\d{3}\b)/g, "")
    .replace(",", ".");
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function stripOtcSuffix(label) {
  return String(label || "").replace(/-OTC$/i, "");
}

function hasOtcSuffix(label) {
  return /-OTC$/i.test(String(label || ""));
}

function average(values) {
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function viewportSnapshot() {
  return {
    width: Math.max(1, window.innerWidth || document.documentElement?.clientWidth || 1),
    height: Math.max(1, window.innerHeight || document.documentElement?.clientHeight || 1),
    dpr: Number(window.devicePixelRatio || 1),
  };
}

function normalizeViewportPoint(x, y, viewport = viewportSnapshot()) {
  const width = Math.max(1, Number(viewport?.width) || 1);
  const height = Math.max(1, Number(viewport?.height) || 1);
  const pointX = Number(x);
  const pointY = Number(y);
  if (!Number.isFinite(pointX) || !Number.isFinite(pointY)) return null;
  if (pointX < 0 || pointY < 0) return null;
  if (pointX > width * 1.05 || pointY > height * 1.05) return null;
  return {
    x: pointX,
    y: pointY,
    xNorm: Number((pointX / width).toFixed(6)),
    yNorm: Number((pointY / height).toFixed(6)),
    viewport: {
      width,
      height,
      dpr: Number(viewport?.dpr || 1),
    },
  };
}

function pointFromAnchor(anchor, viewport = viewportSnapshot()) {
  if (!anchor) return null;
  const width = Math.max(1, Number(viewport?.width) || 1);
  const height = Math.max(1, Number(viewport?.height) || 1);
  const xNorm = Number(anchor?.xNorm ?? anchor?.x);
  const yNorm = Number(anchor?.yNorm ?? anchor?.y);
  if (!Number.isFinite(xNorm) || !Number.isFinite(yNorm)) return null;
  return {
    x: Math.round(xNorm * width),
    y: Math.round(yNorm * height),
    xNorm,
    yNorm,
    viewport: {
      width,
      height,
      dpr: Number(viewport?.dpr || 1),
    },
  };
}

function isSaneAnchorPoint(point) {
  if (!point) return false;
  if (!Number.isFinite(point.xNorm) || !Number.isFinite(point.yNorm)) return false;
  return point.xNorm >= 0 && point.xNorm <= 1.02 && point.yNorm >= 0 && point.yNorm <= 1.02;
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, Math.max(0, Number(ms) || 0)));
}

function pushBounded(list, item, limit = 40) {
  list.push(item);
  while (list.length > limit) list.shift();
}

function guessPricePrecision(price) {
  if (!Number.isFinite(price)) return 6;
  const text = String(price);
  const [, decimals = ""] = text.split(".");
  return clamp(decimals.length || 6, 3, 6);
}

function optionTypeIdFromSelection(value) {
  if (Number.isFinite(value)) return Number(value);
  const text = String(value || "").toLowerCase();
  if (!text) return 3;
  if (text.includes("digital")) return 1;
  if (text.includes("blitz")) return 7;
  if (text.includes("turbo") || text.includes("binary") || text.includes("binaria")) return 3;
  return 3;
}

function updateViewportState() {
  state.layout.viewport = viewportSnapshot();
}

function classifyControlAnchor(point) {
  if (!point) return "";
  const { xNorm, yNorm } = point;
  if (xNorm < 0.78) return "";
  if (xNorm > 0.93 && yNorm >= 0.08 && yNorm <= 0.14) {
    return xNorm >= 0.975 ? "amount_plus" : "amount_minus";
  }
  if (xNorm > 0.93 && yNorm >= 0.16 && yNorm <= 0.24) {
    return xNorm >= 0.975 ? "expiry_plus" : "expiry_minus";
  }
  if (xNorm > 0.88 && yNorm >= 0.34 && yNorm <= 0.46) return "trade_call";
  if (xNorm > 0.88 && yNorm >= 0.47 && yNorm <= 0.53) return "open_new_option";
  if (xNorm > 0.88 && yNorm >= 0.54 && yNorm <= 0.66) return "trade_put";
  return "";
}

function rememberLayoutAnchor(name, point, meta = {}) {
  if (!name || !point) return null;
  if (!isSaneAnchorPoint(point)) return null;
  const previous = state.layout.anchors[name];
  const count = Math.min((previous?.count || 0) + 1, 25);
  const xNorm = previous
    ? (((previous.xNorm * (count - 1)) + point.xNorm) / count)
    : point.xNorm;
  const yNorm = previous
    ? (((previous.yNorm * (count - 1)) + point.yNorm) / count)
    : point.yNorm;
  const anchor = {
    name,
    xNorm: Number(xNorm.toFixed(6)),
    yNorm: Number(yNorm.toFixed(6)),
    count,
    source: meta.source || previous?.source || "runtime",
    lastAt: now(),
    viewport: point.viewport || previous?.viewport || viewportSnapshot(),
    raw: {
      x: point.x,
      y: point.y,
    },
  };
  state.layout.anchors[name] = anchor;
  return anchor;
}

function getControlAnchor(name) {
  updateViewportState();
  const learned = state.layout.anchors[name];
  if (learned) {
    const learnedPoint = pointFromAnchor(learned, state.layout.viewport);
    if (isSaneAnchorPoint(learnedPoint)) return learned;
    delete state.layout.anchors[name];
  }
  const fallback = DEFAULT_CONTROL_ANCHORS[name];
  if (!fallback) return null;
  return {
    name,
    xNorm: fallback.x,
    yNorm: fallback.y,
    count: 0,
    source: "default",
    lastAt: 0,
    viewport: state.layout.viewport,
  };
}

function controlPoint(name) {
  const anchor = getControlAnchor(name);
  if (!anchor) return null;
  return {
    anchor,
    point: pointFromAnchor(anchor, state.layout.viewport),
  };
}

function describePointTarget(x, y) {
  const target = document.elementFromPoint(x, y);
  const stack = (document.elementsFromPoint?.(x, y) || []).slice(0, 8);
  return {
    element: target,
    descriptor: target ? buildElementDescriptor(target, 0) : null,
    stackDescriptors: stack.map((item, index) => buildElementDescriptor(item, index)),
  };
}

function probeNamedControl(name) {
  const resolved = controlPoint(name);
  if (!resolved?.point) return null;
  const hit = describePointTarget(resolved.point.x, resolved.point.y);
  const style = hit.element ? window.getComputedStyle(hit.element) : null;
  const bg = parseRgb(style?.backgroundColor || "");
  const text = normalizeText([
    hit.descriptor?.text,
    hit.descriptor?.ariaLabel,
    hit.descriptor?.title,
    hit.descriptor?.dataTitle,
    hit.descriptor?.dataName,
  ].join(" ")).toLowerCase();
  return {
    name,
    anchor: resolved.anchor,
    point: resolved.point,
    target: hit.descriptor,
    stack: hit.stackDescriptors,
    bg,
    text,
  };
}

function isLikelyOpenNewOptionProbe(probe) {
  if (!probe?.target) return false;
  const rect = probe.target.rect || {};
  const rightZone = Number(probe.point?.xNorm || 0) > 0.88;
  const centerZone = Number(probe.point?.yNorm || 0) >= 0.44 && Number(probe.point?.yNorm || 0) <= 0.54;
  const sizeOk = Number(rect.width || 0) >= 48 && Number(rect.height || 0) >= 72;
  const orangeish = probe.bg ? (probe.bg.r >= 180 && probe.bg.g >= 90 && probe.bg.g <= 190 && probe.bg.b <= 140) : false;
  const plusish = /\+|nova opcao|nova opção|new option/.test(probe.text || "");
  const stackText = JSON.stringify(probe.stack || []).toLowerCase();
  return !!(rightZone && centerZone && sizeOk && (orangeish || plusish || /nova opcao|nova opção|new option/.test(stackText)));
}

function isLikelyTradeProbe(probe, side = "call") {
  if (!probe?.target) return false;
  const rect = probe.target.rect || {};
  const rightZone = Number(probe.point?.xNorm || 0) > 0.88;
  const sizeOk = Number(rect.width || 0) >= 48 && Number(rect.height || 0) >= 96;
  const bg = probe.bg || {};
  const isCall = String(side || "").toLowerCase() !== "put";
  const tintOk = isCall
    ? Number(bg.g || 0) > Number(bg.r || 0) + 25
    : Number(bg.r || 0) > Number(bg.g || 0) + 25;
  const textOk = isCall
    ? /(acima|call|higher|up)/.test(probe.text || "")
    : /(abaixo|put|lower|down)/.test(probe.text || "");
  return !!(rightZone && sizeOk && (tintOk || textOk));
}

function detectTradeSurface() {
  const openNewOption = probeNamedControl("open_new_option");
  const tradeCall = probeNamedControl("trade_call");
  const tradePut = probeNamedControl("trade_put");
  return {
    openNewOption: {
      ...openNewOption,
      likely: isLikelyOpenNewOptionProbe(openNewOption),
    },
    tradeCall: {
      ...tradeCall,
      likely: isLikelyTradeProbe(tradeCall, "call"),
    },
    tradePut: {
      ...tradePut,
      likely: isLikelyTradeProbe(tradePut, "put"),
    },
  };
}

function parsePointerClickPoint(payload) {
  const raw = typeof payload === "string"
    ? payload
    : String(payload?.url || payload?.text || payload?.raw || "");
  if (!raw || !/pointer-click/i.test(raw)) return null;
  let decoded = raw;
  try {
    decoded = decodeURIComponent(raw);
  } catch (_) {}
  const match = decoded.match(/pointer-click=.*?:X:(\d+):Y:(\d+)/i);
  if (!match) return null;
  const point = normalizeViewportPoint(Number(match[1]), Number(match[2]), state.layout.viewport);
  if (!point) return null;
  const control = classifyControlAnchor(point);
  state.layout.clicks.push({
    ts: now(),
    x: point.x,
    y: point.y,
    xNorm: point.xNorm,
    yNorm: point.yNorm,
    control,
    source: "pointer-click",
  });
  while (state.layout.clicks.length > 80) state.layout.clicks.shift();
  if (control) {
    rememberLayoutAnchor(control, point, { source: "pointer-click" });
  }
  return { ...point, control };
}

function shouldUseNewOptionFallback() {
  const surface = detectTradeSurface();
  if (surface.openNewOption?.likely) return true;
  if (state.trade.openPositionsCount > 0) return true;
  if (now() - (state.trade.lastTradeUiAt || 0) < 90_000) return true;
  return false;
}

function clickNamedControl(name) {
  const resolved = controlPoint(name);
  if (!resolved?.point) {
    return { ok: false, error: "control_anchor_not_found", control: name };
  }
  const clicked = clickByPoint(resolved.point.x, resolved.point.y);
  return {
    ...clicked,
    control: name,
    anchor: resolved.anchor,
  };
}

function rememberUserBalanceId(value, source = "") {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  if (state.trade.userBalanceId !== numeric) {
    state.trade.userBalanceId = numeric;
    emitDiagnostic(
      "trade.user_balance_id",
      { userBalanceId: numeric, source },
      "info",
      `${numeric}:${source}`,
      "",
      60 * 60 * 1000,
    );
  }
  return numeric;
}

function normalizeTradeDirection(value) {
  const text = String(value || "").toLowerCase();
  if (text === "call") return "call";
  if (text === "put") return "put";
  return "";
}

function amountsClose(left, right) {
  if (!Number.isFinite(left) || !Number.isFinite(right)) return false;
  return Math.abs(Number(left) - Number(right)) <= 0.05;
}

function commissionToProfitPercent(value) {
  const commission = Number(value);
  if (!Number.isFinite(commission)) return null;
  const profitPercent = Math.round(100 - commission);
  return Number.isFinite(profitPercent) ? profitPercent : null;
}

function updatePayoutFromCommissionPayload(payload, source = "socket") {
  const data = typeof payload === "string" ? JSON.parse(payload) : payload;
  const actualCommission = data?.msg?.result?.actual_commission;
  const activeId = Number(actualCommission?.active_id);
  const profitPercent = commissionToProfitPercent(actualCommission?.commission);
  if (!Number.isFinite(activeId) || !Number.isFinite(profitPercent)) return null;
  updateLiveEntry(activeId, { payoutPct: profitPercent });
  state.marketCache[activeId] = {
    ...(state.marketCache[activeId] || {}),
    payoutPct: profitPercent,
    updatedAt: now(),
  };
  if (shouldPromoteFocusedActive(activeId)) {
    state.live.payoutPct = profitPercent;
  }
  emitDiagnostic(
    "trade.payout_adjusted",
    { activeId, profitPercent, source },
    "info",
    `${activeId}:${profitPercent}:${source}`,
    `Payout atualizado para ${profitPercent}% após resposta da IQ`,
    30_000,
  );
  return { activeId, profitPercent };
}

function isTerminalIqResponse(entry) {
  if (!entry) return false;
  if (entry.name === "option") return true;
  if (entry.success === false) return true;
  if (Number.isFinite(entry.status)) return true;
  return false;
}

function iqResponseMessage(entry) {
  return String(entry?.message || entry?.payload?.msg?.message || "").trim();
}

function rememberIqResponseFromSocket(payload) {
  try {
    const data = typeof payload === "string" ? JSON.parse(payload) : payload;
    const requestId = String(data?.request_id || "");
    if (data?.name === "option") {
      updatePayoutFromCommissionPayload(data, "option-result");
    }
    if (!requestId) return;
    pushBounded(state.runtime.iqResponses, {
      ts: now(),
      requestId,
      name: String(data?.name || ""),
      status: Number.isFinite(data?.status) ? Number(data.status) : null,
      success: typeof data?.msg?.success === "boolean" ? data.msg.success : null,
      message: data?.message || data?.msg?.message || "",
      payload: data,
    }, 120);
  } catch (_) {}
}

function recordTradeRuntimeEvent(kind, payload = {}) {
  pushBounded(state.runtime.tradeEvents, {
    ts: now(),
    kind,
    payload,
  }, 160);
}

async function waitForIqRequestResult(requestId, timeoutMs = 2500) {
  const startedAt = now();
  const deadline = startedAt + Math.max(100, Number(timeoutMs) || 0);
  let latest = null;
  while (now() < deadline) {
    const matches = state.runtime.iqResponses.filter(
      (entry) => entry.requestId === requestId && entry.ts >= startedAt,
    );
    if (matches.length) {
      latest = matches[matches.length - 1];
      const terminal = [...matches].reverse().find(isTerminalIqResponse);
      if (terminal) return terminal;
      const accepted = [...matches].reverse().find((entry) => entry.name === "result" && entry.success === true);
      if (accepted && (now() - accepted.ts) > 350) {
        return accepted;
      }
    }
    await sleep(60);
  }
  return latest;
}

async function waitForTradeOpenEvidence({ activeId, direction, amount, baselineOpenCount, startedAt }, timeoutMs = 4500) {
  const deadline = now() + Math.max(200, Number(timeoutMs) || 0);
  const normalizedDirection = normalizeTradeDirection(direction);
  while (now() < deadline) {
    const openedEvent = [...state.runtime.tradeEvents].reverse().find((entry) => {
      if (entry.ts < startedAt) return false;
      if (entry.kind !== "position-changed") return false;
      const payload = entry.payload || {};
      if (String(payload.result || "").toLowerCase() !== "opened") return false;
      if (Number.isFinite(activeId) && Number(payload.activeId) !== Number(activeId)) return false;
      if (normalizedDirection && normalizeTradeDirection(payload.direction) !== normalizedDirection) return false;
      if (Number.isFinite(amount) && !amountsClose(Number(payload.amount), Number(amount))) return false;
      return true;
    });
    if (openedEvent) {
      return {
        ok: true,
        source: "position-changed",
        event: openedEvent,
      };
    }

    const positionStateEvent = [...state.runtime.tradeEvents].reverse().find((entry) => {
      if (entry.ts < startedAt) return false;
      if (entry.kind !== "positions-state") return false;
      const payload = entry.payload || {};
      const positions = Array.isArray(payload.positions) ? payload.positions : [];
      if (!positions.length) return false;
      if (positions.length <= Number(baselineOpenCount || 0)) return false;
      return positions.some((position) => {
        if (Number.isFinite(activeId) && Number(position.activeId) !== Number(activeId)) return false;
        if (normalizedDirection && normalizeTradeDirection(position.direction) !== normalizedDirection) return false;
        if (Number.isFinite(amount) && !amountsClose(Number(position.amount), Number(amount))) return false;
        return true;
      });
    });
    if (positionStateEvent) {
      return {
        ok: true,
        source: "positions-state",
        event: positionStateEvent,
      };
    }

    await sleep(90);
  }
  return null;
}

function inferNextExpiration(activeId, optionTypeId) {
  const liveEntry = state.liveBook[activeId] || {};
  const serverTimeMs = Number(state.live.serverTimeMs || 0);
  const nowSec = Math.floor((Number.isFinite(serverTimeMs) && serverTimeMs > 0 ? serverTimeMs : Date.now()) / 1000);
  const explicit = Number(liveEntry.nextExpiration);
  if (Number.isFinite(explicit) && explicit > nowSec + 5) {
    return explicit;
  }
  const selectedType = String(state.ids.selectedAssetType ?? "").toLowerCase();
  const turboLike = Number(optionTypeId) === 3 || /turbo|binary|binaria/.test(selectedType);
  let target = Math.ceil((nowSec + 1) / 60) * 60;
  if (turboLike && (target - nowSec) < 8) {
    target += 60;
  }
  return target;
}

function buildNativeOpenOptionBody(direction, payload = {}) {
  const template = state.trade.lastOpenOptionTemplate || {};
  const activeId = Number(payload.activeId ?? currentActiveId() ?? template.active_id);
  if (!Number.isFinite(activeId)) return { ok: false, error: "native_missing_active_id" };
  const userBalanceId = Number(payload.userBalanceId ?? state.trade.userBalanceId ?? template.user_balance_id);
  if (!Number.isFinite(userBalanceId)) return { ok: false, error: "native_missing_user_balance_id" };
  const optionTypeId = optionTypeIdFromSelection(payload.optionTypeId ?? state.ids.selectedAssetType ?? template.option_type_id);
  const liveEntry = state.liveBook[activeId] || {};
  const livePrice = Number(payload.currentPrice ?? liveEntry.currentPrice ?? state.current.currentPrice ?? template.value);
  if (!Number.isFinite(livePrice)) return { ok: false, error: "native_missing_live_price" };
  const precision = Number(state.assetMeta[activeId]?.precision ?? guessPricePrecision(livePrice));
  const value = Number(payload.value ?? Math.round(livePrice * (10 ** precision)));
  const rawExpired = Number(payload.expired ?? liveEntry.nextExpiration ?? template.expired);
  const expired = Number.isFinite(rawExpired) && rawExpired > (Math.floor((Number(state.live.serverTimeMs || 0) || Date.now()) / 1000) + 5)
    ? rawExpired
    : inferNextExpiration(activeId, optionTypeId);
  if (!Number.isFinite(expired)) return { ok: false, error: "native_missing_expiration" };
  const price = Number(payload.price ?? payload.amount ?? template.price);
  if (!Number.isFinite(price)) return { ok: false, error: "native_missing_amount" };
  const profitPercent = Number(payload.profitPercent ?? liveEntry.payoutPct ?? state.current.payoutPct ?? template.profit_percent);

  return {
    ok: true,
    body: {
      user_balance_id: userBalanceId,
      active_id: activeId,
      option_type_id: optionTypeId,
      direction,
      expired,
      refund_value: 0,
      price,
      value,
      profit_percent: Number.isFinite(profitPercent) ? Math.round(profitPercent) : 0,
    },
  };
}

function sendBridgeCommand(command, payload = {}, timeoutMs = 1800) {
  const id = `cmd_${now()}_${++state.bridgeCommands.seq}`;
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => {
      delete state.bridgeCommands.pending[id];
      resolve({ ok: false, error: "bridge_command_timeout", id, command });
    }, timeoutMs);
    state.bridgeCommands.pending[id] = { resolve, timer };
    window.postMessage({
      source: BRIDGE_SOURCE,
      kind: "command",
      payload: { id, command, payload },
    }, "*");
  });
}

async function tryNativeTrade(direction, payload = {}) {
  const built = buildNativeOpenOptionBody(direction, payload);
  if (!built?.ok) return { ok: false, method: "native", error: built?.error || "native_unavailable" };
  const requestId = String(Math.floor(now() % 1000000000));
  const startedAt = now();
  const baselineOpenCount = Number(state.trade.openPositionsCount || 0);
  const message = {
    name: "sendMessage",
    request_id: requestId,
    local_time: Math.round(performance.now()),
    msg: {
      name: "binary-options.open-option",
      version: "2.0",
      body: built.body,
    },
  };
  const sent = await sendBridgeCommand("ws-send", { text: JSON.stringify(message) }, 2000);
  if (!sent?.ok) {
    return {
      ...sent,
      method: "native",
      direction,
      request: built.body,
      requestId,
      error: sent?.error || "native_send_failed",
    };
  }

  const socketResult = await waitForIqRequestResult(requestId, 2500);
  const rejectionMessage = iqResponseMessage(socketResult);
  if (socketResult && (
    (socketResult.name === "result" && socketResult.success === false) ||
    (socketResult.name === "option" && Number.isFinite(socketResult.status) && socketResult.status !== 0)
  )) {
    const adjusted = updatePayoutFromCommissionPayload(socketResult.payload, "native-reject");
    const adjustedProfitPercent = Number(adjusted?.profitPercent);
    if (
      socketResult.name === "option" &&
      Number(socketResult.status) === 4117 &&
      Number.isFinite(adjustedProfitPercent) &&
      adjustedProfitPercent > 0 &&
      adjustedProfitPercent !== Number(built.body.profit_percent) &&
      !payload.__retriedProfitChange
    ) {
      return tryNativeTrade(direction, {
        ...payload,
        profitPercent: adjustedProfitPercent,
        __retriedProfitChange: true,
      });
    }
    return {
      ok: false,
      method: "native",
      direction,
      request: built.body,
      requestId,
      sendAck: sent,
      socketResult,
      error: rejectionMessage || "native_request_rejected",
    };
  }

  const tradeEvidence = await waitForTradeOpenEvidence({
    activeId: built.body.active_id,
    direction,
    amount: built.body.price,
    baselineOpenCount,
    startedAt,
  }, 4500);

  if (!tradeEvidence) {
    return {
      ok: false,
      method: "native",
      direction,
      request: built.body,
      requestId,
      sendAck: sent,
      socketResult,
      error: "native_unconfirmed",
    };
  }

  return {
    ok: true,
    method: "native",
    direction,
    request: built.body,
    requestId,
    sendAck: sent,
    socketResult,
    tradeEvidence,
  };
}

async function openNewOptionSurface() {
  const surface = detectTradeSurface();
  if (!surface.openNewOption?.likely && !shouldUseNewOptionFallback()) {
    return { ok: false, skipped: true, reason: "new_option_not_expected", surface };
  }
  const domAttempt = clickByText("nova opcao", false);
  if (domAttempt?.ok) {
    await sleep(140);
    return { ...domAttempt, command: "open_new_option", method: "dom-text", surface };
  }
  if (!surface.openNewOption?.likely) {
    return { ok: false, skipped: true, reason: "new_option_not_visible", surface };
  }
  const fallback = clickNamedControl("open_new_option");
  await sleep(140);
  return {
    ...fallback,
    command: "open_new_option",
    method: fallback?.method || "anchor",
    surface,
  };
}

async function dismissResultOverlay() {
  const buttonTexts = ["fechar", "close", "nova opcao", "nova opção"];
  for (const text of buttonTexts) {
    const clicked = clickByText(text, false);
    if (clicked?.ok) {
      await sleep(100);
      return {
        ...clicked,
        command: "dismiss_result_overlay",
        method: `dom-text:${text}`,
      };
    }
  }
  const surface = detectTradeSurface();
  if (surface.openNewOption?.likely) {
    const clicked = clickNamedControl("open_new_option");
    await sleep(140);
    return {
      ...clicked,
      command: "dismiss_result_overlay",
      method: "anchor:new_option_surface",
      surface,
    };
  }
  return {
    ok: false,
    command: "dismiss_result_overlay",
    method: "not_visible",
    reason: "overlay_not_detected",
    surface,
  };
}

async function ensureTradeSurfaceReady(side = "call") {
  const initialSurface = detectTradeSurface();
  const action = String(side || "").toLowerCase() === "put" ? "put" : "call";
  const targetVisible = action === "put" ? initialSurface.tradePut?.likely : initialSurface.tradeCall?.likely;
  if (targetVisible) {
    return {
      ok: true,
      changed: false,
      reason: "target_visible",
      surfaceBefore: initialSurface,
      surfaceAfter: initialSurface,
    };
  }
  if (initialSurface.openNewOption?.likely) {
    const opened = await openNewOptionSurface();
    await sleep(180);
    const after = detectTradeSurface();
    return {
      ok: !!opened?.ok,
      changed: !!opened?.ok,
      reason: opened?.ok ? "opened_new_option_surface" : opened?.reason || "open_new_option_failed",
      prepare: opened,
      surfaceBefore: initialSurface,
      surfaceAfter: after,
    };
  }
  return {
    ok: false,
    changed: false,
    reason: "surface_plain_or_unknown",
    surfaceBefore: initialSurface,
    surfaceAfter: initialSurface,
  };
}

async function clickTradeControl(side = "call", payload = {}) {
  const action = String(side || "").toLowerCase() === "put" ? "put" : "call";
  const nativeAttempt = await tryNativeTrade(action, payload);
  if (nativeAttempt?.ok) {
    return {
      ...nativeAttempt,
      command: `trade_${action}`,
      side: action,
      transport: "ws-native",
    };
  }
  if (nativeAttempt?.sendAck?.ok || nativeAttempt?.error === "native_unconfirmed" || nativeAttempt?.error === "native_request_rejected") {
    return {
      ...nativeAttempt,
      command: `trade_${action}`,
      side: action,
      transport: "ws-native",
      blockedFallback: true,
    };
  }

  const preparedSurface = await ensureTradeSurfaceReady(action);
  const candidates = collectTradeControlCandidates(action, 12);
  if (candidates.length) {
    const best = candidates[0];
    dispatchClickSequence(best.element);
    return {
      ok: true,
      command: `trade_${action}`,
      method: "candidate",
      side: action,
      nativeAttempt,
      preparedSurface,
      target: best.descriptor,
      score: best.score,
      candidates: candidates.map((item) => ({
        score: item.score,
        descriptor: item.descriptor,
        bg: item.bg,
      })),
    };
  }

  const steps = [];
  if (!preparedSurface?.changed && shouldUseNewOptionFallback()) {
    const prep = await openNewOptionSurface();
    steps.push({ phase: "prepare", result: prep });
  }

  const controlName = action === "call" ? "trade_call" : "trade_put";
  const clicked = clickNamedControl(controlName);
  return {
    ...clicked,
    command: `trade_${action}`,
    method: "anchor",
    side: action,
    steps,
    nativeAttempt,
    preparedSurface,
  };
}

function getIdsSnapshot() {
  return {
    selectedAssetId: state.ids.selectedAssetId,
    selectedAssetType: state.ids.selectedAssetType,
    selectedAssetAt: state.ids.selectedAssetAt,
    quoteActiveId: state.ids.quoteActiveId,
    quoteActiveAt: state.ids.quoteActiveAt,
    liveActiveId: state.live.activeId,
    liveAt: state.live.lastAt,
  };
}

function emitDiagnostic(event, payload = {}, level = "info", dedupeKey = "", message = "", ttlMs = 600) {
  const key = `${event}:${dedupeKey || safePreview(payload, 220)}`;
  const lastAt = state.diagnostics.lastKeys[key] || 0;
  if (now() - lastAt < ttlMs) return;
  state.diagnostics.lastKeys[key] = now();
  chrome.runtime.sendMessage({
    type: "rediq:diagnostic",
    payload: {
      level,
      event,
      asset: resolveAssetLabelFromIds() || state.current.asset || "",
      message,
      payload: {
        ...payload,
        ids: getIdsSnapshot(),
      },
    },
  }).catch(() => {});
}

function getBodyText() {
  const source = document.body || document.documentElement;
  if (!source) return "";
  try {
    const clone = source.cloneNode(true);
    clone.querySelector?.(`#${ROOT_ID}`)?.remove();
    return normalizeText(clone.innerText || clone.textContent || "");
  } catch (_) {
    return normalizeText(source.innerText || source.textContent || "");
  }
}

function isVisibleElement(element) {
  if (!element || element.nodeType !== Node.ELEMENT_NODE) return false;
  const style = window.getComputedStyle(element);
  if (style.visibility === "hidden" || style.display === "none" || style.opacity === "0") {
    return false;
  }
  const rect = element.getBoundingClientRect();
  if (!rect.width && !rect.height) {
    return false;
  }
  return true;
}

function walkRoots(root, callback, visited = new Set()) {
  if (!root || visited.has(root)) return;
  visited.add(root);
  callback(root);
  const elements = root.querySelectorAll?.("*") || [];
  for (const element of elements) {
    if (element.shadowRoot) {
      walkRoots(element.shadowRoot, callback, visited);
    }
  }
}

function pushNodeCandidate(nodes, text, element, source, limit) {
  const normalized = normalizeText(text);
  if (!normalized || normalized.length > 180) return;
  if (!element || !isVisibleElement(element)) return;
  nodes.push({
    text: normalized,
    source,
    rect: element.getBoundingClientRect(),
    elementTag: element.tagName?.toLowerCase?.() || "",
  });
  if (nodes.length > limit) nodes.length = limit;
}

function collectVisibleTextNodes(limit = 2200) {
  const nodes = [];
  const baseRoot = document.body || document.documentElement;
  walkRoots(baseRoot, (root) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (walker.nextNode() && nodes.length < limit) {
      const node = walker.currentNode;
      const parent = node.parentElement;
      if (!parent) continue;
      if (parent.closest?.(`#${ROOT_ID}`)) continue;
      pushNodeCandidate(nodes, node.textContent || "", parent, "text", limit);
    }

    const elements = root.querySelectorAll?.("*") || [];
    for (const element of elements) {
      if (nodes.length >= limit) break;
      if (element.closest?.(`#${ROOT_ID}`)) continue;
      pushNodeCandidate(nodes, element.getAttribute?.("aria-label"), element, "aria-label", limit);
      pushNodeCandidate(nodes, element.getAttribute?.("title"), element, "title", limit);
      pushNodeCandidate(nodes, element.getAttribute?.("data-title"), element, "data-title", limit);
      pushNodeCandidate(nodes, element.getAttribute?.("data-name"), element, "data-name", limit);
      pushNodeCandidate(nodes, element.getAttribute?.("alt"), element, "alt", limit);

      const ownText = normalizeText(element.textContent || "");
      if (ownText && ownText.length <= 80) {
        pushNodeCandidate(nodes, ownText, element, "element-text", limit);
      }
    }
  });
  return nodes;
}

function findLikelyHeaderTexts(textNodes) {
  return textNodes
    .filter((node) => node.rect.top < window.innerHeight * 0.32)
    .sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left)
    .map((item) => item.text);
}

function buildElementText(element) {
  return normalizeText(
    element?.getAttribute?.("aria-label")
    || element?.getAttribute?.("title")
    || element?.getAttribute?.("data-title")
    || element?.getAttribute?.("data-name")
    || element?.innerText
    || element?.textContent
    || ""
  );
}

function isInteractableElement(element) {
  if (!element || !isVisibleElement(element)) return false;
  const tag = String(element.tagName || "").toLowerCase();
  if (["button", "a", "input", "select", "textarea"].includes(tag)) return true;
  const role = String(element.getAttribute?.("role") || "").toLowerCase();
  if (["button", "tab", "link", "menuitem", "option", "switch"].includes(role)) return true;
  if (typeof element.onclick === "function") return true;
  if (element.hasAttribute?.("data-action")) return true;
  if (element.hasAttribute?.("tabindex")) return true;
  const style = window.getComputedStyle(element);
  if (style.cursor === "pointer") return true;
  return false;
}

function buildElementDescriptor(element, index = 0) {
  const rect = element.getBoundingClientRect();
  return {
    index,
    tag: String(element.tagName || "").toLowerCase(),
    text: buildElementText(element),
    role: element.getAttribute?.("role") || "",
    id: element.id || "",
    className: String(element.className || ""),
    dataName: element.getAttribute?.("data-name") || "",
    dataTitle: element.getAttribute?.("data-title") || "",
    ariaLabel: element.getAttribute?.("aria-label") || "",
    title: element.getAttribute?.("title") || "",
    rect: {
      left: Math.round(rect.left),
      top: Math.round(rect.top),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
    },
  };
}

function collectInteractableTargets(limit = 200) {
  const targets = [];
  const baseRoot = document.body || document.documentElement;
  walkRoots(baseRoot, (root) => {
    const elements = root.querySelectorAll?.("*") || [];
    for (const element of elements) {
      if (targets.length >= limit) break;
      if (!isInteractableElement(element)) continue;
      const descriptor = buildElementDescriptor(element, targets.length);
      if (!descriptor.text && !descriptor.ariaLabel && !descriptor.title && !descriptor.dataTitle) continue;
      targets.push({ element, descriptor });
    }
  });
  return targets;
}

function dispatchClickSequence(element, point = null) {
  if (!element) return false;
  const rect = element.getBoundingClientRect();
  const x = Number.isFinite(point?.x) ? Number(point.x) : rect.left + rect.width / 2;
  const y = Number.isFinite(point?.y) ? Number(point.y) : rect.top + rect.height / 2;
  const baseOptions = {
    bubbles: true,
    cancelable: true,
    composed: true,
    clientX: x,
    clientY: y,
    screenX: window.screenX + x,
    screenY: window.screenY + y,
    button: 0,
    buttons: 1,
    pointerId: 1,
    pointerType: "mouse",
    isPrimary: true,
    detail: 1,
  };
  try {
    element.scrollIntoView({ block: "center", inline: "center", behavior: "instant" });
  } catch (_) {}
  try { element.focus?.(); } catch (_) {}
  const pointerTypes = ["pointerover", "pointerenter", "pointermove", "pointerdown", "pointerup"];
  pointerTypes.forEach((type) => {
    try {
      const event = new PointerEvent(type, baseOptions);
      element.dispatchEvent(event);
    } catch (_) {}
  });
  ["mouseover", "mouseenter", "mousemove", "mousedown", "mouseup", "click"].forEach((type) => {
    try {
      const event = new MouseEvent(type, baseOptions);
      element.dispatchEvent(event);
    } catch (_) {}
  });
  try { element.click?.(); } catch (_) {}
  return true;
}

function clickByText(targetText, exact = false) {
  const needle = normalizeText(targetText).toLowerCase();
  if (!needle) return { ok: false, error: "empty_text" };
  const targets = collectInteractableTargets(250);
  const match = targets.find(({ descriptor }) => {
    const hay = normalizeText([
      descriptor.text,
      descriptor.ariaLabel,
      descriptor.title,
      descriptor.dataTitle,
      descriptor.dataName,
    ].join(" ")).toLowerCase();
    return exact ? hay === needle : hay.includes(needle);
  });
  if (!match) return { ok: false, error: "target_not_found", searched: targetText, candidates: targets.slice(0, 20).map((item) => item.descriptor) };
  dispatchClickSequence(match.element);
  return { ok: true, target: match.descriptor };
}

function clickBySelector(selector) {
  const element = document.querySelector(selector);
  if (!element) return { ok: false, error: "selector_not_found", selector };
  const descriptor = buildElementDescriptor(element, 0);
  dispatchClickSequence(element);
  return { ok: true, target: descriptor };
}

function clickByPoint(x, y) {
  const targetX = Number(x);
  const targetY = Number(y);
  if (!Number.isFinite(targetX) || !Number.isFinite(targetY)) {
    return { ok: false, error: "point_invalid", x, y };
  }
  if (targetX < 0 || targetY < 0 || targetX > window.innerWidth || targetY > window.innerHeight) {
    return { ok: false, error: "point_out_of_viewport", x: targetX, y: targetY };
  }
  const element = document.elementFromPoint(targetX, targetY);
  if (!element) return { ok: false, error: "point_not_found", x, y };
  const descriptor = buildElementDescriptor(element, 0);
  const stack = (document.elementsFromPoint?.(targetX, targetY) || [])
    .slice(0, 8)
    .map((item, index) => buildElementDescriptor(item, index));
  dispatchClickSequence(element, { x: targetX, y: targetY });
  return { ok: true, x: targetX, y: targetY, target: descriptor, stack };
}

function probePoints(points = []) {
  const items = Array.isArray(points) ? points : [];
  return items.map((point, index) => {
    const x = Number(point?.x);
    const y = Number(point?.y);
    const element = document.elementFromPoint(x, y);
    const stack = (document.elementsFromPoint?.(x, y) || [])
      .slice(0, 8)
      .map((item, stackIndex) => buildElementDescriptor(item, stackIndex));
    return {
      index,
      x,
      y,
      target: element ? buildElementDescriptor(element, 0) : null,
      stack,
    };
  });
}

function parseRgb(value) {
  const match = String(value || "").match(/rgba?\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
  if (!match) return null;
  return {
    r: Number(match[1]),
    g: Number(match[2]),
    b: Number(match[3]),
  };
}

function collectTradeControlCandidates(side = "call", limit = 30) {
  const isCall = String(side || "").toLowerCase() !== "put";
  const textHints = isCall
    ? ["acima", "call", "up", "higher", "alto"]
    : ["abaixo", "put", "down", "lower", "baixo"];
  const idealY = isCall ? 0.54 : 0.71;
  const idealX = 0.91;
  const candidates = [];
  const baseRoot = document.body || document.documentElement;
  walkRoots(baseRoot, (root) => {
    const elements = root.querySelectorAll?.("*") || [];
    for (const element of elements) {
      if (candidates.length >= limit * 4) break;
      if (!isVisibleElement(element)) continue;
      if (element.id === ROOT_ID || element.closest?.(`#${ROOT_ID}`)) continue;
      const rect = element.getBoundingClientRect();
      if (rect.width < 40 || rect.height < 40) continue;
      if (rect.left < window.innerWidth * 0.62) continue;
      const style = window.getComputedStyle(element);
      const bg = parseRgb(style.backgroundColor);
      const text = buildElementText(element).toLowerCase();
      const textScore = textHints.some((hint) => text.includes(hint)) ? 6 : 0;
      const colorScore = bg
        ? (
            isCall
              ? ((bg.g - ((bg.r + bg.b) / 2)) / 255)
              : ((bg.r - ((bg.g + bg.b) / 2)) / 255)
          )
        : 0;
      const centerX = (rect.left + (rect.width / 2)) / Math.max(window.innerWidth, 1);
      const centerY = (rect.top + (rect.height / 2)) / Math.max(window.innerHeight, 1);
      const positionScore = Math.max(0, 1 - (Math.abs(centerX - idealX) * 2.2) - (Math.abs(centerY - idealY) * 3.2));
      const interactableScore = isInteractableElement(element) ? 1 : 0;
      const areaScore = Math.min((rect.width * rect.height) / 30000, 1.5);
      const score = textScore + (colorScore * 4) + (positionScore * 3) + interactableScore + areaScore;
      if (score < 1.6) continue;
      candidates.push({
        element,
        descriptor: buildElementDescriptor(element, candidates.length),
        score: Number(score.toFixed(3)),
        bg,
        text,
      });
    }
  });
  candidates.sort((a, b) => b.score - a.score);
  return candidates.slice(0, limit);
}

function runEvalScript(source, payload) {
  // Lab-only remote introspection.
  const fn = new Function("payload", source);
  return fn(payload || {});
}

function rememberTick(price, activeId = null) {
  if (!Number.isFinite(price)) return;
  const timestamp = now();
  const store = tickStoreFor(activeId);
  const last = store[store.length - 1];
  if (last && Math.abs(last.price - price) < 1e-8 && timestamp - last.ts < 100) return;
  store.push({ ts: timestamp, price });
  while (store.length > state.config.maxTicks) {
    store.shift();
  }
}

function rememberWsMessage(payload) {
  const text = safePreview(payload, 900);
  if (!text) return;
  if (!/EUR\/|USD\/|GBP\/|JPY\/|OTC|binaria|binary|digital|blitz|price|quote|active|instrument|asset|balance|practice|demo|profit|expiration|countdown|payout/i.test(text)) {
    return;
  }
  state.ws.lastMessageAt = now();
  state.ws.samples.push({ ts: state.ws.lastMessageAt, text });
  while (state.ws.samples.length > 30) {
    state.ws.samples.shift();
  }
}

function rememberNetMessage(payload) {
  const text = safePreview(payload, 1200);
  if (!text) return;
  if (!/EUR\/|USD\/|GBP\/|JPY\/|OTC|binaria|binary|digital|blitz|price|quote|active|instrument|asset|balance|practice|demo|profit|expiration|countdown|payout|option|openets|profile|billing/i.test(text)) {
    return;
  }
  state.net.lastMessageAt = now();
  state.net.samples.push({ ts: state.net.lastMessageAt, text });
  while (state.net.samples.length > 30) {
    state.net.samples.shift();
  }
}

function rememberCanvasText(payload) {
  const text = safePreview(payload, 240);
  if (!text) return;
  if (!/EUR\/|USD\/|GBP\/|JPY\/|OTC|binaria|binary|digital|blitz|price|quote|active|instrument|asset|balance|practice|demo|profit|expiration|countdown|payout|\b\d{1,2}:\d{2}\b|\d+\.\d{3,6}/i.test(text)) {
    return;
  }
  state.canvasText.lastMessageAt = now();
  state.canvasText.samples.push({ ts: state.canvasText.lastMessageAt, text });
  while (state.canvasText.samples.length > 40) {
    state.canvasText.samples.shift();
  }
}

function collectStorageSignals() {
  const results = [];
  const pushIfUseful = (bucket, key, value) => {
    const preview = safePreview(value, 500);
    if (!preview) return;
    if (!/EUR\/|USD\/|GBP\/|JPY\/|OTC|binaria|binary|digital|blitz|practice|demo|asset|instrument|active|price|quote|countdown|expiration|profit|payout/i.test(preview)) {
      return;
    }
    results.push(`${bucket}:${key}=${preview}`);
  };

  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index);
    if (!key) continue;
    pushIfUseful("local", key, localStorage.getItem(key));
  }
  for (let index = 0; index < sessionStorage.length; index += 1) {
    const key = sessionStorage.key(index);
    if (!key) continue;
    pushIfUseful("session", key, sessionStorage.getItem(key));
  }

  state.storage.lastReadAt = now();
  state.storage.samples = results.slice(0, 20).map((text) => ({ ts: state.storage.lastReadAt, text }));
}

function inferPositionDirection(position) {
  const openPrice = Number(position?.open_price);
  const currentPrice = Number(position?.current_price);
  const pnlNet = Number(position?.pnl_net ?? position?.pnl);
  const expectedProfit = Number(position?.expected_profit);
  if (!Number.isFinite(openPrice) || !Number.isFinite(currentPrice) || openPrice === currentPrice) {
    return "";
  }
  const isWinning = (
    (Number.isFinite(expectedProfit) && expectedProfit > 0)
    || (Number.isFinite(pnlNet) && pnlNet > 0)
  );
  if (currentPrice > openPrice) return isWinning ? "call" : "put";
  if (currentPrice < openPrice) return isWinning ? "put" : "call";
  return "";
}

function emitPortfolioTradeDiagnostics(data) {
  const msg = data?.msg || {};
  if (data?.name === "position-changed" && data?.microserviceName === "portfolio") {
    state.trade.lastPortfolioAt = now();
    state.trade.lastTradeUiAt = now();
    const rawEvent = msg?.raw_event?.binary_options_option_changed1 || {};
    rememberUserBalanceId(rawEvent?.balance_id, "portfolio.position-changed");
    const direction = String(rawEvent?.direction || "").toLowerCase() || "";
    const result = String(rawEvent?.result || msg?.close_reason || "").toLowerCase() || "";
    const amount = Number(rawEvent?.amount ?? msg?.invest);
    const profitAmount = Number(rawEvent?.profit_amount ?? msg?.close_profit);
    const activeId = Number(rawEvent?.active_id ?? msg?.active_id);
    const optionId = String(msg?.id || rawEvent?.option_id || msg?.external_id || "");
    const asset = resolveAssetLabelFromId(activeId) || resolveAssetLabelFromIds() || state.current.asset || "";
    recordTradeRuntimeEvent("position-changed", {
      asset,
      activeId,
      optionId,
      status: msg?.status || "",
      direction,
      result,
      amount: Number.isFinite(amount) ? amount : null,
      profitAmount: Number.isFinite(profitAmount) ? profitAmount : null,
      openTime: rawEvent?.open_time ?? msg?.open_time ?? null,
      closeTime: msg?.close_time ?? null,
      expirationTime: rawEvent?.expiration_time ?? null,
      openQuote: Number(rawEvent?.value ?? msg?.open_quote) || null,
      closeQuote: Number(msg?.close_quote) || null,
      pnlNet: Number(msg?.pnl_net) || null,
    });
    emitDiagnostic(
      "trade.position_changed",
      {
        asset,
        activeId,
        optionId,
        status: msg?.status || "",
        direction,
        result,
        amount: Number.isFinite(amount) ? amount : null,
        profitAmount: Number.isFinite(profitAmount) ? profitAmount : null,
        openTime: rawEvent?.open_time ?? msg?.open_time ?? null,
        closeTime: msg?.close_time ?? null,
        expirationTime: rawEvent?.expiration_time ?? null,
        openQuote: Number(rawEvent?.value ?? msg?.open_quote) || null,
        closeQuote: Number(msg?.close_quote) || null,
        pnlNet: Number(msg?.pnl_net) || null,
      },
      "info",
      optionId || `${activeId}:${rawEvent?.open_time ?? msg?.open_time ?? ""}`,
      `${asset || "trade"} ${direction || "?"} ${result || msg?.status || ""}`.trim(),
      60 * 60 * 1000,
    );
    return;
  }

  if (data?.name === "positions-state" && data?.microserviceName === "portfolio") {
    const positions = Array.isArray(msg?.positions) ? msg.positions : [];
    state.trade.openPositionsCount = positions.length;
    state.trade.lastPortfolioAt = now();
    if (positions.length) state.trade.lastTradeUiAt = now();
    const normalizedPositions = positions.map((position) => {
      const activeId = Number(position?.active_id ?? currentActiveId());
      const openPrice = Number(position?.open_price);
      const currentPrice = Number(position?.current_price);
      const amount = Number(position?.margin);
      return {
        optionId: String(position?.id || ""),
        activeId: Number.isFinite(activeId) ? activeId : null,
        direction: inferPositionDirection(position) || "",
        amount: Number.isFinite(amount) ? amount : null,
        openPrice: Number.isFinite(openPrice) ? openPrice : null,
        currentPrice: Number.isFinite(currentPrice) ? currentPrice : null,
        pnlNet: Number(position?.pnl_net ?? position?.pnl) || 0,
      };
    });
    recordTradeRuntimeEvent("positions-state", {
      expiresIn: Number.isFinite(Number(msg?.expires_in)) ? Number(msg.expires_in) : null,
      positions: normalizedPositions,
    });
    const expiresIn = Number(msg?.expires_in);
    positions.forEach((position) => {
      const optionId = String(position?.id || "");
      const amount = Number(position?.margin);
      const activeId = Number(position?.active_id ?? currentActiveId());
      const currentPrice = Number(position?.current_price);
      const openPrice = Number(position?.open_price);
      const direction = inferPositionDirection(position);
      const asset = resolveAssetLabelFromId(activeId) || resolveAssetLabelFromIds() || state.current.asset || "";
      emitDiagnostic(
        "trade.position_open",
        {
          asset,
          activeId,
          optionId,
          instrumentType: position?.instrument_type || "",
          directionHint: direction || "",
          amount: Number.isFinite(amount) ? amount : null,
          openPrice: Number.isFinite(openPrice) ? openPrice : null,
          currentPrice: Number.isFinite(currentPrice) ? currentPrice : null,
          expectedProfit: Number(position?.expected_profit) || 0,
          sellProfit: Number(position?.sell_profit) || 0,
          pnlNet: Number(position?.pnl_net ?? position?.pnl) || 0,
          quoteTimestamp: position?.quote_timestamp ?? null,
          expiresIn: Number.isFinite(expiresIn) ? expiresIn : null,
        },
        "info",
        optionId || `${activeId}:${openPrice}:${amount}`,
        `${asset || "trade"} ${direction || "open"} ${Number.isFinite(amount) ? `$${amount}` : ""}`.trim(),
        20 * 60 * 1000,
      );
    });
  }
}

function rememberTransport(kind, payload) {
  let preview = "";
  let rawText = "";
  let signature = "";
  try {
    if (typeof payload === "string") {
      rawText = safePreview(payload, 12000);
      preview = safePreview(payload, 900);
      try {
        const parsed = JSON.parse(payload);
        signature = [
          parsed.name,
          parsed.microserviceName,
          parsed.msg?.name,
          parsed.event,
          parsed.type,
          parsed.route,
          parsed.request_id,
        ].filter(Boolean).join(" | ");
      } catch (_) {}
    } else {
      rawText = safePreview(payload, 12000);
      preview = safePreview(payload, 900);
      signature = [
        payload?.name,
        payload?.microserviceName,
        payload?.msg?.name,
        payload?.event,
        payload?.type,
        payload?.route,
        payload?.request_id,
      ].filter(Boolean).join(" | ");
    }
  } catch (_) {
    preview = "";
  }

  if (!preview) return;
  state.transport.lastAt = now();
  const sample = {
    ts: state.transport.lastAt,
    kind,
    signature: signature || "",
    text: preview,
    raw: rawText || preview,
  };
  state.transport.samples.push(sample);
  while (state.transport.samples.length > 40) {
    state.transport.samples.shift();
  }

  const pointerPoint = parsePointerClickPoint(payload);
  if (pointerPoint?.control) {
    sample.pointerClick = pointerPoint;
  }

  try {
    const data = typeof payload === "string" ? JSON.parse(payload) : payload;
    const msg = data?.msg || {};
    if (data?.name === "sendMessage" && msg?.name === "binary-options.open-option" && msg?.body) {
      rememberUserBalanceId(msg?.body?.user_balance_id, "sendMessage.open-option");
      state.trade.lastOpenOptionTemplate = {
        ...msg.body,
        capturedAt: now(),
      };
      state.trade.lastTradeUiAt = now();
      sample.nativeOpenOption = {
        activeId: Number(msg?.body?.active_id) || null,
        direction: String(msg?.body?.direction || ""),
        price: Number(msg?.body?.price) || null,
        expired: Number(msg?.body?.expired) || null,
        optionTypeId: Number(msg?.body?.option_type_id) || null,
      };
    }
    const extractedSignals = [];
    if (data?.name === "sendMessage" && msg?.name === "update-user-availability") {
      const id = Number(msg?.body?.selected_asset_id);
      const type = msg?.body?.selected_asset_type ?? null;
      if (updateIdState("selected", id, { type, reason: "update-user-availability" })) {
        extractedSignals.push({ role: "selected", id, type, reason: "update-user-availability" });
      }
    }
    if (data?.name === "sendMessage" && /portfolio\.get-(positions|orders)/.test(String(msg?.name || ""))) {
      rememberUserBalanceId(msg?.body?.user_balance_id, `sendMessage.${msg?.name}`);
    }
    if (data?.name === "sendMessage" && msg?.name === "set-user-settings") {
      const config = msg?.body?.config || {};
      const selectedId = Number(config?.selectedActiveId ?? config?.plotters?.[0]?.activeId);
      const selectedType = config?.selectedActiveType ?? config?.plotters?.[0]?.activeType ?? null;
      if (updateIdState("selected", selectedId, { type: selectedType, reason: "set-user-settings" })) {
        extractedSignals.push({ role: "selected", id: selectedId, type: selectedType, reason: "set-user-settings" });
      }
    }
    if ((data?.name === "subscribeMessage" || data?.name === "unsubscribeMessage") && msg?.name === "candle-generated") {
      const id = Number(msg?.params?.routingFilters?.active_id);
      if (updateIdState("quote", id, { reason: `${data?.name}:candle-generated` })) {
        extractedSignals.push({ role: "quote", id, reason: `${data?.name}:candle-generated` });
      }
    }
    if (data?.name === "sendMessage" && msg?.name === "get-candles") {
      const id = Number(msg?.body?.active_id);
      if (updateIdState("quote", id, { reason: "get-candles" })) {
        extractedSignals.push({ role: "quote", id, reason: "get-candles" });
      }
    }

    const drawingsMatch = String(rawText || preview).match(/drawings-asset-(\d+)/i);
    if (drawingsMatch) {
      const id = Number(drawingsMatch[1]);
      if (updateIdState("selected", id, { reason: "drawings-asset" })) {
        extractedSignals.push({ role: "selected", id, reason: "drawings-asset" });
      }
    }
    harvestAssetMappings(data);
    harvestLiveMarketData(data);
    emitPortfolioTradeDiagnostics(data);
    if (extractedSignals.length) {
      sample.extractedSignals = extractedSignals;
    }
    sample.ids = getIdsSnapshot();
    sample.resolution = resolveActiveContext();
  } catch (_) {}
  return sample;
}

function normalizeAssetLabel(value) {
  const text = normalizeText(value || "").toUpperCase();
  if (!text) return "";
  const isValidPair = (left, right) => VALID_ASSET_CODES.has(left) && VALID_ASSET_CODES.has(right);
  const otcMatch = text.match(/\b([A-Z]{3})\/([A-Z]{3})\s*\(OTC\)\b/);
  if (otcMatch && isValidPair(otcMatch[1], otcMatch[2])) return `${otcMatch[1]}/${otcMatch[2]}-OTC`;
  const otcDash = text.match(/\b([A-Z]{3})\/([A-Z]{3})-OTC\b/);
  if (otcDash && isValidPair(otcDash[1], otcDash[2])) return `${otcDash[1]}/${otcDash[2]}-OTC`;
  const pair = text.match(/\b([A-Z]{3})\/([A-Z]{3})\b/);
  if (pair && isValidPair(pair[1], pair[2])) return `${pair[1]}/${pair[2]}`;
  const compactOtc = text.match(/\b([A-Z]{6})-OTC\b/);
  if (compactOtc) {
    const left = compactOtc[1].slice(0, 3);
    const right = compactOtc[1].slice(3);
    if (isValidPair(left, right)) return `${left}/${right}-OTC`;
  }
  const compact = text.match(/\b([A-Z]{6})\b/);
  if (compact) {
    const left = compact[1].slice(0, 3);
    const right = compact[1].slice(3);
    if (isValidPair(left, right)) return `${left}/${right}`;
  }
  return "";
}

function assetFieldConfidence(source = "") {
  const normalized = String(source || "").toLowerCase();
  if (normalized.includes("seed")) return 100;
  if (normalized.includes("display_name") || normalized.includes("active_name")) return 92;
  if (normalized.includes("underlying") || normalized.includes("ticker")) return 88;
  if (normalized.includes("asset")) return 82;
  if (normalized.includes("instrument")) return 78;
  if (normalized.includes("symbol")) return 65;
  if (normalized.includes("name")) return 58;
  return 50;
}

function inferOtcForActive(activeId, preferredMarket = "") {
  if (!Number.isFinite(activeId)) return false;
  const preferred = String(preferredMarket || "").toLowerCase();
  if (preferred.includes("otc")) return true;

  const liveMarket = String(state.liveBook[activeId]?.marketType || "").toLowerCase();
  if (liveMarket.includes("otc")) return true;

  const cachedMarket = String(state.marketCache[activeId]?.marketType || "").toLowerCase();
  if (cachedMarket.includes("otc")) return true;

  const rawLabel = String(state.assetMap[activeId] || "");
  if (hasOtcSuffix(rawLabel)) return true;

  const meta = state.assetMeta[activeId] || {};
  if (meta.otcHint) return true;

  return false;
}

function buildAssetLabel(activeId, preferredMarket = "") {
  if (!Number.isFinite(activeId)) return "";
  const raw = String(state.assetMap[activeId] || "");
  const base = stripOtcSuffix(raw);
  if (!base) return `active#${activeId}`;
  return inferOtcForActive(activeId, preferredMarket) ? `${base}-OTC` : base;
}

function selectionCutoffForActive(activeId) {
  if (Number.isFinite(state.ids.selectedAssetId) && Number(state.ids.selectedAssetId) === Number(activeId)) {
    return Number(state.ids.selectedAssetAt) || 0;
  }
  return 0;
}

function isFieldFreshForSelection(activeId, fieldAt) {
  if (!Number.isFinite(activeId)) return false;
  if (!Number.isFinite(fieldAt)) return false;
  const cutoff = selectionCutoffForActive(activeId);
  if (!cutoff) return true;
  return fieldAt >= (cutoff - 250);
}

function registerAssetMapping(activeId, value, meta = {}) {
  if (!Number.isFinite(activeId)) return;
  const normalized = normalizeAssetLabel(value);
  if (!normalized) return;
  const base = stripOtcSuffix(normalized);
  const previousRaw = String(state.assetMap[activeId] || "");
  const previousBase = stripOtcSuffix(previousRaw);
  const previousMeta = state.assetMeta[activeId] || {};
  const confidence = Number.isFinite(meta.confidence)
    ? meta.confidence
    : assetFieldConfidence(meta.source || "");
  const otcHint = hasOtcSuffix(normalized) || !!previousMeta.otcHint;

  if (
    previousBase &&
    previousBase !== base &&
    confidence < ((previousMeta.confidence || 0) + 10)
  ) {
    emitDiagnostic("asset.map.reject", {
      activeId,
      previous: previousBase,
      next: base,
      previousConfidence: previousMeta.confidence || 0,
      nextConfidence: confidence,
      source: meta.source || "",
    }, "info", `asset.map.reject:${activeId}:${previousBase}:${base}`);
    return;
  }

  state.assetMap[activeId] = base;
  state.assetMeta[activeId] = {
    base,
    lastLabel: normalized,
    confidence: Math.max(confidence, previousMeta.confidence || 0),
    source: meta.source || previousMeta.source || "",
    otcHint,
    updatedAt: now(),
  };

  if (previousBase !== base || previousRaw !== normalized) {
    emitDiagnostic("asset.map", {
      activeId,
      previous: previousRaw || "",
      next: normalized,
      confidence,
      source: meta.source || "",
    }, "info", `asset.map:${activeId}:${normalized}:${meta.source || ""}`);
  }
}

function registerAssetPrecision(activeId, precision, source = "") {
  if (!Number.isFinite(activeId) || !Number.isFinite(precision)) return;
  const meta = state.assetMeta[activeId] || {};
  state.assetMeta[activeId] = {
    ...meta,
    precision: Number(precision),
    updatedAt: now(),
    source: source || meta.source || "",
  };
}

function visitStructured(value, visitor, seen = new Set()) {
  if (!value || typeof value !== "object" || seen.has(value)) return;
  seen.add(value);
  visitor(value);
  if (Array.isArray(value)) {
    value.forEach((item) => visitStructured(item, visitor, seen));
    return;
  }
  Object.values(value).forEach((item) => visitStructured(item, visitor, seen));
}

function harvestAssetMappings(data) {
  visitStructured(data, (node) => {
    const activeId = Number(node?.active_id ?? node?.asset_id ?? node?.id);
    if (!Number.isFinite(activeId)) return;
    if (Number.isFinite(node?.precision)) {
      registerAssetPrecision(activeId, node.precision, "structured:precision");
    }
    [
      ["symbol", node?.symbol],
      ["name", node?.name],
      ["asset", node?.asset],
      ["active_name", node?.active_name],
      ["display_name", node?.display_name],
      ["underlying", node?.underlying],
      ["ticker", node?.ticker],
      ["instrument", node?.instrument],
    ].forEach(([field, candidate]) => registerAssetMapping(activeId, candidate, { source: `structured:${field}` }));
  });
}

function ensureLiveEntry(activeId) {
  if (!Number.isFinite(activeId)) return null;
  if (!state.liveBook[activeId]) {
    state.liveBook[activeId] = {
      activeId,
      currentPrice: null,
      priceSource: "",
      priceAt: 0,
      payoutPct: null,
      payoutAt: 0,
      marketType: "",
      marketTypeAt: 0,
      countdownLabel: "",
      countdownSeconds: null,
      countdownAt: 0,
      nextExpiration: null,
      instrumentType: "",
      suspendedHint: false,
      suspendedAt: 0,
      lastAt: 0,
      updatedAt: 0,
    };
  }
  return state.liveBook[activeId];
}

function updateLiveEntry(activeId, patch = {}) {
  const entry = ensureLiveEntry(activeId);
  if (!entry) return null;
  const stamp = now();
  if (Object.prototype.hasOwnProperty.call(patch, "currentPrice")) entry.priceAt = stamp;
  if (Object.prototype.hasOwnProperty.call(patch, "payoutPct")) entry.payoutAt = stamp;
  if (Object.prototype.hasOwnProperty.call(patch, "marketType")) entry.marketTypeAt = stamp;
  if (
    Object.prototype.hasOwnProperty.call(patch, "countdownLabel") ||
    Object.prototype.hasOwnProperty.call(patch, "countdownSeconds")
  ) entry.countdownAt = stamp;
  if (Object.prototype.hasOwnProperty.call(patch, "suspendedHint")) entry.suspendedAt = stamp;
  Object.assign(entry, patch);
  entry.updatedAt = stamp;
  return entry;
}

function shouldPromoteFocusedActive(activeId) {
  if (!Number.isFinite(activeId)) return false;
  const selected = state.ids.selectedAssetId;
  const quoted = state.ids.quoteActiveId;
  if (!Number.isFinite(selected) && !Number.isFinite(quoted)) return true;
  if (Number.isFinite(selected) && activeId === selected) return true;
  if (Number.isFinite(quoted) && activeId === quoted) return true;
  return false;
}

function tickStoreFor(activeId) {
  const key = Number.isFinite(activeId) ? String(activeId) : "_global";
  if (!state.ticksByActiveId[key]) {
    state.ticksByActiveId[key] = [];
  }
  return state.ticksByActiveId[key];
}

function setLivePrice(activeId, price, source) {
  if (!Number.isFinite(price)) return;
  if (Number.isFinite(activeId)) {
    updateLiveEntry(activeId, {
      currentPrice: price,
      priceSource: source || "",
      lastAt: now(),
    });
  }
  if (Number.isFinite(activeId) && shouldPromoteFocusedActive(activeId)) {
    state.live.activeId = activeId;
    state.live.currentPrice = price;
    state.live.priceSource = source || state.live.priceSource;
    state.live.lastAt = now();
  }
  rememberTick(price, activeId);
}

function harvestLiveMarketData(data) {
  const msg = data?.msg || {};
  if (data?.name === "client-buyback-generated") {
    const activeId = Number(msg?.asset_id ?? msg?.active_id);
    if (Number.isFinite(activeId)) {
      updateLiveEntry(activeId, {
        nextExpiration: Number(msg?.expiration) || null,
        instrumentType: String(msg?.instrument_type || ""),
      });
    }
    return;
  }

  if (data?.name === "candle-generated") {
    const activeId = Number(msg?.active_id);
    const price = [msg?.close, msg?.ask, msg?.bid, msg?.open].find((value) => Number.isFinite(value));
    setLivePrice(activeId, price, "ws:candle-generated");
    return;
  }

  if (data?.name === "candles-generated") {
    visitStructured(msg, (node) => {
      const activeId = Number(node?.active_id ?? node?.asset_id);
      const price = [node?.close, node?.ask, node?.bid, node?.open, node?.value].find((value) => Number.isFinite(value));
      if (Number.isFinite(activeId) && Number.isFinite(price)) {
        setLivePrice(activeId, price, "ws:candles-generated");
      }
      if (Number.isFinite(node?.spot_profit) && Number.isFinite(activeId)) {
        updateLiveEntry(activeId, { payoutPct: node.spot_profit });
      }
    });
    return;
  }

  if (data?.name === "candles" && Array.isArray(msg?.candles) && msg.candles.length) {
    const activeId = Number(msg?.active_id ?? state.ids.quoteActiveId ?? state.ids.selectedAssetId);
    const candle = msg.candles[msg.candles.length - 1];
    const price = [candle?.close, candle?.ask, candle?.bid, candle?.open].find((value) => Number.isFinite(value));
    if (Number.isFinite(activeId) && Number.isFinite(price)) {
      setLivePrice(activeId, price, "ws:candles");
    }
    return;
  }

  if (data?.name === "top-assets-updated" && Array.isArray(msg?.data)) {
    for (const item of msg.data) {
      const activeId = Number(item?.active_id);
      if (!Number.isFinite(activeId)) continue;
      state.marketCache[activeId] = {
        payoutPct: Number.isFinite(item?.spot_profit) ? item.spot_profit : null,
        marketType: typeof msg?.instrument_type === "string" ? msg.instrument_type : "",
        currentPrice: Number.isFinite(item?.cur_price) ? item.cur_price : null,
        tradersMood: Number.isFinite(item?.traders_mood) ? item.traders_mood : null,
        updatedAt: now(),
      };
      updateLiveEntry(activeId, {
        payoutPct: Number.isFinite(item?.spot_profit) ? item.spot_profit : null,
        marketType: typeof msg?.instrument_type === "string" ? msg.instrument_type : "",
      });
    }
    const targetId = state.ids.selectedAssetId ?? state.ids.quoteActiveId;
    const preferred = msg.data.find((item) => Number(item?.active_id) === Number(targetId)) || msg.data[0];
    if (preferred) {
      const activeId = Number(preferred?.active_id);
      const price = [preferred?.cur_price, preferred?.close, preferred?.price].find((value) => Number.isFinite(value));
      setLivePrice(activeId, price, "ws:top-assets-updated");
      if (Number.isFinite(preferred?.spot_profit) && shouldPromoteFocusedActive(activeId)) {
        state.live.payoutPct = preferred.spot_profit;
      }
      if (typeof msg?.instrument_type === "string" && shouldPromoteFocusedActive(activeId)) {
        state.live.marketType = msg.instrument_type;
      }
    }
    return;
  }

  if (data?.name === "timeSync" && Number.isFinite(msg)) {
    state.live.serverTimeMs = Number(msg);
    state.live.lastAt = now();
    return;
  }

  if (data?.url && typeof data.text === "string") {
    try {
      const parsed = JSON.parse(data.text);
      harvestAssetMappings(parsed);
      visitStructured(parsed, (node) => {
        const activeId = Number(node?.active_id ?? node?.asset_id);
        const price = [
          node?.cur_price,
          node?.price,
          node?.close,
          node?.ask,
          node?.bid,
        ].find((value) => Number.isFinite(value));
        if (Number.isFinite(activeId) && Number.isFinite(price)) {
          setLivePrice(activeId, price, `net:${data.url}`);
        }
        if (Number.isFinite(node?.spot_profit)) {
          if (Number.isFinite(activeId)) {
            updateLiveEntry(activeId, { payoutPct: node.spot_profit });
            if (shouldPromoteFocusedActive(activeId)) {
              state.live.payoutPct = node.spot_profit;
            }
          }
        }
      });
    } catch (_) {}
  }
}

function currentActiveId() {
  return resolveActiveContext().activeId;
}

function resolveActiveContext() {
  const candidates = [
    {
      id: state.ids.selectedAssetId,
      at: state.ids.selectedAssetAt || 0,
      source: "selected",
      priority: 300,
    },
    {
      id: state.ids.quoteActiveId,
      at: state.ids.quoteActiveAt || 0,
      source: "quote",
      priority: 200,
    },
    {
      id: state.live.activeId,
      at: state.live.lastAt || 0,
      source: "live",
      priority: 100,
    },
  ].filter((item) => Number.isFinite(item.id));

  if (!candidates.length) {
    return { activeId: null, source: "", at: 0, candidates: [] };
  }
  candidates.sort((a, b) => b.priority - a.priority || b.at - a.at);
  const picked = candidates[0];
  return {
    activeId: picked.id,
    source: picked.source,
    at: picked.at,
    candidates,
  };
}

function resolveAssetLabelFromIds() {
  const activeId = currentActiveId();
  if (!Number.isFinite(activeId)) return "";
  return buildAssetLabel(activeId);
}

function updateIdState(role, activeId, extra = {}) {
  if (!Number.isFinite(activeId)) return false;
  const ts = now();
  let changed = false;
  if (role === "selected") {
    if (state.ids.selectedAssetId !== activeId || state.ids.selectedAssetType !== (extra.type ?? state.ids.selectedAssetType)) {
      changed = true;
    }
    state.ids.selectedAssetId = activeId;
    if (extra.type != null) state.ids.selectedAssetType = extra.type;
    state.ids.selectedAssetAt = ts;
  } else if (role === "quote") {
    if (state.ids.quoteActiveId !== activeId) changed = true;
    state.ids.quoteActiveId = activeId;
    state.ids.quoteActiveAt = ts;
  }
  if (changed) {
    emitDiagnostic("id.change", {
      role,
      activeId,
      asset: state.assetMap[activeId] || "",
      reason: extra.reason || "",
      selectedAssetType: state.ids.selectedAssetType,
    }, "info", `id.change:${role}:${activeId}:${extra.reason || ""}`);
  }
  return changed;
}

function findMainCanvas() {
  const canvases = Array.from(document.querySelectorAll("canvas"))
    .filter((canvas) => !canvas.closest(`#${ROOT_ID}`))
    .filter((canvas) => {
      const rect = canvas.getBoundingClientRect();
      return rect.width >= 180 && rect.height >= 180;
    });

  const scored = canvases.map((canvas) => {
    const rect = canvas.getBoundingClientRect();
    const label = `${canvas.id || ""} ${canvas.className || ""}`.toLowerCase();
    let score = rect.width * rect.height;
    if (label.includes("glcanvas")) score += 500000;
    if (label.includes("topleft")) score += 200000;
    if (label.includes("svelte")) score += 50000;
    return {
      canvas,
      rect,
      score,
      id: canvas.id || "",
      className: String(canvas.className || ""),
    };
  });

  scored.sort((a, b) => b.score - a.score);
  return scored[0] || null;
}

async function maybeSendCanvasFrame() {
  const minInterval = Math.max(1200, Number(state.config.frameMinIntervalMs) || 2500);
  if (now() - state.canvasCapture.lastSentAt < minInterval) return;

  const main = findMainCanvas();
  state.canvasCapture.lastCanvasMeta = main
    ? {
        id: main.id,
        className: main.className,
        width: Math.round(main.rect.width),
        height: Math.round(main.rect.height),
      }
    : null;

  if (!main?.canvas) return;

  try {
    const dataUrl = main.canvas.toDataURL("image/jpeg", 0.55);
    if (!dataUrl || dataUrl.length < 1500) return;
    state.canvasCapture.lastSentAt = now();
    state.canvasCapture.lastError = "";
    await chrome.runtime.sendMessage({
      type: "rediq:frame",
      payload: {
        asset: state.current.asset,
        marketType: state.current.marketType,
        mode: state.current.mode,
        payoutPct: state.current.payoutPct,
        countdown: state.current.countdown,
        canvas: state.canvasCapture.lastCanvasMeta,
        imageDataUrl: dataUrl,
      },
    }).catch(() => {});
  } catch (error) {
    state.canvasCapture.lastError = String(error);
  }
}

function loadOverlayState() {
  try {
    const rawPos = localStorage.getItem(POS_KEY);
    if (rawPos) {
      const parsed = JSON.parse(rawPos);
      if (Number.isFinite(parsed.left) && Number.isFinite(parsed.top)) {
        state.overlay.left = parsed.left;
        state.overlay.top = parsed.top;
      }
    }
  } catch (_) {}

  try {
    state.overlay.minimized = localStorage.getItem(MIN_KEY) === "1";
  } catch (_) {
    state.overlay.minimized = false;
  }
}

function saveOverlayPosition() {
  try {
    localStorage.setItem(POS_KEY, JSON.stringify({
      left: state.overlay.left,
      top: state.overlay.top,
    }));
  } catch (_) {}
}

function saveOverlayMinimized() {
  try {
    localStorage.setItem(MIN_KEY, state.overlay.minimized ? "1" : "0");
  } catch (_) {}
}

function applyOverlayPosition(root) {
  if (!root) return;
  if (Number.isFinite(state.overlay.left) && Number.isFinite(state.overlay.top)) {
    root.style.left = `${Math.round(state.overlay.left)}px`;
    root.style.top = `${Math.round(state.overlay.top)}px`;
    root.style.right = "auto";
  }
}

function clampOverlayPosition(root) {
  if (!root) return;
  const rect = root.getBoundingClientRect();
  const maxLeft = Math.max(0, window.innerWidth - rect.width - 8);
  const maxTop = Math.max(0, window.innerHeight - rect.height - 8);
  state.overlay.left = clamp(Number.isFinite(state.overlay.left) ? state.overlay.left : rect.left, 8, maxLeft);
  state.overlay.top = clamp(Number.isFinite(state.overlay.top) ? state.overlay.top : rect.top, 8, maxTop);
  applyOverlayPosition(root);
}

function toggleMinimized() {
  state.overlay.minimized = !state.overlay.minimized;
  saveOverlayMinimized();
  render();
}

function bindOverlayInteractions(root) {
  if (!root || root.dataset.bound === "1") return;
  root.dataset.bound = "1";

  const handle = root.querySelector("[data-role='drag-handle']");
  const toggle = root.querySelector("[data-role='toggle-min']");

  toggle?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    toggleMinimized();
  });

  handle?.addEventListener("pointerdown", (event) => {
    if (event.target?.closest("[data-role='toggle-min']")) return;
    const rect = root.getBoundingClientRect();
    state.overlay.dragging = true;
    state.overlay.offsetX = event.clientX - rect.left;
    state.overlay.offsetY = event.clientY - rect.top;
    handle.setPointerCapture?.(event.pointerId);
    root.dataset.dragging = "1";
    event.preventDefault();
  });

  window.addEventListener("pointermove", (event) => {
    if (!state.overlay.dragging) return;
    state.overlay.left = event.clientX - state.overlay.offsetX;
    state.overlay.top = event.clientY - state.overlay.offsetY;
    clampOverlayPosition(root);
  });

  const stopDragging = () => {
    if (!state.overlay.dragging) return;
    state.overlay.dragging = false;
    root.dataset.dragging = "0";
    saveOverlayPosition();
  };

  window.addEventListener("pointerup", stopDragging);
  window.addEventListener("blur", stopDragging);
  window.addEventListener("resize", () => clampOverlayPosition(root));
}

function handleWindowMessage(event) {
  if (event.source !== window) return;
  const data = event.data;
  if (!data || data.source !== BRIDGE_SOURCE) return;

  if (data.kind === "ws-command-result") {
    const id = String(data.payload?.id || "");
    const pending = state.bridgeCommands.pending[id];
    if (pending) {
      window.clearTimeout(pending.timer);
      delete state.bridgeCommands.pending[id];
      pending.resolve({
        ok: !!data.payload?.ok,
        id,
        command: data.payload?.command || "",
        result: data.payload?.result || {},
        error: data.payload?.error || "",
      });
    }
    return;
  }

  if (data.kind === "ws-open") {
    state.ws.lastUrl = String(data.payload?.url || "");
    const sample = rememberTransport("ws-open", data.payload);
    pushTransportLog(sample);
    return;
  }
  if (data.kind === "canvas-text") {
    rememberCanvasText(data.payload);
    return;
  }
  if (data.kind === "ws-send") {
    const sample = rememberTransport("ws-send", data.payload);
    pushTransportLog(sample);
    return;
  }
  if (data.kind === "ws-message") {
    const sample = rememberTransport("ws-message", data.payload);
    rememberIqResponseFromSocket(data.payload);
    rememberWsMessage(data.payload);
    pushTransportLog(sample);
    return;
  }
  if (data.kind === "fetch" || data.kind === "xhr" || data.kind === "probe") {
    const sample = rememberTransport(data.kind, data.payload);
    rememberNetMessage(data.payload);
    pushTransportLog(sample);
  }
}

function pushTransportLog(sample) {
  if (!sample) return;
  chrome.runtime.sendMessage({
    type: "rediq:transport",
    payload: {
      ...sample,
      asset: state.current.asset,
      ids: {
        selectedAssetId: state.ids.selectedAssetId,
        selectedAssetType: state.ids.selectedAssetType,
        selectedAssetAt: state.ids.selectedAssetAt,
        quoteActiveId: state.ids.quoteActiveId,
        quoteActiveAt: state.ids.quoteActiveAt,
        liveActiveId: state.live.activeId,
        liveAt: state.live.lastAt,
      },
    },
  }).catch(() => {});
}

function buildRawSnapshot(textNodes, bodyText) {
  const activeId = currentActiveId();
  updateViewportState();
  return {
    ts: now(),
    title: document.title,
    href: location.href,
    viewport: state.layout.viewport,
    current: {
      ...state.current,
      activeId,
    },
    ids: {
      selectedAssetId: state.ids.selectedAssetId,
      selectedAssetType: state.ids.selectedAssetType,
      selectedAssetAt: state.ids.selectedAssetAt,
      quoteActiveId: state.ids.quoteActiveId,
      quoteActiveAt: state.ids.quoteActiveAt,
      liveActiveId: state.live.activeId,
      liveAt: state.live.lastAt,
    },
    live: { ...state.live },
    assetMap: state.assetMap,
    assetMeta: state.assetMeta,
    marketCache: state.marketCache,
    layout: {
      anchors: state.layout.anchors,
      clicks: state.layout.clicks.slice(-30),
    },
    trade: state.trade,
    sampleTexts: textNodes.slice(0, 80).map((item) => item.text),
    headerTexts: findLikelyHeaderTexts(textNodes).slice(0, 30),
    bodySnippet: bodyText.slice(0, 3000),
    wsSamples: state.ws.samples.slice(-30),
    netSamples: state.net.samples.slice(-30),
    storageSamples: state.storage.samples.slice(-30),
    transportSamples: state.transport.samples.slice(-40),
    ticks: state.ticks.slice(-120),
  };
}

function maybeSendRawSnapshot(textNodes, bodyText) {
  const activeId = currentActiveId();
  const key = JSON.stringify({
    activeId,
    asset: state.current.asset,
    marketType: state.current.marketType,
    payoutPct: state.current.payoutPct,
    currentPrice: state.current.currentPrice,
  });
  const intervalMs = Math.max(1000, Number(state.config.rawSnapshotIntervalMs) || 2500);
  const due = (now() - state.raw.lastSnapshotSentAt) >= intervalMs;
  const changed = key !== state.raw.lastSnapshotKey;
  if (!due && !changed) return;

  state.raw.lastSnapshotSentAt = now();
  state.raw.lastSnapshotKey = key;
  chrome.runtime.sendMessage({
    type: "rediq:raw-snapshot",
    payload: buildRawSnapshot(textNodes, bodyText),
  }).catch(() => {});
}

function ticksInWindow(ms) {
  const cutoff = now() - ms;
  return state.ticks.filter((tick) => tick.ts >= cutoff);
}

function computePulse() {
  const recent = ticksInWindow(5000);
  if (recent.length < 2) {
    return { slope: 0, volatility: 0, impulse: "frio", direction: "flat" };
  }
  const first = recent[0].price;
  const last = recent[recent.length - 1].price;
  const slope = last - first;
  const diffs = [];
  for (let index = 1; index < recent.length; index += 1) {
    diffs.push(Math.abs(recent[index].price - recent[index - 1].price));
  }
  const volatility = average(diffs) || 0;
  const direction = slope > 0 ? "up" : slope < 0 ? "down" : "flat";
  let impulse = "frio";
  if (Math.abs(slope) > volatility * 8) impulse = "forte";
  else if (Math.abs(slope) > volatility * 3) impulse = "medio";
  else if (Math.abs(slope) > volatility * 1.5) impulse = "leve";
  return { slope, volatility, impulse, direction };
}

function getAllSignalTexts(textNodes, bodyText) {
  return [
    ...textNodes.map((node) => node.text),
    ...findLikelyHeaderTexts(textNodes),
    bodyText,
    document.title || "",
    ...state.canvasText.samples.map((item) => item.text),
    ...state.ws.samples.map((item) => item.text),
    ...state.net.samples.map((item) => item.text),
    ...state.storage.samples.map((item) => item.text),
  ];
}

function detectMode(bodyText) {
  const lower = bodyText.toLowerCase();
  const networkText = state.net.samples.map((sample) => sample.text.toLowerCase()).join(" ");
  const wsText = state.ws.samples.map((sample) => sample.text.toLowerCase()).join(" ");
  if (/\bpractice\b|\bdemo\b/.test(lower) || /\bpractice\b|\bdemo\b/.test(networkText) || /\bpractice\b|\bdemo\b/.test(wsText)) {
    return "demo";
  }
  if (/\breal\b|\bconta real\b/.test(lower) || /\breal\b/.test(networkText)) {
    return "real";
  }
  return "unknown";
}

function detectAsset(textNodes, bodyText) {
  const activeId = currentActiveId();
  if (Number.isFinite(activeId)) {
    return buildAssetLabel(activeId);
  }

  const sources = getAllSignalTexts(textNodes, bodyText);
  const patterns = [
    /\b[A-Z]{3}\/[A-Z]{3}\s*\(OTC\)\b/,
    /\b[A-Z]{3}\/[A-Z]{3}-OTC\b/,
    /\b[A-Z]{3}\/[A-Z]{3}\b/,
  ];

  for (const source of sources) {
    for (const pattern of patterns) {
      const match = String(source).match(pattern);
      if (!match) continue;
      return match[0].replace(/\s+\(OTC\)/, "-OTC");
    }
  }
  return "-";
}

function detectMarketType(textNodes, bodyText, asset) {
  const activeId = currentActiveId();
  if (Number.isFinite(activeId) && state.liveBook[activeId]?.marketType && isFieldFreshForSelection(activeId, state.liveBook[activeId]?.marketTypeAt)) {
    const market = String(state.liveBook[activeId].marketType).toLowerCase();
    if (market.includes("blitz")) return "Blitz";
    if (market.includes("digital")) return "Digital";
    if (market.includes("binary") || market.includes("turbo")) return "Binaria";
  }
  if (Number.isFinite(activeId) && state.marketCache[activeId]?.marketType && isFieldFreshForSelection(activeId, state.marketCache[activeId]?.updatedAt)) {
    const market = String(state.marketCache[activeId].marketType).toLowerCase();
    if (market.includes("blitz")) return "Blitz";
    if (market.includes("digital")) return "Digital";
    if (market.includes("binary") || market.includes("turbo")) return "Binaria";
  }
  const selectedType = String(state.ids.selectedAssetType ?? "").toLowerCase();
  if (selectedType) {
    if (selectedType.includes("blitz")) return "Blitz";
    if (selectedType.includes("digital")) return "Digital";
    if (selectedType.includes("binary") || selectedType.includes("turbo") || selectedType === "3" || selectedType === "1") {
      return "Binaria";
    }
  }
  if (!Number.isFinite(activeId) && state.live.marketType) {
    const market = String(state.live.marketType).toLowerCase();
    if (market.includes("blitz")) return "Blitz";
    if (market.includes("digital")) return "Digital";
    if (market.includes("binary") || market.includes("turbo")) return "Binaria";
  }
  const sources = getAllSignalTexts(textNodes, bodyText).map((item) => String(item).toLowerCase());
  for (const text of sources) {
    if (/\bbinaria\b|\bbinarias\b|\bbinary\b/.test(text)) return "Binaria";
    if (/\bdigital\b/.test(text)) return "Digital";
    if (/\bblitz\b/.test(text)) return "Blitz";
  }
  if (asset.includes("-OTC")) return "Binaria";
  return "-";
}

function detectPayout(textNodes, bodyText) {
  const activeId = currentActiveId();
  if (Number.isFinite(activeId) && Number.isFinite(state.liveBook[activeId]?.payoutPct)) {
    return state.liveBook[activeId].payoutPct;
  }
  if (Number.isFinite(activeId) && Number.isFinite(state.marketCache[activeId]?.payoutPct)) {
    return state.marketCache[activeId].payoutPct;
  }
  if (!Number.isFinite(activeId) && Number.isFinite(state.live.payoutPct)) {
    return state.live.payoutPct;
  }
  const values = [];
  const source = getAllSignalTexts(textNodes, bodyText).join(" ");
  for (const match of source.matchAll(/([+]?)\b(\d{1,3})%/g)) {
    const value = Number(match[2]);
    if (value >= 20 && value <= 95) values.push(value);
  }
  return values.length ? Math.max(...values) : null;
}

function detectCountdown(textNodes, bodyText) {
  const activeId = currentActiveId();
  if (Number.isFinite(activeId) && state.liveBook[activeId]?.countdownLabel && Number.isFinite(state.liveBook[activeId]?.countdownSeconds)) {
    return {
      label: state.liveBook[activeId].countdownLabel,
      totalSeconds: state.liveBook[activeId].countdownSeconds,
    };
  }
  if (!Number.isFinite(activeId) && state.live.countdownLabel && Number.isFinite(state.live.countdownSeconds)) {
    return { label: state.live.countdownLabel, totalSeconds: state.live.countdownSeconds };
  }
  const values = [];
  const source = getAllSignalTexts(textNodes, bodyText).join(" ");
  for (const match of source.matchAll(/\b(\d{1,2}:\d{2})\b/g)) {
    const [mm, ss] = match[1].split(":").map(Number);
    const total = (mm * 60) + ss;
    if (total <= 900) {
      values.push({ label: match[1], total });
    }
  }
  if (!values.length) return { label: "-", totalSeconds: null };
  values.sort((a, b) => a.total - b.total);
  return { label: values[0].label, totalSeconds: values[0].total };
}

function detectSuspendedHint(textNodes, bodyText) {
  const source = getAllSignalTexts(textNodes, bodyText).join(" ").toLowerCase();
  if (state.live.suspendedHint === true) return true;
  if (Number.isFinite(state.live.currentPrice) && state.live.lastAt && now() - state.live.lastAt < 2500) {
    return false;
  }
  return /active is suspended|mercado fechado|suspend|closed|disabled|not available|temporarily unavailable|asset is suspended/.test(source);
}

function pickLikelyPriceCandidate(textNodes) {
  const candidates = [];
  for (const node of textNodes) {
    if (!/\d+\.\d{3,6}\b/.test(node.text)) continue;
    const value = toNumber(node.text);
    if (value == null || value <= 0) continue;
    const rightBias = clamp(node.rect.left / Math.max(window.innerWidth, 1), 0, 1);
    const verticalBias = 1 - clamp(node.rect.top / Math.max(window.innerHeight, 1), 0, 1);
    const centerPenalty = Math.abs((node.rect.left + node.rect.width / 2) - window.innerWidth * 0.72) / Math.max(window.innerWidth, 1);
    const score = (rightBias * 0.5) + (verticalBias * 0.15) + ((1 - centerPenalty) * 0.35);
    candidates.push({ value, score, rect: node.rect, text: node.text, source: node.source });
  }
  candidates.sort((a, b) => b.score - a.score);
  return candidates[0] || null;
}

function buildEntryHint(snapshot) {
  if (state.config.demoOnly && snapshot.mode === "real") return "Bloqueado: conta real detectada";
  if (snapshot.suspendedHint) return "Mercado com pista de suspensao ou fechamento";
  if (!Number.isFinite(snapshot.currentPrice)) return "Preco ainda nao estabilizado";
  if (!snapshot.buyWindowOpen) return "Fora da janela de compra ou countdown indefinido";
  const pulse = computePulse();
  if (pulse.impulse === "forte") {
    return pulse.direction === "up"
      ? "Impulso forte de alta; cuidado com entrada tardia"
      : "Impulso forte de baixa; cuidado com entrada tardia";
  }
  if (pulse.impulse === "medio") {
    return pulse.direction === "up" ? "Fluxo de alta em andamento" : "Fluxo de baixa em andamento";
  }
  return "Mercado neutro ou respirando; boa hora para observar";
}

function ensureUi() {
  if (state.uiReady) return;
  if (document.getElementById(ROOT_ID)) {
    state.uiReady = true;
    return;
  }
  const root = document.createElement("div");
  root.id = ROOT_ID;
  root.innerHTML = `
    <div class="rediq-panel">
      <div class="rediq-header" data-role="drag-handle">
        <div class="rediq-title-wrap">
          <div class="rediq-title">RED IQ Demo Vision</div>
          <div class="rediq-version">v${EXT_VERSION}</div>
        </div>
        <div class="rediq-header-actions">
          <button class="rediq-icon-btn" data-role="toggle-min" title="Minimizar">-</button>
          <div class="rediq-badge" data-role="mode">--</div>
        </div>
      </div>
      <div class="rediq-body" data-role="panel-body">
      <div class="rediq-grid">
        <div class="rediq-cell"><span class="rediq-label">Ativo</span><strong data-role="asset">-</strong></div>
        <div class="rediq-cell"><span class="rediq-label">Mercado</span><strong data-role="market">-</strong></div>
        <div class="rediq-cell"><span class="rediq-label">Preco</span><strong data-role="price">-</strong></div>
        <div class="rediq-cell"><span class="rediq-label">Payout</span><strong data-role="payout">-</strong></div>
        <div class="rediq-cell"><span class="rediq-label">Countdown</span><strong data-role="countdown">-</strong></div>
        <div class="rediq-cell"><span class="rediq-label">Tick age</span><strong data-role="tick-age">-</strong></div>
      </div>
      <canvas class="rediq-sparkline" width="320" height="76" data-role="sparkline"></canvas>
      <div class="rediq-pulse">
        <div><span class="rediq-label">Direcao curta</span><strong data-role="direction">-</strong></div>
        <div><span class="rediq-label">Impulso</span><strong data-role="impulse">-</strong></div>
        <div><span class="rediq-label">Volatilidade</span><strong data-role="volatility">-</strong></div>
      </div>
      <div class="rediq-entry" data-role="entry-hint">Aguardando leitura inicial</div>
      <ul class="rediq-notes" data-role="notes"></ul>
      </div>
    </div>
  `;
  (document.documentElement || document.body).appendChild(root);
  applyOverlayPosition(root);
  clampOverlayPosition(root);
  bindOverlayInteractions(root);
  state.uiReady = true;
}

function renderSparkline(canvas, ticks) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "rgba(255, 82, 82, 0.08)";
  ctx.fillRect(0, 0, width, height);
  if (ticks.length < 2) {
    ctx.strokeStyle = "rgba(255,255,255,0.15)";
    ctx.beginPath();
    ctx.moveTo(0, height / 2);
    ctx.lineTo(width, height / 2);
    ctx.stroke();
    return;
  }
  const prices = ticks.map((tick) => tick.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = Math.max(max - min, 1e-8);

  ctx.beginPath();
  ticks.forEach((tick, index) => {
    const x = (index / (ticks.length - 1)) * width;
    const y = height - (((tick.price - min) / range) * (height - 10) + 5);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "#ff6236";
  ctx.lineWidth = 2;
  ctx.stroke();

  const last = ticks[ticks.length - 1];
  const lx = width - 3;
  const ly = height - (((last.price - min) / range) * (height - 10) + 5);
  ctx.beginPath();
  ctx.arc(lx, ly, 3, 0, Math.PI * 2);
  ctx.fillStyle = "#6dff9b";
  ctx.fill();
}

function render() {
  ensureUi();
  const root = document.getElementById(ROOT_ID);
  if (!root) return;
  const pulse = computePulse();
  const current = state.current;
  const panelBody = root.querySelector("[data-role='panel-body']");
  const toggleBtn = root.querySelector("[data-role='toggle-min']");
  root.querySelector("[data-role='mode']").textContent = current.mode === "demo" ? "DEMO" : current.mode.toUpperCase();
  root.querySelector("[data-role='mode']").dataset.mode = current.mode;
  if (panelBody) panelBody.hidden = state.overlay.minimized;
  if (toggleBtn) toggleBtn.textContent = state.overlay.minimized ? "+" : "-";
  root.querySelector("[data-role='asset']").textContent = current.asset || "-";
  root.querySelector("[data-role='market']").textContent = current.marketType || "-";
  root.querySelector("[data-role='price']").textContent = Number.isFinite(current.currentPrice) ? current.currentPrice.toFixed(6) : "-";
  root.querySelector("[data-role='payout']").textContent = current.payoutPct != null ? `${current.payoutPct}%` : "-";
  root.querySelector("[data-role='countdown']").textContent = current.countdown || "-";
  root.querySelector("[data-role='tick-age']").textContent = current.tickAgeMs != null ? `${Math.round(current.tickAgeMs)}ms` : "-";
  root.querySelector("[data-role='direction']").textContent = pulse.direction;
  root.querySelector("[data-role='impulse']").textContent = pulse.impulse;
  root.querySelector("[data-role='volatility']").textContent = pulse.volatility ? pulse.volatility.toFixed(6) : "-";
  root.querySelector("[data-role='entry-hint']").textContent = current.entryHint;
  root.querySelector("[data-role='entry-hint']").dataset.state = current.demoAllowed ? "ok" : "warn";

  const notes = root.querySelector("[data-role='notes']");
  notes.innerHTML = "";
  for (const note of current.notes) {
    const item = document.createElement("li");
    item.textContent = note;
    notes.appendChild(item);
  }

  renderSparkline(root.querySelector("[data-role='sparkline']"), state.ticks.slice(-120));
}

function snapshotState() {
  updateViewportState();
  collectStorageSignals();
  const textNodes = collectVisibleTextNodes();
  const bodyText = getBodyText();
  const resolution = resolveActiveContext();
  const resolvedActiveId = resolution.activeId;
  const mode = detectMode(bodyText);
  const asset = detectAsset(textNodes, bodyText);
  const marketType = detectMarketType(textNodes, bodyText, asset);
  const payoutPct = detectPayout(textNodes, bodyText);
  const countdown = detectCountdown(textNodes, bodyText);
  const priceCandidate = pickLikelyPriceCandidate(textNodes);
  const activeLive = Number.isFinite(resolvedActiveId) ? state.liveBook[resolvedActiveId] : null;
  const livePrice =
    Number.isFinite(activeLive?.currentPrice) &&
    activeLive?.lastAt &&
    (now() - activeLive.lastAt) < 4000
      ? activeLive.currentPrice
      : Number.isFinite(state.live.currentPrice) &&
        state.live.lastAt &&
        (now() - state.live.lastAt) < 4000 &&
        (!Number.isFinite(resolvedActiveId) || resolvedActiveId === state.live.activeId)
          ? state.live.currentPrice
      : null;
  const price = priceCandidate?.value ?? livePrice ?? null;

  if (Number.isFinite(resolvedActiveId)) {
    state.ticks = tickStoreFor(resolvedActiveId).slice(-state.config.maxTicks);
  }
  const currentTick = state.ticks[state.ticks.length - 1] || null;
  const tickAgeMs = currentTick ? now() - currentTick.ts : null;
  const suspendedHint = detectSuspendedHint(textNodes, bodyText);
  const buyWindowOpen = countdown.totalSeconds != null ? countdown.totalSeconds > 0 : !suspendedHint;
  const pulse = computePulse();

  const notes = [];
  if (asset === "-") notes.push("Ativo ainda nao reconhecido no DOM ou no fluxo da pagina.");
  if (String(asset).startsWith("active#")) notes.push("Ativo resolvido so por ID; falta mapear o simbolo humano.");
  if (marketType === "-") notes.push("Mercado ainda nao reconhecido; preciso capturar mais contexto.");
  if (price == null) notes.push("Preco nao identificado em texto ou mensagens uteis.");
  if (state.canvasText.samples.length) notes.push("Canvas da pagina esta entregando texto util; bom sinal para leitura fina.");
  if (!state.ws.samples.length) notes.push("Ainda nao capturei mensagens uteis do websocket da pagina.");
  if (state.transport.samples.length) notes.push("Tap de transporte ativo; capturando o caminho real dos dados.");
  if (!state.net.samples.length) notes.push("Ainda nao capturei respostas uteis de fetch/xhr da pagina.");
  if (tickAgeMs != null && tickAgeMs > 1200) notes.push("Leitura de preco ficou velha demais para microtiming.");
  if (pulse.impulse === "forte") notes.push("Movimento acelerado: risco de entrada tardia.");
  if (suspendedHint) notes.push("A interface esta dando pista de mercado suspenso ou fechado.");
  if (
    Number.isFinite(resolvedActiveId)
    && Number.isFinite(state.live.activeId)
    && resolvedActiveId !== state.live.activeId
  ) {
    notes.push(`Fluxo paralelo detectado: foco ${resolvedActiveId}, ultimo tick global ${state.live.activeId}.`);
  }
  if (!notes.length) notes.push("Leitura estavel. Bom momento para observar a ponta do grafico.");

  state.current = {
    mode,
    demoAllowed: !state.config.demoOnly || mode === "demo",
    asset,
    marketType,
    payoutPct,
    countdown: countdown.label,
    currentPrice: price,
    tickAgeMs,
    buyWindowOpen,
    suspendedHint,
    entryHint: buildEntryHint({ mode, currentPrice: price, suspendedHint, buyWindowOpen }),
    notes,
    updatedAt: now(),
    debug: {
      textNodeCount: textNodes.length,
      sampleTexts: textNodes.slice(0, 18).map((item) => item.text),
      bodySnippet: bodyText.slice(0, 600),
      priceCandidate: priceCandidate ? { text: priceCandidate.text, value: priceCandidate.value, source: priceCandidate.source } : null,
      livePrice: Number.isFinite(state.live.currentPrice)
        ? {
            value: state.live.currentPrice,
            source: state.live.priceSource,
            activeId: state.live.activeId,
            ageMs: state.live.lastAt ? now() - state.live.lastAt : null,
          }
        : null,
      canvasLastMessageAgeMs: state.canvasText.lastMessageAt ? now() - state.canvasText.lastMessageAt : null,
      canvasSamples: state.canvasText.samples.slice(-8),
      wsLastUrl: state.ws.lastUrl || "",
      wsLastMessageAgeMs: state.ws.lastMessageAt ? now() - state.ws.lastMessageAt : null,
      wsSamples: state.ws.samples.slice(-5),
      netLastMessageAgeMs: state.net.lastMessageAt ? now() - state.net.lastMessageAt : null,
      netSamples: state.net.samples.slice(-5),
      storageLastReadAt: state.storage.lastReadAt || null,
      storageSamples: state.storage.samples.slice(-8),
      transportLastAt: state.transport.lastAt || null,
      transportSamples: state.transport.samples.slice(-10),
      ids: {
        ...getIdsSnapshot(),
      },
      resolution,
      assetMap: Object.entries(state.assetMap).slice(0, 24),
      assetMeta: Object.entries(state.assetMeta).slice(0, 24),
      marketCache: Object.entries(state.marketCache).slice(0, 24),
      liveBook: Object.entries(state.liveBook).slice(0, 24),
      layout: {
        viewport: state.layout.viewport,
        anchors: state.layout.anchors,
        clicks: state.layout.clicks.slice(-20),
      },
      trade: state.trade,
      canvasCapture: {
        lastSentAt: state.canvasCapture.lastSentAt || null,
        lastError: state.canvasCapture.lastError || "",
        lastCanvasMeta: state.canvasCapture.lastCanvasMeta,
      },
    },
  };

  const resolutionKey = JSON.stringify({
    selected: state.ids.selectedAssetId,
    quote: state.ids.quoteActiveId,
    live: state.live.activeId,
    resolved: resolvedActiveId,
    asset,
    marketType,
    payoutPct,
  });
  if (resolutionKey !== state.diagnostics.lastResolutionKey) {
    state.diagnostics.lastResolutionKey = resolutionKey;
    emitDiagnostic("state.resolution", {
      resolution,
      asset,
      marketType,
      payoutPct,
      livePrice: state.current?.debug?.livePrice || null,
    }, "info", resolutionKey);
  }

  maybeSendRawSnapshot(textNodes, bodyText);
}

async function pushState() {
  if (now() - state.lastSentAt < state.config.sendIntervalMs) return;
  state.lastSentAt = now();
  await chrome.runtime.sendMessage({
    type: "rediq:state",
    payload: {
      ...state.current,
      pulse: computePulse(),
      ticks: state.ticks.slice(-60),
      pageTitle: document.title,
      href: location.href,
      domFreshnessMs: now() - state.lastDomMutationAt,
    },
  }).catch(() => {});
}

async function loadConfig() {
  try {
    const response = await chrome.runtime.sendMessage({ type: "rediq:get-config" });
    if (response?.ok && response.config) {
      state.config = { ...DEFAULT_CONFIG, ...response.config };
    }
  } catch (_) {
    state.config = { ...DEFAULT_CONFIG };
  }
}

function loop() {
  if (!state.config.enabled) return;
  snapshotState();
  render();
  pushState();
  maybeSendCanvasFrame();
}

function startLoop() {
  if (state.started) return;
  state.started = true;
  state.lastDomMutationAt = now();

  ensureUi();
  loop();
  state.intervalId = window.setInterval(loop, Math.max(120, Number(state.config.sampleIntervalMs) || 250));

  const target = document.documentElement || document.body;
  if (target) {
    const observer = new MutationObserver(() => {
      state.lastDomMutationAt = now();
    });
    observer.observe(target, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
    });
  }
}

async function boot() {
  await loadConfig();
  loadOverlayState();
  window.addEventListener("message", handleWindowMessage);
  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === "rediq:ping") {
      sendResponse({
        ok: true,
        version: EXT_VERSION,
        href: location.href,
        title: document.title,
        asset: state.current.asset,
        ids: getIdsSnapshot(),
      });
      return false;
    }
    if (message?.type !== "rediq:command") return false;
    (async () => {
      snapshotState();
      const textNodes = collectVisibleTextNodes();
      const bodyText = getBodyText();
      const command = message.command || "unknown";
      const result = {
        ok: true,
        command,
        current: state.current,
        ids: getIdsSnapshot(),
        live: state.live,
        liveBook: state.liveBook,
        resolution: resolveActiveContext(),
        assetMap: state.assetMap,
        assetMeta: state.assetMeta,
        marketCache: state.marketCache,
        layout: {
          viewport: state.layout.viewport,
          anchors: state.layout.anchors,
          clicks: state.layout.clicks.slice(-20),
        },
        trade: state.trade,
      };

      if (command === "dump_dom") {
        result.sampleTexts = textNodes.slice(0, 120).map((item) => item.text);
        result.headerTexts = findLikelyHeaderTexts(textNodes).slice(0, 60);
        result.bodySnippet = bodyText.slice(0, 5000);
      } else if (command === "list_targets") {
        result.targets = collectInteractableTargets(200).map((item) => item.descriptor);
      } else if (command === "click_text" || command === "switch_asset") {
        const targetText = message.payload?.text || message.payload?.asset || "";
        Object.assign(result, clickByText(targetText, !!message.payload?.exact));
      } else if (command === "click_selector") {
        Object.assign(result, clickBySelector(message.payload?.selector || ""));
      } else if (command === "click_point") {
        Object.assign(result, clickByPoint(message.payload?.x, message.payload?.y));
      } else if (command === "click_control") {
        Object.assign(result, clickNamedControl(String(message.payload?.control || "")));
      } else if (command === "probe_points") {
        result.points = probePoints(message.payload?.points || []);
      } else if (command === "scan_trade_controls") {
        result.surface = detectTradeSurface();
        result.callCandidates = collectTradeControlCandidates("call", 12).map((item) => ({
          score: item.score,
          descriptor: item.descriptor,
          bg: item.bg,
        }));
        result.putCandidates = collectTradeControlCandidates("put", 12).map((item) => ({
          score: item.score,
          descriptor: item.descriptor,
          bg: item.bg,
        }));
        result.controlAnchors = Object.fromEntries(
          Object.keys(DEFAULT_CONTROL_ANCHORS).map((name) => [name, getControlAnchor(name)])
        );
      } else if (command === "open_new_option") {
        Object.assign(result, await openNewOptionSurface());
      } else if (command === "dismiss_result_overlay") {
        Object.assign(result, await dismissResultOverlay());
      } else if (command === "trade_call") {
        Object.assign(result, await clickTradeControl("call", message.payload || {}));
      } else if (command === "trade_put") {
        Object.assign(result, await clickTradeControl("put", message.payload || {}));
      } else if (command === "amount_plus" || command === "amount_minus" || command === "expiry_plus" || command === "expiry_minus") {
        Object.assign(result, clickNamedControl(command));
      } else if (command === "eval_js") {
        result.evalResult = runEvalScript(String(message.payload?.source || message.payload?.script || ""), message.payload?.payload || {});
      } else if (command === "dump_transport") {
        result.transportSamples = state.transport.samples.slice(-80);
        result.wsSamples = state.ws.samples.slice(-60);
        result.netSamples = state.net.samples.slice(-60);
      } else if (command === "dump_resolution") {
        result.resolution = resolveActiveContext();
        result.liveBook = state.liveBook;
        result.ticksByActiveId = state.ticksByActiveId;
        result.assetMeta = state.assetMeta;
      } else if (command === "dump_catalog") {
        result.assetMap = state.assetMap;
        result.assetMeta = state.assetMeta;
        result.marketCache = state.marketCache;
        result.liveBook = state.liveBook;
      } else {
        Object.assign(result, buildRawSnapshot(textNodes, bodyText));
      }

      sendResponse(result);
    })().catch((error) => {
      sendResponse({ ok: false, error: String(error) });
    });
    return true;
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startLoop, { once: true });
  } else {
    startLoop();
  }
}

boot().catch(console.error);
