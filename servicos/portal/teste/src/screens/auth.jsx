// STADIA — Auth screens (login + signup)

function Auth({ go, mode = "login", login }) {
  const [tab, setTab] = React.useState(mode);
  React.useEffect(() => setTab(mode), [mode]);

  return (
    <main className="auth-main">
      <div className="auth-split">
        <aside className="auth-side">
          <button className="brand auth-brand" onClick={() => go("home")}>
            <span className="brand-mark"/>
            <span className="brand-word">STADIA</span>
          </button>
          <div className="auth-side-content">
            <span className="eyebrow">CLUBE STADIA</span>
            <h1 className="display">Mais que uma loja.<br/>Um <span style={{ color: "var(--accent)" }}>time</span>.</h1>
            <ul className="auth-perks">
              <li><Icon name="badge-check" size={18}/> 10% off em todos os kits oficiais</li>
              <li><Icon name="truck" size={18}/> Frete express grátis acima de R$ 199</li>
              <li><Icon name="lightning" size={18}/> Drops antes de todo mundo</li>
              <li><Icon name="headset" size={18}/> Suporte 24/7 com atletas reais</li>
            </ul>
            <div className="auth-stats">
              <div><b>284K</b><span className="mono small">membros</span></div>
              <div><b>4.9</b><span className="mono small">avaliação</span></div>
              <div><b>48h</b><span className="mono small">entrega média</span></div>
            </div>
          </div>
          <div className="auth-side-bg"/>
        </aside>

        <section className="auth-form-wrap">
          <div className="auth-tabs">
            <button className={tab === "login" ? "on" : ""} onClick={() => setTab("login")}>Entrar</button>
            <button className={tab === "signup" ? "on" : ""} onClick={() => setTab("signup")}>Criar conta</button>
            <span className="auth-tab-indicator" style={{ transform: tab === "signup" ? "translateX(100%)" : "translateX(0)" }}/>
          </div>

          {tab === "login" ? <LoginForm go={go} login={login}/> : <SignupForm go={go} login={login}/>}

          <div className="auth-footer">
            <span className="mono small">PROTEGIDO POR CRIPTOGRAFIA SSL · 256-BIT</span>
          </div>
        </section>
      </div>
      <AuthStyles/>
    </main>
  );
}

function LoginForm({ go, login }) {
  const [email, setEmail] = React.useState("");
  const [pw, setPw] = React.useState("");
  const [showPw, setShowPw] = React.useState(false);
  const [err, setErr] = React.useState({});
  const [loading, setLoading] = React.useState(false);

  const submit = (e) => {
    e.preventDefault();
    const er = {};
    if (!email.match(/^\S+@\S+\.\S+$/)) er.email = "Email inválido";
    if (pw.length < 6) er.pw = "Mínimo 6 caracteres";
    setErr(er);
    if (Object.keys(er).length) return;
    setLoading(true);
    setTimeout(() => { login({ name: "Atleta Stadia", email }); go("home"); }, 800);
  };

  return (
    <form className="auth-form" onSubmit={submit}>
      <header className="auth-head">
        <span className="eyebrow">BEM-VINDO DE VOLTA</span>
        <h2 className="display">Entrar na sua conta</h2>
      </header>

      <div className="auth-social">
        <button type="button" className="btn outline social"><span className="social-mark g">G</span> Continuar com Google</button>
        <button type="button" className="btn outline social"><span className="social-mark a"></span> Continuar com Apple</button>
      </div>

      <div className="auth-divider"><span className="mono small">OU COM EMAIL</span></div>

      <div className="field">
        <label>EMAIL</label>
        <input className={"input " + (err.email ? "error" : "")} type="email" value={email}
          onChange={(e) => setEmail(e.target.value)} placeholder="voce@email.com" autoComplete="email"/>
        {err.email && <span className="err">{err.email}</span>}
      </div>

      <div className="field">
        <label className="row between">
          <span>SENHA</span>
          <button type="button" className="link" style={{ fontSize: 12 }}>Esqueci minha senha</button>
        </label>
        <div className="input-wrap">
          <input className={"input " + (err.pw ? "error" : "")} type={showPw ? "text" : "password"} value={pw}
            onChange={(e) => setPw(e.target.value)} placeholder="••••••••" autoComplete="current-password"/>
          <button type="button" className="input-eye" onClick={() => setShowPw(!showPw)} aria-label="Toggle password">
            <Icon name={showPw ? "eye-off" : "eye"} size={16}/>
          </button>
        </div>
        {err.pw && <span className="err">{err.pw}</span>}
      </div>

      <label className="row" style={{ gap: 8, fontSize: 13, color: "var(--fg-2)" }}>
        <input type="checkbox" defaultChecked/> Manter conectado neste dispositivo
      </label>

      <button className="btn lg block" type="submit" disabled={loading}>
        {loading ? <><span className="spinner"/> Entrando…</> : <>Entrar <Icon name="arrow-right" size={16}/></>}
      </button>
    </form>
  );
}

