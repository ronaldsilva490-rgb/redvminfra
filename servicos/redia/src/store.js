const Database = require("better-sqlite3");
const { DEFAULT_CONFIG } = require("./defaultConfig");
const { dbPath, ensureDir } = require("./paths");
const { safeJsonParse, stableJson, deepMerge, nowIso } = require("./json");
const path = require("path");

let db = null;

function getDb() {
  if (!db) initStore();
  return db;
}

function initStore() {
  const file = dbPath();
  ensureDir(path.dirname(file));
  db = new Database(file);
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");
  db.exec(`
    CREATE TABLE IF NOT EXISTS app_config (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS conversations (
      chat_id TEXT PRIMARY KEY,
      kind TEXT NOT NULL DEFAULT 'private',
      name TEXT NOT NULL DEFAULT '',
      summary TEXT NOT NULL DEFAULT '',
      vibe TEXT NOT NULL DEFAULT 'Neutro',
      style TEXT NOT NULL DEFAULT '',
      topics TEXT NOT NULL DEFAULT '',
      context_hint TEXT NOT NULL DEFAULT '',
      pending_model_selection INTEGER NOT NULL DEFAULT 0,
      model TEXT NOT NULL DEFAULT '',
      last_message_at TEXT NOT NULL DEFAULT '',
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS messages (
      id TEXT PRIMARY KEY,
      chat_id TEXT NOT NULL,
      role TEXT NOT NULL,
      direction TEXT NOT NULL,
      sender_jid TEXT NOT NULL DEFAULT '',
      sender_name TEXT NOT NULL DEFAULT '',
      text TEXT NOT NULL DEFAULT '',
      content_type TEXT NOT NULL DEFAULT 'text',
      metadata_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL,
      FOREIGN KEY(chat_id) REFERENCES conversations(chat_id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_messages_chat_created ON messages(chat_id, created_at);

    CREATE TABLE IF NOT EXISTS memories (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      chat_id TEXT NOT NULL DEFAULT '',
      contact_jid TEXT NOT NULL DEFAULT '',
      fact TEXT NOT NULL,
      category TEXT NOT NULL DEFAULT 'geral',
      confidence REAL NOT NULL DEFAULT 0.7,
      source_message_id TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_memories_contact ON memories(contact_jid, updated_at);
    CREATE INDEX IF NOT EXISTS idx_memories_chat ON memories(chat_id, updated_at);

    CREATE TABLE IF NOT EXISTS profiles (
      contact_jid TEXT PRIMARY KEY,
      name TEXT NOT NULL DEFAULT '',
      nicknames_json TEXT NOT NULL DEFAULT '[]',
      style TEXT NOT NULL DEFAULT '',
      notes TEXT NOT NULL DEFAULT '',
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS conversation_learning_state (
      chat_id TEXT PRIMARY KEY,
      last_learned_message_count INTEGER NOT NULL DEFAULT 0,
      last_learned_at TEXT NOT NULL DEFAULT '',
      last_skipped_message_count INTEGER NOT NULL DEFAULT 0,
      updated_at TEXT NOT NULL,
      FOREIGN KEY(chat_id) REFERENCES conversations(chat_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS model_runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      role TEXT NOT NULL,
      model TEXT NOT NULL,
      prompt_chars INTEGER NOT NULL DEFAULT 0,
      response_chars INTEGER NOT NULL DEFAULT 0,
      latency_ms INTEGER NOT NULL DEFAULT 0,
      ok INTEGER NOT NULL DEFAULT 0,
      error TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS image_jobs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      status TEXT NOT NULL DEFAULT 'queued',
      chat_id TEXT NOT NULL DEFAULT '',
      requester_jid TEXT NOT NULL DEFAULT '',
      requester_name TEXT NOT NULL DEFAULT '',
      message_id TEXT NOT NULL DEFAULT '',
      original_prompt TEXT NOT NULL DEFAULT '',
      safe_prompt TEXT NOT NULL DEFAULT '',
      negative_prompt TEXT NOT NULL DEFAULT '',
      profile TEXT NOT NULL DEFAULT '',
      width INTEGER NOT NULL DEFAULT 768,
      height INTEGER NOT NULL DEFAULT 768,
      steps INTEGER NOT NULL DEFAULT 4,
      cfg REAL NOT NULL DEFAULT 1.5,
      result_path TEXT NOT NULL DEFAULT '',
      error TEXT NOT NULL DEFAULT '',
      worker_id TEXT NOT NULL DEFAULT '',
      metadata_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      claimed_at TEXT NOT NULL DEFAULT '',
      completed_at TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_image_jobs_status ON image_jobs(status, created_at);

    CREATE TABLE IF NOT EXISTS scheduled_messages (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      status TEXT NOT NULL DEFAULT 'scheduled',
      chat_id TEXT NOT NULL DEFAULT '',
      chat_name TEXT NOT NULL DEFAULT '',
      mode TEXT NOT NULL DEFAULT 'text',
      text TEXT NOT NULL DEFAULT '',
      prompt TEXT NOT NULL DEFAULT '',
      model TEXT NOT NULL DEFAULT '',
      send_at TEXT NOT NULL,
      metadata_json TEXT NOT NULL DEFAULT '{}',
      result_message_ids_json TEXT NOT NULL DEFAULT '[]',
      last_error TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      started_at TEXT NOT NULL DEFAULT '',
      completed_at TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_scheduled_messages_status_send_at ON scheduled_messages(status, send_at);
  `);

  const existing = db.prepare("SELECT value FROM app_config WHERE key = ?").get("config");
  if (!existing) {
    db.prepare("INSERT INTO app_config (key, value, updated_at) VALUES (?, ?, ?)").run(
      "config",
      stableJson(DEFAULT_CONFIG),
      nowIso(),
    );
  }
  return db;
}

