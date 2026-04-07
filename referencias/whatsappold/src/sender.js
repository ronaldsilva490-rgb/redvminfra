// ══════════════════════════════════════════════════
// SENDER — Envio inteligente de mensagens WhatsApp
// ══════════════════════════════════════════════════
const {
  realtimeStreamState,
  activeStatusMessages,
  sessions,
  contextBuffer,
  STREAM_PRESENCE_REFRESH_MS,
  STREAM_PRESENCE_IDLE_MS,
  STREAM_STATE_RETENTION_MS,
  humanDelay,
} = require("./state");
const { generateAudio } = require("./tts");
const { appendMessageToContextBuffer } = require("./context");

// ── Presence Manager ──
const presenceManager = {
  _active: new Map(),

  async startComposing(sock, jid) {
    if (!sock || !jid) return;
    const current = this._active.get(jid) || { count: 0, timeoutId: null };
    current.count++;
    if (current.timeoutId) clearTimeout(current.timeoutId);
    current.timeoutId = setTimeout(async () => {
      this._active.delete(jid);
      try {
        await sock.sendPresenceUpdate("available", jid);
      } catch (_) {}
    }, 30000);
    this._active.set(jid, current);
    try {
      await sock.sendPresenceUpdate("composing", jid);
    } catch (_) {}
  },

  async stopComposing(sock, jid) {
    if (!sock || !jid) return;
    const current = this._active.get(jid);
    if (current?.timeoutId) clearTimeout(current.timeoutId);
    this._active.delete(jid);
    try {
      await sock.sendPresenceUpdate("available", jid);
    } catch (_) {}
  },

  async withComposing(sock, jid, fn) {
    await this.startComposing(sock, jid);
    try {
      return await fn();
    } finally {
      await this.stopComposing(sock, jid);
    }
  },
};

// ── Stream helpers ──
function streamDataToText(streamData) {
  if (!streamData?.chunks?.length) return "";
  return streamData.chunks
    .map((c) => {
      if (!c || typeof c !== "object") return "";
      if (c.type === "text" && typeof c.content === "string")
        return c.content.trim();
      if (c.type === "heading" && typeof c.content === "string")
        return `*${c.content.trim()}*`;
      if (c.type === "code" && typeof c.content === "string") {
        const lang =
          typeof c.language === "string" && c.language.trim()
            ? c.language.trim()
            : "";
        return lang
          ? `\`\`\`${lang}\n${c.content.trim()}\n\`\`\``
          : `\`\`\`\n${c.content.trim()}\n\`\`\``;
      }
      if (c.type === "list" && Array.isArray(c.items)) {
        return c.items
          .map((item, idx) =>
            c.listType === "ol"
              ? `${idx + 1}. ${String(item).trim()}`
              : `• ${String(item).trim()}`,
          )
          .join("\n")
          .trim();
      }
      if (c.type === "thinking" || c.type === "tool_use") return "";
      return "";
    })
    .filter((v) => v !== undefined && v !== null && v !== "")
    .join("\n\n")
    .trim();
}

function touchRealtimeStreamBuffer(key, streamEvent) {
  if (!key) return;
  const now = Date.now();
  const current = realtimeStreamState.get(key) || {
    text: "",
    updates: 0,
    startedAt: now,
    lastEventAt: now,
    composingLastTouch: now,
    composingInterval: null,
    stopped: false,
  };
  const chunkText = streamDataToText(streamEvent?.data);
  if (chunkText) current.text = chunkText;
  current.updates += 1;
  current.lastEventAt = now;
  current.composingLastTouch = now;
  realtimeStreamState.set(key, current);
}

function startRealtimeComposing(sock, remoteJid, key) {
  if (!sock || !remoteJid || !key) return;
  const existing = realtimeStreamState.get(key);
  if (existing?.stopped) {
    // Sessão anterior encerrou — limpa estado parado para começar do zero
    if (existing.composingInterval) clearInterval(existing.composingInterval);
    realtimeStreamState.delete(key);
  }
  const state = realtimeStreamState.get(key) || {
    text: "",
    updates: 0,
    startedAt: Date.now(),
    lastEventAt: Date.now(),
    composingLastTouch: Date.now(),
    composingInterval: null,
    stopped: false,
  };
  state.composingLastTouch = Date.now();
  const sendComposing = async () => {
    try {
      await sock.sendPresenceUpdate("composing", remoteJid);
    } catch (_) {}
  };
  if (!state.composingInterval) {
    sendComposing();
    state.composingInterval = setInterval(() => {
      const current = realtimeStreamState.get(key);
      if (!current) return;
      if (
        Date.now() - (current.composingLastTouch || 0) >
        STREAM_PRESENCE_IDLE_MS
      ) {
        clearInterval(current.composingInterval);
        current.composingInterval = null;
        sock.sendPresenceUpdate("available", remoteJid).catch(() => {});
        return;
      }
      sendComposing();
    }, STREAM_PRESENCE_REFRESH_MS);
  }
  realtimeStreamState.set(key, state);
}

