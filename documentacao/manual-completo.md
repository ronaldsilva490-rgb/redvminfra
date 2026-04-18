# Manual Completo RED Systems Infra Lab

Este manual e o runbook principal para manter, portar e replicar a stack RED em qualquer ambiente.

## 1. Principios

- Segredo nunca entra no Git.
- Runtime nunca entra no Git.
- Todo deploy deve ter backup antes de sobrescrever arquivo remoto.
- Todo servico deve ter health check.
- Todo servico deve ser implantavel sem depender do caminho local original.
- Modelos IA sao configuracao, nao regra hardcoded de produto.

## 2. Estrutura

```text
servicos/        Codigo de produtos e servicos.
infraestrutura/  Systemd, Nginx, Docker e scripts de infra.
ferramentas/     Helpers locais e diagnosticos.
referencias/     Codigo legado ou externo para consulta.
documentacao/    Manuais e runbooks.
identidade/      Logo e assets RED.
artefatos/       Saidas geradas, ignoradas no Git.
.privado/        Segredos e snapshots locais, ignorados no Git.
```

## 3. Preparar Repo Novo

```powershell
git status --short --ignored
rg -n "(g[h]p_|n[v]api-|g[s]k_|api_key|password|senha|token|secret)" -S .
git add .
git status
git commit -m "Organiza RED Systems infra lab"
```

Se a varredura acusar campos vazios como `api_key` em `.env.example`, avalie manualmente. O problema real sao valores de segredo, nao nomes de campos.

## 4. Preparar Ambiente Local

