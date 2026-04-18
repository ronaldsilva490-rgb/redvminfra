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
seb_frame_streamer/ GUI simples para injetar uma frame fake no RED SEB Monitor.
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

Executar:

```powershell
ferramentas\redclaudecode\RED Systems Claude Code.bat
```

## RED SEB Debug Streamer

Ferramenta desktop simples para publicar uma imagem local como frame de uma sessao SEB fake no monitor.

Executar:

```powershell
pip install -r ferramentas/requirements.txt
python -m ferramentas.seb_frame_streamer
```