function getConfig() {
  const row = getDb().prepare("SELECT value FROM app_config WHERE key = ?").get("config");
  return deepMerge(DEFAULT_CONFIG, safeJsonParse(row?.value, {}));
}

function saveConfig(partial) {
  const merged = deepMerge(getConfig(), partial || {});
  getDb().prepare(
    "INSERT INTO app_config (key, value, updated_at) VALUES ('config', ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
  ).run(stableJson(merged), nowIso());
  return merged;
}

function conversationKind(chatId) {
  return String(chatId || "").endsWith("@g.us") ? "group" : "private";
}

function ensureConversation(chatId, values = {}) {
  const id = String(chatId || "").trim();
  if (!id) throw new Error("chat_id is required");
  const now = nowIso();
  const existing = getDb().prepare("SELECT * FROM conversations WHERE chat_id = ?").get(id);
  if (!existing) {
    getDb().prepare(`
      INSERT INTO conversations (chat_id, kind, name, summary, vibe, style, topics, context_hint, model, last_message_at, updated_at)
      VALUES (?, ?, ?, '', 'Neutro', '', '', '', ?, '', ?)
    `).run(
      id,
      values.kind || conversationKind(id),
      values.name || "",
      values.model || "",
      now,
    );
  } else if (values.name && values.name !== existing.name) {
    getDb().prepare("UPDATE conversations SET name = ?, updated_at = ? WHERE chat_id = ?").run(values.name, now, id);
  }
  return getConversation(id);
}

function getConversation(chatId) {
  return getDb().prepare("SELECT * FROM conversations WHERE chat_id = ?").get(chatId);
}

function listConversations(limit = 80) {
  return getDb()
    .prepare("SELECT * FROM conversations ORDER BY COALESCE(NULLIF(last_message_at, ''), updated_at) DESC LIMIT ?")
    .all(limit);
}

function updateConversation(chatId, changes) {
  const allowed = ["name", "summary", "vibe", "style", "topics", "context_hint", "pending_model_selection", "model", "last_message_at"];
  const keys = Object.keys(changes || {}).filter((key) => allowed.includes(key));
  if (!keys.length) return getConversation(chatId);
  const set = keys.map((key) => `${key} = @${key}`).join(", ");
  getDb().prepare(`UPDATE conversations SET ${set}, updated_at = @updated_at WHERE chat_id = @chat_id`).run({
    ...changes,
    pending_model_selection: changes.pending_model_selection ? 1 : 0,
    updated_at: nowIso(),
    chat_id: chatId,
  });
  return getConversation(chatId);
}

