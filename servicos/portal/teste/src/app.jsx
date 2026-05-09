// STADIA — App shell, routing, state, screen orchestration

const { useState, useEffect, useMemo, useCallback, useRef } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "#c8ff00",
  "fontPair": "neo-grotesque",
  "density": "regular",
  "dark": true,
  "cardStyle": "lift",
  "device": "desktop"
}/*EDITMODE-END*/;

/* Adapter: wrap STADIA_UI.ProductCard so screens that use the
   <ProductCard product={...} go={...} wishlist toggleWish addToCart/>
   signature (Wishlist, Confirmation recs) work too. */
function ProductCardAdapter({ product, go, wishlist = [], toggleWish = () => {}, addToCart = () => {} }) {
  const PC = window.STADIA_UI.ProductCard;
  return (
    <PC p={product} variant="minimal"
      faved={wishlist.includes(product.id)}
      onOpen={() => go("pdp", { id: product.id })}
      onAdd={() => addToCart(product, 1, { size: product.sizes?.[0], color: product.colors?.[0]?.name })}
      onFav={() => toggleWish(product.id)}/>
  );
}
window.STADIA_PRODUCT_CARD = ProductCardAdapter;

/* New-address form adapter shared with checkout */
function NewAddressFormShared({ onAdd, onCancel }) {
  const [f, setF] = useState({ label: "Casa", name: "", zip: "", street: "", district: "", city: "", state: "", phone: "" });
  const [err, setErr] = useState({});
  const submit = () => {
    const e = {};
    ["name", "zip", "street", "district", "city", "state"].forEach((k) => { if (!f[k]) e[k] = "Obrigatório"; });
    setErr(e);
    if (Object.keys(e).length === 0) onAdd({ ...f, id: "a" + Date.now() });
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
        <div className="field"><label>CEP</label><input className={"input " + (err.zip ? "error" : "")} value={f.zip} onChange={(e) => setF({ ...f, zip: e.target.value })} placeholder="00000-000"/></div>
        <div className="field"><label>TELEFONE</label><input className="input" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} placeholder="(11) 9 0000-0000"/></div>
        <div className="field" style={{ gridColumn: "1 / -1" }}><label>RUA / NÚMERO</label><input className={"input " + (err.street ? "error" : "")} value={f.street} onChange={(e) => setF({ ...f, street: e.target.value })}/></div>
        <div className="field"><label>BAIRRO</label><input className={"input " + (err.district ? "error" : "")} value={f.district} onChange={(e) => setF({ ...f, district: e.target.value })}/></div>
        <div className="field"><label>CIDADE</label><input className={"input " + (err.city ? "error" : "")} value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })}/></div>
        <div className="field"><label>UF</label><input className={"input " + (err.state ? "error" : "")} value={f.state} onChange={(e) => setF({ ...f, state: e.target.value.toUpperCase().slice(0, 2) })}/></div>
      </div>
      <div className="row" style={{ gap: 8, marginTop: 16 }}>
        <button className="btn ghost" onClick={onCancel}>Cancelar</button>
        <button className="btn" onClick={submit}>Salvar endereço</button>
      </div>
    </div>
  );
}
window.STADIA_NEW_ADDRESS = NewAddressFormShared;

/* ===========================================================
   App — routing + global state + orchestration
   =========================================================== */
