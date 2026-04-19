(function () {
  const body = document.body;
  const base = body.dataset.basePath || "";

  function path(suffix) {
    return `${base}${suffix}`;
  }

  function toast(message, timeout = 3200) {
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = message;
    el.classList.remove("hidden");
    window.clearTimeout(el._timer);
    el._timer = window.setTimeout(() => el.classList.add("hidden"), timeout);
  }

  async function postJson(url, payload) {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok || data.ok === false) {
      throw new Error(data.error || "Falha na operacao.");
    }
    return data;
  }

  function brl(cents) {
    return (Number(cents || 0) / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function humanStatus(status) {
    const map = {
      pending: "Pendente",
      paid: "Pago",
      expired: "Expirado",
      confirmed: "Confirmado",
    };
    return map[status] || status || "-";
  }

  async function wireLogin() {
    const form = document.getElementById("login-form");
    if (!form) return;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const fd = new FormData(form);
      try {
        const data = await postJson(path("/api/login"), {
          email: fd.get("email"),
          password: fd.get("password"),
        });
        const nextPath = form.dataset.next || data.redirect;
        window.location.href = nextPath ? `${base}${nextPath}`.replace(`${base}${base}`, base) : data.redirect;
      } catch (error) {
        toast(error.message);
      }
    });
  }

  async function wireRegister() {
    const form = document.getElementById("register-form");
    if (!form) return;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const fd = new FormData(form);
      try {
        const data = await postJson(path("/api/register"), {
          name: fd.get("name"),
          cpf: fd.get("cpf"),
          email: fd.get("email"),
          password: fd.get("password"),
        });
        window.location.href = data.redirect;
      } catch (error) {
        toast(error.message);
      }
    });
  }

  async function wirePortal() {
    const userName = document.getElementById("user-name");
    if (!userName) return;
    const providerSelect = document.getElementById("provider-select");
    const topupForm = document.getElementById("topup-form");
    const logoutButton = document.getElementById("logout-button");
    const activeCharge = document.getElementById("active-charge");
    const chargesList = document.getElementById("charges-list");
    const ledgerList = document.getElementById("ledger-list");
    const clientSessionsList = document.getElementById("client-sessions-list");
    let latestBootstrap = null;
    let refreshTimer = null;

    function renderActiveCharge(charge) {
      if (!charge) {
        activeCharge.classList.add("hidden");
        activeCharge.innerHTML = "";
        return;
      }
      const canSandbox = charge.provider_code === "sandbox_pix" && charge.status !== "paid";
      activeCharge.innerHTML = `
        <div class="charge-grid">
          <div>
            ${charge.qr_code_base64 ? `<img src="${charge.qr_code_base64}" alt="QR code">` : ""}
          </div>
          <div class="list-stack">
            <div class="list-item">
              <strong>${humanStatus(charge.status)} • ${brl(charge.amount_cents)}</strong>
              <small>Provider: ${charge.provider_code} | ID: ${charge.id}</small>
              ${charge.qr_code ? `<label>Copia e cola<textarea readonly>${charge.qr_code}</textarea></label>` : ""}
              ${charge.payment_url ? `<a class="btn btn-ghost" href="${charge.payment_url}" target="_blank" rel="noopener">Abrir boleto/link</a>` : ""}
              <div class="row">
                <button class="btn btn-ghost" data-refresh-charge="${charge.id}" type="button">Atualizar status</button>
                ${canSandbox ? `<button class="btn btn-primary" data-sandbox-charge="${charge.id}" type="button">Simular pagamento</button>` : ""}
              </div>
            </div>
          </div>
        </div>
      `;
      activeCharge.classList.remove("hidden");
      activeCharge.querySelectorAll("[data-refresh-charge]").forEach((button) => {
        button.addEventListener("click", () => refreshCharge(button.dataset.refreshCharge));
      });
      activeCharge.querySelectorAll("[data-sandbox-charge]").forEach((button) => {
        button.addEventListener("click", () => sandboxConfirm(button.dataset.sandboxCharge));
      });
    }

    function renderCharges(charges) {
      chargesList.innerHTML = charges.length
        ? charges.map((charge) => `
            <div class="list-item">
              <strong>${brl(charge.amount_cents)} • ${humanStatus(charge.status)}</strong>
              <small>${charge.provider_code} • ${new Date(charge.created_at * 1000).toLocaleString("pt-BR")}</small>
            </div>
          `).join("")
        : `<div class="list-item"><strong>Nenhuma cobranca ainda.</strong><small>Assim que voce gerar um PIX, ele aparece aqui.</small></div>`;
    }

    function renderLedger(entries) {
      ledgerList.innerHTML = entries.length
        ? entries.map((entry) => `
            <div class="list-item">
              <strong>${entry.direction === "credit" ? "+" : "-"} ${brl(entry.amount_cents)}</strong>
              <small>${entry.description || entry.kind} • ${new Date(entry.created_at * 1000).toLocaleString("pt-BR")}</small>
            </div>
          `).join("")
        : `<div class="list-item"><strong>Sem movimentacoes.</strong><small>Creditos e debitos vao aparecer aqui.</small></div>`;
    }

    function renderClientSessions(items) {
      clientSessionsList.innerHTML = items.length
        ? items.map((item) => `
            <div class="list-item">
              <strong>${item.device_name || 'cliente-redsebia'} • ${item.status}</strong>
              <small>${item.exam_ref || 'sem exame vinculado'} • ultimo sinal ${new Date(item.last_seen_at * 1000).toLocaleString("pt-BR")}</small>
            </div>
          `).join("")
        : `<div class="list-item"><strong>Nenhuma sessao ainda.</strong><small>Quando o novo cliente conversar com o backend, ela aparece aqui.</small></div>`;
    }

    function renderBootstrap(data) {
      latestBootstrap = data;
      userName.textContent = data.user.name;
      document.getElementById("user-email").textContent = data.user.email;
      document.getElementById("wallet-balance").textContent = `Saldo: ${brl(data.wallet.balance_cents)}`;
      providerSelect.innerHTML = data.providers.length
        ? data.providers.map((provider) => `<option value="${provider.code}">${provider.name}</option>`).join("")
        : `<option value="">Nenhum provider ativo</option>`;
      renderCharges(data.charges);
      renderLedger(data.ledger);
      renderClientSessions(data.client_sessions || []);
      const pending = data.charges.find((item) => item.status === "pending");
      renderActiveCharge(pending || data.charges[0] || null);
      window.clearTimeout(refreshTimer);
      if (pending) {
        refreshTimer = window.setTimeout(loadBootstrap, 5000);
      }
    }

    async function loadBootstrap() {
      const resp = await fetch(path("/api/bootstrap"), { credentials: "same-origin" });
      if (resp.status === 401) {
        window.location.href = path("/login");
        return;
      }
      renderBootstrap(await resp.json());
    }

    async function refreshCharge(chargeId) {
      try {
        await postJson(path(`/api/topups/${chargeId}/refresh`), {});
        await loadBootstrap();
      } catch (error) {
        toast(error.message);
      }
    }

    async function sandboxConfirm(chargeId) {
      try {
        await postJson(path(`/api/topups/${chargeId}/sandbox/confirm`), {});
        toast("Pagamento sandbox confirmado.");
        await loadBootstrap();
      } catch (error) {
        toast(error.message);
      }
    }

    topupForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const fd = new FormData(topupForm);
      try {
        await postJson(path("/api/topups"), {
          provider_code: fd.get("provider_code"),
          amount_brl: fd.get("amount_brl"),
        });
        toast("Cobranca criada.");
        await loadBootstrap();
      } catch (error) {
        toast(error.message);
      }
    });

    logoutButton.addEventListener("click", async () => {
      await postJson(path("/api/logout"), {});
      window.location.href = path("/login");
    });

    await loadBootstrap();
  }

  async function wireDevice() {
    const panel = document.getElementById("device-panel");
    if (!panel) return;
    const userCode = panel.dataset.userCode;
    const approve = document.getElementById("device-approve");
    const deny = document.getElementById("device-deny");
    if (approve) {
      approve.addEventListener("click", async () => {
        try {
          await postJson(path("/api/device/approve"), { user_code: userCode });
          toast("Dispositivo aprovado.");
        } catch (error) {
          toast(error.message);
        }
      });
    }
    if (deny) {
      deny.addEventListener("click", async () => {
        try {
          await postJson(path("/api/device/deny"), { user_code: userCode });
          toast("Dispositivo negado.");
        } catch (error) {
          toast(error.message);
        }
      });
    }
  }

  wireLogin();
  wireRegister();
  wirePortal();
  wireDevice();
})();