function appendMessage(message) {
  const now = nowIso();
  const chatId = String(message.chat_id || "").trim();
  ensureConversation(chatId, { kind: message.kind, name: message.chat_name });
  const id = String(message.id || `${chatId}:${Date.now()}:${Math.random()}`);
  const payload = {
    id,
    chat_id: chatId,
    role: message.role || "user",
    direction: message.direction || "incoming",
    sender_jid: message.sender_jid || "",
    sender_name: message.sender_name || "",
    text: message.text || "",
    content_type: message.content_type || "text",
    metadata_json: stableJson(message.metadata || {}),
    created_at: message.created_at || now,
  };
  const result = getDb().prepare(`
    INSERT OR IGNORE INTO messages
    (id, chat_id, role, direction, sender_jid, sender_name, text, content_type, metadata_json, created_at)
    VALUES (@id, @chat_id, @role, @direction, @sender_jid, @sender_name, @text, @content_type, @metadata_json, @created_at)
  `).run(payload);
  if (result.changes) {
    updateConversation(chatId, { last_message_at: payload.created_at });
  }
  return result.changes > 0;
}

function recentMessages(chatId, limit = 24) {
  return getDb()
    .prepare("SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?")
    .all(chatId, limit)
    .reverse()
    .map((row) => ({ ...row, metadata: safeJsonParse(row.metadata_json, {}) }));
}

function countMessages(chatId) {
  return getDb().prepare("SELECT COUNT(*) AS count FROM messages WHERE chat_id = ?").get(chatId)?.count || 0;
}

function addMemory(memory) {
  const fact = String(memory.fact || "").trim();
  if (fact.length < 4) return null;
  const now = nowIso();
  const normalizeFact = (value) =>
    String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^\w\s]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  const factNorm = normalizeFact(fact);
  const candidates = getDb()
    .prepare("SELECT id, fact FROM memories WHERE contact_jid = ? OR chat_id = ? ORDER BY updated_at DESC LIMIT 80")
    .all(memory.contact_jid || "", memory.chat_id || "");
  const duplicate = candidates.find((item) => normalizeFact(item.fact) === factNorm);
  if (duplicate) {
    getDb().prepare("UPDATE memories SET confidence = MIN(confidence + 0.08, 1.0), updated_at = ? WHERE id = ?").run(now, duplicate.id);
    return duplicate.id;
  }
  const result = getDb().prepare(`
    INSERT INTO memories (chat_id, contact_jid, fact, category, confidence, source_message_id, created_at, updated_at)
    VALUES (@chat_id, @contact_jid, @fact, @category, @confidence, @source_message_id, @created_at, @updated_at)
  `).run({
    chat_id: memory.chat_id || "",
    contact_jid: memory.contact_jid || "",
    fact,
    category: memory.category || "geral",
    confidence: Number(memory.confidence || 0.7),
    source_message_id: memory.source_message_id || "",
    created_at: now,
    updated_at: now,
  });
  return result.lastInsertRowid;
}

function getMemories({ chatId = "", contactJid = "", limit = 12 } = {}) {
  if (contactJid) {
    return getDb()
      .prepare("SELECT * FROM memories WHERE contact_jid = ? ORDER BY updated_at DESC LIMIT ?")
      .all(contactJid, limit);
  }
  return getDb()
    .prepare("SELECT * FROM memories WHERE chat_id = ? ORDER BY updated_at DESC LIMIT ?")
    .all(chatId, limit);
}

function getLearningState(chatId) {
  ensureConversation(chatId);
  const row = getDb().prepare("SELECT * FROM conversation_learning_state WHERE chat_id = ?").get(chatId);
  if (row) return row;
  const now = nowIso();
  getDb()
    .prepare(
      "INSERT INTO conversation_learning_state (chat_id, last_learned_message_count, last_learned_at, last_skipped_message_count, updated_at) VALUES (?, 0, '', 0, ?)",
    )
    .run(chatId, now);
  return getDb().prepare("SELECT * FROM conversation_learning_state WHERE chat_id = ?").get(chatId);
}

