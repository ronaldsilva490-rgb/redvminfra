const fs = require("fs");
const http = require("http");
const path = require("path");
const { WebSocketServer } = require("ws");

const host = "0.0.0.0";
const port = Number(process.env.PORT || 2580);
const buildLabel = process.env.RED_SEB_MONITOR_BUILD || "RED 2026.04.18.2";
const defaultSebLaunchBase = process.env.RED_SEB_DEFAULT_LINK_BASE || "sebs://digital.uniateneu.edu.br/mod/quiz/accessrule/seb/config.php?cmid=";
const downloadsRoot = process.env.SEB_REMOTE_VIEW_DOWNLOADS_DIR || "/opt/red-seb-monitor/data/downloads";
const repoRoot = process.env.REDVM_REPO_DIR || "/opt/redvm-repo";
const dashboardRoot = process.env.RED_DASHBOARD_DIR || "/opt/redvm-dashboard";
const rediaRoot = process.env.REDIA_DIR || "/opt/redia";
const portalRoot = process.env.RED_PORTAL_DIR || "/var/www/red-portal";
const proxyBase = String(process.env.RED_PROXY_BASE || "http://127.0.0.1:8080").replace(/\/+$/, "");
const committeeDefaultVisionPrimary = process.env.RED_SEB_COMMITTEE_VISION_PRIMARY || "NIM - meta/llama-3.2-11b-vision-instruct";
const committeeDefaultVisionSecondary = process.env.RED_SEB_COMMITTEE_VISION_SECONDARY || "NIM - nvidia/nemotron-nano-12b-v2-vl";
const committeeDefaultLead = process.env.RED_SEB_COMMITTEE_LEAD || "NIM - nvidia/llama-3.1-nemotron-nano-8b-v1";
const debugStreamToken = String(process.env.RED_SEB_DEBUG_TOKEN || "").trim();
const sessions = new Map();
const downloadCandidates = {
  setupMsi: [
    path.join(downloadsRoot, "Setup.msi"),
    "/opt/seb-remote-view/downloads/Setup.msi"
  ],
  setupBundle: [
    path.join(downloadsRoot, "SetupBundle.exe"),
    "/opt/seb-remote-view/downloads/SetupBundle.exe"
  ],
  portableZip: [
    path.join(downloadsRoot, "REDSEBPortable.zip"),
    "/opt/seb-remote-view/downloads/REDSEBPortable.zip"
  ],
  upgradeScript: [
    path.join(downloadsRoot, "upgrade-seb.ps1"),
    "/opt/seb-remote-view/downloads/upgrade-seb.ps1"
  ]
};

const assetCandidates = {
  logo: [
    path.join(repoRoot, "identidade", "logo", "logo.png"),
    path.join(dashboardRoot, "static", "logo.png"),
    path.join(rediaRoot, "public", "assets", "logo.png"),
    path.join(portalRoot, "assets", "logo.png"),
    "/opt/redvm-repo/identidade/logo/logo.png",
    "/opt/redvm-dashboard/static/logo.png",
    "/opt/redia/public/assets/logo.png",
    "/var/www/red-portal/assets/logo.png"
  ],
  favicon: [
    path.join(repoRoot, "identidade", "logo", "favicon.ico"),
    path.join(dashboardRoot, "static", "favicon.ico"),
    path.join(rediaRoot, "public", "favicon.ico"),
    path.join(portalRoot, "assets", "favicon.ico"),
    "/opt/redvm-repo/identidade/logo/favicon.ico",
    "/opt/redvm-dashboard/static/favicon.ico",
    "/opt/redia/public/favicon.ico",
    "/var/www/red-portal/assets/favicon.ico"
  ]
};

function pick(payload, ...keys) {
  for (const key of keys) {
    if (payload[key] !== undefined && payload[key] !== null) {
      return payload[key];
    }
  }

  return undefined;
}

function now() {
  return new Date().toISOString();
}

function slugifyFragment(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
}

function deriveViewId(payload) {
  const explicit = String(pick(payload, "viewId", "ViewId") || "").trim();
  if (explicit) {
    return explicit;
  }

  const windowId = Number(pick(payload, "windowId", "WindowId") || 0);
  if (Number.isFinite(windowId) && windowId > 0) {
    return `window-${windowId}`;
  }

  if (Boolean(pick(payload, "isMainWindow", "IsMainWindow"))) {
    return "main-window";
  }

  const titleFragment = slugifyFragment(pick(payload, "title", "Title"));
  if (titleFragment) {
    return `title-${titleFragment}`;
  }

  const urlFragment = slugifyFragment(pick(payload, "url", "Url"));
  if (urlFragment) {
    return `url-${urlFragment}`;
  }

  return `view-${Date.now()}`;
}

function resolveAsset(type) {
  for (const candidate of assetCandidates[type] || []) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  return null;
}

function resolveCandidate(candidates) {
  for (const candidate of candidates || []) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  return null;
}

const resolvedAssets = {
  favicon: resolveAsset("favicon"),
  logo: resolveAsset("logo")
};
const resolvedDownloads = {
  setupMsi: resolveCandidate(downloadCandidates.setupMsi),
  setupBundle: resolveCandidate(downloadCandidates.setupBundle),
  portableZip: resolveCandidate(downloadCandidates.portableZip),
  upgradeScript: resolveCandidate(downloadCandidates.upgradeScript)
};

function readAsset(filePath) {
  try {
    return fs.readFileSync(filePath);
  } catch {
    return null;
  }
}

function contentTypeFor(filePath) {
  const extension = path.extname(filePath || "").toLowerCase();

  switch (extension) {
    case ".png":
      return "image/png";
    case ".svg":
      return "image/svg+xml";
    case ".ico":
      return "image/x-icon";
    case ".msi":
      return "application/x-msi";
    case ".ps1":
      return "text/plain; charset=utf-8";
    case ".zip":
      return "application/zip";
    default:
      return "application/octet-stream";
  }
}

function sendJson(response, statusCode, payload) {
  response.writeHead(statusCode, { "Content-Type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(payload));
}

function readRequestBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];

    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    request.on("error", reject);
  });
}

function normalizeDuration(value) {
  const parsed = Number(value);

  if (!Number.isFinite(parsed)) {
    return 1000;
  }

  return Math.max(250, Math.min(10000, Math.round(parsed)));
}

function normalizePosition(value) {
  const normalized = String(value || "").toLowerCase();
  const allowed = new Set(["top-left", "top-right", "bottom-left", "bottom-right"]);

  return allowed.has(normalized) ? normalized : "top-right";
}

function requestToken(request) {
  const authHeader = String(request.headers.authorization || "").trim();
  if (/^bearer\s+/i.test(authHeader)) {
    return authHeader.replace(/^bearer\s+/i, "").trim();
  }

  return String(request.headers["x-red-seb-debug-token"] || "").trim();
}

function isLoopbackRequest(request) {
  const remoteAddress = String(request?.socket?.remoteAddress || "").trim();
  return remoteAddress === "::1" || remoteAddress === "127.0.0.1" || remoteAddress === "::ffff:127.0.0.1";
}

function authorizeDebugRequest(request) {
  if (debugStreamToken) {
    return requestToken(request) === debugStreamToken;
  }

  return isLoopbackRequest(request);
}

function normalizeSebLink(value) {
  const raw = String(value || "").trim();

  if (!raw) {
    return { ok: false, error: "Cole o CMID ou o link completo do SEB." };
  }

  if (/^\d+$/.test(raw)) {
    return {
      ok: true,
      link: `${defaultSebLaunchBase}${raw}`,
      cmid: raw,
      mode: "cmid"
    };
  }

  const link = raw;

  if (!/^sebs?:\/\//i.test(link)) {
    return { ok: false, error: "Informe apenas o CMID numerico ou um link que comece com seb:// ou sebs://." };
  }

  try {
    const parsed = new URL(link);

    if (!parsed.hostname) {
      return { ok: false, error: "O link informado nao possui host valido." };
    }

    const cmid = parsed.searchParams.get("cmid") || "";
    return { ok: true, link, cmid, mode: "link" };
  } catch {
    return { ok: false, error: "Nao foi possivel interpretar o link informado." };
  }
}

