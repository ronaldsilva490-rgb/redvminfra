# Rapidleech RED

Hub legado de transferencia remota, upload e gerenciamento de arquivos agora oficializado dentro da stack RED Systems.

Este servico continua sendo um app PHP legado, mas foi trazido para o repo principal, ganhou tema RED, passou a respeitar publicacao atras de prefixo (`/rapidleech/`) e agora entra no portal, no dashboard e no runbook oficial da VM unica.

## O que este servico entrega

- rota publica canonica: `/rapidleech/`
- runtime oficial: `/opt/rapidleech`
- pasta de arquivos: `/opt/rapidleech/files`
- publicacao via nginx na frente e PHP built-in server por tras
- tema visual RED em `templates/red`
- suporte a `X-Forwarded-Prefix` para funcionar limpo atras de `/rapidleech/`

## Estrutura importante

```text
servicos/rapidleech/
  assets/                 logo e favicon RED
  configs/                configuracao legada do app
  files/                  diretorio de downloads/uploads do runtime
  templates/red/          tema oficial RED
  rl_init.php             bootstrap com suporte a prefixo reverso
```

## Configuracao

Os defaults versionados ficam em:

- `configs/default.php`
- `configs/config.php`

Pontos que ja deixamos saneados no repo:

- `template_used = red`
- idioma padrao `pt-br`
- credenciais versionadas removidas
- `secretkey` e usuario admin substituidos por placeholders

Antes de publicar em qualquer VM, ajuste pelo menos:

- `secretkey`
- `users`
- `login`
- politicas de upload/download

## Ambiente do servico

O PHP app em si quase nao usa variavel de ambiente, mas a unit oficial usa:

- `RAPIDLEECH_HOST`
- `RAPIDLEECH_PORT`

Exemplo base em:

- [.env.example](.env.example)

## Instalacao em qualquer VM

1. Instale PHP:

```bash
apt-get update
apt-get install -y php
```

2. Copie o runtime:

```bash
mkdir -p /opt/rapidleech
rsync -a servicos/rapidleech/ /opt/rapidleech/
mkdir -p /opt/rapidleech/files
```

3. Crie o env file:

```bash
cp servicos/rapidleech/.env.example /etc/red-rapidleech.env
```

4. Revise a configuracao da aplicacao:

```bash
nano /opt/rapidleech/configs/config.php
```

5. Instale a unit:

```bash
cp infraestrutura/systemd/rapidleech.service /etc/systemd/system/rapidleech.service
systemctl daemon-reload
systemctl enable --now rapidleech
```

6. Publique no nginx:

```bash
cp infraestrutura/nginx/red-friendly-paths.nginx.conf /etc/nginx/snippets/red-friendly-paths.nginx.conf
nginx -t
systemctl reload nginx
```

## Validacao recomendada

```bash
php -l /opt/rapidleech/index.php
php -l /opt/rapidleech/rl_init.php
systemctl is-active rapidleech
curl -I http://127.0.0.1:2581/
curl -I http://127.0.0.1/rapidleech/
```

## Runtime oficial na RED

- codigo: `/opt/rapidleech`
- arquivos: `/opt/rapidleech/files`
- env: `/etc/red-rapidleech.env`
- unit: `rapidleech.service`
- rota publica: `/rapidleech/`

## Observacoes

- O servico continua legado, entao a meta aqui e estabilidade e organizacao, nao refatorar o app inteiro.
- O tema oficial fica em `templates/red`, mas o markup base do Rapidleech ainda e majoritariamente o original.
- O diretorio `files/` nao deve ir para Git com conteudo de runtime.
