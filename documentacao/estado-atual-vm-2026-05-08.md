# Estado Atual Da VM RED - 2026-05-08

Levantamento operacional feito em `redsystems.ddns.net` em 2026-05-08. Este arquivo nao contem segredos.

## Host

```text
hostname: red
ssh: redsystems.ddns.net:22
http/https: nginx em 80 e 443
uptime observado: 3 dias, 2 horas
disco raiz: 328G total, 17G usado, 297G livre, 6% em uso
memoria: 15Gi total, 1.8Gi usado, 13Gi disponivel
swap: 8Gi total, 0B usado
```

## Servicos ativos

```text
red-dashboard.service         active   /opt/redvm-dashboard      127.0.0.1:9001
red-ollama-proxy.service      active   /opt/redvm-proxy          127.0.0.1:8080
redproxypro.service           active   /opt/redproxypro          127.0.0.1:8095
redclaudeproxy.service        active   /opt/redclaudeproxy       127.0.0.1:8096
rednimclaude.service          active   /opt/rednimclaude         0.0.0.0:5050
redlightningclaude.service    active   /opt/redlightningclaude   0.0.0.0:5051
redalibabaclaude.service      active   /opt/redalibabaclaude     0.0.0.0:5052
red-searxng.service           active   /opt/red-searxng          127.0.0.1:8088
modelos-counter.service       active   /opt/modelos-counter      127.0.0.1:9002
msredpdf.service              active   /opt/msredpdf             127.0.0.1:3142
rapidleech.service            active   /opt/rapidleech           127.0.0.1:2581
redia.service                 active   /opt/redia                127.0.0.1:3099
red-sebia.service             active   /opt/redsebia             127.0.0.1:3130
red-seb-monitor.service       active   /opt/red-seb-monitor      0.0.0.0:2580
red-proxy-lab.service         active   /opt/red-proxy-lab        127.0.0.1:8090
```

## Servicos versionados, mas inativos nesta VM

```text
red-openclaw.service
redtrader.service
red-iq-vision-bridge.service
red-webhook.service
red-seb-webhook.service
```

Eles continuam versionados para compatibilidade, reinstalacao futura ou ativacao pontual, mas nao entram no conjunto essencial ativo desta VM.

## Rotas publicas principais

```text
/                         portal
/portal-assets/            assets do portal
/modelo1/                  landing estatica modelo 1
/modelo2/                  landing estatica modelo 2
/modelos/                  galeria de modelos
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

## Portas dedicadas

```text
:2580                      RED SEB Monitor direto
:5050                      RED NIM Claude direto, TLS proprio
:5051                      RED Lightning Claude direto, TLS proprio
:5052                      RED Alibaba Claude direto, TLS proprio
```

## Proxies e gateways Claude

```text
proxy normal               /opt/redvm-proxy          55 modelos em /v1/models
redproxypro                /opt/redproxypro          19 modelos em /v1/models
redclaudeproxy             /opt/redclaudeproxy       23 modelos em /v1/models
rednimclaude               /opt/rednimclaude         8 modelos em /v1/models
redlightningclaude         /opt/redlightningclaude   3 modelos em /v1/models
redalibabaclaude           /opt/redalibabaclaude     8 modelos em /v1/models
```

Arquivos de ambiente observados:

```text
/etc/red-ollama-proxy.env
/etc/redproxypro.env
/etc/redclaudeproxy.env
/etc/rednimclaude.env
/etc/redlightningclaude.env
/etc/redalibabaclaude.env
```

As chaves reais ficam nesses arquivos remotos ou em arquivos auxiliares apontados por eles. Elas nao devem entrar no repo.

## RED SEB Portable

Fonte versionado:

```text
servicos/redsebia/downloads/REDSEBPortable/
```

Runtime esperado:

```text
/opt/redsebia/downloads/REDSEBPortable/
/opt/red-seb-monitor/data/downloads/REDSEBPortable.zip
```

Regra atual:

- `libcef.dll` fica fatiado no repo em `.redvm-large/libcef.dll.partNNN`;
- o `red-seb-monitor` reconstrói `libcef.dll` antes de empacotar;
- o ZIP publico e gerado sob demanda na pagina `/download`;
- o `.bat` universal so e liberado quando o ZIP existir.

## Validacoes feitas

```text
systemctl ativos principais: OK
nginx em 80/443: OK
proxy normal /v1/models: 200
redproxypro /healthz: 200
redclaudeproxy /healthz: 200
rednimclaude /healthz: 200
redlightningclaude /healthz: 200
redalibabaclaude /healthz: 200
redsebia /healthz: 200
red-seb-monitor /healthz: 200
msredpdf /healthz: 200
modelos-counter /healthz: 200
```

Observacao: `systemctl --failed` mostrou apenas `motd-news.service`, fora da stack RED.

## Regra de manutencao

Quando alterar a VM, atualizar no mesmo ciclo:

- `README.md`
- `servicos/README.md`
- `infraestrutura/README.md`
- README do servico tocado
- unit systemd correspondente, se houver
- `infraestrutura/nginx/red-friendly-paths.nginx.conf`, se a rota mudar
- este snapshot, quando o estado operacional mudar