async function stopRealtimeComposing(sock, remoteJid, key) {
  const state = realtimeStreamState.get(key);
  if (state) {
    state.stopped = true;
    if (state.composingInterval) {
      clearInterval(state.composingInterval);
      state.composingInterval = null;
    }
    const snapshot = { ...state };
    setTimeout(() => {
      const latest = realtimeStreamState.get(key);
      if (!latest) return;
      if (latest.startedAt !== snapshot.startedAt) return;
      realtimeStreamState.delete(key);
    }, STREAM_STATE_RETENTION_MS);
  }
  try {
    await sock.sendPresenceUpdate("available", remoteJid);
  } catch (_) {}
}

function handleRealtimeAIStreamEvent(sock, remoteJid, key, eventData) {
  if (!eventData || !key) return;
  touchRealtimeStreamBuffer(key, eventData);
  if (eventData.action === "NEURAL_STATUS") {
    const tenantId = key.includes("::")
      ? key.split("::")[0]
      : key.split("_")[0];
    handleStatusUpdate(tenantId, remoteJid, eventData.status);
    startRealtimeComposing(sock, remoteJid, key);
  }
  if (eventData.action === "NEURAL_STREAM" || eventData.action === "STREAM_TYPING") {
    startRealtimeComposing(sock, remoteJid, key);
  }
  if (eventData.action === "NEURAL_COMPLETE" || eventData.action === "STREAM_COMPLETE") {
    stopRealtimeComposing(sock, remoteJid, key);
  }
}

// ── Formatting ──
function escapeRegExp(str) {
  return String(str).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function softenSourceReferences(text) {
  const knownLabels = [
    "Pravda em português",
    "Folha de S.Paulo",
    "BBC News Brasil",
    "A Referência",
    "CNN Brasil",
    "Descomplica",
    "Estadão",
    "Reuters",
    "Datafolha",
    "UOL",
    "G1",
  ];
  const sortedLabels = [...knownLabels].sort((a, b) => b.length - a.length);
  return String(text)
    .split("\n")
    .map((rawLine) => {
      let line = rawLine;
      for (const label of sortedLabels) {
        const regex = new RegExp(`(\\s+)(${escapeRegExp(label)})\\s*$`, "i");
        const match = line.match(regex);
        if (!match) continue;
        line = line.replace(regex, ` (_${match[2]}_)`);
        break;
      }
      return line;
    })
    .join("\n");
}

function formatForWhatsApp(text) {
  if (!text) return "";
  let t = String(text);
  t = t.replace(/<br\s*\/?>/gi, "\n");
  t = t.replace(/<\/p>\s*<p>/gi, "\n\n");
  t = t.replace(/<p[^>]*>/gi, "").replace(/<\/p>/gi, "");
  t = t.replace(/<li[^>]*>\s*/gi, "• ").replace(/<\/li>/gi, "\n");
  t = t.replace(/<strong[^>]*>([\s\S]*?)<\/strong>/gi, "*$1*");
  t = t.replace(/<b[^>]*>([\s\S]*?)<\/b>/gi, "*$1*");
  t = t.replace(/<em[^>]*>([\s\S]*?)<\/em>/gi, "_$1_");
  t = t.replace(/<i[^>]*>([\s\S]*?)<\/i>/gi, "_$1_");
  t = t.replace(/<code[^>]*>([\s\S]*?)<\/code>/gi, "```$1```");
  t = t.replace(/<[^>]+>/g, "");
  t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, "$1 ($2)");
  t = t
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
  t = softenSourceReferences(t);
  t = t.replace(/\n{3,}/g, "\n\n");
  return t.trim();
}

