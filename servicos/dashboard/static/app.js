const state = {
    system: null,
    telemetry: null,
    services: [],
    docker: { available: false, containers: [], images: [] },
    processes: [],
    firewall: { enabled: false, raw: [] },
    proxy: null,
    whatsapp: null,
    projects: [],
    selectedProjectId: "",
    selectedWhatsAppConversationId: "",
    whatsappConversationDetail: null,
    whatsappTab: "connection",
    projectWizardMode: "simple",
    proxyLogs: [],
    proxyChat: {
        conversations: [],
        activeConversationId: "",
        pending: false,
        stopping: false,
        activeRequestId: "",
        activeRequestConversationId: "",
    },
    proxyImage: {
        generating: false,
        model: "",
        prompt: "A cinematic red robot mascot holding a glowing phone, dark futuristic server room, RED Systems brand colors, high detail",
        width: 1024,
        height: 1024,
        steps: 4,
        seed: "",
        imageBase64: "",
        mimeType: "image/jpeg",
        durationMs: 0,
        error: "",
    },
    vmAssistant: {
        model: "",
        messages: [],
        pending: false,
        stopping: false,
        activeRequestId: "",
    },
    journal: [],
    socket: null,
    currentView: "overview",
    currentProxyTab: "chat",
    currentFilePath: "/",
    currentContainerLogs: [],
    terminalSessionId: null,
    whatsappUi: {
        configDirty: false,
    },
};

const PROXY_CHAT_STORAGE_KEY = "redvm.proxyChat.v2";
const VM_ASSISTANT_STORAGE_KEY = "redvm.vmAssistant.v1";
const PROJECT_WIZARD_MODE_KEY = "redvm.projects.mode.v1";
const WHATSAPP_TAB_STORAGE_KEY = "redvm.whatsapp.tab.v1";
const APP_BASE_PATH = window.location.pathname === "/dashboard" || window.location.pathname.startsWith("/dashboard/")
    ? "/dashboard"
    : "";
const IMPORTANT_SERVICES = [
    "nginx.service",
    "docker.service",
    "ssh.service",
    "red-ollama-proxy.service",
    "redia.service",
    "redtrader.service",
    "red-proxy-lab.service",
    "red-iq-vision-bridge.service",
    "rapidleech.service",
];

function qs(selector) {
    return document.querySelector(selector);
}

function qsa(selector) {
    return Array.from(document.querySelectorAll(selector));
}