function buildPortableLauncherBat(sebLink) {
  const escapedLink = sebLink.replace(/"/g, '""');

  return [
    "@echo off",
    "setlocal",
    'set "SEB_PORTABLE=1"',
    'set "SEB_DIR=%USERPROFILE%\\Desktop\\REDSEBPortable"',
    'if defined OneDrive set "SEB_DIR_ONEDRIVE=%OneDrive%\\Desktop\\REDSEBPortable"',
    'if not exist "%SEB_DIR%\\SafeExamBrowser.exe" if defined SEB_DIR_ONEDRIVE if exist "%SEB_DIR_ONEDRIVE%\\SafeExamBrowser.exe" set "SEB_DIR=%SEB_DIR_ONEDRIVE%"',
    'if not exist "%SEB_DIR%\\SafeExamBrowser.exe" (',
    "  echo RED SEB Portable nao encontrado.",
    "  echo.",
    "  echo Coloque a pasta REDSEBPortable na area de trabalho deste usuario.",
    '  echo Caminho esperado: "%USERPROFILE%\\Desktop\\REDSEBPortable"',
    "  pause",
    "  exit /b 1",
    ")",
    'start "RED SEB Portable" "%SEB_DIR%\\SafeExamBrowser.exe" "' + escapedLink + '"',
    "exit /b 0",
    ""
  ].join("\r\n");
}

function downloadFilenameFromSeb(normalized) {
  const cmid = String(normalized?.cmid || "").trim();
  if (cmid && /^\d+$/.test(cmid)) {
    return `redseb-${cmid}.bat`;
  }

  return "redseb-link.bat";
}

function getSessionState() {
  return Array.from(sessions.values())
    .sort((left, right) => String(right.timestamp).localeCompare(String(left.timestamp)))
    .map((session) => {
      const views = Array.from((session.views || new Map()).values())
        .sort((left, right) => {
          if (left.isMainWindow !== right.isMainWindow) {
            return left.isMainWindow ? -1 : 1;
          }

          if (left.windowId !== right.windowId) {
            return left.windowId - right.windowId;
          }

          return String(right.timestamp).localeCompare(String(left.timestamp));
        });
      const primaryView = views[0] || {};

      return {
        sessionId: session.sessionId,
        application: session.application,
        title: primaryView.title || "",
        url: primaryView.url || "",
        width: primaryView.width || 0,
        height: primaryView.height || 0,
        timestamp: session.timestamp,
        connectedAt: session.connectedAt,
        remoteAddress: session.remoteAddress,
        lastAlert: session.lastAlert || null,
        imageBase64: primaryView.imageBase64 || "",
        views
      };
    });
}

function getSummary() {
  const items = getSessionState();
  const withFrames = items.reduce((total, item) => total + item.views.filter((view) => view.imageBase64).length, 0);

  return {
    activeSessions: items.length,
    sessionsWithFrames: withFrames,
    lastUpdate: items[0] ? items[0].timestamp : null
  };
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function sendAlertToSession(sessionId, alert) {
  const session = sessions.get(sessionId);
  const socket = session && session.socket;

  if (!session || !socket || socket.readyState !== socket.OPEN) {
    return false;
  }

  socket.send(JSON.stringify({
    type: "alert",
    message: alert.message,
    position: alert.position,
    durationMs: alert.durationMs,
    viewId: alert.viewId || null
  }));

  return true;
}

function createViewState(payload) {
  const windowId = Number(pick(payload, "windowId", "WindowId") || 0);

  return {
    viewId: deriveViewId(payload),
    windowId: Number.isFinite(windowId) ? windowId : 0,
    isMainWindow: Boolean(pick(payload, "isMainWindow", "IsMainWindow")),
    title: pick(payload, "title", "Title") || "",
    url: pick(payload, "url", "Url") || "",
    width: pick(payload, "width", "Width") || 0,
    height: pick(payload, "height", "Height") || 0,
    timestamp: pick(payload, "timestamp", "Timestamp") || now(),
    imageBase64: pick(payload, "imageBase64", "ImageBase64") || ""
  };
}

function ensureSession(sessionId, request, socket, payload) {
  const current = sessions.get(sessionId) || {};
  const views = current.views || new Map();

  return {
    ...current,
    sessionId,
    application: pick(payload, "application", "Application") || current.application || "SafeExamBrowser",
    connectedAt: current.connectedAt || now(),
    remoteAddress: request?.socket?.remoteAddress || current.remoteAddress || "debug",
    socket: socket || current.socket || null,
    timestamp: pick(payload, "timestamp", "Timestamp") || current.timestamp || now(),
    views
  };
}

function ingestSebPayload(payload, request, socket = null) {
  const sessionId = String(pick(payload, "sessionId", "SessionId") || `session-${Date.now()}`);
  const current = ensureSession(sessionId, request, socket, payload);
  const view = createViewState(payload);

  if (!current.connectedAt || !current.views.has(view.viewId)) {
    console.log("seb-live payload:", JSON.stringify({
      keys: Object.keys(payload || {}),
      sessionId,
      viewId: view.viewId,
      title: pick(payload, "title", "Title"),
      url: pick(payload, "url", "Url"),
      width: pick(payload, "width", "Width"),
      height: pick(payload, "height", "Height"),
      imageLength: (pick(payload, "imageBase64", "ImageBase64") || "").length
    }));
  }

  current.views.set(view.viewId, view);
  current.timestamp = view.timestamp;
  sessions.set(sessionId, current);
  return { sessionId, viewId: view.viewId };
}

function normalizeDebugFramePayload(payload) {
  const sessionId = String(payload.sessionId || payload.SessionId || "").trim() || "debug-session";
  const viewId = String(payload.viewId || payload.ViewId || "").trim() || "main-window";
  const imageBase64 = String(payload.imageBase64 || payload.ImageBase64 || "").trim();
  const width = Number(payload.width || payload.Width || 1280);
  const height = Number(payload.height || payload.Height || 720);

  if (!imageBase64) {
    throw new Error("imageBase64 obrigatorio.");
  }

  return {
    sessionId,
    viewId,
    application: String(payload.application || payload.Application || "SafeExamBrowser"),
    title: String(payload.title || payload.Title || "RED SEB Debug Session"),
    url: String(payload.url || payload.Url || "https://debug.local/frame"),
    width: Number.isFinite(width) ? Math.max(1, Math.round(width)) : 1280,
    height: Number.isFinite(height) ? Math.max(1, Math.round(height)) : 720,
    imageBase64,
    isMainWindow: Boolean(payload.isMainWindow ?? payload.IsMainWindow ?? true),
    windowId: Number(payload.windowId || payload.WindowId || 1) || 1,
    timestamp: now()
  };
}

function resolveCommitteeDefaults(models) {
  const ids = new Set((models || []).map((model) => String(model.id || "")));
  const pickFirst = (candidates, fallback = "") => {
    for (const candidate of candidates) {
      if (ids.has(candidate)) {
        return candidate;
      }
    }
    return fallback;
  };

  return {
    visionPrimary: pickFirst(
      [
        committeeDefaultVisionPrimary,
        "NIM - meta/llama-3.2-11b-vision-instruct",
        "NIM - nvidia/nemotron-nano-12b-v2-vl",
        "qwen3-vl:235b-instruct"
      ],
      committeeDefaultVisionPrimary
    ),
    visionSecondary: pickFirst(
      [
        committeeDefaultVisionSecondary,
        "NIM - nvidia/nemotron-nano-12b-v2-vl",
        "NIM - meta/llama-3.2-90b-vision-instruct",
        "qwen3-vl:235b-instruct"
      ],
      committeeDefaultVisionSecondary
    ),
    lead: pickFirst(
      [
        committeeDefaultLead,
        "NIM - nvidia/llama-3.1-nemotron-nano-8b-v1",
        "NIM - abacusai/dracarys-llama-3.1-70b-instruct",
        "qwen3-next:80b"
      ],
      committeeDefaultLead
    )
  };
}

async function fetchProxyJson(pathname, options = {}) {
  const controller = new AbortController();
  const timeoutMs = Number(options.timeoutMs || 120000);
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(proxyBase + pathname, {
      method: options.method || "GET",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {})
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: controller.signal
    });
    const text = await response.text();
    let payload = {};

    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      payload = { raw: text };
    }

    if (!response.ok) {
      const message = payload?.error?.message || payload?.error || payload?.detail || payload?.raw || ("HTTP " + response.status);
      throw new Error(String(message));
    }

    return payload;
  } finally {
    clearTimeout(timer);
  }
}

function extractChatText(payload) {
  const choice = Array.isArray(payload?.choices) ? payload.choices[0] : null;
  const message = choice?.message || {};
  const content = message.content;

  if (typeof content === "string") {
    return content.trim();
  }

  if (Array.isArray(content)) {
    return content
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item.text === "string") return item.text;
        return "";
      })
      .join("")
      .trim();
  }

  return "";
}

function committeeVisionPrompt() {
  return [
    "Analise esta captura do Safe Exam Browser com muito cuidado.",
    "Descreva exatamente o que esta visivel na imagem em portugues do Brasil.",
    "Inclua: contexto geral da tela, textos legiveis, areas da interface, sinais importantes, possiveis riscos ou bloqueios, e qualquer detalhe relevante para operacao.",
    "Nao invente nada. Se algo estiver incerto, diga claramente."
  ].join(" ");
}

function committeeMemberSystemPrompt(roleLabel) {
  return [
    "Voce faz parte do comite de analise visual da RED Systems.",
    "Seu papel neste turno e: " + roleLabel + ".",
    "Receba os relatórios visuais, pense como operador tecnico e responda em portugues do Brasil.",
    "Seja objetivo, preciso e util. Nao invente elementos que nao estejam no relatorio."
  ].join(" ");
}

