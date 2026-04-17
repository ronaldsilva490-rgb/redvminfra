const ENGINE = {
  item: null,
  appliedRevision: -1,
  seenActions: new Set(),
  stateTimer: 0,
  pollTimer: 0,
  lastFetchAt: 0,
  lastFetchError: "",
  bridgeSeq: 0,
  bridgePending: Object.create(null),
};

const DEFAULT_REMOTE = {
  bridgeUrl: "http://redsystems.ddns.net/iq-bridge",
  bridgeToken: "",
  channel: "spy",
  pollMs: 1000,
};

function now() {
  return Date.now();
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function injectBridge() {
  if (document.documentElement?.dataset?.redIqLabBridge === "1") return;
  const script = document.createElement("script");
  script.src = chrome.runtime.getURL("src/injected-bridge.js");
  script.async = false;
  script.onload = () => script.remove();
  (document.documentElement || document.head || document.body).appendChild(script);
  if (document.documentElement) {
    document.documentElement.dataset.redIqLabBridge = "1";
  }
}

function visibleTextSample(limit = 20) {
  const texts = [];
  const seen = new Set();
  const skipParents = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "IFRAME"]);
  const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    const parent = node?.parentElement;
    if (!parent || skipParents.has(parent.tagName)) continue;
    const style = window.getComputedStyle(parent);
    if (!style || style.display === "none" || style.visibility === "hidden" || Number(style.opacity || 1) === 0) continue;
    const rect = parent.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) continue;
    if (rect.bottom < 0 || rect.right < 0 || rect.top > window.innerHeight || rect.left > window.innerWidth) continue;
    const value = String(node?.nodeValue || "").replace(/\s+/g, " ").trim();
    if (!value) continue;
    if (value.length > 180) continue;
    if (/^!function|^function |https?:\/\/|sdkid=|googletagmanager|appsflyer|analytics|kwaiq|snaptr|ym\(/i.test(value)) continue;
    if (seen.has(value)) continue;
    seen.add(value);
    texts.push(value);
    if (texts.length >= limit) break;
  }
  return texts;
}

function summaryState() {
  return {
    ts: now(),
    href: location.href,
    title: document.title,
    viewport: {
      width: window.innerWidth,
      height: window.innerHeight,
      dpr: window.devicePixelRatio || 1,
    },
    topText: visibleTextSample(15),
  };
}

async function report(type, payload) {
  try {
    await chrome.runtime.sendMessage({
      type: "motor-lab-push-log",
      event: type === "motor-lab-state" ? "motor_lab.state" : "motor_lab.report",
      payload: {
        tabId: null,
        url: location.href,
        title: document.title,
        [type === "motor-lab-state" ? "state" : "report"]: payload,
      },
    });
  } catch (_) {
    // ignored
  }
  try {
    await chrome.runtime.sendMessage({
      type,
      [type === "motor-lab-state" ? "state" : "report"]: payload,
    });
  } catch (_) {
    // ignored
  }
}

function pointTarget(x, y) {
  const el = document.elementFromPoint(Number(x), Number(y));
  if (!el) return null;
  return {
    tag: el.tagName,
    id: el.id || "",
    className: String(el.className || ""),
    text: String(el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 120),
  };
}

function currentRequestId() {
  return String(Math.floor(now() % 1000000000));
}

function buildIqSendMessage(name, body = {}, version = "1.0") {
  const requestId = currentRequestId();
  return {
    requestId,
    message: {
      name: "sendMessage",
      request_id: requestId,
      local_time: Math.round(performance.now()),
      msg: {
        name,
        version,
        body,
      },
    },
  };
}

function defaultPlotter(activeId, activeType, isMinimized) {
  return {
    activeId: Number(activeId),
    activeType: String(activeType || "turbo"),
    isMinimized: !!isMinimized,
    plotType: "area",
    emptyCandles: false,
    candleDuration: 1,
    timeScale: 420.3904628753662,
    indicators: "{\"indicators\":[]}",
    scriptedIndicators: "{\"scripted_indicators\":[]}",
    stackPanelSizes: [100.0],
    lineColor: "B72411FF",
    lineWidth: 1.0,
    candleColorUp: "",
    candleColorDown: "",
    emptyHACandles: false,
    candleHAColorUp: "",
    candleHAColorDown: "",
    chartPriceType: "mid",
  };
}

