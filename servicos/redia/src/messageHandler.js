const pino = require("pino");
const { downloadMediaMessage, jidDecode } = require("@whiskeysockets/baileys");
const store = require("./store");
const { normalizeText, foldText, stripGroupTrigger } = require("./format");
const { analyzeImage, transcribeAudio } = require("./media");
const { buildChatMessages, detectContextPolicy } = require("./memory");
const { chatStream, chatComplete } = require("./redsystemsClient");
const { sendPresence, sendText, sendSmart, createStreamingResponder } = require("./sender");
const { maybeLearnFromConversation } = require("./learning");
const { maybeProactive } = require("./proactive");
const { getQueue, enqueue, drain } = require("./queue");
const { handleImageRequest } = require("./imageGeneration");
const activity = require("./activity");

const processed = new Map();

function cleanupProcessed() {
  const now = Date.now();
  for (const [key, ts] of processed) {
    if (now - ts > 10 * 60 * 1000) processed.delete(key);
  }
}
setInterval(cleanupProcessed, 5 * 60 * 1000).unref?.();

function unwrapMessage(message) {
  if (!message) return {};
  if (message.ephemeralMessage?.message) return unwrapMessage(message.ephemeralMessage.message);
  if (message.viewOnceMessageV2?.message) return unwrapMessage(message.viewOnceMessageV2.message);
  if (message.viewOnceMessage?.message) return unwrapMessage(message.viewOnceMessage.message);
  return message;
}

function messageType(message) {
  return Object.keys(message || {})[0] || "";
}

function extractText(message) {
  const msg = unwrapMessage(message);
  const type = messageType(msg);
  return normalizeText(
    msg.conversation ||
      msg.extendedTextMessage?.text ||
      msg.imageMessage?.caption ||
      msg.videoMessage?.caption ||
      msg.documentMessage?.caption ||
      msg.buttonsResponseMessage?.selectedButtonId ||
      msg.listResponseMessage?.singleSelectReply?.selectedRowId ||
      msg[type]?.text ||
      msg[type]?.caption ||
      "",
  ).trim();
}

function extractContextInfo(message) {
  const msg = unwrapMessage(message);
  const type = messageType(msg);
  return (
    msg.extendedTextMessage?.contextInfo ||
    msg.imageMessage?.contextInfo ||
    msg.videoMessage?.contextInfo ||
    msg.audioMessage?.contextInfo ||
    msg.documentMessage?.contextInfo ||
    msg[type]?.contextInfo ||
    {}
  );
}

function findQuotedStoredText(chatId, stanzaId) {
  const quotedId = String(stanzaId || "").trim();
  if (!chatId || !quotedId) return "";
  try {
    const rows = store.recentMessages(chatId, 120);
    for (const row of rows.slice().reverse()) {
      const keys = Array.isArray(row.metadata?.whatsapp_keys) ? row.metadata.whatsapp_keys : [];
      if (keys.some((key) => String(key?.id || "") === quotedId)) return String(row.text || "").trim();
      if (String(row.id || "").endsWith(quotedId)) return String(row.text || "").trim();
    }
  } catch {
    // best effort lookup
  }
  return "";
}

function extractQuotedContext(contextInfo, bot, chatId) {
  const quotedMessage = contextInfo?.quotedMessage || null;
  const quotedText = quotedMessage ? extractText(quotedMessage) : "";
  const quotedId = String(contextInfo?.stanzaId || contextInfo?.quotedStanzaId || "").trim();
  const storedText = quotedText ? "" : findQuotedStoredText(chatId, quotedId);
  const text = normalizeText(quotedText || storedText).trim();
  if (!text && !quotedId) return null;
  return {
    id: quotedId,
    sender_jid: String(contextInfo?.participant || ""),
    from_bot: isReplyToBot(contextInfo, bot),
    text: text.slice(0, 1800),
  };
}

function promptWithQuotedContext(prompt, quoted) {
  const userText = String(prompt || "").trim();
  if (!quoted?.text) return userText;
  const author = quoted.from_bot ? "REDIA" : "outra pessoa";
  return [
    "O usuario esta respondendo a uma mensagem citada no WhatsApp.",
    `Mensagem citada de ${author}: ${quoted.text}`,
    `Resposta do usuario: ${userText || "(sem texto)"}`,
    "Responda levando em conta a mensagem citada. Se ele disse que nao entendeu, explique essa mensagem de forma simples e curta.",
  ].join("\n");
}

