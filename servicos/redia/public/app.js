let config = null;
let statusPayload = null;
let voicesPayload = { voices: [] };
let activitySource = null;
let activityRows = [];
const HIDDEN_ACTIVITY_TYPES = new Set([
  "whatsapp:start",
  "whatsapp:connection",
  "whatsapp:qr",
  "whatsapp:connected",
  "whatsapp:disconnected",
  "whatsapp:reconnecting",
  "whatsapp:session_reset",
  "whatsapp:stopped",
  "whatsapp:error",
  "whatsapp:restart_error",
]);
const APP_BASE_PATH = location.pathname === "/redia" || location.pathname.startsWith("/redia/") ? "/redia" : "";
const NIM_PREFIX = "NIM - ";
const NVIDIA_LEGACY_SUFFIX = " (NVIDIA)";
const uiState = {
  testModel: "",
  benchmarkModels: [],
  dirty: false,
  refreshing: false,
};

const qs = (sel) => document.querySelector(sel);
let adminToken = window.localStorage.getItem("redia_admin_token") || "";

function appPath(path) {
  return `${APP_BASE_PATH}${path}`;
}

function normalizeProxyModelValue(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  if (text.startsWith(NIM_PREFIX)) return text;
  if (text.endsWith(NVIDIA_LEGACY_SUFFIX)) {
    return `${NIM_PREFIX}${text.slice(0, -NVIDIA_LEGACY_SUFFIX.length).trim()}`;
  }
  return text;
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (adminToken) headers.Authorization = `Bearer ${adminToken}`;
  const response = await fetch(appPath(path), {
    headers,
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (response.status === 401) {
    adminToken = window.prompt("Token administrativo da REDIA") || "";
    if (adminToken) {
      window.localStorage.setItem("redia_admin_token", adminToken);
      return api(path, options);
    }
  }
  if (!response.ok) throw new Error(payload.error || payload.detail || `HTTP ${response.status}`);
  return payload;
}

function setValue(id, value) {
  const el = qs(`#${id}`);
  if (!el) return;
  if (el.type === "checkbox") el.checked = !!value;
  else el.value = value ?? "";
}

function getValue(id) {
  const el = qs(`#${id}`);
  if (!el) return "";
  if (el.type === "checkbox") return !!el.checked;
  if (el.tagName === "SELECT" && el.multiple) return Array.from(el.selectedOptions).map((option) => option.value);
  return el.value;
}

function setSyncState(message, tone = "neutral") {
  const el = qs("#syncState");
  if (!el) return;
  el.textContent = message;
  el.className = `state-pill ${tone}`;
}

function setDirty(value) {
  uiState.dirty = !!value;
  const el = qs("#dirtyIndicator");
  if (!el) return;
  el.classList.toggle("hidden", !uiState.dirty);
  if (uiState.dirty) setSyncState("Alterações locais pendentes", "warning");
}

function markDirty() {
  setDirty(true);
}

function toast(message, tone = "info") {
  const host = qs("#toastHost");
  if (!host) return;
  const item = document.createElement("div");
  item.className = `toast ${tone}`;
  item.textContent = message;
  host.appendChild(item);
  window.requestAnimationFrame(() => item.classList.add("show"));
  window.setTimeout(() => {
    item.classList.remove("show");
    window.setTimeout(() => item.remove(), 220);
  }, 4200);
}

function setButtonBusy(buttonId, label) {
  const button = qs(`#${buttonId}`);
  if (!button) return () => {};
  const originalText = button.textContent;
  button.disabled = true;
  button.classList.add("is-busy");
  button.textContent = label;
  return () => {
    button.disabled = false;
    button.classList.remove("is-busy");
    button.textContent = originalText;
  };
}

function setActivityStatus(message, tone = "warning") {
  const el = qs("#activityStatus");
  if (!el) return;
  el.textContent = message;
  el.className = `state-pill ${tone}`;
}

function activityTone(event) {
  if (String(event.type || "").includes("error")) return "error";
  if (["model:done", "whatsapp:sent", "learning:done", "media:image:done", "media:audio:done"].includes(event.type)) return "success";
  if (["model:start", "model:stream", "queue:drain", "proactive:start"].includes(event.type)) return "warning";
  return "";
}

function activityTitle(event) {
  const titles = {
    "whatsapp:start": "WhatsApp iniciando",
    "whatsapp:connection": "Atualizacao de conexao",
    "whatsapp:qr": "QR Code gerado",
    "whatsapp:connected": "WhatsApp conectado",
    "whatsapp:disconnected": "WhatsApp desconectado",
    "whatsapp:reconnecting": "Reconexao agendada",
    "whatsapp:session_reset": "Sessao limpa",
    "whatsapp:stopped": "WhatsApp parado",
    "whatsapp:error": "Falha no WhatsApp",
    "whatsapp:restart_error": "Reconexao falhou",
    "model:start": "Modelo pensando",
    "model:stream": "Resposta em streaming",
    "model:done": "Modelo respondeu",
    "model:error": "Modelo falhou",
    "chat:attempt": "Tentando responder conversa",
    "context:policy": "Política de contexto",
    "quoted_reply": "Resposta a mensagem citada",
    "chat:error": "Tentativa falhou",
    "whatsapp:message": "Mensagem recebida",
    "whatsapp:decision": "REDIA decidiu responder",
    "whatsapp:ignored": "REDIA ignorou a mensagem",
    "whatsapp:sent": "Resposta enviada",
    "queue:drain": "Fila processada",
    "learning:start": "Aprendizado iniciado",
    "learning:done": "Memória atualizada",
    "learning:error": "Aprendizado falhou",
    "proactive:start": "Proativo analisando",
    "proactive:decision": "Proativo decidiu",
    "proactive:scheduled": "Proativo agendado",
    "proactive:error": "Proativo falhou",
    "media:image:start": "Analisando imagem",
    "media:image:done": "Imagem analisada",
    "media:image:error": "Imagem falhou",
    "media:audio:start": "Transcrevendo áudio",
    "media:audio:done": "Áudio transcrito",
    "media:audio:error": "Áudio falhou",
    "media:error": "Mídia falhou",
  };
  return titles[event.type] || event.type || "Atividade";
}

function activityPreview(event) {
  return event.error || event.response_preview || event.text_preview || event.prompt_preview || event.summary_preview || event.caption_preview || "";
}

function renderActivityEvent(event) {
  const at = event.at ? new Date(event.at).toLocaleTimeString("pt-BR") : "";
  const meta = [
    event.role,
    event.model,
    event.mode,
    event.context_policy,
    event.chat_name || event.chat_id,
    event.sender_name,
    event.latency_ms ? `${event.latency_ms}ms` : "",
    event.response_chars ? `${event.response_chars} chars` : "",
  ].filter(Boolean);
  const preview = activityPreview(event);
  return `
    <article class="activity-item ${activityTone(event)}">
      <div class="activity-top">
        <strong>${escapeHtml(activityTitle(event))}</strong>
        <time>${escapeHtml(at)}</time>
      </div>
      <div class="activity-meta">${meta.map((item) => `<span>${escapeHtml(item)}</span>`).join("<span>•</span>")}</div>
      ${preview ? `<p>${escapeHtml(preview)}</p>` : ""}
    </article>
  `;
}

function renderActivity() {
  const el = qs("#activityLog");
  if (!el) return;
  const visibleRows = activityRows.filter((item) => !HIDDEN_ACTIVITY_TYPES.has(String(item?.type || "")));
  el.innerHTML = visibleRows.slice().reverse().map(renderActivityEvent).join("");
}

function appendActivity(event) {
  if (!event?.id || activityRows.some((item) => item.id === event.id)) return;
  activityRows.push(event);
  if (activityRows.length > 160) activityRows = activityRows.slice(-160);
  renderActivity();
}

async function loadActivity() {
  const payload = await api("/api/activity?limit=160");
  activityRows = payload.events || [];
  renderActivity();
}

function connectActivityStream() {
  if (!window.EventSource) {
    setActivityStatus("SSE indisponível", "error");
    return;
  }
  if (activitySource) activitySource.close();
  const url = new URL(appPath("/api/events"), window.location.origin);
  if (adminToken) url.searchParams.set("token", adminToken);
  if (activityRows.length) url.searchParams.set("since", String(activityRows[activityRows.length - 1].id));
  setActivityStatus("Conectando", "warning");
  activitySource = new EventSource(url.toString());
  activitySource.onopen = () => setActivityStatus("Ao vivo", "success");
  activitySource.onerror = () => setActivityStatus("Reconectando", "warning");
  activitySource.addEventListener("activity", (message) => {
    try {
      appendActivity(JSON.parse(message.data));
    } catch {
      // ignore malformed event
    }
  });
}

function optionHtml(value, label = value) {
  return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
}

function sortAlpha(rows) {
  return [...(Array.isArray(rows) ? rows : [])].sort((a, b) => {
    const left = String(a || "").toLowerCase();
    const right = String(b || "").toLowerCase();
    if (left < right) return -1;
    if (left > right) return 1;
    return 0;
  });
}

function sortVoiceRows(rows) {
  return [...(Array.isArray(rows) ? rows : [])].sort((a, b) => {
    const left = String(a?.name || "").toLowerCase();
    const right = String(b?.name || "").toLowerCase();
    if (left < right) return -1;
    if (left > right) return 1;
    return 0;
  });
}

function setSelectOptions(id, rows, selectedValue, options = {}) {
  const el = qs(`#${id}`);
  if (!el) return;
  const allowCustom = options.allowCustom !== false;
  const customLabelOf = Object.prototype.hasOwnProperty.call(options, "labelOf") ? options.labelOf : null;
  const customValueOf = Object.prototype.hasOwnProperty.call(options, "valueOf") ? options.valueOf : null;
  const getValueForRow = customValueOf || ((row) => (typeof row === "string" ? row : row?.value || row?.name || ""));
  const getLabelForRow = customLabelOf || ((row) => (typeof row === "string" ? row : row?.label || row?.display_name || row?.name || row?.value || ""));
  const sourceRows = Array.isArray(rows) ? rows : [];
  const normalizedRows = sourceRows
    .filter((row) => row !== undefined && row !== null)
    .map((row) => {
      const originalValue = String(getValueForRow(row) || "").trim();
      const normalizedValue = normalizeProxyModelValue(originalValue);
      let label = String(getLabelForRow(row) || "").trim();
      if (label === originalValue) label = normalizedValue;
      if (label === `${originalValue} (configurado)`) label = `${normalizedValue} (configurado)`;
      return { value: normalizedValue, label };
    })
    .filter((row) => row.value);
  const seen = new Set();
  const uniqueRows = normalizedRows.filter((row) => {
    if (seen.has(row.value)) return false;
    seen.add(row.value);
    return true;
  });
  const selectedValues = Array.isArray(selectedValue)
    ? selectedValue.map((item) => normalizeProxyModelValue(item)).filter(Boolean)
    : [normalizeProxyModelValue(selectedValue)].filter(Boolean);
  for (const selected of selectedValues) {
    if (allowCustom && selected && !seen.has(selected)) {
      uniqueRows.unshift({ value: selected, label: `${selected} (configurado)` });
      seen.add(selected);
    }
  }
  el.innerHTML = uniqueRows.map((row) => optionHtml(row.value, row.label)).join("");
  if (el.multiple) {
    for (const option of el.options) option.selected = selectedValues.includes(option.value);
  } else if (selectedValues[0]) {
    el.value = selectedValues[0];
  }
}

function renderSttModelOptions(selectedValue = config?.stt?.model) {
  const sttModels = getValue("sttProvider") === "openai"
    ? ["whisper-1", "gpt-4o-mini-transcribe", "gpt-4o-transcribe"]
    : ["whisper-large-v3-turbo", "whisper-large-v3"];
  setSelectOptions("sttModel", sttModels, selectedValue, { allowCustom: true });
}

function renderDynamicOptions() {
  const models = sortAlpha(statusPayload?.proxy?.models || []);
  setSelectOptions("defaultModel", models, config?.chat?.default_model);
  setSelectOptions("visionModel", models, config?.chat?.vision_model);
  setSelectOptions("learningModel", models, config?.learning?.model);
  setSelectOptions("proactiveModel", models, config?.proactive?.model);
  setSelectOptions("fallbackModels", models, config?.chat?.fallback_models || []);
  const selectedTestModel = uiState.testModel || getValue("modelSelect") || config?.chat?.default_model;
  if (selectedTestModel) uiState.testModel = selectedTestModel;
  setSelectOptions("modelSelect", models, selectedTestModel);
  const currentBenchmarkSelection = uiState.benchmarkModels.length ? uiState.benchmarkModels : getValue("benchmarkModels");
  const selectedBenchmarkModels = Array.isArray(currentBenchmarkSelection) ? currentBenchmarkSelection : [];
  uiState.benchmarkModels = selectedBenchmarkModels;
  setSelectOptions("benchmarkModels", models, selectedBenchmarkModels);

  setSelectOptions(
    "ttsVoice",
    sortVoiceRows(voicesPayload.voices || []),
    config?.tts?.voice,
    {
      labelOf: (row) => `${row.name} - ${row.gender || ""}`.trim(),
      valueOf: (row) => row.name,
    },
  );
  setSelectOptions("ttsRate", ["-20%", "-15%", "-10%", "-5%", "0%", "+5%", "+10%", "+15%", "+20%"], config?.tts?.rate);
  setSelectOptions("ttsPitch", ["-12Hz", "-8Hz", "-4Hz", "+0Hz", "+4Hz", "+8Hz", "+12Hz"], config?.tts?.pitch);
  setSelectOptions("privateMode", ["always", "never"], config?.chat?.private_mode, { allowCustom: false });
  setSelectOptions("groupMode", ["prefix_or_mention", "always", "never"], config?.chat?.group_mode, { allowCustom: false });
  setSelectOptions("sttProvider", ["groq", "openai"], config?.stt?.provider, { allowCustom: true });
  renderSttModelOptions(config?.stt?.model);
}

function renderConfig() {
  if (!config) return;
  renderDynamicOptions();
  setValue("defaultModel", config.chat.default_model);
  setValue("visionModel", config.chat.vision_model);
  setValue("learningModel", config.learning.model);
  setValue("proactiveModel", config.proactive.model);
  setValue("ttsEnabled", config.tts.enabled);
  setValue("ttsProbability", Math.round(Number(config.tts.audio_probability || 0) * 100));
  setValue("ttsVoice", config.tts.voice);
  setValue("ttsRate", config.tts.rate);
  setValue("ttsPitch", config.tts.pitch);
  setValue("streamingEnabled", config.streaming.enabled && config.streaming.edit_first_message);
  setValue("learningEnabled", config.learning.enabled);
  setValue("proactiveEnabled", config.proactive.enabled);
  setValue("groupPrefix", config.chat.group_prefix);
  setValue("temperature", config.chat.temperature);
  setValue("privateMode", config.chat.private_mode);
  setValue("groupMode", config.chat.group_mode);
  setValue("sttEnabled", config.stt.enabled);
  setValue("sttApiKey", "");
  setValue("sttProvider", config.stt.provider);
  setValue("sttModel", config.stt.model);
  setValue("imageRequired", config.media.image_required);
  setValue("systemPrompt", config.chat.system_prompt);
}

function renderStatus() {
  const wa = statusPayload?.whatsapp || {};
  qs("#waStatus").textContent = `WhatsApp: ${wa.status || "desconhecido"}`;
  qs("#waPhone").textContent = wa.phone || "-";
  qs("#waCode").textContent = wa.last_disconnect_code ? String(wa.last_disconnect_code) : "-";
  qs("#waRetries").textContent = String(wa.reconnect_attempts || 0);
  qs("#waUpdatedAt").textContent = wa.last_update_at ? new Date(wa.last_update_at).toLocaleTimeString("pt-BR") : "-";
  qs("#waHint").textContent = wa.hint || "Aguardando estado da sessao.";
  qs("#waLastError").textContent = wa.last_error || "-";
  const proxyError = statusPayload?.proxy?.error || "";
  qs("#proxyStatus").textContent = proxyError ? "erro" : "online";
  qs("#modelCount").textContent = String((statusPayload?.proxy?.models || []).length);
  qs("#voiceCount").textContent = String((voicesPayload?.voices || []).length);
  const qrPanel = qs("#qrPanel");
  const qrImage = qs("#qrImage");
  if (wa.qr) {
    qrPanel.classList.remove("hidden");
    qrImage.src = wa.qr;
  } else {
    qrPanel.classList.add("hidden");
    qrImage.removeAttribute("src");
  }

  const models = sortAlpha(statusPayload?.proxy?.models || []);
  const selectedTestModel = uiState.testModel || getValue("modelSelect") || config?.chat?.default_model;
  if (selectedTestModel) uiState.testModel = selectedTestModel;
  setSelectOptions("modelSelect", models, selectedTestModel);

  qs("#runsList").innerHTML = (statusPayload?.runs || [])
    .map(
      (row) => `<div class="row"><strong>${escapeHtml(row.role)} / ${escapeHtml(row.model)}</strong><span>${row.ok ? "ok" : "erro"} - ${row.latency_ms}ms - ${row.response_chars} chars</span></div>`,
    )
    .join("");
}

async function refreshConversations() {
  const payload = await api("/api/conversations");
  qs("#conversationList").innerHTML = (payload.conversations || [])
    .map(
      (item) => `<div class="row"><strong>${escapeHtml(item.name || item.chat_id)}</strong><span>${escapeHtml(item.kind)} - ${escapeHtml(item.vibe || "Neutro")}</span></div>`,
    )
    .join("");
}

async function refreshAll(options = {}) {
  if (uiState.refreshing) return;
  uiState.refreshing = true;
  const shouldRenderConfig = options.force || !config || !uiState.dirty;
  try {
    setSyncState(uiState.dirty ? "Editando, sem sobrescrever campos" : "Sincronizando...", uiState.dirty ? "warning" : "neutral");
    if (shouldRenderConfig) config = await api("/api/config");
    statusPayload = await api("/api/status");
    voicesPayload = await api("/api/tts/voices").catch(() => ({ voices: [] }));
    if (shouldRenderConfig) renderConfig();
    renderStatus();
    refreshConversations().catch(() => {});
    setSyncState(uiState.dirty ? "Alterações locais pendentes" : "Sincronizado", uiState.dirty ? "warning" : "success");
  } catch (err) {
    setSyncState("Erro ao sincronizar", "error");
    toast(err.message || "Falha ao sincronizar o painel.", "error");
  } finally {
    uiState.refreshing = false;
  }
}

async function savePatch(patch, options = {}) {
  const releaseButton = options.buttonId ? setButtonBusy(options.buttonId, options.busyLabel || "Salvando...") : () => {};
  try {
    setSyncState("Salvando...", "neutral");
    config = await api("/api/config", { method: "PUT", body: JSON.stringify(patch) });
    statusPayload = await api("/api/status");
    voicesPayload = await api("/api/tts/voices").catch(() => voicesPayload || { voices: [] });
    setDirty(false);
    renderConfig();
    renderStatus();
    setSyncState("Salvo e sincronizado", "success");
    toast(options.successMessage || "Configuração salva.", "success");
    return config;
  } catch (err) {
    setSyncState("Erro ao salvar", "error");
    toast(err.message || "Falha ao salvar configuração.", "error");
    return null;
  } finally {
    releaseButton();
  }
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function wire() {
  qs("#startBtn").addEventListener("click", async () => {
    const releaseButton = setButtonBusy("startBtn", "Conectando...");
    try {
      await api("/api/whatsapp/start", { method: "POST", body: "{}" });
      toast("WhatsApp iniciado. QR atualizado no painel.", "success");
      await refreshAll();
    } catch (err) {
      toast(err.message || "Falha ao conectar WhatsApp.", "error");
    } finally {
      releaseButton();
    }
  });
  qs("#reconnectBtn").addEventListener("click", async () => {
    const releaseButton = setButtonBusy("reconnectBtn", "Reconectando...");
    try {
      await api("/api/whatsapp/reconnect", { method: "POST", body: JSON.stringify({ reset: false }) });
      toast("Reconexao iniciada. Se precisar, o QR aparece aqui.", "success");
      await refreshAll();
    } catch (err) {
      toast(err.message || "Falha ao reconectar WhatsApp.", "error");
    } finally {
      releaseButton();
    }
  });
  qs("#stopBtn").addEventListener("click", async () => {
    const releaseButton = setButtonBusy("stopBtn", "Parando...");
    try {
      await api("/api/whatsapp/stop", { method: "POST", body: "{}" });
      toast("WhatsApp parado.", "success");
      await refreshAll();
    } catch (err) {
      toast(err.message || "Falha ao parar WhatsApp.", "error");
    } finally {
      releaseButton();
    }
  });
  qs("#resetBtn").addEventListener("click", async () => {
    const releaseButton = setButtonBusy("resetBtn", "Limpando...");
    try {
      await api("/api/whatsapp/reconnect", { method: "POST", body: JSON.stringify({ reset: true }) });
      toast("Sessao limpa. Aguardando novo QR Code.", "success");
      await refreshAll();
    } catch (err) {
      toast(err.message || "Falha ao resetar a sessao.", "error");
    } finally {
      releaseButton();
    }
  });
  qs("#saveModelsBtn").addEventListener("click", () =>
    savePatch({
      chat: {
        default_model: getValue("defaultModel"),
        vision_model: getValue("visionModel"),
        fallback_models: getValue("fallbackModels"),
      },
      learning: { model: getValue("learningModel") },
      proactive: { model: getValue("proactiveModel") },
    }, { buttonId: "saveModelsBtn", successMessage: "Modelos salvos." }),
  );
  qs("#saveTtsBtn").addEventListener("click", () =>
    savePatch({
      tts: {
        enabled: getValue("ttsEnabled"),
        audio_probability: Number(getValue("ttsProbability") || 0) / 100,
        voice: getValue("ttsVoice"),
        rate: getValue("ttsRate"),
        pitch: getValue("ttsPitch"),
      },
    }, { buttonId: "saveTtsBtn", successMessage: "Voz salva." }),
  );
  qs("#saveBehaviorBtn").addEventListener("click", () =>
    savePatch({
      streaming: { enabled: getValue("streamingEnabled"), edit_first_message: getValue("streamingEnabled") },
      learning: { enabled: getValue("learningEnabled") },
      proactive: { enabled: getValue("proactiveEnabled") },
      chat: {
        group_prefix: getValue("groupPrefix"),
        temperature: Number(getValue("temperature") || 0.8),
        private_mode: getValue("privateMode"),
        group_mode: getValue("groupMode"),
      },
    }, { buttonId: "saveBehaviorBtn", successMessage: "Comportamento salvo." }),
  );
  qs("#saveMediaBtn").addEventListener("click", () =>
    {
      const apiKey = getValue("sttApiKey");
      return savePatch({
        stt: {
          enabled: getValue("sttEnabled"),
          provider: getValue("sttProvider"),
          model: getValue("sttModel"),
          ...(apiKey ? { api_key: apiKey } : {}),
        },
        media: { image_required: getValue("imageRequired") },
      }, { buttonId: "saveMediaBtn", successMessage: "Mídia e STT salvos." });
    },
  );
  qs("#sttProvider").addEventListener("change", () => renderSttModelOptions(""));
  qs("#modelSelect").addEventListener("change", () => {
    uiState.testModel = getValue("modelSelect");
  });
  qs("#benchmarkModels").addEventListener("change", () => {
    uiState.benchmarkModels = getValue("benchmarkModels");
  });
  qs("#savePromptBtn").addEventListener("click", () =>
    savePatch({ chat: { system_prompt: getValue("systemPrompt") } }, { buttonId: "savePromptBtn", successMessage: "Persona salva." }),
  );
  qs("#testBtn").addEventListener("click", async () => {
    const releaseButton = setButtonBusy("testBtn", "Testando...");
    qs("#testOutput").textContent = "testando...";
    const selectedModel = getValue("modelSelect");
    uiState.testModel = selectedModel;
    try {
      const payload = await api("/api/test-ai", {
        method: "POST",
        body: JSON.stringify({ model: selectedModel, prompt: getValue("testPrompt") }),
      });
      qs("#testOutput").textContent = `${payload.model} - ${payload.latency_ms}ms\n\n${payload.content}`;
      toast("Teste concluído.", "success");
      await refreshAll();
    } catch (err) {
      qs("#testOutput").textContent = err.message;
      toast(err.message || "Teste falhou.", "error");
    } finally {
      releaseButton();
    }
  });
  qs("#benchmarkBtn").addEventListener("click", async () => {
    const releaseButton = setButtonBusy("benchmarkBtn", "Rodando...");
    qs("#benchmarkOutput").textContent = "rodando...";
    uiState.benchmarkModels = getValue("benchmarkModels");
    try {
      const payload = await api("/api/benchmark", {
        method: "POST",
        body: JSON.stringify({
          models: uiState.benchmarkModels,
        }),
      });
      qs("#benchmarkOutput").textContent = JSON.stringify(payload.rows, null, 2);
      toast("Benchmark concluído.", "success");
      await refreshAll();
    } catch (err) {
      qs("#benchmarkOutput").textContent = err.message;
      toast(err.message || "Benchmark falhou.", "error");
    } finally {
      releaseButton();
    }
  });
  qs("#clearActivityBtn").addEventListener("click", () => {
    activityRows = [];
    renderActivity();
    toast("Log da tela limpo.", "info");
  });

  [
    "defaultModel",
    "visionModel",
    "learningModel",
    "proactiveModel",
    "fallbackModels",
    "ttsEnabled",
    "ttsProbability",
    "ttsVoice",
    "ttsRate",
    "ttsPitch",
    "streamingEnabled",
    "learningEnabled",
    "proactiveEnabled",
    "groupPrefix",
    "temperature",
    "privateMode",
    "groupMode",
    "sttEnabled",
    "sttApiKey",
    "sttProvider",
    "sttModel",
    "imageRequired",
    "systemPrompt",
  ].forEach((id) => {
    const el = qs(`#${id}`);
    if (!el) return;
    el.addEventListener("input", markDirty);
    el.addEventListener("change", markDirty);
  });
}

async function boot() {
  wire();
  await refreshAll({ force: true });
  await loadActivity().catch(() => {});
  connectActivityStream();
  setInterval(refreshAll, 10000);
}

boot();
