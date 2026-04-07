const { formatForWhatsApp, splitWhatsAppText } = require("./format");
const { shouldSendAudio, generateEdgeTts } = require("./tts");

async function sendPresence(sock, jid, presence = "composing") {
  try {
    await sock.sendPresenceUpdate(presence, jid);
  } catch {
    // presence is best effort
  }
}

async function sendText(sock, jid, text, quotedMsg = null) {
  const chunks = splitWhatsAppText(text);
  const sent = [];
  for (const chunk of chunks) {
    sent.push(await sock.sendMessage(jid, { text: chunk }, quotedMsg ? { quoted: quotedMsg } : undefined));
  }
  return sent;
}

async function sendAudio(sock, jid, text, config, quotedMsg = null) {
  const audio = await generateEdgeTts(text, config);
  if (!audio) return null;
  return sock.sendMessage(
    jid,
    { audio, mimetype: "audio/ogg; codecs=opus", ptt: true },
    quotedMsg ? { quoted: quotedMsg } : undefined,
  );
}

async function sendImage(sock, jid, image, caption = "", quotedMsg = null) {
  return sock.sendMessage(
    jid,
    { image, caption: caption || undefined },
    quotedMsg ? { quoted: quotedMsg } : undefined,
  );
}

async function sendSmart(sock, jid, text, config, quotedMsg = null, options = {}) {
  const clean = formatForWhatsApp(text);
  if (!clean) return [];
  if (!options.forceText && shouldSendAudio(config, clean)) {
    const audioResult = await sendAudio(sock, jid, clean, config, quotedMsg).catch(() => null);
    if (audioResult) return [audioResult];
  }
  return sendText(sock, jid, clean, quotedMsg);
}

function shouldUpdateStream(now, lastUpdate, charsSinceUpdate, config) {
  const cfg = config.streaming || {};
  return now - lastUpdate >= (cfg.min_update_ms || 850) || charsSinceUpdate >= (cfg.min_update_chars || 80);
}

async function createStreamingResponder(sock, jid, config, quotedMsg = null) {
  const cfg = config.streaming || {};
  const canEdit = !!cfg.enabled && !!cfg.edit_first_message;
  let sentKey = null;
  let lastText = "";
  let lastUpdate = 0;
  let charsAtUpdate = 0;

  if (canEdit) {
    try {
      const first = await sock.sendMessage(jid, { text: cfg.initial_text || "..." }, quotedMsg ? { quoted: quotedMsg } : undefined);
      sentKey = first?.key || null;
    } catch {
      sentKey = null;
    }
  }

  async function update(fullText, force = false) {
    const formatted = formatForWhatsApp(fullText);
    if (!formatted || formatted === lastText) return;
    const now = Date.now();
    const charsSinceUpdate = Math.abs(formatted.length - charsAtUpdate);
    if (!force && !shouldUpdateStream(now, lastUpdate, charsSinceUpdate, config)) return;
    lastText = formatted;
    lastUpdate = now;
    charsAtUpdate = formatted.length;
    if (sentKey) {
      try {
        await sock.sendMessage(jid, { edit: sentKey, text: formatted });
        return;
      } catch {
        sentKey = null;
      }
    }
  }

  async function finish(fullText) {
    const formatted = formatForWhatsApp(fullText);
    if (!formatted) return [];
    if (sentKey) {
      try {
        await sock.sendMessage(jid, { edit: sentKey, text: formatted });
        return [{ key: sentKey }];
      } catch {
        sentKey = null;
      }
    }
    return sendSmart(sock, jid, formatted, config, quotedMsg, { forceText: true });
  }

  return { update, finish };
}

module.exports = { sendPresence, sendText, sendAudio, sendImage, sendSmart, createStreamingResponder };
