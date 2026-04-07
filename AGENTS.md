# AGENTS.md - RED Systems Infra Lab

Este workspace guarda codigo e infra dos servicos RED Systems. Nao coloque senhas, tokens ou chaves reais neste arquivo.

## Regras De Seguranca

- Use `.env.local` ou `AGENTS.local.md` para credenciais reais.
- `.privado/` e `artefatos/` sao locais e nao devem ir para Git.
- Antes de commitar, rode uma busca por segredos:

```powershell
rg -n "(g[h]p_|n[v]api-|g[s]k_|api_key|password|senha|token|secret)" -S .
```

## VM

Os dados de conexao devem vir de ambiente:

```env
REDSYSTEMS_HOST=
REDSYSTEMS_SSH_PORT=
REDSYSTEMS_SSH_USER=
REDSYSTEMS_SSH_PASSWORD=
```

Use Paramiko e wrapper UTF-8 para saida:

```python
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
```

Helper recomendado:

```powershell
python ferramentas/vm/paramiko_exec.py "systemctl status red-dashboard --no-pager"
```

## Servicos

- `servicos/proxy`: proxy IA Ollama-compatible com roteamento NVIDIA.
- `servicos/dashboard`: painel Red VM / Red Systems.
- `servicos/redia`: IA via WhatsApp.
- `servicos/redtrader`: painel de trading paper/demo.
- `servicos/deploy-agent`: webhook/deploy inteligente legado.

## Infraestrutura

- `infraestrutura/systemd`: units systemd.
- `infraestrutura/nginx`: configs Nginx.
- `infraestrutura/docker`: compose auxiliares.
- `infraestrutura/scripts`: scripts de instalacao/sync/deploy.

## Deploy

Sempre fazer backup remoto antes de sobrescrever arquivos da VM. Depois de subir arquivo, validar sintaxe e reiniciar apenas o servico tocado.
