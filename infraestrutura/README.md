# Infraestrutura

Infra da arquitetura atual de **VM unica** da RED Systems.

```text
systemd/  Units oficiais dos servicos.
nginx/    Friendly paths e reverse proxy.
docker/   Artefatos auxiliares/legados.
scripts/  Instalacao, sync e apoio operacional.
```

Antes de aplicar qualquer unit ou config em uma VM:

1. valide caminhos, usuario, portas e env;
2. faca backup remoto;
3. valide sintaxe;
4. reinicie so o servico tocado.

## Atalhos publicos

Na VM principal, `infraestrutura/nginx/red-friendly-paths.nginx.conf` expoe:

```text
/             Portal
/dashboard/   Dashboard principal
/proxy/       Proxy IA oficial
/ollama/      Alias do proxy oficial
/redia/       Runtime da RED I.A
/trader/      RED Trader
/proxy-lab/   Proxy Lab
/iq-bridge/   IQ Bridge
/openclaw/    OpenClaw
/rapidleech/  Rapidleech
:2580         RED SEB Monitor
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
- `red-seb-monitor.service` e parte oficial da stack, mas hoje vive em porta dedicada `2580`, fora do nginx principal.
