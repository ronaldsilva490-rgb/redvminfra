// ══════════════════════════════════════════════════
// STATE — Singletons globais (Maps, Sets, constantes)
// ══════════════════════════════════════════════════
require("dotenv").config();
const EventEmitter = require("events");
const { createClient } = require("@supabase/supabase-js");

// ── Supabase ──
const supabase = createClient(
  process.env.SUPABASE_URL || "",
  process.env.SUPABASE_SERVICE_KEY || process.env.SUPABASE_KEY || "",
);

// ── Event bus compartilhado ──
const eventEmitter = new EventEmitter();

// ── Constantes ──
const ADMIN_TENANT_ID = process.env.ADMIN_TENANT_ID || "admin";
const VERSION = "5.0.24";
const CHANGELOG =
  "Release 5.0.12: Correção de bugs na extensão Perplexity (prompts duplicados, mensagens antigas e status typing) e sincronização de versão em toda a stack.";

// ── Defaults de configuração ──
const DEFAULT_BUFFER_SIZE = 6;
const DEFAULT_PROACTIVE_COOLDOWN = 15000;
const DEFAULT_REALTIME_COOLDOWN = 8000;
const DEFAULT_ACTIVITY_WINDOW_MS = 120000;
const DEFAULT_ACTIVE_THRESH = 4;

// ── Streaming ──
const STREAM_PRESENCE_REFRESH_MS = 4000;
const STREAM_PRESENCE_IDLE_MS = 18000;
const STREAM_STATE_RETENTION_MS = 120000;

// ── Context ──
const SESSION_CONTEXT_TTL_MS = 2 * 60 * 60 * 1000; // 2 horas
const CONTEXT_BUFFER_MAX_MSGS = 20;
const CONTEXT_BUFFER_TTL_MS = 4 * 60 * 60 * 1000; // 4h

// ── Dedup ──
const PROCESSED_MSG_TTL = 5 * 60 * 1000; // 5 minutos

// ── Bot response TTL ──
const LAST_BOT_RESPONSE_TTL = 3 * 60 * 1000; // 3 minutos

// ══════════════════════════════════════════════════
// MAPS E SETS GLOBAIS
// ══════════════════════════════════════════════════
const sessions = new Map();
const conversationBuffers = new Map();
const waSessionDispatchState = new Map();
const sessionContextSent = new Map();
const activeRedRequests = new Set();
const lastProactiveTime = new Map();
const lastRealtimeAnalysis = new Map();
const groupActivityWindow = new Map();
const activeStatusMessages = new Map();
const lastBotResponseByJid = new Map();
const processedMessageIds = new Map();
const jidProcessingState = new Map();
const realtimeInProgress = new Set();
const contextBuffer = new Map();
const realtimeStreamState = new Map();

// ══════════════════════════════════════════════════
// UTILITÁRIOS PUROS
// ══════════════════════════════════════════════════

function normalize(t) {
  return t
    ? t
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
    : "";
}

/** Lê config dinâmica com fallback pro default — null-safe */
function getCfg(configs, key, defaultVal) {
  try {
    if (!configs) return defaultVal;
    const val = configs?.proactive?.[key] ?? configs?.[key];
    if (val === undefined || val === null || val === "") return defaultVal;
    const n = parseFloat(val);
    return isNaN(n) ? defaultVal : n;
  } catch (_) {
    return defaultVal;
  }
}

function trackGroupActivity(key, configs = {}) {
  const now = Date.now();
  if (!groupActivityWindow.has(key)) groupActivityWindow.set(key, []);
  const times = groupActivityWindow.get(key);
  const window = getCfg(
    configs,
    "activity_window_ms",
    DEFAULT_ACTIVITY_WINDOW_MS,
  );
  const thresh = getCfg(configs, "active_group_thresh", DEFAULT_ACTIVE_THRESH);
  times.push(now);
  const cutoff = now - window;
  while (times.length && times[0] < cutoff) times.shift();
  return times.length >= thresh;
}

function isRecentMessage(msg) {
  const ts = (msg.messageTimestamp || 0) * 1000;
  return Date.now() - ts < 90000;
}

function streamStateKey(tenantId, remoteJid) {
  return `${tenantId || "default"}::${remoteJid || "unknown"}`;
}

async function humanDelay(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ══════════════════════════════════════════════════
// LIMPEZAS PERIÓDICAS
// ══════════════════════════════════════════════════

// Dedup: limpeza a cada hora
setInterval(
  () => {
    const now = Date.now();
    let removed = 0;
    for (const [key, ts] of processedMessageIds) {
      if (now - ts > PROCESSED_MSG_TTL) {
        processedMessageIds.delete(key);
        removed++;
      }
    }
    if (removed > 0)
      console.log(`[DEDUP] 🧹 ${removed} IDs expirados removidos`);
  },
  60 * 60 * 1000,
);

// SessionContext: limpeza a cada 30 min
setInterval(
  () => {
    const now = Date.now();
    let removed = 0;
    for (const [key, val] of sessionContextSent) {
      const sentAt = typeof val === "object" ? val.sentAt : 0;
      if (now - sentAt > SESSION_CONTEXT_TTL_MS) {
        sessionContextSent.delete(key);
        removed++;
      }
    }
    if (removed > 0)
      console.log(
        `[CTX-CLEAN] 🧹 Removidas ${removed} entradas de contexto expiradas`,
      );
  },
  30 * 60 * 1000,
);

// ContextBuffer: limpeza a cada hora
setInterval(
  () => {
    const now = Date.now();
    let removed = 0;
    for (const [key, val] of contextBuffer) {
      if (now - (val.updatedAt || 0) > CONTEXT_BUFFER_TTL_MS) {
        contextBuffer.delete(key);
        removed++;
      }
    }
    if (removed > 0)
      console.log(`[CTX-BUFFER] 🧹 ${removed} entradas expiradas removidas`);
  },
  60 * 60 * 1000,
);

// ── Error handlers ──
process.on("uncaughtException", (err) =>
  console.error("❌ UncaughtException:", err?.message),
);
process.on("unhandledRejection", (r) =>
  console.error("❌ UnhandledRejection:", r?.message || r),
);

module.exports = {
  supabase,
  eventEmitter,
  ADMIN_TENANT_ID,
  VERSION,
  CHANGELOG,
  DEFAULT_BUFFER_SIZE,
  DEFAULT_PROACTIVE_COOLDOWN,
  DEFAULT_REALTIME_COOLDOWN,
  DEFAULT_ACTIVITY_WINDOW_MS,
  DEFAULT_ACTIVE_THRESH,
  STREAM_PRESENCE_REFRESH_MS,
  STREAM_PRESENCE_IDLE_MS,
  STREAM_STATE_RETENTION_MS,
  SESSION_CONTEXT_TTL_MS,
  CONTEXT_BUFFER_MAX_MSGS,
  CONTEXT_BUFFER_TTL_MS,
  PROCESSED_MSG_TTL,
  LAST_BOT_RESPONSE_TTL,
  sessions,
  conversationBuffers,
  waSessionDispatchState,
  sessionContextSent,
  activeRedRequests,
  lastProactiveTime,
  lastRealtimeAnalysis,
  groupActivityWindow,
  activeStatusMessages,
  lastBotResponseByJid,
  processedMessageIds,
  jidProcessingState,
  realtimeInProgress,
  contextBuffer,
  realtimeStreamState,
  normalize,
  getCfg,
  trackGroupActivity,
  isRecentMessage,
  streamStateKey,
  humanDelay,
};
