// STADIA — shared components

const { useState, useEffect, useRef, useMemo, useCallback } = React;

/* ============================================================
   Format helpers
   ============================================================ */
const BRL = (n) => n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const cls = (...args) => args.filter(Boolean).join(" ");

/* ============================================================
   Header — top navigation bar
   ============================================================ */
function Header({ route, go, cart, wishlist, user, density }) {
  const cartCount = cart.reduce((s, i) => s + i.qty, 0);
  const [searchOpen, setSearchOpen] = useState(false);
  const [q, setQ] = useState("");
  return (
    <>
      {/* top ticker */}
      <div className="ticker desktop-only">
        <div className="ticker-track">
          {Array.from({ length: 2 }).map((_, k) => (
            <div className="ticker-row" key={k}>
              <span><Icon name="lightning" size={12}/> ENTREGA EXPRESSA · 24H EM CAPITAIS</span>
              <span className="dot">●</span>
              <span>FRETE GRÁTIS ACIMA DE R$ 299</span>
              <span className="dot">●</span>
              <span><Icon name="badge-check" size={12}/> KITS LICENCIADOS · SELO HOLOGRÁFICO</span>
              <span className="dot">●</span>
              <span>10X SEM JUROS NO PIX OU CARTÃO</span>
              <span className="dot">●</span>
              <span><Icon name="lightning" size={12}/> DROP MATCHDAY 03 — AO VIVO</span>
              <span className="dot">●</span>
            </div>
          ))}
        </div>
      </div>

      <header className="topnav">
        <div className="container topnav-inner">
          <button className="iconbtn mobile-only" onClick={() => go("menu")} aria-label="Menu">
            <Icon name="menu"/>
          </button>

          <button className="brand" onClick={() => go("home")} aria-label="STADIA — Home">
            <span className="brand-mark"></span>
            <span className="brand-word">STADIA</span>
            <span className="brand-sup">/26</span>
          </button>

          <nav className="topnav-links desktop-only">
            <button onClick={() => go("plp", { cat: "camisas" })}>Camisas</button>
            <button onClick={() => go("plp", { cat: "chuteiras" })}>Chuteiras</button>
            <button onClick={() => go("plp", { cat: "treino" })}>Treino</button>
            <button onClick={() => go("plp", { cat: "bolas" })}>Bolas</button>
            <button onClick={() => go("plp", { cat: "acessorios" })}>Acessórios</button>
            <button onClick={() => go("plp", { cat: "femme" })} className="hl">Femme<span className="dot-accent"/></button>
            <button onClick={() => go("plp", { cat: "all", filter: "drop" })}>
              <span className="chip live" style={{height: 22, padding: "0 8px"}}>DROP</span>
            </button>
          </nav>

          <div className="topnav-actions">
            <button className="iconbtn desktop-only" onClick={() => setSearchOpen(true)} aria-label="Buscar">
              <Icon name="search"/>
            </button>
            <button className="iconbtn desktop-only" onClick={() => go("account", { tab: "wishlist" })} aria-label="Favoritos">
              <Icon name="heart"/>
              {wishlist.length > 0 && <span className="badge">{wishlist.length}</span>}
            </button>
            <button className="iconbtn" onClick={() => user ? go("account") : go("auth")} aria-label="Conta">
              <Icon name="user"/>
            </button>
            <button className="iconbtn cart" onClick={() => go("cart")} aria-label="Carrinho">
              <Icon name="bag"/>
              {cartCount > 0 && <span className="badge accent">{cartCount}</span>}
            </button>
          </div>
        </div>
      </header>

      {searchOpen && <SearchOverlay q={q} setQ={setQ} onClose={() => setSearchOpen(false)} go={go}/>}

      <style>{`
        .ticker {
          height: 32px;
          overflow: hidden;
          background: var(--bg-3);
          border-bottom: 1px solid var(--line);
          font-family: var(--font-mono);
          font-size: 11px;
          letter-spacing: 0.14em;
          text-transform: uppercase;
          color: var(--fg-2);
          position: relative;
        }
        .ticker::before, .ticker::after {
          content: "";
          position: absolute;
          top: 0; bottom: 0; width: 60px; z-index: 2;
          pointer-events: none;
        }
        .ticker::before { left: 0; background: linear-gradient(90deg, var(--bg-3), transparent); }
        .ticker::after { right: 0; background: linear-gradient(-90deg, var(--bg-3), transparent); }
        .ticker-track {
          display: flex;
          width: max-content;
          animation: ticker 70s linear infinite;
          height: 100%;
        }
        .ticker-row {
          display: flex; align-items: center; gap: 24px;
          padding: 0 24px;
          white-space: nowrap;
        }
        .ticker-row span { display: inline-flex; align-items: center; gap: 6px; }
        .ticker-row .dot { color: var(--accent); }

        .topnav {
          position: sticky; top: 0; z-index: 50;
          background: color-mix(in oklab, var(--bg-0) 78%, transparent);
          backdrop-filter: blur(20px) saturate(140%);
          -webkit-backdrop-filter: blur(20px) saturate(140%);
          border-bottom: 1px solid var(--line);
        }
        .topnav-inner {
          display: grid;
          grid-template-columns: auto 1fr auto;
          align-items: center;
          gap: 24px;
          height: 68px;
        }
        [data-viewport="mobile"] .topnav-inner { height: 56px; gap: 8px; }
        .brand {
          display: inline-flex; align-items: baseline; gap: 6px;
          background: transparent; border: 0; color: inherit;
          font-family: var(--font-display);
          font-weight: 700;
          font-size: 22px;
          letter-spacing: -0.04em;
          padding: 0;
        }
        .brand-mark {
          display: inline-block; width: 22px; height: 22px;
          background: var(--accent);
          clip-path: polygon(0 0, 100% 0, 100% 60%, 60% 100%, 0 100%);
          transform: translateY(2px);
          margin-right: 4px;
        }
        .brand-sup {
          font-family: var(--font-mono);
          font-size: 11px;
          letter-spacing: 0.1em;
          color: var(--muted);
          text-transform: uppercase;
        }
        .topnav-links {
          display: flex; gap: 4px; align-items: center;
          justify-self: center;
        }
        .topnav-links button {
          background: transparent; border: 0;
          color: var(--fg-2); font-family: var(--font-display);
          font-weight: 600; font-size: 14px;
          padding: 8px 14px; border-radius: 999px;
          letter-spacing: 0.01em;
          position: relative;
          display: inline-flex; align-items: center; gap: 6px;
        }
        .topnav-links button:hover { color: var(--fg); background: var(--surface); }
        .topnav-links .hl { color: var(--accent); }
        .topnav-links .dot-accent { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
        .topnav-actions {
          display: inline-flex; align-items: center; gap: 4px;
          justify-self: end;
        }
        .iconbtn {
          position: relative;
          width: 40px; height: 40px;
          border-radius: 50%;
          background: transparent; border: 0;
          color: var(--fg);
          display: grid; place-items: center;
          transition: background 0.15s;
        }
        .iconbtn:hover { background: var(--surface); }
        .iconbtn .badge {
          position: absolute; top: 4px; right: 4px;
          min-width: 18px; height: 18px; padding: 0 5px;
          border-radius: 999px;
          background: var(--bg-3); color: var(--fg);
          font-family: var(--font-mono); font-size: 10px;
          display: grid; place-items: center;
          border: 1px solid var(--bg-0);
          font-weight: 600;
        }
        .iconbtn .badge.accent { background: var(--accent); color: var(--accent-ink); }

        .desktop-only { display: inline-flex !important; }
        .mobile-only { display: none !important; }
        @media (max-width: 900px) {
          .ticker { display: none; }
          .desktop-only { display: none !important; }
          .mobile-only { display: inline-flex !important; }
          .topnav-links.desktop-only { display: none !important; }
        }
      `}</style>
    </>
  );
}

