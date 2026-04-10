# RED Claude Code

Launcher visual para usar o Claude Code apontando para o proxy oficial da RED Systems.

## O que ele faz

- busca o catalogo vivo em `http://redsystems.ddns.net/proxy/v1/models`
- mostra uma grade com modelo, provider, tipo e route model
- deixa filtrar por busca
- depois abre o Explorer para escolher a pasta de trabalho
- inicia o `claude --model "<modelo>"` no diretório escolhido

## Arquivos

- [RED Systems Claude Code.bat](./RED%20Systems%20Claude%20Code.bat)
- [RED Systems Claude Code.ps1](./RED%20Systems%20Claude%20Code.ps1)

## Uso

```powershell
ferramentas\redclaudecode\RED Systems Claude Code.bat
```

## Observacoes

- o launcher injeta:
  - `ANTHROPIC_AUTH_TOKEN=ollama`
  - `ANTHROPIC_BASE_URL=http://redsystems.ddns.net/proxy`
- ele filtra para modelos com capacidade de chat/vision, porque esse e o caso util do Claude Code.
