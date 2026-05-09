// STADIA — PLP (listagem) com filtros funcionais

const { ProductCard: _PC, BRL: _BRL } = window.STADIA_UI;

function PLP({ go, addToCart, toggleFav, wishlist, cardStyle, params }) {
  const { PRODUCTS, CATEGORIES, TEAMS } = window.STADIA_DATA;
  const cat = params?.cat || "all";
  const team = params?.team || null;
  const filter = params?.filter || null;

  const [sort, setSort] = React.useState("relevance");
  const [view, setView] = React.useState("grid");
  const [priceMax, setPriceMax] = React.useState(1500);
  const [selSizes, setSelSizes] = React.useState([]);
  const [selTeams, setSelTeams] = React.useState(team ? [team] : []);
  const [selBadges, setSelBadges] = React.useState(filter ? [filter] : []);
  const [filtersOpen, setFiltersOpen] = React.useState(false);

  const allSizes = React.useMemo(() => {
    const s = new Set();
    PRODUCTS.forEach((p) => p.sizes.forEach((sz) => s.add(sz)));
    return [...s];
  }, []);

  const filtered = React.useMemo(() => {
    let arr = [...PRODUCTS];
    if (cat !== "all") arr = arr.filter((p) => p.category === cat);
    arr = arr.filter((p) => p.price <= priceMax);
    if (selSizes.length) arr = arr.filter((p) => p.sizes.some((s) => selSizes.includes(s)));
    if (selTeams.length) arr = arr.filter((p) => selTeams.includes(p.team));
    if (selBadges.length) arr = arr.filter((p) => selBadges.includes(p.badge));
    if (sort === "price-asc") arr.sort((a, b) => a.price - b.price);
    if (sort === "price-desc") arr.sort((a, b) => b.price - a.price);
    if (sort === "rating") arr.sort((a, b) => b.rating - a.rating);
    if (sort === "newest") arr.sort((a, b) => (b.badge === "new" ? 1 : 0) - (a.badge === "new" ? 1 : 0));
    return arr;
  }, [cat, priceMax, selSizes, selTeams, selBadges, sort]);

  const catName = cat === "all" ? "Todos os produtos" : (CATEGORIES.find((c) => c.id === cat)?.name || cat);

  const toggle = (setter) => (val) => setter((arr) => arr.includes(val) ? arr.filter((x) => x !== val) : [...arr, val]);
  const tSize = toggle(setSelSizes);
  const tTeam = toggle(setSelTeams);
  const tBadge = toggle(setSelBadges);

  const Filters = (
    <div className="filters">
      <div className="filter-group">
        <h5>PREÇO</h5>
        <div className="row between mono small" style={{ color: "var(--muted)", marginBottom: 8 }}>
          <span>R$ 0</span><span>R$ {priceMax}</span>
        </div>
        <input type="range" min={50} max={1500} step={50} value={priceMax}
          onChange={(e) => setPriceMax(Number(e.target.value))} className="range"/>
      </div>
      <div className="filter-group">
        <h5>TAMANHO</h5>
        <div className="size-grid">
          {allSizes.map((s) => (
            <button key={s} className={"size-btn " + (selSizes.includes(s) ? "on" : "")} onClick={() => tSize(s)}>{s}</button>
          ))}
        </div>
      </div>
      <div className="filter-group">
        <h5>TIME</h5>
        <div className="check-list">
          {TEAMS.map((t) => (
            <label key={t.code} className="check-row">
              <input type="checkbox" checked={selTeams.includes(t.code)} onChange={() => tTeam(t.code)}/>
              <span className="check-box"></span>
              <span>{t.name}</span>
              <span className="mono small" style={{ color: "var(--muted)" }}>{t.code}</span>
            </label>
          ))}
        </div>
      </div>
      <div className="filter-group">
        <h5>STATUS</h5>
        <div className="check-list">
          {[
            { v: "drop", l: "Drop ao vivo" },
            { v: "elite", l: "Pro / Elite" },
            { v: "new", l: "Novidades" },
            { v: "deal", l: "Promoções" },
          ].map((b) => (
            <label key={b.v} className="check-row">
              <input type="checkbox" checked={selBadges.includes(b.v)} onChange={() => tBadge(b.v)}/>
              <span className="check-box"></span>
              <span>{b.l}</span>
            </label>
          ))}
        </div>
      </div>
      <button className="btn ghost block sm" onClick={() => {
        setSelSizes([]); setSelTeams([]); setSelBadges([]); setPriceMax(1500);
      }}>Limpar filtros</button>

      <style>{`
        .filters { display: flex; flex-direction: column; gap: 28px; }
        .filter-group { display: flex; flex-direction: column; gap: 12px; padding-bottom: 24px; border-bottom: 1px solid var(--line); }
        .filter-group:last-of-type { border-bottom: 0; padding-bottom: 0; }
        .filter-group h5 { margin: 0; font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.16em; color: var(--muted); }
        .range { -webkit-appearance: none; width: 100%; height: 4px; background: var(--bg-3); border-radius: 999px; outline: none; }
        .range::-webkit-slider-thumb { -webkit-appearance: none; width: 18px; height: 18px; background: var(--accent); border-radius: 50%; cursor: grab; box-shadow: 0 0 0 4px color-mix(in oklab, var(--accent) 25%, transparent); }
        .range::-moz-range-thumb { width: 18px; height: 18px; background: var(--accent); border-radius: 50%; cursor: grab; border: 0; }
        .size-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
        .size-btn { padding: 8px 4px; background: var(--surface); border: 1px solid var(--line-2); color: var(--fg); border-radius: 6px; font-family: var(--font-mono); font-size: 12px; }
        .size-btn.on { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }
        .check-list { display: flex; flex-direction: column; gap: 10px; }
        .check-row { display: flex; align-items: center; gap: 10px; cursor: pointer; font-size: 14px; color: var(--fg-2); }
        .check-row input { display: none; }
        .check-box { width: 16px; height: 16px; border: 1px solid var(--line-2); border-radius: 4px; background: var(--surface); transition: all 0.15s; flex-shrink: 0; position: relative; }
        .check-row input:checked + .check-box { background: var(--accent); border-color: var(--accent); }
        .check-row input:checked + .check-box::after { content: "✓"; position: absolute; inset: 0; display: grid; place-items: center; font-size: 11px; color: var(--accent-ink); font-weight: 700; }
        .check-row .small { margin-left: auto; }
      `}</style>
    </div>
  );

  return (
    <main className="plp-main">
      <div className="container">
        <div className="plp-head">
          <nav className="crumb mono">
            <button onClick={() => go("home")}>STADIA</button>
            <span>/</span>
            <button onClick={() => go("plp")}>LOJA</button>
            <span>/</span>
            <span style={{ color: "var(--fg)" }}>{catName.toUpperCase()}</span>
          </nav>
          <div className="plp-title-row">
            <div>
              <h1 className="display" style={{ fontSize: "clamp(40px,5vw,72px)", margin: 0 }}>{catName}</h1>
              <p className="mono small" style={{ color: "var(--muted)", marginTop: 8 }}>
                {filtered.length} PRODUTOS · ATUALIZADO 14:02 BRT
              </p>
            </div>
            <div className="plp-controls">
              <button className="btn ghost sm mobile-only" onClick={() => setFiltersOpen(true)}>
                <Icon name="filter" size={14}/> Filtros
              </button>
              <div className="seg">
                <button className={view === "grid" ? "on" : ""} onClick={() => setView("grid")}><Icon name="grid" size={14}/></button>
                <button className={view === "list" ? "on" : ""} onClick={() => setView("list")}><Icon name="rows" size={14}/></button>
              </div>
              <select className="sort-sel" value={sort} onChange={(e) => setSort(e.target.value)}>
                <option value="relevance">Relevância</option>
                <option value="newest">Novidades</option>
                <option value="rating">Mais avaliados</option>
                <option value="price-asc">Menor preço</option>
                <option value="price-desc">Maior preço</option>
              </select>
            </div>
          </div>
        </div>

        <div className="plp-grid">
          <aside className="plp-side desktop-only">
            <h4 className="mono" style={{ margin: 0, marginBottom: 18, fontSize: 12, letterSpacing: "0.16em", color: "var(--fg)" }}>FILTROS</h4>
            {Filters}
          </aside>

          <section className="plp-cat-grid">
            {(selBadges.length || selSizes.length || selTeams.length) > 0 && (
              <div className="active-tags">
                {selBadges.map((b) => <span key={b} className="tag-pill">{b} <button onClick={() => tBadge(b)}>×</button></span>)}
                {selSizes.map((s) => <span key={s} className="tag-pill">{s} <button onClick={() => tSize(s)}>×</button></span>)}
                {selTeams.map((t) => <span key={t} className="tag-pill">{t} <button onClick={() => tTeam(t)}>×</button></span>)}
              </div>
            )}

            {filtered.length === 0 ? (
              <div className="empty">
                <Icon name="search" size={36}/>
                <h3 className="display">Nada por aqui</h3>
                <p>Tente afrouxar os filtros — talvez o tamanho ou a faixa de preço.</p>
              </div>
            ) : view === "grid" ? (
              <div className="cards-4">
                {filtered.map((p) => (
                  <ProductCard key={p.id} p={p} variant={cardStyle}
                    faved={wishlist.includes(p.id)}
                    onOpen={() => go("pdp", { id: p.id })}
                    onFav={() => toggleFav(p.id)}
                    onAdd={() => addToCart(p)}/>
                ))}
              </div>
            ) : (
              <div className="list-rows">
                {filtered.map((p) => (
                  <button key={p.id} className="list-row" onClick={() => go("pdp", { id: p.id })}>
                    <div className="lr-thumb img-ph has-viz" style={{ background: p.imageBg }}><STADIA_PRODUCT_VISUAL p={p}/></div>
                    <div className="lr-info">
                      <span className="mono small" style={{ color: "var(--muted)" }}>{p.sub}</span>
                      <h4>{p.name}</h4>
                      <p>{p.desc?.slice(0, 100)}...</p>
                    </div>
                    <div className="lr-meta">
                      <div className="mono small" style={{ color: "var(--muted)" }}>RATING</div>
                      <b>{p.rating} ★</b>
                    </div>
                    <div className="lr-price">
                      <b>{BRL(p.price)}</b>
                      {p.listPrice > p.price && <s>{BRL(p.listPrice)}</s>}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>

      {filtersOpen && (
        <window.STADIA_UI.Drawer open={filtersOpen} onClose={() => setFiltersOpen(false)} side="left" title="Filtros">
          {Filters}
        </window.STADIA_UI.Drawer>
      )}

      <style>{`
        .plp-main { padding: 24px 0 60px; }
        .plp-head { padding: 12px 0 32px; }
        .crumb { display: flex; align-items: center; gap: 8px; font-size: 11px; letter-spacing: 0.14em; color: var(--muted); margin-bottom: 24px; }
        .crumb button { background: transparent; border: 0; color: inherit; font-family: inherit; }
        .crumb button:hover { color: var(--fg); }
        .plp-title-row {
          display: flex; align-items: flex-end; justify-content: space-between; gap: 24px;
          flex-wrap: wrap;
        }
        .plp-controls { display: flex; align-items: center; gap: 8px; }
        .seg { display: flex; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 2px; }
        .seg button { background: transparent; border: 0; padding: 6px 10px; color: var(--muted); border-radius: 6px; }
        .seg button.on { background: var(--bg-3); color: var(--fg); }
        .sort-sel {
          height: 38px; padding: 0 32px 0 14px; border-radius: 999px;
          background: var(--surface); border: 1px solid var(--line);
          color: var(--fg); font-family: inherit; font-size: 13px;
          appearance: none;
          background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path fill='%238a8f99' d='M0 0h10L5 6z'/></svg>");
          background-repeat: no-repeat; background-position: right 12px center;
        }
        .plp-grid {
          display: grid; grid-template-columns: 240px 1fr; gap: 48px;
          align-items: start;
        }
        @media (max-width: 1000px) { .plp-grid { grid-template-columns: 1fr; gap: 24px; } }
        .plp-side {
          position: sticky; top: 100px;
          padding-right: 12px;
        }
        .plp-cat-grid { min-width: 0; }
        .active-tags { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }
        .tag-pill {
          display: inline-flex; align-items: center; gap: 4px;
          padding: 4px 4px 4px 12px; height: 28px;
          border-radius: 999px;
          background: var(--accent); color: var(--accent-ink);
          font-family: var(--font-mono); font-size: 11px;
          letter-spacing: 0.1em; text-transform: uppercase;
        }
        .tag-pill button {
          width: 20px; height: 20px;
          background: rgba(0,0,0,.2); color: inherit;
          border: 0; border-radius: 50%;
          margin-left: 4px;
        }
        .cards-4 {
          display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px;
        }
        @media (max-width: 1300px) { .cards-4 { grid-template-columns: repeat(2, 1fr); } }
        [data-viewport="mobile"] .cards-4 { grid-template-columns: repeat(2, 1fr); gap: 12px; }
        .list-rows { display: flex; flex-direction: column; gap: 8px; }
        .list-row {
          display: grid; grid-template-columns: 120px 1fr auto auto;
          gap: 24px; align-items: center;
          padding: 16px;
          background: var(--surface); border: 1px solid var(--line);
          border-radius: var(--r-md);
          color: var(--fg); text-align: left; font-family: inherit;
        }
        .list-row:hover { border-color: var(--line-2); }
        .lr-thumb { width: 120px; aspect-ratio: 1; border-radius: var(--r-sm); }
        .lr-info h4 { margin: 4px 0; font-family: var(--font-display); font-size: 18px; }
        .lr-info p { margin: 0; color: var(--muted); font-size: 13px; max-width: 460px; }
        .lr-meta b { font-family: var(--font-mono); font-size: 16px; }
        .lr-price b { font-family: var(--font-display); font-size: 20px; color: var(--accent); display: block; }
        .lr-price s { color: var(--muted); font-size: 12px; }
        .empty { padding: 80px 0; text-align: center; color: var(--muted); }
        .empty h3 { color: var(--fg); margin: 16px 0 8px; }
      `}</style>
    </main>
  );
}

window.STADIA_PLP = PLP;