// ── Status Premium ──
function formatStatusText(rawStatus) {
  let text = String(rawStatus || "").trim();
  if (!text) return "";
  const lower = text.toLowerCase();
  if (lower.includes("thinking")) text = "💭 Pensando...";
  else if (
    lower.includes("reading file") ||
    lower.includes("reading artifact") ||
    lower.includes("reading document")
  )
    text = "📖 Lendo documento...";
  else if (
    lower.includes("writing document") ||
    lower.includes("creating artifact") ||
    lower.includes("generating")
  )
    text = "📝 Criando documento...";
  else if (lower.includes("executing")) text = "⚙️ Executando código...";
  else if (lower.includes("fetching") || lower.includes("searching"))
    text = "🔍 Buscando informações...";
  else if (lower.includes("error") || lower.includes("failed"))
    text = "⚠️ Houve um pequeno erro, tentando novamente...";
  else if (lower.includes("thought for") || lower.includes("pensou por"))
    text = "✅ Raciocínio concluído";
  const oneLine = text.replace(/\s+/g, " ").trim();
  return oneLine.length > 220 ? oneLine.slice(0, 217) + "..." : oneLine;
}

function normalizeJidForKey(jid) {
  if (!jid) return "";
  let j = String(jid).trim();
  j = j.replace(/@lid$/i, "@s.whatsapp.net");
  j = j.replace(/@broadcast$/i, "");
  if (!j.includes("@")) {
    j =
      j.includes("-") || j.replace(/[^0-9]/g, "").length > 15
        ? `${j}@g.us`
        : `${j}@s.whatsapp.net`;
  }
  return j;
}

async function handleStatusUpdate(tenantId, jid, rawStatus) {
  return;
  if (!rawStatus) return;
  
  // Se o status for silenciador, remove mensagens antigas e ignora
  if (rawStatus === "SILENT" || rawStatus.includes("✅")) {
    const finalJid = normalizeJidForKey(jid);
    const key = `${tenantId}_${finalJid}`;
    const state = activeStatusMessages.get(key);
    if (state) {
        const session = sessions.get(tenantId);
        if (session?.sock) {
            try { await session.sock.sendMessage(String(jid).trim(), { delete: state.key }); } catch (_) {}
        }
        activeStatusMessages.delete(key);
    }
    return;
  }

  const statusText = formatStatusText(rawStatus);
  const sendJid = String(jid).trim();
  const finalJid = normalizeJidForKey(jid);
  const key = `${tenantId}_${finalJid}`;
  const state = activeStatusMessages.get(key);
  const session = sessions.get(tenantId);
  if (!session || !session.sock) {
    const fallbackSession = Array.from(sessions.values()).find(
      (s) => s.tenantId === "admin" || s.tenantId === tenantId,
    );
    if (!fallbackSession || !fallbackSession.sock) return;
    Object.assign(session || {}, fallbackSession);
  }
  const validSock = session?.sock || Array.from(sessions.values())[0]?.sock;
  if (!validSock) return;
  try {
    if (state && state.lastText === statusText) return;
    if (!state) {
      activeStatusMessages.delete(key);
      const sent = await validSock.sendMessage(sendJid, { text: statusText });
      if (sent && sent.key) {
        activeStatusMessages.set(key, {
          key: sent.key,
          lastText: statusText,
          createdAt: Date.now(),
          sendJid,
        });
      }
    } else {
      await validSock.sendMessage(sendJid, {
        edit: state.key,
        text: statusText,
      });
      state.lastText = statusText;
      if (rawStatus.includes("✅") || statusText.includes("✅")) {
        activeStatusMessages.delete(key);
      } else {
        activeStatusMessages.set(key, state);
      }
    }
  } catch (err) {
    console.warn(`[STATUS] Falha ao atualizar: ${err.message}`);
    activeStatusMessages.delete(key);
  }
}

// ── File sending ──
function normalizeIncomingFiles(files) {
  if (!Array.isArray(files)) return [];
  return files
    .filter(
      (f) =>
        (typeof f?.url === "string" && f.url.trim()) ||
        (typeof f?.dataBase64 === "string" && f.dataBase64.trim()),
    )
    .map((f) => ({
      name:
        typeof f?.name === "string" && f.name.trim()
          ? f.name.trim()
          : "arquivo",
      url: typeof f?.url === "string" ? f.url.trim() : "",
      mimeType:
        typeof f?.mimeType === "string" && f.mimeType.trim()
          ? f.mimeType.trim()
          : "application/octet-stream",
      dataBase64: typeof f?.dataBase64 === "string" ? f.dataBase64.trim() : "",
    }));
}

