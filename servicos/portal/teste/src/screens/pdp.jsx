// STADIA — PDP (detalhe do produto) com 2 variants

const { ProductCard: __PC, BRL: __BRL, StarRating: __SR } = window.STADIA_UI;

function PDP({ go, addToCart, toggleFav, wishlist, params, variant }) {
  const { PRODUCTS, REVIEWS } = window.STADIA_DATA;
  const id = params?.id || "p01";
  const p = PRODUCTS.find((x) => x.id === id) || PRODUCTS[0];
  const [size, setSize] = React.useState(p.sizes[Math.floor(p.sizes.length / 2)]);
  const [color, setColor] = React.useState(p.colors[0]);
  const [qty, setQty] = React.useState(1);
  const [tab, setTab] = React.useState("desc");
  const faved = wishlist.includes(p.id);

  React.useEffect(() => {
    setSize(p.sizes[Math.floor(p.sizes.length / 2)]);
    setColor(p.colors[0]);
  }, [p.id]);

  const discount = p.listPrice > p.price ? Math.round((1 - p.price / p.listPrice) * 100) : 0;
  const installments = (p.price / 10).toFixed(2).replace(".", ",");

  const recs = PRODUCTS.filter((x) => x.id !== p.id && x.category === p.category).slice(0, 4);
  if (recs.length < 4) recs.push(...PRODUCTS.filter((x) => !recs.includes(x) && x.id !== p.id).slice(0, 4 - recs.length));

  if (variant === "spec") return (
    <PDPSpec p={p} go={go} addToCart={addToCart} toggleFav={toggleFav} faved={faved}
      size={size} setSize={setSize} color={color} setColor={setColor}
      qty={qty} setQty={setQty} tab={tab} setTab={setTab}
      discount={discount} installments={installments} recs={recs} REVIEWS={REVIEWS}/>
  );
  return (
    <PDPDefault p={p} go={go} addToCart={addToCart} toggleFav={toggleFav} faved={faved}
      size={size} setSize={setSize} color={color} setColor={setColor}
      qty={qty} setQty={setQty} tab={tab} setTab={setTab}
      discount={discount} installments={installments} recs={recs} REVIEWS={REVIEWS}/>
  );
}

/* ============================================================
   PDP Default — gallery left, sticky details right
   ============================================================ */
