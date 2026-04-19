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

  async function wireAdminLogin() {
    const form = document.getElementById("admin-login-form");
    if (!form) return;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const fd = new FormData(form);
      try {
        const data = await postJson(path("/api/admin/login"), { password: fd.get("password") });
        window.location.href = data.redirect;
      } catch (error) {
        toast(error.message);
      }
    });
  }

  async function wireAdmin() {
    const statsWrap = document.getElementById("admin-stats");
    if (!statsWrap) return;
    const providerWrap = document.getElementById("provider-cards");
    const usersWrap = document.getElementById("users-list");
    const chargesWrap = document.getElementById("charges-admin-list");
    const clientSessionsWrap = document.getElementById("client-sessions-admin-list");
    const eventsWrap = document.getElementById("events-list");
    const logout = document.getElementById("admin-logout-button");

    function renderStats(stats) {
      statsWrap.innerHTML = `
        <article class="stats-card"><span class="label">Usuarios</span><strong>${stats.total_users}</strong></article>
        <article class="stats-card"><span class="label">Cobrancas abertas</span><strong>${stats.active_charges}</strong></article>
        <article class="stats-card"><span class="label">Saldo agregado</span><strong>${brl(stats.total_balance_cents)}</strong></article>
        <article class="stats-card"><span class="label">Creditos liquidados</span><strong>${stats.paid_charges}</strong></article>
      `;
    }

    function renderProviders(providers) {
      providerWrap.innerHTML = providers.map((provider) => `
        <form class="provider-card" data-provider="${provider.code}">
          <div class="row" style="justify-content:space-between">
            <div>
              <h3>${provider.display_name || provider.name}</h3>
              <div class="provider-meta">
                <span class="pill ${provider.enabled ? 'ok' : 'warn'}">${provider.enabled ? 'Ativo' : 'Inativo'}</span>
                <span class="pill">${provider.supported_methods.join(", ")}</span>
                <span class="pill">${provider.implemented ? 'Adapter pronto' : 'Adapter base'}</span>
              </div>
            </div>
          </div>
          <label>Nome exibido
            <input type="text" name="display_name" value="${provider.display_name || provider.name}">
          </label>
          <label style="margin-top:10px">
            <input type="checkbox" name="enabled" ${provider.enabled ? "checked" : ""}> Ativar provider
          </label>
          ${provider.config_fields.map((field) => {
            const value = provider.settings_redacted?.[field.name] ?? "";
            if (field.type === "textarea") {
              return `<label>${field.label}<textarea name="${field.name}" placeholder="${field.placeholder || ''}">${value || ""}</textarea></label>`;
            }
            if (field.type === "select") {
              return `<label>${field.label}<select name="${field.name}">${(field.options || []).map((option) => `<option value="${option}" ${value === option ? "selected" : ""}>${option}</option>`).join("")}</select></label>`;
            }
            if (field.type === "checkbox") {
              return `<label><input type="checkbox" name="${field.name}" ${value ? "checked" : ""}> ${field.label}</label>`;
            }
            return `<label>${field.label}<input type="${field.type === 'password' ? 'password' : 'text'}" name="${field.name}" value="${value || ""}" placeholder="${field.placeholder || ""}"></label>`;
          }).join("")}
          <p class="helper">Webhook esperado: <code>${provider.webhook_url}</code></p>
          ${provider.docs_url ? `<p class="helper"><a href="${provider.docs_url}" target="_blank" rel="noopener">Documentacao oficial</a></p>` : ""}
          <button class="btn btn-primary" type="submit">Salvar provider</button>
        </form>
      `).join("");
      providerWrap.querySelectorAll("form[data-provider]").forEach((form) => {
        form.addEventListener("submit", async (event) => {
          event.preventDefault();
          const fd = new FormData(form);
          const payload = {};
          for (const [key, value] of fd.entries()) {
            payload[key] = value;
          }
          form.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
            payload[checkbox.name] = checkbox.checked;
          });
          try {
            await postJson(path(`/api/admin/providers/${form.dataset.provider}`), payload);
            toast("Provider atualizado.");
            await load();
          } catch (error) {
            toast(error.message);
          }
        });
      });
    }

    function renderUsers(users) {
      usersWrap.innerHTML = users.map((user) => `
        <div class="list-item">
          <strong>${user.name}</strong>
          <small>${user.email}</small>
          <div class="row">
            <span class="pill">${brl(user.wallet.balance_cents)}</span>
            <span class="pill">${new Date(user.created_at * 1000).toLocaleString("pt-BR")}</span>
          </div>
        </div>
      `).join("");
    }

    function renderCharges(charges) {
      chargesWrap.innerHTML = charges.map((charge) => `
        <div class="list-item">
          <strong>${brl(charge.amount_cents)} • ${charge.status}</strong>
          <small>${charge.provider_code} • ${charge.id}</small>
          <div class="row">
            <button class="btn btn-ghost" type="button" data-charge-paid="${charge.id}">Marcar pago</button>
            <button class="btn btn-ghost" type="button" data-charge-expire="${charge.id}">Expirar</button>
          </div>
        </div>
      `).join("");
      chargesWrap.querySelectorAll("[data-charge-paid]").forEach((button) => {
        button.addEventListener("click", async () => {
          try {
            await postJson(path(`/api/admin/charges/${button.dataset.chargePaid}/mark-paid`), {});
            toast("Cobranca liquidada.");
            await load();
          } catch (error) {
            toast(error.message);
          }
        });
      });
      chargesWrap.querySelectorAll("[data-charge-expire]").forEach((button) => {
        button.addEventListener("click", async () => {
          try {
            await postJson(path(`/api/admin/charges/${button.dataset.chargeExpire}/expire`), {});
            toast("Cobranca expirada.");
            await load();
          } catch (error) {
            toast(error.message);
          }
        });
      });
    }

    function renderEvents(events) {
      eventsWrap.innerHTML = events.map((event) => `
        <div class="list-item">
          <strong>${event.kind}</strong>
          <small>${new Date(event.ts * 1000).toLocaleString("pt-BR")} • ${event.message}</small>
        </div>
      `).join("");
    }

    function renderClientSessions(items) {
      clientSessionsWrap.innerHTML = items.length
        ? items.map((item) => `
            <div class="list-item">
              <strong>${item.device_name || 'cliente-redsebia'} • ${item.status}</strong>
              <small>${item.exam_ref || 'sem exame'} • usuario ${item.user_id} • ultimo sinal ${new Date(item.last_seen_at * 1000).toLocaleString("pt-BR")}</small>
            </div>
          `).join("")
        : `<div class="list-item"><strong>Nenhuma sessao do cliente ainda.</strong></div>`;
    }

    async function load() {
      const resp = await fetch(path("/api/admin/bootstrap"), { credentials: "same-origin" });
      if (resp.status === 401) {
        window.location.href = path("/admin/login");
        return;
      }
      const data = await resp.json();
      renderStats(data.stats);
      renderProviders(data.providers);
      renderUsers(data.users);
      renderCharges(data.charges);
      renderClientSessions(data.client_sessions || []);
      renderEvents(data.events);
    }

    logout.addEventListener("click", async () => {
      await postJson(path("/api/admin/logout"), {});
      window.location.href = path("/admin/login");
    });

    await load();
  }

  wireAdminLogin();
  wireAdmin();
})();
