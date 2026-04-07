const { chatComplete } = require("./redsystemsClient");
const store = require("./store");
const activity = require("./activity");
const { nowIso } = require("./json");

const lastLearnAt = new Map();

function extractJson(text) {
  const raw = String(text || "").replace(/```json/gi, "").replace(/```/g, "").trim();
  const start = raw.indexOf("{");
  const end = raw.lastIndexOf("}");
  if (start < 0 || end < start) return null;
  try {
    return JSON.parse(raw.slice(start, end + 1));
  } catch {
    return null;
  }
}

function recentHasLearningSignal(rows) {
  const userRows = (rows || []).filter((row) => row.direction === "incoming" || row.role === "user");
  const text = userRows.map((row) => String(row.text || "")).join("\n");
  const meaningfulRows = userRows.filter((row) => {
    const value = String(row.text || "").trim();
    if (value.length >= 24) return true;
    if (/[?]/.test(value)) return true;
    if (row.metadata?.media_type || row.content_type !== "text") return true;
    return false;
  });
  return meaningfulRows.length >= 2 || text.length >= 160;
}

function transcriptFromRows(rows) {
  return rows
    .map((item) => {
      const name = item.sender_name || item.role || "usuario";
      const jid = item.sender_jid ? ` (${item.sender_jid})` : "";
      const direction = item.direction === "outgoing" ? "REDIA" : `${name}${jid}`;
      return `${direction}: ${String(item.text || "").slice(0, 900)}`;
    })
    .join("\n");
}

function aliasKey(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\ufe0f/g, "")
    .toLowerCase()
    .trim();
}

function participantAliases(rows) {
  const aliases = new Map();
  const participants = new Map();
  for (const row of rows || []) {
    const jid = String(row.sender_jid || "").trim();
    const name = String(row.sender_name || "").trim();
    if (!jid.includes("@")) continue;
    participants.set(jid, name || jid);
    aliases.set(aliasKey(jid), jid);
    aliases.set(aliasKey(jid.split("@")[0].split(":")[0]), jid);
    if (name) aliases.set(aliasKey(name), jid);
  }
  return { aliases, participants };
}

function sanitizeContactJid(value, aliases = new Map()) {
  const text = String(value || "").trim();
  if (text.includes("@")) return text;
  return aliases.get(aliasKey(text)) || "";
}

