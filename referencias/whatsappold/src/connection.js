// ══════════════════════════════════════════════════
// CONNECTION — Baileys setup, QR, reconexão, auto-start
// ══════════════════════════════════════════════════
const path = require("path");
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
const { supabase, sessions } = require("./state");
const { loadTenantAIConfigs } = require("./config");
const { setupMessageHandler } = require("./messageHandler");
const { presenceManager } = require("./sender");

let cachedBaileysVersion = null;
async function getBaileysVersion() {
  if (cachedBaileysVersion) return cachedBaileysVersion;
  try {
    cachedBaileysVersion = await fetchLatestBaileysVersion();
    return cachedBaileysVersion;
  } catch {
    return { version: [2, 3000, 1033846690], isLatest: true };
  }
}

const BLOCKED_OUTBOUND_RULES = [
  ["ia", "demorando"],
  ["processando", "demorar"],
  ["continuar", "aguardando"],
  ["sem", "conexao", "modelo"],
];

function normalizeOutboundText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function isBlockedOutboundText(value) {
  const text = normalizeOutboundText(value);
  if (!text) return false;
  return BLOCKED_OUTBOUND_RULES.some((rule) =>
    rule.every((token) => text.includes(token)),
  );
}

async function connectToWhatsApp(tenantId, forceReset = false) {
  if (!forceReset && sessions.has(tenantId)) {
    const existing = sessions.get(tenantId);
    if (
      existing.status === "authenticated" ||
      existing.status === "connecting"
    ) {
      console.log(
        `[WA] ⚠️ Tenant ${tenantId} já está conectado/conectando. Ignorando chamada duplicada.`,
      );
      return;
    }
  }

  console.log(
    `[WA] Conectando tenant: ${tenantId}${forceReset ? " (RESET)" : ""}`,
  );
  const authPath = path.join(
    __dirname,
    "..",
    `auth_info_baileys/tenant_${tenantId}`,
  );

  if (forceReset && fs.existsSync(authPath))
    fs.rmSync(authPath, { recursive: true, force: true });
  if (!fs.existsSync(authPath)) fs.mkdirSync(authPath, { recursive: true });

  const { state, saveCreds } = await useMultiFileAuthState(authPath);
  const { version } = await getBaileysVersion();

  const sock = makeWASocket({
    version,
    auth: state,
    printQRInTerminal: false,
    browser: Browsers.macOS("Desktop"),
    logger: pino({ level: "error" }),
    connectTimeoutMs: 60000,
    defaultQueryTimeoutMs: 60000,
    keepAliveIntervalMs: 25000,
    syncFullHistory: false,
    getMessage: async () => ({ conversation: "" }),
  });

  const _sendMessage = sock.sendMessage.bind(sock);
  sock.sendMessage = async (jid, content, options) => {
    const textPayload =
      typeof content?.text === "string"
        ? content.text
        : typeof content?.caption === "string"
          ? content.caption
          : "";
    if (isBlockedOutboundText(textPayload)) {
      console.warn(
        `[WA-BLOCK] Mensagem de sistema bloqueada para ${jid}: ${textPayload.substring(0, 120)}`,
      );
      return { key: null };
    }
    return _sendMessage(jid, content, options);
  };

  const session = {
    sock,
    aiConfigs: null,
    lastQr: null,
    status: "connecting",
    lastConfigRefresh: 0,
  };
  sessions.set(tenantId, session);
  await loadTenantAIConfigs(tenantId);
  session.lastConfigRefresh = Date.now();

  sock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      session.lastQr = await QRCode.toDataURL(qr);
      session.status = "qrcode";
      try {
        await supabase
          .from("whatsapp_sessions")
          .upsert(
            {
              tenant_id: tenantId,
              status: "qrcode",
              qr: session.lastQr,
              updated_at: new Date(),
            },
            { onConflict: "tenant_id" },
          );
      } catch (_) {}
    }

    if (connection === "close") {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      session.status = "disconnected";
      session.lastQr = null;
      presenceManager._active.clear();

      if (statusCode === DisconnectReason.loggedOut || statusCode === 428) {
        sessions.delete(tenantId);
        try {
          await supabase
            .from("whatsapp_sessions")
            .delete()
            .eq("tenant_id", tenantId);
        } catch (_) {}
        if (fs.existsSync(authPath))
          fs.rmSync(authPath, { recursive: true, force: true });
        if (statusCode === 428)
          setTimeout(() => connectToWhatsApp(tenantId, false), 3000);
      } else {
        setTimeout(() => connectToWhatsApp(tenantId, false), 2000);
      }
    } else if (connection === "open") {
      session.status = "authenticated";
      session.lastQr = null;
      try {
        await supabase
          .from("whatsapp_sessions")
          .upsert(
            {
              tenant_id: tenantId,
              status: "authenticated",
              phone: sock.user.id,
              qr: null,
              updated_at: new Date(),
            },
            { onConflict: "tenant_id" },
          );
      } catch (_) {}
      console.log(`✅ Tenant ${tenantId} conectado!`);
    }
  });

  sock.ev.on("creds.update", saveCreds);
  setupMessageHandler(sock, tenantId);
}

async function autoStartSavedSessions() {
  await new Promise((r) => setTimeout(r, 3000));
  try {
    const { data: savedSessions, error } = await supabase
      .from("whatsapp_sessions")
      .select("tenant_id")
      .eq("status", "authenticated");
    if (error) {
      console.error("[AUTO-START] Erro:", error.message);
      return;
    }
    if (!savedSessions?.length) {
      console.log("[AUTO-START] Nenhuma sessão salva.");
      return;
    }
    console.log(
      `[AUTO-START] 🔄 ${savedSessions.length} sessão(ões) para restaurar...`,
    );
    for (const { tenant_id } of savedSessions) {
      const credsFile = path.join(
        __dirname,
        "..",
        `auth_info_baileys/tenant_${tenant_id}/creds.json`,
      );
      if (fs.existsSync(credsFile)) {
        console.log(`[AUTO-START] ✅ Restaurando: ${tenant_id}`);
        connectToWhatsApp(tenant_id, false).catch((err) =>
          console.error(`[AUTO-START] ❌ ${tenant_id}:`, err.message),
        );
        await new Promise((r) => setTimeout(r, 2000));
      } else {
        console.log(`[AUTO-START] ⚠️  ${tenant_id}: sem creds.json`);
      }
    }
  } catch (err) {
    console.error("[AUTO-START] Exceção:", err.message);
  }
}

module.exports = { connectToWhatsApp, autoStartSavedSessions };