/* ============================================================
   Search overlay
   ============================================================ */
function SearchOverlay({ q, setQ, onClose, go }) {
  const inputRef = useRef(null);
  const { PRODUCTS } = window.STADIA_DATA;

  useEffect(() => { inputRef.current?.focus(); }, []);
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const trending = ["camisa volturi", "chuteira hyperblade", "meião pro", "femme orsa", "matchday drop"];
  const results = useMemo(() => {
    if (!q.trim()) return [];
    const s = q.toLowerCase();
    return PRODUCTS.filter(p =>
      p.name.toLowerCase().includes(s) || p.sub.toLowerCase().includes(s) || p.category.includes(s)
    ).slice(0, 6);
  }, [q]);

  return (
    <div className="search-overlay" onClick={onClose}>
      <div className="search-panel" onClick={e => e.stopPropagation()}>
        <div className="search-bar">
          <Icon name="search" size={20}/>
          <input ref={inputRef} value={q} onChange={e => setQ(e.target.value)}
                 placeholder="Buscar produto, time, categoria..." />
          <kbd className="kbd">ESC</kbd>
        </div>

        <div className="search-body">
          {!q.trim() ? (
            <>
              <div className="eyebrow" style={{padding: "8px 24px 12px"}}>Trending agora</div>
              <ul className="search-list">
                {trending.map((t, i) => (
                  <li key={t} onClick={() => setQ(t)}>
                    <span className="num mono">0{i+1}</span>
                    <span>{t}</span>
                    <Icon name="arrow-up-right" size={14}/>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <>
              <div className="eyebrow" style={{padding: "8px 24px 12px"}}>{results.length} resultados</div>
              <ul className="search-results">
                {results.map(p => (
                  <li key={p.id} onClick={() => { onClose(); go("pdp", { id: p.id }); }}>
                    <div className="thumb img-ph has-viz" style={{background: p.imageBg}}><STADIA_PRODUCT_VISUAL p={p}/></div>
                    <div className="info">
                      <div className="nm">{p.name}</div>
                      <div className="sub">{p.sub}</div>
                    </div>
                    <div className="pr mono">{BRL(p.price)}</div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>

      <style>{`
        .search-overlay {
          position: fixed; inset: 0; z-index: 100;
          background: color-mix(in oklab, var(--bg-0) 70%, transparent);
          backdrop-filter: blur(8px);
          animation: fade-in 0.2s ease;
          display: flex; justify-content: center; align-items: flex-start;
          padding-top: 10vh;
        }
        .search-panel {
          width: min(720px, calc(100% - 32px));
          background: var(--surface); border: 1px solid var(--line-2);
          border-radius: var(--r-md);
          box-shadow: var(--shadow-2);
          animation: fade-up 0.25s ease;
          overflow: hidden;
        }
        .search-bar {
          display: flex; align-items: center; gap: 14px;
          padding: 0 20px; height: 64px;
          border-bottom: 1px solid var(--line);
          color: var(--muted);
        }
        .search-bar input {
          flex: 1; background: transparent; border: 0; outline: none;
          font-size: 17px; color: var(--fg);
        }
        .kbd {
          font-family: var(--font-mono); font-size: 10px;
          padding: 4px 8px; border: 1px solid var(--line-2); border-radius: 4px;
          color: var(--muted);
        }
        .search-body { max-height: 420px; overflow: auto; padding-bottom: 12px; }
        .search-list {
          margin: 0; padding: 0; list-style: none;
        }
        .search-list li {
          display: flex; align-items: center; gap: 16px;
          padding: 14px 24px;
          color: var(--fg-2);
          font-size: 14px;
          border-bottom: 1px solid var(--line);
        }
        .search-list li:last-child { border: 0; }
        .search-list li:hover { background: var(--surface-2); color: var(--fg); }
        .search-list .num { color: var(--muted); font-size: 11px; min-width: 24px; }
        .search-list li > span:nth-child(2) { flex: 1; text-transform: lowercase; }
        .search-list li svg { color: var(--muted); }
        .search-results { margin: 0; padding: 0; list-style: none; }
        .search-results li {
          display: grid; grid-template-columns: 48px 1fr auto;
          gap: 14px; align-items: center;
          padding: 12px 24px;
          border-bottom: 1px solid var(--line);
        }
        .search-results li:hover { background: var(--surface-2); }
        .search-results .thumb { width: 48px; height: 48px; border-radius: 6px; }
        .search-results .nm { font-weight: 600; }
        .search-results .sub { font-size: 12px; color: var(--muted); }
        .search-results .pr { font-weight: 700; color: var(--accent); }
      `}</style>
    </div>
  );
}

/* ============================================================
   ProductCard — accepts variant
   ============================================================ */
function ProductCard({ p, variant = "minimal", onOpen, onFav, onAdd, faved }) {
  const discount = p.listPrice > p.price ? Math.round((1 - p.price / p.listPrice) * 100) : 0;

  if (variant === "data") return <ProductCardData p={p} discount={discount} onOpen={onOpen} onFav={onFav} faved={faved}/>;
  if (variant === "editorial") return <ProductCardEditorial p={p} discount={discount} onOpen={onOpen} onFav={onFav} faved={faved}/>;
  return <ProductCardMinimal p={p} discount={discount} onOpen={onOpen} onFav={onFav} onAdd={onAdd} faved={faved}/>;
}

function ProductCardMinimal({ p, discount, onOpen, onFav, onAdd, faved }) {
  return (
    <article className="pcard pcard-min">
      <div className="pcard-media img-ph has-viz" style={{ background: p.imageBg }} onClick={onOpen}>
        <STADIA_PRODUCT_VISUAL p={p}/>
        {p.badge && <span className={`pbadge bg-${p.badge}`}>{p.badge}</span>}
        <button className="pcard-fav" data-on={faved ? "1" : "0"} onClick={(e) => { e.stopPropagation(); onFav(); }} aria-label="Favoritar">
          <Icon name="heart" size={16}/>
        </button>
        <button className="pcard-quick" onClick={(e) => { e.stopPropagation(); onAdd(); }}>
          + Adicionar
        </button>
      </div>
      <div className="pcard-body" onClick={onOpen}>
        <div className="pcard-meta mono">{p.sub}</div>
        <h3 className="pcard-title">{p.name}</h3>
        <div className="pcard-price">
          <span className="cur mono">{BRL(p.price)}</span>
          {discount > 0 && <span className="old mono">{BRL(p.listPrice)}</span>}
          {discount > 0 && <span className="off mono">−{discount}%</span>}
        </div>
        <div className="pcard-colors">
          {p.colors.map((c) => (
            <span key={c.hex} className="cdot" style={{ background: c.hex }} title={c.name}/>
          ))}
        </div>
      </div>
      <ProductCardStyles/>
    </article>
  );
}

function ProductCardData({ p, discount, onOpen, onFav, faved }) {
  return (
    <article className="pcard pcard-data" onClick={onOpen}>
      <div className="pcard-data-head mono">
        <span>{p.id.toUpperCase()}</span>
        <span>·</span>
        <span>{p.team || "STD"}</span>
        <span style={{flex: 1}}/>
        <button className="pcard-fav-flat" onClick={(e) => { e.stopPropagation(); onFav(); }} data-on={faved ? "1" : "0"}>
          <Icon name="heart" size={14}/>
        </button>
      </div>
      <div className="pcard-media img-ph has-viz" style={{ background: p.imageBg }}>
        <STADIA_PRODUCT_VISUAL p={p}/>
        {p.badge && <span className={`pbadge bg-${p.badge}`}>{p.badge}</span>}
      </div>
      <div className="pcard-body">
        <h3 className="pcard-title">{p.name}</h3>
        <div className="pcard-stats">
          <div><span className="k">PREÇO</span><span className="v">{BRL(p.price)}</span></div>
          <div><span className="k">RATING</span><span className="v">{p.rating} ★</span></div>
          <div><span className="k">ESTOQUE</span><span className="v">{p.stock} un</span></div>
        </div>
        {discount > 0 && (
          <div className="pcard-strip mono">
            <span>−{discount}%</span><span>OFF · TIME LIMITED</span>
          </div>
        )}
      </div>
      <ProductCardStyles/>
    </article>
  );
}

function ProductCardEditorial({ p, discount, onOpen, onFav, faved }) {
  return (
    <article className="pcard pcard-edi" onClick={onOpen}>
      <div className="pcard-media img-ph tall has-viz" style={{ background: p.imageBg }}>
        <STADIA_PRODUCT_VISUAL p={p}/>
        <div className="edi-overlay">
          <span className="num mono">№ {p.id.replace("p", "")}</span>
          <button className="pcard-fav-flat light" onClick={(e) => { e.stopPropagation(); onFav(); }} data-on={faved ? "1" : "0"}>
            <Icon name="heart" size={14}/>
          </button>
        </div>
      </div>
      <div className="pcard-body">
        <div className="row between">
          <div>
            <h3 className="pcard-title edi">{p.name}</h3>
            <div className="pcard-meta mono">{p.drop || p.sub}</div>
          </div>
          <span className="pcard-price-edi mono">{BRL(p.price)}</span>
        </div>
      </div>
      <ProductCardStyles/>
    </article>
  );
}

function ProductCardStyles() {
  return (
    <style>{`
      .pcard {
        position: relative;
        cursor: pointer;
        transition: transform 0.2s;
      }
      .pcard:hover .pcard-media { border-color: var(--line-2); }
      .pcard:hover .pcard-quick { transform: translateY(0); opacity: 1; }
      .pcard-media {
        position: relative;
        aspect-ratio: 4/5;
        border-radius: var(--r-md);
        border: 1px solid var(--line);
        overflow: hidden;
      }
      .pcard-media.tall { aspect-ratio: 3/4.4; }
      .pcard-body { padding: 14px 4px 0; display: flex; flex-direction: column; gap: 6px; }
      .pcard-meta {
        font-family: var(--font-mono);
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--muted);
      }
      .pcard-title {
        margin: 0;
        font-family: var(--font-display);
        font-size: 16px;
        font-weight: 600;
        letter-spacing: -0.01em;
        color: var(--fg);
        text-wrap: balance;
      }
      .pcard-title.edi {
        font-family: 'Instrument Serif', Georgia, serif;
        font-style: italic;
        font-weight: 400;
        font-size: 22px;
      }
      .pcard-price { display: flex; align-items: baseline; gap: 8px; }
      .pcard-price .cur { font-weight: 700; font-size: 15px; }
      .pcard-price .old { color: var(--muted); text-decoration: line-through; font-size: 12px; }
      .pcard-price .off { color: var(--accent); font-size: 11px; font-weight: 600; }
      .pcard-price-edi { font-weight: 600; font-size: 14px; color: var(--fg); }
      .pcard-colors { display: flex; gap: 4px; margin-top: 2px; }
      .cdot { width: 12px; height: 12px; border-radius: 50%; border: 1px solid var(--line-2); }

      .pbadge {
        position: absolute; top: 12px; left: 12px;
        font-family: var(--font-mono);
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        padding: 4px 8px;
        border-radius: 4px;
      }
      .pbadge.bg-drop { background: var(--accent); color: var(--accent-ink); }
      .pbadge.bg-elite { background: var(--bg-0); color: var(--fg); border: 1px solid var(--accent-2); color: var(--accent-2); }
      .pbadge.bg-deal { background: var(--danger); color: white; }
      .pbadge.bg-new { background: var(--accent-3); color: var(--accent-ink); }

      .pcard-fav {
        position: absolute; top: 12px; right: 12px;
        width: 32px; height: 32px;
        border-radius: 50%;
        border: 1px solid var(--line-2);
        background: color-mix(in oklab, var(--bg-0) 70%, transparent);
        color: var(--fg);
        display: grid; place-items: center;
        backdrop-filter: blur(8px);
      }
      .pcard-fav[data-on="1"] { color: var(--danger); border-color: var(--danger); }
      .pcard-fav[data-on="1"] svg { fill: var(--danger); }
      .pcard-fav-flat {
        background: transparent; border: 0; color: var(--muted);
        padding: 4px; border-radius: 4px;
      }
      .pcard-fav-flat[data-on="1"] { color: var(--danger); }
      .pcard-fav-flat[data-on="1"] svg { fill: var(--danger); }
      .pcard-fav-flat.light { color: rgba(255,255,255,.85); }

      .pcard-quick {
        position: absolute; left: 12px; right: 12px; bottom: 12px;
        height: 38px; border-radius: 999px;
        background: var(--accent);
        color: var(--accent-ink);
        font-family: var(--font-display);
        font-weight: 700;
        font-size: 13px;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        border: 0;
        opacity: 0; transform: translateY(8px);
        transition: opacity 0.2s, transform 0.2s;
      }
      .pcard-quick:hover { background: color-mix(in oklab, var(--accent) 90%, white); }

      /* data variant */
      .pcard-data {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: var(--r-md);
        padding: 12px;
        display: flex; flex-direction: column; gap: 12px;
      }
      .pcard-data:hover { border-color: var(--line-2); }
      .pcard-data .pcard-media { aspect-ratio: 1.2/1; border-radius: var(--r-sm); }
      .pcard-data-head {
        display: flex; align-items: center; gap: 6px;
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: var(--muted);
      }
      .pcard-data .pcard-body { padding: 0; }
      .pcard-stats {
        display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 4px;
        margin-top: 4px;
        border-top: 1px solid var(--line);
        padding-top: 8px;
      }
      .pcard-stats > div {
        display: flex; flex-direction: column; gap: 2px;
        padding-right: 6px;
      }
      .pcard-stats .k {
        font-family: var(--font-mono);
        font-size: 9px;
        text-transform: uppercase;
        color: var(--muted);
        letter-spacing: 0.12em;
      }
      .pcard-stats .v {
        font-family: var(--font-mono);
        font-size: 12px;
        font-weight: 600;
        color: var(--fg);
      }
      .pcard-strip {
        display: flex; justify-content: space-between;
        background: var(--accent); color: var(--accent-ink);
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 0.14em;
        padding: 6px 10px;
        border-radius: 4px;
        text-transform: uppercase;
      }

      /* editorial */
      .pcard-edi .pcard-body { padding: 16px 0 0; }
      .pcard-edi .edi-overlay {
        position: absolute; inset: 12px;
        display: flex; justify-content: space-between; align-items: flex-start;
        color: white;
      }
      .pcard-edi .edi-overlay .num { font-size: 11px; letter-spacing: 0.18em; }
    `}</style>
  );
}

/* ============================================================
   Drawer / Side panel
   ============================================================ */
function Drawer({ open, onClose, side = "right", width = 440, children, title, footer }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="drawer-bg" onClick={onClose}>
      <aside className={`drawer drawer-${side}`} style={{ maxWidth: width }} onClick={e => e.stopPropagation()}>
        <header className="drawer-head">
          <h3>{title}</h3>
          <button className="iconbtn" onClick={onClose} aria-label="Fechar"><Icon name="x"/></button>
        </header>
        <div className="drawer-body">{children}</div>
        {footer && <div className="drawer-foot">{footer}</div>}
      </aside>
      <style>{`
        .drawer-bg {
          position: fixed; inset: 0; z-index: 90;
          background: color-mix(in oklab, var(--bg-0) 60%, transparent);
          backdrop-filter: blur(6px);
          display: flex; animation: fade-in 0.15s ease;
        }
        .drawer { background: var(--bg-1); height: 100%; display: flex; flex-direction: column;
          width: 100%; border-left: 1px solid var(--line); animation: slide-in 0.25s cubic-bezier(.3,.7,.4,1); }
        .drawer-right { margin-left: auto; }
        .drawer-left { margin-right: auto; border-left: 0; border-right: 1px solid var(--line); animation: slide-in-l 0.25s cubic-bezier(.3,.7,.4,1); }
        .drawer-head {
          display: flex; align-items: center; justify-content: space-between;
          padding: 18px 24px; border-bottom: 1px solid var(--line);
        }
        .drawer-head h3 { margin: 0; font-family: var(--font-display); font-size: 20px; font-weight: 700; letter-spacing: -0.02em; }
        .drawer-body { flex: 1; overflow: auto; padding: 24px; }
        .drawer-foot { border-top: 1px solid var(--line); padding: 20px 24px; background: var(--surface); }
        @keyframes slide-in { from { transform: translateX(100%); } to { transform: translateX(0); } }
        @keyframes slide-in-l { from { transform: translateX(-100%); } to { transform: translateX(0); } }
      `}</style>
    </div>
  );
}

/* ============================================================
   Toast
   ============================================================ */
function Toast({ items, dismiss }) {
  return (
    <div className="toast-stack">
      {items.map(t => (
        <div key={t.id} className={`toast toast-${t.kind || "info"}`}>
          <Icon name={t.kind === "success" ? "check" : t.kind === "error" ? "alert" : "info"} size={16}/>
          <span>{t.message}</span>
          <button onClick={() => dismiss(t.id)}><Icon name="x" size={14}/></button>
        </div>
      ))}
      <style>{`
        .toast-stack { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); z-index: 200; display: flex; flex-direction: column-reverse; gap: 8px; pointer-events: none; }
        .toast {
          display: inline-flex; align-items: center; gap: 12px;
          padding: 12px 14px 12px 16px;
          background: var(--surface);
          border: 1px solid var(--line-2);
          border-radius: var(--r-pill);
          box-shadow: var(--shadow-2);
          color: var(--fg);
          font-size: 14px;
          pointer-events: all;
          animation: fade-up 0.2s ease;
        }
        .toast-success { border-color: var(--accent-3); color: var(--accent-3); }
        .toast-error { border-color: var(--danger); color: var(--danger); }
        .toast button { background: transparent; border: 0; color: inherit; padding: 4px; opacity: 0.5; }
        .toast button:hover { opacity: 1; }
      `}</style>
    </div>
  );
}

/* ============================================================
   Footer
   ============================================================ */
function Footer({ go }) {
  return (
    <footer className="footer">
      <div className="container">
        <div className="footer-grid">
          <div className="footer-brand">
            <div className="brand">
              <span className="brand-mark"></span>
              <span className="brand-word">STADIA</span>
            </div>
            <p className="footer-blurb">
              Marketplace de futebol e esportes coletivos. Kits oficiais, equipamento de alto rendimento, drops semanais.
            </p>
            <div className="footer-newsletter">
              <input className="input" placeholder="seu@email.com"/>
              <button className="btn">Assinar drops</button>
            </div>
          </div>
          <div>
            <h5>Loja</h5>
            <ul>
              <li><button onClick={() => go("plp", { cat: "camisas" })}>Camisas</button></li>
              <li><button onClick={() => go("plp", { cat: "chuteiras" })}>Chuteiras</button></li>
              <li><button onClick={() => go("plp", { cat: "treino" })}>Treino</button></li>
              <li><button onClick={() => go("plp", { cat: "femme" })}>Femme</button></li>
              <li><button onClick={() => go("plp", { cat: "all", filter: "drop" })}>Drops</button></li>
            </ul>
          </div>
          <div>
            <h5>Conta</h5>
            <ul>
              <li><button onClick={() => go("account")}>Pedidos</button></li>
              <li><button onClick={() => go("account", { tab: "addresses" })}>Endereços</button></li>
              <li><button onClick={() => go("account", { tab: "wishlist" })}>Wishlist</button></li>
              <li><button onClick={() => go("auth")}>Entrar / Cadastrar</button></li>
            </ul>
          </div>
          <div>
            <h5>Suporte</h5>
            <ul>
              <li><button>Central de ajuda</button></li>
              <li><button>Trocas e devoluções</button></li>
              <li><button>Frete e prazo</button></li>
              <li><button>Tabela de medidas</button></li>
              <li><button>Fale conosco</button></li>
            </ul>
          </div>
        </div>
        <div className="footer-bottom">
          <span className="mono">© 2026 STADIA TECH LTDA · CNPJ 00.000.000/0001-00</span>
          <div className="footer-pay">
            <span className="mono small">PAY</span>
            {["VISA", "MASTER", "AMEX", "ELO", "PIX", "BOLETO"].map(p => (
              <span key={p} className="footer-pay-chip mono">{p}</span>
            ))}
          </div>
        </div>
      </div>
      <div className="footer-mega" aria-hidden="true">STADIA</div>
      <style>{`
        .footer {
          position: relative;
          margin-top: 120px;
          padding: 80px 0 40px;
          background: var(--bg-1);
          border-top: 1px solid var(--line);
          overflow: hidden;
        }
        .footer-grid {
          display: grid;
          grid-template-columns: 1.6fr 1fr 1fr 1fr;
          gap: 48px;
          padding-bottom: 80px;
        }
        @media (max-width: 800px) { .footer-grid { grid-template-columns: 1fr 1fr; gap: 32px; } }
        .footer-brand .brand {
          font-family: var(--font-display);
          font-weight: 700; font-size: 22px; letter-spacing: -0.04em;
          display: inline-flex; align-items: baseline; gap: 6px;
          margin-bottom: 16px;
        }
        .footer-blurb { color: var(--muted); font-size: 14px; max-width: 360px; }
        .footer-newsletter {
          display: flex; gap: 8px; margin-top: 20px;
          max-width: 380px;
        }
        .footer-newsletter .input { flex: 1; height: 44px; }
        .footer h5 {
          margin: 0 0 16px;
          font-family: var(--font-mono);
          font-size: 11px;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: var(--muted);
        }
        .footer ul { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 10px; }
        .footer li button {
          background: transparent; border: 0; color: var(--fg-2);
          font-size: 14px; padding: 0; text-align: left;
          font-family: inherit;
        }
        .footer li button:hover { color: var(--accent); }
        .footer-bottom {
          display: flex; justify-content: space-between; align-items: center;
          padding-top: 32px; border-top: 1px solid var(--line);
          color: var(--muted); font-size: 12px;
          flex-wrap: wrap; gap: 16px;
        }
        .footer-pay { display: flex; align-items: center; gap: 8px; }
        .footer-pay-chip {
          font-size: 10px; letter-spacing: 0.1em;
          padding: 4px 8px; border: 1px solid var(--line-2);
          border-radius: 4px; color: var(--fg-2);
        }
        .footer-mega {
          position: absolute; left: 50%; bottom: -48px;
          transform: translateX(-50%);
          font-family: var(--font-display);
          font-weight: 800;
          font-size: clamp(120px, 22vw, 320px);
          letter-spacing: -0.06em;
          color: transparent;
          -webkit-text-stroke: 1px var(--line-2);
          line-height: 0.85;
          pointer-events: none;
          user-select: none;
          white-space: nowrap;
        }
      `}</style>
    </footer>
  );
}

/* ============================================================
   Section header
   ============================================================ */
function SectionHead({ kicker, title, action, onAction }) {
  return (
    <div className="section-head">
      <div>
        {kicker && <div className="eyebrow">{kicker}</div>}
        <h2 className="display section-title">{title}</h2>
      </div>
      {action && (
        <button className="btn ghost sm" onClick={onAction}>
          {action} <Icon name="arrow-right" size={14}/>
        </button>
      )}
      <style>{`
        .section-head {
          display: flex; align-items: flex-end; justify-content: space-between;
          margin-bottom: 32px; gap: 16px;
        }
        .section-title {
          margin: 6px 0 0;
          font-size: clamp(28px, 4vw, 48px);
          letter-spacing: -0.03em;
        }
      `}</style>
    </div>
  );
}

/* ============================================================
   StarRating
   ============================================================ */
function StarRating({ value, count, size = 12, showCount = true }) {
  const full = Math.floor(value);
  return (
    <div className="row" style={{ gap: 6 }}>
      <span className="row" style={{ gap: 1, color: "var(--accent)" }}>
        {[1,2,3,4,5].map(i => (
          <Icon key={i} name={i <= full ? "star" : "star-o"} size={size}/>
        ))}
      </span>
      {showCount && <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>{value} ({count})</span>}
    </div>
  );
}

window.STADIA_UI = { Header, Footer, SearchOverlay, ProductCard, Drawer, Toast, SectionHead, StarRating, BRL, cls };
