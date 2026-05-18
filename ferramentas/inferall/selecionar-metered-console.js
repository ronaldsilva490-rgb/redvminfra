// Cole este bloco no Console do navegador estando logado em https://inferall.ai/billing.
// Ele usa o plano valido "metered" no lugar do botao quebrado "free".
(async () => {
  const plan = "metered";
  const target = new URL("/billing", window.location.origin);
  target.searchParams.set("plan", plan);

  if (!/inferall\.ai$/i.test(window.location.hostname)) {
    console.warn("[InferAll] Este script foi feito para rodar em inferall.ai.");
    console.warn("[InferAll] Host atual:", window.location.hostname);
  }

  console.log("[InferAll] Testando selecao do plano:", plan);
  console.log("[InferAll] URL:", target.toString());

  try {
    const response = await fetch(target.toString(), {
      method: "GET",
      credentials: "include",
      redirect: "follow",
      cache: "no-store",
      headers: {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
      }
    });

    const html = await response.text();
    console.log("[InferAll] HTTP:", response.status, response.url);

    if (response.status === 401 || response.status === 403) {
      console.error("[InferAll] Sessao nao autorizada. Faca login e rode de novo.");
      return;
    }

    if (/Unknown plan/i.test(html)) {
      const msg = html.match(/Unknown plan:[^<\n\r]+/i)?.[0] || "Unknown plan retornado pela pagina.";
      console.error("[InferAll]", msg);
      return;
    }

    console.log("[InferAll] Plano metered aceito. Recarregando a tela...");
    window.location.assign(target.toString());
  } catch (error) {
    console.error("[InferAll] Falha ao selecionar metered:", error);
    console.log("[InferAll] Tentando navegacao direta...");
    window.location.assign(target.toString());
  }
})();