function saveLearningState(chatId, changes = {}) {
  const current = getLearningState(chatId);
  const payload = {
    chat_id: chatId,
    last_learned_message_count: Number(changes.last_learned_message_count ?? current.last_learned_message_count ?? 0),
    last_learned_at: changes.last_learned_at ?? current.last_learned_at ?? "",
    last_skipped_message_count: Number(changes.last_skipped_message_count ?? current.last_skipped_message_count ?? 0),
    updated_at: nowIso(),
  };
  getDb()
    .prepare(
      `INSERT INTO conversation_learning_state
      (chat_id, last_learned_message_count, last_learned_at, last_skipped_message_count, updated_at)
      VALUES (@chat_id, @last_learned_message_count, @last_learned_at, @last_skipped_message_count, @updated_at)
      ON CONFLICT(chat_id) DO UPDATE SET
        last_learned_message_count=excluded.last_learned_message_count,
        last_learned_at=excluded.last_learned_at,
        last_skipped_message_count=excluded.last_skipped_message_count,
        updated_at=excluded.updated_at`,
    )
    .run(payload);
  return getLearningState(chatId);
}

function getProfile(contactJid) {
  const row = getDb().prepare("SELECT * FROM profiles WHERE contact_jid = ?").get(contactJid || "");
  if (!row) return null;
  return { ...row, nicknames: safeJsonParse(row.nicknames_json, []) };
}

function upsertProfile(profile = {}) {
  const contactJid = String(profile.contact_jid || profile.jid || "").trim();
  if (!contactJid) return null;
  const existing = getProfile(contactJid);
  const displayName = String(profile.name || existing?.name || "").trim();
  const nicknames = [
    ...(Array.isArray(existing?.nicknames) ? existing.nicknames : []),
    displayName,
    ...(Array.isArray(profile.nicknames) ? profile.nicknames : []),
  ]
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  const uniqueNicknames = [...new Set(nicknames)].slice(0, 12);
  const payload = {
    contact_jid: contactJid,
    name: String(profile.name || existing?.name || "").slice(0, 120),
    nicknames_json: stableJson(uniqueNicknames),
    style: String(profile.style || profile.communication_style || existing?.style || "").slice(0, 600),
    notes: String(profile.notes || profile.personality_traits || existing?.notes || "").slice(0, 1200),
    updated_at: nowIso(),
  };
  getDb()
    .prepare(
      `INSERT INTO profiles (contact_jid, name, nicknames_json, style, notes, updated_at)
      VALUES (@contact_jid, @name, @nicknames_json, @style, @notes, @updated_at)
      ON CONFLICT(contact_jid) DO UPDATE SET
        name=excluded.name,
        nicknames_json=excluded.nicknames_json,
        style=excluded.style,
        notes=excluded.notes,
        updated_at=excluded.updated_at`,
    )
    .run(payload);
  return getProfile(contactJid);
}

function saveModelRun(row) {
  getDb().prepare(`
    INSERT INTO model_runs (role, model, prompt_chars, response_chars, latency_ms, ok, error, created_at)
    VALUES (@role, @model, @prompt_chars, @response_chars, @latency_ms, @ok, @error, @created_at)
  `).run({
    role: row.role || "chat",
    model: row.model || "",
    prompt_chars: row.prompt_chars || 0,
    response_chars: row.response_chars || 0,
    latency_ms: row.latency_ms || 0,
    ok: row.ok ? 1 : 0,
    error: row.error || "",
    created_at: nowIso(),
  });
}

function modelRuns(limit = 80) {
  return getDb().prepare("SELECT * FROM model_runs ORDER BY created_at DESC LIMIT ?").all(limit);
}

function createImageJob(job = {}) {
  const now = nowIso();
  const payload = {
    status: "queued",
    chat_id: job.chat_id || "",
    requester_jid: job.requester_jid || "",
    requester_name: job.requester_name || "",
    message_id: job.message_id || "",
    original_prompt: String(job.original_prompt || "").slice(0, 3000),
    safe_prompt: String(job.safe_prompt || "").slice(0, 5000),
    negative_prompt: String(job.negative_prompt || "").slice(0, 3000),
    profile: job.profile || "",
    width: Number(job.width || 768),
    height: Number(job.height || 768),
    steps: Number(job.steps || 4),
    cfg: Number(job.cfg || 1.5),
    result_path: "",
    error: "",
    worker_id: "",
    metadata_json: stableJson(job.metadata || {}),
    created_at: now,
    updated_at: now,
    claimed_at: "",
    completed_at: "",
  };
  const result = getDb()
    .prepare(
      `INSERT INTO image_jobs
      (status, chat_id, requester_jid, requester_name, message_id, original_prompt, safe_prompt, negative_prompt, profile,
       width, height, steps, cfg, result_path, error, worker_id, metadata_json, created_at, updated_at, claimed_at, completed_at)
      VALUES
      (@status, @chat_id, @requester_jid, @requester_name, @message_id, @original_prompt, @safe_prompt, @negative_prompt, @profile,
       @width, @height, @steps, @cfg, @result_path, @error, @worker_id, @metadata_json, @created_at, @updated_at, @claimed_at, @completed_at)`,
    )
    .run(payload);
  return getImageJob(result.lastInsertRowid);
}

