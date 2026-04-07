const { EventEmitter } = require("events");

const emitter = new EventEmitter();
emitter.setMaxListeners(200);

const MAX_EVENTS = 500;
let nextId = 1;
const events = [];

function clip(value, limit = 1400) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit - 1)}...` : text;
}

function sanitize(payload = {}) {
  const out = {};
  for (const [key, value] of Object.entries(payload || {})) {
    if (value === undefined || value === null) continue;
    if (typeof value === "string") {
      const limit = key.includes("preview") || key.includes("summary") ? 1600 : 600;
      out[key] = clip(value, limit);
    } else if (typeof value === "number" || typeof value === "boolean") {
      out[key] = value;
    } else if (Array.isArray(value)) {
      out[key] = value.slice(0, 20).map((item) => clip(item, 300));
    } else {
      out[key] = clip(JSON.stringify(value), 1000);
    }
  }
  return out;
}

function publish(type, payload = {}) {
  const event = {
    id: nextId++,
    at: new Date().toISOString(),
    type,
    ...sanitize(payload),
  };
  events.push(event);
  while (events.length > MAX_EVENTS) events.shift();
  emitter.emit("event", event);
  return event;
}

function recent(limit = 120) {
  return events.slice(-limit);
}

function writeSse(res, event) {
  res.write(`id: ${event.id}\n`);
  res.write("event: activity\n");
  res.write(`data: ${JSON.stringify(event)}\n\n`);
}

function stream(req, res) {
  res.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache, no-transform",
    Connection: "keep-alive",
    "X-Accel-Buffering": "no",
  });

  const since = Number(req.headers["last-event-id"] || req.query.since || 0);
  for (const event of events.filter((item) => item.id > since)) writeSse(res, event);

  const onEvent = (event) => writeSse(res, event);
  emitter.on("event", onEvent);
  const heartbeat = setInterval(() => res.write(": keepalive\n\n"), 25000);

  req.on("close", () => {
    clearInterval(heartbeat);
    emitter.off("event", onEvent);
  });
}

module.exports = { publish, recent, stream, clip };