function escapeHtml(text) {
    return String(text ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function stripAnsi(text) {
    return String(text ?? "")
        .replace(/\u001B\[[0-9;?]*[ -/]*[@-~]/g, "")
        .replace(/\u001B\][^\u0007]*(\u0007|\u001B\\)/g, "")
        .replace(/\u001B=/g, "")
        .replace(/\u001B>/g, "");
}

function formatBytes(bytes) {
    const value = Number(bytes || 0);
    if (!value) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const power = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
    return `${(value / (1024 ** power)).toFixed(power === 0 ? 0 : 1)} ${units[power]}`;
}

function formatDate(value) {
    if (!value) return "n/d";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString("pt-BR");
}

function formatUptime(seconds) {
    const total = Math.max(0, Math.round(Number(seconds || 0)));
    const days = Math.floor(total / 86400);
    const hours = Math.floor((total % 86400) / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    if (days > 0) return `${days}d ${hours}h`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
}

function formatSeconds(seconds) {
    const total = Math.max(0, Number(seconds || 0));
    if (!total) return "sem cooldown";
    if (total < 60) return `${Math.round(total)}s`;
    const minutes = Math.floor(total / 60);
    return `${minutes}m ${Math.round(total % 60)}s`;
}

function formatMilliseconds(ms) {
    const total = Math.max(0, Number(ms || 0));
    if (!total) return "0ms";
    if (total < 1000) return `${Math.round(total)}ms`;
    return `${(total / 1000).toFixed(total < 10000 ? 2 : 1)}s`;
}

function levelClass(value) {
    if (value >= 85) return "danger";
    if (value >= 60) return "warning";
    return "ok";
}

function translateAction(action) {
    return {
        start: "iniciar",
        stop: "parar",
        restart: "reiniciar",
        enable: "habilitar",
        disable: "desabilitar",
        remove: "remover",
    }[action] || action;
}

function translateServiceState(value) {
    return {
        active: "ativo",
        inactive: "inativo",
        failed: "falhou",
        activating: "ativando",
        deactivating: "desativando",
        running: "rodando",
        exited: "encerrado",
        dead: "morto",
        loaded: "carregado",
        enabled: "habilitado",
        disabled: "desabilitado",
        static: "estático",
    }[value] || value;
}

function translateContainerStatus(value) {
    return {
        running: "em execução",
        exited: "parado",
        created: "criado",
        restarting: "reiniciando",
        paused: "pausado",
        removing: "removendo",
        dead: "morto",
    }[value] || value;
}

function showToast(message, tone = "info") {
    const stack = qs("#toastStack");
    if (!stack) return;
    const item = document.createElement("div");
    item.className = `toast ${tone}`;
    item.textContent = message;
    stack.appendChild(item);
    setTimeout(() => item.remove(), 4000);
}

async function runUiTask(task) {
    try {
        await task();
    } catch (error) {
        showToast(error.message || "Ação falhou.", "error");
    }
}

function captureScrollState(element, threshold = 48) {
    if (!element) return { top: 0, nearBottom: true };
    const distance = element.scrollHeight - element.clientHeight - element.scrollTop;
    return {
        top: element.scrollTop,
        nearBottom: distance <= threshold,
    };
}

function restoreScrollState(element, memory) {
    if (!element || !memory) return;
    if (memory.nearBottom) {
        element.scrollTop = element.scrollHeight;
        return;
    }
    const maxTop = Math.max(0, element.scrollHeight - element.clientHeight);
    element.scrollTop = Math.min(memory.top, maxTop);
}

function replaceScrollableContent(element, content) {
    const memory = captureScrollState(element);
    element.innerHTML = content;
    restoreScrollState(element, memory);
}

function whatsappConfigFieldSelectors() {
    return [
        "#whatsappBaseUrlInput",
        "#whatsappApiKeyInput",
        "#whatsappInstanceNameInput",
        "#whatsappInstanceTokenInput",
        "#whatsappBotNumberInput",
        "#whatsappWebhookSecretInput",
        "#whatsappEnabledInput",
        "#whatsappTypingPresenceInput",
        "#whatsappMarkAsReadInput",
        "#whatsappAutoSyncTargetsInput",
        "#whatsappDefaultModelSelect",
        "#whatsappGroupPrefixInput",
        "#whatsappContextMaxMessagesInput",
        "#whatsappContextMaxCharsInput",
        "#whatsappSummaryTriggerInput",
        "#whatsappSummaryKeepRecentInput",
        "#whatsappSystemPromptInput",
    ];
}

function setWhatsAppConfigDirty(value) {
    state.whatsappUi.configDirty = Boolean(value);
    renderWhatsAppConfigState();
}

function renderWhatsAppConfigState() {
    const status = qs("#whatsappConfigState");
    const saveButtons = qsa("[data-whatsapp-save]");
    const discardButtons = qsa("[data-whatsapp-discard]");
    const dirty = Boolean(state.whatsappUi.configDirty);
    if (status) {
        status.textContent = dirty
            ? "Alterações pendentes. Salve para persistir na VM."
            : "Configuração salva. Você pode ajustar os campos abaixo quando quiser.";
        status.classList.toggle("active", dirty);
    }
    saveButtons.forEach((button) => {
        button.disabled = !dirty;
    });
    discardButtons.forEach((button) => {
        button.disabled = !dirty;
    });
}

function appPath(path) {
    return `${APP_BASE_PATH}${path}`;
}

async function api(path, options = {}) {
    const response = await fetch(appPath(path), {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
    });

    if (!response.ok) {
        let detail = `${response.status} ${response.statusText}`;
        try {
            const body = await response.json();
            if (body.detail) detail = body.detail;
        } catch (_) {
            // ignore
        }
        throw new Error(detail);
    }

    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
        return response.json();
    }
    return response.text();
}

function hydrateVmAssistantState() {
    try {
        const raw = window.localStorage.getItem(VM_ASSISTANT_STORAGE_KEY);
        if (!raw) return;
        const parsed = JSON.parse(raw);
        state.vmAssistant.model = String(parsed?.model || "");
        state.vmAssistant.messages = Array.isArray(parsed?.messages)
            ? parsed.messages
                .filter((message) => !message?.streaming)
                .map((message) => ({
                    role: message.role === "assistant" ? "assistant" : "user",
                    content: String(message.content || ""),
                    model: String(message.model || ""),
                    createdAt: message.createdAt || new Date().toISOString(),
                }))
            : [];
    } catch (_) {
        state.vmAssistant.model = "";
        state.vmAssistant.messages = [];
    }
}

function persistVmAssistantState() {
    try {
        window.localStorage.setItem(VM_ASSISTANT_STORAGE_KEY, JSON.stringify({
            model: state.vmAssistant.model,
            messages: state.vmAssistant.messages.filter((message) => !message.streaming),
        }));
    } catch (_) {
        // ignore
    }
}

function vmAssistantAvailableModels() {
    return Array.isArray(state.proxy?.models) ? state.proxy.models : [];
}

function renderOverviewAssistant() {
    const select = qs("#overviewAssistantModelSelect");
    const shell = qs("#overviewAssistantMessages");
    if (!select || !shell) return;

    const models = vmAssistantAvailableModels();
    if (models.length && (!state.vmAssistant.model || !models.includes(state.vmAssistant.model))) {
        state.vmAssistant.model = models[0];
        persistVmAssistantState();
    }

    if (models.length) {
        select.innerHTML = models.map((model) => `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`).join("");
        select.value = state.vmAssistant.model || models[0];
    } else {
        select.innerHTML = `<option value="">Nenhum modelo disponível</option>`;
    }

    const status = qs("#overviewAssistantStatus");
    if (status) {
        status.textContent = state.vmAssistant.stopping ? "Interrompendo" : (state.vmAssistant.pending ? "Analisando" : "Pronto");
        status.classList.toggle("active", state.vmAssistant.pending || state.vmAssistant.stopping);
    }
    const stopButton = qs("#overviewAssistantStopButton");
    if (stopButton) {
        stopButton.disabled = !state.vmAssistant.pending || state.vmAssistant.stopping;
    }

    if (!state.vmAssistant.messages.length) {
        shell.innerHTML = `<div class="empty">Pergunte sobre saúde, riscos, proxy, organização da VM, próximos passos ou comandos recomendados.</div>`;
        return;
    }

    const memory = captureScrollState(shell);
    shell.innerHTML = state.vmAssistant.messages.map((message, index) => {
        const role = message.role === "assistant" ? "assistant" : "user";
        const content = role === "assistant"
            ? markdownToHtml(message.content || (message.streaming ? "_Analisando a VM..._" : ""))
            : `<p>${escapeHtml(message.content || "")}</p>`;
        const actions = role === "assistant" && !message.streaming
            ? `<div class="chat-message-actions"><button type="button" data-overview-ai-copy="${index}">Copiar resposta</button></div>`
            : "";
        return `
            <article class="chat-message ${role}">
                <div class="chat-avatar">${role === "assistant" ? "VM" : "VOCE"}</div>
                <div class="chat-bubble">
                    <div class="chat-meta">${role === "assistant" ? "Assistente da VM" : "Você"}${message.model ? ` • ${escapeHtml(message.model)}` : ""} • ${escapeHtml(formatDate(message.createdAt))}</div>
                    <div class="chat-markdown">${content}</div>
                    ${actions}
                </div>
            </article>
        `;
    }).join("");
    restoreScrollState(shell, memory);
    proxyDecorateCodeBlocks();
}

function clearOverviewAssistant() {
    if (state.vmAssistant.pending) {
        showToast("Pare a análise atual antes de iniciar outra.", "info");
        return;
    }
    state.vmAssistant.messages = [];
    persistVmAssistantState();
    renderOverviewAssistant();
}

function stopOverviewAssistant() {
    if (!state.vmAssistant.pending) {
        showToast("Nenhuma análise da VM em andamento.", "info");
        return;
    }
    if (state.vmAssistant.stopping) {
        showToast("A interrupÃ§Ã£o jÃ¡ foi solicitada.", "info");
        return;
    }
    state.vmAssistant.stopping = true;
    renderOverviewAssistant();
    showToast("SolicitaÃ§Ã£o de interrupÃ§Ã£o enviada.", "info");
    state.socket?.send(JSON.stringify({ type: "vm.assistant.stop" }));
}

function sendOverviewAssistantPrompt(prefill = "") {
    const input = qs("#overviewAssistantInput");
    const prompt = (prefill || input?.value || "").trim();
    const model = qs("#overviewAssistantModelSelect")?.value || state.vmAssistant.model || "";

    if (!model) {
        showToast("Selecione um modelo para o assistente da VM.", "error");
        return;
    }
    if (!prompt) {
        showToast("Digite uma pergunta para o assistente da VM.", "error");
        return;
    }
    if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
        showToast("A conexão em tempo real ainda não está pronta.", "error");
        return;
    }
    if (state.vmAssistant.pending) {
        showToast("Aguarde ou pare a análise atual antes de iniciar outra.", "info");
        return;
    }

    const requestId = window.crypto?.randomUUID?.() || `vm-assistant-${Date.now()}`;
    state.vmAssistant.model = model;
    state.vmAssistant.pending = true;
    state.vmAssistant.stopping = false;
    state.vmAssistant.activeRequestId = requestId;
    state.vmAssistant.messages.push({
        role: "user",
        content: prompt,
        model,
        createdAt: new Date().toISOString(),
    });
    state.vmAssistant.messages.push({
        role: "assistant",
        content: "",
        model,
        createdAt: new Date().toISOString(),
        streaming: true,
        requestId,
    });
    if (input && !prefill) {
        input.value = "";
    }
    persistVmAssistantState();
    renderOverviewAssistant();

    const history = state.vmAssistant.messages
        .filter((message) => !message.streaming)
        .map((message) => ({ role: message.role, content: message.content }));

    state.socket.send(JSON.stringify({
        type: "vm.assistant.start",
        payload: {
            request_id: requestId,
            model,
            prompt,
            history,
        },
    }));
}

function renderOverview() {
    if (!state.telemetry || !state.system) return;

    const cpu = Math.round(state.telemetry.cpu.percent || 0);
    const memory = Math.round(state.telemetry.memory.percent || 0);
    const disk = Math.round(state.telemetry.disk.percent || 0);
    const runningContainers = state.docker.containers.filter((item) => item.status === "running").length;

    qs("#metricCpu").textContent = `${cpu}%`;
    qs("#metricMemory").textContent = `${memory}%`;
    qs("#metricDisk").textContent = `${disk}%`;
    qs("#metricNetwork").textContent = formatBytes(state.telemetry.network.bytes_recv);

    qs("#metaCpu").textContent = `${state.telemetry.cpu.count} cores`;
    qs("#metaMemory").textContent = `${formatBytes(state.telemetry.memory.available)} livres`;
    qs("#metaDisk").textContent = `${formatBytes(state.telemetry.disk.free)} livres`;
    qs("#metaNetwork").textContent = `envio ${formatBytes(state.telemetry.network.bytes_sent)} / recebimento ${formatBytes(state.telemetry.network.bytes_recv)}`;

    [["#barCpu", cpu], ["#barMemory", memory], ["#barDisk", disk]].forEach(([selector, value]) => {
        const bar = qs(selector);
        bar.style.width = `${value}%`;
        bar.className = `meter-fill ${levelClass(value)}`;
    });

    qs("#systemSummary").innerHTML = `
        <div class="kv-item"><span>Host</span><strong>${escapeHtml(state.system.hostname)}</strong></div>
        <div class="kv-item"><span>Kernel</span><strong>${escapeHtml(state.system.release)}</strong></div>
        <div class="kv-item"><span>Arquitetura</span><strong>${escapeHtml(state.system.machine)}</strong></div>
        <div class="kv-item"><span>Uptime</span><strong>${formatUptime(state.telemetry.uptime_seconds)}</strong></div>
        <div class="kv-item"><span>Carga 1m</span><strong>${state.system.load_avg.one.toFixed(2)}</strong></div>
        <div class="kv-item"><span>Atualizado</span><strong>${formatDate(state.telemetry.timestamp)}</strong></div>
    `;

    const servicesPreview = state.services
        .filter((service) => IMPORTANT_SERVICES.includes(service.unit))
        .map((service) => `
            <div class="list-row">
                <div>
                    <strong>${escapeHtml(service.unit)}</strong>
                    <small>${escapeHtml(service.description)}</small>
                </div>
                <span class="pill ${service.active}">${escapeHtml(translateServiceState(service.active))}</span>
            </div>
        `)
        .join("");
    qs("#servicesPreview").innerHTML = servicesPreview || `<div class="empty">Sem serviços para mostrar.</div>`;

    const dockerPreview = `
        <div class="list-row"><div><strong>Containers</strong><small>Total detectado</small></div><span class="pill neutral">${state.docker.containers.length}</span></div>
        <div class="list-row"><div><strong>Em execução</strong><small>Ativos agora</small></div><span class="pill ${runningContainers ? "active" : "neutral"}">${runningContainers}</span></div>
        <div class="list-row"><div><strong>Imagens</strong><small>Disponíveis</small></div><span class="pill neutral">${state.docker.images.length}</span></div>
    `;
    qs("#dockerPreview").innerHTML = dockerPreview;
    renderOverviewAssistant();
}

function renderServices() {
    const query = (qs("#serviceSearch")?.value || "").toLowerCase();
    const rows = state.services
        .filter((service) => !query || service.unit.toLowerCase().includes(query) || service.description.toLowerCase().includes(query))
        .map((service) => `
            <tr>
                <td class="mono">${escapeHtml(service.unit)}</td>
                <td><span class="pill ${escapeHtml(service.active)}">${escapeHtml(translateServiceState(service.active))} / ${escapeHtml(translateServiceState(service.sub))}</span></td>
                <td>${escapeHtml(translateServiceState(service.unit_file_state))}</td>
                <td>${escapeHtml(service.description)}</td>
                <td>
                    <div class="row-actions">
                        <button data-service-action="${escapeHtml(service.unit)}:start">iniciar</button>
                        <button data-service-action="${escapeHtml(service.unit)}:stop">parar</button>
                        <button data-service-action="${escapeHtml(service.unit)}:restart">reiniciar</button>
                    </div>
                </td>
            </tr>
        `)
        .join("");
    qs("#servicesTable").innerHTML = rows || `<tr><td colspan="5" class="empty-row">Nenhum serviço encontrado.</td></tr>`;
}

function renderDocker() {
    const containers = state.docker.containers
        .map((container) => `
            <article class="stack-card">
                <div class="stack-head">
                    <div>
                        <strong>${escapeHtml(container.name)}</strong>
                        <small>${escapeHtml(container.image)}</small>
                    </div>
                    <span class="pill ${escapeHtml(container.status)}">${escapeHtml(translateContainerStatus(container.status))}</span>
                </div>
                <div class="stack-meta">
                    <span>ID ${escapeHtml(container.id)}</span>
                    <span>${formatDate(container.created)}</span>
                </div>
                <div class="row-actions">
                    <button data-container-action="${escapeHtml(container.name)}:start">iniciar</button>
                    <button data-container-action="${escapeHtml(container.name)}:stop">parar</button>
                    <button data-container-action="${escapeHtml(container.name)}:restart">reiniciar</button>
                    <button data-container-logs="${escapeHtml(container.name)}">logs</button>
                </div>
            </article>
        `)
        .join("");
    qs("#dockerContainers").innerHTML = containers || `<div class="empty">Nenhum container encontrado.</div>`;

    const images = state.docker.images
        .map((image) => `
            <article class="stack-card">
                <div class="stack-head">
                    <div>
                        <strong>${escapeHtml((image.tags && image.tags[0]) || image.id)}</strong>
                        <small>${escapeHtml(image.id)}</small>
                    </div>
                </div>
                <div class="stack-meta">
                    <span>${formatBytes(image.size)}</span>
                    <span>${formatDate(image.created)}</span>
                </div>
            </article>
        `)
        .join("");
    qs("#dockerImages").innerHTML = images || `<div class="empty">Nenhuma imagem encontrada.</div>`;
}

function renderProcesses() {
    qs("#processesTable").innerHTML = state.processes
        .map((proc) => `
            <tr>
                <td class="mono">${proc.pid}</td>
                <td>${escapeHtml(proc.name)}</td>
                <td>${Number(proc.cpu_percent || 0).toFixed(1)}%</td>
                <td>${Number(proc.memory_percent || 0).toFixed(1)}%</td>
                <td>${escapeHtml(proc.user)}</td>
                <td class="truncate-cell" title="${escapeHtml(proc.command || proc.name)}">${escapeHtml(proc.command || proc.name)}</td>
                <td>
                    <div class="row-actions">
                        <button data-process-signal="${proc.pid}:TERM">TERM</button>
                        <button class="danger" data-process-signal="${proc.pid}:KILL">KILL</button>
                    </div>
                </td>
            </tr>
        `)
        .join("") || `<tr><td colspan="7" class="empty-row">Sem processos.</td></tr>`;
}

function renderFirewall() {
    qs("#firewallRules").innerHTML = (state.firewall.raw || [])
        .map((line) => `<div class="list-row mono compact">${escapeHtml(line)}</div>`)
        .join("") || `<div class="empty">Nenhuma regra carregada.</div>`;
}

function normalizeProxyLog(entry) {
    if (!entry) return null;
    if (typeof entry === "string") {
        return { timestamp: "", level: "RAW", message: entry, raw: entry };
    }
    return {
        timestamp: entry.timestamp || "",
        level: entry.level || "INFO",
        message: entry.message || entry.raw || "",
        endpoint: entry.endpoint || "",
        status_code: entry.status_code || 0,
        key_id: entry.key_id || "",
        raw: entry.raw || JSON.stringify(entry),
    };
}

function markdownToHtml(markdown) {
    const raw = String(markdown || "");
    const html = window.marked ? window.marked.parse(raw) : escapeHtml(raw).replace(/\n/g, "<br>");
    return window.DOMPurify ? window.DOMPurify.sanitize(html) : html;
}

function proxyGenerateId() {
    return window.crypto?.randomUUID?.() || `proxy-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function proxyDefaultOptions() {
    return {
        temperature: "",
        topP: "",
        maxTokens: "",
    };
}

function proxyNormalizeAttachment(raw = {}) {
    return {
        id: raw.id || proxyGenerateId(),
        name: String(raw.name || "anexo"),
        mime: String(raw.mime || "application/octet-stream"),
        kind: raw.kind === "image" ? "image" : "text",
        size: Number(raw.size || 0),
        data: String(raw.data || ""),
        text: String(raw.text || ""),
        previewUrl: String(raw.previewUrl || ""),
        truncated: Boolean(raw.truncated),
    };
}

function proxySerializableAttachment(raw = {}) {
    const attachment = proxyNormalizeAttachment(raw);
    return {
        ...attachment,
        previewUrl: attachment.kind === "image" ? "" : attachment.previewUrl,
    };
}

function proxyNormalizeMessage(raw = {}) {
    return {
        id: raw.id || proxyGenerateId(),
        role: raw.role === "assistant" ? "assistant" : "user",
        content: String(raw.content || ""),
        model: String(raw.model || ""),
        attachments: Array.isArray(raw.attachments) ? raw.attachments.map(proxyNormalizeAttachment) : [],
        createdAt: raw.createdAt || new Date().toISOString(),
        streaming: Boolean(raw.streaming),
        requestId: String(raw.requestId || ""),
        stopped: Boolean(raw.stopped),
        error: Boolean(raw.error),
    };
}

function proxyCreateConversation(seed = {}) {
    return {
        id: seed.id || proxyGenerateId(),
        title: String(seed.title || "Nova conversa"),
        model: String(seed.model || ""),
        systemPrompt: String(seed.systemPrompt || ""),
        options: {
            ...proxyDefaultOptions(),
            ...(seed.options || {}),
        },
        messages: Array.isArray(seed.messages) ? seed.messages.map(proxyNormalizeMessage).filter((message) => !message.streaming) : [],
        draftAttachments: Array.isArray(seed.draftAttachments) ? seed.draftAttachments.map(proxyNormalizeAttachment) : [],
        createdAt: seed.createdAt || new Date().toISOString(),
        updatedAt: seed.updatedAt || new Date().toISOString(),
    };
}

function hydrateProxyChatState() {
    try {
        const raw = window.localStorage.getItem(PROXY_CHAT_STORAGE_KEY);
        if (!raw) {
            state.proxyChat.conversations = [proxyCreateConversation()];
            state.proxyChat.activeConversationId = state.proxyChat.conversations[0].id;
            return;
        }
        const parsed = JSON.parse(raw);
        const conversations = Array.isArray(parsed?.conversations) ? parsed.conversations.map(proxyCreateConversation) : [];
        state.proxyChat.conversations = conversations.length ? conversations : [proxyCreateConversation()];
        state.proxyChat.activeConversationId = String(parsed?.activeConversationId || state.proxyChat.conversations[0].id);
        if (!state.proxyChat.conversations.some((conversation) => conversation.id === state.proxyChat.activeConversationId)) {
            state.proxyChat.activeConversationId = state.proxyChat.conversations[0].id;
        }
    } catch (error) {
        state.proxyChat.conversations = [proxyCreateConversation()];
        state.proxyChat.activeConversationId = state.proxyChat.conversations[0].id;
    }
}

function persistProxyChatState() {
    try {
        const payload = {
            activeConversationId: state.proxyChat.activeConversationId,
            conversations: state.proxyChat.conversations.map((conversation) => ({
                ...conversation,
                messages: conversation.messages
                    .filter((message) => !message.streaming)
                    .map((message) => ({
                        ...message,
                        attachments: (message.attachments || []).map(proxySerializableAttachment),
                    })),
                draftAttachments: (conversation.draftAttachments || []).map(proxySerializableAttachment),
            })),
        };
        window.localStorage.setItem(PROXY_CHAT_STORAGE_KEY, JSON.stringify(payload));
    } catch (error) {
        // ignore storage failures
    }
}

function proxyFindConversation(conversationId) {
    return state.proxyChat.conversations.find((conversation) => conversation.id === conversationId) || null;
}

function proxyActiveConversation() {
    return proxyFindConversation(state.proxyChat.activeConversationId);
}

function proxyEnsureConversation() {
    if (!state.proxyChat.conversations.length) {
        const conversation = proxyCreateConversation();
        state.proxyChat.conversations.push(conversation);
        state.proxyChat.activeConversationId = conversation.id;
    }
    if (!proxyActiveConversation()) {
        state.proxyChat.activeConversationId = state.proxyChat.conversations[0].id;
    }
    return proxyActiveConversation();
}

function proxyTouchConversation(conversation) {
    if (!conversation) return;
    conversation.updatedAt = new Date().toISOString();
}

function proxyConversationPreview(conversation) {
    const last = [...(conversation?.messages || [])].reverse().find((message) => message.content?.trim() || (message.attachments || []).length);
    if (!last) return "Sem mensagens ainda.";
    if (!last.content?.trim() && (last.attachments || []).length) {
        return `${last.attachments.length} anexo(s) enviado(s)`;
    }
    const preview = last.content.replace(/\s+/g, " ").trim();
    return preview.length > 72 ? `${preview.slice(0, 72)}...` : preview;
}

function proxyConversationTitle(conversation) {
    const firstUser = (conversation?.messages || []).find((message) => message.role === "user" && message.content.trim());
    if (!conversation) return "Nova conversa";
    if (conversation.title && conversation.title !== "Nova conversa") return conversation.title;
    if (!firstUser) return "Nova conversa";
    const preview = firstUser.content.replace(/\s+/g, " ").trim();
    return preview.length > 34 ? `${preview.slice(0, 34)}...` : preview;
}

function proxySyncConversationFromControls() {
    const conversation = proxyEnsureConversation();
    if (!conversation) return;
    conversation.model = qs("#proxyModelSelect")?.value || conversation.model || "";
    conversation.systemPrompt = qs("#proxySystemPromptInput")?.value || "";
    conversation.options = {
        temperature: qs("#proxyTemperatureInput")?.value.trim() || "",
        topP: qs("#proxyTopPInput")?.value.trim() || "",
        maxTokens: qs("#proxyMaxTokensInput")?.value.trim() || "",
    };
    proxyTouchConversation(conversation);
    persistProxyChatState();
}

function proxySyncControlsFromConversation() {
    const conversation = proxyEnsureConversation();
    if (!conversation) return;
    const select = qs("#proxyModelSelect");
    if (select && conversation.model && Array.from(select.options).some((option) => option.value === conversation.model)) {
        select.value = conversation.model;
    }
    if (qs("#proxySystemPromptInput")) qs("#proxySystemPromptInput").value = conversation.systemPrompt || "";
    if (qs("#proxyTemperatureInput")) qs("#proxyTemperatureInput").value = conversation.options?.temperature || "";
    if (qs("#proxyTopPInput")) qs("#proxyTopPInput").value = conversation.options?.topP || "";
    if (qs("#proxyMaxTokensInput")) qs("#proxyMaxTokensInput").value = conversation.options?.maxTokens || "";
    if (qs("#proxyActiveConversationMeta")) {
        qs("#proxyActiveConversationMeta").textContent = `${proxyConversationTitle(conversation)} • ${formatDate(conversation.updatedAt)}`;
    }
    if (qs("#proxyChatStatus")) {
        const el = qs("#proxyChatStatus");
        el.textContent = state.proxyChat.stopping ? "Interrompendo" : (state.proxyChat.pending ? "Respondendo" : "Pronto");
        el.classList.toggle("active", state.proxyChat.pending || state.proxyChat.stopping);
    }
    if (qs("#proxyComposerHint")) {
        qs("#proxyComposerHint").textContent = state.proxyChat.pending
            ? "A resposta está em andamento. Você pode parar quando quiser."
            : "Enter envia. Shift+Enter quebra linha.";
    }
    if (state.proxyChat.stopping && qs("#proxyComposerHint")) {
        qs("#proxyComposerHint").textContent = "Interrupcao solicitada. Aguarde o stream encerrar.";
    }
    if (qs("#proxyStopChatButton")) {
        qs("#proxyStopChatButton").disabled = !state.proxyChat.pending || state.proxyChat.stopping;
    }
    if (qs("#proxyRegenerateChatButton")) {
        const messages = conversation.messages || [];
        const last = messages[messages.length - 1];
        qs("#proxyRegenerateChatButton").disabled = state.proxyChat.pending || !last || last.role !== "assistant";
    }
}

function proxySetActiveConversation(conversationId) {
    if (!proxyFindConversation(conversationId)) return;
    state.proxyChat.activeConversationId = conversationId;
    persistProxyChatState();
    renderProxy();
}

function proxyCreateNewConversation() {
    const current = proxyActiveConversation();
    const conversation = proxyCreateConversation({
        model: current?.model || proxySelectedModel(),
        systemPrompt: current?.systemPrompt || "",
        options: current?.options || proxyDefaultOptions(),
    });
    state.proxyChat.conversations.unshift(conversation);
    state.proxyChat.activeConversationId = conversation.id;
    persistProxyChatState();
    renderProxy();
    qs("#proxyChatInput")?.focus();
}

function proxyDeleteConversation(conversationId) {
    if (state.proxyChat.pending && state.proxyChat.activeRequestConversationId === conversationId) {
        showToast("Pare a resposta atual antes de excluir esta conversa.", "info");
        return;
    }
    state.proxyChat.conversations = state.proxyChat.conversations.filter((conversation) => conversation.id !== conversationId);
    if (!state.proxyChat.conversations.length) {
        state.proxyChat.conversations.push(proxyCreateConversation());
    }
    if (!proxyFindConversation(state.proxyChat.activeConversationId)) {
        state.proxyChat.activeConversationId = state.proxyChat.conversations[0].id;
    }
    persistProxyChatState();
    renderProxy();
}

function proxyConversationApiMessages(conversation) {
    const output = [];
    if (conversation?.systemPrompt?.trim()) {
        output.push({ role: "system", content: conversation.systemPrompt.trim() });
    }
    (conversation?.messages || []).forEach((message) => {
        if (message.streaming || message.error) return;
        const apiMessage = {
            role: message.role,
            content: proxyMessageContentForApi(message),
        };
        const images = (message.attachments || [])
            .filter((attachment) => attachment.kind === "image" && attachment.data)
            .map((attachment) => attachment.data);
        if (images.length) {
            apiMessage.images = images;
        }
        if (!apiMessage.content.trim() && !images.length) return;
        output.push(apiMessage);
    });
    return output;
}

function proxyConversationRequestOptions(conversation) {
    const options = {};
    const temperature = Number(conversation?.options?.temperature);
    const topP = Number(conversation?.options?.topP);
    const maxTokens = Number(conversation?.options?.maxTokens);
    if (conversation?.options?.temperature !== "" && Number.isFinite(temperature)) {
        options.temperature = temperature;
    }
    if (conversation?.options?.topP !== "" && Number.isFinite(topP)) {
        options.top_p = topP;
    }
    if (conversation?.options?.maxTokens !== "" && Number.isFinite(maxTokens)) {
        options.num_predict = Math.max(1, Math.round(maxTokens));
    }
    return options;
}

function proxyModelCatalog() {
    return Array.isArray(state.proxy?.model_catalog) ? state.proxy.model_catalog : [];
}

function proxyModelDetails(model) {
    return proxyModelCatalog().find((item) => item.name === model || item.model === model) || null;
}

function proxyModelCapabilities(model) {
    return Array.isArray(proxyModelDetails(model)?.capabilities) ? proxyModelDetails(model).capabilities : [];
}

function proxyModelSupportsVision(model) {
    return Boolean(proxyModelDetails(model)?.supports_vision);
}

function proxyImageModels() {
    const models = Array.isArray(state.proxy?.models) ? state.proxy.models : [];
    return models
        .filter((model) => {
            const lowered = String(model || "").toLowerCase();
            return lowered.includes("(nvidia)") && (lowered.includes("flux") || lowered.includes("stable-diffusion"));
        })
        .sort((a, b) => String(a).localeCompare(String(b)));
}

function proxyImageMinSteps(model) {
    const lowered = String(model || "").toLowerCase();
    if (lowered.includes("stable-diffusion") || lowered.includes("flux.1-dev")) return 5;
    return 1;
}

function proxySyncImageFromControls() {
    const image = state.proxyImage;
    image.model = qs("#proxyImageModelSelect")?.value || image.model || "";
    image.prompt = qs("#proxyImagePromptInput")?.value || "";
    image.width = Number(qs("#proxyImageWidthInput")?.value || image.width || 1024);
    image.height = Number(qs("#proxyImageHeightInput")?.value || image.height || 1024);
    image.steps = Math.max(proxyImageMinSteps(image.model), Number(qs("#proxyImageStepsInput")?.value || image.steps || 4));
    image.seed = qs("#proxyImageSeedInput")?.value.trim() || "";
}

function proxyImageResultFromPayload(payload) {
    const first = Array.isArray(payload?.images) ? payload.images[0] : null;
    if (!first) return { base64: "", mimeType: "image/jpeg" };
    if (typeof first === "string") return { base64: first, mimeType: "image/jpeg" };
    return {
        base64: first.base64 || first.image || "",
        mimeType: first.mime_type || first.mimeType || "image/jpeg",
    };
}

function renderProxyImageGenerator() {
    const image = state.proxyImage;
    const models = proxyImageModels();
    if (!image.model || !models.includes(image.model)) {
        image.model = models[0] || "";
    }

    const select = qs("#proxyImageModelSelect");
    if (select) {
        select.innerHTML = models.length
            ? models.map((model) => `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`).join("")
            : `<option value="">Nenhum modelo NVIDIA de imagem encontrado</option>`;
        select.value = image.model || "";
        select.disabled = image.generating || !models.length;
    }

    const prompt = qs("#proxyImagePromptInput");
    if (prompt && prompt.value !== image.prompt) prompt.value = image.prompt || "";
    const width = qs("#proxyImageWidthInput");
    if (width) width.value = String(image.width || 1024);
    const height = qs("#proxyImageHeightInput");
    if (height) height.value = String(image.height || 1024);
    const steps = qs("#proxyImageStepsInput");
    if (steps) {
        const minSteps = proxyImageMinSteps(image.model);
        steps.min = String(minSteps);
        image.steps = Math.max(minSteps, Number(image.steps || 4));
        steps.value = String(image.steps || minSteps);
    }
    const seed = qs("#proxyImageSeedInput");
    if (seed) seed.value = image.seed || "";

    const generateButton = qs("#proxyImageGenerateButton");
    if (generateButton) {
        generateButton.disabled = image.generating || !models.length;
        generateButton.textContent = image.generating ? "Gerando..." : "Gerar imagem";
    }
    const resetButton = qs("#proxyImageResetButton");
    if (resetButton) resetButton.disabled = image.generating;

    const status = qs("#proxyImageStatus");
    if (status) {
        status.textContent = image.generating
            ? "Gerando imagem pelo proxy NVIDIA..."
            : image.error
                ? image.error
                : image.imageBase64
                    ? `Imagem gerada em ${formatMilliseconds(image.durationMs || 0)}.`
                    : (models.length ? "Escolha um modelo e gere uma imagem de teste." : "Nenhum modelo de imagem NVIDIA apareceu em /api/tags.");
        status.classList.toggle("active", image.generating);
    }

    const meta = qs("#proxyImageResultMeta");
    if (meta) {
        meta.textContent = image.imageBase64
            ? `${image.model || "modelo"} | ${image.width || 1024}x${image.height || 1024} | ${formatMilliseconds(image.durationMs || 0)}`
            : "Sem imagem gerada ainda.";
    }

    const preview = qs("#proxyImagePreview");
    if (preview) {
        preview.innerHTML = image.imageBase64
            ? `<img src="data:${escapeHtml(image.mimeType || "image/jpeg")};base64,${image.imageBase64}" alt="Imagem gerada pelo proxy NVIDIA" />`
            : `<div class="empty">A imagem gerada vai aparecer aqui.</div>`;
    }
}

function proxyAttachmentPreviewUrl(attachment) {
    if (attachment.previewUrl) return attachment.previewUrl;
    if (attachment.kind === "image" && attachment.data) {
        return `data:${attachment.mime || "image/png"};base64,${attachment.data}`;
    }
    return "";
}

function proxyMessageContentForApi(message) {
    const base = String(message.content || "");
    const textAttachments = (message.attachments || []).filter((attachment) => attachment.kind === "text" && attachment.text);
    if (!textAttachments.length) {
        return base;
    }
    const attachmentText = textAttachments.map((attachment) => (
        `\n\n[Arquivo anexado: ${attachment.name}]\n` +
        "```text\n" +
        `${attachment.text}${attachment.truncated ? "\n... conteúdo truncado ..." : ""}\n` +
        "```"
    )).join("");
    return `${base}${attachmentText}`;
}

