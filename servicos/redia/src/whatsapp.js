const fs = require("fs");
const pino = require("pino");
const QRCode = require("qrcode");
const activity = require("./activity");
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  Browsers,
} = require("@whiskeysockets/baileys");
const { authPath } = require("./paths");
const { setupMessageHandler } = require("./messageHandler");
const { sendImage, sendText } = require("./sender");

const runtime = {
  status: "stopped",
  qr: "",
  phone: "",
  last_error: "",
  started_at: "",
  reconnect_attempts: 0,
  reconnect_scheduled_at: "",
  last_disconnect_code: 0,
  last_update_at: "",
  hint: "",
};

let sock = null;
let connecting = false;
let reconnectTimer = null;
const ignoredOutbound = new Map();

function outboundKey(chatId, id) {
  return `${chatId}:${id}`;
}

function rememberIgnoredOutbound(sent) {
  const rows = Array.isArray(sent) ? sent : [sent];
  const expiresAt = Date.now() + 10 * 60 * 1000;
  for (const item of rows) {
    const chatId = item?.key?.remoteJid;
    const id = item?.key?.id;
    if (chatId && id) ignoredOutbound.set(outboundKey(chatId, id), expiresAt);
  }
}

function shouldIgnoreOutbound(chatId, id) {
  const now = Date.now();
  for (const [key, expiresAt] of ignoredOutbound.entries()) {
    if (expiresAt <= now) ignoredOutbound.delete(key);
  }
  const key = outboundKey(chatId, id);
  if (!ignoredOutbound.has(key)) return false;
  ignoredOutbound.delete(key);
  return true;
}

function getRuntime() {
  return { ...runtime };
}

function touchRuntime(patch = {}) {
  Object.assign(runtime, patch, { last_update_at: new Date().toISOString() });
  return getRuntime();
}

function clearReconnectTimer() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
}

function disconnectLabel(code, message = "") {
  const map = {
    [DisconnectReason.loggedOut]: "Sessao desconectada do WhatsApp",
    [DisconnectReason.badSession]: "Sessao invalida",
    [DisconnectReason.connectionClosed]: "Conexao fechada",
    [DisconnectReason.connectionLost]: "Conexao perdida",
    [DisconnectReason.connectionReplaced]: "Sessao substituida por outro login",
    [DisconnectReason.restartRequired]: "Reconexao necessaria",
    [DisconnectReason.timedOut]: "Tempo de conexao esgotado",
    [DisconnectReason.multideviceMismatch]: "Sessao multidevice invalida",
    [DisconnectReason.forbidden]: "WhatsApp recusou a sessao",
    [DisconnectReason.unavailableService]: "Servico do WhatsApp indisponivel",
  };
  return map[code] || message || "Falha de conexao";
}

function authDirFromConfig(config) {
  return authPath(config?.whatsapp?.auth_dir || "");
}

function clearAuthDir(config) {
  const dir = authDirFromConfig(config);
  if (fs.existsSync(dir)) fs.rmSync(dir, { recursive: true, force: true });
}

function scheduleReconnect(config, { delayMs = 2500, resetAuth = false, reason = "" } = {}) {
  clearReconnectTimer();
  const when = new Date(Date.now() + delayMs).toISOString();
  touchRuntime({
    reconnect_attempts: Number(runtime.reconnect_attempts || 0) + 1,
    reconnect_scheduled_at: when,
    hint: resetAuth
      ? "Sessao antiga foi descartada; aguardando novo QR."
      : "Tentando reconectar automaticamente.",
  });
  activity.publish("whatsapp:reconnecting", {
    delay_ms: delayMs,
    reconnect_attempts: runtime.reconnect_attempts,
    reset_auth: resetAuth,
    reason,
  });
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    startWhatsApp(config, { resetAuth, source: "auto-reconnect" }).catch((err) => {
      touchRuntime({ status: "error", last_error: err.message, hint: "Falha ao reconectar automaticamente." });
      activity.publish("whatsapp:restart_error", { error: err.message, source: "auto-reconnect" });
    });
  }, delayMs);
}

async function sendImageToChat(chatId, image, caption = "") {
  if (!sock || runtime.status !== "authenticated") throw new Error("WhatsApp nao esta autenticado");
  return sendImage(sock, chatId, image, caption);
}

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

async function resolveChatId(input) {
  const raw = String(input || "").trim();
  if (!raw) throw new Error("Destino WhatsApp vazio");
  if (raw.includes("@")) return raw;
  const digits = raw.replace(/\D/g, "");
  if (!digits) throw new Error("Destino WhatsApp invalido");
  const candidates = [];
  if (digits.startsWith("55")) candidates.push(`${digits}@s.whatsapp.net`);
  if (!digits.startsWith("55")) candidates.push(`55${digits}@s.whatsapp.net`);
  if (!digits.startsWith("55") && digits.length === 10) {
    candidates.push(`55${digits.slice(0, 2)}9${digits.slice(2)}@s.whatsapp.net`);
  }
  try {
    const checks = await sock.onWhatsApp(...unique(candidates));
    const found = checks.find((item) => item?.exists && item?.jid);
    if (found?.jid) return found.jid;
  } catch {
    // best effort; fallback below
  }
  return unique(candidates)[0];
}

async function sendTextNotification(to, text) {
  if (!sock || runtime.status !== "authenticated") throw new Error("WhatsApp nao esta autenticado");
  const chatId = await resolveChatId(to);
  const sent = await sendText(sock, chatId, String(text || "").trim(), null);
  rememberIgnoredOutbound(sent);
  return {
    chat_id: chatId,
    message_ids: sent.map((item) => item?.key?.id).filter(Boolean),
  };
}