function botIdentifiers(sock) {
  const userId = sock.user?.id || "";
  const decoded = userId ? jidDecode(userId) : null;
  const number = decoded?.user || String(userId).split("@")[0].split(":")[0];
  const lid = sock.user?.lid || "";
  const lidShort = String(lid).split("@")[0].split(":")[0];
  return { userId, number, lid, lidShort };
}

function isMentioned(contextInfo, bot) {
  const mentioned = contextInfo?.mentionedJid || [];
  return mentioned.some((jid) => {
    const value = String(jid || "");
    return (bot.number && value.includes(bot.number)) || (bot.lidShort && value.includes(bot.lidShort));
  });
}

function isReplyToBot(contextInfo, bot) {
  const participant = String(contextInfo?.participant || "");
  return (bot.number && participant.includes(bot.number)) || (bot.lidShort && participant.includes(bot.lidShort));
}

function shouldRespond({ config, conversation, text, contextInfo, bot }) {
  if (!config.chat?.enabled) return { ok: false, prompt: "" };
  if (conversation.kind !== "group") {
    return config.chat.private_mode === "never" ? { ok: false, prompt: "" } : { ok: true, prompt: text };
  }
  const mode = config.chat.group_mode || "prefix_or_mention";
  if (mode === "never") return { ok: false, prompt: "" };
  if (mode === "always") return { ok: true, prompt: text };
  const mentioned = isMentioned(contextInfo, bot) || isReplyToBot(contextInfo, bot);
  const stripped = stripGroupTrigger(text, config.chat.group_prefix || "red", mentioned);
  return { ok: stripped.triggered, prompt: stripped.prompt || text };
}

function isRecent(msg, config) {
  const ts = Number(msg.messageTimestamp || 0) * 1000;
  if (!ts) return true;
  return Date.now() - ts <= (config.whatsapp?.ignore_old_messages_ms || 120000);
}

function modelCandidates(config, conversation) {
  const ordered = [
    conversation.model,
    config.chat.default_model,
    ...(Array.isArray(config.chat.fallback_models) ? config.chat.fallback_models : []),
  ];
  return [...new Set(ordered.map((item) => String(item || "").trim()).filter(Boolean))];
}

function rememberParticipantProfile(senderJid, senderName) {
  const jid = String(senderJid || "").trim();
  const name = normalizeText(senderName || "").trim();
  if (!jid.includes("@") || !name) return;
  const jidUser = jid.split("@")[0].split(":")[0];
  if (name === jid || name === jidUser) return;
  store.upsertProfile({
    contact_jid: jid,
    name,
    nicknames: [name],
  });
}

async function enrichWithMedia(sock, msg, baseText, config, meta = {}) {
  const raw = unwrapMessage(msg.message);
  const type = messageType(raw);
  const isAudio = type === "audioMessage";
  const isImage = type === "imageMessage";
  const isDocument = type === "documentMessage";
  if (!isAudio && !isImage && !isDocument) return { text: baseText, metadata: {} };

  const buffer = await downloadMediaMessage(
    msg,
    "buffer",
    {},
    { logger: pino({ level: "silent" }), reuploadRequest: sock.updateMediaMessage },
  );
  const mediaPayload = raw[type] || {};
  const mimeType = mediaPayload.mimetype || "application/octet-stream";
  const fileName = mediaPayload.fileName || `${type}_${Date.now()}`;

  if (isAudio) {
    const transcription = await transcribeAudio(buffer, mimeType, config, meta);
    return {
      text: [baseText, transcription ? `[Audio transcrito] ${transcription}` : "[Audio recebido sem transcricao]"]
        .filter(Boolean)
        .join("\n"),
      metadata: { media_type: "audio", mime_type: mimeType, transcription },
    };
  }

  if (isImage) {
    const description = await analyzeImage(buffer, baseText, config, meta);
    return {
      text: [baseText, description ? `[Imagem analisada] ${description}` : "[Imagem recebida]"].filter(Boolean).join("\n"),
      metadata: { media_type: "image", mime_type: mimeType, description },
    };
  }

  return {
    text: [baseText, `[Documento recebido] ${fileName}`].filter(Boolean).join("\n"),
    metadata: { media_type: "document", mime_type: mimeType, file_name: fileName },
  };
}

