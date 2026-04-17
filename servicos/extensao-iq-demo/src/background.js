const DEFAULT_CONFIG = {
  enabled: true,
  demoOnly: true,
  sampleIntervalMs: 250,
  maxTicks: 240,
  sendIntervalMs: 500,
  bridgeEnabled: true,
  bridgeUrl: "http://redsystems.ddns.net/iq-bridge",
  bridgeToken: "",
  bridgeMinIntervalMs: 600,
  frameCaptureEnabled: true,
  frameMinIntervalMs: 2500,
  bridgeTransportEnabled: false,
  bridgeTransportFlushMs: 1000,
  bridgeTransportBatchSize: 40,
  bridgeCommandPollingEnabled: true,
  bridgeCommandPollMs: 2000,
  bridgeRawSnapshotEnabled: false,
  bridgeDiagnosticsEnabled: true,
};

const WORKER_LOG_LIMIT = 120;

let bridgeState = {
  lastSuccessAt: 0,
  lastErrorAt: 0,
  lastError: "",
  lastFrameSuccessAt: 0,
  lastFrameErrorAt: 0,
  lastFrameError: "",
};

let workerLogs = [];
let lastStateLogKey = "";
let lastStateLogAt = 0;
let transportQueue = [];
let transportFlushTimer = 0;
let commandPollTimer = 0;
let lastKnownTabId = null;
let reinjectByTabId = {};

function trimText(value, max = 260) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

async function persistWorkerLogs() {
  await chrome.storage.session.set({ workerLogs });
}

function pushWorkerLog(level, event, payload = {}) {
  const entry = {
    ts: Date.now(),
    level,
    event,
    payload,
  };
  workerLogs.push(entry);
  if (workerLogs.length > WORKER_LOG_LIMIT) {
    workerLogs = workerLogs.slice(-WORKER_LOG_LIMIT);
  }

  const stamp = new Date(entry.ts).toLocaleTimeString();
  const line = `[RED IQ][${level.toUpperCase()}][${event}] ${trimText(JSON.stringify(payload))}`;
  if (level === "error") console.error(line);
  else if (level === "warn") console.warn(line);
  else console.log(line);
  persistWorkerLogs().catch(console.error);
}

function summarizeStateForLog(state) {
  const debug = state?.debug || {};
  return {
    mode: state?.mode || "-",
    asset: state?.asset || "-",
    market: state?.marketType || "-",
    price: state?.currentPrice ?? null,
    payout: state?.payoutPct ?? null,
    countdown: state?.countdown || "-",
    buyWindowOpen: !!state?.buyWindowOpen,
    suspendedHint: !!state?.suspendedHint,
    activeId: state?.activeId ?? debug?.ids?.selectedAssetId ?? null,
    uiFlags: state?.uiFlags || {},
    healthFlags: state?.healthFlags || {},
  };
}

function maybeLogState(state) {
  const summary = summarizeStateForLog(state);
  const key = JSON.stringify(summary);
  const now = Date.now();
  if (key === lastStateLogKey && now - lastStateLogAt < 5000) return;
  lastStateLogKey = key;
  lastStateLogAt = now;
  pushWorkerLog("info", "state", summary);
}

async function pushToBridge(snapshot, config) {
  if (!config.bridgeEnabled || !config.bridgeUrl) return;
  const now = Date.now();
  if (now - bridgeState.lastSuccessAt < (config.bridgeMinIntervalMs || 600)) return;

  const response = await fetch(`${config.bridgeUrl.replace(/\/$/, "")}/api/telemetry`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(config.bridgeToken ? { "x-red-token": config.bridgeToken } : {}),
      "x-red-session": `chrome-extension:${chrome.runtime.id}`,
    },
    body: JSON.stringify(snapshot),
  });
  if (!response.ok) {
    throw new Error(`bridge_http_${response.status}`);
  }
  bridgeState.lastSuccessAt = now;
  bridgeState.lastError = "";
}

