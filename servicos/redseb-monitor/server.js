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
const committeeDefaultVisionPrimary = process.env.RED_SEB_COMMITTEE_VISION_PRIMARY || "NIM - nvidia/nemotron-nano-12b-v2-vl";
const committeeDefaultVisionFallback = process.env.RED_SEB_COMMITTEE_VISION_FALLBACK || process.env.RED_SEB_COMMITTEE_VISION_SECONDARY || "NIM - meta/llama-3.2-90b-vision-instruct";
const committeeDefaultTextA = process.env.RED_SEB_COMMITTEE_TEXT_A || process.env.RED_SEB_COMMITTEE_LEAD || "NIM - qwen/qwen3-next-80b-a3b-instruct";
const committeeDefaultTextB = process.env.RED_SEB_COMMITTEE_TEXT_B || "NIM - meta/llama-4-maverick-17b-128e-instruct";
const committeeDefaultTextC = process.env.RED_SEB_COMMITTEE_TEXT_C || "gpt-oss:120b";
const sessionStaleMs = Math.max(1000, Number(process.env.RED_SEB_SESSION_STALE_MS || 5000));
const sessionWebhookUrl = String(process.env.SEB_SESSION_WEBHOOK_URL || "").trim();
const sessionWebhookEnabled = Boolean(sessionWebhookUrl);
const publicPanelUrl = String(process.env.RED_SEB_PUBLIC_URL || "http://redsystems.ddns.net:2580").trim();
const sessions = new Map();
const committeeRuns = new Map();
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

