# RED SEB Monitor

Painel remoto oficial do ecossistema **RED SEB / Safe Exam Browser** exposto hoje na porta `2580` da VM.

Este servico saiu do projeto separado `C:\projetos\redseb` e agora vive dentro da stack principal `redvm`, para ficar versionado, documentado e operado junto com o restante da infraestrutura RED.

## O que ele faz

- recebe sessoes remotas do cliente SEB por WebSocket;
- guarda o estado em memoria;
- exibe viewport, metadados da sessao e status do candidato em tempo real;
- aceita alertas temporarios para a sessao selecionada;
- gera um `.bat` para abrir links `seb://` ou `sebs://` dentro do **RED SEB Portable**;
- serve downloads auxiliares do ecossistema SEB:
  - `Setup.msi`
  - `SetupBundle.exe`
  - `REDSEBPortable.zip`
  - `upgrade-seb.ps1`

## Como ele funciona

O servico e um servidor Node simples:

- `server.js` abre HTTP em `0.0.0.0`
- porta padrao: `2580`
- `ws` e usado para receber atualizacoes do cliente remoto
- assets como logo e favicon sao resolvidos dinamicamente a partir da stack RED
- arquivos de download sao buscados no caminho canonico `/opt/red-seb-monitor/data/downloads`
- o caminho legado `/opt/seb-remote-view/downloads` pode existir como link de compatibilidade

Rotas operacionais principais:

- `GET /healthz`
- `GET /api/sessions`
- `GET /api/summary`
- `POST /api/alert`
- `POST /api/generate-bat`
- `GET /downloads/Setup.msi`
- `GET /downloads/SetupBundle.exe`
- `GET /downloads/REDSEBPortable.zip`
- `GET /downloads/upgrade-seb.ps1`

## Dependencias

- Node.js 20+
- npm

## Variaveis de ambiente

Use `.env.example` como base:

```bash
cp servicos/redseb-monitor/.env.example .env
```

Variaveis principais:

- `PORT`
- `SEB_REMOTE_VIEW_DOWNLOADS_DIR`
- `REDVM_REPO_DIR`
- `RED_DASHBOARD_DIR`
- `REDIA_DIR`
- `RED_PORTAL_DIR`

## Rodar localmente

```bash
cd servicos/redseb-monitor
npm install
npm start
```

Abra:

```text
http://127.0.0.1:2580
```

## Instalacao em qualquer VM

1. Instale dependencias:

```bash
apt-get update
apt-get install -y nodejs npm
```

2. Copie o runtime:

```bash
mkdir -p /opt/red-seb-monitor
rsync -a servicos/redseb-monitor/ /opt/red-seb-monitor/
cd /opt/red-seb-monitor
npm install
```

3. Crie o arquivo de ambiente:

```bash
cp servicos/redseb-monitor/.env.example /etc/red-seb-monitor.env
```

4. Crie o diretório de dados:

```bash
mkdir -p /opt/red-seb-monitor/data/downloads
```

5. Instale a unit oficial:

```bash
cp infraestrutura/systemd/red-seb-monitor.service /etc/systemd/system/red-seb-monitor.service
systemctl daemon-reload
systemctl enable --now red-seb-monitor
```

6. Publique a porta `2580` apenas se o monitor remoto realmente precisar ficar acessivel de fora.

## Validacao recomendada

```bash
node --check /opt/red-seb-monitor/server.js
systemctl is-active red-seb-monitor
curl -s http://127.0.0.1:2580/healthz | python3 -m json.tool
curl -s http://127.0.0.1:2580/api/summary | python3 -m json.tool
```

## Runtime atual observado

Hoje, na VM da RED, ele aparece na porta:

```text
http://redsystems.ddns.net:2580
```

e se identifica como:

```text
RED SEB Monitor
```

Runtime oficial esperado:

- codigo: `/opt/red-seb-monitor`
- downloads canonicos: `/opt/red-seb-monitor/data/downloads`
- compatibilidade legada opcional: `/opt/seb-remote-view/downloads -> /opt/red-seb-monitor/data/downloads`
- env: `/etc/red-seb-monitor.env`
- service: `red-seb-monitor.service`
- exposicao: `http://HOST:2580`

## Origem antiga

Ele era mantido duplicado nestes caminhos:

- `C:\projetos\redseb\seb-win-refactoring\deployment\seb-remote-view`
- `C:\projetos\redseb\REDSEBPORTABLE\deployment\seb-remote-view`

A partir desta reorganizacao, o ponto canonico passa a ser:

- `servicos/redseb-monitor`

## O que existe em `C:\projetos\redseb`

O projeto antigo continua sendo a referencia do cliente Windows e do navegador decomposto do SEB:

- `REDSEBPORTABLE/` guarda a distribuicao portavel baseada em Safe Exam Browser;
- `seb-win-refactoring/` guarda a base Windows refatorada do navegador;
- `deployment/windows/upgrade-seb.ps1` mostra o cliente consumindo este monitor pela URL `http://redsystems.ddns.net:2580`.

Ou seja: o **cliente SEB** continua sendo estudado e mantido no repo `redseb`, mas o **monitor remoto operacional** agora e parte oficial da stack `redvm`.
