# Claude Desktop RED

Ferramentas Windows para apontar o Claude Desktop para o RED Proxy Pro.

## Arquivos

- `Configurar-Claude-RED-ProxyPro.cmd`: grava a configuracao 3P/gateway do Claude Desktop com `https://redsystems.ddns.net/redproxypro`.
- `Ativar-VMP-para-Claude-Desktop.cmd`: tenta ativar Virtual Machine Platform em Windows completo.
- `Iniciar-Claude-RED-Sem-VMP.cmd`: abre a copia portatil patchada em `C:\Projetos\ClaudeREDDesktop\app\Claude.exe`.
- `Preparar-Claude-RED-Chat.ps1`: reforca modo chat e sincroniza a lista atual de modelos no `claude_desktop_config.json` e no `configLibrary`.

## Estado atual

O Windows local usado para operacao esta reduzido/capado e falha ao ativar VMP pelo DISM. Por isso o caminho funcional e o launcher sem VMP:

```text
C:\Users\Ronyd\Desktop\Claude RED Sem VMP.cmd
```

Esse modo serve para chat/modelos customizados pelo RED Proxy Pro. Ele nao entrega workspace/Code real do Claude Desktop, porque essa parte depende do backend local/sandbox que exige VMP.

## Modelos

A lista vem do RED Proxy Pro e deve ficar igual a `/redproxypro/v1/models`. O preparo local grava 19 modelos em ordem alfabetica, incluindo `anthropic/claude-sonnet-4.6`, `openai/gpt-5.5`, `moonshotai/kimi-k2.6`, `zai/glm-5.1` e os novos candidatos solicitados.

Sempre que atualizar modelos no proxy, atualize tambem `Preparar-Claude-RED-Chat.ps1` e `Configurar-Claude-RED-ProxyPro.cmd`.