function buildPortableLauncherBat() {
  const panelUrl = publicPanelUrl.replace(/\/+$/, "");
  const zipUrl = `${panelUrl}/downloads/REDSEBPortable.zip`;
  const escapedPanelUrl = panelUrl.replace(/'/g, "''");
  const escapedZipUrl = zipUrl.replace(/'/g, "''");
  const escapedLaunchBase = defaultSebLaunchBase.replace(/'/g, "''");
  const powershellScript = [
    "$ErrorActionPreference='Stop'",
    "$ProgressPreference='SilentlyContinue'",
    "$p='" + escapedPanelUrl + "'",
    "$z='" + escapedZipUrl + "'",
    "$b='" + escapedLaunchBase + "'",
    "$d=[Environment]::GetFolderPath('MyDocuments')",
    "if([string]::IsNullOrWhiteSpace($d)){$d=Join-Path $env:USERPROFILE 'Documents'}",
    "$t=Join-Path $d 'REDSEBPortable'",
    "$w=Join-Path $env:TEMP ('redseb-work-'+[guid]::NewGuid().ToString('N'))",
    "$f=Join-Path $w 'REDSEBPortable.zip'",
    "$x=Join-Path $w 'extract'",
    "function C($m,$c='Gray'){Write-Host $m -ForegroundColor $c}",
    "function L(){Write-Host '============================================================' -ForegroundColor DarkRed}",
    "function P($label){Write-Host ($label+' [============================] 100%') -ForegroundColor DarkGray}",
    "try{",
    "if($Host.UI.RawUI){$Host.UI.RawUI.WindowTitle='RED Systems | RED SEB Universal'}",
    "Clear-Host",
    "L",
    "C '                           RED' 'Red'",
    "L",
    "C ''",
    "$r='';while(!$r){$r=(Read-Host 'ID ou link').Trim()}",
    "if($r -match '^[0-9]+$'){$l=$b+$r}elseif($r -match '^(?i)sebs?://'){$l=$r}else{throw 'Entrada invalida. Informe um CMID numerico ou um link seb:// ou sebs:// completo.'}",
    "C ''",
    "C 'Verificando dependencias...' 'DarkGray'",
    "$e=Get-ChildItem -LiteralPath $t -Filter 'SafeExamBrowser.exe' -Recurse -File -Force -ErrorAction SilentlyContinue|Select-Object -First 1 -ExpandProperty FullName",
    "if([string]::IsNullOrWhiteSpace($e)){",
    "New-Item -ItemType Directory -Path $w -Force|Out-Null",
    "Invoke-WebRequest -Uri $z -OutFile $f",
    "P 'Instalando dependencias'",
    "if(Test-Path $x){Remove-Item -LiteralPath $x -Recurse -Force}",
    "New-Item -ItemType Directory -Path $x -Force|Out-Null",
    "Expand-Archive -LiteralPath $f -DestinationPath $x -Force",
    "P 'Extraindo dependencias '",
    "$i=@(Get-ChildItem -LiteralPath $x)",
    "if($i.Count -eq 1 -and $i[0].PSIsContainer){$o=$i[0].FullName}else{$o=$x}",
    "if(Test-Path $t){& attrib -h $t | Out-Null;Remove-Item -LiteralPath $t -Recurse -Force}",
    "New-Item -ItemType Directory -Path $t -Force|Out-Null",
    "Copy-Item -Path (Join-Path $o '*') -Destination $t -Recurse -Force",
    "}",
    "& attrib +h $t | Out-Null",
    "$e=Get-ChildItem -LiteralPath $t -Filter 'SafeExamBrowser.exe' -Recurse -File -Force -ErrorAction SilentlyContinue|Select-Object -First 1 -ExpandProperty FullName",
    "if([string]::IsNullOrWhiteSpace($e)){throw 'SafeExamBrowser.exe nao foi encontrado depois da instalacao.'}",
    "C 'Tudo OK, iniciando RED.' 'Green'",
    "Start-Process -FilePath $e -ArgumentList $l|Out-Null",
    "Start-Sleep -Milliseconds 800",
    "if(Test-Path $w){Remove-Item -LiteralPath $w -Recurse -Force -ErrorAction SilentlyContinue}",
    "Start-Sleep -Milliseconds 700",
    "exit 0",
    "}catch{",
    "C ''",
    "C ('ERRO: '+$_.Exception.Message) 'Red'",
    "exit 1",
    "}"
  ].join(";");
  const encodedCommand = Buffer.from(powershellScript, "utf16le").toString("base64");

  return [
    "@echo off",
    "setlocal EnableExtensions",
    "title RED Systems - RED SEB Universal",
    "color 0C",
    ">nul 2>&1 chcp 65001",
    "cls",
    `powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -EncodedCommand ${encodedCommand}`,
    'set "REDSEB_EXIT=%ERRORLEVEL%"',
    'start "" /min cmd /c ping 127.0.0.1 -n 4 ^> nul ^& del /f /q "%~f0"',
    'if not "%REDSEB_EXIT%"=="0" (',
    "  echo.",
    "  echo Falha ao preparar o RED SEB Portable.",
    "  echo Verifique sua conexao e tente novamente.",
    "  pause",
    ")",
    "endlocal & exit /b %REDSEB_EXIT%",
    ""
  ].join("\r\n");
}

function downloadFilenameFromSeb(normalized) {
  return "redseb-universal.bat";
}

function getSessionState() {
  return Array.from(sessions.values())
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
        disconnectedAt: session.disconnectedAt || null,
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
  const lastUpdate = Array.from(sessions.values()).reduce((latest, session) => {
    const value = String(session.timestamp || "");
    if (!latest) {
      return value;
    }
    return value.localeCompare(latest) > 0 ? value : latest;
  }, "");

  return {
    activeSessions: items.length,
    sessionsWithFrames: withFrames,
    lastUpdate: lastUpdate || null
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

function orderedViewsForSession(session) {
  return Array.from((session?.views || new Map()).values())
    .sort((left, right) => {
      if (left.isMainWindow !== right.isMainWindow) {
        return left.isMainWindow ? -1 : 1;
      }

      if (left.windowId !== right.windowId) {
        return left.windowId - right.windowId;
      }

      return String(right.timestamp).localeCompare(String(left.timestamp));
    });
}

async function notifyNewSession(sessionId, session) {
  if (!sessionWebhookEnabled) {
    return;
  }

  const views = orderedViewsForSession(session);
  const primaryView = views[0] || {};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);

  try {
    const response = await fetch(sessionWebhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        type: "seb_session_new",
        sessionId,
        application: session.application || "SafeExamBrowser",
        connectedAt: session.connectedAt || now(),
        timestamp: session.timestamp || now(),
        remoteAddress: session.remoteAddress || "N/A",
        panelUrl: publicPanelUrl,
        viewsCount: views.length,
        primaryView: {
          viewId: primaryView.viewId || "",
          title: primaryView.title || "",
          url: primaryView.url || "",
          width: primaryView.width || 0,
          height: primaryView.height || 0,
          hasFrame: Boolean(primaryView.imageBase64)
        }
      }),
      signal: controller.signal
    });
    const responseText = await response.text();
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}${responseText ? `: ${responseText.slice(0, 240)}` : ""}`);
    }
    console.log("Webhook de nova sessao enviado:", sessionId);
  } catch (error) {
    console.error("Falha no webhook de nova sessao:", error.message);
  } finally {
    clearTimeout(timer);
  }
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
    disconnectedAt: null,
    timestamp: pick(payload, "timestamp", "Timestamp") || current.timestamp || now(),
    views
  };
}

function ingestSebPayload(payload, request, socket = null) {
  const sessionId = String(pick(payload, "sessionId", "SessionId") || `session-${Date.now()}`);
  const isNewSession = !sessions.has(sessionId);
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
  if (isNewSession && sessionWebhookEnabled) {
    notifyNewSession(sessionId, current).catch((error) => {
      console.error("Falha inesperada ao disparar webhook de nova sessao:", error.message);
    });
  }
  return { sessionId, viewId: view.viewId };
}

function markSocketClosed(socket) {
  for (const [sessionId, session] of sessions.entries()) {
    if (session.socket === socket) {
      sessions.set(sessionId, {
        ...session,
        socket: null,
        disconnectedAt: now()
      });
    }
  }
}

function pruneStaleSessions() {
  const cutoff = Date.now() - sessionStaleMs;
  for (const [sessionId, session] of sessions.entries()) {
    const lastTimestamp = Date.parse(String(session.timestamp || session.disconnectedAt || session.connectedAt || ""));
    if (Number.isFinite(lastTimestamp) && lastTimestamp < cutoff) {
      sessions.delete(sessionId);
    }
  }
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
        "NIM - meta/llama-3.2-90b-vision-instruct",
        "NIM - nvidia/nemotron-nano-12b-v2-vl",
        "NIM - meta/llama-3.2-11b-vision-instruct",
        "qwen3-vl:235b-instruct"
      ],
      committeeDefaultVisionPrimary
    ),
    visionFallback: pickFirst(
      [
        committeeDefaultVisionFallback,
        "NIM - meta/llama-3.2-90b-vision-instruct",
        "NIM - nvidia/nemotron-nano-12b-v2-vl",
        "qwen3-vl:235b-instruct"
      ],
      committeeDefaultVisionFallback
    ),
    textA: pickFirst(
      [
        committeeDefaultTextA,
        "NIM - qwen/qwen3-next-80b-a3b-instruct",
        "NIM - nvidia/llama-3.1-nemotron-nano-8b-v1",
        "NIM - abacusai/dracarys-llama-3.1-70b-instruct",
        "NIM - z-ai/glm5",
        "qwen3-next:80b"
      ],
      committeeDefaultTextA
    ),
    textB: pickFirst(
      [
        committeeDefaultTextB,
        "NIM - meta/llama-4-maverick-17b-128e-instruct",
        "NIM - abacusai/dracarys-llama-3.1-70b-instruct",
        "NIM - z-ai/glm5",
        "NIM - qwen/qwen3-next-80b-a3b-instruct",
        "NIM - nvidia/llama-3.1-nemotron-nano-8b-v1"
      ],
      committeeDefaultTextB
    ),
    textC: pickFirst(
      [
        committeeDefaultTextC,
        "gpt-oss:120b",
        "NIM - z-ai/glm5",
        "NIM - qwen/qwen3-next-80b-a3b-instruct",
        "NIM - abacusai/dracarys-llama-3.1-70b-instruct",
        "NIM - nvidia/llama-3.1-nemotron-nano-8b-v1"
      ],
      committeeDefaultTextC
    )
  };
}

async function fetchProxyJson(pathname, options = {}) {
  const controller = new AbortController();
  const timeoutMs = Number(options.timeoutMs || 120000);
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const externalSignal = options.signal;
  let removeExternalAbort = null;

  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort(externalSignal.reason);
    } else {
      const abortFromExternal = () => controller.abort(externalSignal.reason);
      externalSignal.addEventListener("abort", abortFromExternal, { once: true });
      removeExternalAbort = () => externalSignal.removeEventListener("abort", abortFromExternal);
    }
  }

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
    if (removeExternalAbort) {
      removeExternalAbort();
    }
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
    "Analise esta imagem com muito cuidado.",
    "Descreva exatamente o que esta visivel na imagem em portugues do Brasil.",
    "Extraia o texto legivel com o maximo de fidelidade possivel.",
    "Inclua: contexto geral, textos legiveis, objetos, elementos de interface, sinais importantes e qualquer detalhe relevante que realmente apareca na imagem.",
    "Se houver pergunta, enunciado, numeros, opcoes, formulas, login, aviso, animais, pessoas, objetos ou cenarios, deixe isso explicito.",
    "Organize em quatro blocos: CONTEXTO, TEXTO VISIVEL, DETALHES IMPORTANTES e INCERTEZAS.",
    "Nao invente nada. Se algo estiver incerto, diga claramente.",
    "Nao assuma que a imagem pertence a um exame, navegador, painel ou sistema especifico, a menos que isso esteja visivelmente presente na propria imagem."
  ].join(" ");
}

function committeeMemberSystemPrompt(roleLabel) {
  return [
    "Voce faz parte do comite de analise visual da RED Systems.",
    "Seu papel neste turno e: " + roleLabel + ".",
    "Receba o relatorio consolidado do modelo de visao, pense como operador tecnico e responda em portugues do Brasil.",
    "Seja objetivo, preciso e util. Nao invente elementos que nao estejam no relatorio.",
    "Ignore metadados tecnicos de transporte, nomes de sessao, titulos internos e URLs como prova do conteudo da imagem.",
    "Baseie sua analise somente no que foi realmente visto na frame.",
    "Quando houver pergunta de prova, exercicio ou conta, responda com a solucao e uma justificativa curta."
  ].join(" ");
}

function buildCommitteeBrief(context) {
  const parts = [
    "FRAME ATUAL",
    "Sessao: " + (context.session?.sessionId || "n/d"),
    "View: " + (context.view?.viewId || "n/d"),
    "Viewport: " + ((context.view?.width || 0) + "x" + (context.view?.height || 0)),
    "",
    "REGRA DE INTERPRETACAO",
    "Os metadados acima sao apenas tecnicos. Nao use sessao, titulo ou URL para deduzir o conteudo visual da frame.",
    "Use exclusivamente o relatorio visual abaixo como base para a resposta.",
    "",
    "RELATORIO VISUAL PRINCIPAL",
    context.visionReport || "Sem resposta.",
    "",
    "RELATORIO VISUAL DE APOIO",
    context.visionFallback || "Sem resposta.",
    "",
    "TAREFA",
    "Com base nesse material, diga o que a tela mostra, identifique com exatidao perguntas, contas ou instrucoes, e entregue a sua melhor analise."
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
    [defaults.visionPrimary, defaults.visionFallback, "NIM - nvidia/nemotron-nano-12b-v2-vl", "NIM - meta/llama-3.2-90b-vision-instruct", "qwen3-vl:235b-instruct"]
  );
  const textModels = prioritizeModels(
    models.filter((model) => model.capabilities.includes("chat") && !model.capabilities.includes("vision")),
    [defaults.textA, defaults.textB, defaults.textC, "NIM - qwen/qwen3-next-80b-a3b-instruct", "NIM - meta/llama-4-maverick-17b-128e-instruct", "gpt-oss:120b", "NIM - deepseek-ai/deepseek-v3.1", "qwen3-next:80b"]
  );
  return {
    visionModels,
    textModels,
    defaults
  };
}

function resolveActiveSessionAndView(sessionId, viewId) {
  const session = sessions.get(String(sessionId || ""));
  if (!session) {
    throw new Error("Sessao do SEB nao encontrada.");
  }

  const views = Array.from((session.views instanceof Map ? session.views.values() : [])).filter(Boolean);
  if (!views.length) {
    throw new Error("A sessao atual ainda nao publicou nenhuma view.");
  }

  const requestedView = views.find((item) => String(item.viewId || "") === String(viewId || ""));
  const fallbackView = views
    .slice()
    .sort((left, right) => Date.parse(String(right.timestamp || "")) - Date.parse(String(left.timestamp || "")))
    .find((item) => String(item.imageBase64 || "").trim());
  const view = (requestedView && String(requestedView.imageBase64 || "").trim() ? requestedView : null)
    || fallbackView
    || requestedView
    || views[0];
  if (!view?.imageBase64) {
    throw new Error("A view atual ainda nao possui frame valido para analise.");
  }

  return { session, view };
}

async function requestVisionExtraction(model, frameBase64, run) {
  const { controller, cleanup } = createCommitteeAbortController(run, 180000);

  try {
    ensureCommitteeRunActive(run);
    const payload = await fetchProxyJson("/v1/chat/completions", {
      signal: controller.signal,
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

    ensureCommitteeRunActive(run);
    return extractChatText(payload);
  } finally {
    cleanup();
  }
}

function shouldUseVisionFallback(text) {
  const normalized = String(text || "").trim();
  if (!normalized) {
    return true;
  }

  return normalized.length < 120;
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

function createCommitteeRun() {
  const runId = `committee-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const run = {
    runId,
    stopped: false,
    finalized: false,
    controllers: new Set()
  };
  committeeRuns.set(runId, run);
  return run;
}

function finalizeCommitteeRun(run) {
  if (!run || run.finalized) {
    return;
  }

  run.finalized = true;
  for (const controller of Array.from(run.controllers)) {
    run.controllers.delete(controller);
  }
  committeeRuns.delete(run.runId);
}

function stopCommitteeRun(runId) {
  const run = committeeRuns.get(String(runId || ""));
  if (!run) {
    return false;
  }

  run.stopped = true;
  for (const controller of Array.from(run.controllers)) {
    try {
      controller.abort(new Error("Analise interrompida pelo operador."));
    } catch {
      controller.abort();
    }
  }
  return true;
}

function registerCommitteeController(run, controller) {
  if (!run || !controller) {
    return () => {};
  }

  run.controllers.add(controller);
  return () => run.controllers.delete(controller);
}

function createCommitteeAbortController(run, timeoutMs) {
  const controller = new AbortController();
  const unregister = registerCommitteeController(run, controller);
  const timer = setTimeout(() => {
    try {
      controller.abort(new Error("Tempo limite da analise excedido."));
    } catch {
      controller.abort();
    }
  }, Number(timeoutMs || 180000));

  return {
    controller,
    cleanup() {
      clearTimeout(timer);
      unregister();
    }
  };
}

function isCommitteeAbortError(error, run) {
  if (run?.stopped) {
    return true;
  }

  const name = String(error?.name || "");
  if (name === "AbortError") {
    return true;
  }

  const message = String(error?.message || "").toLowerCase();
  return message.includes("interrompida pelo operador") || message.includes("aborted") || message.includes("abort");
}

function ensureCommitteeRunActive(run) {
  if (!run?.stopped) {
    return;
  }

  const error = new Error("Analise interrompida pelo operador.");
  error.code = "COMMITTEE_STOPPED";
  throw error;
}

function writeCommitteeRunEvent(response, run, payload) {
  writeNdjsonEvent(response, { ...payload, runId: run?.runId || null });
}

async function streamCommitteeMember(member, prompt, response, run) {
  const { controller, cleanup } = createCommitteeAbortController(run, 180000);
  let finalText = "";

  try {
    ensureCommitteeRunActive(run);
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

    writeCommitteeRunEvent(response, run, { type: "member_begin", memberId: member.id, role: member.role, model: member.model });
    const reader = upstream.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      ensureCommitteeRunActive(run);
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
              writeCommitteeRunEvent(response, run, { type: "member_delta", memberId: member.id, delta });
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

    ensureCommitteeRunActive(run);
    writeCommitteeRunEvent(response, run, { type: "member_done", memberId: member.id, text: finalText.trim() });
  } finally {
    cleanup();
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
      grid-template-rows: auto auto auto minmax(0, 1fr) auto auto;
      gap: 18px;
      align-items: start;
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
    .insights { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .insight strong { font-size: 17px; line-height: 1.35; word-break: break-word; }
    .command-panel h3, .stage-header h3 { margin: 0; font-size: 18px; }
    .stage-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: end;
      justify-content: flex-end;
    }
    .field-inline {
      min-width: 170px;
    }
    .field-inline label {
      margin-bottom: 6px;
    }
    .ghost-button {
      height: 44px;
      border: 1px solid rgba(232,228,227,0.08);
      border-radius: 14px;
      padding: 0 16px;
      color: var(--text);
      font-weight: 700;
      cursor: pointer;
      background: rgba(232,228,227,0.06);
      box-shadow: 0 10px 24px rgba(12, 0, 0, 0.18);
      white-space: nowrap;
    }
    .ghost-button:disabled {
      opacity: 0.45;
      cursor: not-allowed;
      box-shadow: none;
    }
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
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 12px;
      align-items: end;
      margin-top: 12px;
    }
    .committee-run {
      min-width: 180px;
    }
    .committee-run.is-stop {
      background: linear-gradient(135deg, #6b1510 0%, #94261a 100%);
      box-shadow: 0 14px 30px rgba(12, 0, 0, 0.18);
    }
    .committee-status {
      min-height: 20px;
      color: var(--muted);
      font-size: 13px;
      margin-top: 12px;
    }
    .committee-scene-layout {
      margin-top: 12px;
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(280px, 0.85fr);
      gap: 14px;
      align-items: start;
    }
    .committee-preview,
    .committee-scene-report {
      padding: 14px;
      border-radius: 16px;
      border: 1px solid rgba(232,228,227,0.08);
      background: rgba(16, 2, 2, 0.92);
    }
    .committee-preview {
      margin-top: 0;
    }
    .committee-preview h4,
    .committee-scene-report h4 {
      margin: 0 0 10px;
      font-size: 14px;
    }
    .committee-preview-frame {
      min-height: 220px;
      border-radius: 14px;
      border: 1px solid rgba(232,228,227,0.08);
      background: #080304;
      overflow: auto;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .committee-preview-frame img {
      width: 100%;
      height: auto;
      display: block;
    }
    .committee-preview-empty {
      padding: 24px;
      color: var(--muted);
      line-height: 1.6;
      text-align: center;
    }
    .committee-scene-report {
      margin-top: 0;
      max-height: 220px;
      overflow: auto;
      line-height: 1.6;
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
      word-break: break-word;
    }
    .committee-output {
      margin-top: 12px;
      min-height: 120px;
      max-height: 280px;
      overflow: auto;
      padding: 12px;
      border-radius: 14px;
      background: rgba(16, 2, 2, 0.92);
      border: 1px solid rgba(232,228,227,0.08);
      line-height: 1.6;
      color: var(--text);
      font-family: inherit;
      font-size: 14px;
      word-break: break-word;
      overflow-wrap: anywhere;
    }
    .markdown-content {
      display: grid;
      gap: 10px;
    }
    .markdown-content > :first-child {
      margin-top: 0;
    }
    .markdown-content > :last-child {
      margin-bottom: 0;
    }
    .markdown-content p,
    .markdown-content ul,
    .markdown-content ol,
    .markdown-content blockquote,
    .markdown-content pre,
    .markdown-content h1,
    .markdown-content h2,
    .markdown-content h3,
    .markdown-content h4 {
      margin: 0;
    }
    .markdown-content ul,
    .markdown-content ol {
      padding-left: 20px;
    }
    .markdown-content li + li {
      margin-top: 6px;
    }
    .markdown-content blockquote {
      border-left: 3px solid rgba(238,77,49,0.45);
      padding-left: 12px;
      color: rgba(232,228,227,0.86);
    }
    .markdown-content code {
      font-family: "IBM Plex Mono", Consolas, monospace;
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(232,228,227,0.08);
      border-radius: 8px;
      padding: 1px 6px;
      font-size: 0.95em;
    }
    .markdown-content pre {
      overflow: auto;
      padding: 12px;
      border-radius: 12px;
      background: rgba(8, 3, 4, 0.95);
      border: 1px solid rgba(232,228,227,0.08);
    }
    .markdown-content pre code {
      background: transparent;
      border: 0;
      padding: 0;
      border-radius: 0;
      display: block;
      white-space: pre-wrap;
    }
    .markdown-content a {
      color: #ff8c74;
      text-decoration: none;
    }
    .markdown-content a:hover {
      text-decoration: underline;
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
    .frame[data-size-mode="auto"] img {
      width: 100%;
      max-width: 100%;
      height: auto;
      display: block;
      border-radius: 18px;
    }
    .frame[data-size-mode="manual"] img {
      width: var(--frame-manual-width, 100%);
      max-width: none;
      height: auto;
      display: block;
      border-radius: 18px;
    }
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
    .toolbar-left {
      display: grid;
      gap: 6px;
      align-items: start;
    }
    .toolbar code {
      color: var(--text);
      background: rgba(232,228,227,0.08);
      border: 1px solid rgba(232,228,227,0.08);
      padding: 6px 10px;
      border-radius: 10px;
    }
    .live { color: var(--text); font-size: 13px; display: inline-flex; align-items: center; gap: 8px; }
    .frame-copy-status {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }
    @media (max-width: 1200px) {
      .shell { grid-template-columns: 1fr; }
      .sidebar {
        position: static;
        max-height: none;
      }
      .summary, .insights { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .command-grid, .committee-config-grid { grid-template-columns: 1fr 1fr; }
      .committee-grid { grid-template-columns: 1fr; }
      .committee-scene-layout { grid-template-columns: 1fr; }
    }
    @media (max-width: 720px) {
      .shell { padding: 12px; }
      .summary, .insights, .command-grid, .download-grid, .committee-config-grid { grid-template-columns: 1fr; }
      .hero-top, .stage-header, .toolbar { flex-direction: column; align-items: start; }
      .stage-actions {
        width: 100%;
        justify-content: stretch;
      }
      .field-inline,
      .ghost-button {
        width: 100%;
      }
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
        <h3>Launcher Universal</h3>
        <p>Baixe um único <code>.bat</code> da RED Systems. Quando ele rodar, pergunta o <code>CMID</code> ou o link completo do exame, instala o RED SEB Portable em <code>Documentos\\REDSEBPortable</code> se faltar, abre a prova e se remove sozinho no fim. Tudo em modo usuário, sem pedir administrador.</p>
        <div class="download-grid">
          <button class="download-button" id="download-bat-button" type="button">Baixar launcher .bat</button>
          <a class="download-button" id="download-zip-button" href="/downloads/REDSEBPortable.zip">Baixar .zip</a>
        </div>
        <div class="download-status" id="download-status">O launcher usa a pasta Documentos\\REDSEBPortable e roda sem precisar de admin.</div>
      </section>
      <section class="stage glass">
        <div class="stage-header">
          <div>
            <h3>Viewport Remoto</h3>
            <p>Espelhamento visual por aba ou janela do SEB. Quando uma nova view é aberta, ela aparece abaixo em uma navegação parecida com abas.</p>
          </div>
          <div class="stage-actions">
            <label class="field field-inline">
              <span>Tamanho da frame</span>
              <select id="viewer-frame-size">
                <option value="auto">Automático</option>
                <option value="70">70%</option>
                <option value="85">85%</option>
                <option value="100">100%</option>
                <option value="120">120%</option>
                <option value="140">140%</option>
              </select>
            </label>
            <button class="ghost-button" id="copy-frame-button" type="button" disabled>Copiar frame</button>
          </div>
        </div>
        <div class="view-tabs" id="view-tabs"></div>
        <div class="frame" id="viewer-frame-shell" data-size-mode="auto">
          <img id="viewer-image" alt="Viewport do SEB" hidden>
          <div id="empty-state" class="frame-empty">
            Assim que o Safe Exam Browser publicar frames em <code>/seb-live</code>, o dashboard exibirá a sessão aqui com visualização em tempo real.
          </div>
        </div>
        <div class="toolbar">
          <div class="toolbar-left">
            <div class="live"><span class="dot"></span><strong>Live</strong><span id="connected-at">sem sessão ativa</span></div>
            <div class="frame-copy-status" id="frame-copy-status">Nenhuma frame pronta para copiar.</div>
          </div>
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
        <p>Um modelo de visão lê a frame atual, aciona fallback visual se precisar, e três analistas de texto respondem em paralelo usando o proxy da RED Systems.</p>
        <div class="committee-config-grid">
          <label class="field">
            <span>Visão principal</span>
            <select id="committee-vision-primary"></select>
          </label>
          <label class="field">
            <span>Fallback visual</span>
            <select id="committee-vision-fallback"></select>
          </label>
          <label class="field">
            <span>Analista A</span>
            <select id="committee-text-a"></select>
          </label>
          <label class="field">
            <span>Analista B</span>
            <select id="committee-text-b"></select>
          </label>
          <label class="field">
            <span>Analista C</span>
            <select id="committee-text-c"></select>
          </label>
          <button class="send-button committee-run" id="committee-run-button" type="button">Analisar frame</button>
        </div>
        <div class="committee-status" id="committee-status">Selecione uma sessão com frame válido para iniciar a análise.</div>
        <div class="committee-scene-layout">
          <div class="committee-preview">
            <h4>Frame enviada ao comitê</h4>
            <div class="committee-preview-frame">
              <img id="committee-frame-image" alt="Frame enviada ao comitê" hidden>
              <div class="committee-preview-empty" id="committee-frame-empty">A frame exata enviada para a análise aparecerá aqui.</div>
            </div>
          </div>
          <div class="committee-scene-report">
            <h4>Leitura visual consolidada</h4>
            <div id="committee-scene-report">O relatório visual consolidado aparecerá aqui antes do trio textual responder.</div>
          </div>
        </div>
        <div class="committee-grid">
          <article class="committee-card">
            <h4 id="committee-title-text_a">Analista A</h4>
            <div class="meta" id="committee-meta-text_a">Aguardando configuração.</div>
            <div class="committee-output" id="committee-output-text_a">Sem análise ainda.</div>
          </article>
          <article class="committee-card">
            <h4 id="committee-title-text_b">Analista B</h4>
            <div class="meta" id="committee-meta-text_b">Aguardando configuração.</div>
            <div class="committee-output" id="committee-output-text_b">Sem análise ainda.</div>
          </article>
          <article class="committee-card">
            <h4 id="committee-title-text_c">Analista C</h4>
            <div class="meta" id="committee-meta-text_c">Aguardando configuração.</div>
            <div class="committee-output" id="committee-output-text_c">Sem análise ainda.</div>
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
    const viewerFrameShell = document.getElementById("viewer-frame-shell");
    const viewerImage = document.getElementById("viewer-image");
    const emptyState = document.getElementById("empty-state");
    const viewerFrameSize = document.getElementById("viewer-frame-size");
    const copyFrameButton = document.getElementById("copy-frame-button");
    const frameCopyStatus = document.getElementById("frame-copy-status");
    const viewTabs = document.getElementById("view-tabs");
    const heroLastUpdate = document.getElementById("hero-last-update");
    const connectedAt = document.getElementById("connected-at");
    const alertMessage = document.getElementById("alert-message");
    const alertPosition = document.getElementById("alert-position");
    const alertDuration = document.getElementById("alert-duration");
    const sendAlertButton = document.getElementById("send-alert-button");
    const commandStatus = document.getElementById("command-status");
    const downloadBatButton = document.getElementById("download-bat-button");
    const downloadStatus = document.getElementById("download-status");
    const committeeVisionPrimary = document.getElementById("committee-vision-primary");
    const committeeVisionFallback = document.getElementById("committee-vision-fallback");
    const committeeTextA = document.getElementById("committee-text-a");
    const committeeTextB = document.getElementById("committee-text-b");
    const committeeTextC = document.getElementById("committee-text-c");
    const committeeRunButton = document.getElementById("committee-run-button");
    const committeeStatus = document.getElementById("committee-status");
    const committeeSceneReport = document.getElementById("committee-scene-report");
    const committeeFrameImage = document.getElementById("committee-frame-image");
    const committeeFrameEmpty = document.getElementById("committee-frame-empty");
    const ALERT_POSITION_KEY = "redseb.monitor.alertPosition.v1";
    const FRAME_SIZE_KEY = "redseb.monitor.frameSize.v1";
    const COMMITTEE_MODELS_KEY = "redseb.committee.models.v3";
    let activeSessionId = null;
    let activeViewId = null;
    const knownViewIdsBySession = new Map();
    let committeeCatalog = null;
    let committeeBusy = false;
    let committeeActiveRunId = null;
    let committeeAbortController = null;
    let committeeRequestSerial = 0;
    let frameRenderToken = 0;

    function escapeHtml(value) {
      return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

    function renderInlineMarkdown(text) {
      const tick = String.fromCharCode(96);
      let html = escapeHtml(text || "");
      html = html.replace(new RegExp("\\\\[([^\\\\]]+)\\\\]\\\\((https?:\\\\/\\\\/[^\\\\s)]+)\\\\)", "g"), (_match, label, url) => {
        const safeUrl = escapeHtml(url);
        return '<a href="' + safeUrl + '" target="_blank" rel="noopener noreferrer">' + label + "</a>";
      });
      html = html.replace(new RegExp(tick + "([^" + tick + "]+)" + tick, "g"), "<code>$1</code>");
      html = html.replace(new RegExp("\\\\\\*\\\\\\*([^*]+)\\\\\\*\\\\\\*", "g"), "<strong>$1</strong>");
      html = html.replace(new RegExp("__([^_]+)__", "g"), "<strong>$1</strong>");
      html = html.replace(new RegExp("(^|[\\\\s(])\\\\*([^*]+)\\\\*(?=[\\\\s).,!?:;]|$)", "g"), "$1<em>$2</em>");
      html = html.replace(new RegExp("(^|[\\\\s(])_([^_]+)_(?=[\\\\s).,!?:;]|$)", "g"), "$1<em>$2</em>");
      return html;
    }

    function renderMarkdownHtml(source) {
      const tick = String.fromCharCode(96);
      const fence = tick + tick + tick;
      const text = String(source || "").replace(new RegExp("\\\\r\\\\n", "g"), "\\n");
      if (!text.trim()) {
        return "<p></p>";
      }

      const codeBlocks = [];
      const withPlaceholders = text.replace(new RegExp(fence + "([\\\\w-]*)\\n([\\\\s\\\\S]*?)" + fence, "g"), (_match, language, code) => {
        const token = "@@CODEBLOCK_" + codeBlocks.length + "@@";
        const langClass = language ? ' class="language-' + escapeHtml(language) + '"' : "";
        codeBlocks.push("<pre><code" + langClass + ">" + escapeHtml(code.replace(new RegExp("\\\\n$", "g"), "")) + "</code></pre>");
        return token;
      });

      const blocks = withPlaceholders.split(new RegExp("\\\\n\\\\s*\\\\n")).map((block) => block.trim()).filter(Boolean);
      const htmlBlocks = blocks.map((block) => {
        if (new RegExp("^@@CODEBLOCK_\\\\d+@@$").test(block)) {
          return block;
        }

        const lines = block.split("\\n").map((line) => line.trimRight());
        if (!lines.length) {
          return "";
        }

        if (new RegExp("^#{1,4}\\\\s+").test(lines[0])) {
          const level = Math.min(4, lines[0].match(new RegExp("^#+"))[0].length);
          return "<h" + level + ">" + renderInlineMarkdown(lines[0].replace(new RegExp("^#{1,4}\\\\s+"), "")) + "</h" + level + ">";
        }

        if (lines.every((line) => new RegExp("^>\\\\s?").test(line))) {
          return "<blockquote>" + lines.map((line) => renderInlineMarkdown(line.replace(new RegExp("^>\\\\s?"), ""))).join("<br>") + "</blockquote>";
        }

        if (lines.every((line) => new RegExp("^[-*+]\\\\s+").test(line))) {
          return "<ul>" + lines.map((line) => "<li>" + renderInlineMarkdown(line.replace(new RegExp("^[-*+]\\\\s+"), "")) + "</li>").join("") + "</ul>";
        }

        if (lines.every((line) => new RegExp("^\\\\d+\\\\.\\\\s+").test(line))) {
          return "<ol>" + lines.map((line) => "<li>" + renderInlineMarkdown(line.replace(new RegExp("^\\\\d+\\\\.\\\\s+"), "")) + "</li>").join("") + "</ol>";
        }

        return "<p>" + lines.map((line) => renderInlineMarkdown(line)).join("<br>") + "</p>";
      });

      let html = htmlBlocks.join("");
      html = html.replace(new RegExp("@@CODEBLOCK_(\\\\d+)@@", "g"), (_match, index) => codeBlocks[Number(index)] || "");
      return html;
    }

    function setMarkdownContent(node, source) {
      if (!node) return;
      const text = String(source || "");
      node.dataset.markdownSource = text;
      node.innerHTML = '<div class="markdown-content">' + renderMarkdownHtml(text) + "</div>";
    }

    function formatDate(value) {
      if (!value) return "n/a";
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
    }

    function inferImageMimeType(base64) {
      const sample = String(base64 || "").slice(0, 16);
      if (sample.startsWith("/9j/")) return "image/jpeg";
      if (sample.startsWith("iVBOR")) return "image/png";
      if (sample.startsWith("UklGR")) return "image/webp";
      if (sample.startsWith("R0lGOD")) return "image/gif";
      return "image/jpeg";
    }

    function buildImageDataUrl(base64, mimeType) {
      return "data:" + mimeType + ";base64," + base64;
    }

    function normalizeFrameSize(value) {
      const normalized = String(value || "auto").trim().toLowerCase();
      return ["auto", "70", "85", "100", "120", "140"].includes(normalized) ? normalized : "auto";
    }

    function updateCopyFrameAvailability(message) {
      const hasFrame = Boolean(viewerImage && !viewerImage.hidden && viewerImage.getAttribute("src"));
      if (copyFrameButton) {
        copyFrameButton.disabled = !hasFrame;
      }
      if (frameCopyStatus && message !== undefined) {
        frameCopyStatus.textContent = message;
      }
    }

    function applyFrameSize(value) {
      const normalized = normalizeFrameSize(value);
      if (viewerFrameSize) {
        viewerFrameSize.value = normalized;
      }
      if (viewerFrameShell) {
        if (normalized === "auto") {
          viewerFrameShell.dataset.sizeMode = "auto";
          viewerFrameShell.style.removeProperty("--frame-manual-width");
        } else {
          viewerFrameShell.dataset.sizeMode = "manual";
          viewerFrameShell.style.setProperty("--frame-manual-width", normalized + "%");
        }
      }
    }

    function hydrateFrameSizePreference() {
      try {
        applyFrameSize(window.localStorage.getItem(FRAME_SIZE_KEY) || "auto");
      } catch {
        applyFrameSize("auto");
      }
    }

    function persistFrameSize(value) {
      const normalized = normalizeFrameSize(value);
      applyFrameSize(normalized);
      try {
        window.localStorage.setItem(FRAME_SIZE_KEY, normalized);
      } catch {
        // ignore
      }
    }

    function renderViewerFrame(base64) {
      const value = String(base64 || "").trim();
      if (!value) {
        viewerImage.hidden = true;
        viewerImage.removeAttribute("src");
        emptyState.hidden = false;
        updateCopyFrameAvailability("Nenhuma frame pronta para copiar.");
        return;
      }

      const orderedMimes = [...new Set([
        inferImageMimeType(value),
        "image/jpeg",
        "image/png",
        "image/webp"
      ])];
      const token = ++frameRenderToken;
      let attempt = 0;

      const tryLoad = () => {
        const mime = orderedMimes[attempt] || "image/jpeg";
        viewerImage.onload = () => {
          if (token !== frameRenderToken) return;
          viewerImage.hidden = false;
          emptyState.hidden = true;
          updateCopyFrameAvailability("Frame pronta para copiar.");
        };
        viewerImage.onerror = () => {
          if (token !== frameRenderToken) return;
          attempt += 1;
          if (attempt < orderedMimes.length) {
            tryLoad();
            return;
          }
          viewerImage.hidden = true;
          viewerImage.removeAttribute("src");
          emptyState.hidden = false;
          emptyState.textContent = "A frame chegou, mas o navegador nao conseguiu renderizar a imagem desta view.";
          updateCopyFrameAvailability("A frame atual nao pode ser copiada.");
        };
        viewerImage.src = buildImageDataUrl(value, mime);
      };

      viewerImage.hidden = true;
      emptyState.hidden = false;
      emptyState.textContent = "Carregando frame da view selecionada...";
      updateCopyFrameAvailability("Preparando frame para copia...");
      tryLoad();
    }

    async function copyCurrentFrame() {
      const src = viewerImage && viewerImage.getAttribute("src");
      if (!src || viewerImage.hidden) {
        updateCopyFrameAvailability("Nenhuma frame pronta para copiar.");
        return;
      }

      if (!navigator.clipboard || typeof navigator.clipboard.write !== "function" || typeof window.ClipboardItem === "undefined") {
        updateCopyFrameAvailability("Este navegador nao suporta copiar imagem direto.");
        return;
      }

      copyFrameButton.disabled = true;
      frameCopyStatus.textContent = "Copiando frame...";

      try {
        const response = await fetch(src);
        const blob = await response.blob();
        const mimeType = blob.type || "image/png";
        await navigator.clipboard.write([
          new window.ClipboardItem({ [mimeType]: blob })
        ]);
        frameCopyStatus.textContent = "Frame copiada para a area de transferencia.";
      } catch {
        frameCopyStatus.textContent = "Nao foi possivel copiar a frame atual.";
      } finally {
        updateCopyFrameAvailability();
      }
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
          visionFallback: committeeVisionFallback.value,
          textA: committeeTextA.value,
          textB: committeeTextB.value,
          textC: committeeTextC.value
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
      if (outputNode && text !== undefined) setMarkdownContent(outputNode, text);
    }

    function resetCommitteeOutputs() {
      setMarkdownContent(committeeSceneReport, "O relatório visual consolidado aparecerá aqui antes do trio textual responder.");
      setCommitteeCardMeta("text_a", "Analista A", committeeTextA.value || "Modelo não definido.", "Sem análise ainda.");
      setCommitteeCardMeta("text_b", "Analista B", committeeTextB.value || "Modelo não definido.", "Sem análise ainda.");
      setCommitteeCardMeta("text_c", "Analista C", committeeTextC.value || "Modelo não definido.", "Sem análise ainda.");
      committeeFrameImage.hidden = true;
      committeeFrameImage.removeAttribute("src");
      committeeFrameEmpty.hidden = false;
      committeeFrameEmpty.textContent = "A frame exata enviada para a análise aparecerá aqui.";
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
      populateSelect(committeeVisionFallback, payload.visionModels || [], preferences.visionFallback || defaults.visionFallback || "");
      populateSelect(committeeTextA, payload.textModels || [], preferences.textA || defaults.textA || "");
      populateSelect(committeeTextB, payload.textModels || [], preferences.textB || defaults.textB || "");
      populateSelect(committeeTextC, payload.textModels || [], preferences.textC || defaults.textC || "");
      persistCommitteePreferences();
      resetCommitteeOutputs();
    }

    function updateCommitteeBusy(busy) {
      committeeBusy = Boolean(busy);
      if (committeeRunButton) {
        committeeRunButton.disabled = false;
        committeeRunButton.textContent = committeeBusy ? "Parar" : "Analisar frame";
        committeeRunButton.classList.toggle("is-stop", committeeBusy);
      }
      [committeeVisionPrimary, committeeVisionFallback, committeeTextA, committeeTextB, committeeTextC].forEach((node) => {
        if (node) {
          node.disabled = committeeBusy;
        }
      });
    }

    function appendCommitteeOutput(memberId, delta) {
      const outputNode = document.getElementById("committee-output-" + memberId);
      if (!outputNode) return;
      const current = outputNode.dataset.markdownSource || "";
      const next = (current === "Sem análise ainda." ? "" : current) + String(delta || "");
      setMarkdownContent(outputNode, next);
    }

    function renderCommitteeSnapshot(base64) {
      if (!base64) {
        committeeFrameImage.hidden = true;
        committeeFrameImage.removeAttribute("src");
        committeeFrameEmpty.hidden = false;
        committeeFrameEmpty.textContent = "A frame exata enviada para a análise aparecerá aqui.";
        return;
      }

      committeeFrameEmpty.hidden = true;
      committeeFrameImage.hidden = false;
      committeeFrameImage.src = buildImageDataUrl(base64, inferImageMimeType(base64));
    }

    async function stopCommitteeAnalysis() {
      if (!committeeBusy) {
        return;
      }

      committeeRequestSerial += 1;
      const runId = committeeActiveRunId;
      const controller = committeeAbortController;
      committeeActiveRunId = null;
      committeeAbortController = null;
      committeeStatus.textContent = "Interrompendo análise atual...";
      updateCommitteeBusy(false);

      if (controller) {
        controller.abort();
      }

      if (runId) {
        await fetch("/api/committee/stop", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ runId })
        }).catch(() => {});
      }

      committeeStatus.textContent = "Análise interrompida.";
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
        viewerImage.removeAttribute("src");
        emptyState.hidden = false;
        updateCopyFrameAvailability("Nenhuma frame pronta para copiar.");
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
        renderViewerFrame(activeView.imageBase64);
      } else {
        viewerImage.hidden = true;
        viewerImage.removeAttribute("src");
        emptyState.hidden = false;
        emptyState.textContent = "Assim que o Safe Exam Browser publicar frames em /seb-live, o dashboard exibira a sessao aqui com visualizacao em tempo real.";
        updateCopyFrameAvailability("Nenhuma frame pronta para copiar.");
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
      if (committeeBusy) {
        await stopCommitteeAnalysis();
        return;
      }

      if (!activeSessionId) {
        committeeStatus.textContent = "Selecione uma sessão ativa antes de analisar.";
        return;
      }

      if (!activeViewId) {
        committeeStatus.textContent = "Selecione uma view com frame válido antes de analisar.";
        return;
      }

      updateCommitteeBusy(true);
      resetCommitteeOutputs();
      committeeStatus.textContent = "Preparando análise da frame atual...";
      const requestSerial = ++committeeRequestSerial;

      try {
        persistCommitteePreferences();
        committeeAbortController = new AbortController();
        const response = await fetch("/api/committee/analyze", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: committeeAbortController.signal,
          body: JSON.stringify({
            sessionId: activeSessionId,
            viewId: activeViewId,
            visionPrimaryModel: committeeVisionPrimary.value,
            visionFallbackModel: committeeVisionFallback.value,
            textModelA: committeeTextA.value,
            textModelB: committeeTextB.value,
            textModelC: committeeTextC.value
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
          let boundary = buffer.indexOf("\\n");

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
                if (requestSerial !== committeeRequestSerial) {
                  continue;
                }

                if (!committeeActiveRunId && event.runId) {
                  committeeActiveRunId = event.runId;
                }

                if (event.type === "status") {
                  committeeStatus.textContent = event.message || "Analisando...";
                }

                if (event.type === "capture") {
                  renderCommitteeSnapshot(event.frameBase64 || "");
                }

                if (event.type === "vision_begin") {
                  setMarkdownContent(committeeSceneReport, "Lendo a frame com o modelo de visão principal...");
                }

                if (event.type === "vision_result") {
                  const blocks = [];
                  blocks.push((event.role || "Visão") + " (" + (event.model || "modelo") + ")");
                  if (event.fallbackUsed) {
                    blocks.push("Fallback acionado.");
                  }
                  if (event.error) {
                    blocks.push("Falha: " + event.error);
                  }
                  blocks.push(event.text || "Sem leitura.");
                  setMarkdownContent(committeeSceneReport, blocks.join("\\n\\n"));
                }

                if (event.type === "member_begin") {
                  setCommitteeCardMeta(event.memberId, event.role || event.memberId, event.model || "modelo", "");
                }

                if (event.type === "member_delta") {
                  appendCommitteeOutput(event.memberId, event.delta || "");
                }

                if (event.type === "member_done") {
                  const outputNode = document.getElementById("committee-output-" + event.memberId);
                  if (outputNode && !(outputNode.dataset.markdownSource || "").trim()) {
                    setMarkdownContent(outputNode, event.text || "Sem resposta.");
                  }
                }

                if (event.type === "member_error") {
                  setCommitteeCardMeta(event.memberId, event.role || event.memberId, event.model || "modelo", "Erro: " + (event.error || "falha desconhecida"));
                }

                if (event.type === "stopped") {
                  committeeStatus.textContent = event.message || "Análise interrompida.";
                }

                if (event.type === "done") {
                  committeeStatus.textContent = event.stopped
                    ? "Análise interrompida."
                    : (event.ok ? "Comitê concluído." : "Comitê concluído com avisos.");
                }
              }
            }

            boundary = buffer.indexOf("\\n");
          }

          if (done) {
            break;
          }
        }
      } catch (error) {
        if (committeeRequestSerial === requestSerial) {
          if (String(error?.name || "") === "AbortError") {
            committeeStatus.textContent = "Análise interrompida.";
          } else {
            committeeStatus.textContent = error.message;
          }
        }
      } finally {
        if (committeeAbortController && committeeAbortController.signal.aborted) {
          committeeAbortController = null;
        }
        if (committeeRequestSerial === requestSerial) {
          committeeAbortController = null;
          committeeActiveRunId = null;
          updateCommitteeBusy(false);
        }
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
      downloadBatButton.disabled = true;
      downloadStatus.textContent = "Gerando launcher universal...";

      try {
        const response = await fetch("/api/generate-bat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({})
        });

        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.error || "Falha ao gerar o arquivo.");
        }

        const blob = await response.blob();
        const downloadUrl = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = downloadUrl;
        anchor.download = parseDownloadFilename(response, "redseb-universal.bat");
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(downloadUrl);
        downloadStatus.textContent = "Launcher universal gerado com sucesso.";
      } catch (error) {
        downloadStatus.textContent = error.message;
      } finally {
        downloadBatButton.disabled = false;
      }
    }

    refresh();
    hydrateAlertPreferences();
    hydrateFrameSizePreference();
    loadCommitteeCatalog().catch((error) => {
      committeeStatus.textContent = error.message;
    });
    setInterval(refresh, 1000);
    sendAlertButton.addEventListener("click", sendAlert);
    alertPosition.addEventListener("change", () => persistAlertPosition(alertPosition.value));
    viewerFrameSize.addEventListener("change", () => persistFrameSize(viewerFrameSize.value));
    copyFrameButton.addEventListener("click", copyCurrentFrame);
    downloadBatButton.addEventListener("click", downloadBat);
    committeeRunButton.addEventListener("click", runCommitteeAnalysis);
    [committeeVisionPrimary, committeeVisionFallback, committeeTextA, committeeTextB, committeeTextC].forEach((node) => {
      node.addEventListener("change", () => {
        persistCommitteePreferences();
        resetCommitteeOutputs();
      });
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
        const visionFallbackModel = String(payload.visionFallbackModel || defaults.visionFallback || "").trim();
        const textModelA = String(payload.textModelA || defaults.textA || "").trim();
        const textModelB = String(payload.textModelB || defaults.textB || "").trim();
        const textModelC = String(payload.textModelC || defaults.textC || "").trim();

        const run = createCommitteeRun();
        const closeHandler = () => stopCommitteeRun(run.runId);

        response.writeHead(200, {
          "Content-Type": "application/x-ndjson; charset=utf-8",
          "Cache-Control": "no-store, no-cache, must-revalidate",
          "Connection": "keep-alive",
          "X-Accel-Buffering": "no"
        });
        request.on("close", closeHandler);

        try {
          writeCommitteeRunEvent(response, run, {
            type: "capture",
            sessionId,
            viewId: target.view.viewId,
            frameBase64: target.view.imageBase64
          });

          writeCommitteeRunEvent(response, run, {
            type: "status",
            stage: "capture",
            message: "Frame atual capturada. Iniciando leitura visual."
          });

          writeCommitteeRunEvent(response, run, {
            type: "vision_begin",
            memberId: "vision_primary",
            role: "Visao principal",
            model: visionPrimaryModel
          });

          let primaryVisionText = "";
          let primaryVisionError = "";
          try {
            primaryVisionText = await requestVisionExtraction(visionPrimaryModel, target.view.imageBase64, run);
          } catch (error) {
            if (isCommitteeAbortError(error, run)) {
              throw error;
            }
            primaryVisionError = error.message;
          }

          ensureCommitteeRunActive(run);
          let fallbackVisionText = "";
          let fallbackVisionError = "";
          let fallbackUsed = false;

          if (visionFallbackModel && visionFallbackModel !== visionPrimaryModel && (primaryVisionError || shouldUseVisionFallback(primaryVisionText))) {
            fallbackUsed = true;
            writeCommitteeRunEvent(response, run, {
              type: "status",
              stage: "vision_fallback",
              message: "A leitura principal ficou fraca ou falhou. Acionando fallback visual."
            });
            writeCommitteeRunEvent(response, run, {
              type: "vision_begin",
              memberId: "vision_fallback",
              role: "Fallback visual",
              model: visionFallbackModel
            });
            try {
              fallbackVisionText = await requestVisionExtraction(visionFallbackModel, target.view.imageBase64, run);
            } catch (error) {
              if (isCommitteeAbortError(error, run)) {
                throw error;
              }
              fallbackVisionError = error.message;
            }
          }

          ensureCommitteeRunActive(run);
          const chosenVisionText = String(fallbackVisionText || primaryVisionText || "").trim();
          const supportVisionText = fallbackUsed
            ? (primaryVisionText || (primaryVisionError ? "Falha: " + primaryVisionError : ""))
            : (fallbackVisionText || (fallbackVisionError ? "Falha: " + fallbackVisionError : ""));

          writeCommitteeRunEvent(response, run, {
            type: "vision_result",
            memberId: "vision_primary",
            role: "Relatorio visual consolidado",
            model: fallbackUsed ? visionFallbackModel : visionPrimaryModel,
            text: chosenVisionText || "Nenhum relatorio visual valido foi obtido.",
            fallbackUsed,
            error: (!chosenVisionText && (primaryVisionError || fallbackVisionError)) ? (fallbackVisionError || primaryVisionError) : ""
          });

          const prompt = buildCommitteeBrief({
            session: target.session,
            view: target.view,
            visionReport: chosenVisionText || "Nenhum relatorio visual valido foi obtido.",
            visionFallback: supportVisionText || "Sem apoio adicional."
          });

          writeCommitteeRunEvent(response, run, {
            type: "status",
            stage: "committee",
            message: "Relatorio visual consolidado. Iniciando respostas em paralelo."
          });

          const committeeMembers = [
            { id: "text_a", role: "Analista A", model: textModelA },
            { id: "text_b", role: "Analista B", model: textModelB },
            { id: "text_c", role: "Analista C", model: textModelC }
          ].filter((member) => member.model);

          const results = await Promise.all(
            committeeMembers.map((member) =>
              streamCommitteeMember(member, prompt, response, run)
                .then(() => ({ ok: true }))
                .catch((error) => {
                  if (isCommitteeAbortError(error, run)) {
                    return { ok: false, stopped: true };
                  }
                  writeCommitteeRunEvent(response, run, {
                    type: "member_error",
                    memberId: member.id,
                    role: member.role,
                    model: member.model,
                    error: error.message
                  });
                  return { ok: false, error: error.message };
                })
            )
          );

          ensureCommitteeRunActive(run);
          writeCommitteeRunEvent(response, run, {
            type: "done",
            ok: results.every((item) => item.ok),
            sessionId,
            viewId: target.view.viewId,
            stopped: false
          });
          response.end();
        } catch (error) {
          const stopped = isCommitteeAbortError(error, run);
          if (!response.writableEnded) {
            writeCommitteeRunEvent(response, run, {
              type: stopped ? "stopped" : "done",
              ok: false,
              stopped,
              sessionId,
              viewId: target.view.viewId,
              message: stopped ? "Analise interrompida pelo operador." : (error.message || "Falha durante a analise.")
            });
            if (!stopped) {
              writeCommitteeRunEvent(response, run, {
                type: "done",
                ok: false,
                stopped: false,
                sessionId,
                viewId: target.view.viewId
              });
            }
            response.end();
          }
        } finally {
          request.off("close", closeHandler);
          finalizeCommitteeRun(run);
        }
      })
      .catch((error) => sendJson(response, 500, { ok: false, error: error.message }));
  }

  if (pathname === "/api/committee/stop" && request.method === "POST") {
    return readRequestBody(request)
      .then((body) => {
        let payload;

        try {
          payload = JSON.parse(body || "{}");
        } catch {
          return sendJson(response, 400, { ok: false, error: "Payload invalido." });
        }

        const runId = String(payload.runId || "").trim();
        if (!runId) {
          return sendJson(response, 400, { ok: false, error: "Informe o runId da analise atual." });
        }

        const stopped = stopCommitteeRun(runId);
        if (!stopped) {
          return sendJson(response, 404, { ok: false, error: "Analise nao encontrada ou ja finalizada." });
        }

        return sendJson(response, 200, { ok: true, runId, stopped: true });
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
        try {
          JSON.parse(body || "{}");
        } catch {
          return sendJson(response, 400, { ok: false, error: "Payload invalido." });
        }

        const content = buildPortableLauncherBat();
        const filename = downloadFilenameFromSeb({});
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
    markSocketClosed(socket);
  });
});

setInterval(pruneStaleSessions, Math.min(sessionStaleMs, 1000)).unref();

server.listen(port, host, () => {
  console.log(`seb-remote-view listening on http://${host}:${port}`);
  console.log(`resolved assets: ${JSON.stringify(resolvedAssets)}`);
  console.log(`resolved downloads: ${JSON.stringify(resolvedDownloads)}`);
});