function proxyConversationHasVisionAttachments(conversation) {
    return (conversation?.messages || []).some((message) => (message.attachments || []).some((attachment) => attachment.kind === "image" && attachment.data));
}

function proxySelectedModel() {
    const conversation = proxyEnsureConversation();
    return conversation?.model || qs("#proxyModelSelect")?.value || "";
}

function proxyFindMessage(messageId) {
    const conversation = proxyActiveConversation();
    if (!conversation) return null;
    const index = conversation.messages.findIndex((message) => message.id === messageId);
    if (index < 0) return null;
    return {
        conversation,
        index,
        message: conversation.messages[index],
    };
}

function proxyFindStreamingMessage(requestId) {
    for (const conversation of state.proxyChat.conversations) {
        const index = conversation.messages.findIndex((message) => message.streaming && message.requestId === requestId);
        if (index >= 0) {
            return {
                conversation,
                index,
                message: conversation.messages[index],
            };
        }
    }
    return null;
}

function proxyDraftAttachments() {
    return proxyEnsureConversation()?.draftAttachments || [];
}

function proxyRenderAttachmentChips(attachments, scope = "draft") {
    return (attachments || []).map((attachment) => {
        const preview = attachment.kind === "image"
            ? `<img src="${escapeHtml(proxyAttachmentPreviewUrl(attachment))}" alt="${escapeHtml(attachment.name)}" />`
            : `<div class="attachment-text-preview">${escapeHtml((attachment.text || "").slice(0, 90) || attachment.name)}</div>`;
        const remove = scope === "draft"
            ? `<button type="button" class="attachment-remove" data-proxy-draft-attachment-remove="${escapeHtml(attachment.id)}">×</button>`
            : "";
        return `
            <article class="attachment-chip ${attachment.kind}">
                <div class="attachment-chip-body">
                    <div class="attachment-thumb">${preview}</div>
                    <div class="attachment-meta">
                        <strong>${escapeHtml(attachment.name)}</strong>
                        <small>${attachment.kind === "image" ? "imagem" : "arquivo"} • ${escapeHtml(formatBytes(attachment.size || 0))}</small>
                    </div>
                </div>
                ${remove}
            </article>
        `;
    }).join("");
}

function projectSelected() {
    return state.projects.find((project) => project.id === state.selectedProjectId) || null;
}

function projectStatusLabel(status) {
    return {
        ready: "pronto",
        "needs-attention": "atencao",
        blocked: "bloqueado",
        unknown: "sem analise",
    }[status] || status || "sem analise";
}

function projectStatusClass(status) {
    return {
        ready: "ok",
        "needs-attention": "warning",
        blocked: "danger",
    }[status] || "neutral";
}

function projectWebhookUrl(project) {
    const value = project?.webhook?.url || "";
    if (value.startsWith("/")) {
        return `${window.location.origin}${value}`;
    }
    return value;
}

function projectDeriveNameFromUrl(repoUrl) {
    const raw = String(repoUrl || "").trim();
    if (!raw) return "";
    try {
        const url = new URL(raw);
        const parts = url.pathname.split("/").filter(Boolean);
        const last = parts[parts.length - 1] || "";
        return last.replace(/\.git$/i, "");
    } catch (_) {
        const parts = raw.split("/").filter(Boolean);
        return (parts[parts.length - 1] || "").replace(/\.git$/i, "");
    }
}

function setProjectWizardMode(mode) {
    state.projectWizardMode = mode === "advanced" ? "advanced" : "simple";
    if (state.projectWizardMode === "simple" && qs("#projectManagedCheckoutInput")) {
        qs("#projectManagedCheckoutInput").checked = true;
    }
    try {
        window.localStorage.setItem(PROJECT_WIZARD_MODE_KEY, state.projectWizardMode);
    } catch (_) {
        // ignore
    }
    qsa("[data-project-mode]").forEach((button) => {
        button.classList.toggle("active", button.dataset.projectMode === state.projectWizardMode);
    });
    qs("#projectAdvancedShell")?.classList.toggle("visible", state.projectWizardMode === "advanced");
    syncProjectManagedCheckoutUi();
}

function setWhatsAppTab(tab) {
    const allowed = new Set(["connection", "assistant", "targets", "conversations", "logs"]);
    state.whatsappTab = allowed.has(tab) ? tab : "connection";
    try {
        window.localStorage.setItem(WHATSAPP_TAB_STORAGE_KEY, state.whatsappTab);
    } catch (_) {
        // ignore
    }
    qsa("[data-whatsapp-tab]").forEach((button) => {
        button.classList.toggle("active", button.dataset.whatsappTab === state.whatsappTab);
    });
    qsa(".whatsapp-tab-shell").forEach((shell) => {
        shell.classList.toggle("active", shell.id === `whatsappTab${state.whatsappTab.charAt(0).toUpperCase()}${state.whatsappTab.slice(1)}`);
    });
}

function syncProjectManagedCheckoutUi() {
    const managed = qs("#projectManagedCheckoutInput")?.checked !== false;
    qs("#projectRepoPathField")?.classList.toggle("hidden", managed);
    const pathInput = qs("#projectRepoPathInput");
    if (pathInput) {
        pathInput.disabled = managed;
        if (managed) {
            pathInput.value = "";
        }
    }
}

function resetProjectForm(clearSelection = false) {
    if (clearSelection) {
        state.selectedProjectId = "";
    }
    qs("#projectIdInput").value = "";
    qs("#projectNameInput").value = "";
    qs("#projectRepoPathInput").value = "";
    qs("#projectRepoUrlInput").value = "";
    qs("#projectBranchInput").value = "main";
    qs("#projectDomainInput").value = "";
    qs("#projectBasePathInput").value = "/";
    qs("#projectEnabledInput").checked = true;
    qs("#projectAutoDeployInput").checked = true;
    qs("#projectManagedCheckoutInput").checked = true;
    setProjectWizardMode("simple");
    syncProjectManagedCheckoutUi();
}

function fillProjectForm(project) {
    if (!project) {
        resetProjectForm(false);
        return;
    }
    qs("#projectIdInput").value = project.id || "";
    qs("#projectNameInput").value = project.name || "";
    qs("#projectRepoPathInput").value = project.repo_path || "";
    qs("#projectRepoUrlInput").value = project.repo_url || "";
    qs("#projectBranchInput").value = project.branch || "main";
    qs("#projectDomainInput").value = project.default_domain || "";
    qs("#projectBasePathInput").value = project.default_base_path || "/";
    qs("#projectEnabledInput").checked = Boolean(project.enabled);
    qs("#projectAutoDeployInput").checked = project.auto_deploy !== false;
    qs("#projectManagedCheckoutInput").checked = project.source_mode !== "manual";
    setProjectWizardMode(project.setup_mode || (project.source_mode === "manual" ? "advanced" : "simple"));
    syncProjectManagedCheckoutUi();
}

function selectProject(projectId) {
    state.selectedProjectId = projectId || "";
    fillProjectForm(projectSelected());
    renderProjects();
}

function projectSummaryMetrics() {
    const total = state.projects.length;
    const ready = state.projects.filter((project) => project.analysis?.status === "ready").length;
    const attention = state.projects.filter((project) => project.analysis?.status === "needs-attention").length;
    const blocked = state.projects.filter((project) => project.analysis?.status === "blocked").length;
    return { total, ready, attention, blocked };
}

function renderProjects() {
    const list = qs("#projectsList");
    const kpis = qs("#projectsKpis");
    const currentJobHost = qs("#projectCurrentJob");
    const activityHost = qs("#projectActivityStream");
    const fixHost = qs("#projectFixBox");
    const summary = qs("#projectSummaryCards");
    const diagnostics = qs("#projectDiagnostics");
    const componentsHost = qs("#projectComponents");
    const planSummary = qs("#projectPlanSummary");
    const routesHost = qs("#projectRoutes");
    const webhookHost = qs("#projectWebhookBox");
    const bundleHost = qs("#projectBundleList");
    const installHost = qs("#projectInstallSteps");
    const aiHost = qs("#projectAiReport");
    const deliveriesHost = qs("#projectDeliveries");
    const deploymentsHost = qs("#projectDeployments");
    if (!list || !kpis || !currentJobHost || !activityHost || !fixHost || !summary || !diagnostics || !componentsHost || !planSummary || !routesHost || !webhookHost || !bundleHost || !installHost || !aiHost || !deliveriesHost || !deploymentsHost) return;

    if (!state.selectedProjectId && state.projects.length) {
        state.selectedProjectId = state.projects[0].id;
    }

    const counts = projectSummaryMetrics();
    kpis.innerHTML = `
        <article class="project-kpi"><strong>${counts.total}</strong><span>cadastrados</span></article>
        <article class="project-kpi"><strong>${counts.ready}</strong><span>prontos</span></article>
        <article class="project-kpi"><strong>${counts.attention}</strong><span>em atencao</span></article>
        <article class="project-kpi"><strong>${counts.blocked}</strong><span>bloqueados</span></article>
    `;

    if (!state.projects.length) {
        list.innerHTML = `<div class="empty">Nenhum projeto cadastrado ainda.</div>`;
        currentJobHost.innerHTML = `<div class="empty">Nenhum job em andamento.</div>`;
        activityHost.innerHTML = `<div class="empty">A trilha de atividade do projeto aparece aqui.</div>`;
        fixHost.innerHTML = `<div class="empty">Quando houver erro, a IA e as correcoes aprovaveis aparecem aqui.</div>`;
        summary.innerHTML = `<div class="empty">Cadastre um repositorio para abrir o plano, o webhook e o diagnostico.</div>`;
        diagnostics.innerHTML = "";
        componentsHost.innerHTML = "";
        planSummary.innerHTML = `<div class="empty">Sem plano de deploy ainda.</div>`;
        routesHost.innerHTML = "";
        webhookHost.innerHTML = `<div class="empty">O wizard gera um endpoint unico por projeto.</div>`;
        bundleHost.innerHTML = "";
        installHost.innerHTML = "";
        aiHost.innerHTML = `<div class="empty">A leitura por IA aparece aqui depois da analise assistida.</div>`;
        deliveriesHost.innerHTML = `<div class="empty">Nenhuma entrega registrada.</div>`;
        deploymentsHost.innerHTML = `<div class="empty">Nenhum deploy executado ainda.</div>`;
        return;
    }

    list.innerHTML = state.projects.map((project) => {
        const report = project.analysis || {};
        const countsText = `${report.scores?.deployable_components || 0} comp. implantaveis`;
        return `
            <article class="project-card ${project.id === state.selectedProjectId ? "active" : ""}">
                <button class="project-card-main" data-project-select="${escapeHtml(project.id)}" type="button">
                    <div class="project-card-top">
                        <strong>${escapeHtml(project.name || project.id)}</strong>
                        <span class="status-badge ${projectStatusClass(report.status)}">${escapeHtml(projectStatusLabel(report.status || "unknown"))}</span>
                    </div>
                    <div class="project-card-meta">${escapeHtml(project.repo_url || project.repo_path || "Sem repositorio configurado")}</div>
                    <div class="project-card-meta">${escapeHtml(report.classification?.repo_kind || "Sem classificacao")} • ${escapeHtml(countsText)}</div>
                </button>
            </article>
        `;
    }).join("");

    const selected = projectSelected();
    if (!selected) {
        return;
    }

    const report = selected.analysis || {};
    const diagnosticsRows = Array.isArray(report.diagnostics) ? report.diagnostics : [];
    const components = Array.isArray(report.components) ? report.components : [];
    const plan = report.deployment_plan || {};
    const routes = Array.isArray(report.published_routes) && report.published_routes.length
        ? report.published_routes
        : (Array.isArray(plan.routes) ? plan.routes : []);
    const services = Array.isArray(plan.services) ? plan.services : [];
    const bundle = report.bundle || {};
    const bundleArtifacts = Array.isArray(bundle.artifacts) ? bundle.artifacts : [];
    const deliveries = Array.isArray(selected.deliveries) ? selected.deliveries.slice().reverse() : [];
    const deployments = Array.isArray(selected.deployments) ? selected.deployments.slice().reverse() : [];
    const activity = Array.isArray(selected.activity) ? selected.activity.slice().reverse() : [];
    const currentJob = selected.current_job || {};
    const pendingFix = selected.pending_fix || null;

    currentJobHost.innerHTML = currentJob?.type
        ? `
            <article class="job-card ${escapeHtml(currentJob.status || "running")}">
                <div class="job-card-top">
                    <strong>${escapeHtml(currentJob.type === "deploy" ? "Deploy" : "Analise")}</strong>
                    <span class="status-badge ${projectStatusClass(currentJob.status === "success" ? "ready" : currentJob.status === "failed" ? "blocked" : "needs-attention")}">${escapeHtml(currentJob.status || "running")}</span>
                </div>
                <div class="job-card-stage">${escapeHtml(currentJob.stage || "preparando")}</div>
                <div class="job-card-detail">${escapeHtml(currentJob.detail || "Sem detalhe no momento.")}</div>
                <div class="meter compact"><span style="width:${Math.max(0, Math.min(Number(currentJob.progress || 0), 100))}%"></span></div>
                <div class="job-card-meta">${escapeHtml(formatDate(currentJob.updated_at || currentJob.started_at || ""))}${currentJob.error ? ` • ${escapeHtml(currentJob.error)}` : ""}</div>
            </article>
        `
        : `<div class="empty">Nenhum job recente registrado para este projeto.</div>`;

    activityHost.innerHTML = activity.length
        ? activity.map((entry) => `
            <article class="activity-row ${escapeHtml(entry.level || "info")}">
                <div class="activity-dot"></div>
                <div class="activity-body">
                    <strong>${escapeHtml(entry.stage || "atividade")}</strong>
                    <div>${escapeHtml(entry.message || "")}</div>
                    <small>${escapeHtml(formatDate(entry.at || ""))}</small>
                </div>
            </article>
        `).join("")
        : `<div class="empty">A atividade do projeto aparece aqui em tempo real.</div>`;

    if (pendingFix?.status === "ready") {
        const candidates = Array.isArray(pendingFix.candidates) ? pendingFix.candidates : [];
        const aiContent = pendingFix.ai_report?.content ? markdownToHtml(pendingFix.ai_report.content) : "";
        fixHost.innerHTML = `
            ${pendingFix.error_excerpt ? `<div class="fix-error-box"><strong>Erro analisado</strong><pre>${escapeHtml(pendingFix.error_excerpt)}</pre></div>` : ""}
            ${aiContent ? `<div class="fix-ai-box">${aiContent}</div>` : ""}
            <div class="fix-candidates">
                ${candidates.length ? candidates.map((candidate) => `
                    <article class="fix-card">
                        <strong>${escapeHtml(candidate.label || candidate.id)}</strong>
                        <div>${escapeHtml(candidate.description || "Correcao sugerida pelo sistema.")}</div>
                        <div class="row-actions">
                            <button type="button" data-project-fix-apply="${escapeHtml(candidate.id)}">Aplicar correcao</button>
                            <button type="button" data-project-fix-retry="${escapeHtml(candidate.id)}">Aplicar e tentar de novo</button>
                        </div>
                    </article>
                `).join("") : `<div class="empty">A IA sugeriu uma leitura, mas nao encontrou uma correcao segura e automatica para aplicar sozinha.</div>`}
            </div>
        `;
    } else {
        fixHost.innerHTML = `<div class="empty">Sem correcoes pendentes. Quando um deploy falhar, esta area mostra a leitura da IA e as correcoes seguras aprovaveis.</div>`;
    }

    summary.innerHTML = `
        <article class="project-summary-card">
            <div class="metric-label">Do que se trata</div>
            <div class="project-summary-copy">${escapeHtml(report.brief?.what_it_is || "Sem leitura disponivel.")}</div>
        </article>
        <article class="project-summary-card">
            <div class="metric-label">O que faz</div>
            <div class="project-summary-copy">${escapeHtml(report.brief?.what_it_does || "Sem leitura disponivel.")}</div>
        </article>
        <article class="project-summary-card">
            <div class="metric-label">Para que serve</div>
            <div class="project-summary-copy">${escapeHtml(report.brief?.purpose || "Sem contexto suficiente no README.")}</div>
        </article>
    `;

    diagnostics.innerHTML = diagnosticsRows.length
        ? diagnosticsRows.map((item) => `
            <article class="diagnostic-card ${item.severity || "info"}">
                <div class="diagnostic-top">
                    <strong>${escapeHtml(item.summary || item.code || "Diagnostico")}</strong>
                    <span>${escapeHtml(item.scope || "repository")} • ${escapeHtml(item.severity || "info")}</span>
                </div>
                ${item.suggestion ? `<div class="diagnostic-copy">${escapeHtml(item.suggestion)}</div>` : ""}
                ${Array.isArray(item.evidence) && item.evidence.length ? `<div class="diagnostic-evidence">${item.evidence.map((row) => `<span>${escapeHtml(row)}</span>`).join("")}</div>` : ""}
            </article>
        `).join("")
        : `<div class="empty">Nenhum diagnostico relevante na ultima analise.</div>`;

    componentsHost.innerHTML = components.length
        ? components.map((component) => `
            <article class="component-card">
                <div class="component-top">
                    <strong>${escapeHtml(component.name || component.id)}</strong>
                    <span>${escapeHtml(component.type || "service")}</span>
                </div>
                <div class="component-copy">${escapeHtml(component.rel_path || ".")} • ${escapeHtml(component.language || "unknown")} • ${escapeHtml(component.entry_strategy || "manual")}</div>
                <div class="component-pills">
                    <span>${escapeHtml(component.deployable ? "implantavel" : "suporte")}</span>
                    ${component.public ? `<span>publico</span>` : ""}
                    ${component.container_port ? `<span>porta ${escapeHtml(component.container_port)}</span>` : ""}
                    ${component.host_port ? `<span>host ${escapeHtml(component.host_port)}</span>` : ""}
                </div>
            </article>
        `).join("")
        : `<div class="empty">A analise ainda nao identificou componentes neste repositorio.</div>`;

    planSummary.innerHTML = `
        <div class="kv-item"><span>Status</span><strong>${escapeHtml(projectStatusLabel(report.status || "unknown"))}</strong></div>
        <div class="kv-item"><span>Tipo</span><strong>${escapeHtml(report.classification?.repo_kind || "n/d")}</strong></div>
        <div class="kv-item"><span>Porta base</span><strong>${escapeHtml(plan.port_base || selected.port_base || "n/d")}</strong></div>
        <div class="kv-item"><span>Servicos</span><strong>${escapeHtml(String(services.length))}</strong></div>
        <div class="kv-item"><span>Compose</span><strong>${plan.compose_recommended ? "recomendado" : "opcional"}</strong></div>
        <div class="kv-item"><span>Ultima analise</span><strong>${escapeHtml(formatDate(report.generated_at || selected.last_analyzed_at || ""))}</strong></div>
        <div class="kv-item"><span>Ultimo deploy</span><strong>${escapeHtml(formatDate(selected.last_deployed_at || ""))}</strong></div>
        <div class="kv-item"><span>Status do deploy</span><strong>${escapeHtml(selected.last_deployment_status || "n/d")}</strong></div>
    `;

    routesHost.innerHTML = routes.length
        ? routes.map((route) => `
            <article class="route-card">
                <strong>${escapeHtml(route.component_name || route.component_id)}</strong>
                <span>${escapeHtml(route.domain || "sem dominio")} ${escapeHtml(route.effective_path || route.path || "/")}</span>
                <small>porta ${escapeHtml(route.target_host_port || "n/d")} • health ${escapeHtml(route.health_path || "/")} ${route.path_warning ? `• ${escapeHtml(route.path_warning)}` : ""}</small>
            </article>
        `).join("")
        : `<div class="empty">Nenhuma rota publica planejada ainda.</div>`;

    webhookHost.innerHTML = `
        <div class="project-webhook-row">
            <span>Webhook URL</span>
            <strong>${escapeHtml(projectWebhookUrl(selected) || "n/d")}</strong>
            <button type="button" data-project-copy="webhook_url">Copiar URL</button>
        </div>
        <div class="project-webhook-row">
            <span>Secret</span>
            <strong>${escapeHtml(selected.webhook?.secret || "n/d")}</strong>
            <button type="button" data-project-copy="webhook_secret">Copiar secret</button>
        </div>
        <div class="project-webhook-row">
            <span>Branch</span>
            <strong>${escapeHtml(selected.branch || "main")}</strong>
        </div>
        <div class="project-webhook-row">
            <span>Uso</span>
            <strong>GitHub push -> ${escapeHtml(selected.webhook?.path || "/hooks/github/...")}</strong>
        </div>
    `;

    bundleHost.innerHTML = bundleArtifacts.length
        ? bundleArtifacts.map((artifact, index) => `
            <article class="bundle-card">
                <div class="bundle-top">
                    <strong>${escapeHtml(artifact.name || artifact.kind || "artefato")}</strong>
                    <span>${escapeHtml(artifact.kind || "arquivo")} • ${escapeHtml(artifact.mode || "generated")}</span>
                </div>
                <div class="bundle-copy">${escapeHtml(artifact.written_to || artifact.path_hint || "")}</div>
                <div class="row-actions">
                    <button type="button" data-project-bundle-copy="${index}">Copiar conteudo</button>
                    <button type="button" data-file-shortcut="${escapeHtml(artifact.written_to || artifact.path_hint || "")}">Abrir arquivo</button>
                </div>
            </article>
        `).join("")
        : `<div class="empty">O bundle aparece aqui depois da analise do projeto.</div>`;

    installHost.innerHTML = Array.isArray(bundle.install_steps) && bundle.install_steps.length
        ? `
            <div class="install-card">
                <div class="metric-label">Passos recomendados</div>
                <ol>
                    ${bundle.install_steps.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}
                </ol>
            </div>
        `
        : "";

    const aiReport = report.ai_report?.content || "";
    aiHost.innerHTML = aiReport ? markdownToHtml(aiReport) : `<div class="empty">A leitura por IA aparece aqui quando voce clicar em "Gerar leitura IA".</div>`;

    deliveriesHost.innerHTML = deliveries.length
        ? deliveries.map((delivery) => `
            <article class="stack-card">
                <div class="stack-head">
                    <strong>${escapeHtml(delivery.event || "evento")}</strong>
                    <span class="status-badge ${projectStatusClass(delivery.status === "processed" ? "ready" : delivery.status === "failed" ? "blocked" : "needs-attention")}">${escapeHtml(delivery.status || "received")}</span>
                </div>
                <div class="stack-meta">${escapeHtml(formatDate(delivery.received_at || ""))} • ${escapeHtml(delivery.ref || "sem ref")}</div>
                <div class="stack-copy">${escapeHtml(delivery.detail || "Sem detalhe.")}</div>
            </article>
        `).join("")
        : `<div class="empty">Nenhuma entrega de webhook registrada ainda.</div>`;
    deploymentsHost.innerHTML = deployments.length
        ? deployments.map((deployment) => `
            <article class="stack-card">
                <div class="stack-head">
                    <strong>release ${escapeHtml(deployment.release_id || deployment.id || "n/d")}</strong>
                    <span class="status-badge ${projectStatusClass(deployment.status === "success" ? "ready" : deployment.status === "failed" ? "blocked" : "needs-attention")}">${escapeHtml(deployment.status || "running")}</span>
                </div>
                <div class="stack-meta">${escapeHtml(formatDate(deployment.requested_at || ""))} • ${escapeHtml(deployment.reason || "manual")}</div>
                <div class="stack-copy">${escapeHtml(deployment.detail || "Sem detalhe.")}</div>
            </article>
        `).join("")
        : `<div class="empty">Nenhum deploy executado ainda.</div>`;
    proxyDecorateCodeBlocks();
}