function buildNativeSelectAssetMessages(targetActiveId, currentActiveId, activeType = "turbo") {
  const targetId = Number(targetActiveId);
  const currentId = Number(currentActiveId);
  const clientId = `${Date.now()}000`;
  const gridConfig = {
    name: "default",
    gridSchemeName: "default_1_1",
    gridSchemeRows: [100.0],
    gridSchemeColumns: [100.0],
    fixedNumberOfPlotters: 1,
    plotters: [
      defaultPlotter(currentId, activeType, true),
      defaultPlotter(targetId, activeType, false),
    ],
  };
  const availability = buildIqSendMessage("update-user-availability", {
    platform_id: "9",
    idle_duration: 44,
    selected_asset_id: targetId,
    selected_asset_type: 3,
  }, "1.1");
  const grid = buildIqSendMessage("set-user-settings", {
    name: "traderoom_gl_grid",
    version: 2,
    client_id: clientId,
    config: gridConfig,
  }, "1.0");
  const candles = buildIqSendMessage("get-candles", {
    active_id: targetId,
    size: 1,
    from_id: 0,
    to_id: 0,
    split_normalization: true,
    only_closed: true,
  }, "2.0");
  return [availability, grid, candles];
}

function sendBridgeCommand(command, payload = {}, timeoutMs = 2500) {
  const id = `lab_${now()}_${++ENGINE.bridgeSeq}`;
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => {
      delete ENGINE.bridgePending[id];
      resolve({ ok: false, error: "bridge_command_timeout", id, command });
    }, timeoutMs);
    ENGINE.bridgePending[id] = { resolve, timer };
    window.postMessage({
      source: "RED_IQ_LAB_BRIDGE",
      kind: "command",
      payload: { id, command, payload },
    }, "*");
  });
}

function clickAt(x, y) {
  const target = document.elementFromPoint(Number(x), Number(y));
  if (!target) return { ok: false, error: "no_target", x, y };
  const options = { bubbles: true, cancelable: true, clientX: Number(x), clientY: Number(y), composed: true };
  target.dispatchEvent(new PointerEvent("pointerdown", options));
  target.dispatchEvent(new MouseEvent("mousedown", options));
  target.dispatchEvent(new PointerEvent("pointerup", options));
  target.dispatchEvent(new MouseEvent("mouseup", options));
  target.dispatchEvent(new MouseEvent("click", options));
  return { ok: true, x, y, target: pointTarget(x, y) };
}

function clickSelector(selector) {
  const el = document.querySelector(String(selector || ""));
  if (!el) return { ok: false, error: "selector_not_found", selector };
  el.click();
  return {
    ok: true,
    selector,
    target: {
      tag: el.tagName,
      id: el.id || "",
      className: String(el.className || ""),
      text: String(el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 120),
    },
  };
}

function clickText(text) {
  const needle = String(text || "").trim().toLowerCase();
  if (!needle) return { ok: false, error: "empty_text" };
  const all = Array.from(document.querySelectorAll("body *"));
  const match = all.find((el) => String(el.textContent || "").replace(/\s+/g, " ").trim().toLowerCase().includes(needle));
  if (!match) return { ok: false, error: "text_not_found", text };
  match.click();
  return {
    ok: true,
    text,
    target: {
      tag: match.tagName,
      id: match.id || "",
      className: String(match.className || ""),
      text: String(match.textContent || "").replace(/\s+/g, " ").trim().slice(0, 120),
    },
  };
}

function evalJs(code) {
  try {
    // Intencionalmente voltado para laboratorio local de desenvolvimento.
    const value = Function(`"use strict"; return (${code});`)();
    return { ok: true, value };
  } catch (error) {
    try {
      const value = Function(String(code))();
      return { ok: true, value };
    } catch (error2) {
      return { ok: false, error: String(error2 || error) };
    }
  }
}

async function executeAction(action) {
  const type = String(action?.type || "").trim();
  if (!type) return { ok: false, error: "missing_type" };
  if (type === "sleep") {
    await sleep(Number(action.ms || 0));
    return { ok: true, sleptMs: Number(action.ms || 0) };
  }
  if (type === "report_state") {
    return { ok: true, state: summaryState() };
  }
  if (type === "elements_at_point") {
    const x = Number(action.x || 0);
    const y = Number(action.y || 0);
    const elements = (document.elementsFromPoint?.(x, y) || []).slice(0, 12).map((el) => ({
      tag: el.tagName,
      id: el.id || "",
      className: String(el.className || ""),
      text: String(el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 120),
    }));
    return { ok: true, x, y, elements };
  }
  if (type === "click_point") return clickAt(action.x, action.y);
  if (type === "click_selector") return clickSelector(action.selector);
  if (type === "click_text") return clickText(action.text);
  if (type === "eval_js") return evalJs(action.code);
  if (type === "native_ws_send") {
    return sendBridgeCommand("ws-send", { text: String(action.text || "") }, Number(action.timeoutMs || 2500));
  }
  if (type === "main_eval") {
    return sendBridgeCommand("eval-main", { code: String(action.code || "") }, Number(action.timeoutMs || 3000));
  }
  if (type === "native_select_asset") {
    const targetActiveId = Number(action.targetActiveId || action.activeId);
    const currentActiveId = Number(action.currentActiveId);
    if (!Number.isFinite(targetActiveId) || !Number.isFinite(currentActiveId)) {
      return { ok: false, error: "native_select_requires_current_and_target" };
    }
    const packets = buildNativeSelectAssetMessages(targetActiveId, currentActiveId, String(action.activeType || "turbo"));
    const results = [];
    for (const packet of packets) {
      const sent = await sendBridgeCommand("ws-send", { text: JSON.stringify(packet.message) }, Number(action.timeoutMs || 2500));
      results.push({
        requestId: packet.requestId,
        message: packet.message?.msg?.name || "",
        ok: !!sent?.ok,
        sent,
      });
      await sleep(120);
    }
    return { ok: results.some((item) => item.ok), targetActiveId, currentActiveId, results };
  }
  return { ok: false, error: "unknown_action", type };
}

