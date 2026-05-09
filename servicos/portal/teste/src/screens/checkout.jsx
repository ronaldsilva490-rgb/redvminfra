// STADIA — Checkout (entrega + pagamento)

function Checkout({ go, cart, user, addresses, addAddress, placeOrder }) {
  const { PRODUCTS } = window.STADIA_DATA;
  const { BRL } = window.STADIA_UI;

  const items = cart.map((c) => ({ ...c, p: PRODUCTS.find((x) => x.id === c.id) })).filter((c) => c.p);
  const subtotal = items.reduce((s, i) => s + i.p.price * i.qty, 0);

  const [step, setStep] = React.useState(1); // 1 entrega, 2 pagamento, 3 review
  const [selAddr, setSelAddr] = React.useState(addresses.find((a) => a.primary)?.id || addresses[0]?.id);
  const [shipMethod, setShipMethod] = React.useState("express");
  const [payMethod, setPayMethod] = React.useState("credit");
  const [showAddrForm, setShowAddrForm] = React.useState(addresses.length === 0);

  const [card, setCard] = React.useState({ num: "", name: "", exp: "", cvv: "", inst: "1x" });
  const [cardErrors, setCardErrors] = React.useState({});

  const shipping = shipMethod === "same-day" ? 39.9 : shipMethod === "express" ? 19.9 : (subtotal > 299 ? 0 : 24.9);
  const pixDiscount = payMethod === "pix" ? subtotal * 0.05 : 0;
  const total = subtotal - pixDiscount + shipping;

  const validateCard = () => {
    const e = {};
    if (!card.num.replace(/\s/g, "").match(/^\d{16}$/)) e.num = "Número inválido";
    if (!card.name || card.name.length < 3) e.name = "Nome obrigatório";
    if (!card.exp.match(/^\d{2}\/\d{2}$/)) e.exp = "MM/AA";
    if (!card.cvv.match(/^\d{3,4}$/)) e.cvv = "CVV inválido";
    setCardErrors(e);
    return Object.keys(e).length === 0;
  };

  const formatCard = (v) => v.replace(/\D/g, "").slice(0, 16).replace(/(\d{4})(?=\d)/g, "$1 ").trim();
  const formatExp = (v) => v.replace(/\D/g, "").slice(0, 4).replace(/^(\d{2})(\d)/, "$1/$2");

  const submitOrder = () => {
    if (payMethod === "credit" && !validateCard()) { setStep(2); return; }
    const orderId = "STD-2026-" + Math.floor(80000 + Math.random() * 20000);
    placeOrder({ id: orderId, items, total, address: addresses.find((a) => a.id === selAddr), shipMethod, payMethod, placedAt: new Date() });
    go("confirmation", { id: orderId });
  };

  return (
    <main className="checkout-main">
      <div className="container">
        <header className="checkout-head">
          <button className="brand" onClick={() => go("home")}>
            <span className="brand-mark"></span>
            <span className="brand-word">STADIA</span>
          </button>
          <div className="checkout-stepper mono">
            <button className={step >= 1 ? "on" : ""} onClick={() => setStep(1)}>
              <span className="step-num">{step > 1 ? <Icon name="check" size={12}/> : "1"}</span> Entrega
            </button>
            <span className="line"/>
            <button className={step >= 2 ? "on" : ""} onClick={() => step >= 2 && setStep(2)}>
              <span className="step-num">{step > 2 ? <Icon name="check" size={12}/> : "2"}</span> Pagamento
            </button>
            <span className="line"/>
            <button className={step >= 3 ? "on" : ""} onClick={() => step >= 3 && setStep(3)}>
              <span className="step-num">3</span> Revisar
            </button>
          </div>
          <div className="row" style={{ gap: 8, color: "var(--muted)", fontSize: 12 }}>
            <Icon name="lock" size={14}/> <span className="mono small">CHECKOUT 256-BIT SSL</span>
          </div>
        </header>

        <div className="checkout-grid">
          <section className="checkout-content">
            {/* STEP 1 — ENDEREÇO */}
            {step === 1 && (
              <div className="step-block">
                <div className="step-head">
                  <span className="eyebrow">PASSO 1 / 3</span>
                  <h2 className="display">Onde devemos entregar?</h2>
                </div>

                <div className="addr-list">
                  {addresses.map((a) => (
                    <label key={a.id} className={"addr-card " + (selAddr === a.id ? "on" : "")}>
                      <input type="radio" name="addr" checked={selAddr === a.id} onChange={() => setSelAddr(a.id)}/>
                      <div className="addr-radio"/>
                      <div className="addr-info">
                        <div className="row" style={{ gap: 8, marginBottom: 4 }}>
                          <h4>{a.label}</h4>
                          {a.primary && <span className="chip" style={{ height: 22 }}>PADRÃO</span>}
                        </div>
                        <div>{a.name}</div>
                        <div style={{ color: "var(--muted)" }}>{a.street}</div>
                        <div style={{ color: "var(--muted)" }}>{a.district} · {a.city}/{a.state} · {a.zip}</div>
                      </div>
                      <button className="link" onClick={(e) => { e.preventDefault(); }}>Editar</button>
                    </label>
                  ))}
                  <button className="btn ghost block" onClick={() => setShowAddrForm(!showAddrForm)}>
                    <Icon name="plus" size={14}/> Adicionar novo endereço
                  </button>
                </div>

                {showAddrForm && <NewAddressForm onAdd={(a) => { addAddress(a); setShowAddrForm(false); }} onCancel={() => setShowAddrForm(false)}/>}

                <div className="step-head" style={{ marginTop: 32 }}>
                  <span className="eyebrow">FORMA DE ENTREGA</span>
                </div>
                <div className="ship-options">
                  {[
                    { id: "same-day", l: "STADIA Express · Mesmo dia", t: "Hoje até 22h", p: 39.9 },
                    { id: "express", l: "Expresso 24h", t: "Amanhã até 18h", p: 19.9 },
                    { id: "standard", l: "Padrão", t: "3 a 7 dias úteis", p: subtotal > 299 ? 0 : 24.9 },
                  ].map((s) => (
                    <label key={s.id} className={"ship-card " + (shipMethod === s.id ? "on" : "")}>
                      <input type="radio" name="ship" checked={shipMethod === s.id} onChange={() => setShipMethod(s.id)}/>
                      <div className="addr-radio"/>
                      <div className="ship-info">
                        <h5>{s.l}</h5>
                        <span className="mono small" style={{ color: "var(--muted)" }}>{s.t}</span>
                      </div>
                      <span className="mono ship-price">{s.p === 0 ? "GRÁTIS" : BRL(s.p)}</span>
                    </label>
                  ))}
                </div>

                <div className="row" style={{ gap: 12, marginTop: 32, justifyContent: "flex-end" }}>
                  <button className="btn lg" onClick={() => setStep(2)}>
                    Continuar para pagamento <Icon name="arrow-right" size={16}/>
                  </button>
                </div>
              </div>
            )}

            {/* STEP 2 — PAGAMENTO */}
            {step === 2 && (
              <div className="step-block">
                <div className="step-head">
                  <span className="eyebrow">PASSO 2 / 3</span>
                  <h2 className="display">Como você quer pagar?</h2>
                </div>

                <div className="pay-tabs">
                  {[
                    { id: "credit", ic: "card", l: "Cartão de crédito", s: "Até 10x sem juros" },
                    { id: "pix", ic: "pix", l: "Pix", s: "5% de desconto · aprovação imediata" },
                    { id: "boleto", ic: "boleto", l: "Boleto", s: "Compensação em 1-2 dias úteis" },
                  ].map((m) => (
                    <button key={m.id} className={"pay-tab " + (payMethod === m.id ? "on" : "")} onClick={() => setPayMethod(m.id)}>
                      <Icon name={m.ic} size={20}/>
                      <div className="pay-tab-text">
                        <h5>{m.l}</h5>
                        <span className="mono small">{m.s}</span>
                      </div>
                      <div className="addr-radio" style={{ marginLeft: "auto" }}/>
                    </button>
                  ))}
                </div>

                {payMethod === "credit" && (
                  <div className="card-form">
                    <div className="card-mock">
                      <div className="row between"><span className="mono small">STADIA · CRÉDITO</span><span className="mono small" style={{ color: "var(--accent)" }}>VISA</span></div>
                      <div className="card-num mono">{card.num || "•••• •••• •••• ••••"}</div>
                      <div className="row between mono small">
                        <span>{card.name || "NOME COMPLETO"}</span>
                        <span>{card.exp || "MM/AA"}</span>
                      </div>
                    </div>

                    <div className="form-grid">
                      <div className="field">
                        <label>NÚMERO DO CARTÃO</label>
                        <input className={"input " + (cardErrors.num ? "error" : "")}
                          value={card.num} onChange={(e) => setCard({ ...card, num: formatCard(e.target.value) })}
                          placeholder="0000 0000 0000 0000"/>
                        {cardErrors.num && <span className="err">{cardErrors.num}</span>}
                      </div>
                      <div className="field" style={{ gridColumn: "1 / -1" }}>
                        <label>NOME IMPRESSO</label>
                        <input className={"input " + (cardErrors.name ? "error" : "")}
                          value={card.name} onChange={(e) => setCard({ ...card, name: e.target.value.toUpperCase() })}
                          placeholder="COMO ESTÁ NO CARTÃO"/>
                        {cardErrors.name && <span className="err">{cardErrors.name}</span>}
                      </div>
                      <div className="field">
                        <label>VALIDADE</label>
                        <input className={"input " + (cardErrors.exp ? "error" : "")}
                          value={card.exp} onChange={(e) => setCard({ ...card, exp: formatExp(e.target.value) })}
                          placeholder="MM/AA"/>
                        {cardErrors.exp && <span className="err">{cardErrors.exp}</span>}
                      </div>
                      <div className="field">
                        <label>CVV</label>
                        <input className={"input " + (cardErrors.cvv ? "error" : "")}
                          value={card.cvv} onChange={(e) => setCard({ ...card, cvv: e.target.value.replace(/\D/g, "").slice(0, 4) })}
                          placeholder="123"/>
                        {cardErrors.cvv && <span className="err">{cardErrors.cvv}</span>}
                      </div>
                      <div className="field" style={{ gridColumn: "1 / -1" }}>
                        <label>PARCELAS</label>
                        <select className="input" value={card.inst} onChange={(e) => setCard({ ...card, inst: e.target.value })}>
                          {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                            <option key={n} value={n + "x"}>
                              {n}x de R$ {(total / n).toFixed(2).replace(".", ",")} {n === 1 ? "à vista" : "sem juros"}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </div>
                )}

                {payMethod === "pix" && (
                  <div className="pix-block">
                    <div className="pix-qr">
                      <div className="pix-qr-grid">
                        {Array.from({ length: 144 }).map((_, i) => (
                          <span key={i} style={{ background: Math.random() > 0.5 ? "var(--bg-0)" : "transparent" }}/>
                        ))}
                      </div>
                      <div className="pix-qr-corner top-left"/>
                      <div className="pix-qr-corner top-right"/>
                      <div className="pix-qr-corner bottom-left"/>
                      <div className="pix-mark"><Icon name="pix" size={32}/></div>
                    </div>
                    <div>
                      <h4>Pague em segundos</h4>
                      <p>Escaneie o QR Code com o app do seu banco. O pagamento será confirmado em poucos segundos.</p>
                      <div className="pix-stats">
                        <div><span className="mono small">VALOR</span><b>{BRL(total)}</b></div>
                        <div><span className="mono small">DESCONTO</span><b style={{ color: "var(--accent-3)" }}>−5%</b></div>
                        <div><span className="mono small">VÁLIDO ATÉ</span><b>15 min</b></div>
                      </div>
                      <button className="btn outline">
                        <Icon name="check" size={14}/> Copiar código Pix
                      </button>
                    </div>
                  </div>
                )}

                {payMethod === "boleto" && (
                  <div className="boleto-block">
                    <Icon name="boleto" size={32}/>
                    <h4>Boleto bancário</h4>
                    <p>Após confirmar, você receberá o boleto por email. Compensação em 1 a 2 dias úteis.</p>
                    <div className="row between mono small" style={{ width: "100%", paddingTop: 16, borderTop: "1px solid var(--line)" }}>
                      <span>VENCIMENTO</span>
                      <span>09 MAIO 2026</span>
                    </div>
                    <div className="row between mono small" style={{ width: "100%" }}>
                      <span>VALOR</span>
                      <b>{BRL(total)}</b>
                    </div>
                  </div>
                )}

                <div className="row" style={{ gap: 12, marginTop: 32, justifyContent: "space-between" }}>
                  <button className="btn ghost lg" onClick={() => setStep(1)}><Icon name="arrow-left" size={14}/> Voltar</button>
                  <button className="btn lg" onClick={() => setStep(3)}>Revisar pedido <Icon name="arrow-right" size={16}/></button>
                </div>
              </div>
            )}

            {/* STEP 3 — REVIEW */}
            {step === 3 && (
              <div className="step-block">
                <div className="step-head">
                  <span className="eyebrow">PASSO 3 / 3</span>
                  <h2 className="display">Revise e finalize</h2>
                </div>

                <div className="review-card">
                  <div className="review-row">
                    <div className="review-label">
                      <Icon name="pin" size={16}/>
                      <span className="mono small">ENTREGA</span>
                    </div>
                    <div>
                      {(() => {
                        const a = addresses.find((x) => x.id === selAddr);
                        if (!a) return "—";
                        return <>
                          <b>{a.label}</b><br/>
                          {a.street}, {a.district}<br/>
                          <span style={{ color: "var(--muted)" }}>{a.city}/{a.state} · {a.zip}</span>
                        </>;
                      })()}
                    </div>
                    <button className="link" onClick={() => setStep(1)}>Alterar</button>
                  </div>

                  <div className="review-row">
                    <div className="review-label">
                      <Icon name="truck" size={16}/>
                      <span className="mono small">FORMA DE ENVIO</span>
                    </div>
                    <div>
                      <b>{shipMethod === "same-day" ? "STADIA Express · Mesmo dia" : shipMethod === "express" ? "Expresso 24h" : "Padrão"}</b><br/>
                      <span style={{ color: "var(--muted)" }}>Chega {shipMethod === "same-day" ? "hoje até 22h" : shipMethod === "express" ? "amanhã até 18h" : "em 3-7 dias"}</span>
                    </div>
                    <button className="link" onClick={() => setStep(1)}>Alterar</button>
                  </div>

                  <div className="review-row">
                    <div className="review-label">
                      <Icon name={payMethod === "pix" ? "pix" : payMethod === "boleto" ? "boleto" : "card"} size={16}/>
                      <span className="mono small">PAGAMENTO</span>
                    </div>
                    <div>
                      {payMethod === "credit" && <>
                        <b>Cartão · final {(card.num || "0000 0000 0000 0000").slice(-4)}</b><br/>
                        <span style={{ color: "var(--muted)" }}>{card.inst} de R$ {(total / parseInt(card.inst)).toFixed(2).replace(".", ",")}</span>
                      </>}
                      {payMethod === "pix" && <><b>Pix</b><br/><span style={{ color: "var(--accent-3)" }}>5% off aplicado</span></>}
                      {payMethod === "boleto" && <><b>Boleto bancário</b><br/><span style={{ color: "var(--muted)" }}>Vence em 09/05</span></>}
                    </div>
                    <button className="link" onClick={() => setStep(2)}>Alterar</button>
                  </div>
                </div>

                <div className="review-items">
                  <h5 className="mono small" style={{ color: "var(--muted)", letterSpacing: "0.16em", marginBottom: 12 }}>{items.length} ITENS</h5>
                  {items.map((i) => (
                    <div key={i.id + i.size + i.color} className="rev-item">
                      <div className="rev-thumb img-ph has-viz" style={{ background: i.p.imageBg }}><STADIA_PRODUCT_VISUAL p={i.p}/></div>
                      <div className="rev-info">
                        <h5>{i.p.name}</h5>
                        <span className="mono small" style={{ color: "var(--muted)" }}>{i.color || i.p.colors[0].name} · {i.size || i.p.sizes[0]} · QTD {i.qty}</span>
                      </div>
                      <span className="mono">{BRL(i.p.price * i.qty)}</span>
                    </div>
                  ))}
                </div>

                <div className="row" style={{ gap: 12, marginTop: 32, justifyContent: "space-between" }}>
                  <button className="btn ghost lg" onClick={() => setStep(2)}><Icon name="arrow-left" size={14}/> Voltar</button>
                  <button className="btn lg" onClick={submitOrder}>
                    <Icon name="lock" size={14}/> Finalizar compra · {BRL(total)}
                  </button>
                </div>
              </div>
            )}
          </section>

          {/* SUMMARY (sticky) */}
          <aside className="checkout-summary">
            <div className="sum-card">
              <h3>Pedido</h3>
              <div className="sum-items">
                {items.slice(0, 3).map((i) => (
                  <div key={i.id + i.size + i.color} className="sum-item">
                    <div className="sum-thumb img-ph has-viz" style={{ background: i.p.imageBg }}>
                      <STADIA_PRODUCT_VISUAL p={i.p}/>
                      <span className="qty-bubble mono">{i.qty}</span>
                    </div>
                    <div className="sum-item-info">
                      <span className="mono small" style={{ color: "var(--muted)" }}>{i.p.sub}</span>
                      <h5>{i.p.name}</h5>
                      <span className="mono small">{i.color || i.p.colors[0].name} · {i.size || i.p.sizes[0]}</span>
                    </div>
                    <span className="mono">{BRL(i.p.price * i.qty)}</span>
                  </div>
                ))}
                {items.length > 3 && <span className="mono small" style={{ color: "var(--muted)", display: "block", textAlign: "center", padding: 8 }}>+ {items.length - 3} itens</span>}
              </div>
              <div className="sum-divider"/>
              <div className="sum-line"><span>Subtotal</span><span className="mono">{BRL(subtotal)}</span></div>
              <div className="sum-line"><span>Frete</span><span className="mono">{shipping === 0 ? "GRÁTIS" : BRL(shipping)}</span></div>
              {pixDiscount > 0 && <div className="sum-line" style={{ color: "var(--accent-3)" }}><span>Pix · 5%</span><span className="mono">−{BRL(pixDiscount)}</span></div>}
              <div className="sum-divider"/>
              <div className="sum-total">
                <span>Total</span>
                <b className="display">{BRL(total)}</b>
              </div>
            </div>
          </aside>
        </div>
      </div>

      <CheckoutStyles/>
    </main>
  );
}

function NewAddressForm({ onAdd, onCancel }) {
  const [f, setF] = React.useState({ label: "Casa", name: "", zip: "", street: "", district: "", city: "", state: "", phone: "" });
  const [err, setErr] = React.useState({});

  const submit = () => {
    const e = {};
    ["name", "zip", "street", "district", "city", "state"].forEach((k) => { if (!f[k]) e[k] = "Obrigatório"; });
    setErr(e);
    if (Object.keys(e).length === 0) {
      onAdd({ ...f, id: "a" + Date.now() });
    }
  };

  return (
    <div className="addr-form">
      <h4 style={{ marginTop: 0 }}>Novo endereço</h4>
      <div className="form-grid">
        <div className="field" style={{ gridColumn: "1 / -1" }}>
          <label>RÓTULO</label>
          <div className="row" style={{ gap: 8 }}>
            {["Casa", "Trabalho", "Outro"].map((l) => (
              <button key={l} className={"chip-toggle " + (f.label === l ? "on" : "")} onClick={() => setF({ ...f, label: l })}>{l}</button>
            ))}
          </div>
        </div>
        <div className="field" style={{ gridColumn: "1 / -1" }}>
          <label>NOME COMPLETO</label>
          <input className={"input " + (err.name ? "error" : "")} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })}/>
        </div>
        <div className="field">
          <label>CEP</label>
          <input className={"input " + (err.zip ? "error" : "")} value={f.zip} onChange={(e) => setF({ ...f, zip: e.target.value })} placeholder="00000-000"/>
        </div>
        <div className="field">
          <label>TELEFONE</label>
          <input className="input" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} placeholder="(11) 9 0000-0000"/>
        </div>
        <div className="field" style={{ gridColumn: "1 / -1" }}>
          <label>RUA / NÚMERO / COMPLEMENTO</label>
          <input className={"input " + (err.street ? "error" : "")} value={f.street} onChange={(e) => setF({ ...f, street: e.target.value })}/>
        </div>
        <div className="field">
          <label>BAIRRO</label>
          <input className={"input " + (err.district ? "error" : "")} value={f.district} onChange={(e) => setF({ ...f, district: e.target.value })}/>
        </div>
        <div className="field">
          <label>CIDADE</label>
          <input className={"input " + (err.city ? "error" : "")} value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })}/>
        </div>
        <div className="field">
          <label>UF</label>
          <input className={"input " + (err.state ? "error" : "")} value={f.state} onChange={(e) => setF({ ...f, state: e.target.value.toUpperCase().slice(0, 2) })}/>
        </div>
      </div>
      <div className="row" style={{ gap: 8, marginTop: 16 }}>
        <button className="btn ghost" onClick={onCancel}>Cancelar</button>
        <button className="btn" onClick={submit}>Salvar endereço</button>
      </div>
    </div>
  );
}

