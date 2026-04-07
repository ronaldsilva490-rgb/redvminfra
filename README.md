<p align="center">
  <img src="identidade/logo/logo.png" alt="RED Systems" width="150" />
</p>

<h1 align="center">RED Systems Infra Lab</h1>

<p align="center">
  <strong>Proxy IA, dashboard de VM, WhatsApp AI, trading paper e automacao de deploy em um laboratorio RED.</strong>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-BB1D13?style=for-the-badge&labelColor=140202">
  <img alt="Node" src="https://img.shields.io/badge/Node.js-20-EE4D31?style=for-the-badge&labelColor=140202">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-dashboard-DB2315?style=for-the-badge&labelColor=140202">
  <img alt="NVIDIA" src="https://img.shields.io/badge/NVIDIA-NIM-76B900?style=for-the-badge&labelColor=140202">
</p>

<p align="center">
  <em>Uma base para replicar a stack RED em qualquer VM: subir, testar, observar, quebrar com elegancia e corrigir rapido.</em>
</p>

---

## Mapa Do Repositorio

```text
servicos/
  proxy/                 Proxy Ollama-compatible com roteamento NVIDIA
  dashboard/             Painel Red VM / Red Systems
  redia/                 IA de WhatsApp com memoria, midia, TTS e STT
  redtrader/             Trading paper/demo com dados reais e IA
  deploy-agent/          Webhook/deploy inteligente legado

infraestrutura/
  systemd/               Units de servicos
  nginx/                 Reverse proxy
  docker/                Compose auxiliares
  scripts/               Espaco para automacao de infra

ferramentas/
  vm/                    Helpers Paramiko/env
  implantacao/           Analisadores e ferramentas de deploy
  diagnosticos/          Checks reutilizaveis
  avaliacoes/            Benchmarks de modelos
  nvidia/                Utilitarios NIM/NVCF

referencias/
  whatsappold/           Bot antigo para portar logicas uteis

documentacao/
  implantacao-servicos.md Manual de implantacao por servico
  manual-completo.md      Runbook geral da RED Systems
  arquitetura.md          Visao tecnica
  preparacao-vm.md        Preparacao de VM

identidade/
  logo/                  Logo e favicon RED

artefatos/               Ignorado: imagens, audios e catalogos gerados
.privado/                Ignorado: senhas, snapshots e scripts antigos locais
```

## Servicos

| Servico | Caminho | Funcao |
|---|---|---|
| Proxy IA | `servicos/proxy` | Expoe `/api/chat`, `/api/generate`, `/api/tags` e `/api/images/generate`; modelos com `(NVIDIA)` vao para NVIDIA NIM. |
| Dashboard | `servicos/dashboard` | Painel operacional da VM, com chat do proxy, chaves, logs e teste de geracao de imagens. |
| REDIA | `servicos/redia` | Runtime WhatsApp AI com memoria local, aprendizado, midia, Edge TTS e fila de imagem. |
| RED Trader | `servicos/redtrader` | Painel de paper trading 24/7 com dados reais, saldo simulado e comite de IA. |
| Deploy Agent | `servicos/deploy-agent` | Webhook/deploy inteligente legado para projetos Docker/systemd. |

## Comeco Rapido

```powershell
git clone <repo-url>
cd redsystems-infra
Copy-Item .env.example .env.local
```

Edite `.env.local` com valores reais. Nunca commite esse arquivo.

Para executar comando remoto via Paramiko:

```powershell
$env:REDSYSTEMS_HOST="seu-host"
$env:REDSYSTEMS_SSH_PORT="22"
$env:REDSYSTEMS_SSH_USER="root"
$env:REDSYSTEMS_SSH_PASSWORD="sua-senha"
python ferramentas/vm/paramiko_exec.py "systemctl status red-dashboard --no-pager"
```

## Manuais

- [Implantacao de servicos](documentacao/implantacao-servicos.md)
- [Manual completo](documentacao/manual-completo.md)
- [Arquitetura](documentacao/arquitetura.md)
- [Preparacao de VM](documentacao/preparacao-vm.md)

## Regras De Seguranca

Segredos reais ficam fora do Git:

```text
.env.local
AGENTS.local.md
.privado/
artefatos/
```

Antes de qualquer commit:

```powershell
rg -n "(g[h]p_|n[v]api-|g[s]k_|api_key|password|senha|token|secret)" -S .
git status --short --ignored
```

O arquivo antigo com instrucoes sensiveis foi preservado em `.privado/AGENTS.original.md`. Scripts antigos com credenciais hardcoded foram movidos para `.privado/legacy-vm-scripts/`.