function fileFingerprint(file) {
  const name = (file?.name || "arquivo").trim().toLowerCase();
  const mime = (file?.mimeType || "application/octet-stream")
    .trim()
    .toLowerCase();
  const url = (file?.url || "").trim();
  const b64Len =
    typeof file?.dataBase64 === "string" ? file.dataBase64.length : 0;
  return `${name}|${mime}|${url}|${b64Len}`;
}

async function sendRemoteFilesToWhatsApp(
  sock,
  remoteJid,
  files,
  quotedMsg,
  captionText = "",
) {
  let sentAny = false;
  let captionPending = !!captionText;
  for (const f of files) {
    try {
      let buffer = null;
      if (typeof f?.dataBase64 === "string" && f.dataBase64.trim()) {
        buffer = Buffer.from(f.dataBase64, "base64");
      } else {
        const url = typeof f?.url === "string" ? f.url.trim() : "";
        if (!/^https?:\/\//i.test(url)) continue;
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 30000);
        try {
          const resp = await fetch(url, {
            method: "GET",
            signal: controller.signal,
          });
          clearTimeout(timeoutId);
          if (!resp.ok) continue;
          const arr = await resp.arrayBuffer();
          buffer = Buffer.from(arr);
        } catch (fetchErr) {
          console.warn(
            `[SEND] Timeout ou erro ao baixar arquivo remoto: ${url} - ${fetchErr.message}`,
          );
          continue;
        }
        if (!f?.mimeType) f.mimeType = "application/octet-stream";
        if (!f?.name) {
          try {
            f.name = decodeURIComponent(
              new URL(url).pathname.split("/").filter(Boolean).pop() ||
                "arquivo",
            );
          } catch (_) {
            f.name = "arquivo";
          }
        }
      }
      if (!buffer.length) continue;
      let fileName = typeof f?.name === "string" ? f.name.trim() : "arquivo";
      if (!fileName) fileName = "arquivo";
      const mime = f?.mimeType || "application/octet-stream";
      const message = { document: buffer, fileName, mimetype: mime };
      if (captionPending) {
        message.caption = captionText;
        captionPending = false;
      }
      await sock.sendMessage(remoteJid, message, { quoted: quotedMsg });
      sentAny = true;
    } catch (_) {}
  }
  return sentAny;
}

