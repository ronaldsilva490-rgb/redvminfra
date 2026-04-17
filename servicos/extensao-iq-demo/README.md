# RED IQ Demo Vision

Extensao Chrome Manifest V3 para acompanhar a IQ Option demo em tempo real, com foco em leitura do transporte da pagina, overlay operacional e automacao controlada em conta demo.

## Estado atual

Hoje a extensao ja faz:

- captura de `WebSocket`, `fetch`, `XHR` e eventos derivados da pagina
- resolucao de ativo por `active_id`, com dicionario alimentado pelo proprio fluxo da IQ
- leitura de ativo atual, mercado, preco, payout, hints de countdown e portfolio
- overlay com sparkline e diagnosticos
- envio de snapshots e logs para a VM
- canal remoto bridge -> extensao para inspecao, clique assistido e tentativa de trade

## Dependencias

No navegador:

- Google Chrome ou Chromium com suporte a Manifest V3

No lado da VM:

- Python 3.11+
- `python3-venv`
- acesso HTTP ao bridge

## Fluxo tecnico

1. `injected-bridge.js` intercepta APIs da pagina no `MAIN world`.
2. `content.js` monta o estado vivo, o overlay e a runtime local.
3. `background.js` publica logs do worker e manda lotes para o bridge.
4. O bridge na VM salva telemetria, logs, comandos e resultados.

## Estrutura

```text
servicos/extensao-iq-demo/
  manifest.json
  README.md
  src/
    background.js
    content.js
    injected-bridge.js
    overlay.css
    popup.html
    popup.js
  bridge/
    app.py
    README.md
  tools/
    bridge_inspect.py
    bridge_remote.py
    motor_config.py
```

## Motor Lab secundario

Quando o objetivo for iterar comportamento muito rapido, sem rebuild constante da extensao principal, use a extensao separada `servicos/extensao-iq-motor-lab`.

## Instalacao em qualquer VM

### 1. Bridge

```bash
mkdir -p /opt/red-iq-vision-bridge
rsync -a servicos/extensao-iq-demo/bridge/ /opt/red-iq-vision-bridge/
python3 -m venv /opt/red-iq-vision-bridge/.venv
/opt/red-iq-vision-bridge/.venv/bin/pip install -r /opt/red-iq-vision-bridge/requirements.txt
cp /opt/red-iq-vision-bridge/.env.example /etc/red-iq-vision-bridge.env
cp infraestrutura/systemd/red-iq-vision-bridge.service /etc/systemd/system/red-iq-vision-bridge.service
systemctl daemon-reload
systemctl enable --now red-iq-vision-bridge
```

Exponha `/iq-bridge/` pelo nginx se a extensao for falar com o host por rota publica.

### 2. Extensao

1. Abra `chrome://extensions`
2. Ative `Modo do desenvolvedor`
3. Clique em `Carregar sem compactacao`
4. Selecione `servicos/extensao-iq-demo`
5. Abra a IQ demo no navegador

## Validacao recomendada

Bridge:

```bash
python3 -m py_compile /opt/red-iq-vision-bridge/app.py
systemctl is-active red-iq-vision-bridge
curl http://127.0.0.1:3115/healthz
```

Navegador:

- confirmar que o overlay aparece
- confirmar que snapshots e logs chegam ao bridge
- testar pelo menos um comando remoto controlado

## Runtime oficial na RED

- bridge: `/opt/red-iq-vision-bridge`
- data: `/opt/red-iq-vision-bridge/data`
- env: `/etc/red-iq-vision-bridge.env`
- service: `red-iq-vision-bridge.service`
- publicacao: `/iq-bridge/`

## Observacoes

- Trate transporte e portfolio como fonte principal de verdade.
- OCR e DOM superficial sao apoio, nao base operacional.
