# RED Trader Painel

Painel 24/7 de paper trading com feed da extensao IQ, saldo demo local e comite de IA via proxy RED Systems.

O MVP segue em modo simulado/browser-native:

- dados vivos da IQ via extensao Chrome + bridge;
- saldo paper local em SQLite;
- sem API comunitaria da IQ e sem ordem real fora do navegador demo;
- IA so e chamada quando o motor tecnico encontra candidato;
- dashboard protegido por senha;
- perfis de risco ajustaveis: conservador, balanceado, agressivo e full agressivo;
- painel de plataformas: IQ via extensao como feed/execucao demo, mais tastytrade Sandbox e Webull Paper como trilhos futuros;
- feed vivo da extensao IQ Option via bridge, refletido no painel em tempo real.

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

Na VM publica da RED, o nginx tambem expoe o painel por caminho amigavel:

```text
http://redsystems.ddns.net/trader/
```

## Variaveis

Copie `.env.example` para `.env` se quiser customizar. Por padrao:

- Porta: `3100`
- Senha: `change-me` apenas para desenvolvimento local
- Proxy IA: `http://redsystems.ddns.net:8080`
- Banco: `./data/redtrader.sqlite`
- Bridge IQ local: `http://127.0.0.1:3115`

Adapters de plataforma:

- `BINANCE_BASE_URL`: market data Spot em tempo real.
- `TASTYTRADE_USERNAME` / `TASTYTRADE_PASSWORD`: habilitam a proxima etapa do adapter Sandbox.
- `WEBULL_APP_KEY` / `WEBULL_APP_SECRET`: habilitam a proxima etapa do adapter Paper/OpenAPI.
- `REDTRADER_IQ_BRIDGE_URL`: endpoint HTTP local do bridge da extensao IQ.
- `REDTRADER_IQ_BRIDGE_TOKEN`: token opcional do bridge.
- `REDTRADER_IQ_BRIDGE_SESSION_ID`: fixa uma sessao da extensao; se vazio, o Trader escolhe a melhor telemetria recente.
- `REDTRADER_IQ_BRIDGE_POLL_MS`: intervalo de sincronizacao do feed da extensao.

## Fluxo

```text
market data -> strategy gates -> fast filter -> final decision -> critic veto -> paper trade
```

Fluxo da extensao IQ no Trader:

```text
RED IQ Demo Vision -> iq-bridge -> runtime do Trader -> websocket /ws -> painel
```

O runtime do Trader agora:

- busca o estado vivo da extensao pelo bridge;
- escolhe automaticamente a melhor sessao recente quando houver mais de uma;
- replica esse estado no painel em tempo real;
- enfileira comandos para a extensao pelo mesmo bridge;
- monta snapshots e executa ordens binarias usando apenas a extensao/bridge, sem depender da API comunitaria antiga.

## Perfis de risco

- `Conservador`: menos entradas, posicao menor, score/confianca mais altos.
- `Balanceado`: padrao inicial do MVP.
- `Agressivo`: mais oportunidades em paper, com limites maiores.
- `Full agressivo`: experimental, aceita setups mais arriscados, mas ainda sem alavancagem e sem ordem real.

Regras iniciais do modo balanceado:

- Spot only, sem alavancagem.
- Pares tradaveis: `BTCUSDT`, `ETHUSDT`.
- `SOLUSDT` fica em observacao.
- Cooldown padrao: 30 minutos.
- Maximo: 3 trades por dia.
- Stop diario: -5%.
- Meta diaria: +3%.
