# Claude Desktop RED

Ferramentas Windows para apontar o Claude Desktop para os gateways RED.

## Arquivos

- `Configurar-Claude-RED-ProxyPro.cmd`: grava a configuracao 3P/gateway do Claude Desktop com `https://redsystems.ddns.net/redproxypro`.
- `Preparar-Claude-RED-Proxy-Normal.ps1`: grava a configuracao 3P/gateway do Claude Desktop com `https://redsystems.ddns.net/proxy`, preservando sessoes e storage local e usando os IDs crus do catalogo publico de `/proxy/v1/models`.
- `Iniciar-Claude-RED-Proxy-Normal-Sem-VMP.cmd`: aplica o preparo do proxy normal completo e abre o Claude RED portatil.
- `Preparar-Claude-RED-ClaudeProxy.ps1`: grava a configuracao 3P/gateway do Claude Desktop com `https://redsystems.ddns.net/redclaudeproxy`.
- `Iniciar-Claude-RED-ClaudeProxy-Sem-VMP.cmd`: aplica o preparo da ponte Claude para o proxy normal e abre o Claude RED portatil.
- `Ativar-VMP-para-Claude-Desktop.cmd`: tenta ativar Virtual Machine Platform em Windows completo.
- `Iniciar-Claude-RED-Sem-VMP.cmd`: abre a copia portatil patchada em `C:\Projetos\ClaudeREDDesktop\app\Claude.exe`.
- `Preparar-Claude-RED-Chat.ps1`: reforca modo chat e sincroniza a lista atual de modelos no `claude_desktop_config.json` e no `configLibrary`.

## Estado atual

O Windows local usado para operacao esta reduzido/capado e falha ao ativar VMP pelo DISM. Por isso o caminho funcional e o launcher sem VMP:

```text
C:\Users\Ronyd\Desktop\Claude RED Sem VMP.cmd
C:\Users\Ronyd\Desktop\Claude RED Proxy Normal.cmd
C:\Users\Ronyd\Desktop\Claude RED ClaudeProxy.cmd
```

Esse modo serve para chat/modelos customizados pelo RED Proxy Pro ou pelo proxy normal. Ele nao entrega workspace/Code real do Claude Desktop, porque essa parte depende do backend local/sandbox que exige VMP.

Os launchers do proxy normal e do RED Claude Proxy nao movem `Local Storage`, `Session Storage`, `IndexedDB`, `WebStorage`, `blob_storage`, `claude-code-sessions` nem `local-agent-mode-sessions`. Eles fazem backup dos JSONs de configuracao e trocam apenas o gateway/modelos.

## Modelos

A lista principal do RED Proxy Pro vem de `/redproxypro/v1/models`.

A lista do proxy normal completo vem de `/proxy/v1/models`, igual ao catalogo publico usado por clientes genericos como Page Assist.

A lista da ponte Claude vem de `/redclaudeproxy/v1/models`, que importa dinamicamente os modelos `claude-red-*` publicados pelo proxy normal.

Sempre que atualizar modelos fixos, revise `Preparar-Claude-RED-Chat.ps1`, `Configurar-Claude-RED-ProxyPro.cmd` e os fallbacks dos scripts do proxy normal. O `Preparar-Claude-RED-ClaudeProxy.ps1` prefere o catalogo vivo de `/redclaudeproxy/v1/models`.
