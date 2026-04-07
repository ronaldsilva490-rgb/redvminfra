// ══════════════════════════════════════════════════
// MESSAGE HANDLER — Listener principal de mensagens
// ══════════════════════════════════════════════════
const pino = require("pino");
const { downloadMediaMessage } = require("@whiskeysockets/baileys");
const { jidDecode } = require("@whiskeysockets/baileys");
const {
  supabase,
  sessions,
  conversationBuffers,
  waSessionDispatchState,
  sessionContextSent,
  activeRedRequests,
  lastProactiveTime,
  lastBotResponseByJid,
  processedMessageIds,
  normalize,
  getCfg,
  trackGroupActivity,
  isRecentMessage,
  streamStateKey,
  humanDelay,
  DEFAULT_BUFFER_SIZE,
  ADMIN_TENANT_ID,
  realtimeStreamState,
  activeStatusMessages,
} = require("./state");
const { loadTenantAIConfigs } = require("./config");
const { transcribeAudio, analyzeImage } = require("./media");
const { getAIResponse, sanitizeJidForSession } = require("./aiProvider");
const {
  presenceManager,
  sendSmartResponse,
  startRealtimeComposing,
  stopRealtimeComposing,
  handleRealtimeAIStreamEvent,
  handleStatusUpdate,
  fileFingerprint,
  formatForWhatsApp,
  normalizeJidForKey,
} = require("./sender");
const { getJidState, clearJidTimeouts } = require("./queue");
const { pickReaction, sendReaction, sendSticker } = require("./stickers");
const {
  learnFromConversation,
  realtimeProactiveAnalysis,
} = require("./proactive");
const {
  resolveNames,
  getTenantContext,
  getGroupPersonality,
  detectSimpleIntent,
  buildContextBlock,
  appendMessageToContextBuffer,
} = require("./context");
const { getContactMemory } = require("./memory");

