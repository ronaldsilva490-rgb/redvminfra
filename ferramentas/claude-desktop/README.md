# Claude Desktop RED

Ferramentas Windows para apontar o Claude Desktop para o RED Proxy Pro.

## Arquivos

- `Configurar-Claude-RED-ProxyPro.cmd`: grava a configuracao 3P/gateway do Claude Desktop com `https://redsystems.ddns.net/redproxypro`.
- `Preparar-Claude-RED-Proxy-Normal.ps1`: grava a configuracao 3P/gateway do Claude Desktop com `https://redsystems.ddns.net/proxy`, preservando sessoes e storage local.
- `Iniciar-Claude-RED-Proxy-Normal-Sem-VMP.cmd`: aplica o preparo do proxy normal e abre o Claude RED portatil.
- `Ativar-VMP-para-Claude-Desktop.cmd`: tenta ativar Virtual Machine Platform em Windows completo.
- `Iniciar-Claude-RED-Sem-VMP.cmd`: abre a copia portatil patchada em `C:\Projetos\ClaudeREDDesktop\app\Claude.exe`.
- `Preparar-Claude-RED-Chat.ps1`: reforca modo chat e sincroniza a lista atual de modelos no `claude_desktop_config.json` e no `configLibrary`.

## Estado atual

O Windows local usado para operacao esta reduzido/capado e falha ao ativar VMP pelo DISM. Por isso o caminho funcional e o launcher sem VMP:

```text
C:\Users\Ronyd\Desktop\Claude RED Sem VMP.cmd
C:\Users\Ronyd\Desktop\Claude RED Proxy Normal.cmd
```

Esse modo serve para chat/modelos customizados pelo RED Proxy Pro ou pelo proxy normal. Ele nao entrega workspace/Code real do Claude Desktop, porque essa parte depende do backend local/sandbox que exige VMP.

O launcher do proxy normal nao move `Local Storage`, `Session Storage`, `IndexedDB`, `WebStorage`, `blob_storage`, `claude-code-sessions` nem `local-agent-mode-sessions`. Ele faz backup dos JSONs de configuracao e troca apenas o gateway/modelos.

## Modelos

A lista vem do RED Proxy Pro e deve ficar igual a `/redproxypro/v1/models`. O preparo local grava 19 modelos em ordem alfabetica, incluindo `anthropic/claude-sonnet-4.6`, `openai/gpt-5.5`, `moonshotai/kimi-k2.6`, `zai/glm-5.1` e os novos candidatos solicitados.

Sempre que atualizar modelos no proxy, atualize tambem `Preparar-Claude-RED-Chat.ps1` e `Configurar-Claude-RED-ProxyPro.cmd`.