async function runAiForMessage({ sock, msg, conversation, incoming, prompt, config }) {
  const jid = conversation.chat_id;
  const models = modelCandidates(config, conversation);
  const activityMeta = {
    chat_id: jid,
    chat_kind: conversation.kind,
    chat_name: conversation.name,
    sender_name: incoming.sender_name,
    sender_jid: incoming.sender_jid,
  };
  let lastError = null;

  for (const model of models) {
    const messages = buildChatMessages({
      config,
      conversation,
      prompt,
      senderName: incoming.sender_name,
      senderJid: incoming.sender_jid,
      model,
    });
    const contextPolicy = detectContextPolicy(prompt, config);
    const promptChars = messages.reduce((sum, item) => sum + String(item.content || "").length, 0);
    const started = Date.now();
    try {
      activity.publish("chat:attempt", {
        ...activityMeta,
        model,
        context_policy: contextPolicy.mode,
        prompt_chars: promptChars,
        prompt_preview: prompt,
      });
      await sendPresence(sock, jid, "composing");
      let result;
      let sentMessages = [];
      if (config.streaming?.enabled && config.streaming?.edit_first_message) {
        const responder = await createStreamingResponder(sock, jid, config, msg);
        result = await chatStream(config, {
          role: "chat",
          model,
          messages,
          meta: activityMeta,
          onToken: async (_token, fullText) => responder.update(fullText),
        });
        sentMessages = await responder.finish(result.content);
      } else {
        result = await chatComplete(config, { role: "chat", model, messages, meta: activityMeta });
        sentMessages = await sendSmart(sock, jid, result.content, config, msg);
      }
      activity.publish("whatsapp:sent", {
        ...activityMeta,
        model: result.model || model,
        response_chars: result.content.length,
        response_preview: result.content,
      });
      store.saveModelRun({
        role: "chat",
        model: result.model || model,
        prompt_chars: promptChars,
        response_chars: result.content.length,
        latency_ms: result.latency_ms || Date.now() - started,
        ok: true,
      });
      store.appendMessage({
        id: `${jid}:assistant:${Date.now()}`,
        chat_id: jid,
        role: "assistant",
        direction: "outgoing",
        sender_name: "REDIA",
        text: result.content,
        content_type: "text",
        metadata: {
          whatsapp_keys: (sentMessages || []).map((item) => ({
            id: item?.key?.id || "",
            remote_jid: item?.key?.remoteJid || "",
            from_me: !!item?.key?.fromMe,
          })),
        },
      });
      return result.content;
    } catch (err) {
      lastError = err;
      activity.publish("chat:error", {
        ...activityMeta,
        model,
        error: err.message,
      });
      store.saveModelRun({
        role: "chat",
        model,
        prompt_chars: promptChars,
        response_chars: 0,
        latency_ms: Date.now() - started,
        ok: false,
        error: err.message,
      });
    } finally {
      await sendPresence(sock, jid, "available");
    }
  }
  throw lastError || new Error("Nenhum modelo respondeu.");
}

async function processOne({ sock, msg, incoming, prompt, config }) {
  const conversation = store.ensureConversation(incoming.chat_id, {
    kind: incoming.kind,
    name: incoming.chat_name,
  });
  const image = await handleImageRequest({ sock, msg, incoming, prompt, config, sendText });
  if (image.handled) return "";
  const text = await runAiForMessage({ sock, msg, conversation, incoming, prompt, config });
  return text;
}

async function processQueue({ sock, chatId, config }) {
  const state = getQueue(chatId);
  if (state.processing) return;
  state.processing = true;
  try {
    let items = drain(chatId);
    while (items.length) {
      activity.publish("queue:drain", {
        chat_id: chatId,
        count: items.length,
        combined: items.length > 1,
      });
      const item =
        items.length === 1
          ? items[0]
          : {
              ...items[0],
              prompt: `O usuario enviou varias mensagens em sequencia:\n${items
                .map((entry, index) => `${index + 1}. ${entry.incoming.sender_name || "usuario"}: ${entry.prompt}`)
                .join("\n")}\n\nResponda considerando tudo como uma conversa fluida.`,
            };
      await processOne({ sock, msg: item.msg, incoming: item.incoming, prompt: item.prompt, config });
      items = drain(chatId);
    }
  } finally {
    state.processing = false;
  }
}