function getImageJob(id) {
  const row = getDb().prepare("SELECT * FROM image_jobs WHERE id = ?").get(Number(id || 0));
  if (!row) return null;
  return { ...row, metadata: safeJsonParse(row.metadata_json, {}) };
}

function listImageJobs(limit = 80) {
  return getDb()
    .prepare("SELECT * FROM image_jobs ORDER BY id DESC LIMIT ?")
    .all(Number(limit || 80))
    .map((row) => ({ ...row, metadata: safeJsonParse(row.metadata_json, {}) }));
}

function pendingImageJobCount() {
  return getDb().prepare("SELECT COUNT(*) AS count FROM image_jobs WHERE status IN ('queued', 'claimed', 'generating')").get()?.count || 0;
}

function claimImageJob(workerId = "") {
  const now = nowIso();
  const dbi = getDb();
  const tx = dbi.transaction(() => {
    const job = dbi
      .prepare("SELECT * FROM image_jobs WHERE status = 'queued' ORDER BY id ASC LIMIT 1")
      .get();
    if (!job) return null;
    dbi.prepare("UPDATE image_jobs SET status = 'claimed', worker_id = ?, claimed_at = ?, updated_at = ? WHERE id = ?").run(
      workerId,
      now,
      now,
      job.id,
    );
    return getImageJob(job.id);
  });
  return tx();
}

function markImageJobGenerating(id, workerId = "") {
  const now = nowIso();
  getDb()
    .prepare("UPDATE image_jobs SET status = 'generating', worker_id = COALESCE(NULLIF(?, ''), worker_id), updated_at = ? WHERE id = ?")
    .run(workerId, now, Number(id || 0));
  return getImageJob(id);
}

function completeImageJob(id, { result_path = "", worker_id = "", metadata = {} } = {}) {
  const now = nowIso();
  const current = getImageJob(id);
  getDb()
    .prepare(
      `UPDATE image_jobs
       SET status = 'completed', result_path = ?, worker_id = COALESCE(NULLIF(?, ''), worker_id),
           metadata_json = ?, updated_at = ?, completed_at = ?
       WHERE id = ?`,
    )
    .run(
      result_path,
      worker_id,
      stableJson({ ...(current?.metadata || {}), ...(metadata || {}) }),
      now,
      now,
      Number(id || 0),
    );
  return getImageJob(id);
}

function failImageJob(id, error, workerId = "") {
  const now = nowIso();
  getDb()
    .prepare("UPDATE image_jobs SET status = 'failed', error = ?, worker_id = COALESCE(NULLIF(?, ''), worker_id), updated_at = ?, completed_at = ? WHERE id = ?")
    .run(String(error || "image job failed").slice(0, 2000), workerId, now, now, Number(id || 0));
  return getImageJob(id);
}

function mapScheduledMessage(row) {
  if (!row) return null;
  return {
    ...row,
    metadata: safeJsonParse(row.metadata_json, {}),
    result_message_ids: safeJsonParse(row.result_message_ids_json, []),
  };
}

function getScheduledMessage(id) {
  const row = getDb().prepare("SELECT * FROM scheduled_messages WHERE id = ?").get(Number(id || 0));
  return mapScheduledMessage(row);
}

function listScheduledMessages(limit = 80) {
  return getDb()
    .prepare("SELECT * FROM scheduled_messages ORDER BY datetime(send_at) ASC, id DESC LIMIT ?")
    .all(Number(limit || 80))
    .map(mapScheduledMessage);
}

