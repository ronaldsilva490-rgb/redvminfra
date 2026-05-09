// STADIA — Home / Landing — 3 variants

const { Header: _H1, ProductCard, SectionHead, BRL } = window.STADIA_UI;

function Home({ go, addToCart, toggleFav, wishlist, cardStyle, variant }) {
  const { PRODUCTS, CATEGORIES, TEAMS } = window.STADIA_DATA;
  const featured = PRODUCTS.slice(0, 8);
  const drops = PRODUCTS.filter((p) => p.badge === "drop");
  const elite = PRODUCTS.filter((p) => p.badge === "elite");

  if (variant === "scoreboard") return (
    <HomeScoreboard go={go} addToCart={addToCart} toggleFav={toggleFav} wishlist={wishlist}
                    cardStyle={cardStyle} featured={featured} drops={drops} elite={elite}/>
  );
  if (variant === "editorial") return (
    <HomeEditorial go={go} addToCart={addToCart} toggleFav={toggleFav} wishlist={wishlist}
                   cardStyle={cardStyle} featured={featured} drops={drops}/>
  );
  return (
    <HomeKinetic go={go} addToCart={addToCart} toggleFav={toggleFav} wishlist={wishlist}
                 cardStyle={cardStyle} featured={featured} drops={drops} elite={elite}/>
  );
}

/* ============================================================
   VARIANT 1 · "Kinetic" — bold sport, mega type, ticker rail
   ============================================================ */
