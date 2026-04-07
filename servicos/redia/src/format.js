function normalizeText(value) {
  return String(value || "")
    .normalize("NFC")
    .replace(/\ufeff/g, "")
    .replace(/\u200b/g, "");
}

function foldText(value) {
  return normalizeText(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function formatForWhatsApp(value) {
  let text = normalizeText(value).replace(/\r\n/g, "\n");
  text = text.replace(/<br\s*\/?>/gi, "\n");
  text = text.replace(/<\/p>\s*<p>/gi, "\n\n");
  text = text.replace(/<p[^>]*>/gi, "").replace(/<\/p>/gi, "");
  text = text.replace(/<li[^>]*>\s*/gi, "- ").replace(/<\/li>/gi, "\n");
  text = text.replace(/<strong[^>]*>([\s\S]*?)<\/strong>/gi, "*$1*");
  text = text.replace(/<b[^>]*>([\s\S]*?)<\/b>/gi, "*$1*");
  text = text.replace(/<em[^>]*>([\s\S]*?)<\/em>/gi, "_$1_");
  text = text.replace(/<i[^>]*>([\s\S]*?)<\/i>/gi, "_$1_");
  text = text.replace(/<code[^>]*>([\s\S]*?)<\/code>/gi, "```$1```");
  text = text.replace(/<[^>]+>/g, "");
  text = text.replace(/```(\w+)?\n/g, "```\n");
  text = text.replace(/^#{1,6}\s*/gm, "");
  text = text.replace(/\*\*(.*?)\*\*/g, "*$1*");
  text = text.replace(/__(.*?)__/g, "_$1_");
  text = text.replace(/~~(.*?)~~/g, "~$1~");
  text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, "$1: $2");
  text = text
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
  text = text.replace(/^\s*[-*]\s+/gm, "- ");
  text = text.replace(/^\s*\d+\.\s+/gm, "- ");
  text = text.replace(/\n{3,}/g, "\n\n");
  return text.trim();
}

function splitWhatsAppText(value, maxChars = 3500) {
  const text = formatForWhatsApp(value);
  if (!text) return [];
  if (text.length <= maxChars) return [text];
  const blocks = text.split("\n\n");
  const chunks = [];
  let current = "";
  for (const block of blocks) {
    const candidate = current ? `${current}\n\n${block}` : block;
    if (candidate.length <= maxChars) {
      current = candidate;
      continue;
    }
    if (current) chunks.push(current);
    if (block.length <= maxChars) {
      current = block;
      continue;
    }
    for (let start = 0; start < block.length; start += maxChars) {
      chunks.push(block.slice(start, start + maxChars));
    }
    current = "";
  }
  if (current) chunks.push(current);
  return chunks.filter(Boolean);
}

function stripGroupTrigger(text, prefix, mentioned) {
  const clean = normalizeText(text).trim();
  if (!clean) return { triggered: false, prompt: "" };
  const base = normalizeText(prefix || "").trim().replace(/[\s,;:._-]+$/, "");
  if (base) {
    const start = new RegExp(`^\\s*${escapeRegExp(base)}(?:[\\s,;:._-]+|$)`, "i");
    const end = new RegExp(`(?:^|[\\s,;:._-]+)${escapeRegExp(base)}\\s*$`, "i");
    const startMatch = clean.match(start);
    if (startMatch) return { triggered: true, prompt: trimTrigger(clean.slice(startMatch[0].length)) };
    const endMatch = clean.match(end);
    if (endMatch) return { triggered: true, prompt: trimTrigger(clean.slice(0, endMatch.index)) };
  }
  if (mentioned) return { triggered: true, prompt: trimTrigger(clean.replace(/@\S+/g, "")) || clean };
  return { triggered: false, prompt: clean };
}

function trimTrigger(value) {
  return String(value || "").replace(/^[\s,;:._-]+|[\s,;:._-]+$/g, "");
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

module.exports = { normalizeText, foldText, formatForWhatsApp, splitWhatsAppText, stripGroupTrigger };
