const { recentMessages, getMemories, getProfile } = require("./store");

function foldForPolicy(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function normalizePromptForPolicy(prompt, config) {
  const prefix = foldForPolicy(config.chat?.group_prefix || "red").replace(/[^\w]+/g, "");
  let text = foldForPolicy(prompt)
    .replace(/\[(imagem analisada|audio transcrito|audio recebido|documento recebido)[\s\S]*$/g, " ")
    .replace(/@\d+/g, " ")
    .replace(/[^\w\s?]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (prefix) {
    text = text
      .replace(new RegExp(`^${prefix}\\b\\s*`, "i"), "")
      .replace(new RegExp(`\\b${prefix}$`, "i"), "")
      .replace(/\s+/g, " ")
      .trim();
  }
  return text;
}

function hasMediaPayload(prompt) {
  return /\[(Imagem analisada|Audio transcrito|Audio recebido|Documento recebido)/i.test(String(prompt || ""));
}

function hasQuotedPayload(prompt) {
  return /O usuario esta respondendo a uma mensagem citada|Mensagem citada de/i.test(String(prompt || ""));
}

function hasFollowupCue(text) {
  return /\b(isso|isto|essa|esse|esta|este|aquilo|anterior|antes|ultimo|ultima|acima|ref|referencia|resuma|resume|continua|continue|explica|explica melhor|explica essa|explica a piada|como assim|nao entendi|n entendi|entendi nao|nao saquei|qual a graca|qual foi a piada|sobre isso|da imagem|do audio|que eu mandei|que falei|que combinamos|deu certo|conseguiu)\b/.test(text);
}

function asksForMemory(text) {
  return /\b(lembra|memoria|memória|sabe sobre mim|o que sabe de mim|me conhece|meu nome|quem sou eu)\b/.test(text);
}

function isGreetingOrPing(text) {
  const clean = text.replace(/[^\w\s]/g, "").replace(/\s+/g, " ").trim();
  if (!clean) return true;
  if (/^(red|redia)$/.test(clean)) return true;
  if (/^(oi|ola|opa|eai|ei|fala|salve|bom dia|boa tarde|boa noite|hey|hi|hello)( tudo bem| td bem| blz| beleza)?$/.test(clean)) return true;
  if (/^(oi|ola|opa|eai|ei|fala|salve|hey|hi|hello) (red|redia)$/.test(clean)) return true;
  return clean.length <= 14 && /^(oi|ola|opa|eai|ei|fala|salve|red|redia)\b/.test(clean);
}

function detectContextPolicy(prompt, config = {}) {
  const normalized = normalizePromptForPolicy(prompt, config);
  const quoted = hasQuotedPayload(prompt);
  const media = hasMediaPayload(prompt);
  const memoryRequest = asksForMemory(normalized);
  const followup = hasFollowupCue(normalized);

  if (quoted) {
    return {
      mode: "quoted_reply",
      includeSummary: false,
      includeConversationHints: false,
      includeMemory: false,
      includeChatMemory: false,
      includeRecent: false,
      recentScale: 0,
      guidance: "A mensagem atual responde uma mensagem citada. Use a mensagem citada como contexto principal. Se o usuario disser que nao entendeu, explique especificamente a mensagem citada, sem inventar outro assunto.",
    };
  }

  if (media && !followup) {
    return {
      mode: "current_media",
      includeSummary: false,
      includeConversationHints: false,
      includeMemory: memoryRequest,
      includeChatMemory: false,
      includeRecent: false,
      recentScale: 0,
      guidance: "A mensagem atual tem midia analisada/transcrita. Priorize a midia atual e nao misture com imagens, audios ou assuntos antigos se o usuario nao pedir.",
    };
  }

  if (!followup && !memoryRequest && isGreetingOrPing(normalized)) {
    return {
      mode: "fresh_ping",
      includeSummary: false,
      includeConversationHints: false,
      includeMemory: false,
      includeChatMemory: false,
      includeRecent: false,
      recentScale: 0,
      guidance: "A mensagem atual e apenas saudacao, chamado ou ping. Responda como um novo turno curto e natural. Nao puxe assuntos anteriores, tarefas, imagens, codigo ou piadas antigas.",
    };
  }

  if (!followup) {
    return {
      mode: memoryRequest ? "memory_request" : "standalone",
      includeSummary: false,
      includeConversationHints: false,
      includeMemory: true,
      includeChatMemory: memoryRequest,
      includeRecent: false,
      recentScale: 0,
      guidance: memoryRequest
        ? "Use memorias estaveis se ajudarem, mas nao transforme historico recente em assunto se a pergunta nao pedir."
        : "A mensagem parece um pedido independente. Responda ao que foi pedido agora. Use memoria apenas como pano de fundo discreto; nao cite nem continue assuntos anteriores sem necessidade.",
    };
  }

  return {
    mode: "followup",
    includeSummary: true,
    includeConversationHints: true,
    includeMemory: true,
    includeChatMemory: true,
    includeRecent: true,
    recentScale: 1,
    guidance: "A mensagem parece depender de contexto anterior. Use o historico somente para resolver a referencia atual e nao para trocar o assunto.",
  };
}

function buildMemoryBlock(chatId, senderJid, config, options = {}) {
  const limit = config.learning?.memory_facts_per_contact || 12;
  const personal = options.includePersonal === false ? [] : getMemories({ contactJid: senderJid, limit });
  const chat = options.includeChat === false ? [] : getMemories({ chatId, limit: Math.max(4, Math.floor(limit / 2)) });
  const profile = options.includePersonal === false || !senderJid ? null : getProfile(senderJid);
  const lines = [];
  if (profile) {
    const nicknames = Array.isArray(profile.nicknames) && profile.nicknames.length ? `; apelidos: ${profile.nicknames.join(", ")}` : "";
    const style = profile.style ? `; estilo: ${profile.style}` : "";
    const notes = profile.notes ? `; notas: ${profile.notes}` : "";
    lines.push(`Perfil aprendido desta pessoa: ${profile.name || senderJid}${nicknames}${style}${notes}`);
  }
  if (personal.length) {
    lines.push("Memoria sobre esta pessoa:");
    for (const item of personal) lines.push(`- ${item.fact}`);
  }
  if (chat.length) {
    lines.push("Memoria desta conversa/grupo:");
    for (const item of chat) lines.push(`- ${item.fact}`);
  }
  return lines.length ? lines.join("\n") : "";
}

function modelContextBudget(config, model = "") {
  const configured = Number(config.chat?.max_context_chars || 12000);
  const name = String(model || "").toLowerCase();
  if (/gemma3:4b/.test(name)) return Math.min(configured, 7600);

  const sizeMatch = name.match(/(?::|-)(\d+(?:\.\d+)?)b(?:\b|$)/);
  const size = sizeMatch ? Number(sizeMatch[1]) : 0;
  if (size && size <= 4) return Math.min(configured, 7600);
  if (size && size <= 8) return Math.min(configured, 9000);
  return configured;
}

function clipLine(line, maxChars) {
  if (line.length <= maxChars) return line;
  return `${line.slice(0, Math.max(0, maxChars - 3)).trim()}...`;
}

function buildRecentContext(chatId, config, options = {}) {
  const maxMessages = config.chat?.max_context_messages || 24;
  const maxChars = Number(options.maxChars || modelContextBudget(config, options.model));
  const rows = recentMessages(chatId, maxMessages);
  const selected = [];
  let chars = 0;
  for (let index = rows.length - 1; index >= 0; index -= 1) {
    const item = rows[index];
    const name = item.sender_name || (item.role === "assistant" ? "REDIA" : "Usuario");
    const text = String(item.text || "").trim();
    if (!text) continue;
    let line = `${item.role === "assistant" ? "assistant" : name}: ${text}`;
    if (line.length > maxChars) line = clipLine(line, maxChars);
    const nextChars = chars + line.length + 1;
    if (nextChars > maxChars && selected.length) break;
    if (nextChars > maxChars) line = clipLine(line, Math.max(300, maxChars - chars - 1));
    selected.push(line);
    chars += line.length + 1;
  }
  const out = selected.reverse();
  return out.length ? `Historico recente:\n${out.join("\n")}` : "";
}

function buildChatMessages({ config, conversation, prompt, senderName, senderJid, model = "" }) {
  const policy = detectContextPolicy(prompt, config);
  const budget = modelContextBudget(config, model);
  const memoryBlock = policy.includeMemory
    ? buildMemoryBlock(conversation.chat_id, senderJid, config, { includeChat: policy.includeChatMemory })
    : "";
  const recentBlock = policy.includeRecent
    ? buildRecentContext(conversation.chat_id, config, { model, maxChars: Math.max(1200, Math.floor(budget * policy.recentScale)) })
    : "";
  const system = [
    config.chat.system_prompt,
    `Politica de contexto: ${policy.mode}. ${policy.guidance}`,
    `Canal: ${conversation.kind === "group" ? "grupo" : "privado"}.`,
    conversation.name ? `Nome do chat: ${conversation.name}.` : "",
    policy.includeSummary && conversation.summary ? `Resumo acumulado: ${conversation.summary}` : "",
    conversation.vibe ? `Vibe atual: ${conversation.vibe}.` : "",
    policy.includeConversationHints && conversation.style ? `Estilo/girias: ${conversation.style}.` : "",
    policy.includeConversationHints && conversation.topics ? `Topicos atuais: ${conversation.topics}.` : "",
    policy.includeConversationHints && conversation.context_hint ? `Dica de contexto: ${conversation.context_hint}.` : "",
    memoryBlock,
    recentBlock,
  ]
    .filter(Boolean)
    .join("\n\n");

  return [
    { role: "system", content: system },
    {
      role: "user",
      content: `Mensagem de ${senderName || "usuario"}: ${prompt || "Oi"}`,
    },
  ];
}

module.exports = {
  buildMemoryBlock,
  buildRecentContext,
  buildChatMessages,
  modelContextBudget,
  detectContextPolicy,
};
