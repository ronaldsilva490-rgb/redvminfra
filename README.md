<p align="center">
  <img src="identidade/logo/logo.png" alt="RED Systems" width="150" />
</p>

<h1 align="center">RED Systems Infra Lab</h1>

<p align="center">
  <strong>Proxy IA, dashboard de VM, WhatsApp AI, trading paper e automação de deploy em um laboratório RED.</strong>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-BB1D13?style=for-the-badge&labelColor=140202">
  <img alt="Node" src="https://img.shields.io/badge/Node.js-20-EE4D31?style=for-the-badge&labelColor=140202">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-dashboard-DB2315?style=for-the-badge&labelColor=140202">
  <img alt="NVIDIA" src="https://img.shields.io/badge/NVIDIA-NIM-76B900?style=for-the-badge&labelColor=140202">
</p>

<p align="center">
  <em>Uma base para replicar a stack RED em qualquer VM: subir, testar, observar, quebrar com elegância e corrigir rápido.</em>
</p>

---

## Mapa do Repositório

```text
servicos/
  proxy/                 Proxy Ollama-compatible com roteamento NVIDIA
  dashboard/             Painel Red VM / Red Systems
  redia/                 IA de WhatsApp com memória, mídia, TTS e STT
  redtrader/             Trading paper/demo com dados reais e IA
  deploy-agent/          Webhook/deploy inteligente legado

infraestrutura/
  systemd/               Units de serviços
  nginx/                 Reverse proxy
  docker/                Compose auxiliares
  scripts/               Espaço para automação de infra

ferramentas/
  vm/                    Helpers Paramiko/env
  implantacao/           Analisadores e ferramentas de deploy
  diagnosticos/          Checks reutilizáveis
  avaliacoes/            Benchmarks de modelos
  nvidia/                Utilitários NIM/NVCF

referencias/
  whatsappold/           Bot antigo para portar lógicas úteis

documentacao/
  implantacao-servicos.md Manual de implantação por serviço
  manual-completo.md      Runbook geral da RED Systems
  arquitetura.md          Visão técnica
  preparacao-vm.md        Preparação de VM

identidade/
  logo/                  Logo e favicon RED

artefatos/               Ignorado: imagens, áudios e catálogos gerados
.privado/                Ignorado: senhas, snapshots e scripts antigos locais
```

## Serviços

| Serviço | Caminho | Função |
|---|---|---|
| Proxy IA | `servicos/proxy` | Expõe `/api/chat`, `/api/generate`, `/api/tags` e `/api/images/generate`; modelos com `(NVIDIA)` vão para NVIDIA NIM. |
| Dashboard | `servicos/dashboard` | Painel operacional da VM, com chat do proxy, chaves, logs e teste de geração de imagens. |
| REDIA | `servicos/redia` | Runtime WhatsApp AI com memória local, aprendizado, mídia, Edge TTS e fila de imagem. |
| RED Trader | `servicos/redtrader` | Painel de paper trading 24/7 com dados reais, saldo simulado e comitê de IA. |
| Deploy Agent | `servicos/deploy-agent` | Webhook/deploy inteligente legado para projetos Docker/systemd. |

## Começo Rápido

```powershell
git clone <repo-url>
cd redvminfra
Copy-Item .env.example .env.local
```

Edite `.env.local` com valores reais. Nunca faça commit desse arquivo.

Para executar comando remoto via Paramiko:

```powershell
$env:REDSYSTEMS_HOST="seu-host"
$env:REDSYSTEMS_SSH_PORT="22"
$env:REDSYSTEMS_SSH_USER="root"
$env:REDSYSTEMS_SSH_PASSWORD="sua-senha"
python ferramentas/vm/paramiko_exec.py "systemctl status red-dashboard --no-pager"
```

## Manuais

- [Implantação de serviços](documentacao/implantacao-servicos.md)
- [Manual completo](documentacao/manual-completo.md)
- [Arquitetura](documentacao/arquitetura.md)
- [Preparação de VM](documentacao/preparacao-vm.md)

## Regras de Segurança

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

O arquivo antigo com instruções sensíveis foi preservado em `.privado/AGENTS.original.md`. Scripts antigos com credenciais hardcoded foram movidos para `.privado/legacy-vm-scripts/`.
