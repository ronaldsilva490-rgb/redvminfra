# Servicos

Codigo dos servicos vivos, experimentais ou legados ainda uteis da RED Systems.

## Mapa rapido

```text
portal/                 Home publica da stack
dashboard/              Painel principal da VM unica
proxy/                  Proxy IA oficial
redproxypro/            Proxy Vercel AI Gateway com rotacao de keys
redclaudeproxy/         Ponte Claude para modelos do proxy normal
rednimclaude/           Gateway direto para NVIDIA NIM (porta 5050)
redlightningclaude/     Gateway direto para Lightning AI (porta 5051)
redalibabaclaude/       Gateway direto para Alibaba DashScope (porta 5052)
msredpdf/               Analise juridica de PDFs com IA
searxng/                Busca web gratuita para OpenClaude
proxy-lab/              Laboratorio de benchmark pago
redia/                  Runtime da RED I.A
redtrader/              Trader demo/paper
openclaw/               Assistente operacional privado
rapidleech/             Transfer hub legado oficializado
redseb-monitor/         Painel remoto do ecossistema SEB
redsebia/               Novo portal, wallet e runtime do produto REDSEBIA
extensao-iq-demo/       Extensao Chrome e IQ Bridge
extensao-iq-motor-lab/  Motor secundario de experimentacao remota na IQ
modelos-counter/        Contador de uso de modelos (servico interno)
deploy-agent/           Legado
```

## Guias por servico

- [portal/README.md](portal/README.md)
- [dashboard/README.md](dashboard/README.md)
- [proxy/README.md](proxy/README.md)
- [redproxypro/README.md](redproxypro/README.md)
- [redclaudeproxy/README.md](redclaudeproxy/README.md)
- [rednimclaude/README.md](rednimclaude/README.md)
- [redlightningclaude/README.md](redlightningclaude/README.md)
- [redalibabaclaude/README.md](redalibabaclaude/README.md)
- [msredpdf/README.md](msredpdf/README.md)
- [searxng/README.md](searxng/README.md)
- [proxy-lab/README.md](proxy-lab/README.md)
- [redia/README.md](redia/README.md)
- [redtrader/README.md](redtrader/README.md)
- [openclaw/README.md](openclaw/README.md)
- [rapidleech/README.md](rapidleech/README.md)
- [redseb-monitor/README.md](redseb-monitor/README.md)
- [redsebia/README.md](redsebia/README.md)
- [extensao-iq-demo/README.md](extensao-iq-demo/README.md)
- [extensao-iq-motor-lab/README.md](extensao-iq-motor-lab/README.md)
- [modelos-counter/server.py](modelos-counter/server.py) _(servico interno, sem README dedicado)_
- [deploy-agent/README.md](deploy-agent/README.md)

## Regras operacionais

- `dashboard/` e o centro operacional da VM unica.
- `redia/` continua existindo como runtime proprio, mas o caminho principal de operacao e `/dashboard/redia`.
- `proxy-lab/` e laboratorio; nao trate como producao.
- `redproxypro/` e o proxy dedicado ao Vercel AI Gateway; keys reais vivem em `/etc/redproxypro.env`, nunca no repo.
- `redclaudeproxy/` e a ponte dedicada do Claude Desktop/Code para os modelos do proxy normal; usa `/etc/redclaudeproxy.env`.
- `rednimclaude/` e o gateway direto para NVIDIA NIM em porta propria (5050); TLS proprio, auth `red`.
- `redlightningclaude/` e o gateway direto para Lightning AI em porta propria (5051); TLS proprio, auth `red`.
- `redalibabaclaude/` e o gateway direto para Alibaba DashScope multi-regiao em porta propria (5052); TLS proprio, auth `red`.
- `msredpdf/` e o backend de analise juridica de PDF, publicado em `/msredpdf/` e integrado ao proxy IA oficial.
- `searxng/` e o backend de busca web gratuita usado pelo OpenClaude via provedor custom.
- `rapidleech/` virou parte oficial da stack e deve ser tratado como runtime publicado por `/rapidleech/`, nao como pasta solta fora do repo.
- `redseb-monitor/` e o painel remoto oficial do ecossistema RED SEB / Safe Exam Browser, hoje exposto em `:2580`.
- `redsebia/` e o backend independente do novo produto REDSEBIA, com portal do cliente, admin, wallet, PIX e runtime API.
- `openclaw/`, `redtrader/`, `extensao-iq-demo/bridge`, `deploy-agent/` e o webhook WhatsApp do SEB continuam versionados, mas foram **removidos da VM principal** em 2026-05-10 (sem unit systemd nem runtime em `/opt/`).
- `extensao-iq-motor-lab/` existe para iteracao rapida por JSON remoto antes de tocar a extensao principal.
- `deploy-agent/` e legado; so mexa se houver motivo real.

## Estado da VM principal em 2026-05-10

Ativos:

```text
portal, dashboard, proxy, redproxypro, redclaudeproxy, rednimclaude,
redlightningclaude, redalibabaclaude, searxng, msredpdf, rapidleech, redia,
redsebia, red-seb-monitor, proxy-lab, modelos-counter
```

Inativos por decisao operacional, removidos da VM mas versionados no repo:

```text
openclaw, redtrader, iq-bridge, deploy-agent, red-seb-webhook
```

Snapshot completo: [../documentacao/estado-atual-vm-2026-05-10.md](../documentacao/estado-atual-vm-2026-05-10.md)

## Padrao esperado para cada servico

Cada servico operacional deve manter:

- `README.md` com instalacao em qualquer VM
- dependencias declaradas
- `.env.example` quando houver configuracao por ambiente

Dados de runtime devem ficar em `data/` ou nos caminhos oficiais da VM e nao devem ir para Git.