async function sendSmartResponse(
  sock,
  remoteJid,
  text,
  quotedMsg,
  configs,
  extraOpts = {},
) {
  const attachmentFiles = Array.isArray(extraOpts.files) ? extraOpts.files : [];
  const waText = formatForWhatsApp(text);
  const ttsCfg = configs.tts || {};
  const ttsEnabled = ttsCfg.enabled === true || ttsCfg.enabled === "true";
  const shouldSendAudio =
    ttsEnabled && Math.random() < (parseFloat(ttsCfg.audio_probability) || 0.3);
  const skipPresence = !!extraOpts.skipPresence;

  if (extraOpts.reactKey) {
    try {
      await sock.sendMessage(remoteJid, {
        react: { text: "", key: extraOpts.reactKey },
      });
    } catch (_) {}
  }

  const tenantId = configs.tenant_id;
  const statusMapKey = `${tenantId}_${remoteJid}`;
  const placeholder = activeStatusMessages.get(statusMapKey);
  if (placeholder) activeStatusMessages.delete(statusMapKey);

  const _rawEditKey = extraOpts.editKey || placeholder;
  let resolvedEditKey = null;
  if (_rawEditKey) {
    if (_rawEditKey.id && _rawEditKey.remoteJid !== undefined) {
      resolvedEditKey = { key: _rawEditKey, sendJid: remoteJid };
    } else if (_rawEditKey.key && _rawEditKey.key.id) {
      resolvedEditKey = _rawEditKey;
    }
  }

  // ── PTT flow ──
  if (shouldSendAudio && waText.length < 500 && attachmentFiles.length === 0) {
    if (resolvedEditKey) {
      try {
        await sock.sendMessage(remoteJid, { delete: resolvedEditKey.key });
      } catch (_) {}
    }
    let recordingInterval = null;
    const stopRecording = async () => {
      if (recordingInterval) {
        clearInterval(recordingInterval);
        recordingInterval = null;
      }
      try {
        await sock.sendPresenceUpdate("available", remoteJid);
      } catch (_) {}
    };
    try {
      if (!skipPresence) {
        try {
          await sock.sendPresenceUpdate("recording", remoteJid);
        } catch (_) {}
        recordingInterval = setInterval(async () => {
          try {
            await sock.sendPresenceUpdate("recording", remoteJid);
          } catch (_) {}
        }, 4000);
      }
      let ttsText = waText;
      try {
        const { getAIResponse } = require("./aiProvider");
        const learningCfg = configs.learning || configs.proactive || {};
        if (learningCfg.provider && learningCfg.api_key) {
          const rewriteCfg = {
            ...configs,
            chat: {
              provider: learningCfg.provider,
              api_key: learningCfg.api_key,
              model: learningCfg.model || "",
            },
          };
          const rewritten = await getAIResponse(
            `Reescreva o texto abaixo como se fosse falar em voz alta.\nSem markdown, sem listas, sem emojis. Flua naturalmente, máx 2 frases:\n\n${waText}`,
            rewriteCfg,
            "Responda APENAS com o texto reescrito, sem comentários adicionais.",
          );
          if (rewritten && rewritten.trim().length > 5)
            ttsText = rewritten.trim();
        }
      } catch (_) {}
      const audioBuffer = await generateAudio(ttsText, configs);
      if (audioBuffer) {
        if (!skipPresence) await humanDelay(800 + Math.random() * 1200);
        await stopRecording();
        await sock.sendMessage(
            remoteJid,
            { audio: audioBuffer, mimetype: "audio/ogg; codecs=opus", ptt: true },
            { quoted: quotedMsg },
          );
          appendMessageToContextBuffer(tenantId, remoteJid, "Você (Bot)", waText);
          return;
      }
    } catch (_) {}
    await stopRecording();
  }

  // ── Text flow ──
  if (!skipPresence) {
    try {
      await sock.sendPresenceUpdate("composing", remoteJid);
    } catch (_) {}
  }
  try {
    if (attachmentFiles.length) {
      const sentWithCaption = await sendRemoteFilesToWhatsApp(
        sock,
        remoteJid,
        attachmentFiles,
        quotedMsg,
        waText,
      );
      if (!sentWithCaption && waText) {
        await sock.sendMessage(
          remoteJid,
          { text: waText },
          { quoted: quotedMsg },
        );
        appendMessageToContextBuffer(tenantId, remoteJid, "Você (Bot)", waText);
        await sendRemoteFilesToWhatsApp(
          sock,
          remoteJid,
          attachmentFiles,
          quotedMsg,
          "",
        );
      }
      if (sentWithCaption && waText) {
        appendMessageToContextBuffer(tenantId, remoteJid, "Você (Bot)", waText);
      }
      return;
    }

    if (waText) {
      const _rawEditKey2 = extraOpts.editKey || placeholder;
      let editKey2 = null;
      if (_rawEditKey2) {
        if (_rawEditKey2.id && _rawEditKey2.remoteJid !== undefined)
          editKey2 = { key: _rawEditKey2, sendJid: remoteJid };
        else if (_rawEditKey2.key && _rawEditKey2.key.id)
          editKey2 = _rawEditKey2;
      }
      if (editKey2) {
        try {
          await sock.sendMessage(editKey2.sendJid || remoteJid, {
            edit: editKey2.key,
            text: waText,
          });
          appendMessageToContextBuffer(tenantId, remoteJid, "Você (Bot)", waText);
        } catch (err) {
          await sock.sendMessage(
            remoteJid,
            { text: waText },
            { quoted: quotedMsg },
          );
          appendMessageToContextBuffer(tenantId, remoteJid, "Você (Bot)", waText);
        }
      } else {
        await sock.sendMessage(
          remoteJid,
          { text: waText },
          { quoted: quotedMsg },
        );
        appendMessageToContextBuffer(tenantId, remoteJid, "Você (Bot)", waText);
      }
    }
  } finally {
    try {
      await sock.sendPresenceUpdate("available", remoteJid);
    } catch (_) {}
  }
}

module.exports = {
  presenceManager,
  streamDataToText,
  touchRealtimeStreamBuffer,
  startRealtimeComposing,
  stopRealtimeComposing,
  handleRealtimeAIStreamEvent,
  formatForWhatsApp,
  formatStatusText,
  normalizeJidForKey,
  handleStatusUpdate,
  normalizeIncomingFiles,
  fileFingerprint,
  sendRemoteFilesToWhatsApp,
  sendSmartResponse,
};