function HomeKinetic({ go, addToCart, toggleFav, wishlist, cardStyle, featured, drops, elite }) {
  const { TEAMS } = window.STADIA_DATA;
  const [hover, setHover] = React.useState(null);

  return (
    <main className="home-kinetic">
      {/* HERO */}
      <section className="hero">
        <div className="hero-bg" aria-hidden="true">
          <div className="hero-grid"></div>
          <div className="hero-blob"></div>
        </div>
        <div className="container hero-inner">
          <div className="hero-meta">
            <span className="chip live">DROP AO VIVO · MATCHDAY 03</span>
            <span className="mono small" style={{ color: "var(--muted)" }}>09 · MAI · 26 — 14:00 BRT</span>
          </div>
          <h1 className="display hero-title">
            <span>JOGUE</span>
            <span>COMO</span>
            <span className="hero-italic">ELite.</span>
          </h1>
          <p className="hero-sub">
            Equipamento técnico para futebol e esportes coletivos. Kits oficiais, chuteiras pro-series e treino de alta intensidade — entregues em 24h.
          </p>
          <div className="hero-actions">
            <button className="btn lg" onClick={() => go("plp", { cat: "all", filter: "drop" })}>
              Comprar drop atual <Icon name="arrow-right" size={16}/>
            </button>
            <button className="btn lg ghost" onClick={() => go("plp", { cat: "camisas" })}>
              Ver kits 25/26
            </button>
          </div>
          <div className="hero-stats mono">
            <div><b>184</b><span>KITS LICENCIADOS</span></div>
            <div><b>24h</b><span>ENTREGA EXPRESSA</span></div>
            <div><b>4.9★</b><span>12K AVALIAÇÕES</span></div>
            <div><b>0%</b><span>JUROS PIX</span></div>
          </div>
        </div>
        <aside className="hero-card">
          <div className="hero-card-img img-ph" style={{ background: "linear-gradient(160deg,#0b0d12,#1f2933 60%,#c8ff00 220%)" }}>
            <span className="label">camisa hero</span>
          </div>
          <div className="hero-card-body">
            <div className="row between">
              <span className="eyebrow">N° 01 · CAMISA</span>
              <span className="mono small" style={{ color: "var(--accent)" }}>+ EXCLUSIVO APP</span>
            </div>
            <h3>Volturi Home 26</h3>
            <div className="row between" style={{ marginTop: 8 }}>
              <div>
                <div className="mono small" style={{ color: "var(--muted)" }}>A PARTIR DE</div>
                <div className="hero-card-price">{BRL(449.9)}</div>
              </div>
              <button className="btn sm" onClick={() => go("pdp", { id: "p01" })}>
                <Icon name="arrow-up-right" size={14}/>
              </button>
            </div>
          </div>
        </aside>
      </section>

      {/* SCROLLING TEAMS */}
      <section className="teams-strip">
        <div className="strip-track">
          {[...TEAMS, ...TEAMS, ...TEAMS].map((t, i) => (
            <div key={i} className="team-cell">
              <span className="mono">{t.code}</span>
              <span className="team-name">{t.name}</span>
            </div>
          ))}
        </div>
      </section>

      {/* DROP MATCHDAY */}
      <section className="container section">
        <SectionHead kicker="MATCHDAY 03" title="Drop da semana"
          action="Ver todos" onAction={() => go("plp", { cat: "all", filter: "drop" })}/>
        <div className="grid-cards">
          {drops.slice(0, 4).map((p) => (
            <ProductCard key={p.id} p={p} variant={cardStyle}
              faved={wishlist.includes(p.id)}
              onOpen={() => go("pdp", { id: p.id })}
              onFav={() => toggleFav(p.id)}
              onAdd={() => addToCart(p)}/>
          ))}
        </div>
      </section>

      {/* CATEGORIES */}
      <section className="container section">
        <SectionHead kicker="CATEGORIAS" title="Compre por modalidade"/>
        <div className="cat-grid">
          {window.STADIA_DATA.CATEGORIES.map((c) => (
            <button key={c.id} className="cat-tile" onClick={() => go("plp", { cat: c.id })}>
              <div className="cat-icon"><Icon name={c.icon} size={28} stroke={1.4}/></div>
              <div className="cat-text">
                <h4>{c.name}</h4>
                <span className="mono">{c.count} produtos</span>
              </div>
              <Icon name="arrow-up-right" size={18}/>
            </button>
          ))}
        </div>
      </section>

      {/* PRO STORY */}
      <section className="container section">
        <div className="pro-grid">
          <div className="pro-text">
            <span className="eyebrow">PRO SERIES</span>
            <h2 className="display" style={{ fontSize: "clamp(36px,5vw,64px)" }}>
              Construído para a 89ª linha de fundo.
            </h2>
            <p>Cada peça PRO passa por testes de campo com atletas de elite — em 240 ciclos de lavagem, 18 jogos completos e ambientes de 0 a 38 °C antes do drop.</p>
            <button className="btn outline">Conheça a linha PRO <Icon name="arrow-right" size={14}/></button>
          </div>
          <div className="pro-stats">
            {[
              { n: "240", l: "Ciclos de lavagem testados" },
              { n: "+18%", l: "Recuperação muscular vs categoria" },
              { n: "92%", l: "Aprovação de atletas pro" },
              { n: "0,4kg", l: "Peso médio chuteira FG" },
            ].map((s, i) => (
              <div key={i} className="pro-stat">
                <span className="mono small">0{i + 1}</span>
                <b className="mono">{s.n}</b>
                <span>{s.l}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* MOST WANTED */}
      <section className="container section">
        <SectionHead kicker="MAIS DESEJADOS" title="Trending no app"
          action="Ver ranking" onAction={() => go("plp", { cat: "all" })}/>
        <div className="grid-cards">
          {featured.slice(0, 8).map((p) => (
            <ProductCard key={p.id} p={p} variant={cardStyle}
              faved={wishlist.includes(p.id)}
              onOpen={() => go("pdp", { id: p.id })}
              onFav={() => toggleFav(p.id)}
              onAdd={() => addToCart(p)}/>
          ))}
        </div>
      </section>

      {/* USPS */}
      <section className="container section">
        <div className="usp-grid">
          {[
            { ic: "truck", t: "Entrega 24h", s: "Em capitais via STADIA Express" },
            { ic: "shield", t: "Selo de autenticidade", s: "Holograma em todas as camisas oficiais" },
            { ic: "spark-2", t: "Troca grátis 30 dias", s: "Frete reverso sem custo na primeira" },
            { ic: "headset", t: "Suporte humano", s: "Time pro 7-dias-22h por chat e WhatsApp" },
          ].map((u, i) => (
            <div key={i} className="usp-tile">
              <div className="usp-ic"><Icon name={u.ic} size={22} stroke={1.5}/></div>
              <h5>{u.t}</h5>
              <p>{u.s}</p>
            </div>
          ))}
        </div>
      </section>

      <style>{`
        .home-kinetic { padding-bottom: 60px; }
        .section { padding: 80px 0 0; }

        .hero {
          position: relative;
          min-height: 720px;
          padding: 80px 0 100px;
          overflow: hidden;
        }
        [data-viewport="mobile"] .hero { min-height: 600px; padding: 40px 0 60px; }
        .hero-bg { position: absolute; inset: 0; z-index: 0; pointer-events: none; }
        .hero-grid {
          position: absolute; inset: 0;
          background:
            linear-gradient(var(--line) 1px, transparent 1px) 0 0 / 80px 80px,
            linear-gradient(90deg, var(--line) 1px, transparent 1px) 0 0 / 80px 80px;
          mask-image: radial-gradient(ellipse at 30% 40%, black 30%, transparent 70%);
        }
        .hero-blob {
          position: absolute; right: -10%; top: -20%;
          width: 60vw; height: 60vw; max-width: 900px; max-height: 900px;
          background: radial-gradient(circle, var(--accent-glow), transparent 60%);
          filter: blur(40px);
        }
        .hero-inner { position: relative; z-index: 1; max-width: var(--max-w); }
        .hero-meta { display: flex; align-items: center; gap: 16px; margin-bottom: 32px; }
        .hero-meta .small { font-size: 11px; letter-spacing: 0.12em; }
        .hero-title {
          font-size: clamp(72px, 11vw, 188px);
          line-height: 0.86;
          letter-spacing: -0.05em;
          margin: 0;
          display: flex; flex-direction: column;
          text-wrap: balance;
        }
        .hero-title .hero-italic {
          font-family: 'Instrument Serif', Georgia, serif;
          font-style: italic;
          font-weight: 400;
          color: var(--accent);
          letter-spacing: -0.02em;
        }
        .hero-sub {
          max-width: 540px;
          margin: 32px 0;
          font-size: clamp(16px, 1.6vw, 19px);
          line-height: 1.5;
          color: var(--fg-2);
        }
        .hero-actions { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 64px; }
        .hero-stats {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 24px;
          max-width: 720px;
        }
        .hero-stats > div {
          display: flex; flex-direction: column; gap: 4px;
          padding-top: 16px;
          border-top: 1px solid var(--line-2);
        }
        .hero-stats b {
          font-family: var(--font-display);
          font-weight: 700; font-size: clamp(22px, 3vw, 36px);
          letter-spacing: -0.03em;
        }
        .hero-stats span {
          font-size: 10px; letter-spacing: 0.14em; color: var(--muted);
        }

        .hero-card {
          position: absolute;
          right: 60px;
          bottom: 60px;
          width: 320px;
          background: var(--surface);
          border: 1px solid var(--line-2);
          border-radius: var(--r-md);
          overflow: hidden;
          box-shadow: var(--shadow-2);
          z-index: 2;
          transform: rotate(-2deg);
          transition: transform 0.4s;
        }
        .hero-card:hover { transform: rotate(0); }
        .hero-card-img { aspect-ratio: 1.2/1; }
        .hero-card-body { padding: 18px 20px 20px; }
        .hero-card-body h3 { margin: 8px 0 0; font-family: var(--font-display); font-size: 18px; font-weight: 700; }
        .hero-card-price { font-family: var(--font-display); font-size: 26px; font-weight: 700; }

        @media (max-width: 1100px) {
          .hero-card { display: none; }
        }

        .teams-strip {
          height: 96px;
          border-block: 1px solid var(--line);
          background: var(--bg-1);
          display: flex; align-items: center;
          overflow: hidden;
        }
        .strip-track {
          display: flex; gap: 0; width: max-content;
          animation: ticker 60s linear infinite;
        }
        .team-cell {
          display: flex; align-items: baseline; gap: 12px;
          padding: 0 56px;
          border-right: 1px solid var(--line);
          height: 96px;
          align-items: center;
        }
        .team-cell .mono {
          font-size: 12px;
          color: var(--muted);
          letter-spacing: 0.14em;
        }
        .team-cell .team-name {
          font-family: var(--font-display);
          font-size: 32px;
          font-weight: 700;
          letter-spacing: -0.02em;
          color: var(--fg);
        }

        .grid-cards {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 24px;
        }
        @media (max-width: 1100px) { .grid-cards { grid-template-columns: repeat(3, 1fr); } }
        @media (max-width: 800px) { .grid-cards { grid-template-columns: repeat(2, 1fr); } }
        [data-viewport="mobile"] .grid-cards { grid-template-columns: repeat(2, 1fr); gap: 12px; }

        .cat-grid {
          display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;
        }
        @media (max-width: 900px) { .cat-grid { grid-template-columns: repeat(2, 1fr); } }
        [data-viewport="mobile"] .cat-grid { grid-template-columns: 1fr; }
        .cat-tile {
          display: grid;
          grid-template-columns: 56px 1fr auto;
          align-items: center; gap: 16px;
          padding: 20px 22px;
          background: var(--surface); border: 1px solid var(--line);
          border-radius: var(--r-md);
          color: var(--fg);
          text-align: left;
          font-family: inherit;
          transition: border-color 0.2s, transform 0.2s;
        }
        .cat-tile:hover { border-color: var(--accent); transform: translateY(-2px); }
        .cat-tile:hover .cat-icon { background: var(--accent); color: var(--accent-ink); }
        .cat-icon {
          width: 56px; height: 56px;
          border-radius: var(--r-sm);
          background: var(--bg-2);
          color: var(--fg);
          display: grid; place-items: center;
          transition: background 0.2s, color 0.2s;
        }
        .cat-tile h4 { margin: 0; font-family: var(--font-display); font-size: 18px; font-weight: 600; }
        .cat-tile .mono { font-size: 11px; color: var(--muted); letter-spacing: 0.1em; }

        .pro-grid {
          display: grid; grid-template-columns: 1fr 1fr; gap: 80px;
          padding: 64px;
          background: var(--bg-1);
          border: 1px solid var(--line);
          border-radius: var(--r-lg);
        }
        @media (max-width: 900px) { .pro-grid { grid-template-columns: 1fr; gap: 32px; padding: 32px; } }
        .pro-text { display: flex; flex-direction: column; gap: 16px; align-items: flex-start; }
        .pro-text h2 { margin: 0; }
        .pro-text p { color: var(--muted); max-width: 420px; line-height: 1.6; }
        .pro-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
        .pro-stat {
          display: flex; flex-direction: column; gap: 8px;
          padding: 24px; padding-left: 0;
          border-top: 1px solid var(--line-2);
          padding-top: 20px;
        }
        .pro-stat .small { color: var(--muted); font-size: 11px; }
        .pro-stat b {
          font-family: var(--font-display); font-size: clamp(28px, 3vw, 44px);
          font-weight: 700; color: var(--accent);
          letter-spacing: -0.03em; line-height: 1;
        }
        .pro-stat span { color: var(--fg-2); font-size: 14px; }

        .usp-grid {
          display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
        }
        @media (max-width: 900px) { .usp-grid { grid-template-columns: repeat(2, 1fr); } }
        .usp-tile {
          padding: 24px;
          background: var(--surface); border: 1px solid var(--line);
          border-radius: var(--r-md);
        }
        .usp-ic {
          width: 44px; height: 44px;
          background: var(--bg-2); color: var(--accent);
          border-radius: var(--r-sm);
          display: grid; place-items: center;
          margin-bottom: 16px;
        }
        .usp-tile h5 { margin: 0 0 6px; font-family: var(--font-display); font-size: 16px; font-weight: 700; }
        .usp-tile p { margin: 0; color: var(--muted); font-size: 13px; }
      `}</style>
    </main>
  );
}

/* ============================================================
   VARIANT 2 · "Scoreboard" — data-rich, dashboard feel
   ============================================================ */
function HomeScoreboard({ go, addToCart, toggleFav, wishlist, cardStyle, featured, drops, elite }) {
  const { TEAMS, PRODUCTS } = window.STADIA_DATA;
  const [tick, setTick] = React.useState(0);
  React.useEffect(() => { const id = setInterval(() => setTick(t => t + 1), 1500); return () => clearInterval(id); }, []);
  const live = 1248 + (tick % 12);
  const sales = 38942 + (tick * 7);

  return (
    <main className="home-score">
      <section className="score-hero">
        <div className="container">
          <div className="score-hero-grid">
            <div className="score-left">
              <span className="chip live">LIVE · {live} ATIVOS NA LOJA</span>
              <h1 className="display score-title">
                Performance é<br/>número, não promessa.
              </h1>
              <p>Cada produto STADIA é testado em campo, monitorado em tempo real e recomendado por atletas verificados. Veja os dados.</p>
              <div className="row" style={{ gap: 12 }}>
                <button className="btn lg" onClick={() => go("plp")}>Explorar catálogo <Icon name="arrow-right" size={16}/></button>
                <button className="btn lg ghost" onClick={() => go("plp", { filter: "drop" })}>Ver drop ao vivo</button>
              </div>
            </div>
            <div className="score-right">
              <div className="score-board">
                <div className="board-row mono"><span>STADIA / LIVE</span><span style={{color: "var(--accent-3)"}}>● ON-AIR</span></div>
                <div className="board-grid">
                  <div className="board-cell">
                    <span className="k mono">PEDIDOS HOJE</span>
                    <b className="score">{sales.toLocaleString("pt-BR")}</b>
                    <span className="d up mono">+12.4% vs ontem</span>
                  </div>
                  <div className="board-cell">
                    <span className="k mono">DESPACHADOS</span>
                    <b className="score">{Math.floor(sales * 0.78).toLocaleString("pt-BR")}</b>
                    <span className="d mono">PRAZO MÉDIO 1.2 D</span>
                  </div>
                  <div className="board-cell">
                    <span className="k mono">TIMES ATIVOS</span>
                    <b className="score">{TEAMS.length * 4}</b>
                    <span className="d mono">{TEAMS.length} LICENCIADOS</span>
                  </div>
                  <div className="board-cell">
                    <span className="k mono">SATISFAÇÃO</span>
                    <b className="score">98<span style={{ fontSize: "0.6em", color: "var(--muted)" }}>%</span></b>
                    <span className="d mono">12.4K AVALIAÇÕES</span>
                  </div>
                </div>
                <div className="board-spark mono">
                  <span>SPARKLINE 24H</span>
                  <svg viewBox="0 0 240 40" width="240" height="40">
                    <polyline fill="none" stroke="var(--accent)" strokeWidth="1.5"
                      points="0,30 16,28 32,24 48,30 64,18 80,22 96,12 112,16 128,10 144,18 160,8 176,14 192,6 208,12 224,4 240,8"/>
                  </svg>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="container" style={{ paddingTop: 80 }}>
        <SectionHead kicker="DROP MATCHDAY 03" title="Em alta agora"
          action="Ver tudo" onAction={() => go("plp", { filter: "drop" })}/>
        <div className="grid-cards">
          {drops.concat(elite).slice(0, 4).map((p) => (
            <ProductCard key={p.id} p={p} variant="data"
              faved={wishlist.includes(p.id)}
              onOpen={() => go("pdp", { id: p.id })}
              onFav={() => toggleFav(p.id)}
              onAdd={() => addToCart(p)}/>
          ))}
        </div>
      </section>

      <section className="container" style={{ paddingTop: 80 }}>
        <div className="leaderboard">
          <div className="lb-head">
            <h3 className="display">Leaderboard semanal</h3>
            <span className="mono small" style={{ color: "var(--muted)" }}>SEMANA 19/26 · ATUALIZADO 14:02 BRT</span>
          </div>
          <div className="lb-rows">
            {PRODUCTS.slice(0, 6).map((p, i) => (
              <button key={p.id} className="lb-row" onClick={() => go("pdp", { id: p.id })}>
                <span className="lb-rank mono">0{i + 1}</span>
                <div className="lb-thumb img-ph has-viz" style={{ background: p.imageBg }}><STADIA_PRODUCT_VISUAL p={p}/></div>
                <div className="lb-info">
                  <h4>{p.name}</h4>
                  <span className="mono">{p.sub}</span>
                </div>
                <div className="lb-stats mono">
                  <span><b>{p.rating}★</b> RATING</span>
                  <span><b>{p.reviews}</b> REVIEWS</span>
                  <span><b>{p.stock}</b> ESTOQUE</span>
                </div>
                <div className="lb-price mono">{BRL(p.price)}</div>
                <Icon name="arrow-right" size={16} style={{ color: "var(--muted)" }}/>
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="container" style={{ paddingTop: 80 }}>
        <SectionHead kicker="POR TIME" title="Loja por clube"/>
        <div className="team-cards">
          {TEAMS.map((t) => (
            <button key={t.code} className="team-card" onClick={() => go("plp", { team: t.code })}
              style={{ background: `linear-gradient(160deg, ${t.colors[0]}, ${t.colors[1]})` }}>
              <div className="row between" style={{ width: "100%" }}>
                <span className="mono small" style={{ color: "rgba(255,255,255,.7)" }}>{t.code}</span>
                <Icon name="arrow-up-right" size={16} style={{ color: "white" }}/>
              </div>
              <h4>{t.name}</h4>
              <span className="mono small">12 produtos</span>
            </button>
          ))}
        </div>
      </section>

      <style>{`
        .home-score { padding-bottom: 60px; }
        .score-hero {
          padding: 60px 0;
          background:
            radial-gradient(circle at 80% 30%, color-mix(in oklab, var(--accent) 18%, transparent), transparent 50%),
            var(--bg-0);
        }
        .score-hero-grid {
          display: grid; grid-template-columns: 1.1fr 1fr; gap: 64px; align-items: center;
        }
        @media (max-width: 1000px) { .score-hero-grid { grid-template-columns: 1fr; } }
        .score-title {
          font-size: clamp(40px, 6vw, 88px);
          line-height: 0.95;
          letter-spacing: -0.04em;
          margin: 24px 0;
        }
        .score-left p { color: var(--fg-2); max-width: 460px; font-size: 17px; margin: 0 0 28px; }

        .score-board {
          background: var(--bg-1);
          border: 1px solid var(--line-2);
          border-radius: var(--r-lg);
          padding: 28px;
          box-shadow: var(--shadow-2);
          position: relative;
          overflow: hidden;
        }
        .score-board::before {
          content: ""; position: absolute; inset: 0;
          background:
            linear-gradient(var(--line) 1px, transparent 1px) 0 0 / 32px 32px,
            linear-gradient(90deg, var(--line) 1px, transparent 1px) 0 0 / 32px 32px;
          mask-image: linear-gradient(transparent, black 30%, black 70%, transparent);
          opacity: 0.4;
          pointer-events: none;
        }
        .board-row {
          display: flex; justify-content: space-between;
          font-size: 11px; letter-spacing: 0.14em;
          color: var(--muted);
          padding-bottom: 16px;
          border-bottom: 1px dashed var(--line-2);
          position: relative; z-index: 1;
        }
        .board-grid {
          display: grid; grid-template-columns: 1fr 1fr; gap: 0;
          padding: 24px 0;
          position: relative; z-index: 1;
        }
        .board-cell {
          padding: 16px 8px;
          display: flex; flex-direction: column; gap: 4px;
          border-right: 1px dashed var(--line-2);
          border-bottom: 1px dashed var(--line-2);
        }
        .board-cell:nth-child(2n) { border-right: 0; }
        .board-cell:nth-child(n+3) { border-bottom: 0; }
        .board-cell .k { font-size: 10px; color: var(--muted); letter-spacing: 0.14em; }
        .board-cell b {
          font-size: 40px; font-weight: 700;
          font-family: var(--font-display);
          letter-spacing: -0.03em;
          color: var(--fg);
        }
        .board-cell .d { font-size: 11px; color: var(--muted); letter-spacing: 0.06em; }
        .board-cell .d.up { color: var(--accent-3); }
        .board-spark {
          display: flex; align-items: center; justify-content: space-between;
          padding-top: 16px;
          font-size: 10px; letter-spacing: 0.14em; color: var(--muted);
          border-top: 1px dashed var(--line-2);
          position: relative; z-index: 1;
        }

        .grid-cards {
          display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
        }
        @media (max-width: 1100px) { .grid-cards { grid-template-columns: repeat(2, 1fr); } }
        [data-viewport="mobile"] .grid-cards { grid-template-columns: repeat(2, 1fr); gap: 10px; }

        .leaderboard {
          background: var(--surface);
          border: 1px solid var(--line);
          border-radius: var(--r-lg);
          overflow: hidden;
        }
        .lb-head {
          padding: 24px 28px;
          display: flex; justify-content: space-between; align-items: baseline;
          border-bottom: 1px solid var(--line);
        }
        .lb-head h3 { margin: 0; font-size: 28px; }
        .lb-rows { display: flex; flex-direction: column; }
        .lb-row {
          display: grid;
          grid-template-columns: 32px 64px 1fr auto auto 18px;
          gap: 24px;
          align-items: center;
          padding: 16px 28px;
          border-bottom: 1px solid var(--line);
          background: transparent;
          color: var(--fg);
          text-align: left;
          font-family: inherit;
        }
        .lb-row:hover { background: var(--surface-2); }
        .lb-row:last-child { border-bottom: 0; }
        .lb-rank { font-size: 14px; color: var(--muted); }
        .lb-thumb { width: 64px; height: 64px; border-radius: var(--r-sm); }
        .lb-info h4 { margin: 0; font-family: var(--font-display); font-size: 16px; font-weight: 600; }
        .lb-info .mono { font-size: 11px; color: var(--muted); letter-spacing: 0.1em; }
        .lb-stats { display: flex; gap: 18px; font-size: 11px; color: var(--muted); letter-spacing: 0.1em; }
        .lb-stats b { color: var(--fg); margin-right: 4px; font-size: 13px; font-weight: 700; }
        .lb-price { font-size: 16px; font-weight: 700; color: var(--accent); }
        @media (max-width: 900px) {
          .lb-row { grid-template-columns: 24px 48px 1fr; }
          .lb-stats, .lb-price, .lb-row > svg { display: none; }
        }

        .team-cards {
          display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;
        }
        @media (max-width: 900px) { .team-cards { grid-template-columns: repeat(2, 1fr); } }
        [data-viewport="mobile"] .team-cards { grid-template-columns: 1fr; }
        .team-card {
          aspect-ratio: 5/3;
          border-radius: var(--r-md);
          padding: 22px;
          display: flex; flex-direction: column; justify-content: space-between;
          color: white; text-align: left;
          border: 0; font-family: inherit;
          position: relative; overflow: hidden;
        }
        .team-card::after {
          content: "";
          position: absolute; inset: 0;
          background: radial-gradient(circle at 100% 100%, rgba(0,0,0,.4), transparent 60%);
        }
        .team-card h4 {
          margin: 0;
          font-family: var(--font-display);
          font-size: 28px;
          font-weight: 700;
          letter-spacing: -0.02em;
          z-index: 1; position: relative;
        }
        .team-card .mono.small { font-size: 11px; opacity: 0.7; z-index: 1; position: relative; letter-spacing: 0.1em; }
      `}</style>
    </main>
  );
}

/* ============================================================
   VARIANT 3 · "Editorial" — full-bleed lookbook
   ============================================================ */
function HomeEditorial({ go, addToCart, toggleFav, wishlist, cardStyle, featured, drops }) {
  return (
    <main className="home-edi">
      <section className="edi-hero">
        <div className="edi-hero-img img-ph" style={{ background: "linear-gradient(160deg,#0b0d12 30%, #1f2933 70%, #c8ff00 200%)" }}>
          <span className="label" style={{ background: "rgba(0,0,0,.4)", color: "white", border: 0 }}>FOTO EDITORIAL — KIT 26</span>
        </div>
        <div className="edi-hero-content">
          <div className="container">
            <span className="eyebrow" style={{ color: "rgba(255,255,255,.7)" }}>VOLUME 03 — MAY 2026</span>
            <h1 className="display edi-h1">
              The new<br/><i>matchday</i><br/>uniform.
            </h1>
            <div className="row" style={{ gap: 12, marginTop: 32 }}>
              <button className="btn lg" onClick={() => go("plp", { cat: "camisas" })}>Comprar a coleção</button>
              <button className="btn lg ghost" onClick={() => go("plp")}>Ler editorial</button>
            </div>
          </div>
        </div>
      </section>

      <section className="container" style={{ paddingTop: 80 }}>
        <div className="edi-quote">
          <span className="eyebrow">№ 01</span>
          <h2 className="display" style={{ fontFamily: "'Instrument Serif',serif", fontStyle: "italic", fontWeight: 400, fontSize: "clamp(36px,5vw,72px)", letterSpacing: "-0.01em" }}>
            "Roupa não é só identidade. É a primeira camada de performance."
          </h2>
          <span className="mono small" style={{ color: "var(--muted)" }}>— DIRETOR DE PRODUTO STADIA</span>
        </div>
      </section>

      <section className="container" style={{ paddingTop: 80 }}>
        <SectionHead kicker="DROP MATCHDAY" title="Coleção da semana"/>
        <div className="edi-grid">
          {drops.concat(featured).slice(0, 6).map((p) => (
            <ProductCard key={p.id} p={p} variant="editorial"
              faved={wishlist.includes(p.id)}
              onOpen={() => go("pdp", { id: p.id })}
              onFav={() => toggleFav(p.id)}
              onAdd={() => addToCart(p)}/>
          ))}
        </div>
      </section>

      <section className="container" style={{ paddingTop: 80 }}>
        <div className="edi-split">
          <div className="edi-split-img img-ph" style={{ background: "linear-gradient(150deg, #1a1f3b, #ff4566 220%)" }}>
            <span className="label" style={{ background: "rgba(0,0,0,.4)", color: "white", border: 0 }}>foto femme — meteora</span>
          </div>
          <div className="edi-split-text">
            <span className="eyebrow">№ 02 · COLEÇÃO FEMME</span>
            <h2 className="display" style={{ fontFamily: "'Instrument Serif',serif", fontStyle: "italic", fontWeight: 400, fontSize: "clamp(40px,5vw,72px)" }}>
              Athletica.
            </h2>
            <p style={{ color: "var(--fg-2)", maxWidth: 480, fontSize: 17, lineHeight: 1.6 }}>
              Modelagem feminina sem concessões. 14 silhuetas desenhadas em conjunto com atletas das ligas regionais — testadas em jogo, ajustadas no traço.
            </p>
            <button className="btn outline lg" onClick={() => go("plp", { cat: "femme" })}>
              Ver coleção <Icon name="arrow-right" size={16}/>
            </button>
          </div>
        </div>
      </section>

      <section className="container" style={{ paddingTop: 80 }}>
        <SectionHead kicker="MAIS DESEJADOS" title="Trending"/>
        <div className="edi-grid">
          {featured.slice(0, 6).map((p) => (
            <ProductCard key={p.id} p={p} variant="editorial"
              faved={wishlist.includes(p.id)}
              onOpen={() => go("pdp", { id: p.id })}
              onFav={() => toggleFav(p.id)}
              onAdd={() => addToCart(p)}/>
          ))}
        </div>
      </section>

      <style>{`
        .home-edi { padding-bottom: 60px; }
        .edi-hero {
          position: relative;
          height: min(820px, 100vh);
          margin-bottom: 0;
        }
        [data-viewport="mobile"] .edi-hero { height: 600px; }
        .edi-hero-img {
          position: absolute; inset: 0;
        }
        .edi-hero-img::after {
          content: "";
          position: absolute; inset: 0;
          background: linear-gradient(180deg, transparent 30%, rgba(0,0,0,.7) 100%);
        }
        .edi-hero-content {
          position: absolute;
          inset: 0;
          display: flex; align-items: flex-end;
          padding-bottom: 64px;
          color: white;
        }
        .edi-h1 {
          font-family: 'Instrument Serif', Georgia, serif;
          font-style: italic;
          font-weight: 400;
          font-size: clamp(56px, 9vw, 168px);
          line-height: 0.94;
          letter-spacing: -0.02em;
          margin: 12px 0 0;
        }
        .edi-h1 i { color: var(--accent); }

        .edi-quote {
          max-width: 920px;
          margin: 0 auto;
          text-align: center;
          padding: 32px 0;
        }
        .edi-quote h2 { margin: 16px 0; text-wrap: balance; }

        .edi-grid {
          display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px;
        }
        @media (max-width: 1000px) { .edi-grid { grid-template-columns: repeat(2, 1fr); } }
        [data-viewport="mobile"] .edi-grid { grid-template-columns: repeat(2, 1fr); gap: 12px; }

        .edi-split {
          display: grid; grid-template-columns: 1fr 1fr; gap: 64px; align-items: center;
        }
        @media (max-width: 900px) { .edi-split { grid-template-columns: 1fr; gap: 32px; } }
        .edi-split-img { aspect-ratio: 4/5; border-radius: var(--r-md); }
        .edi-split-text { display: flex; flex-direction: column; gap: 16px; align-items: flex-start; }
      `}</style>
    </main>
  );
}

window.STADIA_HOME = Home;
