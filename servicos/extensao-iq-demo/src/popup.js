async function getConfig() {
  const response = await chrome.runtime.sendMessage({ type: "rediq:get-config" });
  return response?.config || {};
}

async function getState() {
  const response = await chrome.runtime.sendMessage({ type: "rediq:get-state" });
  return response || {};
}

async function setConfig(patch) {
  return chrome.runtime.sendMessage({ type: "rediq:set-config", patch });
}

function setText(id, value, className = "") {
  const element = document.getElementById(id);
  if (!element) return;
  element.textContent = value;
  element.className = `value ${className}`.trim();
}

async function refresh() {
  const [config, stateEnvelope] = await Promise.all([getConfig(), getState()]);
  const snapshot = stateEnvelope?.snapshot || null;
  const bridgeState = stateEnvelope?.bridgeState || null;
  document.getElementById("sample-interval").value = String(config.sampleIntervalMs || 250);
  document.getElementById("toggle-enabled").textContent = config.enabled ? "Pausar overlay" : "Ativar overlay";
  const bridgeStatus = document.getElementById("bridge-status");
  const bridgeDetail = document.getElementById("bridge-detail");

  if (bridgeState?.lastSuccessAt) {
    bridgeStatus.textContent = "Conectado";
    bridgeStatus.className = "value ok";
    const date = new Date(bridgeState.lastSuccessAt);
    bridgeDetail.textContent = `Último envio: ${date.toLocaleTimeString()}`;
  } else if (bridgeState?.lastError) {
    bridgeStatus.textContent = "Com falha";
    bridgeStatus.className = "value warn";
    bridgeDetail.textContent = bridgeState.lastError;
  } else {
    bridgeStatus.textContent = "Aguardando";
    bridgeStatus.className = "value";
    bridgeDetail.textContent = "Sem telemetria enviada ainda.";
  }

  if (!snapshot?.state) {
    setText("mode", "Sem leitura ainda");
    setText("asset", "-");
    setText("market", "-");
    setText("price", "-");
    document.getElementById("hint").textContent = "Abra a IQ com o gráfico visível para a extensão começar a ler.";
    return;
  }

  const state = snapshot.state;
  setText("mode", state.mode === "demo" ? "DEMO" : (state.mode || "-").toUpperCase(), state.mode === "demo" ? "ok" : "warn");
  setText("asset", state.asset || "-");
  setText("market", state.marketType || "-");
  setText("price", Number.isFinite(state.currentPrice) ? state.currentPrice.toFixed(6) : "-");
  const debug = state.debug || {};
  const tail = [];
  if (debug.textNodeCount != null) tail.push(`textos: ${debug.textNodeCount}`);
  if (debug.priceCandidate?.text) tail.push(`preço: ${debug.priceCandidate.text}`);
  document.getElementById("hint").textContent = `${state.entryHint || "Sem hint no momento."}${tail.length ? ` · ${tail.join(" · ")}` : ""}`;
}

document.getElementById("sample-interval").addEventListener("change", async (event) => {
  await setConfig({ sampleIntervalMs: Number(event.target.value) || 250 });
  await refresh();
});

document.getElementById("toggle-enabled").addEventListener("click", async () => {
  const config = await getConfig();
  await setConfig({ enabled: !config.enabled });
  await refresh();
});

refresh().catch(console.error);
