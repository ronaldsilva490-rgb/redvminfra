const express = require("express");
const cors = require("cors");
const fs = require("fs");
const path = require("path");
const { execFile } = require("child_process");
const { promisify } = require("util");
const store = require("./store");
const { listModels, chatComplete } = require("./redsystemsClient");
const { saveResultImage } = require("./imageGeneration");
const activity = require("./activity");
const { buildChatMessages } = require("./memory");

const execFileAsync = promisify(execFile);

const FALLBACK_EDGE_VOICES = [
  { name: "pt-BR-FranciscaNeural", locale: "pt-BR", gender: "Female", display_name: "Francisca" },
  { name: "pt-BR-AntonioNeural", locale: "pt-BR", gender: "Male", display_name: "Antonio" },
  { name: "pt-BR-ThalitaMultilingualNeural", locale: "pt-BR", gender: "Female", display_name: "Thalita" },
];

let voiceCache = { at: 0, rows: FALLBACK_EDGE_VOICES };

async function listEdgeVoices() {
  if (Date.now() - voiceCache.at < 10 * 60 * 1000 && voiceCache.rows.length) return voiceCache.rows;
  const script = `
import asyncio, json, edge_tts
async def main():
    voices = await edge_tts.list_voices()
    rows = []
    for item in voices:
        locale = item.get("Locale", "")
        if locale.startswith("pt-BR"):
            rows.append({
                "name": item.get("ShortName", ""),
                "locale": locale,
                "gender": item.get("Gender", ""),
                "display_name": item.get("FriendlyName", "") or item.get("ShortName", ""),
            })
    print(json.dumps(rows, ensure_ascii=False))
asyncio.run(main())
`.trim();
  try {
    const { stdout } = await execFileAsync("python3", ["-c", script], { timeout: 20000, maxBuffer: 1024 * 1024 * 2 });
    const rows = JSON.parse(stdout || "[]").filter((item) => item.name);
    if (rows.length) {
      rows.sort((a, b) => {
        const left = String(a.name || "").toLowerCase();
        const right = String(b.name || "").toLowerCase();
        if (left < right) return -1;
        if (left > right) return 1;
        return 0;
      });
      voiceCache = { at: Date.now(), rows };
    }
  } catch {
    voiceCache = { at: Date.now(), rows: FALLBACK_EDGE_VOICES };
  }
  return voiceCache.rows;
}

function normalizeIsoDate(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString();
}

function clipText(value, limit = 4000) {
  return String(value || "").trim().slice(0, limit);
}

function recordOutgoingMessage({ chatId, chatName = "", text = "", metadata = {} }) {
  const finalText = clipText(text, 12000);
  if (!chatId || !finalText) return;
  store.ensureConversation(chatId, { name: chatName });
  store.appendMessage({
    id: `${chatId}:assistant:${Date.now()}:${Math.random().toString(16).slice(2, 8)}`,
    chat_id: chatId,
    chat_name: chatName,
    role: "assistant",
    direction: "outgoing",
    sender_name: "RED I.A",
    text: finalText,
    content_type: "text",
    metadata,
  });
}

function buildScheduledAiMessages(schedule, config) {
  const conversation = store.ensureConversation(schedule.chat_id, { name: schedule.chat_name || "" });
  const prompt = clipText(
    schedule.prompt
      || "Puxe assunto com naturalidade, em portugues do Brasil, sem parecer automatizado e sem dizer que foi agendado.",
    6000,
  );
  const messages = buildChatMessages({
    config,
    conversation,
    prompt,
    senderName: schedule.chat_name || conversation?.name || "operador",
    senderJid: schedule.chat_id,
    model: schedule.model || config.proactive?.model || config.chat?.default_model || "",
  });
  if (messages[0]?.content) {
    messages[0].content += "\n\nVoce esta enviando uma mensagem proativa agendada pelo operador. Seja natural, contextual, curta quando fizer sentido e nao diga que esta executando automacao, agenda ou rotina.";
  }
  return messages;
}

