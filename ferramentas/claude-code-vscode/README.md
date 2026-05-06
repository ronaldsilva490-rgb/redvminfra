# Claude Code VS Code RED

Configuracao local para a extensao oficial `anthropic.claude-code` do VS Code usar o RED Proxy Pro.

## Arquivos

- `Configurar-Claude-Code-RED.ps1`: atualiza `~/.claude/settings.json` e `Code\User\settings.json` com variaveis do Claude Code.
- `Iniciar-VSCode-Claude-Code-RED.cmd`: abre o VS Code ja com ambiente apontado para o proxy.

## Endpoint

```text
ANTHROPIC_BASE_URL=https://redsystems.ddns.net/redproxypro
ANTHROPIC_API_KEY=red
ANTHROPIC_AUTH_TOKEN=red
```

O modelo padrao atual e:

```text
anthropic/claude-sonnet-4.6
```

O proxy tambem aceita aliases antigos, mas novos launchers devem usar os IDs reais `provider/model`.

## Uso

Feche o VS Code e abra pelo atalho:

```text
C:\Users\Ronyd\Desktop\VS Code Claude RED.cmd
```

Validacao rapida:

```powershell
claude -p --model anthropic/claude-sonnet-4.6 "Responda OK"
```

Para tarefa de codigo real, prefira essa extensao/CLI ao Code interno do Claude Desktop neste Windows, porque a extensao do VS Code usa o workspace do proprio VS Code e nao depende do VMP do Claude Desktop.
