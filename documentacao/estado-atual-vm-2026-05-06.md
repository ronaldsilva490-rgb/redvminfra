# Estado Atual Da VM RED - 2026-05-06

Levantamento operacional feito em `redsystems.ddns.net` em 2026-05-06. Este arquivo nao contem segredos.

## Host

```text
hostname: red
ssh: redsystems.ddns.net:22
http/https: nginx em 80 e 443
```

## Servicos ativos

```text
red-dashboard.service       active   /opt/redvm-dashboard      127.0.0.1:9001
red-ollama-proxy.service    active   /opt/redvm-proxy          127.0.0.1:8080
redproxypro.service         active   /opt/redproxypro          127.0.0.1:8095
redclaudeproxy.service      active   /opt/redclaudeproxy       127.0.0.1:8096
red-searxng.service         active   /opt/red-searxng          127.0.0.1:8088
msredpdf.service            active   /opt/msredpdf             127.0.0.1:3142
rapidleech.service          active   /opt/rapidleech           127.0.0.1:2581
redia.service               active   /opt/redia                127.0.0.1:3099
red-sebia.service           active   /opt/redsebia             127.0.0.1:3130
red-seb-monitor.service     active   /opt/red-seb-monitor      0.0.0.0:2580
red-proxy-lab.service       active   /opt/red-proxy-lab        127.0.0.1:8090
```

## Servicos mantidos no repo, mas inativos nesta VM

```text
red-openclaw.service
redtrader.service
red-iq-vision-bridge.service
```

Eles continuam versionados para compatibilidade e reinstalacao futura, mas nao entram no conjunto essencial ativo desta VM.

## Rotas publicas principais

```text
/                         portal
/portal-assets/            assets do portal
/modelo1/                  landing estatica modelo 1
/modelo2/                  landing estatica modelo 2
/dashboard/                dashboard principal
/hooks/                    webhooks do dashboard/deploy
/proxy/                    proxy IA oficial
/ollama/                   alias do proxy IA oficial
/redproxypro/              RED Proxy Pro / Vercel AI Gateway
/redclaudeproxy/           ponte Claude para modelos do proxy normal
/search/                   SearXNG
/msredpdf/                 analise juridica de PDF/DOCX
/redia/                    RED I.A
/redsebia/                 REDSEBIA
/redseb/                   SEB Monitor via nginx
/download/                 downloads auxiliares do SEB Monitor
/rapidleech/               Rapidleech
/proxy-lab/                laboratorio de proxy
```

## Rotas/portas dedicadas

```text
:2580                      RED SEB Monitor direto
```

## RED Proxy Pro

Runtime:

```text
/opt/redproxypro
/etc/redproxypro.env
/var/lib/redproxypro/usage.json
```

Modelos publicados em `/redproxypro/v1/models`, em ordem alfabetica:

```text
alibaba/qwen-3.6-max-preview
alibaba/qwen3.5-flash
alibaba/qwen3.5-plus
alibaba/qwen3.6-27b
anthropic/claude-sonnet-4.5
anthropic/claude-sonnet-4.6
deepseek/deepseek-v4-pro
google/gemini-3.1-pro-preview
moonshotai/kimi-k2.5
moonshotai/kimi-k2.6
openai/gpt-5.4-pro
openai/gpt-5.5
openai/gpt-5.5-pro
xai/grok-4.20-multi-agent
xai/grok-4.20-reasoning
xai/grok-4.3
xiaomi/mimo-v2.5
xiaomi/mimo-v2.5-pro
zai/glm-5.1
```

Aliases antigos ainda aceitos:

```text
claude-red-gpt-55    -> openai/gpt-5.5
claude-red-sonnet-46 -> anthropic/claude-sonnet-4.6
claude-red-kimi-k26  -> moonshotai/kimi-k2.6
claude-red-glm-51    -> zai/glm-5.1
```

## RED Claude Proxy

Runtime:

```text
/opt/redclaudeproxy
/etc/redclaudeproxy.env
/var/lib/redclaudeproxy/usage.json
```

Funcao:

```text
Claude Desktop/Code -> /redclaudeproxy -> proxy normal em 127.0.0.1:8080/v1
```

Estado validado em 2026-05-06:

```text
servico: active
modelos publicados: 23
catalogo: /redclaudeproxy/v1/models
upstream: http://127.0.0.1:8080/v1
```

Validacoes feitas:

```text
chat sem streaming: OK
streaming Anthropic SSE: OK
tool_use forcado: OK
count_tokens: OK
HTTP e HTTPS publicos: OK
```

## Validacoes recomendadas

```bash
systemctl --failed
systemctl status redproxypro --no-pager
systemctl status redclaudeproxy --no-pager
systemctl status msredpdf --no-pager
systemctl status rapidleech --no-pager
nginx -t
curl -sS http://127.0.0.1:8095/v1/models -H 'Authorization: Bearer red'
curl -sS http://127.0.0.1:8096/v1/models -H 'Authorization: Bearer red'
curl -sS http://127.0.0.1:3142/healthz
curl -I http://127.0.0.1:2581/
```

## Regra de manutencao

Quando alterar a VM, atualizar no mesmo ciclo:

- `README.md`
- `servicos/README.md`
- `infraestrutura/README.md`
- README do servico tocado
- unit systemd correspondente, se houver
- `infraestrutura/nginx/red-friendly-paths.nginx.conf`, se a rota mudar
