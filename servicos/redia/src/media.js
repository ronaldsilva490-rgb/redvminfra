const fs = require("fs");
const { tmpPath } = require("./paths");
const { chatComplete } = require("./redsystemsClient");
const activity = require("./activity");

async function optimizeImage(buffer, config) {
  const maxBytes = Number(config.media?.max_image_bytes || 1200000);
  if (!buffer || buffer.length <= maxBytes) return buffer;
  try {
    const sharp = require("sharp");
    return await sharp(buffer)
      .resize(1280, 1280, { fit: "inside", withoutEnlargement: true })
      .jpeg({ quality: 78 })
      .toBuffer();
  } catch {
    return buffer;
  }
}

async function analyzeImage(buffer, caption, config, meta = {}) {
  if (!config.media?.image_required) return "";
  const optimized = await optimizeImage(buffer, config);
  const base64 = optimized.toString("base64");
  const prompt = caption
    ? `Analise esta imagem no contexto do WhatsApp. Caption do usuario: "${caption}". Responda com uma descricao objetiva em portugues.`
    : "Analise esta imagem no contexto do WhatsApp. Responda com uma descricao objetiva em portugues.";
  activity.publish("media:image:start", {
    ...meta,
    model: config.chat.vision_model,
    bytes: optimized.length,
    caption_preview: caption || "",
  });
  try {
    const result = await chatComplete(config, {
      role: "vision",
      model: config.chat.vision_model,
      temperature: 0.2,
      messages: [{ role: "user", content: prompt, images: [base64] }],
      meta,
    });
    activity.publish("media:image:done", {
      ...meta,
      model: result.model || config.chat.vision_model,
      response_chars: result.content.length,
      response_preview: result.content,
    });
    return result.content || "";
  } catch (err) {
    activity.publish("media:image:error", {
      ...meta,
      model: config.chat.vision_model,
      error: err.message,
    });
    throw err;
  }
}

async function transcribeAudio(buffer, mimeType, config, meta = {}) {
  if (!config.stt?.enabled) return "";
  const provider = String(config.stt.provider || "groq").toLowerCase();
  const apiKey =
    config.stt.api_key ||
    (provider === "openai"
      ? process.env.OPENAI_API_KEY
      : process.env.GROQ_API_KEY || process.env.OPENAI_API_KEY);
  if (!apiKey) throw new Error(`STT ${provider} precisa de API key no ambiente.`);

  const model = config.stt.model || (provider === "openai" ? "whisper-1" : "whisper-large-v3-turbo");
  const apiUrl =
    provider === "openai"
      ? "https://api.openai.com/v1/audio/transcriptions"
      : "https://api.groq.com/openai/v1/audio/transcriptions";
  const ext = mimeType?.includes("mpeg") ? "mp3" : "ogg";
  const filePath = tmpPath(`stt_${Date.now()}_${Math.random().toString(16).slice(2)}.${ext}`);
  const started = Date.now();
  activity.publish("media:audio:start", {
    ...meta,
    provider,
    model,
    mime_type: mimeType || "audio/ogg",
    bytes: buffer?.length || 0,
  });
  try {
    fs.writeFileSync(filePath, buffer);
    const fileBytes = fs.readFileSync(filePath);
    const form = new FormData();
    form.append("file", new Blob([fileBytes], { type: mimeType || "audio/ogg" }), `audio.${ext}`);
    form.append("model", model);
    form.append("language", config.stt.language || "pt");
    form.append("response_format", "text");
    const resp = await fetch(apiUrl, {
      method: "POST",
      headers: { Authorization: `Bearer ${apiKey}` },
      body: form,
    });
    const text = await resp.text();
    if (!resp.ok) throw new Error(text || `STT HTTP ${resp.status}`);
    activity.publish("media:audio:done", {
      ...meta,
      provider,
      model,
      latency_ms: Date.now() - started,
      response_chars: text.trim().length,
      response_preview: text,
    });
    return text.trim();
  } catch (err) {
    activity.publish("media:audio:error", {
      ...meta,
      provider,
      model,
      latency_ms: Date.now() - started,
      error: err.message,
    });
    throw err;
  } finally {
    try {
      if (fs.existsSync(filePath)) fs.unlinkSync(filePath);
    } catch {
      // ignore tmp cleanup
    }
  }
}

module.exports = { analyzeImage, transcribeAudio, optimizeImage };