async function loadProjects(showMessage = false) {
    const payload = await api("/api/projects");
    state.projects = Array.isArray(payload.projects) ? payload.projects : [];
    if (!state.selectedProjectId && state.projects.length) {
        state.selectedProjectId = state.projects[0].id;
    } else if (state.selectedProjectId && !state.projects.some((project) => project.id === state.selectedProjectId)) {
        state.selectedProjectId = state.projects[0]?.id || "";
    }
    if (state.selectedProjectId) {
        fillProjectForm(projectSelected());
    }
    renderProjects();
    if (showMessage) {
        showToast("Catalogo de projetos atualizado.", "success");
    }
}

function projectFormPayload() {
    const repoUrl = qs("#projectRepoUrlInput").value.trim();
    const managedCheckout = qs("#projectManagedCheckoutInput").checked || state.projectWizardMode === "simple";
    return {
        id: qs("#projectIdInput").value.trim(),
        name: qs("#projectNameInput").value.trim() || projectDeriveNameFromUrl(repoUrl),
        repo_path: managedCheckout ? "" : qs("#projectRepoPathInput").value.trim(),
        repo_url: repoUrl,
        branch: qs("#projectBranchInput").value.trim() || "main",
        default_domain: qs("#projectDomainInput").value.trim(),
        default_base_path: qs("#projectBasePathInput").value.trim() || "/",
        enabled: qs("#projectEnabledInput").checked,
        auto_deploy: qs("#projectAutoDeployInput").checked,
        source_mode: managedCheckout ? "managed" : "manual",
        setup_mode: state.projectWizardMode,
    };
}

async function saveProject({ quiet = false } = {}) {
    const payload = projectFormPayload();
    if (!payload.repo_url && !payload.repo_path) {
        showToast("Informe a URL do repositorio ou um caminho manual na VM.", "error");
        return null;
    }
    if (!payload.name && !payload.repo_url) {
        showToast("Informe um nome para o projeto.", "error");
        return null;
    }
    if (payload.source_mode === "manual" && !payload.repo_path) {
        showToast("No modo avancado manual, informe o caminho do repositorio na VM.", "error");
        return null;
    }
    const saved = await api("/api/projects", { method: "POST", body: JSON.stringify(payload) });
    state.selectedProjectId = saved.id;
    await loadProjects(false);
    fillProjectForm(projectSelected());
    if (!quiet) {
        showToast("Projeto salvo com sucesso.", "success");
    }
    return saved;
}

async function quickDeployProject() {
    const saved = await saveProject({ quiet: true });
    if (!saved) return;
    const payload = await api(`/api/projects/${encodeURIComponent(saved.id)}/bootstrap`, {
        method: "POST",
        body: JSON.stringify({}),
    });
    const project = payload.project;
    state.projects = state.projects.map((item) => item.id === project.id ? project : item);
    if (!state.projects.some((item) => item.id === project.id)) {
        state.projects.push(project);
    }
    state.selectedProjectId = project.id;
    fillProjectForm(projectSelected());
    renderProjects();
    showToast(`Projeto implantado: ${payload.deployment?.release_id || "release"}.`, "success");
}

async function applyProjectFix(candidateId, retryDeploy = false) {
    const projectId = qs("#projectIdInput").value.trim();
    if (!projectId || !candidateId) {
        showToast("Selecione um projeto e uma correcao valida.", "error");
        return;
    }
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/apply-fix`, {
        method: "POST",
        body: JSON.stringify({ candidate_id: candidateId, retry_deploy: retryDeploy }),
    });
    const project = payload.project;
    state.projects = state.projects.map((item) => item.id === project.id ? project : item);
    if (!state.projects.some((item) => item.id === project.id)) {
        state.projects.push(project);
    }
    state.selectedProjectId = project.id;
    fillProjectForm(projectSelected());
    renderProjects();
    showToast(retryDeploy ? "Correcao aplicada e novo deploy iniciado." : "Correcao aplicada com sucesso.", "success");
}

async function analyzeProject(includeAi = false) {
    let projectId = qs("#projectIdInput").value.trim();
    if (!projectId) {
        const saved = await saveProject({ quiet: true });
        if (!saved) return;
        projectId = saved.id;
    }
    const updated = await api(`/api/projects/${encodeURIComponent(projectId)}/analyze`, {
        method: "POST",
        body: JSON.stringify({ include_ai: includeAi }),
    });
    state.projects = state.projects.map((project) => project.id === updated.id ? updated : project);
    state.selectedProjectId = updated.id;
    renderProjects();
    fillProjectForm(projectSelected());
    showToast(includeAi ? "Analise + leitura IA concluida." : "Analise deterministica concluida.", "success");
}

async function rotateProjectSecret() {
    const projectId = qs("#projectIdInput").value.trim();
    if (!projectId) {
        showToast("Selecione um projeto para girar o secret.", "error");
        return;
    }
    const updated = await api(`/api/projects/${encodeURIComponent(projectId)}/rotate-secret`, { method: "POST" });
    state.projects = state.projects.map((project) => project.id === updated.id ? updated : project);
    state.selectedProjectId = updated.id;
    renderProjects();
    fillProjectForm(projectSelected());
    showToast("Secret do webhook atualizado.", "success");
}

async function deleteSelectedProject() {
    const projectId = qs("#projectIdInput").value.trim();
    if (!projectId) {
        showToast("Selecione um projeto para excluir.", "error");
        return;
    }
    await api(`/api/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" });
    state.projects = state.projects.filter((project) => project.id !== projectId);
    state.selectedProjectId = state.projects[0]?.id || "";
    if (state.selectedProjectId) {
        fillProjectForm(projectSelected());
    } else {
        resetProjectForm(true);
    }
    renderProjects();
    showToast("Projeto excluido.", "success");
}