Python:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r ferramentas/requirements.txt
```

Node para REDIA:

```powershell
cd servicos/redia
npm install
npm run check
```

Python para dashboard/proxy/redtrader:

```powershell
python -m py_compile servicos/proxy/proxy.py servicos/dashboard/app.py
python -m py_compile servicos/redtrader/src/redtrader/app.py
```

## 5. Configuracao Local

Copie:

```powershell
Copy-Item .env.example .env.local
```

Preencha valores reais localmente:

```env
REDSYSTEMS_HOST=
REDSYSTEMS_SSH_PORT=
REDSYSTEMS_SSH_USER=
REDSYSTEMS_SSH_PASSWORD=
RED_PROXY_NVIDIA_API_KEY=
REDIA_ADMIN_TOKEN=
REDIA_IMAGE_WORKER_TOKEN=
REDTRADER_PASSWORD=
```

Nao commitar `.env.local`.

## 6. Conexao Com VM

Use o helper:

```powershell
$env:REDSYSTEMS_HOST="example.com"
$env:REDSYSTEMS_SSH_PORT="22"
$env:REDSYSTEMS_SSH_USER="root"
$env:REDSYSTEMS_SSH_PASSWORD="..."
python ferramentas/vm/paramiko_exec.py "hostname && uptime"
```

Para scripts mais especificos, siga o padrao:

```python
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
```

## 7. Proxy IA

Papel:

- catalogar modelos;
- aceitar chamadas Ollama-like;
- rotear NVIDIA por prefixo `NIM - `;
- gerar imagens via NVIDIA.

Endpoints:

```text
GET  /api/tags
POST /api/chat
POST /api/generate
POST /api/images/generate
GET  /api/nvidia/models
```

Modelos de imagem validados:

```text
NIM - flux.1-dev
NIM - flux.1-schnell
NIM - flux.2-klein-4b
NIM - stable-diffusion-3-medium
NIM - stable-diffusion-xl
```

Nota: modelos Stable Diffusion da NVIDIA precisam de `steps >= 5`. O proxy e o dashboard ja protegem esse minimo.

## 8. Dashboard

Papel:

- status da VM;
- controle do proxy;
- chat do proxy;
- geracao de imagem para teste dos modelos;
- controle de chaves;
- suporte a deploys.

Validacoes:

```bash
systemctl status red-dashboard --no-pager
curl -I http://127.0.0.1:9001/
```

Teste de imagem via dashboard, apos login/cookie:

```text
POST /api/proxy/images/generate
```

Payload:

```json
{
  "model": "NIM - flux.1-schnell",
  "prompt": "red robot mascot, dark neon dashboard, no text",
  "width": 1024,
  "height": 1024,
  "steps": 4
}
```

## 9. REDIA

Papel:

- WhatsApp AI;
- memoria por conversa/pessoa;
- aprendizado por lote;
- midia, STT, TTS;
- geracao de imagem via worker/fila.

Comandos locais:

```powershell
cd servicos/redia
npm install
npm run check
npm start
```

Em producao, preferir systemd com env file.

## 10. RED Trader

Papel:

- simulador paper/demo;
- dados reais de mercado;
- relatorio de trades;
- comite IA via proxy.

Comandos locais:

```powershell
cd servicos/redtrader
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
$env:PYTHONPATH="src"
$env:REDTRADER_PASSWORD="change-me"
$env:REDTRADER_SECRET="change-me-too"
python -m redtrader.app
```

Nunca usar chaves reais de exchange no MVP paper.

## 10A. RED SEB Monitor

Papel:

- espelhar sessoes remotas do RED SEB / Safe Exam Browser;
- servir downloads do ecossistema SEB;
- permitir alertas e observacao operacional em tempo real.

Comandos locais:

```powershell
cd servicos/redseb-monitor
npm install
node --check server.js
npm start
```

Health:

```text
http://127.0.0.1:2580/healthz
http://127.0.0.1:2580/api/summary
```

## 10B. Rapidleech

Papel:

- centralizar downloads remotos, uploads e gerenciamento de arquivos;
- manter o legado Rapidleech dentro da stack oficial;
- publicar o app atras do nginx em `/rapidleech/`.

Comandos locais:

```powershell
cd servicos/rapidleech
php -l index.php
php -l rl_init.php
```

Runtime oficial:

```text
/opt/rapidleech
/opt/rapidleech/files
```

## 11. Deploy Seguro

Fluxo recomendado:

```text
1. Validar sintaxe local.
2. Backup remoto do arquivo atual.
3. Upload por SFTP/rsync.
4. Validar sintaxe na VM.
5. Restart do servico tocado.
6. Health check.
7. Se falhar, restaurar backup.
```

Exemplo:

```bash
cp /opt/redsystems/proxy/proxy.py /opt/redsystems/proxy/.backups/proxy.py.$(date +%Y%m%d-%H%M%S)
python3 -m py_compile /opt/redsystems/proxy/proxy.py
systemctl restart red-ollama-proxy
systemctl status red-ollama-proxy --no-pager
```

## 12. Logs

Proxy:

```bash
journalctl -u red-ollama-proxy -f
tail -f /var/lib/redsystems/proxy/proxy.log
```

Dashboard:

```bash
journalctl -u red-dashboard -f
```

REDIA:

```bash
journalctl -u redia -f
```

RED Trader:

```bash
journalctl -u redtrader -f
```

RED SEB Monitor:

```bash
journalctl -u red-seb-monitor -f
```

Rapidleech:

```bash
journalctl -u rapidleech -f
```

## 13. Nginx

Sempre validar antes de reload:

```bash
nginx -t
systemctl reload nginx
```

## 14. Backup

Antes de migrar VM:

```bash
tar -czf /root/redsystems-data-$(date +%Y%m%d).tar.gz /var/lib/redsystems
tar -czf /root/redsystems-opt-$(date +%Y%m%d).tar.gz /opt/redsystems
```

Nao inclua backups com dados reais no repo.

## 15. Checklist Para Nova VM

```text
[ ] Instalar pacotes base.
[ ] Copiar repo.
[ ] Criar env files locais.
[ ] Instalar proxy e validar /api/tags.
[ ] Instalar dashboard e validar login.
[ ] Configurar Nginx.
[ ] Instalar REDIA se a VM for de WhatsApp.
[ ] Instalar RED Trader se a VM for de trading.
[ ] Instalar Rapidleech se a VM tambem for operar o transfer hub legado.
[ ] Instalar RED SEB Monitor se a VM tambem operar o ecossistema SEB.
[ ] Configurar backups.
[ ] Rodar secret scan antes de qualquer push.
```

## 16. Troubleshooting Rapido

Servico nao sobe:

```bash
systemctl status NOME --no-pager -l
journalctl -u NOME --since "10 minutes ago" --no-pager
```

Proxy sem modelos NVIDIA:

```bash
systemctl show red-ollama-proxy --property=Environment
grep RED_PROXY_NVIDIA_API_KEY /etc/red-ollama-proxy.env
```

Dashboard sem atualizar JS/CSS:

```text
Atualize o cache-bust no template ou use Ctrl+F5 no navegador.
```

Geracao de imagem falhando por steps:

```text
Use steps >= 5 para stable-diffusion-* e flux.1-dev.
Flux schnell/klein podem usar steps 4.
```

## 17. Identidade Visual

O README usa apenas a logo local da RED em `identidade/logo/`. Evite depender de midia externa ou asset pesado no topo do repo.