async function startWhatsApp(config, options = {}) {
  const resetAuth = !!options.resetAuth;
  const source = String(options.source || "manual").trim();
  if (connecting || (runtime.status === "authenticated" && !resetAuth) || runtime.status === "connecting") return getRuntime();
  connecting = true;
  clearReconnectTimer();
  touchRuntime({
    status: "connecting",
    started_at: new Date().toISOString(),
    last_error: "",
    reconnect_scheduled_at: "",
    hint: resetAuth ? "Criando nova sessao e aguardando QR." : "Conectando ao WhatsApp...",
  });
  activity.publish("whatsapp:start", { source, reset_auth: resetAuth });
  try {
    if (resetAuth) {
      clearAuthDir(config);
      touchRuntime({ phone: "", qr: "", last_disconnect_code: 0 });
      activity.publish("whatsapp:session_reset", { source });
    }
    const authDir = authDirFromConfig(config);
    fs.mkdirSync(authDir, { recursive: true });
    const { state, saveCreds } = await useMultiFileAuthState(authDir);
    let version;
    try {
      version = (await fetchLatestBaileysVersion()).version;
    } catch {
      version = [2, 3000, 1033846690];
    }

    sock = makeWASocket({
      version,
      auth: state,
      browser: Browsers.macOS("Desktop"),
      logger: pino({ level: process.env.REDIA_BAILEYS_LOG_LEVEL || "error" }),
      connectTimeoutMs: 60000,
      defaultQueryTimeoutMs: 60000,
      keepAliveIntervalMs: 25000,
      syncFullHistory: false,
      getMessage: async () => ({ conversation: "" }),
    });

    sock.ev.on("creds.update", saveCreds);
    sock.ev.on("connection.update", async (update) => {
      const { connection, lastDisconnect, qr } = update;
      const code = lastDisconnect?.error?.output?.statusCode || 0;
      const message = lastDisconnect?.error?.message || "";
      if (connection || qr || code) {
        activity.publish("whatsapp:connection", {
          connection: connection || "",
          has_qr: !!qr,
          disconnect_code: code || 0,
          error: message,
        });
      }
      if (qr) {
        touchRuntime({
          qr: await QRCode.toDataURL(qr),
          status: "qrcode",
          last_error: "",
          reconnect_scheduled_at: "",
          hint: "Escaneie o QR Code com o WhatsApp do celular.",
        });
        activity.publish("whatsapp:qr", { reconnect_attempts: runtime.reconnect_attempts });
      }
      if (connection === "open") {
        clearReconnectTimer();
        touchRuntime({
          status: "authenticated",
          qr: "",
          phone: sock.user?.id || "",
          last_error: "",
          last_disconnect_code: 0,
          reconnect_attempts: 0,
          reconnect_scheduled_at: "",
          hint: "Sessao conectada e pronta.",
        });
        activity.publish("whatsapp:connected", { phone: runtime.phone });
      }
      if (connection === "close") {
        const friendly = disconnectLabel(code, message);
        touchRuntime({
          status: "disconnected",
          qr: "",
          last_error: friendly,
          last_disconnect_code: code || 0,
          hint: code === DisconnectReason.loggedOut || code === DisconnectReason.badSession || code === DisconnectReason.multideviceMismatch
            ? "Sessao invalida. Vamos limpar e gerar um novo QR."
            : "Conexao caiu. Tentando retomar automaticamente.",
        });
        sock = null;
        activity.publish("whatsapp:disconnected", {
          disconnect_code: code || 0,
          error: friendly,
        });
        if (code === DisconnectReason.connectionReplaced) {
          touchRuntime({ hint: "Outra sessao assumiu o WhatsApp. Reconecte quando quiser retomar." });
          return;
        }
        if (code === DisconnectReason.loggedOut || code === DisconnectReason.badSession || code === DisconnectReason.multideviceMismatch) {
          scheduleReconnect(config, { delayMs: 1800, resetAuth: true, reason: friendly });
          return;
        }
        scheduleReconnect(config, { delayMs: 2500, resetAuth: false, reason: friendly });
      }
    });

    setupMessageHandler(sock, { shouldIgnoreOutbound });
    return getRuntime();
  } catch (err) {
    touchRuntime({
      status: "error",
      last_error: err.message,
      hint: "Falha ao iniciar a sessao do WhatsApp.",
    });
    activity.publish("whatsapp:error", { error: err.message, source });
    throw err;
  } finally {
    connecting = false;
  }
}

async function restartWhatsApp(config, { reset = false, source = "manual-restart" } = {}) {
  await stopWhatsApp({ reset, config });
  return startWhatsApp(config, { resetAuth: false, source });
}

async function stopWhatsApp({ reset = false, config = null } = {}) {
  clearReconnectTimer();
  if (sock) {
    try {
      await sock.logout();
    } catch {
      try {
        sock.end();
      } catch {
        // ignore
      }
    }
  }
  sock = null;
  touchRuntime({
    status: "stopped",
    qr: "",
    reconnect_scheduled_at: "",
    hint: reset ? "Sessao apagada. Gere um novo QR para conectar." : "Sessao parada manualmente.",
  });
  if (reset) {
    clearAuthDir(config || { whatsapp: { auth_dir: "" } });
    touchRuntime({ phone: "", last_disconnect_code: 0, reconnect_attempts: 0 });
    activity.publish("whatsapp:session_reset", { source: "manual-stop" });
  }
  activity.publish("whatsapp:stopped", { reset });
  return getRuntime();
}

module.exports = { startWhatsApp, restartWhatsApp, stopWhatsApp, getRuntime, sendImageToChat, sendTextNotification };