async function deployProject() {
    let projectId = qs("#projectIdInput").value.trim();
    if (!projectId) {
        const saved = await saveProject({ quiet: true });
        if (!saved) return;
        projectId = saved.id;
    }
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/deploy`, {
        method: "POST",
        body: JSON.stringify({ reason: "manual-dashboard" }),
    });
    const project = payload.project;
    state.projects = state.projects.map((item) => item.id === project.id ? project : item);
    if (!state.projects.some((item) => item.id === project.id)) {
        state.projects.push(project);
    }
    state.selectedProjectId = project.id;
    fillProjectForm(projectSelected());
    renderProjects();
    showToast(`Deploy concluido: ${payload.deployment?.release_id || "release"}.`, "success");
}

function renderProxyDraftAttachments() {
    const container = qs("#proxyDraftAttachments");
    if (!container) return;
    const attachments = proxyDraftAttachments();
    container.innerHTML = attachments.length ? proxyRenderAttachmentChips(attachments, "draft") : "";
    container.classList.toggle("empty", attachments.length === 0);
}

function proxyRemoveDraftAttachment(attachmentId) {
    const conversation = proxyEnsureConversation();
    if (!conversation) return;
    conversation.draftAttachments = (conversation.draftAttachments || []).filter((attachment) => attachment.id !== attachmentId);
    persistProxyChatState();
    renderProxyDraftAttachments();
}

function proxyTextFileLike(file) {
    const name = file.name.toLowerCase();
    const mime = (file.type || "").toLowerCase();
    if (mime.startsWith("text/")) return true;
    return [".txt", ".md", ".json", ".js", ".ts", ".tsx", ".jsx", ".py", ".html", ".css", ".csv", ".log", ".xml", ".yml", ".yaml", ".sql"].some((ext) => name.endsWith(ext));
}

function proxyReadFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ""));
        reader.onerror = () => reject(reader.error || new Error("Falha ao ler arquivo."));
        reader.readAsDataURL(file);
    });
}

function proxyReadFileAsText(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ""));
        reader.onerror = () => reject(reader.error || new Error("Falha ao ler arquivo."));
        reader.readAsText(file, "utf-8");
    });
}

async function proxyAttachFiles(fileList) {
    const conversation = proxyEnsureConversation();
    if (!conversation) return;
    const files = Array.from(fileList || []);
    if (!files.length) return;
    const selectedModel = proxySelectedModel();
    const supportsVision = proxyModelSupportsVision(selectedModel);
    const attachments = [];

    for (const file of files) {
        if (file.type.startsWith("image/")) {
            if (!supportsVision) {
                showToast("O modelo selecionado não indica suporte a imagem.", "error");
                continue;
            }
            const dataUrl = await proxyReadFileAsDataUrl(file);
            const [, base64 = ""] = dataUrl.split(",", 2);
            attachments.push(proxyNormalizeAttachment({
                name: file.name,
                mime: file.type || "image/png",
                kind: "image",
                size: file.size,
                data: base64,
                previewUrl: dataUrl,
            }));
            continue;
        }

        if (proxyTextFileLike(file)) {
            const rawText = await proxyReadFileAsText(file);
            const limit = 120_000;
            const truncated = rawText.length > limit;
            attachments.push(proxyNormalizeAttachment({
                name: file.name,
                mime: file.type || "text/plain",
                kind: "text",
                size: file.size,
                text: truncated ? rawText.slice(0, limit) : rawText,
                truncated,
            }));
            continue;
        }

        showToast(`Tipo de arquivo ainda não suportado: ${file.name}`, "info");
    }

    if (!attachments.length) return;
    conversation.draftAttachments = [...(conversation.draftAttachments || []), ...attachments];
    proxyTouchConversation(conversation);
    persistProxyChatState();
    renderProxyDraftAttachments();
    showToast(`${attachments.length} anexo(s) adicionado(s).`, "success");
}

async function proxyCopyToClipboard(text, successMessage = "Conteúdo copiado.") {
    try {
        await navigator.clipboard.writeText(text);
        showToast(successMessage, "success");
    } catch (error) {
        showToast("Não foi possível copiar o conteúdo.", "error");
    }
}

function proxyStartAssistantResponse(conversation) {
    const model = conversation?.model || proxySelectedModel();
    if (!model) {
        showToast("Selecione um modelo antes de enviar.", "error");
        return;
    }
    if (proxyConversationHasVisionAttachments(conversation) && !proxyModelSupportsVision(model)) {
        showToast("Esta conversa tem imagens. Selecione um modelo com suporte a visão para continuar.", "error");
        return;
    }
    if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
        showToast("A conexão em tempo real ainda não está pronta.", "error");
        return;
    }
    const requestId = proxyGenerateId();
    const assistantMessage = proxyNormalizeMessage({
        role: "assistant",
        model,
        content: "",
        streaming: true,
        requestId,
    });
    conversation.messages.push(assistantMessage);
    proxyTouchConversation(conversation);
    conversation.title = proxyConversationTitle(conversation);
    state.proxyChat.pending = true;
    state.proxyChat.activeRequestId = requestId;
    state.proxyChat.activeRequestConversationId = conversation.id;
    persistProxyChatState();
    renderProxyChat();
    renderProxyConversationList();
    proxySyncControlsFromConversation();
    state.socket?.send(JSON.stringify({
        type: "proxy.chat.start",
        payload: {
            request_id: requestId,
            model,
            messages: proxyConversationApiMessages(conversation),
            options: proxyConversationRequestOptions(conversation),
        },
    }));
}

function proxyStopChat() {
    if (!state.proxyChat.pending || !state.proxyChat.activeRequestId) {
        showToast("Não existe resposta em andamento.", "info");
        return;
    }
    if (state.proxyChat.stopping) {
        showToast("A interrupcao ja foi solicitada.", "info");
        return;
    }
    state.proxyChat.stopping = true;
    proxySyncControlsFromConversation();
    showToast("Solicitacao de interrupcao enviada.", "info");
    state.socket?.send(JSON.stringify({ type: "proxy.chat.stop" }));
}

function proxyRegenerateLastAssistant() {
    const conversation = proxyActiveConversation();
    if (!conversation || state.proxyChat.pending) {
        showToast("Pare a resposta atual antes de regenerar.", "info");
        return;
    }
    const last = conversation.messages[conversation.messages.length - 1];
    if (!last || last.role !== "assistant") {
        showToast("Nenhuma resposta anterior para regenerar.", "info");
        return;
    }
    conversation.messages.pop();
    proxyStartAssistantResponse(conversation);
}

function proxyTrimConversationFromMessage(messageId) {
    const found = proxyFindMessage(messageId);
    if (!found) return null;
    found.conversation.messages = found.conversation.messages.slice(0, found.index);
    proxyTouchConversation(found.conversation);
    persistProxyChatState();
    return found.message;
}

function proxyDecorateCodeBlocks() {
    qsa("#proxyChatMessages pre, #overviewAssistantMessages pre, #projectAiReport pre, #projectFixBox pre").forEach((pre, index) => {
        if (pre.querySelector(".code-copy-button")) return;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "code-copy-button";
        button.dataset.codeBlockIndex = String(index);
        button.textContent = "Copiar código";
        pre.prepend(button);
    });
}

function setProxyTab(tab) {
    state.currentProxyTab = tab;
    qsa(".proxy-tab-button").forEach((button) => {
        button.classList.toggle("active", button.dataset.proxyTab === tab);
    });
    qsa(".proxy-tab-panel").forEach((panel) => {
        panel.classList.toggle("active", panel.id === `proxy-tab-${tab}`);
    });
}

function renderProxy() {
    if (!state.proxy) return;

    setProxyTab(state.currentProxyTab || "chat");

    const proxy = state.proxy;
    const summary = proxy.summary || {};
    const service = proxy.service || {};
    const models = proxy.models || [];
    const tagsPreview = (proxy.tags_preview || [])
        .map((item) => item.name || item.model || JSON.stringify(item))
        .slice(0, 6)
        .join(", ");
    const conversation = proxyEnsureConversation();

    if (models.length && (!conversation.model || !models.includes(conversation.model))) {
        conversation.model = models[0];
        proxyTouchConversation(conversation);
        persistProxyChatState();
    }

    qs("#proxyMetricStatus").textContent = translateServiceState(service.active || "unknown");
    qs("#proxyMetricService").textContent = `${service.service || "red-ollama-proxy.service"} / PID ${service.main_pid || 0}`;
    qs("#proxyMetricKeys").textContent = String(summary.total || 0);
    qs("#proxyMetricKeysMeta").textContent = `${summary.active || 0} ativas / ${summary.cooldown || 0} em cooldown`;
    qs("#proxyMetricRequests").textContent = String(summary.total_requests || 0);
    qs("#proxyMetricRequestsMeta").textContent = `${summary.successes || 0} sucessos / ${summary.failures || 0} falhas`;
    qs("#proxyMetricModel").textContent = conversation.model || "--";
    qs("#proxyMetricTags").textContent = proxy.tags_status === 200 ? (tagsPreview || "tags disponíveis") : (proxy.tags_error || "sem resposta");

    qs("#proxySummary").innerHTML = `
        <div class="kv-item"><span>Servico</span><strong>${escapeHtml(translateServiceState(service.active || "unknown"))} / ${escapeHtml(translateServiceState(service.sub || "unknown"))}</strong></div>
        <div class="kv-item"><span>Unit file</span><strong>${escapeHtml(translateServiceState(service.unit_file_state || "unknown"))}</strong></div>
        <div class="kv-item"><span>Proxy local</span><strong>${escapeHtml(proxy.proxy_url || "n/d")}</strong></div>
        <div class="kv-item"><span>Upstream</span><strong>${escapeHtml(proxy.upstream || "n/d")}</strong></div>
        <div class="kv-item"><span>Arquivo de keys</span><strong>${escapeHtml(proxy.keys_file || "n/d")}</strong></div>
        <div class="kv-item"><span>Arquivo de log</span><strong>${escapeHtml(proxy.log_file || "n/d")}</strong></div>
        <div class="kv-item"><span>Cache</span><strong>${Number(proxy.cache?.entries || 0)} entradas</strong></div>
        <div class="kv-item"><span>Tags</span><strong>HTTP ${proxy.tags_status || 0}</strong></div>
    `;

    const keyCards = (proxy.keys || [])
        .map((key) => `
            <article class="stack-card">
                <div class="stack-head">
                    <div>
                        <strong>${escapeHtml(key.label || `Key ${key.id}`)}</strong>
                        <small>${escapeHtml(key.key_masked || "sem valor")}</small>
                    </div>
                    <span class="pill ${key.active ? "active" : "failed"}">${key.active ? "ativa" : "inativa"}</span>
                </div>
                <div class="stack-meta">
                    <span>ID ${escapeHtml(key.id)}</span>
                    <span>${Number(key.total_requests || 0)} req / ${Number(key.successes || 0)} ok / ${Number(key.failures || 0)} falhas</span>
                    <span>${formatSeconds(key.cooldown_remaining || 0)}</span>
                </div>
                <div class="row-actions">
                    <button data-proxy-key-edit="${escapeHtml(key.id)}">editar</button>
                    <button data-proxy-key-toggle="${escapeHtml(key.id)}:${key.active ? "off" : "on"}">${key.active ? "desativar" : "ativar"}</button>
                    <button data-proxy-key-reset="${escapeHtml(key.id)}">zerar metricas</button>
                    <button class="danger" data-proxy-key-delete="${escapeHtml(key.id)}">excluir</button>
                </div>
            </article>
        `)
        .join("");
    qs("#proxyKeysList").innerHTML = keyCards || `<div class="empty">Nenhuma key cadastrada ainda.</div>`;

    const select = qs("#proxyModelSelect");
    if (select) {
        if (models.length) {
            select.innerHTML = models.map((model) => `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`).join("");
            select.value = conversation.model || models[0];
        } else {
            select.innerHTML = `<option value="">Nenhum modelo disponível</option>`;
        }
    }

    const modelInfo = qs("#proxyModelInfo");
    if (modelInfo) {
        modelInfo.textContent = proxy.tags_status === 200
            ? (tagsPreview || "Modelos carregados com sucesso.")
            : (proxy.tags_error || "Cadastre uma key válida para carregar os modelos via api/tags.");
    }

    const capabilityHost = qs("#proxyModelCapabilities");
    if (capabilityHost) {
        const capabilities = proxyModelCapabilities(conversation.model);
        capabilityHost.innerHTML = capabilities.length
            ? capabilities.map((item) => `<span class="capability-pill">${escapeHtml(item)}</span>`).join("")
            : `<span class="capability-pill muted">capacidades indisponíveis</span>`;
    }

    const attachmentHint = qs("#proxyAttachmentHint");
    if (attachmentHint) {
        attachmentHint.textContent = proxyModelSupportsVision(conversation.model)
            ? "Este modelo aceita imagens e também arquivos de texto/código."
            : "Este modelo aceita arquivos de texto/código. Imagens só serão enviadas para modelos com visão.";
    }

    proxySyncControlsFromConversation();
    renderProxyConversationList();
    renderProxyDraftAttachments();
    renderProxyChat();
    renderProxyImageGenerator();
}

function renderProxyConversationList() {
    const list = qs("#proxyConversationList");
    if (!list) return;
    const ordered = [...state.proxyChat.conversations].sort((a, b) => `${b.updatedAt}`.localeCompare(`${a.updatedAt}`));
    replaceScrollableContent(list, ordered.map((conversation) => `
        <article class="conversation-card ${conversation.id === state.proxyChat.activeConversationId ? "active" : ""}">
            <button class="conversation-select" data-proxy-conversation-select="${escapeHtml(conversation.id)}" type="button">
                <strong>${escapeHtml(proxyConversationTitle(conversation))}</strong>
                <span>${escapeHtml(proxyConversationPreview(conversation))}</span>
                <small>${escapeHtml(formatDate(conversation.updatedAt))}</small>
            </button>
            <button class="conversation-delete" data-proxy-conversation-delete="${escapeHtml(conversation.id)}" type="button" aria-label="Excluir conversa">×</button>
        </article>
    `).join(""));
}

function renderProxyLogs() {
    const stream = qs("#proxyLogStream");
    if (!stream) return;
    replaceScrollableContent(stream, (state.proxyLogs || [])
        .map((entry) => {
            const row = normalizeProxyLog(entry);
            if (!row) return "";
            const meta = [row.timestamp, row.level, row.endpoint, row.status_code ? `HTTP ${row.status_code}` : "", row.key_id ? `key ${row.key_id}` : ""]
                .filter(Boolean)
                .join(" | ");
            return `<div><strong>${escapeHtml(meta)}</strong>\n${escapeHtml(row.message)}</div>`;
        })
        .join(""));
}

function appendProxyLogs(lines) {
    const entries = (lines || []).map(normalizeProxyLog).filter(Boolean);
    state.proxyLogs.push(...entries);
    state.proxyLogs = state.proxyLogs.slice(-400);
    renderProxyLogs();
}

function renderProxyChat() {
    const shell = qs("#proxyChatMessages");
    const conversation = proxyEnsureConversation();
    if (!shell || !conversation) return;

    if (!conversation.messages.length) {
        shell.innerHTML = `<div class="empty">Escolha um modelo, ajuste o prompt de sistema se quiser e comece a conversa.</div>`;
        return;
    }

    const memory = captureScrollState(shell);
    shell.innerHTML = conversation.messages.map((message) => {
        const role = message.role === "assistant" ? "assistant" : "user";
        const content = role === "assistant"
            ? markdownToHtml(message.content || (message.streaming ? "_Gerando resposta..._" : ""))
            : `<p>${escapeHtml(message.content || "")}</p>`;
        const attachments = (message.attachments || []).length
            ? `<div class="attachment-message-list">${proxyRenderAttachmentChips(message.attachments, "message")}</div>`
            : "";
        const status = message.streaming
            ? `<span class="chat-badge active">respondendo</span>`
            : message.stopped
                ? `<span class="chat-badge">interrompida</span>`
                : message.error
                    ? `<span class="chat-badge error">erro</span>`
                    : "";
        const actions = [
            `<button type="button" data-proxy-chat-copy="${escapeHtml(message.id)}">Copiar</button>`,
            role === "assistant" && !message.streaming ? `<button type="button" data-proxy-chat-use="${escapeHtml(message.id)}">Usar no prompt</button>` : "",
            role === "user" && !state.proxyChat.pending ? `<button type="button" data-proxy-chat-edit="${escapeHtml(message.id)}">Editar e reenviar</button>` : "",
            role === "assistant" && !message.streaming && !state.proxyChat.pending ? `<button type="button" data-proxy-chat-retry="${escapeHtml(message.id)}">Regenerar daqui</button>` : "",
        ].filter(Boolean).join("");
        return `
            <article class="chat-message ${role}">
                <div class="chat-avatar">${role === "assistant" ? "IA" : "VOCE"}</div>
                <div class="chat-bubble">
                    <div class="chat-meta">${role === "assistant" ? "Assistente" : "Você"}${message.model ? ` • ${escapeHtml(message.model)}` : ""} • ${escapeHtml(formatDate(message.createdAt))} ${status}</div>
                    ${attachments}
                    <div class="chat-markdown">${content}</div>
                    <div class="chat-message-actions">${actions}</div>
                </div>
            </article>
        `;
    }).join("");
    restoreScrollState(shell, memory);
    proxyDecorateCodeBlocks();
}

function whatsappModels() {
    return Array.isArray(state.proxy?.models) ? state.proxy.models : [];
}

function whatsappTargetById(chatId) {
    return (state.whatsapp?.targets || []).find((item) => item.chat_id === chatId) || null;
}

function whatsappRespondModeLabel(mode) {
    return {
        always: "sempre",
        prefix_or_mention: "prefixo ou menção",
        never: "nunca",
    }[mode] || "prefixo ou menção";
}

function whatsappConnectionReady(connectionState) {
    return ["open", "connected"].includes(String(connectionState || "").toLowerCase());
}

function whatsappChecklistItem(label, done, detail) {
    return `
        <article class="stack-card whatsapp-check-item ${done ? "ok" : "pending"}">
            <div class="stack-head">
                <strong>${escapeHtml(label)}</strong>
                <span class="status-badge ${done ? "healthy" : "warning"}">${done ? "ok" : "pendente"}</span>
            </div>
            <small>${escapeHtml(detail || "")}</small>
        </article>
    `;
}

function discardWhatsAppConfigChanges() {
    setWhatsAppConfigDirty(false);
    renderWhatsApp();
    showToast("Alterações locais descartadas.", "info");
}

function renderWhatsApp() {
    const snapshot = state.whatsapp;
    if (!snapshot) return;

    const config = snapshot.config || {};
    const connection = snapshot.connection || {};
    const runtime = snapshot.runtime || {};
    const targets = snapshot.targets || [];
    const models = whatsappModels();
    const aiEnabledCount = targets.filter((target) => target.ai_enabled && !target.muted).length;
    const alertsEnabledCount = targets.filter((target) => target.alerts_enabled && !target.muted).length;
    const elevatedCount = targets.filter((target) => target.admin || target.shell_enabled).length;
    const dirty = Boolean(state.whatsappUi.configDirty);

    const modelSelect = qs("#whatsappDefaultModelSelect");
    if (modelSelect) {
        const currentValue = dirty ? modelSelect.value : (config.default_model || "");
        if (models.length) {
            modelSelect.innerHTML = [`<option value="">Selecionar modelo</option>`]
                .concat(models.map((model) => `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`))
                .join("");
            modelSelect.value = currentValue || "";
        } else {
            modelSelect.innerHTML = `<option value="">Nenhum modelo disponivel</option>`;
        }
    }

    const assignValue = (selector, value) => {
        const field = qs(selector);
        if (field) field.value = value ?? "";
    };
    const assignChecked = (selector, value) => {
        const field = qs(selector);
        if (field) field.checked = Boolean(value);
    };

    if (!dirty) {
        assignValue("#whatsappBaseUrlInput", config.base_url || "");
        assignValue("#whatsappApiKeyInput", "");
        assignValue("#whatsappInstanceNameInput", config.instance_name || "red-whatsapp-ai");
        assignValue("#whatsappInstanceTokenInput", config.instance_token || "");
        assignValue("#whatsappBotNumberInput", config.bot_number || "");
        assignValue("#whatsappGroupPrefixInput", config.group_prefix || "red,");
        assignValue("#whatsappWebhookSecretInput", config.webhook_secret || "");
        assignValue("#whatsappSystemPromptInput", config.system_prompt || "");
        assignValue("#whatsappContextMaxMessagesInput", config.context?.max_messages || 28);
        assignValue("#whatsappContextMaxCharsInput", config.context?.max_chars || 14000);
        assignValue("#whatsappSummaryTriggerInput", config.context?.summary_trigger_messages || 20);
        assignValue("#whatsappSummaryKeepRecentInput", config.context?.summary_keep_recent || 10);
        assignChecked("#whatsappEnabledInput", config.enabled);
        assignChecked("#whatsappTypingPresenceInput", config.typing_presence);
        assignChecked("#whatsappMarkAsReadInput", config.mark_as_read);
        assignChecked("#whatsappAutoSyncTargetsInput", config.auto_sync_targets);
    }
    renderWhatsAppConfigState();

    const kpis = qs("#whatsappKpis");
    if (kpis) {
        kpis.innerHTML = `
            <article class="metric-card compact">
                <div class="metric-label">Instancia</div>
                <div class="metric-value">${escapeHtml(connection.state || "n/d")}</div>
                <div class="metric-meta">${snapshot.configured ? "configurada" : "nao configurada"}</div>
            </article>
            <article class="metric-card compact">
                <div class="metric-label">IA habilitada</div>
                <div class="metric-value">${Number(aiEnabledCount || 0)}</div>
                <div class="metric-meta">destinos prontos para conversar</div>
            </article>
            <article class="metric-card compact">
                <div class="metric-label">Alertas ativos</div>
                <div class="metric-value">${Number(alertsEnabledCount || 0)}</div>
                <div class="metric-meta">contatos e grupos monitorados</div>
            </article>
            <article class="metric-card compact">
                <div class="metric-label">Conversas</div>
                <div class="metric-value">${Number(snapshot.conversation_count || 0)}</div>
                <div class="metric-meta">${elevatedCount ? `${elevatedCount} com acesso elevado` : "memória persistida"}</div>
            </article>
        `;
    }

    const summary = qs("#whatsappSummary");
    if (summary) {
        summary.innerHTML = `
            <div class="kv-item"><span>Webhook</span><strong>${escapeHtml(snapshot.webhook?.url || "n/d")}</strong></div>
            <div class="kv-item"><span>Secret</span><strong>${escapeHtml(config.webhook_secret_masked || "n/d")}</strong></div>
            <div class="kv-item"><span>URL Evolution</span><strong>${escapeHtml(config.base_url || "n/d")}</strong></div>
            <div class="kv-item"><span>API key</span><strong>${escapeHtml(config.api_key_masked || "n/d")}</strong></div>
            <div class="kv-item"><span>Estado</span><strong>${escapeHtml(connection.state || "n/d")}</strong></div>
            <div class="kv-item"><span>Status HTTP</span><strong>${escapeHtml(connection.status_code ?? "n/d")}</strong></div>
            <div class="kv-item"><span>Última sync</span><strong>${escapeHtml(formatDate(runtime.last_targets_sync_at))}</strong></div>
            <div class="kv-item"><span>Sync de chats</span><strong>${escapeHtml(runtime.last_targets_sync_status || "pendente")}</strong></div>
            <div class="kv-item"><span>Webhook remoto</span><strong>${escapeHtml(runtime.last_webhook_sync_status || "pendente")}</strong></div>
            <div class="kv-item"><span>Webhook sync</span><strong>${escapeHtml(formatDate(runtime.last_webhook_sync_at))}</strong></div>
        `;
    }

    const webhookHint = qs("#whatsappWebhookHint");
    if (webhookHint) {
        webhookHint.textContent = `Webhook esperado: ${snapshot.webhook?.url || "n/d"}`;
    }

    const runtimeBox = qs("#whatsappRuntimeBox");
    if (runtimeBox) {
        const qr = runtime.qrcode_base64 || "";
        const syncMeta = runtime.last_targets_sync_at
            ? `${Number(runtime.last_targets_sync_count || 0)} itens importados (${Number(runtime.last_targets_sync_chats || 0)} chats e ${Number(runtime.last_targets_sync_groups || 0)} grupos)`
            : "Aguardando a primeira sincronização de contatos e grupos.";
        runtimeBox.innerHTML = `
            <div class="panel-head compact">
                <div>
                    <div class="eyebrow">PAREAMENTO</div>
                    <h2>Estado da conexao</h2>
                </div>
            </div>
            <div class="kv-grid">
                <div class="kv-item"><span>Ultimo evento</span><strong>${escapeHtml(runtime.last_event || "n/d")}</strong></div>
                <div class="kv-item"><span>Connection state</span><strong>${escapeHtml(runtime.connection_state || connection.state || "n/d")}</strong></div>
                <div class="kv-item"><span>Pairing code</span><strong>${escapeHtml(runtime.pairing_code || "n/d")}</strong></div>
                <div class="kv-item"><span>Atualizado</span><strong>${escapeHtml(formatDate(runtime.updated_at))}</strong></div>
            </div>
            <div class="chat-hint">${escapeHtml(syncMeta)}</div>
            ${runtime.last_targets_sync_error ? `<div class="chat-hint">${escapeHtml(runtime.last_targets_sync_error)}</div>` : ""}
            ${qr ? `<div class="whatsapp-qr-shell"><img class="whatsapp-qr-image" src="${escapeHtml(qr)}" alt="QR Code do WhatsApp" /></div>` : `<div class="empty">Clique em "Conectar / QR". Se a Evolution emitir um QR por webhook, ele aparece aqui.</div>`}
        `;
    }

    const identity = qs("#whatsappInstanceIdentity");
    if (identity) {
        const instance = snapshot.instance || {};
        identity.innerHTML = `
            <div class="kv-item"><span>Numero</span><strong>${escapeHtml(instance.owner || config.bot_number || "n/d")}</strong></div>
            <div class="kv-item"><span>Perfil</span><strong>${escapeHtml(instance.profile_name || "n/d")}</strong></div>
            <div class="kv-item"><span>Status</span><strong>${escapeHtml(instance.status || connection.state || "n/d")}</strong></div>
            <div class="kv-item"><span>Integracao</span><strong>${escapeHtml(instance.integration || "n/d")}</strong></div>
        `;
    }

    const checklist = qs("#whatsappChecklist");
    if (checklist) {
        const webhookReady = Boolean(snapshot.webhook?.url && config.webhook_secret_masked);
        const hasModels = models.length > 0;
        checklist.innerHTML = [
            whatsappChecklistItem("Configuracao base", snapshot.configured, snapshot.configured ? "Evolution e credenciais preenchidas." : "Preencha URL e API key da Evolution."),
            whatsappChecklistItem("Instancia conectada", whatsappConnectionReady(connection.state), whatsappConnectionReady(connection.state) ? "Numero conectado e pronto para receber mensagens." : "Conecte o QR ou confira a sessao."),
            whatsappChecklistItem("Webhook preparado", webhookReady && runtime.last_webhook_sync_status === "success", webhookReady && runtime.last_webhook_sync_status === "success" ? "Webhook sincronizado com sucesso na Evolution." : "A VM ja gerou a URL, mas a sincronizacao remota ainda precisa confirmar."),
            whatsappChecklistItem("Chats sincronizados", Number(runtime.last_targets_sync_count || 0) > 0, Number(runtime.last_targets_sync_count || 0) > 0 ? `${Number(runtime.last_targets_sync_count || 0)} destinos importados.` : "Ainda nao ha contatos ou grupos carregados."),
            whatsappChecklistItem("Modelo disponivel", hasModels, hasModels ? `${models.length} modelos detectados no proxy IA.` : "Cadastre uma key valida no proxy para liberar a IA."),
            whatsappChecklistItem("Prompt operacional", Boolean((config.system_prompt || "").trim()), Boolean((config.system_prompt || "").trim()) ? "System prompt definido para o RED Whatsapp A.I." : "Defina um prompt-base para a IA."),
        ].join("");
    }

    renderWhatsAppTargets();
    renderWhatsAppConversations();
    renderWhatsAppLogs();
    setWhatsAppTab(state.whatsappTab);
}

function renderWhatsAppTargets() {
    const host = qs("#whatsappTargetsList");
    if (!host) return;
    const allTargets = [...(state.whatsapp?.targets || [])].sort((a, b) => `${a.kind}:${a.name || a.chat_id}`.localeCompare(`${b.kind}:${b.name || b.chat_id}`));
    const filter = (qs("#whatsappTargetsSearchInput")?.value || "").trim().toLowerCase();
    const targets = filter
        ? allTargets.filter((target) => `${target.name || ""} ${target.chat_id || ""} ${target.kind || ""}`.toLowerCase().includes(filter))
        : allTargets;
    const hint = qs("#whatsappTargetsHint");
    if (hint) {
        hint.textContent = `${targets.length} de ${allTargets.length} destinos visíveis. Defina quem recebe alertas, quem fala com a IA e quem pode executar shell.`;
    }
    const stats = qs("#whatsappTargetsStats");
    if (stats) {
        const groups = allTargets.filter((target) => target.kind === "group").length;
        const aiEnabled = allTargets.filter((target) => target.ai_enabled && !target.muted).length;
        const alertsEnabled = allTargets.filter((target) => target.alerts_enabled && !target.muted).length;
        const elevated = allTargets.filter((target) => target.admin || target.shell_enabled).length;
        stats.innerHTML = `
            <article class="metric-card compact"><div class="metric-label">Total</div><div class="metric-value">${allTargets.length}</div><div class="metric-meta">${groups} grupos e ${Math.max(0, allTargets.length - groups)} privados</div></article>
            <article class="metric-card compact"><div class="metric-label">IA ativa</div><div class="metric-value">${aiEnabled}</div><div class="metric-meta">respondem ao assistente</div></article>
            <article class="metric-card compact"><div class="metric-label">Alertas</div><div class="metric-value">${alertsEnabled}</div><div class="metric-meta">monitoramento ligado</div></article>
            <article class="metric-card compact"><div class="metric-label">Acesso elevado</div><div class="metric-value">${elevated}</div><div class="metric-meta">admin ou shell</div></article>
        `;
    }
    host.innerHTML = targets.length
        ? targets.map((target) => `
            <article class="stack-card whatsapp-target-card">
                <div class="whatsapp-target-head">
                    <div class="whatsapp-target-meta">
                        <strong>${escapeHtml(target.name || target.chat_id)}</strong>
                        <small>${escapeHtml(target.chat_id)}</small>
                    </div>
                    <div class="whatsapp-target-actions">
                        <div class="component-pills whatsapp-target-pills">
                            <span>${escapeHtml(target.kind === "group" ? "grupo" : "privado")}</span>
                            <span>${escapeHtml(whatsappRespondModeLabel(target.respond_mode))}</span>
                            <span>${escapeHtml(target.model || state.whatsapp?.config?.default_model || "modelo padrão")}</span>
                        </div>
                        <button class="ghost-button" data-whatsapp-target-open="${escapeHtml(target.chat_id)}" type="button">Abrir memória</button>
                    </div>
                </div>
                <div class="whatsapp-target-flags">
                    <label class="checkbox-field compact">
                        <input type="checkbox" data-whatsapp-target-toggle="${escapeHtml(target.chat_id)}:alerts_enabled" ${target.alerts_enabled ? "checked" : ""} />
                        <span>alertas</span>
                    </label>
                    <label class="checkbox-field compact">
                        <input type="checkbox" data-whatsapp-target-toggle="${escapeHtml(target.chat_id)}:ai_enabled" ${target.ai_enabled ? "checked" : ""} />
                        <span>IA</span>
                    </label>
                    <label class="checkbox-field compact">
                        <input type="checkbox" data-whatsapp-target-toggle="${escapeHtml(target.chat_id)}:shell_enabled" ${target.shell_enabled ? "checked" : ""} />
                        <span>shell</span>
                    </label>
                    <label class="checkbox-field compact">
                        <input type="checkbox" data-whatsapp-target-toggle="${escapeHtml(target.chat_id)}:admin" ${target.admin ? "checked" : ""} />
                        <span>admin</span>
                    </label>
                    <label class="checkbox-field compact">
                        <input type="checkbox" data-whatsapp-target-toggle="${escapeHtml(target.chat_id)}:muted" ${target.muted ? "checked" : ""} />
                        <span>silenciado</span>
                    </label>
                </div>
                <div class="whatsapp-target-config">
                    <label>
                        <span>modo</span>
                        <select data-whatsapp-target-select="${escapeHtml(target.chat_id)}:respond_mode">
                            <option value="always" ${target.respond_mode === "always" ? "selected" : ""}>sempre</option>
                            <option value="prefix_or_mention" ${target.respond_mode === "prefix_or_mention" ? "selected" : ""}>prefixo ou mencao</option>
                            <option value="never" ${target.respond_mode === "never" ? "selected" : ""}>nunca</option>
                        </select>
                    </label>
                    <label>
                        <span>prefixo</span>
                        <input type="text" value="${escapeHtml(target.prefix_override || "")}" data-whatsapp-target-input="${escapeHtml(target.chat_id)}:prefix_override" placeholder="usa o global" />
                    </label>
                    <label>
                        <span>modelo</span>
                        <select data-whatsapp-target-select="${escapeHtml(target.chat_id)}:model">
                            <option value="">padrao</option>
                            ${whatsappModels().map((model) => `<option value="${escapeHtml(model)}" ${target.model === model ? "selected" : ""}>${escapeHtml(model)}</option>`).join("")}
                        </select>
                    </label>
                </div>
            </article>
        `).join("")
        : `<div class="empty">${allTargets.length ? "Nenhum destino combina com o filtro atual." : "Nenhum contato ou grupo sincronizado ainda."}</div>`;
}

function renderWhatsAppConversations() {
    const list = qs("#whatsappConversationsList");
    const meta = qs("#whatsappConversationMeta");
    const stream = qs("#whatsappConversationMessages");
    const compose = qs("#whatsappConversationComposeInput");
    const clearButton = qs("#whatsappConversationClearButton");
    const useTestButton = qs("#whatsappConversationUseTestButton");
    const sendButton = qs("#whatsappConversationSendButton");
    if (!list || !meta || !stream) return;

    const allConversations = state.whatsapp?.conversations || [];
    const filter = (qs("#whatsappConversationsSearchInput")?.value || "").trim().toLowerCase();
    const conversations = filter
        ? allConversations.filter((item) => `${item.name || ""} ${item.chat_id || ""} ${item.last_message_preview || ""}`.toLowerCase().includes(filter))
        : allConversations;
    const hint = qs("#whatsappConversationsHint");
    if (hint) {
        hint.textContent = `${conversations.length} de ${allConversations.length} conversas visíveis. Cada chat mantém memória própria, resumo e modelo separado.`;
    }
    const stats = qs("#whatsappConversationsStats");
    if (stats) {
        const groups = allConversations.filter((item) => item.kind === "group").length;
        const withSummary = allConversations.filter((item) => item.summary).length;
        const pendingModelChoice = allConversations.filter((item) => item.pending_model_selection).length;
        stats.innerHTML = `
            <article class="metric-card compact"><div class="metric-label">Total</div><div class="metric-value">${allConversations.length}</div><div class="metric-meta">${groups} grupos com memória separada</div></article>
            <article class="metric-card compact"><div class="metric-label">Resumidas</div><div class="metric-value">${withSummary}</div><div class="metric-meta">contexto compactado pela IA</div></article>
            <article class="metric-card compact"><div class="metric-label">Escolha de modelo</div><div class="metric-value">${pendingModelChoice}</div><div class="metric-meta">aguardando resposta ao configurared</div></article>
            <article class="metric-card compact"><div class="metric-label">Instância</div><div class="metric-value">${escapeHtml(whatsappConnectionReady(state.whatsapp?.connection?.state) ? "pronta" : "pendente")}</div><div class="metric-meta">pronta para conversar</div></article>
        `;
    }
    replaceScrollableContent(list, conversations.length
        ? conversations.map((item) => `
            <article class="conversation-card ${item.chat_id === state.selectedWhatsAppConversationId ? "active" : ""}">
                <button class="conversation-select" data-whatsapp-conversation="${escapeHtml(item.chat_id)}" type="button">
                    <strong>${escapeHtml(item.name || item.chat_id)}</strong>
                    <span>${escapeHtml(item.last_message_preview || "Sem historico")}</span>
                    <small>${escapeHtml(formatDate(item.updated_at || item.last_message_at))}</small>
                </button>
            </article>
        `).join("")
        : `<div class="empty">${allConversations.length ? "Nenhuma conversa combina com o filtro atual." : "Nenhuma conversa salva ainda."}</div>`);

    const detail = state.whatsappConversationDetail;
    if (!detail || !state.selectedWhatsAppConversationId) {
        meta.innerHTML = `<div class="kv-item"><span>Conversa</span><strong>Selecione um chat</strong></div>`;
        stream.innerHTML = `Selecione uma conversa para ver a memoria salva.`;
        if (compose) compose.value = "";
        if (clearButton) clearButton.disabled = true;
        if (useTestButton) useTestButton.disabled = true;
        if (sendButton) sendButton.disabled = true;
        return;
    }

    if (clearButton) clearButton.disabled = false;
    if (useTestButton) useTestButton.disabled = false;
    if (sendButton) sendButton.disabled = false;

    meta.innerHTML = `
        <div class="kv-item"><span>Chat</span><strong>${escapeHtml(detail.name || detail.chat_id)}</strong></div>
        <div class="kv-item"><span>Tipo</span><strong>${escapeHtml(detail.kind || "n/d")}</strong></div>
        <div class="kv-item"><span>Modelo</span><strong>${escapeHtml(detail.model || whatsappTargetById(detail.chat_id)?.model || state.whatsapp?.config?.default_model || "auto")}</strong></div>
        <div class="kv-item"><span>Resumo</span><strong>${detail.summary ? "sim" : "nao"}</strong></div>
        <div class="kv-item"><span>Mensagens</span><strong>${Number(detail.messages?.length || 0)}</strong></div>
        <div class="kv-item"><span>Selecionando modelo</span><strong>${detail.pending_model_selection ? "sim" : "nao"}</strong></div>
    `;
    const memory = captureScrollState(stream);
    stream.innerHTML = (detail.messages || []).length
        ? detail.messages.map((message) => {
            const role = message.role === "assistant" ? "assistant" : (message.role === "system" ? "assistant" : "user");
            const content = role === "assistant" ? markdownToHtml(message.text || "") : `<p>${escapeHtml(message.text || "")}</p>`;
            return `
                <article class="chat-message ${role}">
                    <div class="chat-avatar">${role === "assistant" ? "IA" : "WA"}</div>
                    <div class="chat-bubble">
                        <div class="chat-meta">${escapeHtml(role === "assistant" ? "Assistente" : (message.sender_name || message.sender_jid || "Contato"))} • ${escapeHtml(formatDate(message.at))}</div>
                        <div class="chat-markdown">${content}</div>
                    </div>
                </article>
            `;
        }).join("")
        : "Sem mensagens salvas nesta conversa.";
    restoreScrollState(stream, memory);
    proxyDecorateCodeBlocks();
}

function renderWhatsAppLogs() {
    const host = qs("#whatsappLogStream");
    if (!host) return;
    replaceScrollableContent(host, (state.whatsapp?.logs || []).map((row) => `
        <div><strong>${escapeHtml([row.timestamp, row.kind, row.level].filter(Boolean).join(" | "))}</strong>\n${escapeHtml(row.message || "")}</div>
    `).join(""));
}

async function refreshWhatsApp(showMessage = true) {
    const payload = await api("/api/whatsapp");
    state.whatsapp = payload;
    if (state.selectedWhatsAppConversationId) {
        try {
            state.whatsappConversationDetail = await api(`/api/whatsapp/conversations/${encodeURIComponent(state.selectedWhatsAppConversationId)}`);
        } catch (_) {
            state.whatsappConversationDetail = null;
        }
    }
    renderWhatsApp();
    if (showMessage) showToast("Painel do WhatsApp atualizado.", "success");
}

async function loadWhatsAppConversation(chatId) {
    state.selectedWhatsAppConversationId = chatId;
    state.whatsappConversationDetail = await api(`/api/whatsapp/conversations/${encodeURIComponent(chatId)}`);
    const testField = qs("#whatsappTestChatInput");
    if (testField) testField.value = chatId;
    renderWhatsAppConversations();
}

async function clearWhatsAppConversation() {
    const chatId = state.selectedWhatsAppConversationId;
    if (!chatId) {
        showToast("Selecione uma conversa primeiro.", "error");
        return;
    }
    await api(`/api/whatsapp/conversations/${encodeURIComponent(chatId)}`, { method: "DELETE" });
    state.selectedWhatsAppConversationId = "";
    state.whatsappConversationDetail = null;
    const compose = qs("#whatsappConversationComposeInput");
    if (compose) compose.value = "";
    showToast("Memoria da conversa removida.", "success");
    await refreshWhatsApp(false);
}

async function sendWhatsAppConversationMessage() {
    const chatId = state.selectedWhatsAppConversationId;
    if (!chatId) {
        showToast("Selecione uma conversa primeiro.", "error");
        return;
    }
    const compose = qs("#whatsappConversationComposeInput");
    const message = compose?.value.trim() || "";
    if (!message) {
        showToast("Digite a mensagem que deseja enviar.", "error");
        return;
    }
    await api("/api/whatsapp/send-test", {
        method: "POST",
        body: JSON.stringify({ chat_id: chatId, message }),
    });
    if (compose) compose.value = "";
    showToast("Mensagem enviada para a conversa selecionada.", "success");
    await refreshWhatsApp(false);
    await loadWhatsAppConversation(chatId);
}

async function saveWhatsAppConfig() {
    const payload = await api("/api/whatsapp/config", {
        method: "POST",
        body: JSON.stringify({
            enabled: qs("#whatsappEnabledInput")?.checked,
            base_url: qs("#whatsappBaseUrlInput")?.value.trim(),
            api_key: qs("#whatsappApiKeyInput")?.value.trim(),
            instance_name: qs("#whatsappInstanceNameInput")?.value.trim(),
            instance_token: qs("#whatsappInstanceTokenInput")?.value.trim(),
            bot_number: qs("#whatsappBotNumberInput")?.value.trim(),
            default_model: qs("#whatsappDefaultModelSelect")?.value || "",
            group_prefix: qs("#whatsappGroupPrefixInput")?.value.trim(),
            webhook_secret: qs("#whatsappWebhookSecretInput")?.value.trim(),
            system_prompt: qs("#whatsappSystemPromptInput")?.value,
            mark_as_read: qs("#whatsappMarkAsReadInput")?.checked,
            typing_presence: qs("#whatsappTypingPresenceInput")?.checked,
            auto_sync_targets: qs("#whatsappAutoSyncTargetsInput")?.checked,
            context_max_messages: qs("#whatsappContextMaxMessagesInput")?.value,
            context_max_chars: qs("#whatsappContextMaxCharsInput")?.value,
            summary_trigger_messages: qs("#whatsappSummaryTriggerInput")?.value,
            summary_keep_recent: qs("#whatsappSummaryKeepRecentInput")?.value,
        }),
    });
    state.whatsapp = payload;
    setWhatsAppConfigDirty(false);
    renderWhatsApp();
    showToast("Configuracao do WhatsApp salva.", "success");
}

async function updateWhatsAppTarget(chatId, changes) {
    await api(`/api/whatsapp/targets/${encodeURIComponent(chatId)}`, {
        method: "POST",
        body: JSON.stringify({
            ...(whatsappTargetById(chatId) || {}),
            ...changes,
        }),
    });
    await refreshWhatsApp(false);
}

async function testWhatsAppConnection() {
    const payload = await api("/api/whatsapp/test", { method: "POST" });
    showToast(`Estado da instancia: ${payload.state || "n/d"}`, payload.status_code === 200 ? "success" : "info");
    await refreshWhatsApp(false);
}

async function createWhatsAppInstance() {
    const payload = await api("/api/whatsapp/instance/create", { method: "POST" });
    showToast(payload.status_code === 200 || payload.status_code === 201 ? "Instancia criada ou atualizada." : "Create instance enviado. Confira o retorno.", "success");
    if (payload.payload) {
        qs("#whatsappLogStream").textContent = JSON.stringify(payload.payload, null, 2);
    }
    await refreshWhatsApp(false);
}

async function connectWhatsAppInstance() {
    const payload = await api("/api/whatsapp/instance/connect", { method: "POST" });
    const stateName = String(payload?.payload?.instance?.state || payload?.payload?.state || "").toLowerCase();
    if (whatsappConnectionReady(stateName)) {
        setWhatsAppTab("targets");
        showToast("WhatsApp conectado. Os chats serão sincronizados automaticamente.", "success");
    } else {
        showToast("Pedido de conexao enviado para a Evolution.", "success");
    }
    if (payload.payload) {
        qs("#whatsappLogStream").textContent = JSON.stringify(payload.payload, null, 2);
    }
    await refreshWhatsApp(false);
}

async function syncWhatsAppWebhook() {
    const payload = await api("/api/whatsapp/webhook/sync", { method: "POST" });
    showToast(payload.status_code === 200 ? "Webhook sincronizado na Evolution." : "Sync do webhook enviado. Confira os logs.", "success");
    if (payload.payload) {
        qs("#whatsappLogStream").textContent = JSON.stringify(payload.payload, null, 2);
    }
    await refreshWhatsApp(false);
}

async function syncWhatsAppTargets() {
    const payload = await api("/api/whatsapp/sync-targets", { method: "POST" });
    setWhatsAppTab("targets");
    showToast(`Chats sincronizados: ${payload.imported || 0}.`, "success");
    await refreshWhatsApp(false);
}

async function sendWhatsAppTest() {
    const chatId = qs("#whatsappTestChatInput")?.value.trim();
    if (!chatId) {
        showToast("Informe um destino para o teste.", "error");
        return;
    }
    const message = qs("#whatsappTestMessageInput")?.value.trim() || "Teste do RED Whatsapp A.I";
    await api("/api/whatsapp/send-test", {
        method: "POST",
        body: JSON.stringify({ chat_id: chatId, message }),
    });
    showToast("Mensagem de teste enviada.", "success");
    await refreshWhatsApp(false);
}

function renderJournal() {
    const stream = qs("#journalStream");
    if (!stream) return;
    replaceScrollableContent(stream, state.journal.map((line) => `<div>${escapeHtml(line)}</div>`).join(""));
}

function appendJournal(lines) {
    state.journal.push(...lines);
    state.journal = state.journal.slice(-400);
    const stream = qs("#journalStream");
    if (!stream) return;
    const memory = captureScrollState(stream);
    const fragment = document.createDocumentFragment();
    lines.forEach((line) => {
        const div = document.createElement("div");
        div.textContent = line;
        fragment.appendChild(div);
    });
    stream.appendChild(fragment);
    restoreScrollState(stream, memory);
}

function renderContainerLogs(lines) {
    const host = qs("#containerLogs");
    if (!host) return;
    replaceScrollableContent(host, (lines || []).map((line) => `<div>${escapeHtml(line)}</div>`).join(""));
}

function renderAll() {
    renderOverview();
    renderServices();
    renderDocker();
    renderProcesses();
    renderFirewall();
    renderProxy();
    renderWhatsApp();
    renderProjects();
}

function updateClock() {
    const el = qs("#clockDisplay");
    if (!el) return;
    el.textContent = new Date().toLocaleTimeString("pt-BR");
}

function setView(view) {
    state.currentView = view;
    qsa(".nav-item").forEach((item) => {
        item.classList.toggle("active", item.dataset.view === view);
    });
    qsa(".view").forEach((panel) => {
        panel.classList.toggle("active", panel.id === `view-${view}`);
    });
    const label = {
        overview: "Visão geral",
        services: "Serviços",
        docker: "Docker",
        proxy: "Proxy IA",
        whatsapp: "WhatsApp",
        projects: "Projetos",
        logs: "Logs",
        terminal: "Terminal",
        files: "Arquivos",
        firewall: "Firewall",
        processes: "Processos",
    }[view];
    qs("#pageTitle").textContent = label || "Visão geral";
}

function updateSocketStatus(connected) {
    const el = qs("#socketStatus");
    if (!el) return;
    el.className = `status-pill ${connected ? "connected" : "disconnected"}`;
    el.querySelector("span:last-child").textContent = connected ? "Conexão em tempo real ativa" : "Conexão em tempo real offline";
}

function createWsUrl() {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    return `${protocol}://${window.location.host}${APP_BASE_PATH}/ws`;
}