function buildCommitteeBrief(context) {
  const parts = [
    "FRAME ATUAL DO SEB",
    "Sessao: " + (context.session?.sessionId || "n/d"),
    "View: " + (context.view?.viewId || "n/d"),
    "Titulo: " + (context.view?.title || context.session?.title || "n/d"),
    "URL: " + (context.view?.url || context.session?.url || "n/d"),
    "Viewport: " + ((context.view?.width || 0) + "x" + (context.view?.height || 0)),
    "",
    "RELATORIO VISUAL A",
    context.visionPrimary || "Sem resposta.",
    "",
    "RELATORIO VISUAL B",
    context.visionSecondary || "Sem resposta.",
    "",
    "TAREFA",
    "Com base nesses relatórios, diga o que a tela mostra, o que merece atenção e qual seria a próxima ação sensata do operador."
  ];

  return parts.join("\n");
}

function normalizeModelCatalogItems(items) {
  return (Array.isArray(items) ? items : []).map((item) => ({
    id: String(item.id || ""),
    provider: String(item.provider || ""),
    kind: String(item.kind || ""),
    note: String(item.note || ""),
    capabilities: Array.isArray(item.capabilities) ? item.capabilities.map((value) => String(value)) : []
  }));
}

function prioritizeModels(models, preferredIds) {
  const priority = new Map((preferredIds || []).map((id, index) => [String(id || ""), index]));
  return (models || []).slice().sort((left, right) => {
    const leftRank = priority.has(left.id) ? priority.get(left.id) : 999;
    const rightRank = priority.has(right.id) ? priority.get(right.id) : 999;
    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }
    return String(left.id || "").localeCompare(String(right.id || ""));
  });
}

async function fetchCommitteeModelCatalog() {
  const payload = await fetchProxyJson("/api/router/models", { timeoutMs: 30000 });
  const models = normalizeModelCatalogItems(payload?.models);
  const defaults = resolveCommitteeDefaults(models);
  const visionModels = prioritizeModels(
    models.filter((model) => model.capabilities.includes("vision")),
    [defaults.visionPrimary, defaults.visionSecondary, "NIM - meta/llama-3.2-90b-vision-instruct", "qwen3-vl:235b-instruct"]
  );
  const leadModels = prioritizeModels(
    models.filter((model) => model.capabilities.includes("chat") && !model.capabilities.includes("vision")),
    [defaults.lead, "NIM - abacusai/dracarys-llama-3.1-70b-instruct", "NIM - deepseek-ai/deepseek-v3.1", "qwen3-next:80b"]
  );
  return {
    visionModels,
    leadModels,
    defaults
  };
}

function resolveActiveSessionAndView(sessionId, viewId) {
  const session = sessions.get(String(sessionId || ""));
  if (!session) {
    throw new Error("Sessao do SEB nao encontrada.");
  }

  const views = Array.from(session.views || new Map().values());
  if (!views.length) {
    throw new Error("A sessao atual ainda nao publicou nenhuma view.");
  }

  const view = views.find((item) => String(item.viewId || "") === String(viewId || "")) || views[0];
  if (!view?.imageBase64) {
    throw new Error("A view atual ainda nao possui frame valido para analise.");
  }

  return { session, view };
}

async function requestVisionExtraction(model, frameBase64) {
  const payload = await fetchProxyJson("/v1/chat/completions", {
    method: "POST",
    timeoutMs: 180000,
    body: {
      model,
      stream: false,
      temperature: 0.2,
      max_tokens: 700,
      messages: [
        { role: "system", content: "Voce e um analista visual rigoroso da RED Systems." },
        {
          role: "user",
          content: [
            { type: "text", text: committeeVisionPrompt() },
            { type: "image_url", image_url: { url: "data:image/jpeg;base64," + frameBase64 } }
          ]
        }
      ]
    }
  });

  return extractChatText(payload);
}

function extractStreamDelta(chunkPayload) {
  const choices = Array.isArray(chunkPayload?.choices) ? chunkPayload.choices : [];
  let text = "";

  for (const choice of choices) {
    const delta = choice?.delta || {};
    if (typeof delta.content === "string") {
      text += delta.content;
      continue;
    }

    if (Array.isArray(delta.content)) {
      for (const item of delta.content) {
        if (typeof item === "string") {
          text += item;
        } else if (item && typeof item.text === "string") {
          text += item.text;
        }
      }
    }
  }

  return text;
}

function writeNdjsonEvent(response, payload) {
  response.write(JSON.stringify(payload) + "\n");
}

async function streamCommitteeMember(member, prompt, response) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 180000);
  let finalText = "";

  try {
    const upstream = await fetch(proxyBase + "/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        model: member.model,
        stream: true,
        temperature: 0.4,
        max_tokens: 900,
        messages: [
          { role: "system", content: committeeMemberSystemPrompt(member.role) },
          { role: "user", content: prompt }
        ]
      })
    });

    if (!upstream.ok || !upstream.body) {
      const errorText = await upstream.text().catch(() => "");
      throw new Error(errorText || ("Falha ao iniciar stream do modelo " + member.model));
    }

    writeNdjsonEvent(response, { type: "member_begin", memberId: member.id, role: member.role, model: member.model });
    const reader = upstream.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const chunk = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const dataLines = chunk
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trim())
          .filter(Boolean);

        for (const dataLine of dataLines) {
          if (dataLine === "[DONE]") {
            continue;
          }

          try {
            const payload = JSON.parse(dataLine);
            const delta = extractStreamDelta(payload);
            if (delta) {
              finalText += delta;
              writeNdjsonEvent(response, { type: "member_delta", memberId: member.id, delta });
            }
          } catch {
            // ignore malformed event chunk
          }
        }

        boundary = buffer.indexOf("\n\n");
      }

      if (done) {
        break;
      }
    }

    writeNdjsonEvent(response, { type: "member_done", memberId: member.id, text: finalText.trim() });
  } finally {
    clearTimeout(timer);
  }
}

