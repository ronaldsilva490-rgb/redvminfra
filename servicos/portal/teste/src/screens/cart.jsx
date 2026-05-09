// STADIA — Cart screen

function Cart({ go, cart, updateCartQty, removeFromCart, addToCart, wishlist, toggleFav }) {
  const { PRODUCTS } = window.STADIA_DATA;
  const { BRL } = window.STADIA_UI;
  const [coupon, setCoupon] = React.useState("");
  const [appliedCoupon, setAppliedCoupon] = React.useState(null);
  const [couponMsg, setCouponMsg] = React.useState(null);

  const items = cart.map((c) => ({ ...c, p: PRODUCTS.find((x) => x.id === c.id) })).filter((c) => c.p);
  const subtotal = items.reduce((s, i) => s + i.p.price * i.qty, 0);
  const discount = appliedCoupon ? subtotal * 0.1 : 0;
  const shipping = subtotal > 299 ? 0 : 24.9;
  const total = subtotal - discount + shipping;
  const recs = PRODUCTS.filter((p) => !cart.find((c) => c.id === p.id)).slice(0, 4);

  const applyCoupon = () => {
    if (coupon.toUpperCase() === "MATCHDAY10") {
      setAppliedCoupon({ code: "MATCHDAY10", off: 10 });
      setCouponMsg({ type: "success", text: "Cupom MATCHDAY10 aplicado · 10% off" });
    } else if (coupon.length > 0) {
      setCouponMsg({ type: "error", text: "Cupom inválido. Tente MATCHDAY10." });
    }
  };

  if (items.length === 0) return <CartEmpty go={go} recs={recs} addToCart={addToCart} toggleFav={toggleFav} wishlist={wishlist}/>;

  return (
    <main className="cart-main">
      <div className="container">
        <nav className="crumb mono" style={{ padding: "20px 0" }}>
          <button onClick={() => go("home")}>STADIA</button><span>/</span>
          <span style={{ color: "var(--fg)" }}>CARRINHO</span>
        </nav>

        <div className="cart-head">
          <h1 className="display" style={{ fontSize: "clamp(40px,5vw,72px)", margin: 0 }}>Carrinho</h1>
          <div className="cart-stepper mono">
            <span className="on">1 · CARRINHO</span><span className="line"/><span>2 · ENTREGA</span><span className="line"/><span>3 · PAGAMENTO</span><span className="line"/><span>4 · CONFIRMAÇÃO</span>
          </div>
        </div>

        <div className="cart-grid">
          <section className="cart-items">
            <div className="cart-items-head mono">
              <span>{items.length} ITENS</span>
              <span style={{ flex: 1 }}/>
              <button onClick={() => go("plp")}><Icon name="arrow-left" size={12}/> Continuar comprando</button>
            </div>

            {items.map((i) => (
              <article key={i.id + i.size + i.color} className="cart-row">
                <div className="cart-thumb img-ph has-viz" style={{ background: i.p.imageBg }}>
                  <STADIA_PRODUCT_VISUAL p={i.p}/>
                </div>
                <div className="cart-info">
                  <span className="mono small" style={{ color: "var(--muted)" }}>{i.p.sub.toUpperCase()}</span>
                  <h3>{i.p.name}</h3>
                  <div className="row" style={{ gap: 16, marginTop: 8 }}>
                    <span className="mono small">COR · {i.color || i.p.colors[0].name}</span>
                    <span className="mono small">TAM · {i.size || i.p.sizes[0]}</span>
                  </div>
                  <div className="row" style={{ gap: 12, marginTop: 12 }}>
                    <button className="link" onClick={() => toggleFav(i.id)}>
                      <Icon name="heart" size={12}/> Salvar para depois
                    </button>
                    <button className="link" onClick={() => removeFromCart(i.id, i.size, i.color)}>
                      <Icon name="trash" size={12}/> Remover
                    </button>
                  </div>
                </div>
                <div className="cart-actions">
                  <div className="qty">
                    <button onClick={() => updateCartQty(i.id, i.size, i.color, Math.max(1, i.qty - 1))}><Icon name="minus" size={12}/></button>
                    <span className="mono">{i.qty}</span>
                    <button onClick={() => updateCartQty(i.id, i.size, i.color, i.qty + 1)}><Icon name="plus" size={12}/></button>
                  </div>
                  <div className="cart-price">
                    <b>{BRL(i.p.price * i.qty)}</b>
                    {i.qty > 1 && <span className="mono small">{BRL(i.p.price)} cada</span>}
                  </div>
                </div>
              </article>
            ))}

            <div className="cart-banner">
              <Icon name="lightning" size={20}/>
              <span>Adicione mais <b>{BRL(Math.max(0, 299 - subtotal))}</b> e ganhe frete grátis em todo o Brasil.</span>
              <div className="frete-bar"><div style={{ width: `${Math.min(100, (subtotal / 299) * 100)}%` }}/></div>
            </div>

            <div className="cart-recs">
              <h4 className="mono small" style={{ color: "var(--muted)", letterSpacing: "0.16em", marginBottom: 16 }}>FREQUENTEMENTE COMPRADOS JUNTOS</h4>
              <div className="rec-row">
                {recs.map((p) => (
                  <div key={p.id} className="rec-mini">
                    <div className="rec-thumb img-ph has-viz" style={{ background: p.imageBg }}><STADIA_PRODUCT_VISUAL p={p}/></div>
                    <div className="rec-info">
                      <h5>{p.name}</h5>
                      <span className="mono">{BRL(p.price)}</span>
                    </div>
                    <button className="btn ghost sm" onClick={() => addToCart(p)}>+ Add</button>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <aside className="cart-summary">
            <div className="sum-card">
              <h3>Resumo</h3>
              <div className="sum-line"><span>Subtotal · {items.length} {items.length === 1 ? "item" : "itens"}</span><span className="mono">{BRL(subtotal)}</span></div>
              {appliedCoupon && (
                <div className="sum-line" style={{ color: "var(--accent-3)" }}><span>Cupom {appliedCoupon.code}</span><span className="mono">−{BRL(discount)}</span></div>
              )}
              <div className="sum-line"><span>Frete</span><span className="mono">{shipping === 0 ? "GRÁTIS" : BRL(shipping)}</span></div>
              <div className="sum-line">
                <span>Pix · 5% off</span>
                <span className="mono" style={{ color: "var(--accent-3)" }}>−{BRL(total * 0.05)}</span>
              </div>
              <div className="sum-divider"/>
              <div className="sum-total">
                <span>Total</span>
                <div style={{ textAlign: "right" }}>
                  <b className="display">{BRL(total)}</b>
                  <div className="mono small" style={{ color: "var(--muted)" }}>ou 10x R$ {(total / 10).toFixed(2).replace(".", ",")} sem juros</div>
                </div>
              </div>

              <button className="btn lg block" onClick={() => go("checkout")}>
                Ir para entrega <Icon name="arrow-right" size={16}/>
              </button>
              <button className="btn lg dark block">
                <Icon name="lightning" size={16}/> Comprar com 1 clique
              </button>
            </div>

            <div className="coupon-card">
              <h4 className="mono small" style={{ color: "var(--muted)", letterSpacing: "0.16em", marginBottom: 12 }}>CUPOM</h4>
              <div className="row" style={{ gap: 8 }}>
                <input className="input" style={{ height: 44 }} placeholder="Insira seu cupom"
                  value={coupon} onChange={(e) => setCoupon(e.target.value.toUpperCase())}/>
                <button className="btn ghost" onClick={applyCoupon}>Aplicar</button>
              </div>
              {couponMsg && (
                <p className="mono small" style={{ marginTop: 8, color: couponMsg.type === "success" ? "var(--accent-3)" : "var(--danger)" }}>
                  {couponMsg.text}
                </p>
              )}
            </div>

            <div className="trust-card">
              <div className="row" style={{ gap: 12 }}><Icon name="lock" size={14}/><span>Pagamento 256-bit SSL</span></div>
              <div className="row" style={{ gap: 12 }}><Icon name="shield" size={14}/><span>Compra protegida</span></div>
              <div className="row" style={{ gap: 12 }}><Icon name="package" size={14}/><span>Troca grátis em 30 dias</span></div>
            </div>
          </aside>
        </div>
      </div>

      <style>{`
        .cart-main { padding-bottom: 60px; }
        .cart-head { display: flex; justify-content: space-between; align-items: center; gap: 32px; padding-bottom: 32px; flex-wrap: wrap; }
        .cart-stepper { display: flex; align-items: center; gap: 12px; font-size: 11px; letter-spacing: 0.14em; color: var(--muted); }
        .cart-stepper .on { color: var(--accent); }
        .cart-stepper .line { width: 24px; height: 1px; background: var(--line-2); }

        .cart-grid { display: grid; grid-template-columns: 1fr 400px; gap: 48px; align-items: start; }
        @media (max-width: 1000px) { .cart-grid { grid-template-columns: 1fr; gap: 24px; } }
        [data-viewport="mobile"] .cart-grid { grid-template-columns: 1fr; gap: 16px; }

        .cart-items { display: flex; flex-direction: column; gap: 12px; }
        .cart-items-head {
          display: flex; align-items: center; gap: 16px;
          padding-bottom: 16px;
          font-size: 11px; letter-spacing: 0.14em; color: var(--muted);
          border-bottom: 1px solid var(--line);
        }
        .cart-items-head button {
          background: transparent; border: 0; color: var(--accent);
          display: inline-flex; align-items: center; gap: 6px;
          font-family: inherit; font-size: 11px; letter-spacing: 0.14em;
        }
        .cart-row {
          display: grid;
          grid-template-columns: 120px 1fr auto;
          gap: 24px;
          padding: 20px;
          background: var(--surface);
          border: 1px solid var(--line);
          border-radius: var(--r-md);
        }
        [data-viewport="mobile"] .cart-row { grid-template-columns: 80px 1fr; padding: 12px; gap: 12px; }
        [data-viewport="mobile"] .cart-actions { grid-column: 1 / -1; flex-direction: row !important; align-items: center; justify-content: space-between; }
        .cart-thumb { width: 120px; aspect-ratio: 1; border-radius: var(--r-sm); }
        [data-viewport="mobile"] .cart-thumb { width: 80px; }
        .cart-info { min-width: 0; }
        .cart-info h3 { margin: 4px 0; font-family: var(--font-display); font-size: 18px; font-weight: 700; }
        .cart-actions { display: flex; flex-direction: column; align-items: flex-end; justify-content: space-between; gap: 12px; }
        .cart-price b { font-family: var(--font-display); font-size: 20px; font-weight: 700; display: block; text-align: right; }
        .cart-price .mono { display: block; text-align: right; color: var(--muted); margin-top: 2px; }
        .link { background: transparent; border: 0; color: var(--muted); padding: 0; display: inline-flex; align-items: center; gap: 6px; font-size: 12px; }
        .link:hover { color: var(--fg); }

        .cart-banner {
          display: grid; grid-template-columns: 24px 1fr; gap: 12px 16px;
          padding: 16px 20px; background: color-mix(in oklab, var(--accent-3) 10%, var(--surface));
          border: 1px solid color-mix(in oklab, var(--accent-3) 30%, var(--line));
          border-radius: var(--r-md);
          align-items: center;
          color: var(--fg-2); font-size: 14px;
        }
        .cart-banner svg { color: var(--accent-3); }
        .cart-banner b { color: var(--accent-3); }
        .frete-bar { grid-column: 1 / -1; height: 4px; background: var(--bg-3); border-radius: 999px; overflow: hidden; }
        .frete-bar > div { height: 100%; background: var(--accent-3); transition: width 0.3s; }

        .cart-recs { padding-top: 32px; margin-top: 16px; border-top: 1px solid var(--line); }
        .rec-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        @media (max-width: 700px) { .rec-row { grid-template-columns: 1fr; } }
        .rec-mini { display: grid; grid-template-columns: 56px 1fr auto; gap: 12px; align-items: center; padding: 8px; background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-sm); }
        .rec-thumb { width: 56px; aspect-ratio: 1; border-radius: 6px; }
        .rec-info h5 { margin: 0; font-family: var(--font-display); font-size: 14px; font-weight: 600; }
        .rec-info .mono { font-size: 12px; color: var(--accent); font-weight: 600; }

        .cart-summary { display: flex; flex-direction: column; gap: 12px; position: sticky; top: 100px; }
        @media (max-width: 1000px) { .cart-summary { position: static; } }
        .sum-card, .coupon-card, .trust-card {
          background: var(--surface); border: 1px solid var(--line);
          border-radius: var(--r-md); padding: 24px;
        }
        .sum-card h3 { margin: 0 0 20px; font-family: var(--font-display); font-size: 22px; font-weight: 700; }
        .sum-line { display: flex; justify-content: space-between; padding: 8px 0; color: var(--fg-2); font-size: 14px; }
        .sum-line .mono { font-size: 14px; }
        .sum-divider { height: 1px; background: var(--line); margin: 12px 0; }
        .sum-total { display: flex; justify-content: space-between; align-items: center; padding-bottom: 24px; }
        .sum-total span { font-size: 16px; }
        .sum-total b { font-size: 32px; letter-spacing: -0.03em; line-height: 1; display: block; }
        .sum-card .btn { margin-top: 8px; }
        .trust-card { display: flex; flex-direction: column; gap: 12px; color: var(--muted); font-size: 13px; }
        .trust-card svg { color: var(--accent-3); }
      `}</style>
    </main>
  );
}

function CartEmpty({ go, recs, addToCart, toggleFav, wishlist }) {
  return (
    <main className="cart-empty">
      <div className="container">
        <div className="empty-hero">
          <Icon name="bag" size={56} stroke={1.2}/>
          <h1 className="display" style={{ fontSize: "clamp(40px,5vw,64px)", margin: "16px 0 12px" }}>Seu carrinho está em jejum.</h1>
          <p style={{ color: "var(--muted)", fontSize: 16, maxWidth: 480, margin: "0 auto" }}>Comece pelos drops mais quentes da semana ou retome de onde parou.</p>
          <div className="row" style={{ gap: 12, marginTop: 32, justifyContent: "center" }}>
            <button className="btn lg" onClick={() => go("plp", { filter: "drop" })}>Ver drop atual</button>
            <button className="btn lg ghost" onClick={() => go("plp")}>Explorar tudo</button>
          </div>
        </div>
        <section style={{ paddingTop: 80 }}>
          <window.STADIA_UI.SectionHead kicker="MAIS DESEJADOS" title="Comece por aqui"/>
          <div className="grid-cards">
            {recs.map((p) => (
              <window.STADIA_UI.ProductCard key={p.id} p={p} variant="minimal"
                faved={wishlist.includes(p.id)}
                onOpen={() => go("pdp", { id: p.id })}
                onFav={() => toggleFav(p.id)}
                onAdd={() => addToCart(p)}/>
            ))}
          </div>
        </section>
      </div>
      <style>{`
        .cart-empty { padding: 60px 0; }
        .empty-hero { text-align: center; padding: 64px 0; color: var(--muted); }
        .empty-hero svg { color: var(--accent); }
        .grid-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 24px; }
        @media (max-width: 1000px) { .grid-cards { grid-template-columns: repeat(2, 1fr); } }
      `}</style>
    </main>
  );
}

window.STADIA_CART = Cart;