function connectSocket() {
    const socket = new WebSocket(createWsUrl());
    state.socket = socket;

    socket.addEventListener("open", () => {
        updateSocketStatus(true);
        socket.send(JSON.stringify({ type: "request.snapshot" }));
    });

    socket.addEventListener("close", () => {
        updateSocketStatus(false);
        state.proxyChat.pending = false;
        state.proxyChat.stopping = false;
        state.proxyChat.activeRequestId = "";
        state.proxyChat.activeRequestConversationId = "";
        state.vmAssistant.pending = false;
        state.vmAssistant.stopping = false;
        state.vmAssistant.activeRequestId = "";
        proxySyncControlsFromConversation();
        renderOverviewAssistant();
        setTimeout(connectSocket, 1500);
    });

    socket.addEventListener("message", (event) => {
        const message = JSON.parse(event.data);
        const { type, payload } = message;

        if (type === "bootstrap" || type === "snapshot") {
            state.system = payload.system || state.system;
            state.telemetry = payload.telemetry || state.telemetry;
            state.services = payload.services || state.services;
            state.docker = payload.docker || state.docker;
            state.processes = payload.processes || state.processes;
            state.firewall = payload.firewall || state.firewall;
            state.proxy = payload.proxy || state.proxy;
            state.whatsapp = payload.whatsapp || state.whatsapp;
            state.projects = payload.projects || state.projects;
            if (payload.journal) {
                state.journal = payload.journal.slice(-400);
                renderJournal();
            }
            if (payload.proxy_logs) {
                state.proxyLogs = payload.proxy_logs.slice(-400).map(normalizeProxyLog).filter(Boolean);
                renderProxyLogs();
            }
            if (state.selectedWhatsAppConversationId) {
                loadWhatsAppConversation(state.selectedWhatsAppConversationId).catch(() => {
                    state.whatsappConversationDetail = null;
                    renderWhatsAppConversations();
                });
            }
            renderAll();
        }

        if (type === "journal.append") {
            appendJournal(payload.lines || []);
        }

        if (type === "proxy.log.append") {
            appendProxyLogs(payload.lines || []);
        }

        if (type === "whatsapp.log.append") {
            state.whatsapp = state.whatsapp || {};
            state.whatsapp.logs = [...(state.whatsapp.logs || []), ...(payload.lines || [])].slice(-400);
            renderWhatsAppLogs();
        }

        if (type === "proxy.chat.started") {
            state.proxyChat.pending = true;
            state.proxyChat.stopping = false;
            state.proxyChat.activeRequestId = payload.request_id || state.proxyChat.activeRequestId;
        }

        if (type === "proxy.chat.chunk") {
            state.proxyChat.pending = true;
            state.proxyChat.stopping = false;
            const current = proxyFindStreamingMessage(payload.request_id || state.proxyChat.activeRequestId);
            if (current?.message) {
                current.message.content += payload.chunk || "";
                proxyTouchConversation(current.conversation);
                renderProxyChat();
                persistProxyChatState();
            }
        }

        if (type === "proxy.chat.done") {
            state.proxyChat.pending = false;
            state.proxyChat.stopping = false;
            state.proxyChat.activeRequestId = "";
            state.proxyChat.activeRequestConversationId = "";
            const current = proxyFindStreamingMessage(payload.request_id || "");
            if (current?.message) {
                current.message.streaming = false;
                current.message.content = payload.content || current.message.content;
                current.message.model = payload.model || current.message.model;
                proxyTouchConversation(current.conversation);
                renderProxyChat();
                renderProxyConversationList();
                proxySyncControlsFromConversation();
                persistProxyChatState();
            }
        }

        if (type === "proxy.chat.error") {
            state.proxyChat.pending = false;
            state.proxyChat.stopping = false;
            state.proxyChat.activeRequestId = "";
            state.proxyChat.activeRequestConversationId = "";
            const current = proxyFindStreamingMessage(payload.request_id || "");
            if (current?.message) {
                current.message.streaming = false;
                current.message.error = true;
                current.message.content = `Erro: ${payload.error || "Falha no chat do proxy."}`;
                proxyTouchConversation(current.conversation);
                renderProxyChat();
                renderProxyConversationList();
                proxySyncControlsFromConversation();
                persistProxyChatState();
            } else {
                showToast(payload.error || "Falha no chat do proxy.", "error");
            }
        }

        if (type === "proxy.chat.stopped") {
            state.proxyChat.pending = false;
            state.proxyChat.stopping = false;
            state.proxyChat.activeRequestId = "";
            state.proxyChat.activeRequestConversationId = "";
            const current = proxyFindStreamingMessage(payload.request_id || "");
            if (current?.message) {
                current.message.streaming = false;
                current.message.stopped = true;
                current.message.content = payload.content || current.message.content || "_Resposta interrompida pelo usuário._";
                proxyTouchConversation(current.conversation);
                renderProxyChat();
                renderProxyConversationList();
                proxySyncControlsFromConversation();
                persistProxyChatState();
            }
            showToast("Resposta interrompida.", "info");
        }

        if (type === "vm.assistant.started") {
            state.vmAssistant.pending = true;
            state.vmAssistant.stopping = false;
            state.vmAssistant.activeRequestId = payload.request_id || state.vmAssistant.activeRequestId;
            renderOverviewAssistant();
        }

        if (type === "vm.assistant.chunk") {
            state.vmAssistant.pending = true;
            state.vmAssistant.stopping = false;
            const current = state.vmAssistant.messages.find((message) => message.streaming && message.requestId === (payload.request_id || state.vmAssistant.activeRequestId));
            if (current) {
                current.content += payload.chunk || "";
                renderOverviewAssistant();
            }
        }

        if (type === "vm.assistant.done") {
            state.vmAssistant.pending = false;
            state.vmAssistant.stopping = false;
            state.vmAssistant.activeRequestId = "";
            const current = state.vmAssistant.messages.find((message) => message.streaming && message.requestId === payload.request_id);
            if (current) {
                current.streaming = false;
                current.content = payload.content || current.content;
                current.model = payload.model || current.model;
                persistVmAssistantState();
                renderOverviewAssistant();
            }
        }

        if (type === "vm.assistant.stopped") {
            state.vmAssistant.pending = false;
            state.vmAssistant.stopping = false;
            state.vmAssistant.activeRequestId = "";
            const current = state.vmAssistant.messages.find((message) => message.streaming && message.requestId === payload.request_id);
            if (current) {
                current.streaming = false;
                current.content = payload.content || current.content || "_Análise interrompida._";
                persistVmAssistantState();
                renderOverviewAssistant();
            }
            showToast("Análise da VM interrompida.", "info");
        }

        if (type === "vm.assistant.error") {
            state.vmAssistant.pending = false;
            state.vmAssistant.stopping = false;
            state.vmAssistant.activeRequestId = "";
            const current = state.vmAssistant.messages.find((message) => message.streaming && message.requestId === payload.request_id);
            if (current) {
                current.streaming = false;
                current.content = `Erro: ${payload.error || "Falha no assistente da VM."}`;
                persistVmAssistantState();
                renderOverviewAssistant();
            } else {
                showToast(payload.error || "Falha no assistente da VM.", "error");
            }
        }

        if (type === "terminal.opened") {
            state.terminalSessionId = payload.session_id;
            showToast("Terminal conectado", "success");
        }

        if (type === "terminal.output") {
            const output = qs("#terminalOutput");
            const chunk = stripAnsi(payload.chunk || "");
            const memory = captureScrollState(output);
            output.textContent += chunk;
            restoreScrollState(output, memory);
        }
    });
}

