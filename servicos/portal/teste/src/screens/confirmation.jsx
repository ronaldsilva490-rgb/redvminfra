// STADIA — Order confirmation screen

function Confirmation({ go, route, orders }) {
  const order = orders.find((o) => o.id === route.id) || orders[0];
  const { BRL } = window.STADIA_UI;
  const { PRODUCTS } = window.STADIA_DATA;

  const [copied, setCopied] = React.useState(false);

  if (!order) {
    return (
      <main className="confirm-main">
        <div className="container" style={{ padding: 80, textAlign: "center" }}>
          <h2>Nenhum pedido encontrado.</h2>
          <button className="btn" onClick={() => go("home")}>Voltar para a Home</button>
        </div>
      </main>
    );
  }

  const items = order.items.map((i) => ({ ...i, p: PRODUCTS.find((x) => x.id === i.id) || i.p })).filter(i => i.p);
  const eta = new Date(Date.now() + (order.shipMethod === "same-day" ? 1 : order.shipMethod === "express" ? 2 : 5) * 24 * 60 * 60 * 1000);
  const etaStr = eta.toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" });

  const copyId = () => {
    navigator.clipboard?.writeText(order.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <main className="confirm-main">
      <ConfettiBg/>

      <div className="container">
        <div className="confirm-hero">
          <div className="confirm-check">
            <svg viewBox="0 0 64 64" width="64" height="64">
              <circle cx="32" cy="32" r="28" fill="none" stroke="currentColor" strokeWidth="2" className="check-circle"/>
              <path d="M20 33l9 9 16-18" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="check-path"/>
            </svg>
          </div>
          <span className="eyebrow" style={{ color: "var(--accent-3)" }}>PEDIDO CONFIRMADO</span>
          <h1 className="display">Boa partida.<br/>Seu pedido está em jogo.</h1>
          <p style={{ color: "var(--muted)", maxWidth: 540, margin: 0 }}>
            Enviamos os detalhes para seu email. Você pode acompanhar tudo na área <button className="link" onClick={() => go("account", { tab: "orders" })}>Meus pedidos</button>.
          </p>

          <div className="confirm-id-card">
            <div>
              <span className="mono small" style={{ color: "var(--muted)" }}>NÚMERO DO PEDIDO</span>
              <h3 className="display">{order.id}</h3>
            </div>
            <button className="btn outline sm" onClick={copyId}>
              {copied ? <><Icon name="check" size={14}/> Copiado</> : <>Copiar</>}
            </button>
          </div>
        </div>

        <div className="confirm-grid">
          <section className="confirm-main-col">
            {/* TIMELINE */}
            <div className="card-block">
              <h3 className="card-title">Linha do tempo</h3>
              <div className="timeline">
                {[
                  { l: "Pedido recebido", s: "Confirmamos seu pedido", t: "agora", on: true },
                  { l: "Pagamento aprovado", s: "Liberado para preparo", t: "em alguns minutos", on: true },
                  { l: "Em separação", s: "Seus itens sendo preparados", t: "até 12h" },
                  { l: "A caminho", s: "Pedido despachado", t: "em até 24h" },
                  { l: "Entregue", s: `Previsto para ${etaStr}`, t: "" },
                ].map((s, i) => (
                  <div key={i} className={"tl-step " + (s.on ? "done" : "")}>
                    <span className="tl-dot"/>
                    <div>
                      <h5>{s.l}</h5>
                      <span className="mono small" style={{ color: "var(--muted)" }}>{s.s}{s.t && " · " + s.t.toUpperCase()}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* ITEMS */}
            <div className="card-block">
              <h3 className="card-title">Itens ({items.length})</h3>
              <div className="confirm-items">
                {items.map((i, idx) => (
                  <div key={idx} className="confirm-item">
                    <div className="ci-thumb img-ph has-viz" style={{ background: i.p.imageBg }}>
                      <STADIA_PRODUCT_VISUAL p={i.p}/>
                    </div>
                    <div className="ci-info">
                      <span className="mono small" style={{ color: "var(--muted)" }}>{i.p.sub}</span>
                      <h5>{i.p.name}</h5>
                      <span className="mono small">{i.color || i.p.colors?.[0]?.name} · {i.size || i.p.sizes?.[0]} · QTD {i.qty}</span>
                    </div>
                    <span className="mono">{BRL(i.p.price * i.qty)}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <aside className="confirm-side">
            <div className="card-block sticky">
              <h3 className="card-title">Resumo</h3>
              {order.address && (
                <div className="info-row">
                  <Icon name="pin" size={16}/>
                  <div>
                    <span className="mono small" style={{ color: "var(--muted)" }}>ENTREGA EM</span>
                    <p style={{ margin: "2px 0 0" }}>{order.address.street}<br/>{order.address.district} · {order.address.city}/{order.address.state}</p>
                  </div>
                </div>
              )}
              <div className="info-row">
                <Icon name="truck" size={16}/>
                <div>
                  <span className="mono small" style={{ color: "var(--muted)" }}>PREVISÃO</span>
                  <p style={{ margin: "2px 0 0", textTransform: "capitalize" }}>{etaStr}</p>
                </div>
              </div>
              <div className="info-row">
                <Icon name={order.payMethod === "pix" ? "pix" : order.payMethod === "boleto" ? "boleto" : "card"} size={16}/>
                <div>
                  <span className="mono small" style={{ color: "var(--muted)" }}>PAGAMENTO</span>
                  <p style={{ margin: "2px 0 0", textTransform: "capitalize" }}>
                    {order.payMethod === "credit" ? "Cartão de crédito" : order.payMethod === "pix" ? "Pix" : "Boleto"}
                  </p>
                </div>
              </div>

              <div className="hr"/>
              <div className="row between"><span style={{ color: "var(--muted)" }}>Total</span><b className="display" style={{ fontSize: 28 }}>{BRL(order.total)}</b></div>

              <div className="row" style={{ gap: 8, marginTop: 16, flexDirection: "column" }}>
                <button className="btn block" onClick={() => go("account", { tab: "orders" })}>
                  Ver pedido <Icon name="arrow-right" size={14}/>
                </button>
                <button className="btn outline block" onClick={() => go("home")}>Continuar comprando</button>
              </div>

              <div className="confirm-support">
                <Icon name="headset" size={16}/>
                <span>Dúvidas? Fale com a gente <span style={{ color: "var(--accent)" }}>24/7</span>.</span>
              </div>
            </div>
          </aside>
        </div>

        {/* Recommendations */}
        <section style={{ marginTop: 64, paddingTop: 48, borderTop: "1px solid var(--line)" }}>
          <h3 className="display" style={{ fontSize: 28, margin: "0 0 24px" }}>Você também pode curtir</h3>
          <div className="confirm-recs">
            {PRODUCTS.slice(2, 6).map((p) => {
              const ProductCard = window.STADIA_PRODUCT_CARD;
              return <ProductCard key={p.id} product={p} go={go} wishlist={[]} toggleWish={() => {}} addToCart={() => {}}/>;
            })}
          </div>
        </section>
      </div>
      <ConfirmStyles/>
    </main>
  );
}

function ConfettiBg() {
  return (
    <div className="confetti-bg" aria-hidden>
      {Array.from({ length: 24 }).map((_, i) => (
        <span key={i} style={{
          left: (i * 4.3) + "%",
          animationDelay: (i * 0.06) + "s",
          background: ["var(--accent)", "var(--accent-2)", "var(--accent-3)"][i % 3],
        }}/>
      ))}
    </div>
  );
}

function ConfirmStyles() {
  return (
    <style>{`
      .confirm-main { padding: 48px 0 80px; position: relative; overflow: hidden; }
      .confetti-bg { position: absolute; inset: 0 0 auto; height: 360px; pointer-events: none; overflow: hidden; }
      .confetti-bg span {
        position: absolute; top: -20px; width: 8px; height: 14px;
        animation: confetti 4s ease-out forwards;
        opacity: 0;
      }
      @keyframes confetti {
        0% { opacity: 0; transform: translateY(0) rotate(0deg); }
        10% { opacity: 1; }
        100% { opacity: 0; transform: translateY(420px) rotate(540deg); }
      }

      .confirm-hero {
        text-align: center;
        display: flex; flex-direction: column; align-items: center; gap: 12px;
        margin-bottom: 48px;
        position: relative; z-index: 1;
      }
      .confirm-check {
        width: 72px; height: 72px; border-radius: 50%;
        background: color-mix(in oklab, var(--accent-3) 14%, transparent);
        display: grid; place-items: center;
        color: var(--accent-3);
        margin-bottom: 8px;
      }
      .check-circle { stroke-dasharray: 176; stroke-dashoffset: 176; animation: draw 0.7s ease forwards; }
      .check-path { stroke-dasharray: 50; stroke-dashoffset: 50; animation: draw 0.4s ease 0.5s forwards; }
      @keyframes draw { to { stroke-dashoffset: 0; } }
      .confirm-hero h1 { margin: 0; font-size: clamp(36px, 4.5vw, 56px); letter-spacing: -0.04em; line-height: 1; }
      .confirm-id-card {
        display: flex; align-items: center; gap: 24px;
        padding: 16px 24px;
        background: var(--surface); border: 1px solid var(--line);
        border-radius: var(--r-md);
        margin-top: 16px;
      }
      .confirm-id-card h3 { margin: 0; font-size: 22px; letter-spacing: -0.02em; }

      .confirm-grid { display: grid; grid-template-columns: 1fr 360px; gap: 32px; align-items: start; }
      @media (max-width: 1000px) { .confirm-grid { grid-template-columns: 1fr; } }
      .confirm-main-col { display: flex; flex-direction: column; gap: 16px; }

      .card-block { background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-md); padding: 24px; }
      .card-title { font-family: var(--font-display); font-size: 18px; font-weight: 700; margin: 0 0 16px; }
      .sticky { position: sticky; top: 16px; }

      .timeline { display: flex; flex-direction: column; gap: 4px; padding-left: 8px; position: relative; }
      .timeline::before { content: ""; position: absolute; left: 14px; top: 12px; bottom: 12px; width: 1px; background: var(--line); }
      .tl-step { display: grid; grid-template-columns: 20px 1fr; gap: 16px; align-items: start; padding: 8px 0; position: relative; z-index: 1; }
      .tl-dot { width: 12px; height: 12px; border-radius: 50%; background: var(--bg-2); border: 2px solid var(--line-2); margin-top: 4px; }
      .tl-step.done .tl-dot { background: var(--accent); border-color: var(--accent); box-shadow: 0 0 0 4px color-mix(in oklab, var(--accent) 16%, transparent); }
      .tl-step h5 { margin: 0; font-family: var(--font-display); font-size: 14px; font-weight: 600; }
      .tl-step.done h5 { color: var(--fg); }
      .tl-step:not(.done) h5 { color: var(--muted); }

      .confirm-items { display: flex; flex-direction: column; gap: 8px; }
      .confirm-item { display: grid; grid-template-columns: 56px 1fr auto; gap: 16px; align-items: center; padding: 12px; background: var(--bg-1); border-radius: var(--r-sm); }
      .ci-thumb { width: 56px; aspect-ratio: 1; border-radius: 6px; }
      .ci-info h5 { margin: 4px 0; font-family: var(--font-display); font-size: 14px; font-weight: 600; }

      .info-row { display: grid; grid-template-columns: 16px 1fr; gap: 12px; padding: 10px 0; border-bottom: 1px dashed var(--line); align-items: start; }
      .info-row:last-of-type { border-bottom: 0; }
      .info-row svg { color: var(--muted); margin-top: 2px; }
      .info-row p { font-size: 14px; }
      .hr { height: 1px; background: var(--line); margin: 12px 0; }

      .confirm-support { display: flex; align-items: center; gap: 8px; margin-top: 16px; padding: 12px; background: var(--bg-1); border-radius: var(--r-sm); font-size: 13px; color: var(--muted); }
      .confirm-support svg { color: var(--accent); }

      .confirm-recs { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }
    `}</style>
  );
}

window.STADIA_CONFIRMATION = Confirmation;
