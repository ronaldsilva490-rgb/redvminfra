# RED Trader Painel

Painel 24/7 de paper trading com dados reais de mercado, saldo demo local e comitê de IA via proxy RED Systems.

O MVP começa em modo simulado:

- Dados reais da Binance Spot.
- Saldo paper local em SQLite.
- Sem chaves de corretora e sem ordens reais.
- IA só é chamada quando o motor técnico encontra candidato.
- Dashboard protegido por senha.
- Perfis de risco ajustáveis: conservador, balanceado, agressivo e full agressivo.

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

Na VM pública da RED, o Nginx também pode expor o painel por caminho amigável:

```text
http://redsystems.ddns.net/trader/
```

## Variáveis

Copie `.env.example` para `.env` se quiser customizar. Por padrão:

- Porta: `3100`
- Senha: `change-me` apenas para desenvolvimento local
- Proxy IA: `http://redsystems.ddns.net:8080`
- Banco: `./data/redtrader.sqlite`

## Fluxo

```text
market data -> strategy gates -> fast filter -> final decision -> critic veto -> paper trade
```

Perfis de risco:

- `Conservador`: menos entradas, posição menor, score/confiança mais altos.
- `Balanceado`: padrão inicial do MVP.
- `Agressivo`: mais oportunidades em paper, com limites maiores.
- `Full agressivo`: experimental, aceita setups mais arriscados, mas ainda sem alavancagem e sem ordem real.

Regras iniciais do modo balanceado:

- Spot only, sem alavancagem.
- Pares tradáveis: `BTCUSDT`, `ETHUSDT`.
- `SOLUSDT` fica em observação.
- Cooldown padrão: 30 minutos.
- Máximo: 3 trades por dia.
- Stop diário: -5%.
- Meta diária: +3%.