function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  // Routing
  const [route, setRoute] = useState({ name: "home", params: {} });
  const go = useCallback((name, params = {}) => {
    setRoute({ name, params });
    window.scrollTo({ top: 0, behavior: "instant" });
  }, []);

  // User
  const [user, setUser] = useState(null);
  const login = useCallback((u) => setUser(u), []);
  const logout = useCallback(() => { setUser(null); go("home"); }, [go]);

  // Cart
  const [cart, setCart] = useState([]);
  const addToCart = useCallback((product, qty = 1, opts = {}) => {
    setCart((cs) => {
      const key = (i) => i.id + "|" + (i.size || "") + "|" + (i.color || "");
      const newKey = product.id + "|" + (opts.size || "") + "|" + (opts.color || "");
      const exists = cs.find((i) => key(i) === newKey);
      if (exists) return cs.map((i) => key(i) === newKey ? { ...i, qty: i.qty + qty } : i);
      return [...cs, { id: product.id, qty, size: opts.size, color: opts.color }];
    });
    setToast({ msg: "Adicionado: " + product.name, kind: "success", id: Date.now() });
    setCartFlash(true);
    setTimeout(() => setCartFlash(false), 800);
  }, []);
  const updateCartQty = useCallback((id, size, color, qty) => {
    setCart((cs) => cs.map((i) => i.id === id && i.size === size && i.color === color ? { ...i, qty: Math.max(1, qty) } : i));
  }, []);
  const removeFromCart = useCallback((id, size, color) => {
    setCart((cs) => cs.filter((i) => !(i.id === id && i.size === size && i.color === color)));
  }, []);

  // Wishlist
  const [wishlist, setWishlist] = useState(["p02", "p05"]);
  const toggleWish = useCallback((id) => {
    setWishlist((ws) => ws.includes(id) ? ws.filter((x) => x !== id) : [...ws, id]);
  }, []);

  // Addresses + Orders (seeded from data)
  const [addresses, setAddresses] = useState(window.STADIA_DATA.ADDRESSES);
  const addAddress = useCallback((a) => setAddresses((as) => [...as, { ...a, primary: as.length === 0 }]), []);
  const removeAddress = useCallback((id) => setAddresses((as) => as.filter((a) => a.id !== id)), []);
  const setPrimaryAddress = useCallback((id) => setAddresses((as) => as.map((a) => ({ ...a, primary: a.id === id }))), []);

  const [orders, setOrders] = useState(window.STADIA_DATA.ORDERS || []);
  const placeOrder = useCallback((o) => {
    setOrders((os) => [{ ...o, status: "preparing" }, ...os]);
    setCart([]);
  }, []);

  // Toast + cart flash
  const [toast, setToast] = useState(null);
  const [cartFlash, setCartFlash] = useState(false);

  // Apply tweaks → CSS vars on root
  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = t.dark ? "dark" : "light";
    root.dataset.density = t.density;
    root.dataset.fontPair = t.fontPair;
    root.style.setProperty("--accent", t.accent);
    // accent-ink (foreground on accent fill) — pick black for bright accents, white for dark
    const c = t.accent.replace("#", "");
    const r = parseInt(c.slice(0, 2), 16) || 200;
    const g = parseInt(c.slice(2, 4), 16) || 255;
    const b = parseInt(c.slice(4, 6), 16) || 0;
    const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    root.style.setProperty("--accent-ink", lum > 0.55 ? "#0a0c10" : "#fafafa");
    // glow
    root.style.setProperty("--accent-glow", `color-mix(in oklab, ${t.accent} 38%, transparent)`);
  }, [t.accent, t.dark, t.density, t.fontPair]);

  // Device frame for mobile preview
  const deviceClass = t.device === "mobile" ? "device-mobile" : "device-desktop";

  // Active screen
  const screen = useMemo(() => {
    const props = { go, addToCart, toggleFav: toggleWish, wishlist, cardStyle: t.cardStyle };
    switch (route.name) {
      case "home": return <window.STADIA_HOME {...props} variant={route.params.v || "kinetic"}/>;
      case "plp": return <window.STADIA_PLP {...props} params={route.params}/>;
      case "pdp": return <window.STADIA_PDP {...props} params={route.params} variant={route.params.v || "editorial"}/>;
      case "cart": return <window.STADIA_CART go={go} cart={cart} updateCartQty={updateCartQty} removeFromCart={removeFromCart} addToCart={addToCart} wishlist={wishlist} toggleFav={toggleWish}/>;
      case "checkout": return <window.STADIA_CHECKOUT go={go} cart={cart} user={user || { name: "Convidado", email: "" }} addresses={addresses} addAddress={addAddress} placeOrder={placeOrder}/>;
      case "auth": return <window.STADIA_AUTH go={go} mode={route.params.mode || "login"} login={login}/>;
      case "account":
        if (!user) return <window.STADIA_AUTH go={go} mode="login" login={login}/>;
        return <window.STADIA_ACCOUNT go={go} route={route.params} user={user} addresses={addresses} addAddress={addAddress} removeAddress={removeAddress} setPrimaryAddress={setPrimaryAddress} orders={orders} wishlist={wishlist} toggleWish={toggleWish} addToCart={addToCart} logout={logout}/>;
      case "confirmation": return <window.STADIA_CONFIRMATION go={go} route={route.params} orders={orders}/>;
      default: return <window.STADIA_HOME {...props} variant="kinetic"/>;
    }
  }, [route, cart, user, wishlist, addresses, orders, t.cardStyle, go, addToCart, updateCartQty, removeFromCart, toggleWish, login, logout, placeOrder, addAddress, removeAddress, setPrimaryAddress]);

  const showHeader = !["auth", "checkout", "confirmation"].includes(route.name);
  const showFooter = !["auth", "checkout"].includes(route.name);

  const { Header, Footer, Toast } = window.STADIA_UI;

  return (
    <div className={"stadia-app " + deviceClass}>
      <div className="device-stage">
        <div className="device-frame">
          {showHeader && <Header route={route} go={go} cart={cart} wishlist={wishlist} user={user} density={t.density} cartFlash={cartFlash}/>}
          {screen}
          {showFooter && <Footer go={go}/>}
        </div>
      </div>

      {toast && <Toast {...toast} onDone={() => setToast(null)}/>}

      <StadiaTweaks t={t} setTweak={setTweak}/>
    </div>
  );
}

/* ===========================================================
   Tweaks panel
   =========================================================== */
function StadiaTweaks({ t, setTweak }) {
  return (
    <TweaksPanel title="Tweaks">
      <TweakSection label="Tema"/>
      <TweakToggle label="Modo escuro" value={t.dark} onChange={(v) => setTweak("dark", v)}/>
      <TweakColor label="Cor de destaque" value={t.accent}
        options={["#c8ff00", "#7c5cff", "#00e5a0", "#ff4500", "#ffb020"]}
        onChange={(v) => setTweak("accent", v)}/>

      <TweakSection label="Tipografia"/>
      <TweakRadio label="Pareamento" value={t.fontPair}
        options={[
          { value: "neo-grotesque", label: "Bold sans" },
          { value: "editorial", label: "Editorial" },
        ]}
        onChange={(v) => setTweak("fontPair", v)}/>

      <TweakSection label="Layout"/>
      <TweakRadio label="Densidade" value={t.density}
        options={[
          { value: "compact", label: "Compacto" },
          { value: "regular", label: "Regular" },
          { value: "comfy", label: "Espaçoso" },
        ]}
        onChange={(v) => setTweak("density", v)}/>
      <TweakSelect label="Estilo de card" value={t.cardStyle}
        options={[
          { value: "lift", label: "Lift (hover up)" },
          { value: "flat", label: "Flat" },
          { value: "frame", label: "Frame (com borda)" },
          { value: "blur", label: "Blur metric" },
        ]}
        onChange={(v) => setTweak("cardStyle", v)}/>

      <TweakSection label="Preview"/>
      <TweakRadio label="Dispositivo" value={t.device}
        options={[
          { value: "desktop", label: "Desktop" },
          { value: "mobile", label: "Mobile" },
        ]}
        onChange={(v) => setTweak("device", v)}/>
    </TweaksPanel>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
