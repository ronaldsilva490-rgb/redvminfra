// STADIA — Account screens (orders, addresses, wishlist, profile)

function Account({ go, route, user, addresses, addAddress, removeAddress, setPrimaryAddress, orders, wishlist, toggleWish, addToCart, logout }) {
  const { PRODUCTS } = window.STADIA_DATA;
  const tab = route.tab || "overview";

  const navItems = [
    { id: "overview", l: "Visão geral", ic: "user" },
    { id: "orders", l: "Pedidos", ic: "package", badge: orders.length },
    { id: "addresses", l: "Endereços", ic: "pin", badge: addresses.length },
    { id: "wishlist", l: "Favoritos", ic: "heart", badge: wishlist.length },
    { id: "profile", l: "Perfil", ic: "settings" },
  ];

  return (
    <main className="acc-main">
      <div className="container">
        <header className="acc-head">
          <div>
            <span className="eyebrow">CLUBE STADIA</span>
            <h1 className="display">Olá, {user.name.split(" ")[0]} <span style={{ color: "var(--accent)" }}>↗</span></h1>
            <p style={{ color: "var(--muted)", margin: 0 }}>Seu espaço para pedidos, favoritos e configurações.</p>
          </div>
          <div className="acc-stats">
            <div><b>{orders.length}</b><span className="mono small">PEDIDOS</span></div>
            <div><b>{wishlist.length}</b><span className="mono small">FAVORITOS</span></div>
            <div><b>1.840</b><span className="mono small">PONTOS</span></div>
          </div>
        </header>

        <div className="acc-grid">
          <aside className="acc-side">
            <nav className="acc-nav">
              {navItems.map((n) => (
                <button key={n.id} className={"acc-nav-item " + (tab === n.id ? "on" : "")}
                  onClick={() => go("account", { tab: n.id })}>
                  <Icon name={n.ic} size={16}/>
                  <span>{n.l}</span>
                  {n.badge != null && <span className="acc-nav-badge mono">{n.badge}</span>}
                  <Icon name="chevron-right" size={14} />
                </button>
              ))}
              <div className="acc-nav-divider"/>
              <button className="acc-nav-item logout" onClick={logout}>
                <Icon name="logout" size={16}/>
                <span>Sair</span>
              </button>
            </nav>

            <div className="acc-side-card">
              <span className="eyebrow">PRÓXIMO NÍVEL</span>
              <h4>STADIA PRO</h4>
              <div className="acc-progress">
                <span style={{ width: "62%" }}/>
              </div>
              <span className="mono small" style={{ color: "var(--muted)" }}>1.840 / 3.000 PTS</span>
              <p style={{ fontSize: 13, color: "var(--fg-2)", margin: "8px 0 0" }}>Faltam 1.160 pontos para frete grátis ilimitado.</p>
            </div>
          </aside>

          <section className="acc-content">
            {tab === "overview" && <Overview go={go} orders={orders} wishlist={wishlist}/>}
            {tab === "orders" && <Orders go={go} orders={orders}/>}
            {tab === "addresses" && <Addresses addresses={addresses} addAddress={addAddress} removeAddress={removeAddress} setPrimaryAddress={setPrimaryAddress}/>}
            {tab === "wishlist" && <Wishlist wishlist={wishlist} go={go} toggleWish={toggleWish} addToCart={addToCart}/>}
            {tab === "profile" && <Profile user={user}/>}
          </section>
        </div>
      </div>
      <AccountStyles/>
    </main>
  );
}

