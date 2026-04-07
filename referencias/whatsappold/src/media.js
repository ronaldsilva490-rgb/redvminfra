// ══════════════════════════════════════════════════
// MEDIA — STT, Vision, Download de mídia
// ══════════════════════════════════════════════════
const path = require("path");
const fs = require("fs");

async function transcribeAudio(audioBuffer, mimeType, configs) {
  const sttCfg = configs.stt || {};
  const chatCfg = configs.chat || {};

  let provider = sttCfg.provider || chatCfg.provider || "";
  let apiKey = sttCfg.api_key || chatCfg.api_key || configs.api_key || "";

  // Se ainda assim o provider não for um emissor válido de STT e for red-claude, assume groq padrão e pega a chave correspondente
  if (provider === "red-claude" || provider === "red-perplexity") {
    provider = "groq";
    apiKey = process.env.GROQ_API_KEY || "";
  }

  if (!apiKey || !provider) {
    console.error(
      "[STT] Falha silenciosa prevenida: Sem provider ou api_key para STT.",
    );
    return null;
  }

  try {
    const tmpPath = path.join("/tmp", `audio_${Date.now()}.ogg`);
    fs.writeFileSync(tmpPath, audioBuffer);
    audioBuffer = null;

    let apiUrl = "https://api.groq.com/openai/v1/audio/transcriptions";
    const model =
      sttCfg.model ||
      (provider === "openai" ? "whisper-1" : "whisper-large-v3-turbo");
    if (provider === "openai")
      apiUrl = "https://api.openai.com/v1/audio/transcriptions";

    const fileBytes = fs.readFileSync(tmpPath);
    const blob = new Blob([fileBytes], { type: mimeType || "audio/ogg" });
    const form = new globalThis.FormData();
    form.append("file", blob, "audio.ogg");
    form.append("model", model);
    form.append("language", "pt");
    form.append("response_format", "text");

    const resp = await fetch(apiUrl, {
      method: "POST",
      headers: { Authorization: `Bearer ${apiKey}` },
      body: form,
    });
    try {
      fs.unlinkSync(tmpPath);
    } catch (_) {}

    if (!resp.ok) {
      console.error("[STT] Erro:", await resp.text());
      return null;
    }
    const text = await resp.text();
    console.log(`[STT] ✅ "${text.trim().substring(0, 80)}"`);
    return text.trim();
  } catch (err) {
    console.error("[STT] Exceção:", err.message);
    return null;
  }
}

async function analyzeImage(imageBuffer, caption, configs) {
  const visionCfg = configs.vision || {};
  const provider = visionCfg.provider || "";
  const apiKey = visionCfg.api_key || "";
  const model = visionCfg.model || "";
  if (!apiKey || !provider || !model) return null;

  try {
    let imgData = imageBuffer;
    if (imageBuffer.length > 800_000) {
      try {
        const sharp = require("sharp");
        imgData = await sharp(imageBuffer)
          .resize(800, 800, { fit: "inside", withoutEnlargement: true })
          .jpeg({ quality: 75 })
          .toBuffer();
      } catch (_) {}
    }
    const base64 = imgData.toString("base64");
    imgData = null;
    imageBuffer = null;
    const question = caption
      ? `Caption: "${caption}". Descreva o que vê e comente.`
      : "Descreva detalhadamente.";

    if (provider === "gemini") {
      const geminiUrl = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
      const geminiResp = await fetch(geminiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contents: [
            {
              parts: [
                { inline_data: { mime_type: "image/jpeg", data: base64 } },
                { text: question },
              ],
            },
          ],
        }),
      });
      const geminiData = await geminiResp.json();
      if (geminiData.error) {
        console.error(
          `[VISION-GEMINI] ❌ Erro: ${JSON.stringify(geminiData.error).substring(0, 200)}`,
        );
        return null;
      }
      return geminiData.candidates?.[0]?.content?.parts?.[0]?.text || null;
    }

    let apiUrl = "https://openrouter.ai/api/v1/chat/completions";
    if (provider === "openai")
      apiUrl = "https://api.openai.com/v1/chat/completions";
    if (provider === "nvidia")
      apiUrl = "https://integrate.api.nvidia.com/v1/chat/completions";

    const resp = await fetch(apiUrl, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model,
        messages: [
          {
            role: "user",
            content: [
              {
                type: "image_url",
                image_url: { url: `data:image/jpeg;base64,${base64}` },
              },
              { type: "text", text: question },
            ],
          },
        ],
      }),
    });
    const data = await resp.json();
    return data.choices?.[0]?.message?.content || null;
  } catch (err) {
    console.error("[VISION] Exceção:", err.message);
    return null;
  }
}

module.exports = { transcribeAudio, analyzeImage };