async function maybeLearnFromConversation(config, conversation) {
  if (!config.learning?.enabled) return;
  const chatId = conversation.chat_id;
  const now = Date.now();
  const state = store.getLearningState(chatId);
  const cooldown = Math.max(Number(config.learning.cooldown_ms || 120000), Number(config.learning.min_interval_ms || 120000));
  if (now - (lastLearnAt.get(chatId) || 0) < cooldown) return;

  const total = store.countMessages(chatId);
  const minMessages = Number(config.learning.min_conversation_messages || config.learning.batch_messages || 8);
  if (total < minMessages) return;

  const lastLearnedCount = Number(state.last_learned_message_count || 0);
  const newMessages = total - lastLearnedCount;
  const batchMessages = Number(config.learning.batch_messages || 8);
  if (lastLearnedCount > 0 && newMessages < batchMessages) return;

  if (state.last_learned_at) {
    const lastAt = Date.parse(state.last_learned_at);
    if (Number.isFinite(lastAt) && now - lastAt < cooldown) return;
  }

  lastLearnAt.set(chatId, now);
  activity.publish("learning:start", {
    chat_id: chatId,
    chat_kind: conversation.kind,
    chat_name: conversation.name,
    model: config.learning.model,
    message_count: total,
    new_messages: newMessages,
  });

  const windowSize = Math.max(
    Number(config.learning.analysis_window_messages || 28),
    Math.min(60, newMessages + Number(config.learning.keep_recent_messages || 10)),
  );
  const rows = store.recentMessages(chatId, windowSize);
  if (!recentHasLearningSignal(rows)) {
    store.saveLearningState(chatId, {
      last_learned_message_count: total,
      last_learned_at: nowIso(),
      last_skipped_message_count: total,
    });
    activity.publish("learning:skip", {
      chat_id: chatId,
      chat_kind: conversation.kind,
      chat_name: conversation.name,
      reason: "sem sinal estavel de aprendizado",
      message_count: total,
    });
    return;
  }

  const transcript = transcriptFromRows(rows);
  const { aliases, participants } = participantAliases(rows);
  const participantList = [...participants.entries()]
    .map(([jid, name]) => `- ${name} => ${jid}`)
    .join("\n");
  const prompt = [
    "Analise um BLOCO de conversa de WhatsApp e atualize o estado aprendido da REDIA.",
    "Nao crie uma nova conclusao para cada mensagem isolada. Aprenda apenas o que for estavel, recorrente ou util para responder melhor depois.",
    "Separe assunto atual de memoria permanente: topicos/vibe/context_hint podem mudar; memories e profiles precisam ser fatos duraveis.",
    "Retorne APENAS JSON puro, sem markdown.",
    "Formato:",
    '{"summary":"resumo acumulado atualizado em ate 700 chars","vibe":"Neutro|Zoeira|Serio|Animado|Tenso|Carinhoso|Irritado|Focado","group_type":"Amigos|Trabalho|Familia|Projeto|Geral","style":"girias, tom e ritmo do chat","topics":"assuntos atuais separados por virgula","context_hint":"dica curta para proximas respostas; quando nao houver assunto, diga para nao puxar contexto antigo","memories":[{"contact_jid":"","fact":"","category":"preferencia|perfil|pendencia|relacao|geral","confidence":0.7}],"profiles":[{"jid":"","name":"","nicknames":[],"style":"","notes":"","memory_facts":[]}]}',
    "Regras de memories:",
    "- Nao salve saudacoes, piadas pontuais, insultos isolados, respostas da REDIA ou assunto temporario como memoria permanente.",
    "- Salve preferencias, nomes/apelidos, projetos importantes, relacoes, pendencias explicitas e padroes de estilo.",
    "- Use contact_jid/jid como o JID real do WhatsApp. Display name/apelido deve ir em name/nicknames, nunca no campo jid.",
    "- Se a pessoa aparecer como '®️', isso e nome/apelido do WhatsApp; associe ao JID correspondente listado abaixo.",
    "",
    `Participantes conhecidos neste bloco:\n${participantList || "nenhum"}`,
    "",
    `Resumo anterior: ${conversation.summary || "nenhum"}`,
    `Vibe anterior: ${conversation.vibe || "Neutro"}`,
    `Topicos anteriores: ${conversation.topics || "nenhum"}`,
    `Estilo anterior: ${conversation.style || "nenhum"}`,
    `Dica anterior: ${conversation.context_hint || "nenhuma"}`,
    `Conversa:\n${transcript}`,
  ].join("\n");

  let result;
  try {
    result = await chatComplete(config, {
      role: "learning",
      model: config.learning.model,
      temperature: 0.12,
      messages: [
        { role: "system", content: "Voce e um analisador de memoria conversacional. Responda somente JSON valido." },
        { role: "user", content: prompt },
      ],
      timeoutMs: 60000,
      meta: {
        chat_id: chatId,
        chat_kind: conversation.kind,
        chat_name: conversation.name,
      },
    });
    store.saveModelRun({
      role: "learning",
      model: result.model,
      prompt_chars: prompt.length,
      response_chars: result.content.length,
      latency_ms: result.latency_ms,
      ok: true,
    });
  } catch (err) {
    store.saveModelRun({
      role: "learning",
      model: config.learning.model,
      prompt_chars: prompt.length,
      response_chars: 0,
      latency_ms: 0,
      ok: false,
      error: err.message,
    });
    activity.publish("learning:error", {
      chat_id: chatId,
      chat_kind: conversation.kind,
      chat_name: conversation.name,
      model: config.learning.model,
      error: err.message,
    });
    return;
  }

  const parsed = extractJson(result.content);
  if (!parsed) {
    activity.publish("learning:error", {
      chat_id: chatId,
      chat_kind: conversation.kind,
      chat_name: conversation.name,
      model: result.model,
      error: "JSON de aprendizado invalido",
      response_preview: result.content,
    });
    return;
  }

  store.updateConversation(chatId, {
    summary: String(parsed.summary || conversation.summary || "").slice(0, 1200),
    vibe: String(parsed.vibe || conversation.vibe || "Neutro").slice(0, 80),
    style: String(parsed.style || conversation.style || "").slice(0, 600),
    topics: String(parsed.topics || conversation.topics || "").slice(0, 600),
    context_hint: String(parsed.context_hint || conversation.context_hint || "").slice(0, 800),
  });

  let memoriesAdded = 0;
  let profilesUpdated = 0;
  if (Array.isArray(parsed.memories)) {
    for (const memory of parsed.memories.slice(0, Number(config.learning.max_memory_facts_per_run || 6))) {
      const contactJid = sanitizeContactJid(memory.contact_jid || memory.jid || "", aliases);
      const id = store.addMemory({
        chat_id: chatId,
        contact_jid: contactJid,
        fact: memory.fact || "",
        category: memory.category || "geral",
        confidence: memory.confidence || 0.7,
      });
      if (id) memoriesAdded += 1;
    }
  }

  if (Array.isArray(parsed.profiles)) {
    for (const profile of parsed.profiles.slice(0, 12)) {
      const contactJid = sanitizeContactJid(profile.jid || profile.contact_jid || "", aliases);
      if (!contactJid) continue;
      const saved = store.upsertProfile({
        contact_jid: contactJid,
        name: profile.name || "",
        nicknames: profile.nicknames || [],
        style: profile.style || "",
        notes: profile.notes || "",
      });
      if (!saved) continue;
      profilesUpdated += 1;
      const facts = Array.isArray(profile.memory_facts) ? profile.memory_facts : [];
      for (const fact of facts.slice(0, 4)) {
        const id = store.addMemory({
          chat_id: chatId,
          contact_jid: saved.contact_jid,
          fact,
          category: "perfil",
          confidence: 0.75,
        });
        if (id) memoriesAdded += 1;
      }
    }
  }

  store.saveLearningState(chatId, {
    last_learned_message_count: total,
    last_learned_at: nowIso(),
  });

  activity.publish("learning:done", {
    chat_id: chatId,
    chat_kind: conversation.kind,
    chat_name: conversation.name,
    model: result.model,
    summary_preview: parsed.summary || "",
    vibe: parsed.vibe || conversation.vibe || "Neutro",
    memories: memoriesAdded,
    profiles: profilesUpdated,
    new_messages: newMessages,
  });
}

module.exports = { maybeLearnFromConversation, extractJson };