function Overview({ go, orders, wishlist }) {
  const { BRL } = window.STADIA_UI;
  const lastOrder = orders[0];
  return (
    <div className="acc-block">
      <div className="acc-cards">
        <div className="acc-card-lg">
          <div className="row between" style={{ marginBottom: 16 }}>
            <span className="eyebrow">ÚLTIMO PEDIDO</span>
            {lastOrder && <span className={"chip status status-" + lastOrder.status}>{statusLabel(lastOrder.status)}</span>}
          </div>
          {lastOrder ? (
            <>
              <h3 className="display">{lastOrder.id}</h3>
              <div className="track-bar">
                {["paid", "preparing", "shipping", "delivered"].map((s, i) => {
                  const idx = ["paid", "preparing", "shipping", "delivered"].indexOf(lastOrder.status);
                  return (
                    <div key={s} className={"track-step " + (i <= idx ? "done" : "")}>
                      <span className="track-dot"/>
                      <span className="mono small">{["PAGO", "PREPARO", "ENVIADO", "ENTREGUE"][i]}</span>
                    </div>
                  );
                })}
              </div>
              <div className="row between" style={{ marginTop: 16 }}>
                <span style={{ color: "var(--muted)" }}>{lastOrder.items.length} itens · {BRL(lastOrder.total)}</span>
                <button className="btn outline sm" onClick={() => go("account", { tab: "orders" })}>
                  Ver detalhes <Icon name="arrow-right" size={12}/>
                </button>
              </div>
            </>
          ) : (
            <p style={{ color: "var(--muted)" }}>Você ainda não fez pedidos.</p>
          )}
        </div>

        <div className="acc-card-sm" onClick={() => go("account", { tab: "wishlist" })} style={{ cursor: "pointer" }}>
          <span className="eyebrow">FAVORITOS</span>
          <h3 className="display" style={{ fontSize: 48 }}>{wishlist.length}</h3>
          <span className="mono small" style={{ color: "var(--muted)" }}>ITENS NA LISTA</span>
        </div>

        <div className="acc-card-sm gradient">
          <span className="eyebrow">CASHBACK</span>
          <h3 className="display" style={{ fontSize: 36, color: "var(--accent-ink)" }}>R$ 84,20</h3>
          <span className="mono small" style={{ color: "color-mix(in oklab, var(--accent-ink) 70%, transparent)" }}>DISPONÍVEL</span>
        </div>
      </div>

      <div style={{ marginTop: 32 }}>
        <h3 style={{ fontFamily: "var(--font-display)", fontSize: 22, margin: "0 0 16px" }}>Atalhos</h3>
        <div className="acc-shortcuts">
          {[
            { ic: "package", l: "Rastrear pedido", s: "Status em tempo real" },
            { ic: "truck", l: "Trocas e devoluções", s: "30 dias para trocar" },
            { ic: "headset", l: "Falar com suporte", s: "24/7 com atletas reais" },
            { ic: "card", l: "Métodos de pagamento", s: "Salve seus cartões" },
          ].map((s) => (
            <button key={s.l} className="acc-shortcut">
              <Icon name={s.ic} size={20}/>
              <div>
                <h5>{s.l}</h5>
                <span className="mono small">{s.s}</span>
              </div>
              <Icon name="arrow-up-right" size={14}/>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Orders({ go, orders }) {
  const { PRODUCTS } = window.STADIA_DATA;
  const { BRL } = window.STADIA_UI;
  const [open, setOpen] = React.useState(null);
  const [filter, setFilter] = React.useState("all");

  const filtered = orders.filter((o) => filter === "all" || o.status === filter);

  return (
    <div className="acc-block">
      <div className="row between" style={{ marginBottom: 24 }}>
        <h3 style={{ fontFamily: "var(--font-display)", fontSize: 22, margin: 0 }}>Seus pedidos</h3>
        <div className="row" style={{ gap: 6 }}>
          {[
            { id: "all", l: "Todos" },
            { id: "preparing", l: "Em preparo" },
            { id: "shipping", l: "Enviados" },
            { id: "delivered", l: "Entregues" },
          ].map((f) => (
            <button key={f.id} className={"chip-toggle " + (filter === f.id ? "on" : "")} onClick={() => setFilter(f.id)}>{f.l}</button>
          ))}
        </div>
      </div>

      <div className="orders-list">
        {filtered.length === 0 && (
          <div className="empty">
            <Icon name="package" size={32}/>
            <h4>Nada por aqui ainda</h4>
            <p>Quando você fizer um pedido, ele aparece aqui.</p>
          </div>
        )}
        {filtered.map((o) => {
          const items = o.items.map((i) => ({ ...i, p: PRODUCTS.find((x) => x.id === i.id) || i.p })).filter(i => i.p);
          const isOpen = open === o.id;
          return (
            <article key={o.id} className={"order-card " + (isOpen ? "open" : "")}>
              <header className="order-head" onClick={() => setOpen(isOpen ? null : o.id)}>
                <div className="order-thumbs">
                  {items.slice(0, 3).map((i, idx) => (
                    <div key={idx} className="order-thumb img-ph has-viz" style={{ background: i.p.imageBg }}>
                      <STADIA_PRODUCT_VISUAL p={i.p}/>
                    </div>
                  ))}
                  {items.length > 3 && <div className="order-thumb-more mono">+{items.length - 3}</div>}
                </div>
                <div className="order-info">
                  <div className="row" style={{ gap: 12 }}>
                    <span className="mono small" style={{ color: "var(--muted)" }}>PEDIDO {o.id}</span>
                    <span className={"chip status status-" + o.status}>{statusLabel(o.status)}</span>
                  </div>
                  <h4>{items.length} {items.length === 1 ? "item" : "itens"} · {BRL(o.total)}</h4>
                  <span className="mono small" style={{ color: "var(--muted)" }}>{formatDate(o.placedAt)}</span>
                </div>
                <div className="order-toggle">
                  <Icon name="chevron-down" size={18}/>
                </div>
              </header>

              {isOpen && (
                <div className="order-body">
                  <div className="track-bar">
                    {["paid", "preparing", "shipping", "delivered"].map((s, i) => {
                      const idx = ["paid", "preparing", "shipping", "delivered"].indexOf(o.status);
                      return (
                        <div key={s} className={"track-step " + (i <= idx ? "done" : "")}>
                          <span className="track-dot"/>
                          <span className="mono small">{["PAGO", "PREPARO", "ENVIADO", "ENTREGUE"][i]}</span>
                        </div>
                      );
                    })}
                  </div>

                  <div className="order-items">
                    {items.map((i, idx) => (
                      <div key={idx} className="order-item">
                        <div className="order-thumb-lg img-ph has-viz" style={{ background: i.p.imageBg }}>
                          <STADIA_PRODUCT_VISUAL p={i.p}/>
                        </div>
                        <div className="order-item-info">
                          <span className="mono small" style={{ color: "var(--muted)" }}>{i.p.sub}</span>
                          <h5>{i.p.name}</h5>
                          <span className="mono small">{i.color || i.p.colors?.[0]?.name} · {i.size || i.p.sizes?.[0]} · QTD {i.qty}</span>
                        </div>
                        <div className="order-item-price">
                          <span className="mono">{BRL(i.p.price * i.qty)}</span>
                          <button className="link" onClick={() => go("pdp", { id: i.p.id })}>Ver produto</button>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="order-footer">
                    {o.address && (
                      <div>
                        <span className="mono small" style={{ color: "var(--muted)" }}>ENTREGA</span>
                        <p style={{ margin: "4px 0 0" }}>{o.address.street}<br/>{o.address.district} · {o.address.city}/{o.address.state}</p>
                      </div>
                    )}
                    <div className="row" style={{ gap: 8 }}>
                      <button className="btn outline sm">Rastrear</button>
                      <button className="btn outline sm">Nota fiscal</button>
                      {o.status === "delivered" && <button className="btn sm">Comprar de novo</button>}
                    </div>
                  </div>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}

function Addresses({ addresses, addAddress, removeAddress, setPrimaryAddress }) {
  const [showForm, setShowForm] = React.useState(false);

  return (
    <div className="acc-block">
      <div className="row between" style={{ marginBottom: 24 }}>
        <h3 style={{ fontFamily: "var(--font-display)", fontSize: 22, margin: 0 }}>Endereços salvos</h3>
        <button className="btn sm" onClick={() => setShowForm(!showForm)}><Icon name="plus" size={14}/> Novo endereço</button>
      </div>

      {showForm && (
        <div style={{ marginBottom: 24 }}>
          {window.STADIA_NEW_ADDRESS && (
            <window.STADIA_NEW_ADDRESS onAdd={(a) => { addAddress(a); setShowForm(false); }} onCancel={() => setShowForm(false)}/>
          )}
        </div>
      )}

      <div className="addr-grid">
        {addresses.length === 0 && (
          <div className="empty" style={{ gridColumn: "1 / -1" }}>
            <Icon name="pin" size={32}/>
            <h4>Nenhum endereço salvo</h4>
            <p>Adicione um endereço para agilizar seus pedidos.</p>
          </div>
        )}
        {addresses.map((a) => (
          <article key={a.id} className={"addr-tile " + (a.primary ? "primary" : "")}>
            <div className="row between" style={{ marginBottom: 12 }}>
              <div className="row" style={{ gap: 8 }}>
                <h4>{a.label}</h4>
                {a.primary && <span className="chip" style={{ height: 22 }}>PADRÃO</span>}
              </div>
              <Icon name="pin" size={18} stroke={1.5}/>
            </div>
            <div style={{ color: "var(--fg)" }}>{a.name}</div>
            <div style={{ color: "var(--muted)" }}>{a.street}</div>
            <div style={{ color: "var(--muted)" }}>{a.district} · {a.city}/{a.state} · {a.zip}</div>
            {a.phone && <div style={{ color: "var(--muted)" }}>{a.phone}</div>}
            <div className="row" style={{ gap: 8, marginTop: 16 }}>
              {!a.primary && <button className="btn outline sm" onClick={() => setPrimaryAddress(a.id)}>Definir padrão</button>}
              <button className="btn ghost sm">Editar</button>
              <button className="btn ghost sm" style={{ marginLeft: "auto", color: "var(--accent-2)" }} onClick={() => removeAddress(a.id)}>
                <Icon name="trash" size={14}/>
              </button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function Wishlist({ wishlist, go, toggleWish, addToCart }) {
  const { PRODUCTS } = window.STADIA_DATA;
  const items = wishlist.map((id) => PRODUCTS.find((p) => p.id === id)).filter(Boolean);
  const ProductCard = window.STADIA_PRODUCT_CARD;

  return (
    <div className="acc-block">
      <div className="row between" style={{ marginBottom: 24 }}>
        <h3 style={{ fontFamily: "var(--font-display)", fontSize: 22, margin: 0 }}>Seus favoritos</h3>
        <span className="mono small" style={{ color: "var(--muted)" }}>{items.length} {items.length === 1 ? "ITEM" : "ITENS"}</span>
      </div>

      {items.length === 0 ? (
        <div className="empty">
          <Icon name="heart" size={32}/>
          <h4>Nenhum favorito ainda</h4>
          <p>Salve produtos para comparar e comprar depois.</p>
          <button className="btn" onClick={() => go("plp")}>Explorar produtos</button>
        </div>
      ) : (
        <div className="wish-grid">
          {items.map((p) => (
            <ProductCard key={p.id} product={p} go={go} wishlist={wishlist} toggleWish={toggleWish} addToCart={addToCart}/>
          ))}
        </div>
      )}
    </div>
  );
}

function Profile({ user }) {
  return (
    <div className="acc-block">
      <h3 style={{ fontFamily: "var(--font-display)", fontSize: 22, margin: "0 0 24px" }}>Seu perfil</h3>
      <div className="profile-card">
        <div className="profile-avatar">{user.name.split(" ").map(s => s[0]).slice(0, 2).join("")}</div>
        <div style={{ flex: 1 }}>
          <h4 style={{ margin: 0 }}>{user.name}</h4>
          <span style={{ color: "var(--muted)" }}>{user.email}</span>
        </div>
        <button className="btn outline sm">Alterar foto</button>
      </div>

      <div className="profile-grid">
        <div className="field">
          <label>NOME COMPLETO</label>
          <input className="input" defaultValue={user.name}/>
        </div>
        <div className="field">
          <label>EMAIL</label>
          <input className="input" defaultValue={user.email}/>
        </div>
        <div className="field">
          <label>CPF</label>
          <input className="input" placeholder="000.000.000-00"/>
        </div>
        <div className="field">
          <label>TELEFONE</label>
          <input className="input" placeholder="(11) 9 0000-0000"/>
        </div>
        <div className="field">
          <label>DATA DE NASCIMENTO</label>
          <input className="input" placeholder="DD/MM/AAAA"/>
        </div>
        <div className="field">
          <label>GÊNERO</label>
          <select className="input"><option>Prefiro não dizer</option><option>Masculino</option><option>Feminino</option><option>Outro</option></select>
        </div>
      </div>

      <div className="row" style={{ gap: 8, marginTop: 24 }}>
        <button className="btn">Salvar alterações</button>
        <button className="btn ghost">Alterar senha</button>
      </div>
    </div>
  );
}

function statusLabel(s) {
  return { paid: "Pago", preparing: "Em preparo", shipping: "Enviado", delivered: "Entregue", cancelled: "Cancelado" }[s] || s;
}

function formatDate(d) {
  const date = new Date(d);
  return date.toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" });
}

function AccountStyles() {
  return (
    <style>{`
      .acc-main { padding: 32px 0 80px; }
      .acc-head { display: grid; grid-template-columns: 1fr auto; gap: 32px; align-items: center; padding-bottom: 32px; border-bottom: 1px solid var(--line); margin-bottom: 32px; }
      .acc-head h1 { margin: 8px 0; font-size: clamp(40px, 5vw, 64px); letter-spacing: -0.04em; }
      .acc-stats { display: flex; gap: 32px; }
      .acc-stats > div { display: flex; flex-direction: column; }
      .acc-stats b { font-family: var(--font-display); font-size: 32px; font-weight: 700; letter-spacing: -0.03em; line-height: 1; }
      .acc-stats .small { color: var(--muted); margin-top: 4px; }

      .acc-grid { display: grid; grid-template-columns: 260px 1fr; gap: 48px; }
      @media (max-width: 900px) { .acc-grid { grid-template-columns: 1fr; gap: 24px; } }

      .acc-side { display: flex; flex-direction: column; gap: 16px; position: sticky; top: 16px; align-self: start; }
      @media (max-width: 900px) { .acc-side { position: static; } }
      .acc-nav { display: flex; flex-direction: column; gap: 4px; padding: 8px; background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-md); }
      .acc-nav-item {
        display: grid; grid-template-columns: 16px 1fr auto auto;
        gap: 12px; align-items: center;
        padding: 10px 12px;
        background: transparent; border: 0; color: var(--fg-2);
        font-family: inherit; font-size: 14px; text-align: left;
        border-radius: var(--r-sm); cursor: pointer;
      }
      .acc-nav-item:hover { color: var(--fg); background: var(--bg-2); }
      .acc-nav-item.on { background: var(--bg-2); color: var(--fg); }
      .acc-nav-item.on::before { content: ""; width: 3px; background: var(--accent); position: absolute; left: 0; top: 8px; bottom: 8px; border-radius: 2px; }
      .acc-nav-item { position: relative; }
      .acc-nav-badge { font-size: 11px; color: var(--muted); padding: 2px 6px; background: var(--bg-3); border-radius: 999px; }
      .acc-nav-divider { height: 1px; background: var(--line); margin: 8px 4px; }
      .acc-nav-item.logout:hover { color: var(--accent-2); }

      .acc-side-card {
        padding: 20px;
        background: var(--surface); border: 1px solid var(--line);
        border-radius: var(--r-md);
        display: flex; flex-direction: column; gap: 8px;
      }
      .acc-side-card h4 { margin: 0; font-family: var(--font-display); font-size: 20px; font-weight: 800; letter-spacing: -0.02em; }
      .acc-progress { height: 6px; background: var(--bg-3); border-radius: 3px; overflow: hidden; }
      .acc-progress span { display: block; height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent-2)); }

      .acc-block { display: flex; flex-direction: column; }

      .acc-cards { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 16px; }
      @media (max-width: 800px) { .acc-cards { grid-template-columns: 1fr; } }
      .acc-card-lg, .acc-card-sm { padding: 24px; background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-md); }
      .acc-card-lg h3 { font-size: 32px; margin: 0 0 24px; letter-spacing: -0.03em; }
      .acc-card-sm { display: flex; flex-direction: column; gap: 8px; }
      .acc-card-sm.gradient { background: linear-gradient(135deg, var(--accent), var(--accent-2)); border-color: transparent; color: var(--accent-ink); }
      .acc-card-sm.gradient .eyebrow { color: var(--accent-ink); opacity: 0.8; }

      .track-bar { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; padding: 16px 0; position: relative; }
      .track-bar::before { content: ""; position: absolute; left: 8%; right: 8%; top: 50%; height: 1px; background: var(--line-2); transform: translateY(-50%); }
      .track-step { display: flex; flex-direction: column; align-items: center; gap: 8px; position: relative; z-index: 1; }
      .track-dot { width: 14px; height: 14px; border-radius: 50%; background: var(--bg-3); border: 1px solid var(--line-2); }
      .track-step.done .track-dot { background: var(--accent); border-color: var(--accent); box-shadow: 0 0 0 4px color-mix(in oklab, var(--accent) 16%, transparent); }
      .track-step .small { color: var(--muted); font-size: 10px; }
      .track-step.done .small { color: var(--fg); }

      .acc-shortcuts { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
      @media (max-width: 800px) { .acc-shortcuts { grid-template-columns: 1fr; } }
      .acc-shortcut {
        display: grid; grid-template-columns: 32px 1fr 14px; gap: 16px; align-items: center;
        padding: 16px; background: var(--surface); border: 1px solid var(--line);
        border-radius: var(--r-md); cursor: pointer;
        color: inherit; font-family: inherit; text-align: left;
        transition: border-color .2s;
      }
      .acc-shortcut:hover { border-color: var(--accent); }
      .acc-shortcut h5 { margin: 0; font-family: var(--font-display); font-size: 14px; font-weight: 600; }
      .acc-shortcut .small { color: var(--muted); }
      .acc-shortcut svg:first-child { color: var(--accent); }

      /* ORDERS */
      .orders-list { display: flex; flex-direction: column; gap: 12px; }
      .order-card { background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-md); overflow: hidden; }
      .order-head { display: grid; grid-template-columns: auto 1fr auto; gap: 24px; align-items: center; padding: 16px; cursor: pointer; }
      .order-thumbs { display: flex; }
      .order-thumb { width: 60px; height: 60px; border-radius: var(--r-sm); margin-right: -12px; border: 2px solid var(--surface); }
      .order-thumb-more {
        width: 60px; height: 60px; border-radius: var(--r-sm); margin-right: -12px;
        background: var(--bg-2); display: grid; place-items: center;
        font-size: 14px; font-weight: 600; color: var(--muted);
      }
      .order-info h4 { margin: 6px 0 4px; font-family: var(--font-display); font-size: 18px; font-weight: 600; }
      .order-toggle { display: grid; place-items: center; width: 40px; height: 40px; background: var(--bg-2); border-radius: 50%; transition: transform .3s; }
      .order-card.open .order-toggle { transform: rotate(180deg); }

      .order-body { padding: 0 16px 16px; border-top: 1px solid var(--line); }
      .order-items { display: flex; flex-direction: column; gap: 8px; margin-top: 16px; }
      .order-item { display: grid; grid-template-columns: 64px 1fr auto; gap: 16px; align-items: center; padding: 12px; background: var(--bg-1); border-radius: var(--r-sm); }
      .order-thumb-lg { width: 64px; aspect-ratio: 1; border-radius: 6px; }
      .order-item-info h5 { margin: 4px 0; font-family: var(--font-display); font-size: 14px; font-weight: 600; }
      .order-item-price { text-align: right; display: flex; flex-direction: column; gap: 4px; align-items: flex-end; }

      .order-footer { display: grid; grid-template-columns: 1fr auto; gap: 24px; align-items: center; margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--line); }
      @media (max-width: 700px) { .order-footer { grid-template-columns: 1fr; } }

      .chip.status-paid { background: color-mix(in oklab, var(--accent-3) 16%, transparent); color: var(--accent-3); border-color: transparent; }
      .chip.status-preparing { background: color-mix(in oklab, var(--accent) 16%, transparent); color: var(--accent); border-color: transparent; }
      .chip.status-shipping { background: color-mix(in oklab, var(--accent-2) 16%, transparent); color: var(--accent-2); border-color: transparent; }
      .chip.status-delivered { background: color-mix(in oklab, var(--accent-3) 20%, transparent); color: var(--accent-3); border-color: transparent; }

      /* ADDRESSES */
      .addr-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
      @media (max-width: 700px) { .addr-grid { grid-template-columns: 1fr; } }
      .addr-tile {
        padding: 20px; background: var(--surface); border: 1px solid var(--line);
        border-radius: var(--r-md); display: flex; flex-direction: column; gap: 4px;
      }
      .addr-tile.primary { border-color: var(--accent); background: color-mix(in oklab, var(--accent) 4%, var(--surface)); }
      .addr-tile h4 { margin: 0; font-family: var(--font-display); font-size: 16px; font-weight: 700; }

      /* WISHLIST */
      .wish-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }

      /* PROFILE */
      .profile-card {
        display: flex; align-items: center; gap: 16px; padding: 24px;
        background: var(--surface); border: 1px solid var(--line);
        border-radius: var(--r-md); margin-bottom: 24px;
      }
      .profile-avatar {
        width: 64px; height: 64px; border-radius: 50%;
        background: linear-gradient(135deg, var(--accent), var(--accent-2));
        color: var(--accent-ink);
        display: grid; place-items: center;
        font-family: var(--font-display); font-size: 22px; font-weight: 700;
      }
      .profile-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
      @media (max-width: 700px) { .profile-grid { grid-template-columns: 1fr; } }

      /* EMPTY */
      .empty {
        padding: 48px 24px; text-align: center;
        background: var(--surface); border: 1px dashed var(--line-2);
        border-radius: var(--r-md);
        display: flex; flex-direction: column; align-items: center; gap: 8px;
      }
      .empty svg { color: var(--muted); margin-bottom: 8px; }
      .empty h4 { margin: 0; font-family: var(--font-display); font-size: 18px; font-weight: 700; }
      .empty p { color: var(--muted); margin: 0 0 8px; }
    `}</style>
  );
}

window.STADIA_ACCOUNT = Account;
