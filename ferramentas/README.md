# Ferramentas

Ferramentas locais reaproveitaveis:

```text
vm/           Conexao Paramiko/env.
implantacao/  Analisadores e helpers de deploy.
diagnosticos/ Espaco para checks sem credenciais hardcoded.
avaliacoes/   Benchmarks de modelos.
nvidia/       Testes e utilitarios NVIDIA NIM/NVCF.
red_model_studio/ App desktop PySide6 para testar chat/imagem do proxy.
redclaudecode/  Launcher visual do Claude Code usando o proxy da RED Systems.
seb_frame_streamer/ GUI simples para simular uma sessao SEB real via WebSocket.
```

Scripts antigos com senha hardcoded foram preservados em `.privado/legacy-vm-scripts/` e nao devem ser publicados.

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

## RED SEB Debug Streamer

Ferramenta desktop simples para publicar uma imagem local como frame de uma sessao SEB fake no monitor.

Executar:

```powershell
pip install -r ferramentas/requirements.txt
python -m ferramentas.seb_frame_streamer
```