async function getRemoteSettings() {
  try {
    const stored = await chrome.storage.local.get("motorLabConfig");
    return { ...DEFAULT_REMOTE, ...(stored.motorLabConfig || {}) };
  } catch (_) {
    return { ...DEFAULT_REMOTE };
  }
}

async function applyConfig(item) {
  ENGINE.item = item;
  const revision = Number(item?.revision || 0);
  const config = item?.config || {};
  if (ENGINE.appliedRevision !== revision) {
    ENGINE.appliedRevision = revision;
    if (Array.isArray(config.actions)) {
      for (const action of config.actions) {
        const id = String(action?.id || `${revision}:${action?.type || "action"}`);
        if (action?.once !== false && ENGINE.seenActions.has(id)) continue;
        const result = await executeAction(action);
        if (action?.once !== false) ENGINE.seenActions.add(id);
        await report("motor-lab-report", {
          ts: now(),
          revision,
          action: {
            id,
            type: action?.type || "",
          },
          result,
        });
      }
    }
    await report("motor-lab-report", {
      ts: now(),
      revision,
      action: {
        id: `config-applied:${revision}`,
        type: "config_applied",
      },
      result: {
        ok: true,
        href: location.href,
        title: document.title,
      },
    });
  }
  if (ENGINE.stateTimer) clearTimeout(ENGINE.stateTimer);
  if (config.reportState !== false) {
    const tick = async () => {
      await report("motor-lab-state", summaryState());
      ENGINE.stateTimer = setTimeout(tick, Number(config.stateIntervalMs || 1500));
    };
    ENGINE.stateTimer = setTimeout(tick, 60);
  }
}

async function fetchRemoteConfigDirect() {
  try {
    const result = await chrome.runtime.sendMessage({
      type: "motor-lab-fetch-config",
    });
    if (!result?.ok) {
      throw new Error(result?.error || "motor_lab_fetch_failed");
    }
    ENGINE.lastFetchAt = now();
    ENGINE.lastFetchError = "";
    await applyConfig(result?.item || {});
  } catch (error) {
    ENGINE.lastFetchError = String(error);
    await report("motor-lab-report", {
      ts: now(),
      revision: ENGINE.appliedRevision,
      action: {
        id: `fetch-error:${now()}`,
        type: "config_fetch_error",
      },
      result: {
        ok: false,
        error: String(error),
      },
    });
  }
}

async function startRemoteLoop() {
  if (ENGINE.pollTimer) clearTimeout(ENGINE.pollTimer);
  const settings = await getRemoteSettings();
  const run = async () => {
    await fetchRemoteConfigDirect();
    ENGINE.pollTimer = setTimeout(run, Math.max(500, Number(settings.pollMs || DEFAULT_REMOTE.pollMs)));
  };
  ENGINE.pollTimer = setTimeout(run, 120);
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "motor-lab-config") {
    applyConfig(message.item || {}).then(() => sendResponse({ ok: true })).catch((error) => {
      sendResponse({ ok: false, error: String(error) });
    });
    return true;
  }
  if (message?.type === "motor-lab-ping") {
    sendResponse({ ok: true, state: summaryState(), revision: ENGINE.appliedRevision });
    return true;
  }
  return false;
});

window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  const data = event.data;
  if (!data || data.source !== "RED_IQ_LAB_BRIDGE") return;
  if (data.kind === "command-result") {
    const payload = data.payload || {};
    const pending = ENGINE.bridgePending[payload.id];
    if (!pending) return;
    window.clearTimeout(pending.timer);
    delete ENGINE.bridgePending[payload.id];
    pending.resolve({
      ok: !!payload.ok,
      command: payload.command || "",
      result: payload.result || {},
      error: payload.error || "",
    });
  }
});

injectBridge();
report("motor-lab-state", summaryState()).catch(() => {});
startRemoteLoop().catch(() => {});