function setupMessageHandler(sock, tenantId) {
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;

    const botJid = sock.user?.id || "";
    const botNumber = jidDecode(botJid)?.user + "@s.whatsapp.net";
    const botLid = sock.user?.lid || "";
    const botId = botNumber.split("@")[0].split(":")[0];
    const botLidShort = botLid.split("@")[0].split(":")[0];

    for (const msg of messages) {
      if (!msg.message || msg.key.fromMe) continue;

      if (!isRecentMessage(msg)) {
        console.log(
          `[SKIP] Mensagem antiga ignorada (${new Date((msg.messageTimestamp || 0) * 1000).toLocaleTimeString()})`,
        );
        continue;
      }

      const dedupKey = `${tenantId}_${msg.key.id}`;
      if (processedMessageIds.has(dedupKey)) {
        console.log(
          `[DEDUP] ⏭️ ${msg.key.id} já processado — ignorando re-entrega do Baileys`,
        );
        continue;
      }
      processedMessageIds.set(dedupKey, Date.now());

      const remoteJid = msg.key.remoteJid;
      if (
        remoteJid === "status@broadcast" ||
        remoteJid.endsWith("@broadcast")
      ) {
        console.log(
          `[SKIP] Status/story ignorado de ${msg.pushName || remoteJid}`,
        );
        continue;
      }

      const isGroup = remoteJid.endsWith("@g.us");
      const isPV = !isGroup;

      const msgType = Object.keys(msg.message)[0];
      let textContent = "";
      let mediaContent = null;

      if (msgType === "conversation") textContent = msg.message.conversation;
      else if (msgType === "extendedTextMessage")
        textContent = msg.message.extendedTextMessage.text;
      else if (msgType === "buttonsResponseMessage")
        textContent = msg.message.buttonsResponseMessage.selectedButtonId;
      else if (msgType === "listResponseMessage")
        textContent =
          msg.message.listResponseMessage.singleSelectReply.selectedRowId;
      else if (msg.message[msgType]?.text)
        textContent = msg.message[msgType].text;
      else if (msg.message[msgType]?.caption)
        textContent = msg.message[msgType].caption;

      const isAudio = msgType === "audioMessage";
      const isImage =
        msgType === "imageMessage" ||
        (msgType === "viewOnceMessageV2" &&
          msg.message.viewOnceMessageV2?.message?.imageMessage);
      const isDocument = msgType === "documentMessage";
      const isVideo =
        msgType === "videoMessage" ||
        (msgType === "viewOnceMessageV2" &&
          msg.message.viewOnceMessageV2?.message?.videoMessage);

      const incomingFiles = [];

      const contextInfo =
        msg.message?.extendedTextMessage?.contextInfo ||
        msg.message?.imageMessage?.contextInfo ||
        msg.message?.audioMessage?.contextInfo ||
        msg.message?.documentMessage?.contextInfo ||
        msg.message?.videoMessage?.contextInfo ||
        msg.message?.ephemeralMessage?.message?.extendedTextMessage
          ?.contextInfo ||
        msg.message?.viewOnceMessageV2?.message?.imageMessage?.contextInfo ||
        msg.message?.viewOnceMessageV2?.message?.videoMessage?.contextInfo;

      const isMentioned = !!contextInfo?.mentionedJid?.some(
        (jid) =>
          jid.includes(botId) || (botLidShort && jid.includes(botLidShort)),
      );
      const isReplyToMe = !!(
        contextInfo?.participant?.includes(botId) ||
        (botLidShort && contextInfo?.participant?.includes(botLidShort))
      );

      const session = sessions.get(tenantId);
      if (Date.now() - (session.lastConfigRefresh || 0) > 10000) {
        session.lastConfigRefresh = Date.now();
        loadTenantAIConfigs(tenantId).catch(() => {});
      }
      const configs = session.aiConfigs || {};
      const isBotEnabled = String(configs.ai_bot_enabled) === "true";

      const keyword = (configs.ai_prefix || "").trim();
      const containsKeyword = Boolean(
        keyword && normalize(textContent).includes(normalize(keyword)),
      );

      const botName =
        configs.chat?.system_prompt?.match(/meu nome é (\w+)/i)?.[1] || "ia";
      const mentionedByName =
        botName.length > 2 &&
        normalize(textContent).includes(normalize(botName));

      const author = msg.pushName || remoteJid.split("@")[0];
      const authorJid = msg.key.participant || remoteJid;
      const bufferKey = `${tenantId}_${remoteJid}`;
      const isActiveGroup = isGroup && trackGroupActivity(bufferKey, configs);

      if (!conversationBuffers.has(bufferKey))
        conversationBuffers.set(bufferKey, { tenantId, messages: [] });
      const buffer = conversationBuffers.get(bufferKey);

      const learningEnabled = configs.learning?.enabled !== false;
      const sttEnabled = configs.stt?.enabled !== false;

      let bufferText = textContent.trim();

      // ── Comando de Cancelamento ──
      if (normalize(bufferText) === "cancelartudo") {
        const jidSt = getJidState(tenantId, remoteJid);
        jidSt.processing = false;
        jidSt.queue = [];
        clearJidTimeouts(jidSt);
        
        // Limpa também estados globais de despacho e contexto
        const jidSuffixLoc = sanitizeJidForSession(remoteJid);
        const aiSessionId = jidSuffixLoc && jidSuffixLoc !== "default"
            ? `WA_${tenantId || "default"}_${jidSuffixLoc}`
            : `WA_${tenantId || "default"}`;
        
        waSessionDispatchState.delete(aiSessionId);
        activeRedRequests.delete(aiSessionId);
        
        const liveStateKey = streamStateKey(tenantId, remoteJid);
        const st = realtimeStreamState.get(liveStateKey);
        if (st?.composingInterval) clearInterval(st.composingInterval);
        realtimeStreamState.delete(liveStateKey);

        await sock.sendMessage(remoteJid, { text: "Fila limpa." }, { quoted: msg });
        continue;
      }

      const isRedProxy =
        configs.chat?.provider === "red-claude" ||
        configs.chat?.provider === "red-perplexity" ||
        !!(configs.chat?.red_instance_id || configs.red_instance_id);

      if (
        (isAudio || isImage || isDocument || isVideo) &&
        (learningEnabled || isRedProxy)
      ) {
        try {
          const mediaType = isAudio
            ? "audio"
            : isImage
              ? "image"
              : isVideo
                ? "video"
                : "document";
          const mediaMsg = isAudio
            ? msg.message.audioMessage
            : isImage
              ? msg.message.imageMessage ||
                msg.message.viewOnceMessageV2?.message?.imageMessage
              : isVideo
                ? msg.message.videoMessage ||
                  msg.message.viewOnceMessageV2?.message?.videoMessage
                : msg.message.documentMessage;

          const mediaBuffer = await downloadMediaMessage(
            msg,
            "buffer",
            {},
            {
              logger: pino({ level: "silent" }),
              reuploadRequest: sock.updateMediaMessage,
            },
          );

          if (mediaBuffer) {
            let mimeType = mediaMsg?.mimetype || "application/octet-stream";
            if (isImage && mimeType === "application/octet-stream")
              mimeType = "image/jpeg";

            let fileName = mediaMsg?.fileName;
            if (!fileName) {
              const ext = mimeType.split("/")[1] || "bin";
              fileName = `${mediaType}_${Date.now()}.${ext.split(";")[0]}`;
            }

            let processedBuffer = mediaBuffer;
            if (isImage && mediaBuffer.length > 2 * 1024 * 1024) {
              try {
                const sharp = require("sharp");
                processedBuffer = await sharp(mediaBuffer)
                  .resize(1280, 1280, {
                    fit: "inside",
                    withoutEnlargement: true,
                  })
                  .jpeg({ quality: 80 })
                  .toBuffer();
              } catch (err) {}
            }

            if (isRedProxy) {
              incomingFiles.push({
                name: fileName,
                mimeType: mimeType,
                dataBase64: processedBuffer.toString("base64"),
              });
            }

            if (isAudio && sttEnabled) {
              const transcription = await transcribeAudio(
                mediaBuffer,
                mimeType,
                configs,
              );
              if (transcription) {
                bufferText = `[AUDIO] ${transcription}`;
                mediaContent = { type: "audio", transcription };
              }
            } else if (isImage && configs.vision?.enabled !== false) {
              const caption = mediaMsg?.caption || "";
              const description = await analyzeImage(
                mediaBuffer,
                caption,
                configs,
              );
              if (description) {
                bufferText = `[IMAGEM] ${description}${caption ? ` | "${caption}"` : ""}`;
                mediaContent = { type: "image", description, caption };
              }
            } else if (isDocument || isVideo) {
              bufferText = `[ARQUIVO: ${fileName}]`;
            }
          }
        } catch (e) {
          console.error("[MEDIA] Erro ao baixar:", e.message);
        }
      }

      const bufferSize = getCfg(configs, "buffer_size", DEFAULT_BUFFER_SIZE);

      if (bufferText.length > 2) {
        buffer.messages.push({ author, authorJid, text: bufferText });
        appendMessageToContextBuffer(tenantId, remoteJid, author, bufferText);
        console.log(
          `[BUFFER] ${author}: "${bufferText}" (${buffer.messages.length}/${bufferSize}) ativo:${isActiveGroup}`,
        );
      }

      const shouldRespond =
        isPV ||
        (isGroup &&
          (isMentioned || isReplyToMe || containsKeyword || mentionedByName));

      console.log(
        `[MSG] 📨 ${isGroup ? "GRUPO" : "PV"} | De: ${author} | Texto: "${bufferText}" | Responder: ${shouldRespond} | Ativo: ${isActiveGroup}`,
      );

      const realtimeEnabled = configs.proactive?.realtime_enabled !== false;
      if (isBotEnabled && isGroup && realtimeEnabled && bufferText.length > 3) {
        const session2 = sessions.get(tenantId);
        realtimeProactiveAnalysis(
          tenantId,
          remoteJid,
          bufferText,
          author,
          configs,
          session2?.sock && session2.status === "authenticated"
            ? session2.sock
            : null,
          isActiveGroup,
        ).catch((e) => console.error("[RT BG] Erro:", e.message));
      }

      if (buffer.messages.length >= bufferSize && learningEnabled) {
        const msgs = [...buffer.messages];
        buffer.messages = [];
        learnFromConversation(
          tenantId,
          remoteJid,
          msgs,
          configs,
          isActiveGroup,
        ).catch((e) => console.error("[LEARN BG] Erro:", e.message));
      }

      if (!isBotEnabled) continue;

      let contentForAI = textContent;
      if (mediaContent?.type === "audio")
        contentForAI = `[Mensagem de voz] ${mediaContent.transcription}`;
      else if (mediaContent?.type === "image")
        contentForAI = `[Imagem] ${mediaContent.description}${textContent ? ` | "${textContent}"` : ""}`;

      if (!contentForAI.trim() && !mediaContent) continue;
      if (!shouldRespond) continue;

      // ── Fila ──
      const jidState = getJidState(tenantId, remoteJid);
      if (jidState.processing) {
        // Enfileira a mensagem e avisa o usuário visualmente
        jidState.queue.push({ msg, contentForAI, author, authorJid });
        try {
          await sock.sendMessage(remoteJid, {
            react: { text: "⏳", key: msg.key },
          });
        } catch (_) {}
        continue;
      }

      jidState.processing = true;

      // Snapshots
      const _msg = msg,
        _author = author,
        _authorJid = authorJid;
      const _isGroup = isGroup,
        _isPV = isPV,
        _isActiveGrp = isActiveGroup;
      const _configs = configs,
        _sock = sock,
        _tenantId = tenantId,
        _remoteJid = remoteJid;
      const _botId = botId,
        _botLidShort = botLidShort;
      const _containsKw = containsKeyword,
        _keyword = keyword;
      const _incomingFiles = [...incomingFiles];
      const _isRedProxy = isRedProxy;

      const _quotedCtx = (() => {
        try {
          const qm = contextInfo?.quotedMessage;
          if (!qm) return "";
          const quotedText =
            qm.conversation ||
            qm.extendedTextMessage?.text ||
            qm.imageMessage?.caption ||
            "";
          if (!quotedText.trim()) return "";
          const quotedParticipant = contextInfo?.participant || "";
          const isQuotedFromBot =
            quotedParticipant.includes(botId) ||
            (botLidShort && quotedParticipant.includes(botLidShort));
          const quotedName = isQuotedFromBot
            ? "você mesmo"
            : msg.pushName || quotedParticipant.split("@")[0] || "alguém";
          const quoteLabel = isQuotedFromBot
            ? `o usuário está RESPONDENDO a uma mensagem sua anterior: "${quotedText.trim().substring(0, 300)}". Continue a conversa a partir dessa referência, mas NÃO repita o que já foi dito se não for necessário.`
            : `o usuário está RESPONDENDO a uma mensagem de ${quotedName}: "${quotedText.trim().substring(0, 300)}".`;
          return `\n[CONTEXTO DE RESPOSTA: ${quoteLabel}]`;
        } catch (_) {
          return "";
        }
      })();

      async function _runAIProcessing(
        procMsg,
        procContent,
        procAuthor,
        procAuthorJid,
        isAggregated = false,
      ) {
        let convMemory = "",
          senderProfile = "",
          longTermMemory = "",
          currentVibe = "Neutro";

        try {
          const { data: convData } = await supabase
            .from("whatsapp_conversation_contexts")
            .select(
              "summary, vibe, group_type, daily_topics, communication_style, context_hint",
            )
            .eq("tenant_id", _tenantId)
            .eq("conversation_id", _remoteJid)
            .single();

          if (convData?.summary) {
            convMemory = `\n[CONTEXTO DA CONVERSA: ${convData.summary}]`;
            if (convData.group_type)
              convMemory += `\n[TIPO DE GRUPO: ${convData.group_type}]`;
            if (convData.daily_topics)
              convMemory += `\n[TÓPICOS DO MOMENTO: ${convData.daily_topics}]`;
            if (convData.communication_style)
              convMemory += `\n[ESTILO/GÍRIAS DO GRUPO: ${convData.communication_style}]`;
            if (convData.context_hint)
              convMemory += `\n[DICA IMPORTANTE: ${convData.context_hint}]`;
          }
          if (convData?.vibe) currentVibe = convData.vibe;

          const { data: profData } = await supabase
            .from("whatsapp_contact_profiles")
            .select(
              "full_name, nickname, personality_traits, communication_style, metadata",
            )
            .eq("tenant_id", _tenantId)
            .eq("contact_id", procAuthorJid)
            .single();

          if (profData) {
            const nicks = profData.metadata?.nicknames || [];
            senderProfile = `\n[PERFIL DE ${procAuthor}: nome=${profData.full_name || procAuthor}${nicks.length ? `, apelidos: ${nicks.join(", ")}` : ""}, personalidade: ${profData.personality_traits || "N/A"}, estilo: ${profData.communication_style || "N/A"}]`;
          }

          longTermMemory = await getContactMemory(_tenantId, procAuthorJid, 8);
        } catch (_) {}

        let groupPersonality = null;
        if (_isGroup) {
          groupPersonality = await getGroupPersonality(_tenantId, _remoteJid);
          if (groupPersonality?.enabled === false) return false;
        }

        const simpleIntent = detectSimpleIntent(procContent);

        let cleanText = procContent
          .replace(new RegExp(`@${_botId}`, "g"), "")
          .replace(new RegExp(`@${_botLidShort}`, "g"), "")
          .trim();
        if (_containsKw && _keyword) {
          cleanText = cleanText
            .replace(
              new RegExp(_keyword.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"),
              "",
            )
            .trim();
        }

        const chatCfg = _configs.chat || {};
        const basePrompt =
          groupPersonality?.system_prompt ||
          chatCfg.system_prompt ||
          _configs.system_prompt ||
          "Você é um assistente.";
        const activeGroupCtx = _isActiveGrp
          ? "\n[GRUPO MOVIMENTADO: conversa ativa, seja mais espontânea e presente]"
          : "";
        const groupCtx = _isGroup
          ? `\n[VOCÊ ESTÁ NUM GRUPO. Seja natural, como membro da galera. Vibe atual: ${currentVibe}. NUNCA diga que é IA.]`
          : `\n[CONVERSA PRIVADA. Seja atencioso, carinhoso e direto.]`;
        const styleInstruction = `\n[ESTILO: vibe = ${currentVibe}. Use gírias do grupo se descontraído. Seja HUMANO. Grupo → resposta curta e natural. PV → pode ser mais detalhado.]`;
        const sizeInstruction = `\n[TAMANHO: varie o tamanho de forma humana — às vezes 2-3 palavras, às vezes 1-2 frases. Nunca responda da mesma forma sempre.]`;

        let businessCtx = "";
        if (_tenantId !== ADMIN_TENANT_ID)
          businessCtx = await getTenantContext(_tenantId);

        const resolvedMemory = await resolveNames(convMemory, _tenantId, _sock);
        const resolvedCleanText = await resolveNames(
          cleanText,
          _tenantId,
          _sock,
        );

        const ctxKey = `${_tenantId}::${_remoteJid}`;
        const alreadySentCtx = sessionContextSent.get(ctxKey);
        const recentCtxBlock = buildContextBlock(_tenantId, _remoteJid);

        let fullPrompt;
        if (!alreadySentCtx) {
          // Primeira mensagem da sessão: Mandamos TUDO (Persona + Histórico + Msg)
          fullPrompt = `${businessCtx ? `EMPRESA:\n${businessCtx}\n\n` : ""}INSTRUÇÕES:\n${basePrompt}${resolvedMemory}${longTermMemory}${senderProfile}${groupCtx}${activeGroupCtx}${styleInstruction}${sizeInstruction}${recentCtxBlock}${_quotedCtx}\n\nRESPONDA AGORA — MENSAGEM DE ${procAuthor}: ${resolvedCleanText || "Oi!"}`;
          sessionContextSent.set(ctxKey, {
            sentAt: Date.now(),
            vibe: currentVibe,
          });
        } else {
          const vibeChanged = alreadySentCtx.vibe !== currentVibe;
          const vibeHint = vibeChanged ? `\n[VIBE ATUAL: ${currentVibe}]` : "";
          
          // MÍNIMO POSSÍVEL: Se já estamos conversando na mesma aba, não mandamos o histórico.
          // Mandamos apenas o "contexto de resposta" (se ele quotou alguém) e a mensagem nova.
          if (isRedProxy) {
            fullPrompt = `${vibeHint}${activeGroupCtx}${_quotedCtx}\n\nRESPONDA AGORA — MENSAGEM DE ${procAuthor}: ${resolvedCleanText || "Oi!"}`;
          } else {
            // Outros providers (OpenAI, Gemini) ainda precisam do histórico em cada chamada
            fullPrompt = `${vibeHint}${activeGroupCtx}${recentCtxBlock}${_quotedCtx}\n\nRESPONDA AGORA — MENSAGEM DE ${procAuthor}: ${resolvedCleanText || "Oi!"}`;
          }

          if (vibeChanged)
            sessionContextSent.set(ctxKey, {
              sentAt: alreadySentCtx.sentAt,
              vibe: currentVibe,
            });
        }

        const setReact = async (emoji) => {
          try {
            await _sock.sendMessage(_remoteJid, {
              react: { text: emoji, key: procMsg.key },
            });
          } catch (_) {}
        };

        try {
          const liveStateKey = streamStateKey(_tenantId, _remoteJid);
          const jidSuffixLoc = sanitizeJidForSession(_remoteJid);
          const aiSessionId =
            jidSuffixLoc && jidSuffixLoc !== "default"
              ? `WA_${_tenantId || "default"}_${jidSuffixLoc}`
              : `WA_${_tenantId || "default"}`;

          await setReact("🔵");

          // Limpa estado de stream anterior (garante typing em toda nova mensagem)
          realtimeStreamState.delete(liveStateKey);

          const existingDisp = waSessionDispatchState.get(aiSessionId);
          waSessionDispatchState.set(aiSessionId, {
            ...existingDisp,
            sock: _sock,
            remoteJid: _remoteJid,
            updatedAt: Date.now(),
            sentFileFingerprints: existingDisp?.sentFileFingerprints || new Set(),
          });

          const _jidSt = getJidState(_tenantId, _remoteJid);
          clearJidTimeouts(_jidSt);

          const aiResult = await getAIResponse(fullPrompt, _configs, null, {
            includeMeta: true,
            conversationId: _remoteJid,
            files: _incomingFiles,
            onStream: (eventData) => {
              _jidSt.lastStreamEventAt = Date.now();
              handleRealtimeAIStreamEvent(
                _sock,
                _remoteJid,
                liveStateKey,
                eventData,
              );
            },
          });

          clearJidTimeouts(_jidSt);

          const response =
            typeof aiResult === "string" ? aiResult : aiResult?.text || null;
          const files = Array.isArray(aiResult?.files) ? aiResult.files : [];

          const waDispSt = waSessionDispatchState.get(aiSessionId);
          if (waDispSt) {
            files.forEach((f) =>
              waDispSt.sentFileFingerprints.add(fileFingerprint(f)),
            );
            waDispSt.updatedAt = Date.now();
          }

          if (response || files.length) {
            lastProactiveTime.set(`${_tenantId}_${_remoteJid}`, Date.now());
            if (response) {
              lastBotResponseByJid.set(`${_tenantId}_${_remoteJid}`, {
                text: response.substring(0, 300),
                sentAt: Date.now(),
              });
            }
            await stopRealtimeComposing(_sock, _remoteJid, liveStateKey);
            
            // Limpa qualquer status pendente antes de enviar a resposta final
            const statusKey = `${_tenantId}_${normalizeJidForKey(_remoteJid)}`;
            if (activeStatusMessages.has(statusKey)) {
                const statusData = activeStatusMessages.get(statusKey);
                try {
                    await _sock.sendMessage(_remoteJid, { delete: statusData.key });
                } catch (_) {}
                activeStatusMessages.delete(statusKey);
            }

            await setReact("🟢");

            const finalEditKey = aiResult?.editKey || null;
            const finalText = response || "📎 Arquivo gerado.";

            await sendSmartResponse(
              _sock,
              _remoteJid,
              finalText,
              procMsg,
              _configs,
              {
                files,
                skipPresence: true,
                editKey: finalEditKey,
              },
            );
            await stopRealtimeComposing(_sock, _remoteJid, liveStateKey);

            setTimeout(() => {
              const latest = waSessionDispatchState.get(aiSessionId);
              if (!latest) return;
              if (Date.now() - (latest.updatedAt || 0) >= 180000)
                waSessionDispatchState.delete(aiSessionId);
            }, 185000);

            return true;
          } else {
            await stopRealtimeComposing(_sock, _remoteJid, liveStateKey);
            await setReact("🟠");
            return false;
          }
        } catch (err) {
          await stopRealtimeComposing(
            _sock,
            _remoteJid,
            streamStateKey(_tenantId, _remoteJid),
          );
          await presenceManager.stopComposing(_sock, _remoteJid);
          clearJidTimeouts(getJidState(_tenantId, _remoteJid));
          try {
            await setReact("🔴");
          } catch (_) {}
          console.error(`[RESP] Erro:`, err.message);
          return false;
        }
      }

      // Dispara processamento e drena fila
      (async () => {
        try {
          await _runAIProcessing(_msg, contentForAI, _author, _authorJid);

          const _jidSt = getJidState(_tenantId, _remoteJid);
          while (_jidSt.queue.length > 0) {
            const queued = [..._jidSt.queue];
            _jidSt.queue = [];
            let aggregatedContent;
            if (queued.length === 1) {
              aggregatedContent = queued[0].contentForAI;
            } else {
              const lines = queued
                .map(
                  (item, i) =>
                    `[${i + 1}] ${item.author}: "${item.contentForAI}"`,
                )
                .join("\n");
              aggregatedContent = `[O USUÁRIO ENVIOU VÁRIAS MENSAGENS ENQUANTO VOCÊ PROCESSAVA:\n${lines}\n\nResponda de forma natural, considerando todas como parte da mesma conversa. Não liste as respostas em tópicos — responda como em conversa fluida.]`;
            }
            const firstQueued = queued[0];
            await _runAIProcessing(
              firstQueued.msg,
              aggregatedContent,
              firstQueued.author,
              firstQueued.authorJid || _authorJid,
              queued.length > 1,
            );
          }
        } catch (e) {
          console.error("[FILA] Erro no processamento:", e.message);
        } finally {
          const _jidSt = getJidState(_tenantId, _remoteJid);
          _jidSt.processing = false;
        }
      })();
    }
  });
}

module.exports = { setupMessageHandler };