function setupMessageHandler(sock) {
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    const config = store.getConfig();
    const bot = botIdentifiers(sock);

    for (const msg of messages) {
      if (!msg.message) continue;
      const chatId = msg.key.remoteJid;
      if (!chatId || chatId === "status@broadcast" || chatId.endsWith("@broadcast")) continue;
      const id = msg.key.id || `${chatId}:${msg.messageTimestamp || Date.now()}`;
      const dedup = `${chatId}:${id}`;
      if (processed.has(dedup)) continue;
      processed.set(dedup, Date.now());
      if (!isRecent(msg, config)) continue;

      const kind = chatId.endsWith("@g.us") ? "group" : "private";
      let baseText = extractText(msg.message);
      const contextInfo = extractContextInfo(msg.message);
      const senderJid = msg.key.participant || chatId;
      const senderName = msg.pushName || senderJid.split("@")[0];
      rememberParticipantProfile(senderJid, senderName);
      const quoted = extractQuotedContext(contextInfo, bot, chatId);

      let enriched;
      try {
        enriched = await enrichWithMedia(sock, msg, baseText, config, {
          chat_id: chatId,
          chat_kind: kind,
          sender_name: senderName,
          sender_jid: senderJid,
        });
      } catch (err) {
        enriched = { text: baseText || "[Midia recebida, mas nao consegui processar]", metadata: { media_error: err.message } };
        activity.publish("media:error", {
          chat_id: chatId,
          chat_kind: kind,
          sender_name: senderName,
          sender_jid: senderJid,
          error: err.message,
        });
      }
      const text = normalizeText(enriched.text || baseText).trim();
      if (!text) continue;

      const conversation = store.ensureConversation(chatId, { kind, name: kind === "group" ? chatId : senderName });
      const incoming = {
        id,
        chat_id: chatId,
        kind,
        chat_name: conversation.name || (kind === "group" ? chatId : senderName),
        sender_jid: senderJid,
        sender_name: senderName,
        text,
        metadata: {
          ...enriched.metadata,
          from_me: !!msg.key.fromMe,
          mentioned: isMentioned(contextInfo, bot),
          reply_to_bot: isReplyToBot(contextInfo, bot),
          quoted_message_id: quoted?.id || "",
          quoted_sender_jid: quoted?.sender_jid || "",
          quoted_from_bot: !!quoted?.from_bot,
          quoted_text: quoted?.text || "",
        },
      };

      store.appendMessage({
        id,
        chat_id: chatId,
        kind,
        chat_name: incoming.chat_name,
        role: msg.key.fromMe ? "assistant" : "user",
        direction: msg.key.fromMe ? "outgoing" : "incoming",
        sender_jid: senderJid,
        sender_name: senderName,
        text,
        metadata: incoming.metadata,
      });

      activity.publish("whatsapp:message", {
        chat_id: chatId,
        chat_kind: kind,
        chat_name: incoming.chat_name,
        sender_name: senderName,
        sender_jid: senderJid,
        from_me: !!msg.key.fromMe,
        media_type: enriched.metadata?.media_type || "text",
        text_preview: text,
        quoted_preview: quoted?.text || "",
      });

      if (msg.key.fromMe) continue;

      maybeLearnFromConversation(config, store.getConversation(chatId)).catch((err) => {
        console.warn("[learn]", err.message);
      });

      if (config.whatsapp?.mark_read) {
        try {
          await sock.readMessages([msg.key]);
        } catch {
          // best effort
        }
      }

      const decision = shouldRespond({ config, conversation, text, contextInfo, bot });
      activity.publish(decision.ok ? "whatsapp:decision" : "whatsapp:ignored", {
        chat_id: chatId,
        chat_kind: kind,
        chat_name: incoming.chat_name,
        sender_name: senderName,
        prompt_preview: decision.prompt || text,
      });
      maybeProactive(config, conversation, incoming, async (proactiveText) => {
        await sendSmart(sock, chatId, proactiveText, config, null, { forceText: false });
        activity.publish("whatsapp:sent", {
          chat_id: chatId,
          chat_kind: kind,
          chat_name: incoming.chat_name,
          sender_name: "REDIA",
          response_chars: proactiveText.length,
          response_preview: proactiveText,
          proactive: true,
        });
        store.appendMessage({
          chat_id: chatId,
          role: "assistant",
          direction: "outgoing",
          sender_name: "REDIA",
          text: proactiveText,
          content_type: "text",
          metadata: { proactive: true },
        });
      }).catch((err) => console.warn("[proactive]", err.message));

      if (!decision.ok) continue;

      enqueue(chatId, { msg, incoming, prompt: promptWithQuotedContext(decision.prompt || text, quoted) });
      processQueue({ sock, chatId, config }).catch(async (err) => {
        console.error("[message]", err);
        await sendSmart(sock, chatId, "Nao consegui responder agora. Vou tentar de novo na proxima mensagem.", config, msg, { forceText: true }).catch(() => {});
      });
    }
  });
}

module.exports = { setupMessageHandler };
