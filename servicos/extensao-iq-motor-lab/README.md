# RED IQ Motor Lab

Extensao secundaria, separada da principal, para testar comportamento remoto na IQ demo sem precisar recarregar a extensao operacional a cada tentativa.

## Ideia

- a extensao principal continua como fonte estavel de leitura e operacao
- esta extensao `motor-lab` puxa um JSON do bridge
- o JSON define acoes de laboratorio em tempo real
- quando um comportamento se provar bom, ele e portado para a extensao principal

## Dependencias

- Chrome ou Chromium com suporte a Manifest V3
- bridge da extensao principal acessivel em `/iq-bridge/`

## Fluxo

1. O content script busca a config viva em `/iq-bridge/api/motor/config/current?channel=spy`.
2. O worker continua servindo como relay e telemetria, mas a aplicacao da config nao depende mais so do broadcast dele.
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

## Instalacao em qualquer VM e navegador

O `motor-lab` nao precisa de um backend proprio. Ele depende do mesmo bridge da extensao principal.

1. Instale o bridge principal da IQ na VM.
2. No navegador, abra `chrome://extensions`.
3. Ative `Modo do desenvolvedor`.
4. Clique em `Carregar sem compactacao`.
5. Selecione `servicos/extensao-iq-motor-lab`.

## Validacao recomendada

- confirmar no bridge que a extensao aparece com sessao nova
- aplicar uma config simples por `PUT /iq-bridge/api/motor/config/current`
- verificar `report_state` e `config_applied`

## Observacoes

- O `motor-lab` existe para testar comportamento antes de portar para a principal.
- Se algo ainda estiver pedindo reload constante, a direcao certa e melhorar o motor remoto, nao a principal.
