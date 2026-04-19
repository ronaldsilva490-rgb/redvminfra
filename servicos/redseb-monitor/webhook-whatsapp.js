#!/usr/bin/env node
"use strict";

const http = require("http");
const { spawn } = require("child_process");

const port = Number(process.env.SEB_WEBHOOK_PORT || 2590);
const whatsappTarget = String(process.env.SEB_WHATSAPP_TARGET || "").trim();
const proxyBase = String(process.env.RED_PROXY_BASE || "http://127.0.0.1:8080").replace(/\/+$/, "");
const formatterModel = String(process.env.SEB_WHATSAPP_FORMATTER_MODEL || "NIM - nvidia/llama-3.1-nemotron-nano-8b-v1").trim();
const formatterTimeoutMs = Number(process.env.SEB_WHATSAPP_FORMATTER_TIMEOUT_MS || 12000);
const openclawBin = process.env.OPENCLAW_BIN || "/usr/local/bin/openclaw";
const openclawChannel = process.env.OPENCLAW_CHANNEL || "whatsapp";
const openclawHome = process.env.OPENCLAW_HOME || "/home/openclaw";
const openclawPath = process.env.OPENCLAW_PATH || "/opt/red-openclaw/node/bin:/opt/red-openclaw/npm/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin";

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
  return [
    "🚨 *NOVA SESSAO SEB DETECTADA!*",
    `🌐 *IP:* ${asText(sessionInfo.remoteAddress)}`,
    `🪟 *TITULO:* ${asText(primaryView.title)}`,
    `🖥️ *RESOLUCAO:* ${viewport}`,
    `🕒 *HORA DA CONEXAO:* ${formatDate(sessionInfo.connectedAt)}`
  ].join("\n");
}

function normalizeWhatsappText(text, fallback) {
  const normalized = String(text || "")
    .replace(/\r/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]*\n[ \t]*/g, "\n")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
  return normalized || fallback;
}

function isAcceptableFormattedMessage(text, sessionInfo) {
  const value = String(text || "");
  const lines = value
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  const primaryView = sessionInfo?.primaryView || {};
  const width = asInt(primaryView.width, 0);
  const height = asInt(primaryView.height, 0);
  const viewport = width > 0 && height > 0 ? `${width} x ${height}` : "n/d";
  const requiredValues = [
    asText(sessionInfo.remoteAddress),
    asText(primaryView.title),
    viewport,
    formatDate(sessionInfo.connectedAt)
  ];
  const requiredLabels = [
    "NOVA SESSAO SEB DETECTADA",
    "IP:",
    "TITULO:",
    "RESOLUCAO:",
    "HORA DA CONEXAO:"
  ];
  if (!value || value.length > 420 || lines.length !== 5) {
    return false;
  }
  return requiredValues.every((part) => value.includes(part))
    && requiredLabels.every((part) => value.toUpperCase().includes(part));
}

async function formatMessageWithProxy(sessionInfo, fallbackMessage) {
  const primaryView = sessionInfo?.primaryView || {};
  const width = asInt(primaryView.width, 0);
  const height = asInt(primaryView.height, 0);
  const viewport = width > 0 && height > 0 ? `${width} x ${height}` : "n/d";
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), formatterTimeoutMs);
  try {
    const upstream = await fetch(proxyBase + "/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        model: formatterModel,
        temperature: 0.2,
        max_tokens: 180,
        messages: [
          {
            role: "system",
            content: [
              "Formate alertas operacionais para WhatsApp em pt-BR.",
              "Responda com UMA mensagem curta, elegante e objetiva.",
              "Voce pode usar markdown e alguns emojis sutis.",
              "Nao invente fatos.",
              "Nao explique nada.",
              "Nao adicione contexto extra.",
              "Nao use listas longas ou frases narrativas.",
              "Retorne exatamente 5 linhas curtas.",
              "Use exatamente estes rotulos: NOVA SESSAO SEB DETECTADA, IP, TITULO, RESOLUCAO e HORA DA CONEXAO.",
              "Nao adicione cabecalhos extras, apelidos, nomes de instituicao ou comentarios.",
              "Inclua com precisao apenas estes fatos: alerta de nova sessao, IP, titulo, resolucao e hora da conexao.",
              "Mantenha todos os valores exatamente como recebidos.",
              "Use algo bem legivel para WhatsApp, com no maximo um emoji por linha e no maximo uma linha para cada campo."
            ].join(" ")
          },
          {
            role: "user",
            content: [
              "Transforme estes dados em um alerta elegante para WhatsApp:",
              `tipo=NOVA SESSAO SEB DETECTADA`,
              `ip=${asText(sessionInfo.remoteAddress)}`,
              `titulo=${asText(primaryView.title)}`,
              `resolucao=${viewport}`,
              `hora=${formatDate(sessionInfo.connectedAt)}`
            ].join("\n")
          }
        ]
      }),
      signal: controller.signal
    });
    if (!upstream.ok) {
      throw new Error(`proxy HTTP ${upstream.status}`);
    }
    const data = await upstream.json();
    const content = data?.choices?.[0]?.message?.content;
    const normalized = normalizeWhatsappText(content, fallbackMessage);
    if (!isAcceptableFormattedMessage(normalized, sessionInfo)) {
      throw new Error("formatter saiu do formato esperado");
    }
    return normalized;
  } finally {
    clearTimeout(timeout);
  }
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
  const fallbackMessage = buildSessionMessage(sessionInfo);
  let message = fallbackMessage;
  try {
    message = await formatMessageWithProxy(sessionInfo, fallbackMessage);
    console.log("[WHATSAPP] Mensagem formatada via proxy:", formatterModel);
  } catch (error) {
    console.warn("[WHATSAPP] Formatter fallback:", error.message);
  }
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
