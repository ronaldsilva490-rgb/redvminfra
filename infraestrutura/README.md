# Infraestrutura

Infra da arquitetura atual de **VM unica** da RED Systems.

```text
systemd/  Units oficiais dos servicos.
nginx/    Friendly paths e reverse proxy.
docker/   Artefatos auxiliares/legados.
scripts/  Instalacao, sync e apoio operacional.
shell/    Helpers shell (red-root e afins).
```

Antes de aplicar qualquer unit ou config em uma VM:

1. valide caminhos, usuario, portas e env;
2. faca backup remoto;
3. valide sintaxe;
4. reinicie so o servico tocado.

## Atalhos publicos

Na VM principal, `infraestrutura/nginx/red-friendly-paths.nginx.conf` e publicado no include ativo `/etc/nginx/redvm-routes/red-enabled-paths.conf`. A copia `/etc/nginx/snippets/red-friendly-paths.nginx.conf` e mantida como espelho. Ele expoe:

```text
/             Portal
/portal-assets/ Assets do portal
/modelo1/     Landing estatica modelo 1
/modelo2/     Landing estatica modelo 2
/teste/       Site estatico de teste esports
/dashboard/   Dashboard principal
/proxy/       Proxy IA oficial
/redproxypro/ Proxy Vercel AI Gateway com rotacao de keys
/redclaudeproxy/ Ponte Claude para os modelos do proxy normal
/ollama/      Alias do proxy oficial
/search/      Busca web gratuita via SearXNG
/msredpdf/    Analise juridica de PDF/DOCX com IA
/redia/       Runtime da RED I.A
/trader/      RED Trader
/proxy-lab/   Proxy Lab
/iq-bridge/   IQ Bridge
/openclaw/    OpenClaw
/rapidleech/  Rapidleech
/redsebia/    Portal e backend do novo REDSEBIA
/redseb/      SEB Monitor via nginx
/download/    Downloads auxiliares do SEB Monitor
:2580         RED SEB Monitor
```

## Units ativas na VM principal em 2026-05-10

```text
red-dashboard.service
red-ollama-proxy.service
redproxypro.service
redclaudeproxy.service
rednimclaude.service
redlightningclaude.service
redalibabaclaude.service
red-searxng.service
modelos-counter.service
msredpdf.service
rapidleech.service
redia.service
red-sebia.service
red-seb-monitor.service
red-proxy-lab.service
```

Units versionadas no repo, mas **removidas da VM** (sem unit systemd nem runtime):

```text
red-openclaw.service
redtrader.service
red-iq-vision-bridge.service
red-webhook.service
red-seb-webhook.service
```

## Dashboard com subrotas

O dashboard principal tambem responde por caminho real:

```text
/dashboard/
/dashboard/servicos
/dashboard/docker
/dashboard/proxyia
/dashboard/redia
/dashboard/projetos
/dashboard/logs
/dashboard/terminal
/dashboard/arquivos
/dashboard/firewall
/dashboard/processos
```

## Legado

- Evolution nao e mais parte central da stack.
- Artefatos legados em `docker/` ou `systemd/` devem ser tratados como compatibilidade, nao como eixo da arquitetura.
- `rapidleech.service` agora e parte oficial da stack e deve ser publicado pelo nginx em `/rapidleech/`.
- `red-sebia.service` agora e parte oficial da stack e deve ser publicado pelo nginx em `/redsebia/`.
- `red-seb-monitor.service` e parte oficial da stack, mas hoje vive em porta dedicada `2580`, fora do nginx principal.
- `msredpdf.service`, `redproxypro.service`, `redclaudeproxy.service` e `red-searxng.service` fazem parte do conjunto essencial atual.
- `openclaw`, `redtrader` e `iq-bridge` ficam no repo para reativacao futura, mas nao devem ser tratados como essenciais na VM principal atual.
