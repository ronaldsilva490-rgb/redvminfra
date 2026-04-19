#!/usr/bin/env node
"use strict";

const http = require("http");
const { spawn } = require("child_process");

const port = Number(process.env.SEB_WEBHOOK_PORT || 2590);
const whatsappTarget = String(process.env.SEB_WHATSAPP_TARGET || "").trim();
const openclawBin = process.env.OPENCLAW_BIN || "/usr/local/bin/openclaw";
const openclawChannel = process.env.OPENCLAW_CHANNEL || "whatsapp";
const openclawHome = process.env.OPENCLAW_HOME || "/home/openclaw";
const openclawPath = process.env.OPENCLAW_PATH || "/opt/red-openclaw/node/bin:/opt/red-openclaw/npm/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin";
const publicPanelUrl = String(process.env.RED_SEB_PUBLIC_URL || "http://redsystems.ddns.net:2580").trim();

function asText(value, fallback = "n/d") {
  const text = String(value || "").trim();
  return text || fallback;
}

function asInt(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.round(parsed) : fallback;
}

function formatDate(value) {
  const date = new Date(value || "");
  if (Number.isNaN(date.getTime())) {
    return asText(value, "n/d");
  }
  return date.toLocaleString("pt-BR");
}

function buildSessionMessage(sessionInfo) {
  const primaryView = sessionInfo?.primaryView || {};
  const width = asInt(primaryView.width, 0);
  const height = asInt(primaryView.height, 0);
  const viewport = width > 0 && height > 0 ? `${width} x ${height}` : "n/d";
  const hasFrame = primaryView.hasFrame ? "sim" : "nao";
  return [
    "*Nova sessao SEB conectada*",
    "",
    `*ID*`,
    `\`${asText(sessionInfo.sessionId)}\``,
    "",
    `*Aplicacao*`,
    `${asText(sessionInfo.application, "SafeExamBrowser")}`,
    "",
    `*View ativa*`,
    `- Janela: \`${asText(primaryView.viewId)}\``,
    `- Titulo: ${asText(primaryView.title)}`,
    `- URL: ${asText(primaryView.url)}`,
    "",
    `*Conexao*`,
    `- Origem: \`${asText(sessionInfo.remoteAddress)}\``,
    `- Views abertas: \`${asInt(sessionInfo.viewsCount, 0)}\``,
    `- Viewport: \`${viewport}\``,
    `- Frame valida: \`${hasFrame}\``,
    "",
    `*Tempos*`,
    `- Conectado em: ${formatDate(sessionInfo.connectedAt)}`,
    `- Atualizado em: ${formatDate(sessionInfo.timestamp)}`,
    "",
    `*Painel*`,
    `${asText(sessionInfo.panelUrl || publicPanelUrl, publicPanelUrl)}`
  ].join("\n");
}

function sendViaOpenClaw(message) {
  return new Promise((resolve, reject) => {
    if (!whatsappTarget) {
      reject(new Error("SEB_WHATSAPP_TARGET nao configurado."));
      return;
    }

    const args = [
      "message",
      "send",
      "--channel",
      openclawChannel,
      "--target",
      whatsappTarget,
      "--message",
      message,
      "--json"
    ];

    const child = spawn(openclawBin, args, {
      env: {
        ...process.env,
        HOME: openclawHome,
        PATH: openclawPath
      },
      cwd: openclawHome
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString("utf8");
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolve({ stdout, stderr });
        return;
      }
      reject(new Error(`openclaw exited with code ${code}: ${(stderr || stdout).trim()}`));
    });
  });
}

async function handleNewSession(sessionInfo) {
  const message = buildSessionMessage(sessionInfo);
  console.log("[WEBHOOK] Nova sessao detectada:", asText(sessionInfo.sessionId));
  console.log("[WHATSAPP] Enviando para", whatsappTarget);
  const result = await sendViaOpenClaw(message);
  const summary = (result.stdout || result.stderr || "").trim();
  console.log("[WHATSAPP] Enviado com sucesso.", summary ? `Resposta: ${summary}` : "");
}

const server = http.createServer(async (req, res) => {
  if (req.method !== "POST" || req.url !== "/webhook/seb-session") {
    res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Not found");
    return;
  }

  let body = "";
  req.on("data", (chunk) => {
    body += chunk.toString("utf8");
  });

  req.on("end", async () => {
    try {
      const payload = JSON.parse(body || "{}");
      if (payload.type !== "seb_session_new") {
        res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
        res.end(JSON.stringify({ ok: true, ignored: true }));
        return;
      }

      await handleNewSession(payload);
      res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
      res.end(JSON.stringify({ ok: true, delivered: true }));
    } catch (error) {
      console.error("[WEBHOOK] Falha:", error.message);
      res.writeHead(500, { "Content-Type": "application/json; charset=utf-8" });
      res.end(JSON.stringify({ ok: false, error: error.message }));
    }
  });
});

server.listen(port, "127.0.0.1", () => {
  console.log(`SEB Webhook -> WhatsApp listening on http://127.0.0.1:${port}`);
  console.log(`Target: ${whatsappTarget || "(not configured)"}`);
  console.log(`OpenClaw: ${openclawBin}`);
});
