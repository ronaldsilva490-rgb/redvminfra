# RED Claude Code

Launcher desktop em Python + PySide6 para usar o Claude Code apontando para o proxy oficial da RED Systems.

## O que ele faz

- busca o catalogo vivo em `http://redsystems.ddns.net/proxy/v1/models`
- mostra interface RED Systems de verdade
- filtra por busca em tempo real
- exibe provider, tipo, capabilities, route model e nota
- abre o Explorer para escolher a pasta de trabalho
- inicia o `claude --model "<modelo>"` em uma nova janela de terminal

## Arquivos

- [RED Systems Claude Code.bat](./RED%20Systems%20Claude%20Code.bat)
- [__main__.py](./__main__.py)
- [app.py](./app.py)

## Uso

```powershell
ferramentas\redclaudecode\RED Systems Claude Code.bat
```

## Observacoes

- o launcher injeta:
  - `ANTHROPIC_AUTH_TOKEN=ollama`
  - `ANTHROPIC_BASE_URL=http://redsystems.ddns.net/proxy`
- ele filtra para modelos com capacidade de chat/vision, porque esse e o caso util do Claude Code.
- o `.bat` apenas chama o launcher Python; a UI principal agora nao depende mais de PowerShell.