function renderDashboard() {
  const logoTag = resolvedAssets.logo
    ? '<img class="brand-logo" src="/assets/logo" alt="RED logo">'
    : '<div class="brand-mark">R</div>';

  return `<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RED SEB Monitor</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Space+Grotesk:wght@400;500;700&display=swap" rel="stylesheet">
  <link rel="icon" href="/assets/favicon">
  <style>
    :root {
      --bg: #1a0202;
      --bg-elevated: #240303;
      --bg-panel: #3b0505;
      --bg-panel-soft: #580707;
      --panel: rgba(25, 3, 3, 0.66);
      --panel-strong: rgba(34, 4, 4, 0.84);
      --panel-muted: rgba(232, 228, 227, 0.08);
      --line: rgba(232, 68, 44, 0.18);
      --line-strong: rgba(232, 68, 44, 0.34);
      --text: #fff3f1;
      --muted: #d9b7b3;
      --accent: #db2315;
      --accent-strong: #ee4d31;
      --accent-hot: #ff7a59;
      --chrome: #e8e4e3;
      --success: #34d399;
      --warning: #fbbf24;
      --danger: #ee4d31;
      --shadow: 0 28px 80px rgba(12, 0, 0, 0.62);
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      min-height: 100%;
      font-family: "Space Grotesk", "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top, rgba(238, 77, 49, 0.20), transparent 16rem),
        radial-gradient(circle at 82% 18%, rgba(219, 35, 21, 0.14), transparent 20rem),
        linear-gradient(180deg, rgba(88, 7, 7, 0.46), rgba(26, 2, 2, 0.96) 58%),
        linear-gradient(140deg, #140202 0%, #1f0303 52%, #100101 100%);
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      background:
        linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
      background-size: 34px 34px;
      mask-image: radial-gradient(circle at center, black 42%, transparent 100%);
      pointer-events: none;
      opacity: 0.22;
    }
    .shell {
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr);
      gap: 18px;
      min-height: 100vh;
      padding: 18px;
      align-items: start;
    }
    .glass {
      border: 1px solid var(--line);
      background: var(--panel);
      backdrop-filter: blur(24px) saturate(140%);
      -webkit-backdrop-filter: blur(24px) saturate(140%);
      box-shadow: var(--shadow);
    }
    .sidebar {
      border-radius: 24px;
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      overflow: hidden;
      position: sticky;
      top: 18px;
      max-height: calc(100vh - 36px);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 14px;
      padding: 14px;
      border-radius: 22px;
      background:
        linear-gradient(135deg, rgba(238, 77, 49, 0.18), rgba(219, 35, 21, 0.06)),
        rgba(18, 2, 2, 0.92);
      border: 1px solid var(--line);
    }
    .brand-logo {
      width: 62px;
      height: 62px;
      object-fit: contain;
      filter: drop-shadow(0 10px 24px rgba(219, 35, 21, 0.25));
    }
    .brand-mark {
      width: 62px;
      height: 62px;
      border-radius: 18px;
      display: grid;
      place-items: center;
      background: linear-gradient(135deg, var(--accent) 0%, var(--accent-strong) 100%);
      color: white;
      font-weight: 800;
      font-size: 28px;
    }
    .brand-copy h1 { margin: 0; font-size: 22px; letter-spacing: 0.04em; }
    .brand-copy p { margin: 6px 0 0; color: var(--muted); font-size: 12px; line-height: 1.45; }
    .summary, .insights { display: grid; gap: 12px; }
    .summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .metric, .insight, .command-panel {
      padding: 14px;
      border-radius: 18px;
      background: var(--panel-strong);
    }
    .metric span, .insight span, .field label {
      display: block;
      color: var(--muted);
      font-size: 11px;
      font-family: "IBM Plex Mono", Consolas, monospace;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      margin-bottom: 8px;
    }
    .metric strong { font-size: 26px; line-height: 1; }
    .session-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
      min-height: 0;
      overflow: auto;
      padding-right: 4px;
    }
    .session {
      position: relative;
      padding: 14px;
      border-radius: 18px;
      border: 1px solid rgba(232,228,227,0.08);
      background: linear-gradient(180deg, rgba(232,68,44,0.08), rgba(255,255,255,0.02));
      cursor: pointer;
    }
    .session.active {
      border-color: var(--line-strong);
      background: linear-gradient(180deg, rgba(238,77,49,0.16), rgba(255,255,255,0.03));
      box-shadow: 0 18px 40px rgba(12, 0, 0, 0.28);
    }
    .session h3 { margin: 0 0 10px; font-size: 15px; line-height: 1.45; }
    .view-tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .view-tab {
      border: 1px solid rgba(232,228,227,0.08);
      background: rgba(232,228,227,0.06);
      color: var(--text);
      border-radius: 999px;
      padding: 10px 14px;
      cursor: pointer;
      font-size: 12px;
    }
    .view-tab.active {
      border-color: var(--line-strong);
      background: rgba(238,77,49,0.18);
      box-shadow: 0 10px 24px rgba(12, 0, 0, 0.22);
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.10em;
      color: var(--muted);
      margin-bottom: 10px;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--success);
      box-shadow: 0 0 0 6px rgba(125, 244, 189, 0.08);
    }
    .meta {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
      word-break: break-word;
    }
    .viewer {
      min-width: 0;
      display: grid;
      grid-template-columns: minmax(0, 1.45fr) minmax(320px, 0.95fr);
      gap: 18px;
      align-items: start;
    }
    .viewer > .hero {
      grid-column: 1 / -1;
    }
    .viewer > .insights {
      grid-column: 2;
      grid-row: 2;
      height: fit-content;
    }
    .viewer > .command-panel:first-of-type {
      grid-column: 2;
      grid-row: 3;
      height: fit-content;
    }
    .viewer > .stage {
      grid-column: 1;
      grid-row: 2 / span 3;
    }
    .viewer > .command-panel:last-of-type {
      grid-column: 2;
      grid-row: 4;
      height: fit-content;
    }
    .viewer > .committee-panel {
      grid-column: 1 / -1;
      grid-row: 5;
    }
    .hero {
      border-radius: 24px;
      padding: 18px 20px;
      background:
        radial-gradient(circle at top, rgba(238,77,49,0.12), transparent 18rem),
        linear-gradient(180deg, rgba(20, 2, 2, 0.96), rgba(24, 3, 3, 0.99));
    }
    .hero-top, .toolbar, .stage-header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
    }
    .hero h2 { margin: 0; font-size: 26px; }
    .hero p, .stage-header p, .command-panel p {
      margin: 8px 0 0;
      color: var(--muted);
      line-height: 1.55;
    }
    .hero-badge {
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid rgba(232,228,227,0.08);
      background: rgba(232,228,227,0.08);
      font-size: 12px;
      font-family: "IBM Plex Mono", Consolas, monospace;
      white-space: nowrap;
    }
    .workspace {
      display: grid;
      grid-template-columns: minmax(0, 1.45fr) minmax(320px, 0.95fr);
      gap: 18px;
      align-items: stretch;
    }
    .workspace-stage,
    .workspace-side {
      min-width: 0;
      display: grid;
      gap: 14px;
    }
    .workspace-side {
      align-content: start;
    }
    .insights { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .insight strong { font-size: 17px; line-height: 1.35; word-break: break-word; }
    .command-panel h3, .stage-header h3 { margin: 0; font-size: 18px; }
    .command-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 160px 140px auto;
      gap: 12px;
      align-items: end;
      margin-top: 12px;
    }
    .field { display: grid; gap: 8px; }
    .field input, .field select {
      width: 100%;
      border: 1px solid rgba(232,228,227,0.08);
      outline: none;
      border-radius: 14px;
      padding: 12px 14px;
      color: var(--text);
      background: rgba(16, 2, 2, 0.92);
    }
    .send-button {
      height: 48px;
      border: 0;
      border-radius: 14px;
      padding: 0 18px;
      color: white;
      font-weight: 700;
      cursor: pointer;
      background: linear-gradient(135deg, var(--accent) 0%, var(--accent-strong) 100%);
      box-shadow: 0 14px 30px rgba(12, 0, 0, 0.28);
    }
    .send-button:disabled { opacity: 0.5; cursor: not-allowed; box-shadow: none; }
    .command-status { min-height: 20px; color: var(--muted); font-size: 13px; margin-top: 12px; }
    .download-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto auto;
      gap: 12px;
      align-items: end;
      margin-top: 12px;
    }
    .download-button {
      height: 48px;
      border: 0;
      border-radius: 14px;
      padding: 0 18px;
      color: white;
      font-weight: 700;
      cursor: pointer;
      background: linear-gradient(135deg, var(--accent) 0%, var(--accent-hot) 100%);
      box-shadow: 0 14px 30px rgba(12, 0, 0, 0.26);
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      white-space: nowrap;
    }
    .download-status { min-height: 20px; color: var(--muted); font-size: 13px; margin-top: 12px; }
    .committee-config-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      align-items: end;
      margin-top: 12px;
    }
    .committee-run {
      min-width: 180px;
    }
    .committee-status {
      min-height: 20px;
      color: var(--muted);
      font-size: 13px;
      margin-top: 12px;
    }
    .committee-scene-report {
      margin-top: 12px;
      padding: 14px;
      border-radius: 16px;
      border: 1px solid rgba(232,228,227,0.08);
      background: rgba(16, 2, 2, 0.92);
      color: var(--muted);
      line-height: 1.6;
      max-height: 220px;
      overflow: auto;
      white-space: pre-wrap;
    }
    .committee-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 14px;
    }
    .committee-card {
      padding: 14px;
      border-radius: 18px;
      border: 1px solid rgba(232,228,227,0.08);
      background: linear-gradient(180deg, rgba(232,68,44,0.08), rgba(255,255,255,0.02));
      min-width: 0;
    }
    .committee-card h4 {
      margin: 0;
      font-size: 15px;
    }
    .committee-card .meta {
      margin-top: 6px;
    }
    .committee-output {
      margin-top: 12px;
      min-height: 160px;
      max-height: 360px;
      overflow: auto;
      padding: 12px;
      border-radius: 14px;
      background: rgba(16, 2, 2, 0.92);
      border: 1px solid rgba(232,228,227,0.08);
      white-space: pre-wrap;
      line-height: 1.6;
      color: var(--text);
      font-family: "IBM Plex Mono", Consolas, monospace;
      font-size: 12px;
    }
    .stage {
      border-radius: 24px;
      padding: 16px;
      min-height: 0;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .frame {
      flex: 1;
      min-height: 400px;
      border-radius: 20px;
      background: linear-gradient(180deg, rgba(232,68,44,0.08), rgba(255,255,255,0.02)), #080304;
      border: 1px solid rgba(232,228,227,0.08);
      overflow: auto;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .frame img { width: 100%; height: auto; display: block; border-radius: 18px; }
    .frame-empty {
      max-width: 580px;
      text-align: center;
      color: var(--muted);
      line-height: 1.7;
      padding: 32px;
    }
    .toolbar {
      padding-top: 2px;
    }
    .toolbar code {
      color: var(--text);
      background: rgba(232,228,227,0.08);
      border: 1px solid rgba(232,228,227,0.08);
      padding: 6px 10px;
      border-radius: 10px;
    }
    .live { color: var(--text); font-size: 13px; display: inline-flex; align-items: center; gap: 8px; }
    @media (max-width: 1200px) {
      .shell { grid-template-columns: 1fr; }
      .sidebar {
        position: static;
        max-height: none;
      }
      .viewer {
        grid-template-columns: 1fr;
      }
      .viewer > .hero,
      .viewer > .insights,
      .viewer > .stage,
      .viewer > .committee-panel,
      .viewer > .command-panel:first-of-type,
      .viewer > .command-panel:last-of-type {
        grid-column: auto;
        grid-row: auto;
      }
      .workspace {
        grid-template-columns: 1fr;
      }
      .summary, .insights { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .command-grid, .committee-config-grid { grid-template-columns: 1fr 1fr; }
      .committee-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 720px) {
      .shell { padding: 12px; }
      .summary, .insights, .command-grid, .download-grid, .committee-config-grid { grid-template-columns: 1fr; }
      .hero-top, .stage-header, .toolbar { flex-direction: column; align-items: start; }
      .frame { min-height: 280px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar glass">
      <div class="brand">
        ${logoTag}
        <div class="brand-copy">
          <h1>RED SEB Monitor</h1>
          <p>Painel de observação em tempo real para sessões do Safe Exam Browser com identidade visual da RED.</p>
          <p><strong>Build:</strong> ${buildLabel}</p>
        </div>
      </div>
      <div class="summary">
        <div class="metric">
          <span>Sessões Ativas</span>
          <strong id="metric-sessions">0</strong>
        </div>
        <div class="metric">
          <span>Frames Válidos</span>
          <strong id="metric-frames">0</strong>
        </div>
      </div>
      <div class="session-list" id="session-list"></div>
    </aside>
    <main class="viewer">
      <section class="hero glass">
        <div class="hero-top">
          <div>
            <h2>Observação sincronizada do SEB</h2>
            <p>Viewer em tema vermelho, pronto para acompanhar a tela do candidato em tempo real com atualização contínua do viewport e dos metadados da sessão.</p>
          </div>
          <div class="hero-badge" id="hero-last-update">${buildLabel}</div>
        </div>
      </section>
      <section class="insights">
        <div class="insight glass">
          <span>Título da Sessão</span>
          <strong id="viewer-title">Aguardando sessão</strong>
        </div>
        <div class="insight glass">
          <span>Endereço Atual</span>
          <strong id="viewer-url">Nenhum stream recebido ainda.</strong>
        </div>
        <div class="insight glass">
          <span>Viewport</span>
          <strong id="viewer-status">offline</strong>
        </div>
      </section>
      <section class="command-panel glass">
        <h3>Gerador de BAT</h3>
        <p>Cole só o <code>CMID</code> da prova ou, se preferir, o link <code>seb://</code>/<code>sebs://</code> completo. O painel monta o <code>.bat</code> pronto para abrir o RED SEB Portable da área de trabalho, dentro da pasta <code>REDSEBPortable</code>.</p>
        <div class="download-grid">
          <div class="field">
            <label for="bat-link">CMID ou link do SEB</label>
            <input id="bat-link" type="text" spellcheck="false" placeholder="Ex.: 764281">
          </div>
          <button class="download-button" id="download-bat-button" type="button">Baixar .bat</button>
          <a class="download-button" id="download-zip-button" href="/downloads/REDSEBPortable.zip">Baixar .zip</a>
        </div>
        <div class="download-status" id="download-status">Cole o CMID da prova ou o link completo do SEB para gerar o arquivo.</div>
      </section>
      <section class="stage glass">
        <div class="stage-header">
          <div>
            <h3>Viewport Remoto</h3>
            <p>Espelhamento visual por aba ou janela do SEB. Quando uma nova view é aberta, ela aparece abaixo em uma navegação parecida com abas.</p>
          </div>
        </div>
        <div class="view-tabs" id="view-tabs"></div>
        <div class="frame">
          <img id="viewer-image" alt="Viewport do SEB" hidden>
          <div id="empty-state" class="frame-empty">
            Assim que o Safe Exam Browser publicar frames em <code>/seb-live</code>, o dashboard exibirá a sessão aqui com visualização em tempo real.
          </div>
        </div>
        <div class="toolbar">
          <div class="live"><span class="dot"></span><strong>Live</strong><span id="connected-at">sem sessão ativa</span></div>
          <div><code>/seb-live</code> <code>/api/sessions</code> <code>/api/alert</code> <code>/downloads/REDSEBPortable.zip</code></div>
        </div>
      </section>
      <section class="command-panel glass">
        <h3>Alerta Remoto</h3>
        <p>Envie um popup temporário para a sessão selecionada. A mensagem aparece sobre o SEB na posição configurada pelo painel.</p>
        <div class="command-grid">
          <div class="field">
            <label for="alert-message">Mensagem</label>
            <input id="alert-message" type="text" maxlength="180" placeholder="Ex.: Aguarde a liberação do fiscal.">
          </div>
          <div class="field">
            <label for="alert-position">Posição</label>
            <select id="alert-position">
              <option value="top-right">Canto superior direito</option>
              <option value="top-left">Canto superior esquerdo</option>
              <option value="bottom-right">Canto inferior direito</option>
              <option value="bottom-left">Canto inferior esquerdo</option>
            </select>
          </div>
          <div class="field">
            <label for="alert-duration">Duração</label>
            <input id="alert-duration" type="number" min="250" max="10000" step="250" value="1000">
          </div>
          <button class="send-button" id="send-alert-button" type="button">Enviar</button>
        </div>
        <div class="command-status" id="command-status">Selecione uma sessão ativa para enviar um alerta.</div>
      </section>
      <section class="command-panel glass committee-panel">
        <h3>Comitê de IA</h3>
        <p>Dois revisores visuais e um relator principal analisam a frame atual da view selecionada usando o proxy da RED Systems.</p>
        <div class="committee-config-grid">
          <label class="field">
            <span>Visão A</span>
            <select id="committee-vision-primary"></select>
          </label>
          <label class="field">
            <span>Visão B</span>
            <select id="committee-vision-secondary"></select>
          </label>
          <label class="field">
            <span>Relator</span>
            <select id="committee-lead"></select>
          </label>
          <button class="send-button committee-run" id="committee-run-button" type="button">Analisar frame</button>
        </div>
        <div class="committee-status" id="committee-status">Selecione uma sessão com frame válido para iniciar a análise.</div>
        <div class="committee-scene-report" id="committee-scene-report">A leitura-base dos modelos de visão aparecerá aqui antes do comitê responder.</div>
        <div class="committee-grid">
          <article class="committee-card">
            <h4 id="committee-title-vision_primary">Visão A</h4>
            <div class="meta" id="committee-meta-vision_primary">Aguardando configuração.</div>
            <div class="committee-output" id="committee-output-vision_primary">Sem análise ainda.</div>
          </article>
          <article class="committee-card">
            <h4 id="committee-title-vision_secondary">Visão B</h4>
            <div class="meta" id="committee-meta-vision_secondary">Aguardando configuração.</div>
            <div class="committee-output" id="committee-output-vision_secondary">Sem análise ainda.</div>
          </article>
          <article class="committee-card">
            <h4 id="committee-title-lead">Relator principal</h4>
            <div class="meta" id="committee-meta-lead">Aguardando configuração.</div>
            <div class="committee-output" id="committee-output-lead">Sem análise ainda.</div>
          </article>
        </div>
      </section>
    </main>
  </div>
  <script>
    const sessionList = document.getElementById("session-list");
    const metricSessions = document.getElementById("metric-sessions");
    const metricFrames = document.getElementById("metric-frames");
    const viewerTitle = document.getElementById("viewer-title");
    const viewerUrl = document.getElementById("viewer-url");
    const viewerStatus = document.getElementById("viewer-status");
    const viewerImage = document.getElementById("viewer-image");
    const emptyState = document.getElementById("empty-state");
    const viewTabs = document.getElementById("view-tabs");
    const heroLastUpdate = document.getElementById("hero-last-update");
    const connectedAt = document.getElementById("connected-at");
    const alertMessage = document.getElementById("alert-message");
    const alertPosition = document.getElementById("alert-position");
    const alertDuration = document.getElementById("alert-duration");
    const sendAlertButton = document.getElementById("send-alert-button");
    const commandStatus = document.getElementById("command-status");
    const batLink = document.getElementById("bat-link");
    const downloadBatButton = document.getElementById("download-bat-button");
    const downloadStatus = document.getElementById("download-status");
    const committeeVisionPrimary = document.getElementById("committee-vision-primary");
    const committeeVisionSecondary = document.getElementById("committee-vision-secondary");
    const committeeLead = document.getElementById("committee-lead");
    const committeeRunButton = document.getElementById("committee-run-button");
    const committeeStatus = document.getElementById("committee-status");
    const committeeSceneReport = document.getElementById("committee-scene-report");
    const ALERT_POSITION_KEY = "redseb.monitor.alertPosition.v1";
    const COMMITTEE_MODELS_KEY = "redseb.committee.models.v1";
    let activeSessionId = null;
    let activeViewId = null;
    const knownViewIdsBySession = new Map();
    let committeeCatalog = null;
    let committeeBusy = false;

    function escapeHtml(value) {
      return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

    function formatDate(value) {
      if (!value) return "n/a";
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
    }

    function parseDownloadFilename(response, fallbackName) {
      const disposition = response.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="([^"]+)"/i);
      if (match && match[1]) {
        return match[1];
      }
      return fallbackName;
    }

    function hydrateAlertPreferences() {
      try {
        const savedPosition = window.localStorage.getItem(ALERT_POSITION_KEY) || "top-right";
        alertPosition.value = savedPosition;
      } catch {
        alertPosition.value = "top-right";
      }
    }

    function persistAlertPosition(value) {
      try {
        window.localStorage.setItem(ALERT_POSITION_KEY, String(value || "top-right"));
      } catch {
        // ignore
      }
    }

    function readCommitteePreferences() {
      try {
        const raw = window.localStorage.getItem(COMMITTEE_MODELS_KEY);
        return raw ? JSON.parse(raw) : {};
      } catch {
        return {};
      }
    }

    function persistCommitteePreferences() {
      try {
        window.localStorage.setItem(COMMITTEE_MODELS_KEY, JSON.stringify({
          visionPrimary: committeeVisionPrimary.value,
          visionSecondary: committeeVisionSecondary.value,
          lead: committeeLead.value
        }));
      } catch {
        // ignore
      }
    }

    function populateSelect(select, models, selectedId) {
      if (!select) return;
      select.innerHTML = (models || []).map((model) => {
        const selected = String(model.id || "") === String(selectedId || "") ? " selected" : "";
        const note = model.note ? " - " + model.note : "";
        return '<option value="' + escapeHtml(model.id) + '"' + selected + '>' + escapeHtml(model.id + note) + '</option>';
      }).join("");
    }

    function setCommitteeCardMeta(memberId, title, meta, text) {
      const titleNode = document.getElementById("committee-title-" + memberId);
      const metaNode = document.getElementById("committee-meta-" + memberId);
      const outputNode = document.getElementById("committee-output-" + memberId);
      if (titleNode) titleNode.textContent = title;
      if (metaNode) metaNode.textContent = meta;
      if (outputNode && text !== undefined) outputNode.textContent = text;
    }

    function resetCommitteeOutputs() {
      committeeSceneReport.textContent = "A leitura-base dos modelos de visão aparecerá aqui antes do comitê responder.";
      setCommitteeCardMeta("vision_primary", "Visão A", committeeVisionPrimary.value || "Modelo não definido.", "Sem análise ainda.");
      setCommitteeCardMeta("vision_secondary", "Visão B", committeeVisionSecondary.value || "Modelo não definido.", "Sem análise ainda.");
      setCommitteeCardMeta("lead", "Relator principal", committeeLead.value || "Modelo não definido.", "Sem análise ainda.");
    }

    async function loadCommitteeCatalog() {
      const response = await fetch("/api/committee/models", { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Falha ao carregar catálogo do comitê.");
      }

      committeeCatalog = payload;
      const preferences = readCommitteePreferences();
      const defaults = payload.defaults || {};
      populateSelect(committeeVisionPrimary, payload.visionModels || [], preferences.visionPrimary || defaults.visionPrimary || "");
      populateSelect(committeeVisionSecondary, payload.visionModels || [], preferences.visionSecondary || defaults.visionSecondary || "");
      populateSelect(committeeLead, payload.leadModels || [], preferences.lead || defaults.lead || "");
      persistCommitteePreferences();
      resetCommitteeOutputs();
    }

    function updateCommitteeBusy(busy) {
      committeeBusy = Boolean(busy);
      if (committeeRunButton) {
        committeeRunButton.disabled = committeeBusy;
        committeeRunButton.textContent = committeeBusy ? "Analisando..." : "Analisar frame";
      }
    }

    function appendCommitteeOutput(memberId, delta) {
      const outputNode = document.getElementById("committee-output-" + memberId);
      if (!outputNode) return;
      if (outputNode.textContent === "Sem análise ainda.") {
        outputNode.textContent = "";
      }
      outputNode.textContent += delta;
    }

    function getActiveView(session) {
      const views = Array.isArray(session && session.views) ? session.views : [];

      if (!views.length) {
        return null;
      }

      if (!activeViewId || !views.some((view) => view.viewId === activeViewId)) {
        activeViewId = views[0].viewId;
      }

      return views.find((view) => view.viewId === activeViewId) || views[0];
    }

    function syncKnownViews(sessions) {
      const liveSessionIds = new Set();

      for (const session of sessions) {
        const sessionId = String(session.sessionId || "");
        if (!sessionId) continue;
        liveSessionIds.add(sessionId);
        knownViewIdsBySession.set(
          sessionId,
          new Set((Array.isArray(session.views) ? session.views : []).map((view) => String(view.viewId || "")).filter(Boolean))
        );
      }

      for (const sessionId of Array.from(knownViewIdsBySession.keys())) {
        if (!liveSessionIds.has(sessionId)) {
          knownViewIdsBySession.delete(sessionId);
        }
      }
    }

    function renderSessions(sessions) {
      metricSessions.textContent = String(sessions.length);
      metricFrames.textContent = String(sessions.reduce((total, session) => total + (Array.isArray(session.views) ? session.views.filter((view) => view.imageBase64).length : 0), 0));
      heroLastUpdate.textContent = sessions[0] ? "Última atualização: " + formatDate(sessions[0].timestamp) : "Sem atualização";

      if (!sessions.length) {
        sessionList.innerHTML = '<div class="session"><div class="meta">Nenhuma sessão ativa no momento.</div></div>';
        activeSessionId = null;
        activeViewId = null;
        viewerTitle.textContent = "Aguardando sessão";
        viewerUrl.textContent = "Nenhum stream recebido ainda.";
        viewerStatus.textContent = "offline";
        connectedAt.textContent = "sem sessão ativa";
        commandStatus.textContent = "Selecione uma sessão ativa para enviar um alerta.";
        sendAlertButton.disabled = true;
        viewTabs.innerHTML = "";
        viewerImage.hidden = true;
        emptyState.hidden = false;
        return;
      }

      if (!activeSessionId || !sessions.some((session) => session.sessionId === activeSessionId)) {
        activeSessionId = sessions[0].sessionId;
      }

      sessionList.innerHTML = sessions.map((session) => {
        const active = session.sessionId === activeSessionId ? "active" : "";
        const views = Array.isArray(session.views) ? session.views : [];
        const state = views.some((view) => view.imageBase64) ? "com frame" : "aguardando frame";

        return '<div class="session ' + active + '" data-session-id="' + escapeHtml(session.sessionId) + '">' +
          '<div class="pill"><span class="dot"></span>' + escapeHtml(state) + '</div>' +
          '<h3>' + escapeHtml(session.title || "Sessão sem título") + '</h3>' +
          '<div class="meta">Sessão: ' + escapeHtml(session.sessionId) + '</div>' +
          '<div class="meta">Views abertas: ' + escapeHtml(String(views.length)) + '</div>' +
          '<div class="meta">Origem: ' + escapeHtml(session.remoteAddress || "n/a") + '</div>' +
          '<div class="meta">Atualizado: ' + escapeHtml(formatDate(session.timestamp)) + '</div>' +
          '</div>';
      }).join("");

      for (const item of document.querySelectorAll(".session[data-session-id]")) {
        item.addEventListener("click", () => {
          activeSessionId = item.getAttribute("data-session-id");
          activeViewId = null;
          renderSessions(sessions);
        });
      }

      const active = sessions.find((session) => session.sessionId === activeSessionId) || sessions[0];
      const views = Array.isArray(active.views) ? active.views : [];
      const previousViewIds = knownViewIdsBySession.get(String(active.sessionId || "")) || new Set();
      const addedView = views
        .filter((view) => {
          const viewId = String(view.viewId || "");
          return viewId && !previousViewIds.has(viewId);
        })
        .sort((left, right) => String(right.timestamp || "").localeCompare(String(left.timestamp || "")))[0] || null;

      if (addedView?.viewId) {
        activeViewId = addedView.viewId;
      }

      syncKnownViews(sessions);
      const activeView = getActiveView(active);

      viewTabs.innerHTML = views.map((view, index) => {
        const activeClass = view.viewId === activeViewId ? "active" : "";
        const label = view.isMainWindow ? "Principal" : ("Janela " + (index + 1));
        return '<button class="view-tab ' + activeClass + '" data-view-id="' + escapeHtml(view.viewId) + '" type="button">' + escapeHtml(label) + '</button>';
      }).join("");

      for (const item of document.querySelectorAll(".view-tab[data-view-id]")) {
        item.addEventListener("click", () => {
          activeViewId = item.getAttribute("data-view-id");
          renderSessions(sessions);
        });
      }

      viewerTitle.textContent = activeView && activeView.title ? activeView.title : "Sessão sem título";
      viewerUrl.textContent = activeView && activeView.url ? activeView.url : "URL indisponível";
      viewerStatus.textContent = activeView && activeView.width && activeView.height
        ? (activeView.width + " × " + activeView.height)
        : "online";
      connectedAt.textContent = "conectada em " + formatDate(active.connectedAt);
      commandStatus.textContent = active.lastAlert
        ? "Último alerta: " + active.lastAlert.message + " em " + formatDate(active.lastAlert.sentAt)
        : "Pronto para enviar um alerta à sessão selecionada.";
      sendAlertButton.disabled = false;

      if (activeView && activeView.imageBase64) {
        viewerImage.src = "data:image/jpeg;base64," + activeView.imageBase64;
        viewerImage.hidden = false;
        emptyState.hidden = true;
      } else {
        viewerImage.hidden = true;
        emptyState.hidden = false;
      }
    }

    async function sendAlert() {
      if (!activeSessionId) {
        commandStatus.textContent = "Nenhuma sessão selecionada.";
        return;
      }

      const message = alertMessage.value.trim();

      if (!message) {
        commandStatus.textContent = "Digite uma mensagem antes de enviar.";
        alertMessage.focus();
        return;
      }

      sendAlertButton.disabled = true;
      commandStatus.textContent = "Enviando alerta...";

      try {
        const response = await fetch("/api/alert", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            sessionId: activeSessionId,
            viewId: activeViewId,
            message,
            position: alertPosition.value,
            durationMs: Number(alertDuration.value || 1000)
          })
        });
        const payload = await response.json();

        if (!response.ok || !payload.ok) {
          throw new Error(payload.error || "Falha ao enviar alerta.");
        }

        commandStatus.textContent = "Alerta enviado com sucesso.";
        alertMessage.value = "";
        await refresh();
      } catch (error) {
        commandStatus.textContent = error.message;
      } finally {
        sendAlertButton.disabled = !activeSessionId;
      }
    }

    async function runCommitteeAnalysis() {
      if (!activeSessionId) {
        committeeStatus.textContent = "Selecione uma sessão ativa antes de analisar.";
        return;
      }

      if (!activeViewId) {
        committeeStatus.textContent = "Selecione uma view com frame válido antes de analisar.";
        return;
      }

      if (committeeBusy) {
        return;
      }

      updateCommitteeBusy(true);
      resetCommitteeOutputs();
      committeeStatus.textContent = "Preparando análise da frame atual...";

      try {
        persistCommitteePreferences();
        const response = await fetch("/api/committee/analyze", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            sessionId: activeSessionId,
            viewId: activeViewId,
            visionPrimaryModel: committeeVisionPrimary.value,
            visionSecondaryModel: committeeVisionSecondary.value,
            leadModel: committeeLead.value
          })
        });

        if (!response.ok || !response.body) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.error || "Falha ao iniciar o comitê de análise.");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
          let boundary = buffer.indexOf("\n");

          while (boundary !== -1) {
            const line = buffer.slice(0, boundary).trim();
            buffer = buffer.slice(boundary + 1);

            if (line) {
              let event;
              try {
                event = JSON.parse(line);
              } catch {
                event = null;
              }

              if (event) {
                if (event.type === "status") {
                  committeeStatus.textContent = event.message || "Analisando...";
                }

                if (event.type === "vision_begin") {
                  setCommitteeCardMeta(event.memberId, event.role || event.memberId, event.model || "modelo", "Lendo a frame...");
                }

                if (event.type === "vision_result") {
                  const prefix = event.error ? "[Falha] " : "";
                  setCommitteeCardMeta(event.memberId, event.role || event.memberId, event.model || "modelo", prefix + (event.text || "Sem leitura."));
                  const current = committeeSceneReport.textContent === "A leitura-base dos modelos de visão aparecerá aqui antes do comitê responder."
                    ? ""
                    : (committeeSceneReport.textContent + "\n\n");
                  committeeSceneReport.textContent = current + (event.role || event.memberId) + " (" + (event.model || "modelo") + "):\n" + (event.text || "Sem leitura.");
                }

                if (event.type === "member_begin") {
                  setCommitteeCardMeta(event.memberId, event.role || event.memberId, event.model || "modelo", "");
                }

                if (event.type === "member_delta") {
                  appendCommitteeOutput(event.memberId, event.delta || "");
                }

                if (event.type === "member_done") {
                  const outputNode = document.getElementById("committee-output-" + event.memberId);
                  if (outputNode && !outputNode.textContent.trim()) {
                    outputNode.textContent = event.text || "Sem resposta.";
                  }
                }

                if (event.type === "member_error") {
                  setCommitteeCardMeta(event.memberId, event.role || event.memberId, event.model || "modelo", "Erro: " + (event.error || "falha desconhecida"));
                }

                if (event.type === "done") {
                  committeeStatus.textContent = event.ok ? "Comitê concluído." : "Comitê concluído com avisos.";
                }
              }
            }

            boundary = buffer.indexOf("\n");
          }

          if (done) {
            break;
          }
        }
      } catch (error) {
        committeeStatus.textContent = error.message;
      } finally {
        updateCommitteeBusy(false);
      }
    }

    async function refresh() {
      try {
        const response = await fetch("/api/sessions", { cache: "no-store" });
        const sessions = await response.json();
        renderSessions(Array.isArray(sessions) ? sessions : []);
      } catch {
        heroLastUpdate.textContent = "Falha ao atualizar";
      }
    }

    async function downloadBat() {
      const sebLink = batLink.value.trim();

      if (!sebLink) {
        downloadStatus.textContent = "Cole o CMID da prova ou o link completo do SEB antes de gerar.";
        batLink.focus();
        return;
      }

      downloadBatButton.disabled = true;
      downloadStatus.textContent = "Gerando arquivo...";

      try {
        const response = await fetch("/api/generate-bat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sebLink })
        });

        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.error || "Falha ao gerar o arquivo.");
        }

        const blob = await response.blob();
        const downloadUrl = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = downloadUrl;
        const rawValue = String(batLink.value || "").trim();
        const cmidMatch = rawValue.match(/(?:^|[?&]cmid=)(\d+)/i) || rawValue.match(/^(\d+)$/);
        const fallbackName = cmidMatch && cmidMatch[1] ? "redseb-" + cmidMatch[1] + ".bat" : "redseb-link.bat";
        anchor.download = parseDownloadFilename(response, fallbackName);
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(downloadUrl);
        downloadStatus.textContent = "Arquivo gerado com sucesso.";
      } catch (error) {
        downloadStatus.textContent = error.message;
      } finally {
        downloadBatButton.disabled = false;
      }
    }

    refresh();
    hydrateAlertPreferences();
    loadCommitteeCatalog().catch((error) => {
      committeeStatus.textContent = error.message;
    });
    setInterval(refresh, 1000);
    sendAlertButton.addEventListener("click", sendAlert);
    alertPosition.addEventListener("change", () => persistAlertPosition(alertPosition.value));
    downloadBatButton.addEventListener("click", downloadBat);
    committeeRunButton.addEventListener("click", runCommitteeAnalysis);
    committeeVisionPrimary.addEventListener("change", () => {
      persistCommitteePreferences();
      resetCommitteeOutputs();
    });
    committeeVisionSecondary.addEventListener("change", () => {
      persistCommitteePreferences();
      resetCommitteeOutputs();
    });
    committeeLead.addEventListener("change", () => {
      persistCommitteePreferences();
      resetCommitteeOutputs();
    });
  </script>
</body>
</html>`;
}