function SignupForm({ go, login }) {
  const [f, setF] = React.useState({ name: "", email: "", pw: "", team: "VLT" });
  const [show, setShow] = React.useState(false);
  const [err, setErr] = React.useState({});
  const [loading, setLoading] = React.useState(false);

  const score = (() => {
    let s = 0;
    if (f.pw.length >= 8) s++;
    if (/[A-Z]/.test(f.pw)) s++;
    if (/\d/.test(f.pw)) s++;
    if (/[^A-Za-z0-9]/.test(f.pw)) s++;
    return s;
  })();
  const scoreLabels = ["fraca", "fraca", "ok", "boa", "forte"];

  const submit = (e) => {
    e.preventDefault();
    const er = {};
    if (!f.name || f.name.length < 3) er.name = "Nome obrigatório";
    if (!f.email.match(/^\S+@\S+\.\S+$/)) er.email = "Email inválido";
    if (f.pw.length < 8) er.pw = "Mínimo 8 caracteres";
    setErr(er);
    if (Object.keys(er).length) return;
    setLoading(true);
    setTimeout(() => { login({ name: f.name, email: f.email, team: f.team }); go("home"); }, 900);
  };

  return (
    <form className="auth-form" onSubmit={submit}>
      <header className="auth-head">
        <span className="eyebrow">PRIMEIRA VEZ?</span>
        <h2 className="display">Criar sua conta Stadia</h2>
      </header>

      <div className="auth-social">
        <button type="button" className="btn outline social"><span className="social-mark g">G</span> Continuar com Google</button>
        <button type="button" className="btn outline social"><span className="social-mark a"></span> Continuar com Apple</button>
      </div>

      <div className="auth-divider"><span className="mono small">OU COM EMAIL</span></div>

      <div className="field">
        <label>NOME COMPLETO</label>
        <input className={"input " + (err.name ? "error" : "")} value={f.name}
          onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Seu nome"/>
        {err.name && <span className="err">{err.name}</span>}
      </div>

      <div className="field">
        <label>EMAIL</label>
        <input className={"input " + (err.email ? "error" : "")} type="email" value={f.email}
          onChange={(e) => setF({ ...f, email: e.target.value })} placeholder="voce@email.com"/>
        {err.email && <span className="err">{err.email}</span>}
      </div>

      <div className="field">
        <label>SENHA</label>
        <div className="input-wrap">
          <input className={"input " + (err.pw ? "error" : "")} type={show ? "text" : "password"} value={f.pw}
            onChange={(e) => setF({ ...f, pw: e.target.value })} placeholder="Mínimo 8 caracteres"/>
          <button type="button" className="input-eye" onClick={() => setShow(!show)}>
            <Icon name={show ? "eye-off" : "eye"} size={16}/>
          </button>
        </div>
        {f.pw && (
          <div className="pw-meter">
            <div className="pw-bars">
              {[0,1,2,3].map(i => <span key={i} className={i < score ? "on s" + score : ""}/>)}
            </div>
            <span className="mono small" style={{ color: score >= 3 ? "var(--accent-3)" : "var(--muted)" }}>FORÇA: {scoreLabels[score].toUpperCase()}</span>
          </div>
        )}
        {err.pw && <span className="err">{err.pw}</span>}
      </div>

      <div className="field">
        <label>TIME DO CORAÇÃO <span className="mono small" style={{ color: "var(--muted)", marginLeft: 6 }}>(OPCIONAL)</span></label>
        <div className="team-picker">
          {window.STADIA_DATA.TEAMS.slice(0, 6).map((t) => (
            <button key={t.code} type="button"
              className={"team-chip " + (f.team === t.code ? "on" : "")}
              onClick={() => setF({ ...f, team: t.code })}
              style={{ "--tc1": t.colors[0], "--tc2": t.colors[1] }}>
              <span className="team-flag"/>
              <span>{t.name}</span>
            </button>
          ))}
        </div>
      </div>

      <label className="row" style={{ gap: 8, fontSize: 12, color: "var(--fg-2)", alignItems: "flex-start" }}>
        <input type="checkbox" defaultChecked style={{ marginTop: 2 }}/>
        <span>Concordo com os <a className="link">Termos de uso</a> e <a className="link">Política de privacidade</a>. Entendo que posso receber emails sobre drops e ofertas.</span>
      </label>

      <button className="btn lg block" type="submit" disabled={loading}>
        {loading ? <><span className="spinner"/> Criando conta…</> : <>Criar conta <Icon name="arrow-right" size={16}/></>}
      </button>
    </form>
  );
}