function startScheduleWorker({ whatsapp }) {
  let running = false;

  async function tick() {
    if (running) return;
    running = true;
    try {
      while (true) {
        const scheduled = store.claimDueScheduledMessage();
        if (!scheduled) break;
        try {
          const config = store.getConfig();
          const mode = String(scheduled.mode || "text").trim().toLowerCase();
          let text = clipText(scheduled.text, 12000);
          if (mode === "ai") {
            const completion = await chatComplete(config, {
              role: "scheduled-outreach",
              model: scheduled.model || config.proactive?.model || config.chat?.default_model || "",
              temperature: 0.75,
              messages: buildScheduledAiMessages(scheduled, config),
              timeoutMs: 90000,
              meta: { source: "schedule", schedule_id: scheduled.id, chat_id: scheduled.chat_id },
            });
            text = clipText(completion.content, 12000);
            store.saveModelRun({
              role: "scheduled-outreach",
              model: completion.model,
              prompt_chars: scheduled.prompt.length,
              response_chars: text.length,
              latency_ms: completion.latency_ms,
              ok: true,
            });
          }
          if (!text) {
            throw new Error("Mensagem agendada sem texto final");
          }
          activity.publish("schedule:sending", {
            schedule_id: scheduled.id,
            mode,
            chat_id: scheduled.chat_id,
            send_at: scheduled.send_at,
          });
          const sent = await whatsapp.sendTextNotification(scheduled.chat_id, text);
          recordOutgoingMessage({
            chatId: sent.chat_id || scheduled.chat_id,
            chatName: scheduled.chat_name,
            text,
            metadata: {
              schedule_id: scheduled.id,
              mode,
              message_ids: sent.message_ids || [],
            },
          });
          const completed = store.completeScheduledMessage(scheduled.id, {
            result_message_ids: sent.message_ids || [],
            metadata: { sent_chat_id: sent.chat_id || scheduled.chat_id },
          });
          activity.publish("schedule:sent", {
            schedule_id: completed.id,
            mode,
            chat_id: completed.chat_id,
            message_ids: completed.result_message_ids || [],
          });
        } catch (err) {
          const failed = store.failScheduledMessage(scheduled.id, err.message);
          activity.publish("schedule:error", {
            schedule_id: failed?.id || scheduled.id,
            chat_id: scheduled.chat_id,
            mode: scheduled.mode,
            error: err.message,
          });
        }
      }
    } finally {
      running = false;
    }
  }

  const timer = setInterval(() => {
    tick().catch(() => {});
  }, 5000);
  timer.unref?.();
  tick().catch(() => {});
  return timer;
}