async function pushFrameToBridge(frame, config) {
  if (!config.bridgeEnabled || !config.bridgeUrl || !config.frameCaptureEnabled) return;
  const now = Date.now();
  if (now - bridgeState.lastFrameSuccessAt < (config.frameMinIntervalMs || 2500)) return;

  const response = await fetch(`${config.bridgeUrl.replace(/\/$/, "")}/api/frame`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(config.bridgeToken ? { "x-red-token": config.bridgeToken } : {}),
      "x-red-session": `chrome-extension:${chrome.runtime.id}`,
    },
    body: JSON.stringify(frame),
  });
  if (!response.ok) {
    throw new Error(`bridge_frame_http_${response.status}`);
  }
  bridgeState.lastFrameSuccessAt = now;
  bridgeState.lastFrameError = "";
  pushWorkerLog("info", "bridge.frame.ok", {
    asset: frame?.frame?.asset || "-",
    market: frame?.frame?.marketType || "-",
    canvas: frame?.frame?.canvas || null,
  });
}

async function captureVisibleTabImage(windowId, fallbackDataUrl = "") {
  try {
    const dataUrl = await chrome.tabs.captureVisibleTab(
      Number.isFinite(windowId) ? windowId : undefined,
      { format: "jpeg", quality: 72 },
    );
    if (typeof dataUrl === "string" && dataUrl.startsWith("data:image/")) {
      return dataUrl;
    }
  } catch (error) {
    pushWorkerLog("warn", "frame.capture_visible_tab.error", {
      error: String(error),
      windowId,
    });
  }
  return fallbackDataUrl || "";
}

async function pushTransportBatchToBridge(items, config) {
  if (!config.bridgeEnabled || !config.bridgeUrl || !config.bridgeTransportEnabled || !items.length) return;
  const response = await fetch(`${config.bridgeUrl.replace(/\/$/, "")}/api/logs`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(config.bridgeToken ? { "x-red-token": config.bridgeToken } : {}),
      "x-red-session": `chrome-extension:${chrome.runtime.id}`,
    },
    body: JSON.stringify({ items }),
  });
  if (!response.ok) {
    throw new Error(`bridge_logs_http_${response.status}`);
  }
}

async function pushSingleLogToBridge(item, config) {
  if (!config.bridgeEnabled || !config.bridgeUrl) return;
  const response = await fetch(`${config.bridgeUrl.replace(/\/$/, "")}/api/log`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(config.bridgeToken ? { "x-red-token": config.bridgeToken } : {}),
      "x-red-session": `chrome-extension:${chrome.runtime.id}`,
    },
    body: JSON.stringify(item),
  });
  if (!response.ok) {
    throw new Error(`bridge_log_http_${response.status}`);
  }
}

async function flushTransportQueue() {
  if (!transportQueue.length) return;
  const batch = transportQueue.splice(0, transportQueue.length);
  const { config } = await chrome.storage.local.get("config");
  const merged = { ...DEFAULT_CONFIG, ...(config || {}) };
  try {
    await pushTransportBatchToBridge(batch, merged);
  } catch (error) {
    bridgeState.lastErrorAt = Date.now();
    bridgeState.lastError = String(error);
    pushWorkerLog("error", "bridge.transport.error", {
      error: String(error),
      batch: batch.length,
    });
    await chrome.storage.session.set({ bridgeState });
  }
}

function scheduleTransportFlush(delayMs = DEFAULT_CONFIG.bridgeTransportFlushMs) {
  if (transportFlushTimer) return;
  transportFlushTimer = setTimeout(async () => {
    transportFlushTimer = 0;
    await flushTransportQueue();
  }, delayMs);
}