function CheckoutStyles() {
  return (
    <style>{`
      .checkout-main { padding: 24px 0 60px; }
      .checkout-head {
        display: grid; grid-template-columns: auto 1fr auto; gap: 32px; align-items: center;
        padding: 16px 0 32px;
        border-bottom: 1px solid var(--line);
      }
      .checkout-head .brand {
        background: transparent; border: 0; color: inherit;
        display: inline-flex; align-items: baseline; gap: 6px;
        font-family: var(--font-display); font-weight: 700; font-size: 22px; letter-spacing: -0.04em;
      }
      .checkout-stepper {
        display: flex; align-items: center; gap: 12px;
        justify-self: center;
        font-size: 12px; letter-spacing: 0.06em;
      }
      .checkout-stepper button {
        background: transparent; border: 0;
        display: inline-flex; align-items: center; gap: 8px;
        color: var(--muted);
        font-family: inherit; font-size: 12px;
      }
      .checkout-stepper button.on { color: var(--fg); }
      .checkout-stepper .step-num {
        width: 22px; height: 22px; border-radius: 50%;
        background: var(--bg-3); color: var(--muted);
        display: grid; place-items: center;
        font-family: var(--font-mono); font-size: 11px;
      }
      .checkout-stepper .on .step-num { background: var(--accent); color: var(--accent-ink); }
      .checkout-stepper .line { width: 32px; height: 1px; background: var(--line-2); }

      .checkout-grid {
        display: grid; grid-template-columns: 1fr 380px; gap: 48px;
        padding-top: 40px;
      }
      @media (max-width: 1000px) { .checkout-grid { grid-template-columns: 1fr; gap: 24px; } }

      .step-block { display: flex; flex-direction: column; gap: 24px; }
      .step-head { display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; }
      .step-head h2 { margin: 0; font-size: clamp(28px, 3vw, 40px); letter-spacing: -0.02em; }

      .addr-list { display: flex; flex-direction: column; gap: 12px; }
      .addr-card, .ship-card, .pay-tab {
        display: grid;
        grid-template-columns: 24px 1fr auto;
        gap: 16px; align-items: center;
        padding: 20px;
        background: var(--surface); border: 1px solid var(--line);
        border-radius: var(--r-md);
        cursor: pointer;
      }
      .ship-card { grid-template-columns: 24px 1fr auto; }
      .pay-tab { grid-template-columns: 24px 1fr 24px; }
      .addr-card.on, .ship-card.on, .pay-tab.on { border-color: var(--accent); background: color-mix(in oklab, var(--accent) 4%, var(--surface)); }
      .addr-card input, .ship-card input, .pay-tab input { display: none; }
      .addr-radio {
        width: 18px; height: 18px; border: 1px solid var(--line-2); border-radius: 50%;
        position: relative; flex-shrink: 0;
      }
      .addr-card.on .addr-radio, .ship-card.on .addr-radio, .pay-tab.on .addr-radio {
        border-color: var(--accent);
      }
      .addr-card.on .addr-radio::after, .ship-card.on .addr-radio::after, .pay-tab.on .addr-radio::after {
        content: ""; position: absolute; inset: 3px;
        background: var(--accent); border-radius: 50%;
      }
      .addr-info h4 { margin: 0; font-family: var(--font-display); font-size: 16px; font-weight: 700; }
      .ship-info h5 { margin: 0; font-family: var(--font-display); font-size: 15px; font-weight: 600; }
      .ship-price { font-size: 16px; font-weight: 700; color: var(--accent); }
      .pay-tab-text h5 { margin: 0; font-family: var(--font-display); font-size: 15px; font-weight: 600; }
      .pay-tab-text .small { color: var(--muted); }

      .addr-form {
        padding: 24px;
        background: var(--bg-1); border: 1px solid var(--line-2);
        border-radius: var(--r-md);
      }
      .addr-form h4 { margin: 0 0 16px; font-family: var(--font-display); font-size: 18px; font-weight: 700; }
      .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
      .chip-toggle {
        padding: 8px 16px; height: 36px;
        background: var(--surface); border: 1px solid var(--line-2);
        color: var(--fg); border-radius: 999px;
        font-family: inherit; font-size: 13px;
      }
      .chip-toggle.on { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }

      .ship-options, .pay-tabs { display: flex; flex-direction: column; gap: 12px; }

      .card-form { display: grid; grid-template-columns: 320px 1fr; gap: 32px; align-items: start; }
      @media (max-width: 800px) { .card-form { grid-template-columns: 1fr; } }
      .card-mock {
        aspect-ratio: 1.586/1;
        padding: 24px;
        background: linear-gradient(135deg, var(--bg-3), var(--bg-2) 60%, color-mix(in oklab, var(--accent) 30%, var(--bg-3)));
        border-radius: var(--r-md);
        border: 1px solid var(--line-2);
        display: flex; flex-direction: column; justify-content: space-between;
        position: relative; overflow: hidden;
      }
      .card-mock::after {
        content: ""; position: absolute; top: 0; right: 0;
        width: 200px; height: 200px;
        background: radial-gradient(circle, var(--accent-glow), transparent 60%);
        filter: blur(40px);
      }
      .card-num { font-size: 22px; letter-spacing: 0.1em; color: var(--fg); position: relative; z-index: 1; }

      .pix-block { display: grid; grid-template-columns: 240px 1fr; gap: 32px; align-items: center; padding: 24px; background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-md); }
      @media (max-width: 700px) { .pix-block { grid-template-columns: 1fr; justify-items: center; text-align: center; } }
      .pix-qr {
        width: 240px; height: 240px;
        background: white; border-radius: var(--r-sm);
        position: relative; padding: 16px;
      }
      .pix-qr-grid { display: grid; grid-template-columns: repeat(12, 1fr); grid-template-rows: repeat(12, 1fr); gap: 1px; width: 100%; height: 100%; }
      .pix-qr-grid > span { display: block; }
      .pix-qr-corner { position: absolute; width: 36px; height: 36px; background: var(--bg-0); border: 6px solid white; }
      .pix-qr-corner.top-left { top: 16px; left: 16px; }
      .pix-qr-corner.top-right { top: 16px; right: 16px; }
      .pix-qr-corner.bottom-left { bottom: 16px; left: 16px; }
      .pix-mark { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); width: 56px; height: 56px; background: white; border-radius: 8px; display: grid; place-items: center; color: var(--accent-3); }
      .pix-block h4 { margin: 0 0 8px; font-family: var(--font-display); font-size: 24px; font-weight: 700; }
      .pix-block p { margin: 0; color: var(--muted); }
      .pix-stats { display: flex; gap: 16px; padding: 16px 0; border-top: 1px dashed var(--line); border-bottom: 1px dashed var(--line); margin: 16px 0; }
      .pix-stats div { flex: 1; }
      .pix-stats b { display: block; font-family: var(--font-display); font-size: 18px; font-weight: 700; }

      .boleto-block { padding: 32px; background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-md); display: flex; flex-direction: column; align-items: center; text-align: center; gap: 12px; }
      .boleto-block svg { color: var(--accent); }
      .boleto-block h4 { margin: 0; font-family: var(--font-display); font-size: 22px; font-weight: 700; }
      .boleto-block p { color: var(--muted); margin: 0 0 16px; max-width: 360px; }

      .review-card {
        background: var(--surface); border: 1px solid var(--line);
        border-radius: var(--r-md);
        padding: 8px 24px;
      }
      .review-row {
        display: grid; grid-template-columns: 200px 1fr auto;
        gap: 24px; align-items: flex-start;
        padding: 20px 0;
        border-bottom: 1px solid var(--line);
      }
      .review-row:last-child { border-bottom: 0; }
      .review-label { display: flex; align-items: center; gap: 8px; color: var(--muted); }
      .review-label .small { font-size: 11px; letter-spacing: 0.14em; }
      .review-row b { font-weight: 600; color: var(--fg); }

      .review-items { display: flex; flex-direction: column; gap: 8px; }
      .rev-item {
        display: grid; grid-template-columns: 56px 1fr auto;
        gap: 16px; align-items: center;
        padding: 12px;
        background: var(--surface); border: 1px solid var(--line);
        border-radius: var(--r-sm);
      }
      .rev-thumb { width: 56px; aspect-ratio: 1; border-radius: 6px; }
      .rev-info h5 { margin: 0; font-family: var(--font-display); font-size: 15px; font-weight: 600; }

      /* SUMMARY (sticky) */
      .checkout-summary { position: sticky; top: 24px; align-self: start; }
      @media (max-width: 1000px) { .checkout-summary { position: static; } }
      .sum-card {
        background: var(--surface); border: 1px solid var(--line);
        border-radius: var(--r-md);
        padding: 24px;
      }
      .sum-card h3 { margin: 0 0 16px; font-family: var(--font-display); font-size: 18px; font-weight: 700; }
      .sum-items { display: flex; flex-direction: column; gap: 12px; max-height: 240px; overflow: auto; padding-right: 8px; }
      .sum-item { display: grid; grid-template-columns: 48px 1fr auto; gap: 12px; align-items: center; }
      .sum-thumb { width: 48px; aspect-ratio: 1; border-radius: 6px; position: relative; }
      .qty-bubble { position: absolute; top: -6px; right: -6px; width: 20px; height: 20px; background: var(--accent); color: var(--accent-ink); border-radius: 50%; display: grid; place-items: center; font-size: 11px; font-weight: 700; }
      .sum-item-info h5 { margin: 0; font-size: 13px; font-weight: 600; }
      .sum-divider { height: 1px; background: var(--line); margin: 16px 0; }
      .sum-line { display: flex; justify-content: space-between; padding: 4px 0; color: var(--fg-2); font-size: 13px; }
      .sum-total { display: flex; justify-content: space-between; align-items: center; padding-top: 8px; }
      .sum-total b { font-size: 28px; letter-spacing: -0.03em; line-height: 1; }
    `}</style>
  );
}

window.STADIA_CHECKOUT = Checkout;
