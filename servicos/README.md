# Servicos

Codigo dos servicos vivos, experimentais ou legados ainda uteis da RED Systems.

## Mapa rapido

```text
portal/                 Home publica da stack
dashboard/              Painel principal da VM unica
proxy/                  Proxy IA oficial
proxy-lab/              Laboratorio de benchmark pago
redia/                  Runtime da RED I.A
redtrader/              Trader demo/paper
openclaw/               Assistente operacional privado
rapidleech/             Transfer hub legado oficializado
redseb-monitor/         Painel remoto do ecossistema SEB
extensao-iq-demo/       Extensao Chrome e IQ Bridge
extensao-iq-motor-lab/  Motor secundario de experimentacao remota na IQ
deploy-agent/           Legado
```

## Guias por servico

- [portal/README.md](portal/README.md)
- [dashboard/README.md](dashboard/README.md)
- [proxy/README.md](proxy/README.md)
- [proxy-lab/README.md](proxy-lab/README.md)
- [redia/README.md](redia/README.md)
- [redtrader/README.md](redtrader/README.md)
- [openclaw/README.md](openclaw/README.md)
- [rapidleech/README.md](rapidleech/README.md)
- [redseb-monitor/README.md](redseb-monitor/README.md)
- [extensao-iq-demo/README.md](extensao-iq-demo/README.md)
- [extensao-iq-motor-lab/README.md](extensao-iq-motor-lab/README.md)
- [deploy-agent/README.md](deploy-agent/README.md)

## Regras operacionais

- `dashboard/` e o centro operacional da VM unica.
- `redia/` continua existindo como runtime proprio, mas o caminho principal de operacao e `/dashboard/redia`.
- `proxy-lab/` e laboratorio; nao trate como producao.
- `openclaw/` e assistente operacional privado da stack, exposto por `/openclaw/`.
- `rapidleech/` virou parte oficial da stack e deve ser tratado como runtime publicado por `/rapidleech/`, nao como pasta solta fora do repo.
- `redseb-monitor/` e o painel remoto oficial do ecossistema RED SEB / Safe Exam Browser, hoje exposto em `:2580`.
- `extensao-iq-motor-lab/` existe para iteracao rapida por JSON remoto antes de tocar a extensao principal.
- `deploy-agent/` e legado; so mexa se houver motivo real.

## Padrao esperado para cada servico

Cada servico operacional deve manter:

- `README.md` com instalacao em qualquer VM
- dependencias declaradas
- `.env.example` quando houver configuracao por ambiente

Dados de runtime devem ficar em `data/` ou nos caminhos oficiais da VM e nao devem ir para Git.
