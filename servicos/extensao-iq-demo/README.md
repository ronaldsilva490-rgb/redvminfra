# RED IQ Demo Vision

Extensao Chrome Manifest V3 para acompanhar a IQ Option demo em tempo real, com foco em leitura do transporte da pagina, overlay operacional e automacao controlada em conta demo.

## Estado atual

Hoje a extensao ja faz:

- captura de `WebSocket`, `fetch`, `XHR` e eventos derivados da pagina;
- resolucao de ativo por `active_id`, com dicionario alimentado pelo proprio fluxo da IQ;
- leitura de ativo atual, mercado, preco, payout, hints de countdown e portfolio;
- overlay com sparkline e diagnosticos;
- envio de snapshots e logs brutos para a VM;
- canal remoto bridge -> extensao para inspecao, clique assistido e tentativa de trade.

## Limites atuais

Ainda estamos refinando:

- sincronismo fino de payout em mudancas rapidas de ativo;
- resolucao perfeita entre par normal e OTC em todos os casos;
- confirmacao de ordem nativa sem falso positivo;
- fallback visual sem risco de missclick.

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

Quando o objetivo for iterar comportamento muito rapido, sem rebuild constante da extensao principal, use a extensao separada:

- `servicos/extensao-iq-motor-lab`

Ela puxa um JSON vivo do bridge por canal (`spy` por padrao) e executa acoes de laboratorio. O fluxo certo e:

1. validar a ideia no `motor-lab`;
2. observar resultado no bridge;
3. portar so o que prestou para `extensao-iq-demo`.

## Bridge para a VM

O projeto ja vem com um bridge HTTP em `bridge/`.

Ele recebe snapshots, logs e comandos, salvando tudo em SQLite para comparar:

- o que a extensao viu;
- quando viu;
- qual era o ativo;
- o que a IQ respondeu ao socket;
- o que apareceu no portfolio;
- se a ordem foi enviada, recusada ou confirmada.

## Como carregar no Chrome

1. Abra `chrome://extensions`
2. Ative `Modo do desenvolvedor`
3. Clique em `Carregar sem compactacao`
4. Selecione a pasta `servicos/extensao-iq-demo`

## Fluxo esperado

1. Abrir a IQ Option logada na demo.
2. A extensao injeta o overlay e comeca a escutar o transporte.
3. O worker envia o estado para o bridge.
4. A VM pode inspecionar o estado vivo, disparar comandos remotos e comparar snapshots com o portfolio.

## Progresso recente

- `v0.1.18+`: primeiros comandos de trade e controle de superficie.
- `v0.1.20+`: prioridade para caminho nativo da IQ antes de fallback visual.
- `v0.1.23+`: confirmacao de trade exige evidencia real no portfolio.
- `v0.1.24+`: captura de `user_balance_id` para abrir ordem nativa.
- `v0.1.25`: ajuste automatico de payout quando a IQ rejeita por mudanca de lucro (`status 4117`).
