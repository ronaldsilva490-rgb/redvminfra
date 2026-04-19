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
      throw new Error(data.error || "Falha na operação.");
    }
    return data;
  }

  function brl(cents) {
    return (Number(cents || 0) / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function providerLabel(code) {
    const map = {
      sandbox_pix: "PIX instantâneo",
      manual_pix: "PIX manual",
      asaas: "Asaas PIX",
      efi_pix: "Efí Bank PIX",
      mercadopago_pix: "Mercado Pago PIX",
      pagarme_pix: "Pagar.me PIX",
      pagseguro_pix: "PagBank / PagSeguro PIX",
    };
    return map[code] || code || "-";
  }

  function humanStatus(status) {
    const map = {
      pending: "Aguardando pagamento",
      paid: "Liquidado",
      expired: "Encerrado",
      confirmed: "Confirmado",
    };
    return map[status] || status || "-";
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
        <article class="stats-card"><span class="label">Usuários</span><strong>${stats.total_users}</strong></article>
        <article class="stats-card"><span class="label">Cobranças abertas</span><strong>${stats.active_charges}</strong></article>
        <article class="stats-card"><span class="label">Saldo agregado</span><strong>${brl(stats.total_balance_cents)}</strong></article>
        <article class="stats-card"><span class="label">Créditos liquidados</span><strong>${stats.paid_charges}</strong></article>
      `;
    }

    function renderProviders(providers) {
      providerWrap.innerHTML = providers.map((provider) => {
        const fields = [];
        const toggles = [
          `
            <label class="check-item">
              <input type="checkbox" name="enabled" ${provider.enabled ? "checked" : ""}>
              <span>
                <strong>Ativar método</strong>
                <small>Permite emissão de cobrança para clientes.</small>
              </span>
            </label>
          `,
        ];

        provider.config_fields.forEach((field) => {
          const value = provider.settings_redacted?.[field.name] ?? "";
          if (field.type === "checkbox") {
            toggles.push(`
              <label class="check-item">
                <input type="checkbox" name="${field.name}" ${value ? "checked" : ""}>
                <span>
                  <strong>${field.label}</strong>
                  <small>Configuração interna deste método.</small>
                </span>
              </label>
            `);
            return;
          }

          if (field.type === "textarea") {
            fields.push(`
              <label class="field-span-2">${field.label}
                <textarea name="${field.name}" placeholder="${field.placeholder || ''}">${value || ""}</textarea>
              </label>
            `);
            return;
          }

          if (field.type === "select") {
            fields.push(`
              <label>${field.label}
                <select name="${field.name}">${(field.options || []).map((option) => `<option value="${option}" ${value === option ? "selected" : ""}>${option}</option>`).join("")}</select>
              </label>
            `);
            return;
          }

          fields.push(`
            <label>${field.label}
              <input type="${field.type === 'password' ? 'password' : 'text'}" name="${field.name}" value="${value || ""}" placeholder="${field.placeholder || ""}">
            </label>
          `);
        });

        return `
          <form class="provider-card" data-provider="${provider.code}">
            <div class="provider-card-head">
              <div>
                <h3>${provider.display_name || provider.name}</h3>
                <p class="provider-subtitle">Configuração operacional do método ${provider.supported_methods.join(", ")}.</p>
              </div>
              <div class="provider-meta">
                <span class="pill ${provider.enabled ? 'ok' : 'warn'}">${provider.enabled ? 'Ativo' : 'Inativo'}</span>
                <span class="pill">${provider.supported_methods.join(", ")}</span>
                <span class="pill">${provider.implemented ? 'Integração pronta' : 'Credencial preparada'}</span>
              </div>
            </div>

            <div class="provider-form-grid">
              <label class="field-span-2">Nome exibido
                <input type="text" name="display_name" value="${provider.display_name || provider.name}">
              </label>
              ${fields.join("")}
            </div>

            <div class="provider-switches">
              ${toggles.join("")}
            </div>

            <div class="provider-footer">
              <div class="provider-links">
                <div class="helper">
                  <span class="label">Webhook</span>
                  <code class="mono-link">${provider.webhook_url}</code>
                </div>
                ${provider.docs_url ? `<a class="helper provider-doc-link" href="${provider.docs_url}" target="_blank" rel="noopener">Abrir documentação oficial</a>` : ""}
              </div>
              <button class="btn btn-primary" type="submit">Salvar configuração</button>
            </div>
          </form>
        `;
      }).join("");
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
            toast("Configuração salva.");
            await load();
          } catch (error) {
            toast(error.message);
          }
        });
      });
    }

    function renderUsers(users) {
      usersWrap.innerHTML = users.length
        ? users.map((user) => `
            <div class="list-item">
              <strong>${user.name}</strong>
              <small>${user.email}</small>
              <div class="row">
                <span class="pill">Saldo disponível ${brl(user.wallet.balance_cents)}</span>
                <span class="pill">${new Date(user.created_at * 1000).toLocaleString("pt-BR")}</span>
              </div>
            </div>
          `).join("")
        : `<div class="list-item empty-state"><strong>Nenhum cliente recente.</strong><small>As novas contas aparecem aqui assim que forem criadas.</small></div>`;
    }

    function renderCharges(charges) {
      chargesWrap.innerHTML = charges.length
        ? charges.map((charge) => `
            <div class="list-item">
              <strong>${brl(charge.amount_cents)} • ${humanStatus(charge.status)}</strong>
              <small>${providerLabel(charge.provider_code)} • referência ${charge.id}</small>
              <div class="row">
                <button class="btn btn-ghost" type="button" data-charge-paid="${charge.id}">Marcar como pago</button>
                <button class="btn btn-ghost" type="button" data-charge-expire="${charge.id}">Encerrar cobrança</button>
              </div>
            </div>
          `).join("")
        : `<div class="list-item empty-state"><strong>Nenhuma cobrança recente.</strong><small>As cobranças emitidas pela plataforma aparecem aqui com status e ação rápida.</small></div>`;
      chargesWrap.querySelectorAll("[data-charge-paid]").forEach((button) => {
        button.addEventListener("click", async () => {
          try {
            await postJson(path(`/api/admin/charges/${button.dataset.chargePaid}/mark-paid`), {});
            toast("Cobrança liquidada.");
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
            toast("Cobrança encerrada.");
            await load();
          } catch (error) {
            toast(error.message);
          }
        });
      });
    }

    function renderEvents(events) {
      eventsWrap.innerHTML = events.length
        ? events.map((event) => `
            <div class="list-item">
              <strong>${event.kind}</strong>
              <small>${new Date(event.ts * 1000).toLocaleString("pt-BR")} • ${event.message}</small>
            </div>
          `).join("")
        : `<div class="list-item empty-state"><strong>Nenhum evento recente.</strong><small>Os registros operacionais aparecem aqui conforme a plataforma recebe atividade.</small></div>`;
    }

    function renderClientSessions(items) {
      clientSessionsWrap.innerHTML = items.length
        ? items.map((item) => `
            <div class="list-item">
              <strong>${item.device_name || 'Aplicativo REDSEBIA'} • ${item.status}</strong>
              <small>${item.exam_ref || 'sem referência vinculada'} • usuário ${item.user_id} • último sinal ${new Date(item.last_seen_at * 1000).toLocaleString("pt-BR")}</small>
            </div>
          `).join("")
        : `<div class="list-item empty-state"><strong>Nenhuma sessão ativa no momento.</strong><small>Os dispositivos autorizados aparecem aqui assim que o aplicativo iniciar comunicação com o backend.</small></div>`;
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
