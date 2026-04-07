# RED Trader Painel

Painel 24/7 de paper trading com dados reais de mercado, saldo demo local e comite de IA via proxy RED Systems.

O MVP comeca em modo simulado:

- Dados reais da Binance Spot.
- Saldo paper local em SQLite.
- Sem chaves de corretora e sem ordens reais.
- IA so e chamada quando o motor tecnico encontra candidato.
- Dashboard protegido por senha.

## Rodar local

```powershell
cd servicos/redtrader
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
$env:REDTRADER_PASSWORD="change-me"
$env:REDTRADER_SECRET="change-me-too"
$env:PYTHONPATH="src"
python -m redtrader.app
```

Abra `http://localhost:3100` e use a senha definida em `REDTRADER_PASSWORD`.

## Variaveis

Copie `.env.example` para `.env` se quiser customizar. Por padrao:

- Porta: `3100`
- Senha: `change-me` apenas para desenvolvimento local
- Proxy IA: `http://redsystems.ddns.net:8080`
- Banco: `./data/redtrader.sqlite`

## Fluxo

```text
market data -> strategy gates -> fast filter -> final decision -> critic veto -> paper trade
```

Regras iniciais:

- Spot only, sem alavancagem.
- Pares tradaveis: `BTCUSDT`, `ETHUSDT`.
- `SOLUSDT` fica em observacao.
- Cooldown padrao: 30 minutos.
- Maximo: 3 trades por dia.
- Stop diario: -5%.
- Meta diaria: +3%.