async function ensureDefaults() {
  const stored = await chrome.storage.local.get("config");
  if (!stored.config) {
    await chrome.storage.local.set({ config: DEFAULT_CONFIG });
    return DEFAULT_CONFIG;
  }
  const migrated = { ...stored.config };
  const legacyBridgeUrl = String(migrated.bridgeUrl || "").trim();
  if (!legacyBridgeUrl || /:3115\/?$/.test(legacyBridgeUrl)) {
    migrated.bridgeUrl = DEFAULT_CONFIG.bridgeUrl;
  }
  if (typeof migrated.bridgeTransportEnabled !== "boolean") {
    migrated.bridgeTransportEnabled = DEFAULT_CONFIG.bridgeTransportEnabled;
  }
  if (migrated.frameCaptureEnabled !== true) {
    migrated.frameCaptureEnabled = DEFAULT_CONFIG.frameCaptureEnabled;
  }
  if (typeof migrated.bridgeRawSnapshotEnabled !== "boolean") {
    migrated.bridgeRawSnapshotEnabled = DEFAULT_CONFIG.bridgeRawSnapshotEnabled;
  }
  if (typeof migrated.bridgeDiagnosticsEnabled !== "boolean") {
    migrated.bridgeDiagnosticsEnabled = DEFAULT_CONFIG.bridgeDiagnosticsEnabled;
  }
  const merged = { ...DEFAULT_CONFIG, ...migrated };
  if (JSON.stringify(merged) !== JSON.stringify(stored.config)) {
    await chrome.storage.local.set({ config: merged });
  }
  return merged;
}

async function ackCommand(config, id, ok, result) {
  const response = await fetch(`${config.bridgeUrl.replace(/\/$/, "")}/api/commands/${id}/ack`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(config.bridgeToken ? { "x-red-token": config.bridgeToken } : {}),
      "x-red-session": `chrome-extension:${chrome.runtime.id}`,
    },
    body: JSON.stringify({ ok, result }),
  });
  if (!response.ok) {
    throw new Error(`bridge_ack_http_${response.status}`);
  }
}

async function pullCommands(config) {
  if (!config.bridgeEnabled || !config.bridgeUrl || !config.bridgeCommandPollingEnabled) return;
  const response = await fetch(`${config.bridgeUrl.replace(/\/$/, "")}/api/commands/pull`, {
    method: "GET",
    headers: {
      ...(config.bridgeToken ? { "x-red-token": config.bridgeToken } : {}),
      "x-red-session": `chrome-extension:${chrome.runtime.id}`,
    },
  });
  if (!response.ok) {
    throw new Error(`bridge_pull_http_${response.status}`);
  }
  const data = await response.json();
  return Array.isArray(data?.items) ? data.items : [];
}

async function getTargetTabId() {
  const tab = await findBestIqTab();
  if (tab?.id) {
    lastKnownTabId = tab.id;
    return tab.id;
  }
  return lastKnownTabId;
}

function isIqUrl(url) {
  return /^https:\/\/([^.]+\.)?iqoption\.com\//i.test(String(url || ""));
}

function isTraderoomUrl(url) {
  return /^https:\/\/([^.]+\.)?iqoption\.com\/traderoom/i.test(String(url || ""));
}

function isInjectableIqTab(tab) {
  return !!tab?.id && isIqUrl(tab.url || "");
}

async function findBestIqTab() {
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (isInjectableIqTab(activeTab)) {
    return activeTab;
  }

  if (typeof lastKnownTabId === "number") {
    try {
      const lastKnownTab = await chrome.tabs.get(lastKnownTabId);
      if (isInjectableIqTab(lastKnownTab)) {
        return lastKnownTab;
      }
    } catch (_) {}
  }

  const tabs = await chrome.tabs.query({});
  const iqTabs = tabs.filter(isInjectableIqTab);
  if (!iqTabs.length) return null;

  const traderoomTabs = iqTabs.filter((tab) => isTraderoomUrl(tab.url || ""));
  const ordered = traderoomTabs.length ? traderoomTabs : iqTabs;

  ordered.sort((left, right) => {
    const leftScore = Number(!!left.active) * 10 + Number(!!left.highlighted) * 5 + Number(!!isTraderoomUrl(left.url || "")) * 2;
    const rightScore = Number(!!right.active) * 10 + Number(!!right.highlighted) * 5 + Number(!!isTraderoomUrl(right.url || "")) * 2;
    return rightScore - leftScore;
  });

  return ordered[0] || null;
}