async function doLogin(password) {
    await api("/login", {
        method: "POST",
        body: JSON.stringify({ password }),
    });
    window.location.reload();
}

async function loadBootstrap() {
    const payload = await api("/api/bootstrap");
    state.system = payload.system;
    state.telemetry = payload.telemetry;
    state.services = payload.services;
    state.docker = payload.docker;
    state.processes = payload.processes;
    state.firewall = payload.firewall;
    state.proxy = payload.proxy;
    state.whatsapp = payload.whatsapp || null;
    state.projects = payload.projects || [];
    state.proxyLogs = (payload.proxy_logs || []).map(normalizeProxyLog).filter(Boolean);
    state.journal = payload.journal || [];
    renderAll();
    renderJournal();
    renderProxyLogs();
}

async function refreshProxyPanel(showMessage = true) {
    const payload = await api("/api/proxy");
    state.proxy = payload;
    if (payload.logs) {
        state.proxyLogs = payload.logs.map(normalizeProxyLog).filter(Boolean);
    }
    renderProxy();
    if (showMessage) {
        showToast("Painel do proxy atualizado", "success");
    }
}

function clearProxyChat() {
    if (state.proxyChat.pending) {
        showToast("Pare a resposta atual antes de abrir uma nova conversa.", "info");
        return;
    }
    proxyCreateNewConversation();
}

function sendProxyChat() {
    const conversation = proxyEnsureConversation();
    const input = qs("#proxyChatInput");
    const content = input?.value.trim() || "";
    const draftAttachments = [...(conversation?.draftAttachments || [])];

    if (!content && !draftAttachments.length) {
        showToast("Digite uma mensagem para o chat.", "error");
        return;
    }

    if (state.proxyChat.pending) {
        showToast("Aguarde a resposta atual terminar.", "info");
        return;
    }

    proxySyncConversationFromControls();
    if (draftAttachments.some((attachment) => attachment.kind === "image") && !proxyModelSupportsVision(conversation.model || proxySelectedModel())) {
        showToast("Escolha um modelo com suporte a visão para enviar imagens.", "error");
        return;
    }
    conversation.messages.push(proxyNormalizeMessage({
        role: "user",
        content,
        model: conversation.model || proxySelectedModel(),
        attachments: draftAttachments,
    }));
    conversation.draftAttachments = [];
    conversation.title = proxyConversationTitle(conversation);
    proxyTouchConversation(conversation);
    persistProxyChatState();
    input.value = "";
    resizeProxyChatInput();
    proxyStartAssistantResponse(conversation);
}

function resizeProxyChatInput() {
    const input = qs("#proxyChatInput");
    if (!input) return;
    input.style.height = "0px";
    input.style.height = `${Math.min(Math.max(input.scrollHeight, 128), 320)}px`;
}

function resetProxyImageForm() {
    state.proxyImage.prompt = "";
    state.proxyImage.seed = "";
    state.proxyImage.imageBase64 = "";
    state.proxyImage.durationMs = 0;
    state.proxyImage.error = "";
    renderProxyImageGenerator();
}

