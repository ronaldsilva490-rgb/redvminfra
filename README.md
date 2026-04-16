<p align="center">
  <img src="identidade/logo/logo.png" alt="RED Systems" width="150" />
</p>

<h1 align="center">RED Systems Infra Lab</h1>

<p align="center">
  <strong>Portal, dashboard, RED I.A, proxy IA, RED Trader, proxy-lab e IQ bridge organizados para uma VM unica.</strong>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-BB1D13?style=for-the-badge&labelColor=140202">
  <img alt="Node" src="https://img.shields.io/badge/Node.js-20-EE4D31?style=for-the-badge&labelColor=140202">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-dashboard-DB2315?style=for-the-badge&labelColor=140202">
  <img alt="NVIDIA" src="https://img.shields.io/badge/NVIDIA-NIM-76B900?style=for-the-badge&labelColor=140202">
</p>

<p align="center">
  <em>O repo e a VM principal precisam contar a mesma historia: uma stack unificada, observavel e operavel sem pular entre maquinas.</em>
</p>

---

## Visao Atual

Hoje a RED Systems roda consolidada em **uma VM principal**.

Servicos publicos:

- `/` -> portal
- `/dashboard/` -> painel principal
- `/proxy/` -> proxy IA oficial
- `/redia/` -> runtime da RED I.A
- `/trader/` -> RED Trader
- `/proxy-lab/` -> laboratorio de benchmark
- `/iq-bridge/` -> bridge da extensao IQ demo
- `/openclaw/` -> assistente operacional privado OpenClaw

### Dashboard com rotas reais por aba

O dashboard principal nao depende mais so de abas locais em JS. Cada area importante tem caminho proprio:

- `/dashboard/`
- `/dashboard/servicos`
- `/dashboard/docker`
- `/dashboard/proxyia`
- `/dashboard/redia`
- `/dashboard/projetos`
- `/dashboard/logs`
- `/dashboard/terminal`
- `/dashboard/arquivos`
- `/dashboard/firewall`
- `/dashboard/processos`

---

## Mapa do Repositorio

```text
servicos/
  portal/                Home publica da RED Systems
  dashboard/             Painel principal da VM unica
  proxy/                 Proxy IA oficial, Ollama-compatible com upstream NVIDIA
  proxy-lab/             Laboratorio pago/experimental para benchmark de modelos
  redia/                 Runtime da RED I.A com Baileys, memoria, audio e imagem
  redtrader/             Trading demo/paper com IQ e comite/modelos
  openclaw/              Assistente operacional privado da stack
  extensao-iq-demo/      Extensao Chrome MV3 e bridge de telemetria/comandos
  deploy-agent/          Legado

infraestrutura/
  systemd/               Units oficiais da VM unica
  nginx/                 Friendly paths e reverse proxy
  docker/                Artefatos auxiliares/legados
  scripts/               Instalacao, sync e apoio de infra

ferramentas/
  vm/                    Paramiko, execucao remota e migracao
  implantacao/           Utilitarios de deploy
  diagnosticos/          Checks reaproveitaveis
  avaliacoes/            Benchmarks e catalogos
  nvidia/                Utilitarios NIM/NVCF

documentacao/
  arquitetura.md
  implantacao-servicos.md
  manual-completo.md
  preparacao-vm.md
```

---

## Servicos

| Servico | Caminho | Funcao |
|---|---|---|
| Portal | `servicos/portal` | Home publica com atalhos para a stack da VM unica. |
| Dashboard | `servicos/dashboard` | Painel principal da VM: servicos, terminal, arquivos, proxy, RED I.A, projetos e observabilidade. |
| Proxy IA | `servicos/proxy` | Gateway Ollama-compatible com roteamento NVIDIA. |
| RED I.A | `servicos/redia` | Runtime principal de WhatsApp AI com memoria, audio, imagem e automacoes. |
| RED Trader | `servicos/redtrader` | Ambiente demo/paper de trading com IA. |
| Proxy Lab | `servicos/proxy-lab` | Laboratorio separado para benchmark pago e testes de modelos. |
| IQ Bridge | `servicos/extensao-iq-demo/bridge` | Bridge da extensao Chrome para snapshots, logs e comandos da IQ demo. |
| OpenClaw | `servicos/openclaw` | Assistente operacional privado via gateway, usando o proxy RED como backend. |
| Deploy Agent | `servicos/deploy-agent` | Legado, mantido so por compatibilidade. |

---

## RED I.A no Dashboard Principal

A RED I.A nao e mais so “um painel separado”.

Hoje o caminho principal de operacao e:

- dashboard principal -> aba/rota **RED I.A**
- URL: `/dashboard/redia`

Essa area foi portada para dentro do painel principal para concentrar:

- runtime/status
- conversas
- memoria
- envio manual
- agenda
- disparos usando IA
- benchmark/testes

O runtime standalone em `/redia/` continua existindo, mas o centro operacional da stack e o dashboard principal.

---

## Extensao IQ Demo

A extensao e o bridge existem para capturar e comandar a IQ demo com telemetria suficiente para correlacionar:

- `active_id`
- ativo atual
- payout
- ticks/candles
- portfolio/positions
- comandos remotos

Regra pratica: trate transporte e portfolio como fonte principal de verdade; OCR/DOM superficial e so apoio.

---

## Comeco Rapido

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

---

## Fluxo de Deploy

Sempre:

1. editar localmente;
2. validar sintaxe/checks;
3. fazer backup remoto;
4. subir so o que mudou;
5. reiniciar apenas o servico tocado;
6. validar por `systemctl`, endpoint e, quando fizer sentido, UI real.

Nunca subir “na fé”.

---

## Manuais

- [Implantacao de servicos](documentacao/implantacao-servicos.md)
- [Manual completo](documentacao/manual-completo.md)
- [Arquitetura](documentacao/arquitetura.md)
- [Preparacao de VM](documentacao/preparacao-vm.md)

---

## Regras de Seguranca

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

Se a documentacao do repo e a realidade da VM divergirem, considere isso um bug e alinhe os dois lados.
