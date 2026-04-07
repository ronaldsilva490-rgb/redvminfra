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
const { sendImage } = require("./sender");

const runtime = {
  status: "stopped",
  qr: "",
  phone: "",
  last_error: "",
  started_at: "",
};

let sock = null;
let connecting = false;

function getRuntime() {
  return { ...runtime };
}

async function sendImageToChat(chatId, image, caption = "") {
  if (!sock || runtime.status !== "authenticated") throw new Error("WhatsApp nao esta autenticado");
  return sendImage(sock, chatId, image, caption);
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

    setupMessageHandler(sock);
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

module.exports = { startWhatsApp, stopWhatsApp, getRuntime, sendImageToChat };
