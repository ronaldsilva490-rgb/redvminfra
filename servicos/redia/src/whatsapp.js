const fs = require("fs");
const pino = require("pino");
const QRCode = require("qrcode");
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
};

let sock = null;
let connecting = false;
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

async function startWhatsApp(config) {
  if (connecting || runtime.status === "authenticated" || runtime.status === "connecting") return getRuntime();
  connecting = true;
  runtime.status = "connecting";
  runtime.started_at = new Date().toISOString();
  runtime.last_error = "";
  try {
    const authDir = authPath(config.whatsapp?.auth_dir || "");
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
      printQRInTerminal: true,
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
      if (qr) {
        runtime.qr = await QRCode.toDataURL(qr);
        runtime.status = "qrcode";
      }
      if (connection === "open") {
        runtime.status = "authenticated";
        runtime.qr = "";
        runtime.phone = sock.user?.id || "";
      }
      if (connection === "close") {
        const code = lastDisconnect?.error?.output?.statusCode;
        runtime.status = "disconnected";
        runtime.qr = "";
        runtime.last_error = lastDisconnect?.error?.message || "";
        sock = null;
        if (code === DisconnectReason.loggedOut) {
          return;
        }
        setTimeout(() => startWhatsApp(config).catch(() => {}), 2500);
      }
    });

    setupMessageHandler(sock, { shouldIgnoreOutbound });
    return getRuntime();
  } catch (err) {
    runtime.status = "error";
    runtime.last_error = err.message;
    throw err;
  } finally {
    connecting = false;
  }
}

async function stopWhatsApp({ reset = false } = {}) {
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
  runtime.status = "stopped";
  runtime.qr = "";
  if (reset) {
    const dir = authPath("");
    if (fs.existsSync(dir)) fs.rmSync(dir, { recursive: true, force: true });
  }
  return getRuntime();
}

module.exports = { startWhatsApp, stopWhatsApp, getRuntime, sendImageToChat, sendTextNotification };
