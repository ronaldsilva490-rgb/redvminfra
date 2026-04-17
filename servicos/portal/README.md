# Portal RED Systems

Home publica da stack. Hoje ela e um front estatico servido pelo nginx e funciona como entrada para a VM unica.

## O que este servico entrega

- rota publica: `/`
- links oficiais para:
  - dashboard
  - proxy IA
  - RED I.A
  - RED Trader
  - Proxy Lab
  - IQ Bridge
  - OpenClaw

## Dependencias do host

- nginx

## Rodar localmente

Como e um HTML estatico, qualquer servidor simples serve:

```bash
cd servicos/portal
python3 -m http.server 8088
```

Abra:

```text
http://127.0.0.1:8088
```

## Instalacao em qualquer VM

1. Instale nginx:

```bash
apt-get update
apt-get install -y nginx
```

2. Copie o portal para o root publico:

```bash
mkdir -p /var/www/red-portal
rsync -a servicos/portal/ /var/www/red-portal/
```

3. Ajuste o server nginx para servir `/var/www/red-portal/index.html` na raiz `/`.

4. Se usar o include oficial do repo, copie tambem:

```bash
cp infraestrutura/nginx/red-friendly-paths.nginx.conf /etc/nginx/snippets/red-friendly-paths.nginx.conf
```

## Validacao recomendada

```bash
nginx -t
systemctl reload nginx
curl -I http://127.0.0.1/
```

## Runtime oficial na RED

- arquivos: `/var/www/red-portal`
- exposicao: nginx em `/`

## Observacoes

- Como o portal e estatico, qualquer mudanca aqui deve ser validada na UI real do navegador.
- Se adicionar assets, mantenha tudo dentro de `servicos/portal/` para o deploy continuar simples.
