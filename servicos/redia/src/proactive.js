const { chatComplete } = require("./redsystemsClient");
const { buildRecentContext } = require("./memory");
const store = require("./store");
const activity = require("./activity");

const lastProactiveAt = new Map();
const groupActivity = new Map();

function trackActivity(chatId, config) {
  const now = Date.now();
  const windowMs = config.proactive?.active_group_window_ms || 120000;
  const threshold = config.proactive?.active_group_threshold || 5;
  const rows = groupActivity.get(chatId) || [];
  rows.push(now);
  while (rows.length && rows[0] < now - windowMs) rows.shift();
  groupActivity.set(chatId, rows);
  return rows.length >= threshold;
}

async function maybeProactive(config, conversation, incoming, sendText) {
  if (!config.proactive?.enabled || !config.proactive?.realtime_enabled) return;
  if (conversation.kind !== "group") return;
  const chatId = conversation.chat_id;
  const now = Date.now();
  const cooldown = config.proactive.cooldown_ms || 45000;
  if (now - (lastProactiveAt.get(chatId) || 0) < cooldown) return;
  const active = trackActivity(chatId, config);
  if (!active && Math.random() > Number(config.proactive.frequency || 0.16)) return;
  activity.publish("proactive:start", {
    chat_id: chatId,
    chat_kind: conversation.kind,
    chat_name: conversation.name,
    sender_name: incoming.sender_name,
    model: config.proactive.model,
    active_group: active,
  });

  const recent = buildRecentContext(
    chatId,
    { ...config, chat: { ...config.chat, max_context_messages: 10, max_context_chars: 5000 } },
    { model: config.proactive.model },
  );
  const prompt = [
    "Decida se a REDIA deve participar espontaneamente desta conversa de WhatsApp agora.",
    "Retorne APENAS JSON puro: {\"should_reply\":false,\"urgency\":0,\"message\":\"\"}",
    "Regras: message deve ser vazia se nao for participar. Se participar, maximo 2 frases naturais.",
    "Ela deve se inserir no assunto, nao puxar assunto antigo e nao parecer bot. Use a vibe/estilo do grupo.",
    `Vibe: ${conversation.vibe || "Neutro"}`,
    `Topicos atuais aprendidos: ${conversation.topics || "nenhum"}`,
    `Estilo/girias aprendidos: ${conversation.style || "nenhum"}`,
    `Dica de contexto: ${conversation.context_hint || "nenhuma"}`,
    `Ultima mensagem: ${incoming.sender_name || "usuario"}: ${incoming.text}`,
    recent,
  ].join("\n\n");

  let parsed = null;
  try {
    const result = await chatComplete(config, {
      role: "proactive",
      model: config.proactive.model,
      temperature: 0.25,
      messages: [
        { role: "system", content: "Voce decide participacao espontanea em grupos. Responda somente JSON valido." },
        { role: "user", content: prompt },
      ],
      timeoutMs: 45000,
      meta: {
        chat_id: chatId,
        chat_kind: conversation.kind,
        chat_name: conversation.name,
        sender_name: incoming.sender_name,
      },
    });
    store.saveModelRun({
      role: "proactive",
      model: result.model,
      prompt_chars: prompt.length,
      response_chars: result.content.length,
      latency_ms: result.latency_ms,
      ok: true,
    });
    parsed = require("./learning").extractJson(result.content);
    activity.publish("proactive:decision", {
      chat_id: chatId,
      chat_kind: conversation.kind,
      chat_name: conversation.name,
      model: result.model,
      response_preview: result.content,
    });
  } catch (err) {
    activity.publish("proactive:error", {
      chat_id: chatId,
      chat_kind: conversation.kind,
      chat_name: conversation.name,
      model: config.proactive.model,
      error: err.message,
    });
    store.saveModelRun({
      role: "proactive",
      model: config.proactive.model,
      prompt_chars: prompt.length,
      response_chars: 0,
      latency_ms: 0,
      ok: false,
      error: err.message,
    });
  }
  if (!parsed?.should_reply || !String(parsed.message || "").trim()) return;
  const urgency = Number(parsed.urgency || 0);
  const roll = Math.random();
  const frequency = Number(config.proactive.frequency || 0.16);
  if (urgency < 6 && roll > frequency) return;
  lastProactiveAt.set(chatId, Date.now());
  const delay = urgency >= 8 ? 1200 : 2800 + Math.random() * 6500;
  activity.publish("proactive:scheduled", {
    chat_id: chatId,
    chat_kind: conversation.kind,
    chat_name: conversation.name,
    model: config.proactive.model,
    urgency,
    delay_ms: Math.round(delay),
    response_preview: parsed.message,
  });
  setTimeout(() => sendText(String(parsed.message).trim(), { proactive: true }).catch(() => {}), delay);
}

module.exports = { maybeProactive, trackActivity };
