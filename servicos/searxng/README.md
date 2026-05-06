# RED Search / SearXNG

Busca web gratuita da stack RED, usada como backend `custom` do OpenClaude.

## Rotas

- Publica: `http://redsystems.ddns.net/search/`
- API JSON: `http://redsystems.ddns.net/search/search?q=teste&format=json&pageno=1`
- Local na VM: `http://127.0.0.1:8088/`

## Runtime oficial

- Codigo/config: `/opt/red-searxng`
- Service: `red-searxng.service`
- Porta local: `127.0.0.1:8088`
- Publicacao: nginx em `/search/`

## Instalar ou atualizar na VM

```bash
mkdir -p /opt/red-searxng
rsync -a servicos/searxng/ /opt/red-searxng/
cd /opt/red-searxng
cp -n .env.example .env
sed -i "s/troque-por-um-hex-grande/$(openssl rand -hex 32)/" .env
docker compose pull
docker compose up -d
```

Instale a unit:

```bash
cp infraestrutura/systemd/red-searxng.service /etc/systemd/system/red-searxng.service
systemctl daemon-reload
systemctl enable --now red-searxng
```

Publique a rota:

```bash
cp infraestrutura/nginx/red-friendly-paths.nginx.conf /etc/nginx/redvm-routes/red-friendly-paths.nginx.conf
nginx -t
systemctl reload nginx
```

## OpenClaude

Configure o launcher local com:

```powershell
$env:WEB_SEARCH_PROVIDER = "custom"
$env:WEB_PROVIDER = "searxng"
$env:WEB_SEARCH_API = "http://redsystems.ddns.net/search/search"
$env:WEB_PARAMS = '{"format":"json","language":"pt-BR","pageno":"1"}'
$env:WEB_CUSTOM_ALLOW_HTTP = "true"
```

`WEB_KEY` fica vazio. O SearXNG nao exige chave.

## Validacao

```bash
systemctl status red-searxng --no-pager
docker ps --filter name=red-searxng
curl -sS "http://127.0.0.1:8088/search?q=redsystems&format=json" | jq '.results[0]'
curl -sS "http://redsystems.ddns.net/search/search?q=redsystems&format=json&pageno=1" | jq '.results[0]'
```

## Observacoes

O SearXNG consulta buscadores de terceiros e pode sofrer bloqueio ou reduzir resultado quando algum motor externo limita a VM. A rota atual nao exige chave para o OpenClaude local; se virar alvo de abuso, proteja no nginx com allowlist ou `limit_req` antes de anunciar publicamente.
