// ══════════════════════════════════════════════════
// AI PROVIDER — Roteador multi-provider de IA
// ══════════════════════════════════════════════════

const {
  eventEmitter,
  activeRedRequests,
  jidProcessingState,
  waSessionDispatchState,
  activeStatusMessages,
} = require("./state");
const { getProxySocket, WebSocket } = require("./proxy");
const { clearJidTimeouts } = require("./queue");
const {
  streamDataToText,
  normalizeJidForKey,
  handleStatusUpdate,
} = require("./sender");

function sanitizeJidForSession(jid) {
  if (!jid) return "default";
  return jid.replace(/@[\w.]+/g, "").replace(/[^a-zA-Z0-9_-]/g, "_");
}

async function getAIResponse(
  prompt,
  configs,
  overrideSystemPrompt = null,
  options = {},
) {
  const chatCfg = configs.chat || {};
  const incomingFiles = Array.isArray(options?.files) ? options.files : [];

  const isInternalAnalysis = !!(
    overrideSystemPrompt &&
    (overrideSystemPrompt.includes("JSON") ||
      overrideSystemPrompt.includes("Analista interno") ||
      overrideSystemPrompt.includes("Responda APENAS") ||
      overrideSystemPrompt.includes("JSON puro"))
  );

  const learningCfg = configs.learning || {};
  const proactiveCfg2 = configs.proactive || {};
  const instanceId = chatCfg.red_instance_id || configs.red_instance_id;
  const isRedProxyForced = !!instanceId && !isInternalAnalysis;

  let provider, apiKey, model;
  if (isInternalAnalysis) {
    provider =
      learningCfg.provider || proactiveCfg2.provider || chatCfg.provider || "";
    apiKey =
      learningCfg.api_key ||
      proactiveCfg2.api_key ||
      chatCfg.api_key ||
      configs.api_key ||
      "";
    model =
      learningCfg.model ||
      proactiveCfg2.model ||
      chatCfg.model ||
      configs.model ||
      "";
    if (provider === "red-claude" || provider === "red-perplexity") {
      provider = proactiveCfg2.provider || "";
      apiKey = proactiveCfg2.api_key || "";
      model = proactiveCfg2.model || "";
    }
  } else if (isRedProxyForced) {
    // Mantém o provider original (red-claude OU red-perplexity) vindo da config
    provider = chatCfg.provider || "red-claude";
    apiKey = chatCfg.api_key || configs.api_key || "";
    model = chatCfg.model || configs.model || "";
  } else {
    provider = chatCfg.provider || configs.ai_provider || "";
    apiKey = chatCfg.api_key || configs.api_key || "";
    model = chatCfg.model || configs.model || "";
  }

  const systemPrompt =
    overrideSystemPrompt ??
    chatCfg.system_prompt ??
    configs.system_prompt ??
    "";

  const _logPrefix = isInternalAnalysis ? "[AI-INTERNAL]" : "[AI-CHAT]";
  console.log(
    `${_logPrefix} 🔌 Provider: ${provider} | Model: ${model || "⚠️ VAZIO"} | Prompt: ${prompt.length} chars | System: ${systemPrompt.length} chars`,
  );
  if (!model)
    console.warn(
      `${_logPrefix} ⚠️ MODELO NÃO CONFIGURADO — Provider: ${provider || "(nenhum)"}`,
    );
  if (!provider) {
    console.error(
      `${_logPrefix} ❌ PROVIDER NÃO CONFIGURADO! Configure no painel de admin.`,
    );
    return options?.includeMeta ? { text: null, files: [] } : null;
  }

  // ── RED Proxy (Claude ou Perplexity) ──
  if (provider === "red-claude" || provider === "red-perplexity") {
    const _redLabel =
      provider === "red-perplexity" ? "RED-PERPLEXITY" : "RED-CLAUDE";
    if (!instanceId) {
      console.error(
        `[AI-DEBUG] ${_redLabel} selecionado mas red_instance_id não encontrado. Abortando.`,
      );
      return null;
    }

    const jidSuffix = sanitizeJidForSession(options?.conversationId || "");
    const sessionId =
      jidSuffix && jidSuffix !== "default"
        ? `WA_${configs.tenant_id || "default"}_${jidSuffix}`
        : `WA_${configs.tenant_id || "default"}`;

    if (activeRedRequests.has(sessionId)) {
      console.warn(`[AI-${_redLabel}] ⚠️ ${sessionId} travado — limpando.`);
      activeRedRequests.delete(sessionId);
    }

    const proxySocket = getProxySocket();
    return new Promise((resolve) => {
      if (!proxySocket || proxySocket.readyState !== WebSocket.OPEN) {
        console.error(
          "[AI-DEBUG] Proxy RED não está conectado (readyState=" +
            (proxySocket ? proxySocket.readyState : "null") +
            "). Retornando nulo.",
        );
        return resolve(null);
      }

      activeRedRequests.add(sessionId);
      let finished = false;

      const cleanup = () => {
        activeRedRequests.delete(sessionId);
        eventEmitter.off("proxy_message", responseHandler);
      };

      const responseHandler = (data) => {
        if (data.sessionId !== sessionId) return;

        // Repassa eventos de stream para o callback (necessário para typing no WhatsApp)
        if (options.onStream && (data.action === "NEURAL_STREAM" || data.action === "NEURAL_STATUS" || data.action === "STREAM_TYPING")) {
          options.onStream(data);
        }

        // Suporta NEURAL_COMPLETE ou STREAM_COMPLETE para finalizar a sessão
        if (data.action !== "NEURAL_COMPLETE" && data.action !== "STREAM_COMPLETE") return;

        if (finished) return;
        finished = true;
        cleanup();

        let text = typeof data.text === "string" ? data.text : "";
        let files = [];

        if (Array.isArray(data.files)) {
          files = data.files
            .filter(
              (f) =>
                (typeof f?.url === "string" && f.url) ||
                (typeof f?.dataBase64 === "string" && f.dataBase64),
            )
            .map((f) => ({
              name: typeof f.name === "string" ? f.name : "arquivo",
              url: typeof f.url === "string" ? f.url : "",
              mimeType:
                typeof f.mimeType === "string"
                  ? f.mimeType
                  : "application/octet-stream",
              dataBase64: typeof f.dataBase64 === "string" ? f.dataBase64 : "",
            }));
        }

        if (!text && data?.data?.chunks?.length)
          text = streamDataToText(data.data);

        let editKey = null;
        const parts = sessionId.replace("WA_", "").split("_");
        if (parts.length >= 2) {
          const tenantId = parts[0];
          const remoteJid = parts.slice(1).join("_");
          const finalJid = normalizeJidForKey(remoteJid);
          const statusKey = `${tenantId}_${finalJid}`;
          const statusData = activeStatusMessages.get(statusKey);
          if (statusData && statusData.key) {
            activeStatusMessages.delete(statusKey);
            editKey = statusData.key;
          }
        }

        if (options?.includeMeta) {
          console.log(
            `[AI-DEBUG] Resolvendo Promise com includeMeta=true. Text Length: ${(text || "").length}, Files: ${files.length}`,
          );
          resolve({ text: text || null, files, editKey });
        } else {
          console.log(
            `[AI-DEBUG] Resolvendo Promise com includeMeta=false. Text Length: ${(text || "").length}`,
          );
          resolve(text || null);
        }
      };

      eventEmitter.on("proxy_message", responseHandler);

      const sessionState = waSessionDispatchState.get(sessionId);
      const shouldSendPersona = !sessionState || !sessionState.personaSent;

      // Se for a primeira vez ou a sessão foi resetada, manda o Persona. 
      // Caso contrário, manda apenas o prompt (que já tem o histórico recente).
      const proxyText = (shouldSendPersona && systemPrompt)
        ? `${systemPrompt}\n\n${prompt}`
        : prompt;

      // Marca que o persona já foi enviado para economizar tokens nas próximas
      if (sessionState && shouldSendPersona) {
        sessionState.personaSent = true;
      }

      const t0 = Date.now();
      console.log(
        `[AI-DEBUG] [${t0}] Enviando REGISTER_SESSION para ${sessionId}${shouldSendPersona ? " (com Persona)" : " (sem Persona)"}`,
      );
      const t1 = Date.now();
      console.log(
        `[AI-DEBUG] [${t1}] Enviando START_NEURAL_LINK para ${sessionId} — aguardando STREAM_COMPLETE`,
      );
      proxySocket.send(
        JSON.stringify({
          action: "START_NEURAL_LINK",
          text: proxyText,
          instanceId: instanceId,
          sessionId: sessionId,
          timestamp: t1,
          files: incomingFiles.map((f) => ({
            name: f.name,
            type: f.mimeType,
            data: `data:${f.mimeType};base64,${f.dataBase64}`,
          })),
        }),
      );

      setTimeout(() => {
        if (finished) return;
        finished = true;
        cleanup();
        console.error(
          `[AI-${_redLabel}] ⏰ Timeout 180s sem resposta para ${sessionId}`,
        );
        try {
          const [tid] = sessionId.replace(/^WA_/, "").split(/_|::/);
          for (const [key, st] of jidProcessingState) {
            if (key.startsWith(tid) && st.processing) {
              clearJidTimeouts(st);
              st.processing = false;
              st.awaitingUserConfirm = false;
              st.queue = [];
            }
          }
        } catch (_) {}
        resolve(options?.includeMeta ? { text: null, files: [] } : null);
      }, 180000);
    });
  }

  // ── Standard providers ──
  if (!apiKey && provider !== "ollama") {
    return options?.includeMeta ? { text: null, files: [] } : null;
  }

  try {
    if (provider === "gemini") {
      console.log(`[AI-GEMINI] 📡 Requisição → ${model}`);
      const geminiUrl = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
      const geminiBody = {
        ...(systemPrompt
          ? { system_instruction: { parts: [{ text: systemPrompt }] } }
          : {}),
        contents: [{ role: "user", parts: [{ text: prompt }] }],
      };
      const geminiResp = await fetch(geminiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(geminiBody),
      });
      const geminiData = await geminiResp.json();
      if (geminiData.error) {
        console.error(
          `[AI-GEMINI] ❌ Erro: ${JSON.stringify(geminiData.error).substring(0, 200)}`,
        );
        return options?.includeMeta ? { text: null, files: [] } : null;
      }
      const out = geminiData.candidates?.[0]?.content?.parts?.[0]?.text || null;
      console.log(
        `[AI-GEMINI] ✅ Resposta recebida (${(out || "").length} chars)`,
      );
      return options?.includeMeta ? { text: out, files: [] } : out;
    }

    let apiUrl = "";
    if (provider === "groq")
      apiUrl = "https://api.groq.com/openai/v1/chat/completions";
    else if (provider === "openrouter")
      apiUrl = "https://openrouter.ai/api/v1/chat/completions";
    else if (provider === "nvidia")
      apiUrl = "https://integrate.api.nvidia.com/v1/chat/completions";
    else if (provider === "openai")
      apiUrl = "https://api.openai.com/v1/chat/completions";
    else if (provider === "kimi" || provider === "moonshot")
      apiUrl = "https://api.moonshot.ai/v1/chat/completions";
    else if (provider === "deepseek")
      apiUrl = "https://api.deepseek.com/v1/chat/completions";
    else if (provider === "ollama") {
      const ollamaUrl =
        process.env.OLLAMA_PROXY_URL || "http://localhost:11434";
      apiUrl = `${ollamaUrl}/v1/chat/completions`;
    } else return null;

    const resp = await fetch(apiUrl, {
      method: "POST",
      headers: {
        ...(provider !== "ollama" ? { Authorization: `Bearer ${apiKey}` } : {}),
        "Content-Type": "application/json",
        "HTTP-Referer": "https://redcomercial.com.br",
        "X-Title": "Red Comercial AI",
      },
      body: JSON.stringify({
        model,
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: prompt },
        ],
        max_tokens: 1024,
        temperature: 0.88,
      }),
    });
    const data = await resp.json();
    if (data.error) {
      console.error(
        `[AI-${provider.toUpperCase()}] ❌ Erro: ${JSON.stringify(data.error).substring(0, 200)}`,
      );
      return options?.includeMeta ? { text: null, files: [] } : null;
    }
    const out = data.choices?.[0]?.message?.content || null;
    return options?.includeMeta ? { text: out, files: [] } : out;
  } catch (err) {
    console.error(`[AI] Exceção (${provider}):`, err.message);
    return options?.includeMeta ? { text: null, files: [] } : null;
  }
}

module.exports = { getAIResponse, sanitizeJidForSession };
