# RED IQ Motor Lab

Extensao secundaria, separada da principal, para testar comportamento remoto na IQ demo sem precisar recarregar a extensao operacional a cada tentativa.

## Ideia

- a extensao principal continua como fonte estavel de leitura/operacao;
- esta extensao `motor-lab` puxa um JSON do bridge;
- o JSON define acoes de laboratorio em tempo real;
- quando um comportamento se provar bom, ele e portado para a extensao principal.

## Fluxo

1. O content script busca a config viva em `/iq-bridge/api/motor/config/current?channel=spy`.
2. O worker continua servindo como relay/telemetria, mas a aplicacao da config nao depende mais do broadcast dele.
3. O content script executa as acoes e reporta o resultado de volta.

## Acoes suportadas hoje

- `report_state`
- `elements_at_point`
- `click_point`
- `click_selector`
- `click_text`
- `eval_js`
- `sleep`

## Exemplo de config

```json
{
  "enabled": true,
  "pollMs": 1000,
  "reportState": true,
  "stateIntervalMs": 1500,
  "actions": [
    { "id": "probe-right", "type": "elements_at_point", "x": 820, "y": 380 },
    { "id": "js-check", "type": "eval_js", "code": "location.href" }
  ]
}
```

## Carregar no Chrome

1. `chrome://extensions`
2. `Modo do desenvolvedor`
3. `Carregar sem compactacao`
4. selecione `servicos/extensao-iq-motor-lab`

## Ponte com o bridge

O bridge da extensao principal ganhou dois endpoints:

- `GET /iq-bridge/api/motor/config/current`
- `PUT /iq-bridge/api/motor/config/current`

Isso permite alterar comportamento em tempo real sem rebuild da extensao principal.