function AuthStyles() {
  return (
    <style>{`
      .auth-main { min-height: 100vh; display: grid; }
      .auth-split { display: grid; grid-template-columns: 1.1fr 1fr; min-height: 100vh; }
      @media (max-width: 900px) { .auth-split { grid-template-columns: 1fr; } .auth-side { display: none !important; } }

      .auth-side {
        position: relative;
        background: var(--bg-1);
        padding: 32px 48px;
        display: flex; flex-direction: column;
        overflow: hidden;
        border-right: 1px solid var(--line);
      }
      .auth-brand { background: transparent; border: 0; color: inherit; align-self: start;
        display: inline-flex; align-items: baseline; gap: 6px;
        font-family: var(--font-display); font-weight: 700; font-size: 22px; letter-spacing: -0.04em; cursor: pointer;
      }
      .auth-side-bg {
        position: absolute; inset: 0; z-index: 0; pointer-events: none;
        background:
          radial-gradient(900px 600px at 80% 110%, var(--accent-glow), transparent 60%),
          radial-gradient(600px 400px at 20% 30%, color-mix(in oklab, var(--accent-2) 25%, transparent), transparent 60%);
      }
      .auth-side::before {
        content: ""; position: absolute; inset: 0; z-index: 0;
        background-image:
          linear-gradient(to right, var(--line) 1px, transparent 1px),
          linear-gradient(to bottom, var(--line) 1px, transparent 1px);
        background-size: 56px 56px;
        opacity: 0.5;
        mask-image: radial-gradient(ellipse at center, black 30%, transparent 75%);
      }
      .auth-side-content { position: relative; z-index: 1; margin-top: auto; max-width: 460px; display: flex; flex-direction: column; gap: 16px; }
      .auth-side-content h1 { margin: 8px 0 12px; font-size: clamp(40px, 5vw, 64px); line-height: 0.95; letter-spacing: -0.04em; }
      .auth-perks { list-style: none; padding: 0; margin: 8px 0 24px; display: flex; flex-direction: column; gap: 10px; color: var(--fg-2); }
      .auth-perks li { display: flex; align-items: center; gap: 10px; font-size: 14px; }
      .auth-perks svg { color: var(--accent); }
      .auth-stats { display: flex; gap: 24px; padding: 20px 0; border-top: 1px solid var(--line); }
      .auth-stats > div { display: flex; flex-direction: column; gap: 2px; }
      .auth-stats b { font-family: var(--font-display); font-size: 28px; font-weight: 700; letter-spacing: -0.03em; line-height: 1; }
      .auth-stats .small { color: var(--muted); }

      .auth-form-wrap {
        display: flex; flex-direction: column; justify-content: center;
        padding: 48px clamp(24px, 5vw, 72px);
        gap: 24px;
        max-width: 560px; width: 100%;
        margin: 0 auto;
      }

      .auth-tabs { position: relative; display: inline-flex; padding: 4px; background: var(--bg-2); border: 1px solid var(--line); border-radius: 999px; align-self: flex-start; }
      .auth-tabs button {
        position: relative; z-index: 1;
        padding: 10px 24px;
        background: transparent; border: 0;
        color: var(--muted); font-family: inherit; font-weight: 600; font-size: 14px;
        cursor: pointer; transition: color .2s;
      }
      .auth-tabs button.on { color: var(--accent-ink); }
      .auth-tab-indicator {
        position: absolute; top: 4px; left: 4px;
        width: calc(50% - 4px); height: calc(100% - 8px);
        background: var(--accent); border-radius: 999px;
        transition: transform .3s cubic-bezier(.2,.8,.2,1);
      }

      .auth-form { display: flex; flex-direction: column; gap: 16px; }
      .auth-head { display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; }
      .auth-head h2 { margin: 0; font-size: 32px; letter-spacing: -0.02em; }

      .auth-social { display: flex; gap: 12px; }
      @media (max-width: 600px) { .auth-social { flex-direction: column; } }
      .auth-social .social { flex: 1; gap: 8px; }
      .social-mark { width: 18px; height: 18px; border-radius: 50%; display: grid; place-items: center; font-family: var(--font-display); font-weight: 700; font-size: 12px; }
      .social-mark.g { background: white; color: black; }
      .social-mark.a { background: var(--fg); color: var(--bg-0); position: relative; }
      .social-mark.a::after { content: ""; width: 8px; height: 8px; background: var(--bg-0); border-radius: 50%; }

      .auth-divider { display: flex; align-items: center; gap: 12px; color: var(--muted); margin: 4px 0; }
      .auth-divider::before, .auth-divider::after { content: ""; flex: 1; height: 1px; background: var(--line); }

      .input-wrap { position: relative; }
      .input-eye { position: absolute; right: 12px; top: 50%; transform: translateY(-50%); background: transparent; border: 0; color: var(--muted); cursor: pointer; padding: 4px; }
      .input-eye:hover { color: var(--fg); }

      .pw-meter { display: flex; align-items: center; gap: 12px; margin-top: 8px; }
      .pw-bars { display: flex; gap: 4px; flex: 1; }
      .pw-bars span { flex: 1; height: 4px; background: var(--bg-3); border-radius: 2px; }
      .pw-bars span.on { background: var(--accent-2); }
      .pw-bars span.s3, .pw-bars span.s4 { background: var(--accent-3); }

      .team-picker { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
      @media (max-width: 600px) { .team-picker { grid-template-columns: 1fr; } }
      .team-chip {
        display: flex; align-items: center; gap: 10px;
        padding: 10px 14px;
        background: var(--surface); border: 1px solid var(--line);
        color: var(--fg-2); border-radius: var(--r-sm);
        font-family: inherit; font-size: 13px; cursor: pointer;
        text-align: left;
      }
      .team-chip.on { border-color: var(--accent); background: color-mix(in oklab, var(--accent) 6%, var(--surface)); color: var(--fg); }
      .team-flag {
        width: 16px; height: 20px;
        background: linear-gradient(135deg, var(--tc1) 50%, var(--tc2) 50%);
        border-radius: 2px;
        flex-shrink: 0;
      }

      .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%; animation: spin .7s linear infinite; }
      @keyframes spin { to { transform: rotate(360deg); } }

      .auth-footer { padding-top: 16px; border-top: 1px solid var(--line); color: var(--muted); text-align: center; }
    `}</style>
  );
}

window.STADIA_AUTH = Auth;