async function pingReceiver(tabId) {
  const response = await chrome.tabs.sendMessage(tabId, { type: "rediq:ping" });
  return !!response?.ok;
}

async function reinjectIntoTab(tabId) {
  if (!tabId) return false;
  const now = Date.now();
  if (now - (reinjectByTabId[tabId] || 0) < 1500) {
    return false;
  }
  reinjectByTabId[tabId] = now;

  const tab = await chrome.tabs.get(tabId);
  if (!isInjectableIqTab(tab)) {
    pushWorkerLog("warn", "receiver.reinject.skip", { tabId, url: tab?.url || "" });
    return false;
  }

  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["src/injected-bridge.js"],
    world: "MAIN",
  });
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["src/content.js"],
  });
  await chrome.scripting.insertCSS({
    target: { tabId },
    files: ["src/overlay.css"],
  });

  pushWorkerLog("info", "receiver.reinject.ok", {
    tabId,
    url: tab.url || "",
    title: tab.title || "",
  });
  return true;
}

async function ensureReceiver(tabId) {
  if (!tabId) return false;
  try {
    return await pingReceiver(tabId);
  } catch (error) {
    const message = String(error || "");
    pushWorkerLog("warn", "receiver.ping.failed", { tabId, error: message });
    if (!/Receiving end does not exist|Could not establish connection|The message port closed/i.test(message)) {
      return false;
    }
  }

  try {
    const reinjected = await reinjectIntoTab(tabId);
    if (!reinjected) return false;
  } catch (error) {
    pushWorkerLog("error", "receiver.reinject.error", { tabId, error: String(error) });
    return false;
  }

  await new Promise((resolve) => setTimeout(resolve, 250));
  try {
    return await pingReceiver(tabId);
  } catch (error) {
    pushWorkerLog("error", "receiver.ping.retry_failed", { tabId, error: String(error) });
    return false;
  }
}

async function runCommandPoll() {
  const { config } = await chrome.storage.local.get("config");
  const merged = { ...DEFAULT_CONFIG, ...(config || {}) };
  if (!merged.bridgeCommandPollingEnabled) return;

  try {
    const commands = await pullCommands(merged);
    if (!commands.length) return;
    const targetTabId = await getTargetTabId();
    const receiverReady = targetTabId ? await ensureReceiver(targetTabId) : false;
    pushWorkerLog("info", "bridge.command.target", {
      targetTabId,
      receiverReady,
      commands: commands.map((item) => item.command),
    });
    for (const command of commands) {
      let result = { ok: false, error: "no_target_tab" };
      if (targetTabId && receiverReady) {
        try {
          result = await chrome.tabs.sendMessage(targetTabId, {
            type: "rediq:command",
            command: command.command,
            payload: command.payload || {},
          });
        } catch (error) {
          result = { ok: false, error: String(error) };
        }
      }
      await ackCommand(merged, command.id, !!result?.ok, result);
      pushWorkerLog("info", "bridge.command.ack", {
        id: command.id,
        command: command.command,
        ok: !!result?.ok,
      });
    }
  } catch (error) {
    pushWorkerLog("error", "bridge.command.error", { error: String(error) });
  }
}

function ensureCommandPolling() {
  if (commandPollTimer) return;
  commandPollTimer = setInterval(() => {
    runCommandPoll().catch(console.error);
  }, DEFAULT_CONFIG.bridgeCommandPollMs);
}

chrome.runtime.onInstalled.addListener(() => {
  ensureDefaults().catch(console.error);
  ensureCommandPolling();
  pushWorkerLog("info", "worker.installed", { version: chrome.runtime.getManifest().version });
});