function serveAsset(response, filePath) {
  const content = filePath ? readAsset(filePath) : null;

  if (!content) {
    response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Asset not found");
    return;
  }

  response.writeHead(200, { "Content-Type": contentTypeFor(filePath), "Cache-Control": "public, max-age=3600" });
  response.end(content);
}

const server = http.createServer((request, response) => {
  const pathname = new URL(request.url, `http://${request.headers.host || "localhost"}`).pathname;

  if (pathname === "/healthz") {
    return sendJson(response, 200, { ok: true, service: "seb-remote-view", timestamp: now(), assets: resolvedAssets });
  }

  if (pathname === "/api/sessions") {
    return sendJson(response, 200, getSessionState());
  }

  if (pathname === "/api/summary") {
    return sendJson(response, 200, getSummary());
  }

  if (pathname === "/api/committee/models") {
    return fetchCommitteeModelCatalog()
      .then((payload) => sendJson(response, 200, { ok: true, ...payload }))
      .catch((error) => sendJson(response, 500, { ok: false, error: error.message }));
  }

  if (pathname === "/api/committee/analyze" && request.method === "POST") {
    return readRequestBody(request)
      .then(async (body) => {
        let payload;

        try {
          payload = JSON.parse(body || "{}");
        } catch {
          return sendJson(response, 400, { ok: false, error: "Payload inválido." });
        }

        const sessionId = String(payload.sessionId || "");
        const viewId = String(payload.viewId || "");
        if (!sessionId) {
          return sendJson(response, 400, { ok: false, error: "Selecione uma sessão ativa antes de analisar." });
        }

        let target;
        try {
          target = resolveActiveSessionAndView(sessionId, viewId);
        } catch (error) {
          return sendJson(response, 409, { ok: false, error: error.message });
        }

        const catalog = await fetchCommitteeModelCatalog();
        const defaults = catalog.defaults || {};
        const visionPrimaryModel = String(payload.visionPrimaryModel || defaults.visionPrimary || "").trim();
        const visionSecondaryModel = String(payload.visionSecondaryModel || defaults.visionSecondary || "").trim();
        const leadModel = String(payload.leadModel || defaults.lead || "").trim();

        response.writeHead(200, {
          "Content-Type": "application/x-ndjson; charset=utf-8",
          "Cache-Control": "no-store, no-cache, must-revalidate",
          "Connection": "keep-alive",
          "X-Accel-Buffering": "no"
        });

        writeNdjsonEvent(response, {
          type: "status",
          stage: "capture",
          message: "Frame atual capturada. Iniciando leitura visual."
        });

        const visionMembers = [
          { id: "vision_primary", role: "Visão A", model: visionPrimaryModel },
          { id: "vision_secondary", role: "Visão B", model: visionSecondaryModel }
        ].filter((member) => member.model);

        const visionResults = {};
        visionMembers.forEach((member) => {
          writeNdjsonEvent(response, { type: "vision_begin", memberId: member.id, role: member.role, model: member.model });
        });
        await Promise.all(
          visionMembers.map(async (member) => {
            try {
              const text = await requestVisionExtraction(member.model, target.view.imageBase64);
              visionResults[member.id] = text;
              writeNdjsonEvent(response, { type: "vision_result", memberId: member.id, role: member.role, model: member.model, text });
            } catch (error) {
              const text = "Falha ao obter leitura visual: " + error.message;
              visionResults[member.id] = text;
              writeNdjsonEvent(response, { type: "vision_result", memberId: member.id, role: member.role, model: member.model, text, error: true });
            }
          })
        );

        const prompt = buildCommitteeBrief({
          session: target.session,
          view: target.view,
          visionPrimary: visionResults.vision_primary || "Sem relatório da visão A.",
          visionSecondary: visionResults.vision_secondary || "Sem relatório da visão B."
        });

        writeNdjsonEvent(response, {
          type: "status",
          stage: "committee",
          message: "Relatório visual consolidado. Iniciando respostas em paralelo."
        });

        const committeeMembers = [
          { id: "vision_primary", role: "Revisor visual A", model: visionPrimaryModel },
          { id: "vision_secondary", role: "Revisor visual B", model: visionSecondaryModel },
          { id: "lead", role: "Relator principal", model: leadModel }
        ].filter((member) => member.model);

        const results = await Promise.allSettled(
          committeeMembers.map((member) =>
            streamCommitteeMember(member, prompt, response).catch((error) => {
              writeNdjsonEvent(response, { type: "member_error", memberId: member.id, role: member.role, model: member.model, error: error.message });
            })
          )
        );

        writeNdjsonEvent(response, {
          type: "done",
          ok: results.every((item) => item.status === "fulfilled"),
          sessionId,
          viewId: target.view.viewId
        });
        response.end();
      })
      .catch((error) => sendJson(response, 500, { ok: false, error: error.message }));
  }

  if (pathname === "/api/alert" && request.method === "POST") {
    return readRequestBody(request)
      .then((body) => {
        let payload;

        try {
          payload = JSON.parse(body || "{}");
        } catch {
          return sendJson(response, 400, { ok: false, error: "Payload inválido." });
        }

        const sessionId = String(payload.sessionId || "");
        const message = String(payload.message || "").trim();
        const alert = {
          message,
          position: normalizePosition(payload.position),
          durationMs: normalizeDuration(payload.durationMs),
          viewId: String(payload.viewId || "").trim() || null,
          sentAt: now()
        };

        if (!sessionId || !sessions.has(sessionId)) {
          return sendJson(response, 404, { ok: false, error: "Sessão não encontrada." });
        }

        if (!message) {
          return sendJson(response, 400, { ok: false, error: "Mensagem obrigatória." });
        }

        if (!sendAlertToSession(sessionId, alert)) {
          return sendJson(response, 409, { ok: false, error: "Sessão sem canal ativo para receber alertas." });
        }

        const current = sessions.get(sessionId);
        sessions.set(sessionId, { ...current, lastAlert: alert });
        return sendJson(response, 200, { ok: true, sessionId, alert });
      })
      .catch((error) => sendJson(response, 500, { ok: false, error: error.message }));
  }

  if (pathname === "/api/debug/fake-frame" && request.method === "POST") {
    if (!authorizeDebugRequest(request)) {
      return sendJson(response, 403, { ok: false, error: "Debug frame nao autorizado." });
    }

    return readRequestBody(request)
      .then((body) => {
        let payload;

        try {
          payload = JSON.parse(body || "{}");
        } catch {
          return sendJson(response, 400, { ok: false, error: "Payload invalido." });
        }

        const normalized = normalizeDebugFramePayload(payload || {});
        const result = ingestSebPayload(normalized, request, null);
        return sendJson(response, 200, {
          ok: true,
          sessionId: result.sessionId,
          viewId: result.viewId,
          timestamp: normalized.timestamp
        });
      })
      .catch((error) => sendJson(response, 500, { ok: false, error: error.message }));
  }

  if (pathname === "/api/debug/session/clear" && request.method === "POST") {
    if (!authorizeDebugRequest(request)) {
      return sendJson(response, 403, { ok: false, error: "Debug frame nao autorizado." });
    }

    return readRequestBody(request)
      .then((body) => {
        let payload;

        try {
          payload = JSON.parse(body || "{}");
        } catch {
          return sendJson(response, 400, { ok: false, error: "Payload invalido." });
        }

        const sessionId = String(payload.sessionId || "").trim();
        if (!sessionId) {
          return sendJson(response, 400, { ok: false, error: "sessionId obrigatorio." });
        }

        const removed = sessions.delete(sessionId);
        return sendJson(response, 200, { ok: true, sessionId, removed });
      })
      .catch((error) => sendJson(response, 500, { ok: false, error: error.message }));
  }

  if (pathname === "/assets/logo") {
    return serveAsset(response, resolvedAssets.logo);
  }

  if (pathname === "/assets/favicon") {
    return serveAsset(response, resolvedAssets.favicon);
  }

  if (pathname === "/downloads/Setup.msi" || pathname === "/m") {
    return serveAsset(response, resolvedDownloads.setupMsi);
  }

  if (pathname === "/downloads/SetupBundle.exe" || pathname === "/b") {
    return serveAsset(response, resolvedDownloads.setupBundle);
  }

  if (pathname === "/downloads/REDSEBPortable.zip" || pathname === "/z") {
    return serveAsset(response, resolvedDownloads.portableZip);
  }

  if (pathname === "/downloads/upgrade-seb.ps1" || pathname === "/u") {
    return serveAsset(response, resolvedDownloads.upgradeScript);
  }

  if (pathname === "/api/generate-bat" && request.method === "POST") {
    return readRequestBody(request)
      .then((body) => {
        let payload;

        try {
          payload = JSON.parse(body || "{}");
        } catch {
          return sendJson(response, 400, { ok: false, error: "Payload invalido." });
        }

        const normalized = normalizeSebLink(payload.sebLink);

        if (!normalized.ok) {
          return sendJson(response, 400, { ok: false, error: normalized.error });
        }

        const content = buildPortableLauncherBat(normalized.link);
        const filename = downloadFilenameFromSeb(normalized);
        response.writeHead(200, {
          "Content-Type": "application/x-bat; charset=utf-8",
          "Content-Disposition": `attachment; filename="${filename}"`,
          "Cache-Control": "no-store"
        });
        response.end(content, "utf8");
      })
      .catch((error) => sendJson(response, 500, { ok: false, error: error.message }));
  }

  if (pathname === "/" || pathname === "/dashboard") {
    response.writeHead(200, {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store, no-cache, must-revalidate"
    });
    response.end(renderDashboard());
    return;
  }

  response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
  response.end("Not found");
});

const wss = new WebSocketServer({ server, path: "/seb-live" });

wss.on("connection", (socket, request) => {
  socket.on("message", (data, isBinary) => {
    if (isBinary) {
      return;
    }

    try {
      const payload = JSON.parse(data.toString("utf8"));
      ingestSebPayload(payload, request, socket);
    } catch (error) {
      console.error("Invalid SEB payload:", error.message);
    }
  });

  socket.on("close", () => {
    for (const [sessionId, session] of sessions.entries()) {
      if (session.socket === socket) {
        sessions.delete(sessionId);
      }
    }
  });
});

server.listen(port, host, () => {
  console.log(`seb-remote-view listening on http://${host}:${port}`);
  console.log(`resolved assets: ${JSON.stringify(resolvedAssets)}`);
  console.log(`resolved downloads: ${JSON.stringify(resolvedDownloads)}`);
});
