# Ferramentas

Ferramentas locais reaproveitaveis:

```text
vm/           Conexao Paramiko/env.
implantacao/  Analisadores e helpers de deploy.
diagnosticos/ Espaco para checks sem credenciais hardcoded.
avaliacoes/   Benchmarks de modelos.
nvidia/       Testes e utilitarios NVIDIA NIM/NVCF.
openclaw/     Benchmark e testes do OpenClaw.
red_model_studio/ App desktop PySide6 para testar chat/imagem do proxy.
redclaudecode/  Launcher visual do Claude Code usando o proxy da RED Systems.
claude-desktop/  Configuradores do Claude Desktop para RED Proxy Pro, incluindo modo sem VMP.
claude-code-vscode/  Configuracao da extensao Claude Code no VS Code via RED Proxy Pro.
inferall/      Utilitarios manuais para diagnostico/conta InferAll.
oci/           Helpers de descoberta e retry para criar instancia A1 Flex no OCI.
seb_frame_streamer/ GUI simples para simular uma sessao SEB real via WebSocket.
iq_vision_benchmark/ Benchmarks visuais da IQ.
```

Scripts antigos com senha hardcoded foram preservados em `.privado/legacy-vm-scripts/` e nao devem ser publicados.

## Snapshot da VM Unica

Para criar um snapshot restauravel do estado real da VM, carregue as credenciais locais em variaveis de ambiente e rode:

```powershell
python ferramentas/vm/create_system_snapshot.py
```

O script cria um diretorio em `/root/backups/redvm-system-snapshot-YYYYMMDD-HHMMSS/` contendo inventario, manifests SHA256 e arquivos `.tar.gz` com runtime, dados e configuracoes relevantes. Esse snapshot inclui envs/configs remotos para preservar fidelidade de restauracao, entao trate o resultado como material sensivel.

## RED Model Studio

Ferramenta desktop local para conversar com os modelos do proxy RED e testar geracao de imagens.

Executar:

```powershell
pip install -r ferramentas/requirements.txt
python -m ferramentas.red_model_studio
```

## RED Claude Code

Launcher Windows para abrir o Claude Code com:

- selecao visual de modelo do proxy
- busca por modelo/provider
- escolha da pasta de trabalho via Explorer
- modo portatil: copie o `.bat` para qualquer workspace, rode ali e escolha o modelo pelo numero

Executar:

```powershell
ferramentas\redclaudecode\RED Systems Claude Code.bat
```

Portatil:

```powershell
ferramentas\redclaudecode\RED Claude Code Portatil.bat
```

O portatil usa `RED_PROXY_BASE=http://redsystems.ddns.net/proxy` e `RED_PROXY_KEY=red` por padrao, ordena `OLLAMA` e `NIM` por provider/nome e inicia o Claude Code na pasta onde o `.bat` estiver.

## Claude Desktop RED Proxy Pro

Configuradores para o Claude Desktop em modo gateway:

```powershell
ferramentas\claude-desktop\Configurar-Claude-RED-ProxyPro.cmd
ferramentas\claude-desktop\Iniciar-Claude-RED-Sem-VMP.cmd
```

Estado atual:

- o launcher sem VMP usa a copia portatil patchada em `C:\Projetos\ClaudeREDDesktop\app`;
- o script `Preparar-Claude-RED-Chat.ps1` sincroniza os 19 modelos atuais do RED Proxy Pro no `claude_desktop_config.json` e no `configLibrary`;
- Code/workspace real do Claude Desktop nao e suportado nesse Windows reduzido; para codigo, use Claude Code no VS Code.

## Claude Code VS Code RED Proxy Pro

Configurador da extensao oficial `anthropic.claude-code`:

```powershell
ferramentas\claude-code-vscode\Configurar-Claude-Code-RED.ps1
ferramentas\claude-code-vscode\Iniciar-VSCode-Claude-Code-RED.cmd
```

Endpoint usado:

```text
https://redsystems.ddns.net/redproxypro
```

Modelo padrao local:

```text
anthropic/claude-sonnet-4.6
```

## RED SEB Debug Streamer

Ferramenta desktop simples para publicar uma imagem local como frame de uma sessao SEB fake no monitor.

Executar:

```powershell
pip install -r ferramentas/requirements.txt
python -m ferramentas.seb_frame_streamer
```