chrome.runtime.onStartup?.addListener(() => {
  ensureDefaults().catch(console.error);
  ensureCommandPolling();
  pushWorkerLog("info", "worker.startup", { version: chrome.runtime.getManifest().version });
});

ensureCommandPolling();

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  try {
    const tab = await chrome.tabs.get(tabId);
    if (isInjectableIqTab(tab)) {
      lastKnownTabId = tabId;
      pushWorkerLog("info", "tab.activated", { tabId, url: tab.url || "", title: tab.title || "" });
    }
  } catch (_) {}
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (!isInjectableIqTab(tab)) return;
  lastKnownTabId = tabId;
  if (changeInfo.status || changeInfo.url) {
    pushWorkerLog("info", "tab.updated", {
      tabId,
      status: changeInfo.status || "",
      url: changeInfo.url || tab.url || "",
      title: tab.title || "",
    });
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  if (lastKnownTabId === tabId) {
    lastKnownTabId = null;
  }
  delete reinjectByTabId[tabId];
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    const tabId = sender.tab?.id;
    if (typeof tabId === "number") {
      lastKnownTabId = tabId;
    }
    if (message?.type === "rediq:get-config") {
      const { config } = await chrome.storage.local.get("config");
      sendResponse({ ok: true, config: { ...DEFAULT_CONFIG, ...(config || {}) } });
      return;
    }

    if (message?.type === "rediq:set-config") {
      const { config } = await chrome.storage.local.get("config");
      const nextConfig = { ...DEFAULT_CONFIG, ...(config || {}), ...(message.patch || {}) };
      await chrome.storage.local.set({ config: nextConfig });
      sendResponse({ ok: true, config: nextConfig });
      return;
    }

    if (message?.type === "rediq:state" && typeof tabId === "number") {
      const snapshot = {
        tabId,
        title: sender.tab?.title || "",
        url: sender.tab?.url || "",
        receivedAt: Date.now(),
        state: message.payload || {},
      };
      await chrome.storage.session.set({
        [`tab:${tabId}`]: snapshot,
        bridgeState,
      });
      maybeLogState(snapshot.state);
      const { config } = await chrome.storage.local.get("config");
      const merged = { ...DEFAULT_CONFIG, ...(config || {}) };
      try {
        await pushToBridge(snapshot, merged);
        await chrome.storage.session.set({ bridgeState });
      } catch (error) {
        bridgeState.lastErrorAt = Date.now();
        bridgeState.lastError = String(error);
        pushWorkerLog("error", "bridge.telemetry.error", {
          error: String(error),
          asset: snapshot?.state?.asset || "-",
          market: snapshot?.state?.marketType || "-",
        });
        await chrome.storage.session.set({ bridgeState });
      }
      sendResponse({ ok: true });
      return;
    }

    if (message?.type === "rediq:get-state") {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.id) {
        sendResponse({ ok: false, error: "no_active_tab" });
        return;
      }
      const data = await chrome.storage.session.get([`tab:${tab.id}`, "bridgeState"]);
      sendResponse({ ok: true, snapshot: data[`tab:${tab.id}`] || null, bridgeState: data.bridgeState || bridgeState });
      return;
    }

    if (message?.type === "rediq:frame" && typeof tabId === "number") {
      const capturedImage = await captureVisibleTabImage(sender.tab?.windowId, message.payload?.imageDataUrl || "");
      if (!capturedImage || !String(capturedImage).startsWith("data:image/")) {
        pushWorkerLog("warn", "frame.capture.empty", {
          tabId,
          windowId: sender.tab?.windowId,
          asset: message.payload?.asset || "-",
          market: message.payload?.marketType || "-",
        });
        sendResponse({ ok: false, error: "frame_capture_empty" });
        return;
      }
      const frame = {
        tabId,
        title: sender.tab?.title || "",
        url: sender.tab?.url || "",
        receivedAt: Date.now(),
        frame: {
          ...(message.payload || {}),
          imageDataUrl: capturedImage || message.payload?.imageDataUrl || "",
          captureSource: capturedImage ? "visible-tab" : "canvas-fallback",
        },
      };
      const { config } = await chrome.storage.local.get("config");
      const merged = { ...DEFAULT_CONFIG, ...(config || {}) };
      try {
        await pushFrameToBridge(frame, merged);
        await chrome.storage.session.set({ bridgeState });
      } catch (error) {
        bridgeState.lastFrameErrorAt = Date.now();
        bridgeState.lastFrameError = String(error);
        pushWorkerLog("error", "bridge.frame.error", {
          error: String(error),
          asset: frame?.frame?.asset || "-",
          market: frame?.frame?.marketType || "-",
        });
        await chrome.storage.session.set({ bridgeState });
      }
      sendResponse({ ok: true });
      return;
    }

    if (message?.type === "rediq:transport") {
      const payload = message.payload || {};
      const { config } = await chrome.storage.local.get("config");
      const merged = { ...DEFAULT_CONFIG, ...(config || {}) };
      if (!merged.bridgeTransportEnabled) {
        sendResponse({ ok: true, skipped: true });
        return;
      }
      transportQueue.push({
        level: "info",
        event: `transport.${payload.kind || "unknown"}`,
        message: trimText(payload.signature || payload.text || "", 500),
        asset: payload.asset || "",
        payload,
      });
      if (transportQueue.length >= (merged.bridgeTransportBatchSize || DEFAULT_CONFIG.bridgeTransportBatchSize)) {
        await flushTransportQueue();
      } else {
        scheduleTransportFlush(merged.bridgeTransportFlushMs || DEFAULT_CONFIG.bridgeTransportFlushMs);
      }
      sendResponse({ ok: true });
      return;
    }

    if (message?.type === "rediq:raw-snapshot") {
      const { config } = await chrome.storage.local.get("config");
      const merged = { ...DEFAULT_CONFIG, ...(config || {}) };
      if (!merged.bridgeRawSnapshotEnabled) {
        sendResponse({ ok: true, skipped: true });
        return;
      }
      try {
        await pushSingleLogToBridge({
          level: "info",
          event: "snapshot.raw",
          sessionId: "",
          asset: message.payload?.current?.asset || message.payload?.asset || "",
          message: trimText(JSON.stringify({
            asset: message.payload?.current?.asset,
            currentPrice: message.payload?.current?.currentPrice,
            ids: message.payload?.ids,
          }), 500),
          payload: message.payload || {},
        }, merged);
      } catch (error) {
        pushWorkerLog("error", "bridge.snapshot.error", {
          error: String(error),
          asset: message.payload?.current?.asset || "-",
        });
      }
      sendResponse({ ok: true });
      return;
    }

    if (message?.type === "rediq:diagnostic") {
      const { config } = await chrome.storage.local.get("config");
      const merged = { ...DEFAULT_CONFIG, ...(config || {}) };
      if (!merged.bridgeDiagnosticsEnabled) {
        sendResponse({ ok: true, skipped: true });
        return;
      }
      try {
        await pushSingleLogToBridge({
          level: message.payload?.level || "info",
          event: message.payload?.event || "diagnostic",
          sessionId: "",
          asset: message.payload?.asset || "",
          message: trimText(message.payload?.message || message.payload?.event || "diagnostic", 500),
          payload: message.payload?.payload || {},
        }, merged);
      } catch (error) {
        pushWorkerLog("error", "bridge.diagnostic.error", {
          error: String(error),
          event: message.payload?.event || "diagnostic",
        });
      }
      sendResponse({ ok: true });
      return;
    }

    if (message?.type === "rediq:get-worker-logs") {
      sendResponse({ ok: true, logs: workerLogs });
      return;
    }

    sendResponse({ ok: false, error: "unknown_message" });
  })().catch((error) => {
    pushWorkerLog("error", "worker.message.error", { error: String(error), type: message?.type || "unknown" });
    sendResponse({ ok: false, error: String(error) });
  });

  return true;
});
