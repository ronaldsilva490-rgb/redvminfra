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

function startDashboard({ whatsapp }) {
  const app = express();
  app.use(cors());
  app.use(express.json({ limit: "25mb" }));

  const adminToken = String(process.env.REDIA_ADMIN_TOKEN || "").trim();
  app.use("/api", (req, res, next) => {
    const header = String(req.headers.authorization || "");
    const bearer = header.startsWith("Bearer ") ? header.slice(7).trim() : "";
    if (req.path.startsWith("/image/worker")) {
      const workerToken = String(store.getConfig().image_generation?.worker_token || process.env.REDIA_IMAGE_WORKER_TOKEN || "").trim();
      if (workerToken && bearer === workerToken) return next();
    }
    if (!adminToken) return next();
    const queryToken = String(req.query.token || "").trim();
    if (bearer === adminToken || queryToken === adminToken) return next();
    return res.status(401).json({ error: "REDIA admin token required" });
  });

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

  app.post("/api/whatsapp/stop", async (req, res) => {
    res.json(await whatsapp.stopWhatsApp({ reset: !!req.body?.reset }));
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
  return app.listen(port, host, () => {
    console.log(`[dashboard] http://${host}:${port}`);
  });
}

module.exports = { startDashboard };