function PDPDefault({ p, go, addToCart, toggleFav, faved, size, setSize, color, setColor, qty, setQty, tab, setTab, discount, installments, recs, REVIEWS }) {
  const [zoom, setZoom] = React.useState(0);

  const gallery = [
    { bg: p.imageBg, label: p.imageLabel },
    { bg: p.imageBg, label: p.imageLabel + " · costas" },
    { bg: p.imageBg, label: p.imageLabel + " · detalhe" },
    { bg: p.imageBg, label: p.imageLabel + " · uso" },
  ];

  return (
    <main className="pdp-main">
      <div className="container">
        <nav className="crumb mono" style={{ padding: "20px 0" }}>
          <button onClick={() => go("home")}>STADIA</button>
          <span>/</span>
          <button onClick={() => go("plp", { cat: p.category })}>{p.category.toUpperCase()}</button>
          <span>/</span>
          <span style={{ color: "var(--fg)" }}>{p.id.toUpperCase()}</span>
        </nav>

        <div className="pdp-grid">
          <section className="pdp-gallery">
            <div className="gal-thumbs">
              {gallery.map((g, i) => (
                <button key={i} className={"gal-thumb " + (zoom === i ? "on" : "")} onClick={() => setZoom(i)}>
                  <div className="img-ph has-viz" style={{ background: g.bg, height: "100%" }}><STADIA_PRODUCT_VISUAL p={p}/></div>
                </button>
              ))}
            </div>
            <div className="gal-main img-ph has-viz" style={{ background: gallery[zoom].bg }}>
              <STADIA_PRODUCT_VISUAL p={p}/>
              {p.badge && <span className={`pbadge bg-${p.badge}`} style={{ position: "absolute", top: 20, left: 20 }}>{p.badge}</span>}
              <button className="gal-fav" data-on={faved ? "1" : "0"} onClick={() => toggleFav(p.id)}>
                <Icon name="heart" size={18}/>
              </button>
            </div>
          </section>

          <aside className="pdp-side">
            <div className="row" style={{ gap: 8, marginBottom: 12 }}>
              {p.tags?.map((t) => <span key={t} className="chip" style={{ height: 24 }}>{t}</span>)}
              {p.badge === "drop" && <span className="chip live" style={{ height: 24 }}>DROP MATCHDAY 03</span>}
            </div>
            <span className="mono small" style={{ color: "var(--muted)", letterSpacing: "0.14em" }}>{p.sub.toUpperCase()}</span>
            <h1 className="display pdp-title">{p.name}</h1>
            <window.STADIA_UI.StarRating value={p.rating} count={p.reviews}/>

            <div className="pdp-price">
              <span className="cur">{window.STADIA_UI.BRL(p.price)}</span>
              {discount > 0 && <span className="old">{window.STADIA_UI.BRL(p.listPrice)}</span>}
              {discount > 0 && <span className="off">−{discount}%</span>}
            </div>
            <span className="mono small pix-line">
              <Icon name="pix" size={14}/> R$ {(p.price * 0.95).toFixed(2).replace(".", ",")} no Pix · ou 10x R$ {installments}
            </span>

            <div className="pdp-divider"></div>

            <div className="opt-block">
              <div className="opt-head">
                <span className="mono small">COR · {color.name.toUpperCase()}</span>
              </div>
              <div className="row" style={{ gap: 8 }}>
                {p.colors.map((c) => (
                  <button key={c.hex} className={"color-btn " + (color.hex === c.hex ? "on" : "")} onClick={() => setColor(c)} aria-label={c.name}>
                    <span style={{ background: c.hex }}/>
                  </button>
                ))}
              </div>
            </div>

            <div className="opt-block">
              <div className="opt-head">
                <span className="mono small">TAMANHO · {size}</span>
                <button className="opt-link mono small">TABELA DE MEDIDAS</button>
              </div>
              <div className="size-row">
                {p.sizes.map((s) => (
                  <button key={s} className={"size-btn-pdp " + (size === s ? "on" : "")} onClick={() => setSize(s)}>{s}</button>
                ))}
              </div>
            </div>

            <div className="opt-block">
              <div className="opt-head"><span className="mono small">QUANTIDADE</span></div>
              <div className="qty">
                <button onClick={() => setQty(Math.max(1, qty - 1))}><Icon name="minus" size={14}/></button>
                <span className="mono">{qty}</span>
                <button onClick={() => setQty(Math.min(p.stock, qty + 1))}><Icon name="plus" size={14}/></button>
                <span className="mono small" style={{ marginLeft: "auto", color: p.stock < 20 ? "var(--warn)" : "var(--muted)" }}>
                  {p.stock < 20 ? `ÚLTIMAS ${p.stock} UN` : `${p.stock} EM ESTOQUE`}
                </span>
              </div>
            </div>

            <div className="cta-row">
              <button className="btn lg block"
                onClick={() => addToCart(p, qty, { size, color: color.name })}>
                Adicionar ao carrinho · {window.STADIA_UI.BRL(p.price * qty)}
              </button>
              <button className={"btn lg ghost icon-only"} onClick={() => toggleFav(p.id)}>
                <Icon name="heart" size={18} style={{ fill: faved ? "var(--danger)" : "transparent", color: faved ? "var(--danger)" : "currentColor" }}/>
              </button>
            </div>
            <button className="btn lg dark block">
              <Icon name="lightning" size={16}/> Comprar agora · entrega em 24h
            </button>

            <div className="pdp-perks">
              <div className="perk"><Icon name="truck" size={18}/><span><b>Entrega 24h</b><br/>Em capitais via STADIA Express</span></div>
              <div className="perk"><Icon name="shield" size={18}/><span><b>Selo de autenticidade</b><br/>Holograma oficial</span></div>
              <div className="perk"><Icon name="package" size={18}/><span><b>Troca grátis 30d</b><br/>1ª troca sem custo</span></div>
            </div>
          </aside>
        </div>

        {/* Tabs */}
        <section className="pdp-tabs">
          <div className="tab-bar">
            {[
              { id: "desc", l: "Descrição" },
              { id: "specs", l: "Especificações" },
              { id: "reviews", l: `Avaliações (${p.reviews})` },
              { id: "ship", l: "Entrega" },
            ].map((t) => (
              <button key={t.id} className={tab === t.id ? "on" : ""} onClick={() => setTab(t.id)}>
                {t.l}
              </button>
            ))}
          </div>
          <div className="tab-body">
            {tab === "desc" && (
              <div className="tab-desc">
                <p style={{ fontSize: 18, lineHeight: 1.6, maxWidth: 720 }}>{p.desc}</p>
                <div className="hi-grid">
                  {[
                    { t: "Tecido AeroDry", d: "Canais de ventilação no dorso para máxima respirabilidade durante o jogo." },
                    { t: "Modelagem atlética", d: "Caimento ajustado em ombros e gola, com folga estratégica nas laterais." },
                    { t: "Construção sustentável", d: "92% de fibras recicladas; menos 38% de água no processo de tingimento." },
                  ].map((h, i) => (
                    <div key={i} className="hi-cell">
                      <span className="mono small" style={{ color: "var(--muted)" }}>0{i + 1} · FEATURE</span>
                      <h4>{h.t}</h4>
                      <p>{h.d}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {tab === "specs" && (
              <div className="spec-table">
                {[
                  ["Material", p.materials || "Tecido técnico AeroDry"],
                  ["Composição", "92% poliamida reciclada · 8% elastano"],
                  ["Caimento", "Atlético / ajustado"],
                  ["Lavagem", "Máquina, água fria, do avesso"],
                  ["Origem", "Brasil"],
                  ["Drop", p.drop || "MATCHDAY 03"],
                ].map(([k, v]) => (
                  <div key={k} className="spec-row">
                    <span className="mono small" style={{ color: "var(--muted)" }}>{k.toUpperCase()}</span>
                    <span>{v}</span>
                  </div>
                ))}
              </div>
            )}
            {tab === "reviews" && (
              <div className="reviews">
                <div className="rev-summary">
                  <div className="rev-big">
                    <b>{p.rating}</b>
                    <window.STADIA_UI.StarRating value={p.rating} count={p.reviews} size={16} showCount={false}/>
                    <span className="mono small" style={{ color: "var(--muted)" }}>{p.reviews} AVALIAÇÕES VERIFICADAS</span>
                  </div>
                  <div className="rev-bars">
                    {[5, 4, 3, 2, 1].map((s) => (
                      <div key={s} className="rev-bar">
                        <span className="mono">{s}★</span>
                        <div className="bar-track"><div className="bar-fill" style={{ width: `${[78, 16, 4, 1, 1][5 - s]}%` }}/></div>
                        <span className="mono small">{[78, 16, 4, 1, 1][5 - s]}%</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="rev-list">
                  {REVIEWS.map((r) => (
                    <article key={r.id} className="rev-card">
                      <div className="row between">
                        <div className="row" style={{ gap: 12 }}>
                          <div className="ava">{r.name[0]}</div>
                          <div>
                            <div className="row" style={{ gap: 8 }}>
                              <b>{r.name}</b>
                              {r.verified && <span className="chip" style={{ height: 22, color: "var(--accent-3)", borderColor: "var(--accent-3)" }}><Icon name="check" size={10}/> Verificado</span>}
                            </div>
                            <span className="mono small" style={{ color: "var(--muted)" }}>{r.date}</span>
                          </div>
                        </div>
                        <window.STADIA_UI.StarRating value={r.rating} count={0} size={12} showCount={false}/>
                      </div>
                      <p>{r.body}</p>
                    </article>
                  ))}
                </div>
              </div>
            )}
            {tab === "ship" && (
              <div className="ship-grid">
                <div className="ship-card">
                  <Icon name="lightning" size={20}/>
                  <h5>STADIA Express</h5>
                  <p>Entrega no mesmo dia para São Paulo, Rio, BH, Curitiba e Floripa.</p>
                  <span className="mono small" style={{ color: "var(--accent)" }}>R$ 19,90</span>
                </div>
                <div className="ship-card">
                  <Icon name="truck" size={20}/>
                  <h5>Padrão</h5>
                  <p>3 a 7 dias úteis, todo o Brasil. Frete grátis acima de R$ 299.</p>
                  <span className="mono small" style={{ color: "var(--accent-3)" }}>FRETE GRÁTIS</span>
                </div>
                <div className="ship-card">
                  <Icon name="store" size={20}/>
                  <h5>Retire na loja</h5>
                  <p>Disponível em 12 lojas físicas em até 2h após confirmação.</p>
                  <span className="mono small" style={{ color: "var(--accent)" }}>GRÁTIS</span>
                </div>
              </div>
            )}
          </div>
        </section>

        <section style={{ paddingTop: 80 }}>
          <window.STADIA_UI.SectionHead kicker="VOCÊ TAMBÉM PODE GOSTAR" title="Recomendados"/>
          <div className="grid-cards">
            {recs.map((rp) => (
              <ProductCard key={rp.id} p={rp} variant="minimal"
                faved={wishlist.includes(rp.id)}
                onOpen={() => go("pdp", { id: rp.id })}
                onFav={() => toggleFav(rp.id)}
                onAdd={() => addToCart(rp)}/>
            ))}
          </div>
        </section>
      </div>
      <PDPStyles/>
    </main>
  );
}

/* ============================================================
   PDP Spec — full-bleed image left, dossier-style spec right
   ============================================================ */
function PDPSpec({ p, go, addToCart, toggleFav, faved, size, setSize, color, setColor, qty, setQty, tab, setTab, discount, installments, recs, REVIEWS }) {
  return (
    <main className="pdp-main pdp-spec">
      <div className="pdp-spec-grid">
        <section className="pdp-spec-gal img-ph has-viz" style={{ background: p.imageBg }}>
          <STADIA_PRODUCT_VISUAL p={p}/>
          <div className="spec-overlay">
            <div className="spec-corner top-left mono">
              <span>STADIA / SPEC SHEET</span>
              <span style={{ color: "var(--accent-3)" }}>● LIVE STOCK · {p.stock}</span>
            </div>
            <div className="spec-corner top-right mono">
              <span>{p.id.toUpperCase()}</span>
              <span>REV.03 · 26.05</span>
            </div>
            <div className="spec-corner bottom-left mono">
              <div className="big-mono">{p.team || "STD"}</div>
              <span>TEAM CODE</span>
            </div>
            <div className="spec-corner bottom-right mono">
              <div className="big-mono">{p.rating}<span style={{ color: "var(--accent)" }}>★</span></div>
              <span>{p.reviews} REVIEWS</span>
            </div>
          </div>
        </section>

        <aside className="pdp-spec-side">
          <div className="spec-side-inner">
            <nav className="crumb mono" style={{ marginBottom: 24 }}>
              <button onClick={() => go("home")}>STADIA</button>
              <span>/</span>
              <button onClick={() => go("plp", { cat: p.category })}>{p.category.toUpperCase()}</button>
              <span>/</span>
              <span style={{ color: "var(--fg)" }}>{p.id.toUpperCase()}</span>
            </nav>

            <span className="mono small" style={{ color: "var(--accent)", letterSpacing: "0.16em" }}>№ {p.id.replace("p", "").padStart(3, "0")} — {p.drop || "MATCHDAY"}</span>
            <h1 className="display pdp-title" style={{ fontSize: "clamp(36px, 4vw, 56px)" }}>{p.name}</h1>
            <p style={{ color: "var(--fg-2)", lineHeight: 1.6, fontSize: 16 }}>{p.desc}</p>

            <div className="spec-meta-grid">
              <div><span className="mono small">PREÇO</span><b>{window.STADIA_UI.BRL(p.price)}</b></div>
              <div><span className="mono small">PIX 5% OFF</span><b>{window.STADIA_UI.BRL(p.price * 0.95)}</b></div>
              <div><span className="mono small">10X SEM JUROS</span><b>R$ {installments}</b></div>
            </div>

            <div className="opt-block">
              <div className="opt-head"><span className="mono small">COR · {color.name.toUpperCase()}</span></div>
              <div className="row" style={{ gap: 8 }}>
                {p.colors.map((c) => (
                  <button key={c.hex} className={"color-btn " + (color.hex === c.hex ? "on" : "")} onClick={() => setColor(c)}>
                    <span style={{ background: c.hex }}/>
                  </button>
                ))}
              </div>
            </div>

            <div className="opt-block">
              <div className="opt-head">
                <span className="mono small">TAMANHO · {size}</span>
                <button className="opt-link mono small">TABELA DE MEDIDAS</button>
              </div>
              <div className="size-row">
                {p.sizes.map((s) => (
                  <button key={s} className={"size-btn-pdp " + (size === s ? "on" : "")} onClick={() => setSize(s)}>{s}</button>
                ))}
              </div>
            </div>

            <div className="cta-row">
              <button className="btn lg block" onClick={() => addToCart(p, qty, { size, color: color.name })}>
                Adicionar ao carrinho
              </button>
              <button className="btn lg ghost icon-only" onClick={() => toggleFav(p.id)}>
                <Icon name="heart" size={18} style={{ fill: faved ? "var(--danger)" : "transparent", color: faved ? "var(--danger)" : "currentColor" }}/>
              </button>
            </div>

            <div className="spec-list">
              {[
                ["MATERIAL", p.materials || "AeroDry"],
                ["CONSTRUÇÃO", "Termo-soldada · 12 painéis"],
                ["CAIMENTO", "Atlético / Ajustado"],
                ["TESTES DE CAMPO", "240h · 18 jogos"],
                ["DROP", p.drop || "MATCHDAY 03"],
                ["ORIGEM", "Brasil · Ribeirão Preto"],
              ].map(([k, v]) => (
                <div key={k} className="spec-list-row">
                  <span className="mono small" style={{ color: "var(--muted)" }}>{k}</span>
                  <span style={{ borderBottom: "1px dashed var(--line-2)", flex: 1 }}/>
                  <span className="mono">{v}</span>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </div>

      <section className="container" style={{ paddingTop: 80, paddingBottom: 60 }}>
        <window.STADIA_UI.SectionHead kicker="LINHA RELACIONADA" title="Coleção completa"/>
        <div className="grid-cards">
          {recs.map((rp) => (
            <ProductCard key={rp.id} p={rp} variant="minimal"
              faved={wishlist.includes(rp.id)}
              onOpen={() => go("pdp", { id: rp.id })}
              onFav={() => toggleFav(rp.id)}
              onAdd={() => addToCart(rp)}/>
          ))}
        </div>
      </section>

      <PDPStyles/>
    </main>
  );
}

function PDPStyles() {
  return (
    <style>{`
      .pdp-main { padding-bottom: 60px; }
      .pdp-grid {
        display: grid;
        grid-template-columns: 1fr 480px;
        gap: 80px;
        align-items: start;
        padding-top: 12px;
      }
      [data-viewport="mobile"] .pdp-grid { grid-template-columns: 1fr; gap: 24px; }
      @media (max-width: 1100px) { .pdp-grid { grid-template-columns: 1fr; gap: 32px; } }

      .pdp-gallery { display: grid; grid-template-columns: 80px 1fr; gap: 16px; }
      [data-viewport="mobile"] .pdp-gallery { grid-template-columns: 1fr; }
      .gal-thumbs { display: flex; flex-direction: column; gap: 8px; }
      [data-viewport="mobile"] .gal-thumbs { flex-direction: row; }
      .gal-thumb {
        background: transparent; border: 1px solid var(--line);
        border-radius: 8px; overflow: hidden; padding: 0;
        aspect-ratio: 1; cursor: pointer;
      }
      .gal-thumb.on { border-color: var(--accent); }
      .gal-main {
        position: relative;
        aspect-ratio: 4/5;
        border-radius: var(--r-md);
        border: 1px solid var(--line);
      }
      .gal-fav {
        position: absolute; top: 16px; right: 16px;
        width: 44px; height: 44px;
        border-radius: 50%;
        border: 1px solid var(--line-2);
        background: color-mix(in oklab, var(--bg-0) 70%, transparent);
        color: var(--fg);
        backdrop-filter: blur(8px);
        display: grid; place-items: center;
      }
      .gal-fav[data-on="1"] { color: var(--danger); border-color: var(--danger); }
      .gal-fav[data-on="1"] svg { fill: var(--danger); }

      .pdp-side { position: sticky; top: 100px; }
      [data-viewport="mobile"] .pdp-side, @media (max-width: 1100px) { .pdp-side { position: static; } }
      .pdp-title {
        margin: 12px 0 14px;
        font-size: clamp(36px, 4vw, 52px);
        letter-spacing: -0.03em;
      }
      .pdp-price {
        display: flex; align-items: baseline; gap: 12px;
        margin-top: 24px;
      }
      .pdp-price .cur { font-family: var(--font-display); font-size: 40px; font-weight: 700; letter-spacing: -0.03em; color: var(--fg); }
      .pdp-price .old { color: var(--muted); text-decoration: line-through; font-size: 16px; }
      .pdp-price .off {
        background: var(--accent); color: var(--accent-ink);
        padding: 4px 10px; border-radius: 4px;
        font-family: var(--font-mono); font-size: 12px; font-weight: 700;
      }
      .pix-line { display: inline-flex; align-items: center; gap: 6px; color: var(--accent-3); margin-top: 8px; }

      .pdp-divider { height: 1px; background: var(--line); margin: 32px 0; }

      .opt-block { display: flex; flex-direction: column; gap: 12px; margin-bottom: 24px; }
      .opt-head { display: flex; align-items: center; justify-content: space-between; }
      .opt-link { background: transparent; border: 0; color: var(--accent); padding: 0; }
      .color-btn {
        width: 44px; height: 44px;
        background: var(--surface); border: 1px solid var(--line-2);
        border-radius: 50%; padding: 4px;
      }
      .color-btn span { display: block; width: 100%; height: 100%; border-radius: 50%; }
      .color-btn.on { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent); }
      .size-row { display: flex; gap: 8px; flex-wrap: wrap; }
      .size-btn-pdp {
        padding: 0 16px; height: 44px; min-width: 56px;
        background: var(--surface); border: 1px solid var(--line-2);
        color: var(--fg); border-radius: 8px;
        font-family: var(--font-mono); font-size: 13px;
      }
      .size-btn-pdp.on { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }
      .qty {
        display: flex; align-items: center; gap: 12px;
        height: 44px; padding: 0 12px;
        background: var(--surface); border: 1px solid var(--line-2);
        border-radius: 999px;
      }
      .qty button { width: 28px; height: 28px; background: transparent; border: 0; color: var(--fg); border-radius: 50%; }
      .qty button:hover { background: var(--bg-3); }
      .qty .mono { min-width: 24px; text-align: center; font-size: 16px; font-weight: 600; }

      .cta-row { display: flex; gap: 8px; margin: 16px 0 8px; }
      .icon-only { width: 56px; flex: none; padding: 0; }

      .pdp-perks { display: flex; flex-direction: column; gap: 14px; margin-top: 32px; padding-top: 24px; border-top: 1px solid var(--line); }
      .perk { display: flex; align-items: center; gap: 14px; color: var(--fg-2); font-size: 13px; }
      .perk svg { color: var(--accent); flex-shrink: 0; }
      .perk b { color: var(--fg); font-weight: 600; }

      .pdp-tabs { margin-top: 80px; }
      .tab-bar { display: flex; gap: 24px; border-bottom: 1px solid var(--line); margin-bottom: 32px; overflow: auto; }
      .tab-bar button {
        background: transparent; border: 0; color: var(--muted);
        font-family: var(--font-display); font-size: 16px; font-weight: 600;
        padding: 16px 0; border-bottom: 2px solid transparent;
        white-space: nowrap;
      }
      .tab-bar button.on { color: var(--fg); border-color: var(--accent); }
      .hi-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; margin-top: 32px; }
      @media (max-width: 800px) { .hi-grid { grid-template-columns: 1fr; } }
      .hi-cell { padding: 24px; background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-md); }
      .hi-cell h4 { margin: 8px 0; font-family: var(--font-display); font-size: 18px; font-weight: 700; }
      .hi-cell p { margin: 0; color: var(--muted); font-size: 14px; line-height: 1.6; }

      .spec-table { display: grid; grid-template-columns: 1fr 1fr; gap: 0; max-width: 720px; }
      @media (max-width: 600px) { .spec-table { grid-template-columns: 1fr; } }
      .spec-row { display: flex; flex-direction: column; gap: 4px; padding: 16px 0; border-bottom: 1px solid var(--line); padding-right: 32px; }

      .reviews { display: grid; grid-template-columns: 280px 1fr; gap: 64px; }
      @media (max-width: 900px) { .reviews { grid-template-columns: 1fr; gap: 32px; } }
      .rev-summary { display: flex; flex-direction: column; gap: 24px; }
      .rev-big { display: flex; flex-direction: column; gap: 8px; }
      .rev-big b { font-family: var(--font-display); font-size: 64px; font-weight: 700; line-height: 1; letter-spacing: -0.04em; }
      .rev-bars { display: flex; flex-direction: column; gap: 8px; }
      .rev-bar { display: grid; grid-template-columns: 24px 1fr 36px; gap: 12px; align-items: center; font-size: 12px; color: var(--muted); }
      .bar-track { height: 4px; background: var(--bg-3); border-radius: 999px; overflow: hidden; }
      .bar-fill { height: 100%; background: var(--accent); }
      .rev-list { display: flex; flex-direction: column; gap: 16px; }
      .rev-card { padding: 20px; background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-md); }
      .rev-card p { margin: 12px 0 0; color: var(--fg-2); line-height: 1.6; }
      .ava { width: 36px; height: 36px; border-radius: 50%; background: var(--accent); color: var(--accent-ink); display: grid; place-items: center; font-weight: 700; }

      .ship-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
      @media (max-width: 800px) { .ship-grid { grid-template-columns: 1fr; } }
      .ship-card { padding: 24px; background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-md); }
      .ship-card svg { color: var(--accent); margin-bottom: 12px; }
      .ship-card h5 { margin: 0; font-family: var(--font-display); font-size: 18px; font-weight: 700; }
      .ship-card p { margin: 8px 0 12px; color: var(--muted); font-size: 13px; line-height: 1.5; }

      .grid-cards {
        display: grid; grid-template-columns: repeat(4, 1fr); gap: 24px;
      }
      @media (max-width: 1100px) { .grid-cards { grid-template-columns: repeat(2, 1fr); } }
      [data-viewport="mobile"] .grid-cards { grid-template-columns: repeat(2, 1fr); gap: 12px; }

      /* SPEC variant */
      .pdp-spec { padding-top: 0; }
      .pdp-spec-grid {
        display: grid; grid-template-columns: 1fr 540px;
        min-height: 100vh;
        background: var(--bg-0);
      }
      @media (max-width: 1100px) { .pdp-spec-grid { grid-template-columns: 1fr; } }
      .pdp-spec-gal {
        position: relative;
        min-height: 100vh;
        border-radius: 0;
      }
      [data-viewport="mobile"] .pdp-spec-gal { min-height: 60vh; }
      @media (max-width: 1100px) { .pdp-spec-gal { min-height: 60vh; } }
      .spec-overlay {
        position: absolute; inset: 0;
        padding: 32px;
        display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr;
        pointer-events: none;
      }
      .spec-corner {
        display: flex; flex-direction: column; gap: 4px;
        font-size: 11px; letter-spacing: 0.14em;
        color: rgba(255, 255, 255, .85);
      }
      .spec-corner.top-right, .spec-corner.bottom-right { align-items: flex-end; text-align: right; }
      .spec-corner.bottom-left, .spec-corner.bottom-right { align-self: end; }
      .big-mono {
        font-family: var(--font-display);
        font-size: 56px;
        font-weight: 800;
        letter-spacing: -0.04em;
        color: white;
        line-height: 1;
        text-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
      }
      .pdp-spec-side {
        background: var(--bg-1);
        border-left: 1px solid var(--line);
        max-height: 100vh; overflow: auto;
        position: sticky; top: 0;
      }
      @media (max-width: 1100px) { .pdp-spec-side { max-height: none; position: static; } }
      .spec-side-inner { padding: 48px 40px; }
      .spec-meta-grid {
        display: grid; grid-template-columns: 1fr 1fr 1fr;
        gap: 16px; padding: 24px 0;
        border-top: 1px solid var(--line);
        border-bottom: 1px solid var(--line);
        margin: 32px 0;
      }
      .spec-meta-grid > div { display: flex; flex-direction: column; gap: 4px; }
      .spec-meta-grid b { font-family: var(--font-display); font-size: 20px; font-weight: 700; letter-spacing: -0.02em; }
      .spec-list { display: flex; flex-direction: column; gap: 0; margin-top: 32px; }
      .spec-list-row {
        display: flex; align-items: baseline; gap: 12px;
        padding: 10px 0;
        font-size: 13px;
      }
      .spec-list-row .mono { font-size: 12px; }
    `}</style>
  );
}

window.STADIA_PDP = PDP;
