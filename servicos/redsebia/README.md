# REDSEBIA

Novo ecossistema independente do antigo monitor SEB.

O objetivo aqui e separar o produto de cliente e monetizacao do legado:

- portal do cliente;
- painel administrativo;
- carteira com saldo;
- top-up por PIX;
- trilho de autenticacao do comando `red`;
- autorizacao de uso do runtime futuro;
- reserva e liquidacao de uso de IA por tokens.

O portable do SEB agora fica integrado neste repo como fonte bruto. O ZIP publico passa a ser artefato gerado a partir desse diretorio.

Fonte obrigatorio de deploy:

- `downloads/REDSEBPortable/`

Esse diretorio substitui o projeto local avulso `C:\Projetos\redseb\REDSEBPORTABLE\PortableBuild`. Dentro do ZIP gerado, ele deve aparecer como a pasta raiz `REDSEBPortable/`, contendo `SafeExamBrowser.exe`, `config.seb`, `PortableData/`, `locales/` e demais DLLs.

O arquivo `libcef.dll` passa de 100 MB e nao pode ser enviado ao GitHub como blob normal. Por isso ele fica fatiado em `downloads/REDSEBPortable/.redvm-large/libcef.dll.partNNN`. O `red-seb-monitor` reconstrói `downloads/REDSEBPortable/libcef.dll` automaticamente antes de empacotar o ZIP. O `libcef.dll` reconstruido e artefato local e fica ignorado pelo Git.

No runtime atual, quem serve o download publico ainda e o `red-seb-monitor`, portanto o deploy precisa levar esse diretorio para:

```text
/opt/redsebia/downloads/REDSEBPortable
```

A pagina `/download` do monitor detecta esse diretorio, empacota `/opt/red-seb-monitor/data/downloads/REDSEBPortable.zip` sob demanda e libera o `.bat` apenas depois que o ZIP existir.

## O que este servico entrega

- rota publica planejada: `/redsebia/`
- portal do cliente com cadastro, login, saldo, top-ups e historico
- painel admin em `/redsebia/admin`
- device auth para o `red login`
- runtime API para:
  - autorizar uso
  - reservar saldo
  - liquidar uso
  - liberar reserva
- camada de providers de pagamento configuravel pelo painel

## Providers de pagamento

Hoje o servico sobe com estes adapters:

- `sandbox_pix`
- `manual_pix`
- `asaas`
- `efi_pix`
- `mercadopago_pix`
- `pagarme_pix` (estrutura pronta)
- `pagseguro_pix` (estrutura pronta)

O `sandbox_pix` fica ativo por padrao para validar a stack inteira na VM sem depender de credencial externa.

### Guia especifico do PagBank

Se você quiser ligar o `PagBank PIX` no painel admin do REDSEBIA, use:

- [PAGBANK.md](./PAGBANK.md)

## Dependencias

- Python 3.11+
- `venv`
- nginx para publicar a rota amigavel

## Variaveis de ambiente

Use `.env.example` como base:

```bash
cp servicos/redsebia/.env.example /etc/red-sebia.env
```

Principais:

- `REDSEBIA_HOST`
- `REDSEBIA_PORT`
- `REDSEBIA_PUBLIC_BASE_URL`
- `REDSEBIA_DB_PATH`
- `REDSEBIA_PROXY_URL`
- `REDVM_REPO_DIR`
- `REDSEBIA_ADMIN_PASSWORD`
- `REDSEBIA_SECRET`
- `REDSEBIA_DEVICE_CODE_TTL_SECONDS`
- `REDSEBIA_RUNTIME_TOKEN_TTL_SECONDS`
- `REDSEBIA_MIN_LAUNCH_BALANCE_CENTS`
- `REDSEBIA_DEFAULT_HOLD_CENTS`

## Rodar localmente

```bash
cd servicos/redsebia
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH="$PWD/src"
set -a
. ./.env
set +a
python -m redsebia.app
```

Abra:

```text
http://127.0.0.1:3130/
```

## Instalacao em qualquer VM

1. Dependencias base:

```bash
apt-get update
apt-get install -y python3 python3-venv python3-pip nginx
```

2. Copie o runtime:

```bash
mkdir -p /opt/redsebia
rsync -a servicos/redsebia/ /opt/redsebia/
cd /opt/redsebia
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

3. Ambiente:

```bash
cp /opt/redsebia/.env.example /etc/red-sebia.env
mkdir -p /opt/redsebia/data
```

4. Fonte do RED SEB Portable:

```bash
test -d /opt/redsebia/downloads/REDSEBPortable
test -f /opt/redsebia/downloads/REDSEBPortable/SafeExamBrowser.exe
test -f /opt/redsebia/downloads/REDSEBPortable/.redvm-large/libcef.dll.part001
```

Depois de copiar ou atualizar esse diretorio, reinicie somente o monitor SEB para ele usar a nova fonte:

```bash
systemctl restart red-seb-monitor
```

O ZIP final e gerado pela pagina `/download` quando necessario. Para conferir o estado:

```bash
curl -s http://127.0.0.1:2580/api/portable/status | python3 -m json.tool
```

5. Unit oficial:

```bash
cp infraestrutura/systemd/red-sebia.service /etc/systemd/system/red-sebia.service
systemctl daemon-reload
systemctl enable --now red-sebia
```

6. Publicacao:

- incluir a rota `/redsebia/` no nginx usando `infraestrutura/nginx/red-friendly-paths.nginx.conf`

7. Validacao:

```bash
cd /opt/redsebia
. .venv/bin/activate
export PYTHONPATH=/opt/redsebia/src
python -m py_compile src/redsebia/*.py
systemctl is-active red-sebia
systemctl is-active red-seb-monitor
curl -s http://127.0.0.1:3130/healthz
curl -s http://127.0.0.1:2580/api/portable/status | python3 -m json.tool
curl -I http://127.0.0.1:2580/downloads/REDSEBPortable.zip
```

## Endpoints principais

Cliente:

- `GET /`
- `GET /login`
- `GET /register`
- `GET /portal`
- `POST /api/register`
- `POST /api/login`
- `POST /api/logout`
- `GET /api/bootstrap`
- `POST /api/topups`
- `POST /api/topups/{id}/refresh`
- `POST /api/topups/{id}/sandbox/confirm`

Device auth:

- `POST /api/device/start`
- `POST /api/device/poll`
- `GET /device`
- `POST /api/device/approve`
- `POST /api/device/deny`

Admin:

- `GET /admin/login`
- `GET /admin`
- `POST /api/admin/login`
- `POST /api/admin/logout`
- `GET /api/admin/bootstrap`
- `POST /api/admin/providers/{code}`
- `POST /api/admin/charges/{id}/mark-paid`
- `POST /api/admin/charges/{id}/expire`

Runtime futuro:

- `GET /api/runtime/me`
- `GET /api/runtime/models`
- `POST /api/runtime/launch/authorize`
- `POST /api/runtime/analysis/reserve`
- `POST /api/runtime/analysis/settle`
- `POST /api/runtime/analysis/release`

Webhooks:

- `POST /api/payments/webhooks/{provider_code}`

## Runtime oficial planejado

- codigo: `/opt/redsebia`
- dados: `/opt/redsebia/data`
- env: `/etc/red-sebia.env`
- service: `red-sebia.service`
- rota publica: `http://HOST/redsebia/`