function startDashboard({ whatsapp }) {
  const app = express();
  app.use(cors());
  app.use(express.json({ limit: "25mb" }));

  const adminToken = String(process.env.REDIA_ADMIN_TOKEN || "").trim();
  app.use("/api", (req, res, next) => {
    const header = String(req.headers.authorization || "");
    const bearer = header.startsWith("Bearer ") ? header.slice(7).trim() : "";
    if (req.path.startsWith("/internal/")) {
      const internalToken = String(process.env.REDIA_INTERNAL_TOKEN || "").trim();
      if (internalToken && bearer === internalToken) return next();
      return res.status(401).json({ error: "REDIA internal token required" });
    }
    if (req.path.startsWith("/image/worker")) {
      const workerToken = String(store.getConfig().image_generation?.worker_token || process.env.REDIA_IMAGE_WORKER_TOKEN || "").trim();
      if (workerToken && bearer === workerToken) return next();
    }
    if (!adminToken) return next();
    const queryToken = String(req.query.token || "").trim();
    if (bearer === adminToken || queryToken === adminToken) return next();
    return res.status(401).json({ error: "REDIA admin token required" });
  });

  const schedulerTimer = startScheduleWorker({ whatsapp });

  app.use(express.static(path.join(__dirname, "..", "public")));

  app.get("/api/status", async (_req, res) => {
    const config = store.getConfig();
    let models = [];
    let proxy_error = "";
    try {
      models = await listModels(config);
    } catch (err) {
      proxy_error = err.message;
    }
    res.json({
      ok: true,
      whatsapp: whatsapp.getRuntime(),
      proxy: {
        base_url: config.proxy.base_url,
        models,
        error: proxy_error,
      },
      runs: store.modelRuns(30),
    });
  });

  app.get("/api/config", (_req, res) => {
    res.json(store.getConfig());
  });

  app.get("/api/activity", (req, res) => {
    res.json({ events: activity.recent(Number(req.query.limit || 160)) });
  });

  app.post("/api/internal/notify-whatsapp", async (req, res) => {
    const to = String(req.body?.to || process.env.REDIA_NOTIFY_DEFAULT_TO || "").trim();
    const text = String(req.body?.text || "").trim();
    if (!to) return res.status(400).json({ ok: false, error: "missing to" });
    if (!text) return res.status(400).json({ ok: false, error: "missing text" });
    try {
      const sent = await whatsapp.sendTextNotification(to, text);
      activity.publish("whatsapp:external_notification", {
        chat_id: sent.chat_id,
        chars: text.length,
        source: req.body?.source || "external",
        metadata: req.body?.metadata || {},
      });
      res.json({ ok: true, sent });
    } catch (err) {
      activity.publish("whatsapp:external_notification_error", {
        to,
        source: req.body?.source || "external",
        error: err.message,
      });
      res.status(502).json({ ok: false, error: err.message });
    }
  });

  app.post("/api/messages/send", async (req, res) => {
    const to = String(req.body?.chat_id || req.body?.to || "").trim();
    const chatName = String(req.body?.chat_name || "").trim();
    const text = clipText(req.body?.text, 12000);
    if (!to) return res.status(400).json({ ok: false, error: "missing chat_id" });
    if (!text) return res.status(400).json({ ok: false, error: "missing text" });
    try {
      const sent = await whatsapp.sendTextNotification(to, text);
      recordOutgoingMessage({
        chatId: sent.chat_id || to,
        chatName,
        text,
        metadata: {
          source: req.body?.source || "dashboard-manual",
          message_ids: sent.message_ids || [],
        },
      });
      activity.publish("whatsapp:manual_send", {
        chat_id: sent.chat_id || to,
        chars: text.length,
        source: req.body?.source || "dashboard-manual",
      });
      res.json({ ok: true, sent });
    } catch (err) {
      activity.publish("whatsapp:manual_send_error", {
        chat_id: to,
        source: req.body?.source || "dashboard-manual",
        error: err.message,
      });
      res.status(502).json({ ok: false, error: err.message });
    }
  });

  app.get("/api/schedules", (req, res) => {
    res.json({ schedules: store.listScheduledMessages(Number(req.query.limit || 80)) });
  });

  app.post("/api/schedules", (req, res) => {
    const mode = String(req.body?.mode || "text").trim().toLowerCase();
    const chatId = String(req.body?.chat_id || req.body?.to || "").trim();
    const sendAt = normalizeIsoDate(req.body?.send_at);
    const text = clipText(req.body?.text, 12000);
    const prompt = clipText(req.body?.prompt, 12000);
    if (!chatId) return res.status(400).json({ ok: false, error: "missing chat_id" });
    if (!sendAt) return res.status(400).json({ ok: false, error: "invalid send_at" });
    if (mode === "text" && !text) return res.status(400).json({ ok: false, error: "missing text" });
    if (mode === "ai" && !prompt) return res.status(400).json({ ok: false, error: "missing prompt" });
    const schedule = store.createScheduledMessage({
      chat_id: chatId,
      chat_name: String(req.body?.chat_name || "").trim(),
      mode,
      text,
      prompt,
      model: String(req.body?.model || "").trim(),
      send_at: sendAt,
      metadata: {
        source: req.body?.source || "dashboard",
      },
    });
    activity.publish("schedule:queued", {
      schedule_id: schedule.id,
      chat_id: schedule.chat_id,
      mode: schedule.mode,
      send_at: schedule.send_at,
    });
    res.json({ ok: true, schedule });
  });

  app.delete("/api/schedules/:id", (req, res) => {
    const schedule = store.cancelScheduledMessage(req.params.id);
    if (!schedule) return res.status(404).json({ ok: false, error: "schedule not found" });
    activity.publish("schedule:canceled", {
      schedule_id: schedule.id,
      chat_id: schedule.chat_id,
      mode: schedule.mode,
    });
    res.json({ ok: true, schedule });
  });

  app.get("/api/image/jobs", (req, res) => {
    res.json({ jobs: store.listImageJobs(Number(req.query.limit || 80)) });
  });

  app.post("/api/image/worker/claim", (req, res) => {
    const workerId = String(req.body?.worker_id || req.headers["x-worker-id"] || "kaggle-worker").slice(0, 120);
    const job = store.claimImageJob(workerId);
    if (!job) return res.json({ ok: true, job: null });
    activity.publish("image:claimed", { job_id: job.id, worker_id: workerId, profile: job.profile });
    res.json({ ok: true, job });
  });

  app.post("/api/image/worker/generating", (req, res) => {
    const workerId = String(req.body?.worker_id || req.headers["x-worker-id"] || "kaggle-worker").slice(0, 120);
    const job = store.markImageJobGenerating(req.body?.job_id, workerId);
    res.json({ ok: !!job, job });
  });

  app.post("/api/image/worker/result", async (req, res) => {
    const workerId = String(req.body?.worker_id || req.headers["x-worker-id"] || "kaggle-worker").slice(0, 120);
    const job = store.getImageJob(req.body?.job_id);
    if (!job) return res.status(404).json({ ok: false, error: "job not found" });
    if (!req.body?.ok) {
      const failed = store.failImageJob(job.id, req.body?.error || "worker failed", workerId);
      activity.publish("image:failed", { job_id: job.id, worker_id: workerId, error: failed.error });
      return res.json({ ok: true, job: failed });
    }
    try {
      const resultPath = saveResultImage(job.id, req.body?.image_base64, req.body?.mime_type || "image/png");
      const completed = store.completeImageJob(job.id, {
        result_path: resultPath,
        worker_id: workerId,
        metadata: {
          mime_type: req.body?.mime_type || "image/png",
          generation_ms: req.body?.generation_ms || 0,
          seed: req.body?.seed || "",
        },
      });
      const caption = String(completed.metadata?.caption || "Imagem pronta.").slice(0, 900);
      const sent = await whatsapp.sendImageToChat(completed.chat_id, fs.readFileSync(resultPath), caption);
      store.appendMessage({
        id: `${completed.chat_id}:image:${completed.id}:${Date.now()}`,
        chat_id: completed.chat_id,
        role: "assistant",
        direction: "outgoing",
        sender_name: "REDIA",
        text: caption,
        content_type: "image",
        metadata: {
          image_job_id: completed.id,
          result_path: resultPath,
          whatsapp_keys: [
            {
              id: sent?.key?.id || "",
              remote_jid: sent?.key?.remoteJid || "",
              from_me: !!sent?.key?.fromMe,
            },
          ],
        },
      });
      activity.publish("image:sent", { job_id: completed.id, chat_id: completed.chat_id, worker_id: workerId, result_path: resultPath });
      res.json({ ok: true, job: completed, sent: !!sent });
    } catch (err) {
      const failed = store.failImageJob(job.id, err.message, workerId);
      activity.publish("image:failed", { job_id: job.id, worker_id: workerId, error: err.message });
      res.status(500).json({ ok: false, error: err.message, job: failed });
    }
  });

  app.get("/api/events", (req, res) => {
    activity.stream(req, res);
  });

  app.get("/api/tts/voices", async (_req, res) => {
    res.json({ voices: await listEdgeVoices() });
  });

  app.put("/api/config", (req, res) => {
    res.json(store.saveConfig(req.body || {}));
  });

  app.post("/api/whatsapp/start", async (_req, res) => {
    const config = store.getConfig();
    res.json(await whatsapp.startWhatsApp(config));
  });

  app.post("/api/whatsapp/reconnect", async (req, res) => {
    const config = store.getConfig();
    res.json(await whatsapp.restartWhatsApp(config, { reset: !!req.body?.reset, source: "dashboard" }));
  });

  app.post("/api/whatsapp/stop", async (req, res) => {
    const config = store.getConfig();
    res.json(await whatsapp.stopWhatsApp({ reset: !!req.body?.reset, config }));
  });

  app.get("/api/conversations", (_req, res) => {
    res.json({ conversations: store.listConversations(100) });
  });

  app.get("/api/conversations/:chatId/messages", (req, res) => {
    res.json({ messages: store.recentMessages(req.params.chatId, 80) });
  });

  app.post("/api/test-ai", async (req, res) => {
    const config = store.getConfig();
    const prompt = String(req.body?.prompt || "Responda apenas: ok redia").trim();
    const model = String(req.body?.model || config.chat.default_model || "").trim();
    const startedPromptChars = prompt.length;
    try {
      const result = await chatComplete(config, {
        role: "dashboard-test",
        model,
        temperature: Number(req.body?.temperature ?? 0.4),
        messages: [
          { role: "system", content: "Voce e a REDIA em um teste de dashboard. Responda em portugues." },
          { role: "user", content: prompt },
        ],
        meta: { source: "dashboard" },
      });
      store.saveModelRun({
        role: "dashboard-test",
        model: result.model,
        prompt_chars: startedPromptChars,
        response_chars: result.content.length,
        latency_ms: result.latency_ms,
        ok: true,
      });
      res.json(result);
    } catch (err) {
      store.saveModelRun({
        role: "dashboard-test",
        model,
        prompt_chars: startedPromptChars,
        response_chars: 0,
        latency_ms: 0,
        ok: false,
        error: err.message,
      });
      res.status(502).json({ ok: false, error: err.message });
    }
  });

  app.post("/api/benchmark", async (req, res) => {
    const config = store.getConfig();
    const models = Array.isArray(req.body?.models) ? req.body.models : [];
    const prompt = String(req.body?.prompt || "Explique em ate 2 frases como voce responderia uma mensagem de WhatsApp com naturalidade.").trim();
    const rows = [];
    for (const model of models.filter(Boolean).slice(0, 8)) {
      const started = Date.now();
      try {
        const result = await chatComplete(config, {
          role: "benchmark",
          model,
          temperature: 0.35,
          messages: [{ role: "user", content: prompt }],
          timeoutMs: 60000,
          meta: { source: "dashboard" },
        });
        const row = {
          model: result.model,
          ok: true,
          latency_ms: result.latency_ms || Date.now() - started,
          chars: result.content.length,
          content: result.content,
        };
        rows.push(row);
        store.saveModelRun({
          role: "benchmark",
          model: row.model,
          prompt_chars: prompt.length,
          response_chars: row.chars,
          latency_ms: row.latency_ms,
          ok: true,
        });
      } catch (err) {
        rows.push({ model, ok: false, latency_ms: Date.now() - started, error: err.message });
        store.saveModelRun({
          role: "benchmark",
          model,
          prompt_chars: prompt.length,
          response_chars: 0,
          latency_ms: Date.now() - started,
          ok: false,
          error: err.message,
        });
      }
    }
    res.json({ rows });
  });

  const config = store.getConfig();
  const host = config.app.host || "0.0.0.0";
  const port = config.app.port || 3099;
  const server = app.listen(port, host, () => {
    console.log(`[dashboard] http://${host}:${port}`);
  });
  server.on("close", () => {
    clearInterval(schedulerTimer);
  });
  return server;
}

module.exports = { startDashboard };
