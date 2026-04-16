# Servicos

Codigo dos servicos vivos, experimentais ou legados ainda uteis da RED Systems.

```text
portal/            Home publica da stack
dashboard/         Painel principal da VM unica
proxy/             Proxy IA oficial
  proxy-lab/         Laboratorio de benchmark pago
  redia/             Runtime da RED I.A
  redtrader/         Trader demo/paper
  openclaw/          Assistente operacional privado
  extensao-iq-demo/  Extensao Chrome e IQ Bridge
  extensao-iq-motor-lab/ Motor secundario de experimentacao remota na IQ
  deploy-agent/      Legado
```

## Observacoes importantes

- `dashboard/` e o centro operacional da VM unica.
- `redia/` continua existindo como runtime proprio, mas tambem foi portada para dentro do dashboard principal na rota `/dashboard/redia`.
- `proxy-lab/` e laboratorio; nao trate como producao.
- `openclaw/` e assistente operacional privado da stack, exposto por `/openclaw/`.
- `extensao-iq-motor-lab/` existe para iteracao rapida por JSON remoto; use para testar comportamento antes de portar para a extensao principal.
- `deploy-agent/` e legado; so mexa se houver motivo real.

Cada servico deve manter:

- `.env.example`
- dependencias declaradas
- README quando o contexto operacional exigir

Dados runtime devem ficar em `data/` ou nos caminhos de runtime da VM e **nao** devem ir para Git.