async function generateProxyImage() {
    proxySyncImageFromControls();
    const image = state.proxyImage;
    if (!image.model) {
        showToast("Escolha um modelo NVIDIA de imagem.", "error");
        return;
    }
    if (!image.prompt.trim()) {
        showToast("Digite um prompt para gerar a imagem.", "error");
        return;
    }
    if (image.generating) {
        showToast("A imagem ja esta sendo gerada.", "info");
        return;
    }

    image.generating = true;
    image.error = "";
    renderProxyImageGenerator();
    const started = performance.now();
    try {
        const payload = {
            model: image.model,
            prompt: image.prompt.trim(),
            width: Math.round(Number(image.width || 1024)),
            height: Math.round(Number(image.height || 1024)),
            steps: Math.round(Number(image.steps || 4)),
        };
        if (String(image.seed || "").trim()) {
            payload.seed = Math.round(Number(image.seed));
        }
        const response = await api("/api/proxy/images/generate", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        const result = proxyImageResultFromPayload(response);
        if (!result.base64) {
            throw new Error("O proxy respondeu sem imagem.");
        }
        image.imageBase64 = result.base64;
        image.mimeType = result.mimeType;
        image.durationMs = Number(response.duration_ms || response.dashboard_duration_ms || Math.round(performance.now() - started));
        image.seed = response.seed === undefined || response.seed === null ? image.seed : String(response.seed);
        showToast("Imagem gerada com sucesso.", "success");
    } catch (error) {
        image.error = error.message || "Falha ao gerar imagem.";
        showToast(image.error, "error");
    } finally {
        image.generating = false;
        renderProxyImageGenerator();
    }
}

function resetProxyKeyForm() {
    qs("#proxyKeyId").value = "";
    qs("#proxyKeyLabelInput").value = "";
    qs("#proxyKeyValueInput").value = "";
    qs("#proxyKeyActiveInput").checked = true;
}

function fillProxyKeyForm(keyId) {
    const key = (state.proxy?.keys || []).find((item) => Number(item.id) === Number(keyId));
    if (!key) return;
    qs("#proxyKeyId").value = key.id;
    qs("#proxyKeyLabelInput").value = key.label || "";
    qs("#proxyKeyValueInput").value = "";
    qs("#proxyKeyActiveInput").checked = Boolean(key.active);
    showToast(`Editando key ${key.id}. Preencha o campo de chave apenas se quiser trocar o valor.`, "info");
}

async function saveProxyKey() {
    const keyId = qs("#proxyKeyId").value.trim();
    const label = qs("#proxyKeyLabelInput").value.trim();
    const key = qs("#proxyKeyValueInput").value.trim();
    const active = qs("#proxyKeyActiveInput").checked;

    if (!keyId && !key) {
        showToast("Cole uma API key para cadastrar", "error");
        return;
    }

    if (keyId) {
        await api(`/api/proxy/keys/${encodeURIComponent(keyId)}`, {
            method: "POST",
            body: JSON.stringify({ label, key, active }),
        });
        showToast("Key atualizada", "success");
    } else {
        await api("/api/proxy/keys", {
            method: "POST",
            body: JSON.stringify({ label, key, active }),
        });
        showToast("Key adicionada", "success");
    }

    resetProxyKeyForm();
    await refreshProxyPanel(false);
}

async function toggleProxyKey(keyId, mode) {
    await api(`/api/proxy/keys/${encodeURIComponent(keyId)}`, {
        method: "POST",
        body: JSON.stringify({ active: mode === "on" }),
    });
    showToast(mode === "on" ? "Key ativada" : "Key desativada", "success");
    await refreshProxyPanel(false);
}

async function resetProxyKeyMetrics(keyId) {
    await api(`/api/proxy/keys/${encodeURIComponent(keyId)}`, {
        method: "POST",
        body: JSON.stringify({ reset_stats: true }),
    });
    showToast("Métricas da key zeradas", "success");
    await refreshProxyPanel(false);
}

async function deleteProxyKey(keyId) {
    await api(`/api/proxy/keys/${encodeURIComponent(keyId)}`, { method: "DELETE" });
    showToast("Key removida", "success");
    resetProxyKeyForm();
    await refreshProxyPanel(false);
}

async function openDirectory(path) {
    const payload = await api(`/api/files?path=${encodeURIComponent(path)}`);
    state.currentFilePath = payload.current;
    qs("#filePathInput").value = payload.current;
    qs("#fileBrowser").innerHTML = `
        ${payload.parent ? `<button class="file-item directory" data-open-path="${escapeHtml(payload.parent)}">..</button>` : ""}
        ${payload.items.map((item) => `
            <button class="file-item ${item.is_dir ? "directory" : "file"}" data-open-path="${escapeHtml(item.path)}" data-is-dir="${item.is_dir}">
                <span>${escapeHtml(item.name)}</span>
                <small>${item.is_dir ? "pasta" : formatBytes(item.size)}</small>
            </button>
        `).join("")}
    `;
}

async function openFile(path) {
    const payload = await api(`/api/file?path=${encodeURIComponent(path)}`);
    qs("#editorPath").value = payload.path;
    qs("#fileEditor").value = payload.content;
    showToast(`Arquivo aberto: ${payload.name}`, "info");
}

async function saveCurrentFile() {
    const path = qs("#editorPath").value.trim();
    if (!path) {
        showToast("Informe um caminho de arquivo", "error");
        return;
    }
    await api("/api/file", {
        method: "POST",
        body: JSON.stringify({
            path,
            content: qs("#fileEditor").value,
        }),
    });
    showToast("Arquivo salvo", "success");
}

async function serviceAction(unit, action) {
    const payload = await api(`/api/service/${encodeURIComponent(unit)}/${action}`, { method: "POST" });
    showToast(
        payload.success ? `${unit}: ${translateAction(action)} concluído` : payload.stderr || "Falha ao executar a ação no serviço",
        payload.success ? "success" : "error",
    );
    state.socket?.send(JSON.stringify({ type: "request.snapshot" }));
}

async function containerAction(name, action) {
    const payload = await api(`/api/docker/container/${encodeURIComponent(name)}/${action}`, { method: "POST" });
    showToast(
        payload.success ? `Container ${name}: ${translateAction(action)} concluído` : "Erro ao executar a ação no container",
        payload.success ? "success" : "error",
    );
    state.socket?.send(JSON.stringify({ type: "request.snapshot" }));
}

async function loadContainerLogs(name) {
    const payload = await api(`/api/docker/container/${encodeURIComponent(name)}/logs`);
    state.currentContainerLogs = payload.logs || [];
    renderContainerLogs(state.currentContainerLogs);
}

async function dockerPrune() {
    const payload = await api("/api/docker/prune", { method: "POST" });
    showToast(payload.success ? "Limpeza do Docker concluída" : "Falha ao limpar o Docker", payload.success ? "success" : "error");
    state.socket?.send(JSON.stringify({ type: "request.snapshot" }));
}

async function allowFirewallRule() {
    const rule = qs("#firewallAllowInput").value.trim();
    if (!rule) return;
    const payload = await api("/api/firewall/allow", {
        method: "POST",
        body: JSON.stringify({ rule }),
    });
    showToast(payload.success ? "Regra adicionada" : payload.stderr || "Erro ao adicionar a regra", payload.success ? "success" : "error");
    qs("#firewallAllowInput").value = "";
    state.socket?.send(JSON.stringify({ type: "request.snapshot" }));
}

async function deleteFirewallRule() {
    const number = qs("#firewallDeleteInput").value.trim();
    if (!number) return;
    const payload = await api("/api/firewall/delete", {
        method: "POST",
        body: JSON.stringify({ number }),
    });
    showToast(payload.success ? "Regra removida" : payload.stderr || "Erro ao remover a regra", payload.success ? "success" : "error");
    qs("#firewallDeleteInput").value = "";
    state.socket?.send(JSON.stringify({ type: "request.snapshot" }));
}

async function processSignal(pid, signalName) {
    const payload = await api(`/api/process/${pid}/signal`, {
        method: "POST",
        body: JSON.stringify({ signal: signalName }),
    });
    showToast(payload.success ? `Sinal ${signalName} enviado para ${pid}` : "Erro ao sinalizar o processo", payload.success ? "success" : "error");
    state.socket?.send(JSON.stringify({ type: "request.snapshot" }));
}

function ensureTerminal() {
    if (state.terminalSessionId) return;
    state.socket?.send(JSON.stringify({ type: "terminal.open" }));
}

function sendTerminalInput(data) {
    ensureTerminal();
    state.socket?.send(JSON.stringify({
        type: "terminal.input",
        payload: { data },
    }));
}

function wireAuthenticatedUi() {
    hydrateProxyChatState();
    hydrateVmAssistantState();

    qsa(".nav-item").forEach((item) => {
        item.addEventListener("click", () => setView(item.dataset.view));
    });
    qsa(".proxy-tab-button").forEach((button) => {
        button.addEventListener("click", () => setProxyTab(button.dataset.proxyTab));
    });

    qs("#refreshButton").addEventListener("click", () => {
        state.socket?.send(JSON.stringify({ type: "request.snapshot" }));
        showToast("Solicitando atualização do painel", "info");
    });
    qs("#whatsappRefreshButton")?.addEventListener("click", () => runUiTask(() => refreshWhatsApp()));
    qs("#whatsappSaveButton")?.addEventListener("click", () => runUiTask(() => saveWhatsAppConfig()));
    qsa("[data-whatsapp-save]").forEach((button) => {
        button.addEventListener("click", () => runUiTask(() => saveWhatsAppConfig()));
    });
    qsa("[data-whatsapp-discard]").forEach((button) => {
        button.addEventListener("click", discardWhatsAppConfigChanges);
    });
    qs("#whatsappTestButton")?.addEventListener("click", () => runUiTask(() => testWhatsAppConnection()));
    qs("#whatsappCreateInstanceButton")?.addEventListener("click", () => runUiTask(() => createWhatsAppInstance()));
    qs("#whatsappConnectInstanceButton")?.addEventListener("click", () => runUiTask(() => connectWhatsAppInstance()));
    qs("#whatsappSyncWebhookButton")?.addEventListener("click", () => runUiTask(() => syncWhatsAppWebhook()));
    qs("#whatsappSyncTargetsButton")?.addEventListener("click", () => runUiTask(() => syncWhatsAppTargets()));
    qs("#whatsappSendTestButton")?.addEventListener("click", () => runUiTask(() => sendWhatsAppTest()));
    qs("#whatsappConversationUseTestButton")?.addEventListener("click", () => {
        if (!state.selectedWhatsAppConversationId) {
            showToast("Selecione uma conversa primeiro.", "error");
            return;
        }
        setWhatsAppTab("logs");
        const field = qs("#whatsappTestChatInput");
        if (field) field.value = state.selectedWhatsAppConversationId;
        showToast("Conversa aplicada ao envio manual.", "success");
    });
    qs("#whatsappConversationClearButton")?.addEventListener("click", () => runUiTask(() => clearWhatsAppConversation()));
    qs("#whatsappConversationSendButton")?.addEventListener("click", () => runUiTask(() => sendWhatsAppConversationMessage()));
    qsa("[data-whatsapp-tab]").forEach((button) => {
        button.addEventListener("click", () => setWhatsAppTab(button.dataset.whatsappTab));
    });
    whatsappConfigFieldSelectors().forEach((selector) => {
        const field = qs(selector);
        if (!field) return;
        field.addEventListener("input", () => setWhatsAppConfigDirty(true));
        field.addEventListener("change", () => setWhatsAppConfigDirty(true));
    });
    qs("#whatsappTargetsSearchInput")?.addEventListener("input", renderWhatsAppTargets);
    qs("#whatsappConversationsSearchInput")?.addEventListener("input", renderWhatsAppConversations);

    qs("#serviceSearch").addEventListener("input", renderServices);

    document.addEventListener("click", async (event) => {
        const target = event.target.closest("button");
        if (!target) return;

        try {
            if (target.dataset.serviceAction) {
                const [unit, action] = target.dataset.serviceAction.split(":");
                await serviceAction(unit, action);
            }

            if (target.dataset.containerAction) {
                const [name, action] = target.dataset.containerAction.split(":");
                await containerAction(name, action);
            }

            if (target.dataset.containerLogs) {
                await loadContainerLogs(target.dataset.containerLogs);
            }

            if (target.dataset.processSignal) {
                const [pid, signalName] = target.dataset.processSignal.split(":");
                await processSignal(pid, signalName);
            }

            if (target.dataset.whatsappConversation) {
                await loadWhatsAppConversation(target.dataset.whatsappConversation);
            }

            if (target.dataset.whatsappTargetOpen) {
                setWhatsAppTab("conversations");
                await loadWhatsAppConversation(target.dataset.whatsappTargetOpen);
            }

            if (target.dataset.openPath) {
                const isDir = target.dataset.isDir !== "false";
                if (isDir) {
                    await openDirectory(target.dataset.openPath);
                } else {
                    await openFile(target.dataset.openPath);
                }
            }

            if (target.dataset.fileShortcut) {
                const path = target.dataset.fileShortcut;
                if (path.includes(".")) {
                    await openFile(path);
                } else {
                    setView("files");
                    await openDirectory(path);
                }
            }

            if (target.dataset.viewShortcut) {
                setView(target.dataset.viewShortcut);
            }

            if (target.dataset.projectSelect) {
                selectProject(target.dataset.projectSelect);
            }

            if (target.dataset.projectCopy) {
                const selected = projectSelected();
                if (!selected) {
                    throw new Error("Selecione um projeto primeiro.");
                }
                const value = target.dataset.projectCopy === "webhook_url"
                    ? projectWebhookUrl(selected)
                    : (selected.webhook?.secret || "");
                if (!value) {
                    throw new Error("Nada para copiar neste campo.");
                }
                await proxyCopyToClipboard(value, "Valor copiado.");
            }

            if (target.dataset.projectBundleCopy) {
                const selected = projectSelected();
                const artifacts = selected?.analysis?.bundle?.artifacts || [];
                const artifact = artifacts[Number(target.dataset.projectBundleCopy)];
                if (!artifact?.content) {
                    throw new Error("Conteudo do artefato indisponivel.");
                }
                await proxyCopyToClipboard(artifact.content, "Artefato copiado.");
            }

            if (target.dataset.projectFixApply) {
                await applyProjectFix(target.dataset.projectFixApply, false);
            }

            if (target.dataset.projectFixRetry) {
                await applyProjectFix(target.dataset.projectFixRetry, true);
            }

            if (target.dataset.proxyConversationSelect) {
                proxySetActiveConversation(target.dataset.proxyConversationSelect);
            }

            if (target.dataset.proxyConversationDelete) {
                proxyDeleteConversation(target.dataset.proxyConversationDelete);
            }

            if (target.dataset.overviewAiPrompt) {
                sendOverviewAssistantPrompt(target.dataset.overviewAiPrompt);
            }

            if (target.dataset.overviewAiCopy) {
                const message = state.vmAssistant.messages[Number(target.dataset.overviewAiCopy)];
                if (message?.content) {
                    await proxyCopyToClipboard(message.content, "Resposta copiada.");
                }
            }

            if (target.dataset.proxyDraftAttachmentRemove) {
                proxyRemoveDraftAttachment(target.dataset.proxyDraftAttachmentRemove);
            }

            if (target.dataset.proxyChatCopy) {
                const found = proxyFindMessage(target.dataset.proxyChatCopy);
                if (found?.message) {
                    await proxyCopyToClipboard(found.message.content || "", "Mensagem copiada.");
                }
            }

            if (target.dataset.proxyChatUse) {
                const found = proxyFindMessage(target.dataset.proxyChatUse);
                if (found?.message) {
                    qs("#proxyChatInput").value = found.message.content || "";
                    resizeProxyChatInput();
                    qs("#proxyChatInput").focus();
                }
            }

            if (target.dataset.proxyChatEdit) {
                const trimmed = proxyTrimConversationFromMessage(target.dataset.proxyChatEdit);
                if (trimmed) {
                    qs("#proxyChatInput").value = trimmed.content || "";
                    renderProxy();
                    resizeProxyChatInput();
                    qs("#proxyChatInput").focus();
                }
            }

            if (target.dataset.proxyChatRetry) {
                const trimmed = proxyTrimConversationFromMessage(target.dataset.proxyChatRetry);
                if (trimmed) {
                    proxyStartAssistantResponse(proxyActiveConversation());
                }
            }

            if (target.classList.contains("code-copy-button")) {
                const pre = target.closest("pre");
                if (pre) {
                    const code = pre.querySelector("code");
                    await proxyCopyToClipboard(code ? code.textContent : pre.textContent.replace("Copiar código", "").trim(), "Código copiado.");
                }
            }

            if (target.dataset.terminalCommand) {
                setView("terminal");
                ensureTerminal();
                sendTerminalInput(target.dataset.terminalCommand);
            }

            if (target.dataset.serviceShortcut) {
                setView("services");
                qs("#serviceSearch").value = target.dataset.serviceShortcut;
                renderServices();
            }

            if (target.dataset.proxyKeyEdit) {
                fillProxyKeyForm(target.dataset.proxyKeyEdit);
            }

            if (target.dataset.proxyKeyToggle) {
                const [keyId, mode] = target.dataset.proxyKeyToggle.split(":");
                await toggleProxyKey(keyId, mode);
            }

            if (target.dataset.proxyKeyDelete) {
                await deleteProxyKey(target.dataset.proxyKeyDelete);
            }

            if (target.dataset.proxyKeyReset) {
                await resetProxyKeyMetrics(target.dataset.proxyKeyReset);
            }
        } catch (err) {
            showToast(err.message || "Ação falhou", "error");
        }
    });

    document.addEventListener("change", async (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) return;
        try {
            if (target.matches("[data-whatsapp-target-toggle]")) {
                const [chatId, field] = target.dataset.whatsappTargetToggle.split(":");
                await updateWhatsAppTarget(chatId, { [field]: target.checked });
            }
            if (target.matches("[data-whatsapp-target-select]")) {
                const [chatId, field] = target.dataset.whatsappTargetSelect.split(":");
                await updateWhatsAppTarget(chatId, { [field]: target.value });
            }
        } catch (err) {
            showToast(err.message || "Falha ao atualizar destino do WhatsApp.", "error");
        }
    });

    document.addEventListener("blur", async (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement) || !target.matches("[data-whatsapp-target-input]")) return;
        try {
            const [chatId, field] = target.dataset.whatsappTargetInput.split(":");
            await updateWhatsAppTarget(chatId, { [field]: target.value.trim() });
        } catch (err) {
            showToast(err.message || "Falha ao salvar campo do WhatsApp.", "error");
        }
    }, true);

    qs("#dockerPruneButton").addEventListener("click", dockerPrune);
    qs("#clearJournalButton").addEventListener("click", () => {
        state.journal = [];
        renderJournal();
    });
    qs("#openTerminalButton").addEventListener("click", ensureTerminal);
    qs("#clearTerminalButton").addEventListener("click", () => {
        qs("#terminalOutput").textContent = "";
    });
    qs("#proxyRefreshButton").addEventListener("click", () => refreshProxyPanel(true));
    qs("#proxyRestartButton").addEventListener("click", () => serviceAction("red-ollama-proxy.service", "restart"));
    qs("#proxySaveKeyButton").addEventListener("click", saveProxyKey);
    qs("#proxyResetKeyFormButton").addEventListener("click", resetProxyKeyForm);
    qs("#clearProxyLogButton").addEventListener("click", () => {
        state.proxyLogs = [];
        renderProxyLogs();
    });
    qs("#proxyClearChatButton").addEventListener("click", clearProxyChat);
    qs("#proxyNewConversationButton").addEventListener("click", clearProxyChat);
    qs("#proxyRegenerateChatButton").addEventListener("click", proxyRegenerateLastAssistant);
    qs("#proxyStopChatButton").addEventListener("click", proxyStopChat);
    qs("#proxySendChatButton").addEventListener("click", sendProxyChat);
    qs("#proxyImageGenerateButton")?.addEventListener("click", () => runUiTask(generateProxyImage));
    qs("#proxyImageResetButton")?.addEventListener("click", resetProxyImageForm);
    ["#proxyImageModelSelect", "#proxyImagePromptInput", "#proxyImageWidthInput", "#proxyImageHeightInput", "#proxyImageStepsInput", "#proxyImageSeedInput"].forEach((selector) => {
        qs(selector)?.addEventListener("input", proxySyncImageFromControls);
        qs(selector)?.addEventListener("change", () => {
            proxySyncImageFromControls();
            renderProxyImageGenerator();
        });
    });
    qs("#proxyModelSelect").addEventListener("change", () => {
        proxySyncConversationFromControls();
        renderProxy();
    });
    ["#proxySystemPromptInput", "#proxyTemperatureInput", "#proxyTopPInput", "#proxyMaxTokensInput"].forEach((selector) => {
        qs(selector).addEventListener("input", () => {
            proxySyncConversationFromControls();
            proxySyncControlsFromConversation();
        });
    });
    qs("#proxyAttachmentInput").addEventListener("change", async (event) => {
        await proxyAttachFiles(event.target.files);
        event.target.value = "";
    });
    qs("#proxyChatInput").addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            sendProxyChat();
        }
    });
    qs("#whatsappConversationComposeInput")?.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            runUiTask(() => sendWhatsAppConversationMessage());
        }
    });
    qs("#proxyChatInput").addEventListener("input", resizeProxyChatInput);
    qs("#overviewAssistantClearButton").addEventListener("click", clearOverviewAssistant);
    qs("#overviewAssistantStopButton").addEventListener("click", stopOverviewAssistant);
    qs("#overviewAssistantSendButton").addEventListener("click", () => sendOverviewAssistantPrompt());
    qs("#overviewAssistantModelSelect").addEventListener("change", (event) => {
        state.vmAssistant.model = event.target.value;
        persistVmAssistantState();
        renderOverviewAssistant();
    });
    qs("#overviewAssistantInput").addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            sendOverviewAssistantPrompt();
        }
    });
    qs("#projectsRefreshButton").addEventListener("click", () => loadProjects(true));
    qs("#projectsNewButton").addEventListener("click", () => {
        resetProjectForm(false);
        qs("#projectRepoUrlInput").focus();
    });
    qs("#projectResetFormButton").addEventListener("click", () => {
        if (state.selectedProjectId) {
            fillProjectForm(projectSelected());
        } else {
            resetProjectForm(false);
        }
    });
    qsa("[data-project-mode]").forEach((button) => {
        button.addEventListener("click", () => setProjectWizardMode(button.dataset.projectMode));
    });
    qs("#projectManagedCheckoutInput").addEventListener("change", syncProjectManagedCheckoutUi);
    qs("#projectRepoUrlInput").addEventListener("blur", () => {
        const nameInput = qs("#projectNameInput");
        if (nameInput.value.trim()) return;
        const derived = projectDeriveNameFromUrl(qs("#projectRepoUrlInput").value.trim());
        if (derived) {
            nameInput.value = derived;
        }
    });
    qs("#projectQuickDeployButton").addEventListener("click", () => runUiTask(quickDeployProject));
    qs("#projectSaveButton").addEventListener("click", () => runUiTask(() => saveProject()));
    qs("#projectAnalyzeButton").addEventListener("click", () => runUiTask(() => analyzeProject(false)));
    qs("#projectAnalyzeAiButton").addEventListener("click", () => runUiTask(() => analyzeProject(true)));
    qs("#projectDeployButton").addEventListener("click", () => runUiTask(deployProject));
    qs("#projectRotateSecretButton").addEventListener("click", () => runUiTask(rotateProjectSecret));
    qs("#projectDeleteButton").addEventListener("click", () => runUiTask(deleteSelectedProject));

    qs("#terminalInput").addEventListener("keydown", (event) => {
        if (event.key !== "Enter") return;
        event.preventDefault();
        const value = event.target.value;
        if (!value.trim()) return;
        sendTerminalInput(`${value}\n`);
        event.target.value = "";
    });

    qs("#openPathButton").addEventListener("click", async () => {
        await openDirectory(qs("#filePathInput").value.trim() || "/");
    });

    qs("#saveFileButton").addEventListener("click", saveCurrentFile);
    qs("#firewallAllowButton").addEventListener("click", allowFirewallRule);
    qs("#firewallDeleteButton").addEventListener("click", deleteFirewallRule);

    connectSocket();
    loadBootstrap().then(() => {
        try {
            setProjectWizardMode(window.localStorage.getItem(PROJECT_WIZARD_MODE_KEY) || "simple");
        } catch (_) {
            setProjectWizardMode("simple");
        }
        try {
            setWhatsAppTab(window.localStorage.getItem(WHATSAPP_TAB_STORAGE_KEY) || "connection");
        } catch (_) {
            setWhatsAppTab("connection");
        }
        syncProjectManagedCheckoutUi();
        resizeProxyChatInput();
        openDirectory("/");
        if (state.selectedProjectId) {
            fillProjectForm(projectSelected());
        }
    });
    updateClock();
    setInterval(updateClock, 1000);
}

function wireLoginUi() {
    const form = qs("#loginForm");
    if (!form) return;
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const password = qs("#password").value;
        const error = qs("#loginError");
        error.textContent = "";
        try {
            await doLogin(password);
        } catch (err) {
            error.textContent = err.message || "Falha no login";
        }
    });
}

document.addEventListener("DOMContentLoaded", () => {
    lucide.createIcons();
    if (window.REDVM_AUTHENTICATED) {
        wireAuthenticatedUi();
    } else {
        wireLoginUi();
    }
});