function createScheduledMessage(job = {}) {
  const now = nowIso();
  const payload = {
    status: "scheduled",
    chat_id: String(job.chat_id || job.to || "").trim(),
    chat_name: String(job.chat_name || "").trim(),
    mode: String(job.mode || "text").trim() || "text",
    text: String(job.text || "").slice(0, 8000),
    prompt: String(job.prompt || "").slice(0, 8000),
    model: String(job.model || "").trim(),
    send_at: String(job.send_at || now),
    metadata_json: stableJson(job.metadata || {}),
    result_message_ids_json: "[]",
    last_error: "",
    created_at: now,
    updated_at: now,
    started_at: "",
    completed_at: "",
  };
  const result = getDb()
    .prepare(
      `INSERT INTO scheduled_messages
      (status, chat_id, chat_name, mode, text, prompt, model, send_at, metadata_json, result_message_ids_json, last_error, created_at, updated_at, started_at, completed_at)
      VALUES
      (@status, @chat_id, @chat_name, @mode, @text, @prompt, @model, @send_at, @metadata_json, @result_message_ids_json, @last_error, @created_at, @updated_at, @started_at, @completed_at)`,
    )
    .run(payload);
  return getScheduledMessage(result.lastInsertRowid);
}

function claimDueScheduledMessage(referenceIso = nowIso()) {
  const dbi = getDb();
  const tx = dbi.transaction(() => {
    const row = dbi
      .prepare(
        `SELECT * FROM scheduled_messages
         WHERE status = 'scheduled' AND datetime(send_at) <= datetime(?)
         ORDER BY datetime(send_at) ASC, id ASC
         LIMIT 1`,
      )
      .get(referenceIso);
    if (!row) return null;
    dbi
      .prepare("UPDATE scheduled_messages SET status = 'running', started_at = ?, updated_at = ?, last_error = '' WHERE id = ?")
      .run(referenceIso, referenceIso, row.id);
    return getScheduledMessage(row.id);
  });
  return tx();
}

function completeScheduledMessage(id, { result_message_ids = [], metadata = {} } = {}) {
  const now = nowIso();
  const current = getScheduledMessage(id);
  getDb()
    .prepare(
      `UPDATE scheduled_messages
       SET status = 'completed',
           result_message_ids_json = ?,
           metadata_json = ?,
           updated_at = ?,
           completed_at = ?,
           last_error = ''
       WHERE id = ?`,
    )
    .run(
      stableJson(Array.isArray(result_message_ids) ? result_message_ids : []),
      stableJson({ ...(current?.metadata || {}), ...(metadata || {}) }),
      now,
      now,
      Number(id || 0),
    );
  return getScheduledMessage(id);
}

function failScheduledMessage(id, error) {
  const now = nowIso();
  getDb()
    .prepare(
      "UPDATE scheduled_messages SET status = 'failed', last_error = ?, updated_at = ?, completed_at = ? WHERE id = ?",
    )
    .run(String(error || "scheduled message failed").slice(0, 2000), now, now, Number(id || 0));
  return getScheduledMessage(id);
}

function cancelScheduledMessage(id) {
  const now = nowIso();
  getDb()
    .prepare(
      "UPDATE scheduled_messages SET status = 'canceled', updated_at = ?, completed_at = ? WHERE id = ? AND status IN ('scheduled', 'running', 'failed')",
    )
    .run(now, now, Number(id || 0));
  return getScheduledMessage(id);
}

module.exports = {
  initStore,
  getDb,
  getConfig,
  saveConfig,
  ensureConversation,
  getConversation,
  listConversations,
  updateConversation,
  appendMessage,
  recentMessages,
  countMessages,
  addMemory,
  getMemories,
  getLearningState,
  saveLearningState,
  getProfile,
  upsertProfile,
  saveModelRun,
  modelRuns,
  createImageJob,
  getImageJob,
  listImageJobs,
  pendingImageJobCount,
  claimImageJob,
  markImageJobGenerating,
  completeImageJob,
  failImageJob,
  getScheduledMessage,
  listScheduledMessages,
  createScheduledMessage,
  claimDueScheduledMessage,
  completeScheduledMessage,
  failScheduledMessage,
  cancelScheduledMessage,
};
