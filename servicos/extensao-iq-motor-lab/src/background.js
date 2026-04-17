const DEFAULT_CONFIG = {
  enabled: true,
  bridgeUrl: "http://redsystems.ddns.net/iq-bridge",
  bridgeToken: "",
  channel: "spy",
  pollMs: 1000,
  reportState: true,
  stateIntervalMs: 1500,
};

let pollTimer = 0;
let lastRemoteRevision = -1;
let workerState = {
  lastFetchAt: 0,
  lastFetchError: "",
  lastConfig: null,
  lastBroadcastAt: 0,
  lastAppliedRevision: -1,
};

function trim(text, max = 240) {
  const value = String(text || "").replace(/\s+/g, " ").trim();
  return value.length > max ? `${value.slice(0, max)}...` : value;
}

function log(event, payload = {}, level = "info") {
  const line = `[RED IQ LAB][${level.toUpperCase()}][${event}] ${trim(JSON.stringify(payload))}`;
  if (level === "error") console.error(line);
  else if (level === "warn") console.warn(line);
  else console.log(line);
}

async function getConfig() {
  const stored = await chrome.storage.local.get("motorLabConfig");
  const merged = { ...DEFAULT_CONFIG, ...(stored.motorLabConfig || {}) };
  await chrome.storage.local.set({ motorLabConfig: merged });
  return merged;
}

async function findIqTabs() {
  return chrome.tabs.query({ url: ["https://iqoption.com/*", "https://*.iqoption.com/*"] });
}

async function sendToIqTabs(message) {
  const tabs = await findIqTabs();
  let delivered = 0;
  for (const tab of tabs) {
    if (!tab.id) continue;
    try {
      const result = await chrome.tabs.sendMessage(tab.id, message);
      if (result?.ok) delivered += 1;
    } catch (_) {
      // content script may not be ready yet
    }
  }
  return delivered;
}

async function pushLog(event, payload, config) {
  if (!config.bridgeUrl) return;
  try {
    await fetch(`${config.bridgeUrl.replace(/\/$/, "")}/api/log`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(config.bridgeToken ? { "x-red-token": config.bridgeToken } : {}),
        "x-red-session": `chrome-extension:${chrome.runtime.id}`,
      },
      body: JSON.stringify({
        level: "info",
        event,
        sessionId: `chrome-extension:${chrome.runtime.id}`,
        asset: "",
        payload,
      }),
    });
  } catch (error) {
    log("bridge.log.error", { event, error: String(error) }, "warn");
  }
}

async function fetchRemoteConfig() {
  const config = await getConfig();
  if (!config.enabled || !config.bridgeUrl) return;
  try {
    const response = await fetch(
      `${config.bridgeUrl.replace(/\/$/, "")}/api/motor/config/current?channel=${encodeURIComponent(config.channel)}`,
      {
        headers: {
          ...(config.bridgeToken ? { "x-red-token": config.bridgeToken } : {}),
          "x-red-session": `chrome-extension:${chrome.runtime.id}`,
        },
      },
    );
    if (!response.ok) throw new Error(`motor_config_http_${response.status}`);
    const data = await response.json();
    const item = data?.item || {};
    workerState.lastFetchAt = Date.now();
    workerState.lastFetchError = "";
    workerState.lastConfig = item;
    const nextRevision = Number(item.revision || 0);
    const revisionChanged = nextRevision !== lastRemoteRevision;
    const shouldBroadcast =
      revisionChanged
      || !workerState.lastBroadcastAt
      || (Date.now() - workerState.lastBroadcastAt) >= Math.max(2000, Number(config.pollMs || DEFAULT_CONFIG.pollMs) * 3);
    if (revisionChanged) {
      lastRemoteRevision = nextRevision;
      log("config.updated", { revision: lastRemoteRevision, channel: item.channel || config.channel });
      await pushLog("motor_lab.config.updated", {
        revision: lastRemoteRevision,
        channel: item.channel || config.channel,
      }, config);
    }
    if (shouldBroadcast) {
      const delivered = await sendToIqTabs({
        type: "motor-lab-config",
        item,
      });
      workerState.lastBroadcastAt = Date.now();
      log("config.broadcast", {
        revision: nextRevision,
        delivered,
        channel: item.channel || config.channel,
      });
      await pushLog("motor_lab.config.broadcast", {
        revision: nextRevision,
        delivered,
        channel: item.channel || config.channel,
      }, config);
    }
  } catch (error) {
    workerState.lastFetchError = String(error);
    log("config.fetch.error", { error: String(error) }, "warn");
  }
}

function schedulePoll(delayMs = DEFAULT_CONFIG.pollMs) {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => {
    pollTimer = 0;
    const config = await getConfig();
    await fetchRemoteConfig();
    schedulePoll(config.pollMs || DEFAULT_CONFIG.pollMs);
  }, delayMs);
}

chrome.runtime.onInstalled.addListener(async () => {
  await getConfig();
  schedulePoll();
});

chrome.runtime.onStartup.addListener(async () => {
  await getConfig();
  schedulePoll();
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local" || !changes.motorLabConfig) return;
  schedulePoll();
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "motor-lab-fetch-config") {
    getConfig()
      .then(async (config) => {
        const response = await fetch(
          `${config.bridgeUrl.replace(/\/$/, "")}/api/motor/config/current?channel=${encodeURIComponent(config.channel)}`,
          {
            headers: {
              ...(config.bridgeToken ? { "x-red-token": config.bridgeToken } : {}),
              "x-red-session": `chrome-extension:${chrome.runtime.id}`,
            },
            cache: "no-store",
          },
        );
        if (!response.ok) {
          throw new Error(`motor_config_http_${response.status}`);
        }
        const data = await response.json();
        sendResponse({ ok: true, item: data?.item || null });
      })
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }
  if (message?.type === "motor-lab-push-log") {
    getConfig()
      .then(async (config) => {
        await pushLog(
          message.event || "motor_lab.report",
          message.payload || {},
          config,
        );
        sendResponse({ ok: true });
      })
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }
  if (message?.type === "motor-lab-report") {
    const reportPayload = message.report || {};
    if (Number.isFinite(Number(reportPayload?.revision))) {
      workerState.lastAppliedRevision = Number(reportPayload.revision);
    }
    getConfig().then((config) => pushLog("motor_lab.report", {
      tabId: sender?.tab?.id || null,
      url: sender?.tab?.url || "",
      title: sender?.tab?.title || "",
      report: reportPayload,
    }, config));
    sendResponse({ ok: true });
    return true;
  }
  if (message?.type === "motor-lab-state") {
    getConfig().then((config) => pushLog("motor_lab.state", {
      tabId: sender?.tab?.id || null,
      url: sender?.tab?.url || "",
      state: message.state || {},
    }, config));
    sendResponse({ ok: true });
    return true;
  }
  if (message?.type === "motor-lab-get-worker-state") {
    sendResponse({ ok: true, state: workerState });
    return true;
  }
  return false;
});

getConfig().then(() => schedulePoll()).catch(console.error);
