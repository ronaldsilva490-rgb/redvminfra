# Servicos

Codigo dos servicos vivos, experimentais ou legados ainda uteis da RED Systems.

```text
portal/            Home publica da stack
dashboard/         Painel principal da VM unica
proxy/             Proxy IA oficial
proxy-lab/         Laboratorio de benchmark pago
redia/             Runtime da RED I.A
redtrader/         Trader demo/paper
extensao-iq-demo/  Extensao Chrome e IQ Bridge
deploy-agent/      Legado
```

## Observacoes importantes

- `dashboard/` e o centro operacional da VM unica.
- `redia/` continua existindo como runtime proprio, mas tambem foi portada para dentro do dashboard principal na rota `/dashboard/redia`.
- `proxy-lab/` e laboratorio; nao trate como producao.
- `deploy-agent/` e legado; so mexa se houver motivo real.

Cada servico deve manter:

- `.env.example`
- dependencias declaradas
- README quando o contexto operacional exigir

Dados runtime devem ficar em `data/` ou nos caminhos de runtime da VM e **nao** devem ir para Git.
