const { performance } = require("perf_hooks");
const activity = require("./activity");
const { LOCAL_PROXY_URL } = require("./defaultConfig");

function proxyUrl(config) {
  const fallback = String(LOCAL_PROXY_URL || "http://127.0.0.1:8080").replace(/\/+$/, "");
  const raw = String(config?.proxy?.base_url || "").trim();
  if (!raw) return fallback;
  try {
    const url = new URL(raw);
    const host = String(url.hostname || "").toLowerCase();
    const port = String(url.port || "");
    const path = String(url.pathname || "").replace(/\/+$/, "");
    const knownLegacyHosts = new Set(["redsystems.ddns.net", "200.98.201.66", "20.206.248.3", "127.0.0.1", "localhost"]);
    const legacyPath = path === "/proxy" || path === "/ollama";
    if (knownLegacyHosts.has(host) && (port === "8080" || legacyPath || host === "redsystems.ddns.net" || host === "200.98.201.66" || host === "20.206.248.3")) {
      return fallback;
    }
    return raw.replace(/\/+$/, "");
  } catch {
    return fallback;
  }
}

async function fetchJson(url, options = {}) {
  const resp = await fetch(url, options);
  const text = await resp.text();
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = { raw: text };
  }
  if (!resp.ok) {
    const message = payload?.error || payload?.message || text || `HTTP ${resp.status}`;
    throw new Error(message);
  }
  return payload;
}

async function listModels(config) {
  const payload = await fetchJson(`${proxyUrl(config)}/api/tags`, { method: "GET" });
  return (payload.models || [])
    .map((item) => item.name || item.model)
    .filter(Boolean)
    .sort((a, b) => {
      const left = String(a).toLowerCase();
      const right = String(b).toLowerCase();
      if (left < right) return -1;
      if (left > right) return 1;
      return 0;
    });
}

function normalizeMessages(messages) {
  return (messages || [])
    .filter((item) => item && item.role && item.content !== undefined)
    .map((item) => {
      const out = { role: item.role, content: String(item.content || "") };
      if (Array.isArray(item.images) && item.images.length) out.images = item.images;
      return out;
    });
}

function messageStats(messages) {
  const normalized = normalizeMessages(messages);
  return {
    messages: normalized,
    prompt_chars: normalized.reduce((sum, item) => sum + String(item.content || "").length, 0),
    image_count: normalized.reduce((sum, item) => sum + (Array.isArray(item.images) ? item.images.length : 0), 0),
  };
}

async function chatComplete(config, { model, messages, temperature, role = "chat", format = undefined, timeoutMs = undefined, meta = {} }) {
  const started = performance.now();
  const selectedModel = model || config.chat.default_model;
  const stats = messageStats(messages);
  const body = {
    model: selectedModel,
    messages: stats.messages,
    stream: false,
    options: {
      temperature: temperature ?? config.chat.temperature ?? 0.7,
    },
  };
  if (format) body.format = format;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs || config.proxy.timeout_ms || 90000);
  try {
    activity.publish("model:start", {
      ...meta,
      role,
      model: selectedModel,
      mode: "complete",
      prompt_chars: stats.prompt_chars,
      image_count: stats.image_count,
      temperature: body.options.temperature,
    });
    const payload = await fetchJson(`${proxyUrl(config)}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    const content = payload?.message?.content || payload?.response || "";
    const latency = Math.round(performance.now() - started);
    activity.publish("model:done", {
      ...meta,
      role,
      model: payload?.model || selectedModel,
      mode: "complete",
      latency_ms: latency,
      response_chars: content.length,
      response_preview: content,
    });
    return {
      ok: true,
      model: payload?.model || selectedModel,
      content,
      latency_ms: latency,
      role,
      raw: payload,
    };
  } catch (err) {
    activity.publish("model:error", {
      ...meta,
      role,
      model: selectedModel,
      mode: "complete",
      latency_ms: Math.round(performance.now() - started),
      error: err.message,
    });
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

async function chatStream(config, { model, messages, temperature, onToken, onPayload, role = "chat", meta = {} }) {
  const started = performance.now();
  const selectedModel = model || config.chat.default_model;
  const stats = messageStats(messages);
  const body = {
    model: selectedModel,
    messages: stats.messages,
    stream: true,
    options: {
      temperature: temperature ?? config.chat.temperature ?? 0.7,
    },
  };
  activity.publish("model:start", {
    ...meta,
    role,
    model: selectedModel,
    mode: "stream",
    prompt_chars: stats.prompt_chars,
    image_count: stats.image_count,
    temperature: body.options.temperature,
  });
  let resp;
  try {
    resp = await fetch(`${proxyUrl(config)}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    activity.publish("model:error", {
      ...meta,
      role,
      model: selectedModel,
      mode: "stream",
      latency_ms: Math.round(performance.now() - started),
      error: err.message,
    });
    throw err;
  }
  if (!resp.ok) {
    const error = await resp.text();
    activity.publish("model:error", {
      ...meta,
      role,
      model: selectedModel,
      mode: "stream",
      latency_ms: Math.round(performance.now() - started),
      error,
    });
    throw new Error(error);
  }

  const decoder = new TextDecoder();
  const reader = resp.body.getReader();
  let buffer = "";
  let fullText = "";
  let finalPayload = null;
  let lastStreamEventAt = 0;

  async function consumeLine(line) {
    const clean = line.trim();
    if (!clean) return;
    let payload;
    try {
      payload = JSON.parse(clean);
    } catch {
      return;
    }
    finalPayload = payload;
    if (onPayload) onPayload(payload);
    if (payload.error) throw new Error(String(payload.error));
    const token = payload?.message?.content || payload?.response || "";
    if (token) {
      fullText += token;
      const now = Date.now();
      if (now - lastStreamEventAt > 1200) {
        lastStreamEventAt = now;
        activity.publish("model:stream", {
          ...meta,
          role,
          model: payload?.model || selectedModel,
          mode: "stream",
          response_chars: fullText.length,
          response_preview: fullText,
        });
      }
      if (onToken) await onToken(token, fullText, payload);
    }
  }

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() || "";
      for (const line of lines) await consumeLine(line);
    }
    if (buffer.trim()) await consumeLine(buffer);
  } catch (err) {
    activity.publish("model:error", {
      ...meta,
      role,
      model: finalPayload?.model || selectedModel,
      mode: "stream",
      latency_ms: Math.round(performance.now() - started),
      response_chars: fullText.length,
      error: err.message,
    });
    throw err;
  }

  const result = {
    ok: true,
    model: finalPayload?.model || selectedModel,
    content: fullText,
    latency_ms: Math.round(performance.now() - started),
    role,
    raw: finalPayload,
  };
  activity.publish("model:done", {
    ...meta,
    role,
    model: result.model,
    mode: "stream",
    latency_ms: result.latency_ms,
    response_chars: result.content.length,
    response_preview: result.content,
  });
  return result;
}

module.exports = { listModels, chatComplete, chatStream };
