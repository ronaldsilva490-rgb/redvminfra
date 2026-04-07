const fs = require("fs");
const path = require("path");
const { normalizeText, foldText } = require("./format");
const { chatComplete } = require("./redsystemsClient");
const store = require("./store");
const activity = require("./activity");
const { dataPath, ensureDir } = require("./paths");
const { safeJsonParse } = require("./json");

const IMAGE_TRIGGERS = [
  "gera imagem",
  "gerar imagem",
  "cria imagem",
  "criar imagem",
  "faz uma imagem",
  "fazer uma imagem",
  "desenha",
  "desenhe",
  "manda foto",
  "mande foto",
  "gera uma foto",
  "cria uma foto",
  "imagem de",
  "foto de",
];

const BLOCKED_PATTERNS = [];

const NEGATIVE_PROMPT = [].join(", ");

function detectImageIntent(text) {
  const folded = foldText(normalizeText(text || ""));
  const isImageRequest = IMAGE_TRIGGERS.some((trigger) => folded.includes(foldText(trigger)));
  if (!isImageRequest) return { is_image_request: false };
  const blocked = BLOCKED_PATTERNS.find((pattern) => pattern.test(folded));
  if (blocked) {
    return {
      is_image_request: true,
      allowed: false,
      reason: "blocked_explicit_or_illegal_risk",
    };
  }
  return {
    is_image_request: true,
    allowed: true,
    reason: "allowed_general_image",
  };
}

async function buildSafePrompt(config, text, meta = {}) {
  const imageCfg = config.image_generation || {};
  const model = String(imageCfg.prompt_model || config.chat?.default_model || "gpt-oss:20b").trim();
  const fallback = fallbackPrompt(text);
  if (!model) return fallback;
  try {
    const result = await chatComplete(config, {
      role: "image-prompt",
      model,
      temperature: 0.35,
      timeoutMs: 45000,
      messages: [
        {
          role: "system",
          content: [
            "Voce transforma pedidos de imagem em prompts seguros para geracao.",
            "Nao gere prompt sexual explicito, nudez, genitais, pessoa real, celebridade, menor/aparencia jovem, deepfake ou nudify.",
            "Retorne somente JSON valido.",
          ].join(" "),
        },
        {
          role: "user",
          content: [
            "Converta o pedido em prompt visual nao explicito.",
            "JSON: {\"prompt\":\"...\",\"caption\":\"...\"}",
            `Pedido: ${text}`,
          ].join("\n"),
        },
      ],
      meta,
    });
    const parsed = safeJsonParse(stripJson(result.content), null);
    const prompt = String(parsed?.prompt || "").trim();
    const caption = String(parsed?.caption || "").trim();
    if (!prompt || BLOCKED_PATTERNS.some((pattern) => pattern.test(foldText(prompt)))) return fallback;
    return {
      prompt: prompt.slice(0, 1800),
      caption: caption.slice(0, 320) || "Fiz uma versao segura.",
    };
  } catch (err) {
    activity.publish("image:prompt_error", {
      ...meta,
      error: err.message,
    });
    return fallback;
  }
}

function fallbackPrompt(text) {
  const clean = normalizeText(text || "")
    .replace(/^(red[,:\s]*)?/i, "")
    .trim()
    .slice(0, 900);
  return {
    prompt: [
      "A safe non-explicit fictional visual artwork.",
      clean || "creative abstract red themed image",
      "adult tone only if relevant, no nudity, no explicit sexual content, no real person.",
      "high detail, cinematic lighting, polished composition.",
    ].join(" "),
    caption: "Fiz uma versao segura.",
  };
}

function stripJson(text) {
  const value = String(text || "").trim();
  const fenced = value.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const clean = fenced ? fenced[1].trim() : value;
  const start = clean.indexOf("{");
  const end = clean.lastIndexOf("}");
  return start >= 0 && end > start ? clean.slice(start, end + 1) : clean;
}

async function handleImageRequest({ sock, msg, incoming, prompt, config, sendText }) {
  const imageCfg = config.image_generation || {};
  if (!imageCfg.enabled) return { handled: false };
  const decision = detectImageIntent(prompt || incoming.text);
  if (!decision.is_image_request) return { handled: false };

  const meta = {
    chat_id: incoming.chat_id,
    chat_kind: incoming.kind,
    chat_name: incoming.chat_name,
    sender_name: incoming.sender_name,
    sender_jid: incoming.sender_jid,
  };

  if (!decision.allowed) {
    const text = imageCfg.blocked_text || "Nao vou gerar essa imagem. Posso fazer uma versao ficcional nao explicita.";
    await sendText(sock, incoming.chat_id, text, msg);
    activity.publish("image:blocked", { ...meta, reason: decision.reason, prompt_preview: prompt || incoming.text });
    return { handled: true, blocked: true };
  }

  if (!String(imageCfg.worker_token || "").trim()) {
    await sendText(sock, incoming.chat_id, "O gerador de imagem ainda nao esta com worker configurado.", msg);
    activity.publish("image:disabled", { ...meta, reason: "missing_worker_token" });
    return { handled: true, blocked: false };
  }

  if (store.pendingImageJobCount() >= Number(imageCfg.max_pending_jobs || 20)) {
    await sendText(sock, incoming.chat_id, "A fila de imagens esta cheia agora. Tenta de novo daqui a pouco.", msg);
    activity.publish("image:queue_full", { ...meta });
    return { handled: true, blocked: false };
  }

  const safe = await buildSafePrompt(config, prompt || incoming.text, meta);
  const job = store.createImageJob({
    chat_id: incoming.chat_id,
    requester_jid: incoming.sender_jid,
    requester_name: incoming.sender_name,
    message_id: incoming.id,
    original_prompt: prompt || incoming.text,
    safe_prompt: safe.prompt,
    negative_prompt: NEGATIVE_PROMPT,
    profile: imageCfg.default_profile || "sdxl_lightning",
    width: imageCfg.default_width || 768,
    height: imageCfg.default_height || 768,
    steps: imageCfg.default_steps || 4,
    cfg: imageCfg.default_cfg || 1.5,
    metadata: {
      caption: safe.caption,
      policy: decision,
    },
  });
  await sendText(sock, incoming.chat_id, `${imageCfg.ack_text || "Vou gerar e te mando aqui."}\nJob #${job.id}`, msg);
  activity.publish("image:queued", { ...meta, job_id: job.id, profile: job.profile, prompt_preview: safe.prompt });
  return { handled: true, job };
}

function saveResultImage(jobId, imageBase64, mimeType = "image/png") {
  const safeMime = String(mimeType || "image/png").toLowerCase();
  const ext = safeMime.includes("jpeg") || safeMime.includes("jpg") ? "jpg" : "png";
  const dir = ensureDir(dataPath("generated"));
  const filePath = path.join(dir, `image-job-${Number(jobId)}-${Date.now()}.${ext}`);
  const clean = String(imageBase64 || "").replace(/^data:image\/[a-z0-9.+-]+;base64,/i, "");
  fs.writeFileSync(filePath, Buffer.from(clean, "base64"));
  return filePath;
}

module.exports = {
  detectImageIntent,
  handleImageRequest,
  saveResultImage,
};
