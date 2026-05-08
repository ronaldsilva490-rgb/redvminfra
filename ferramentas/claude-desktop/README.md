# Claude Desktop RED

Ferramentas Windows para apontar o Claude Desktop para os gateways RED.

## Arquivos

- `Configurar-Claude-RED-ProxyPro.cmd`: grava a configuracao 3P/gateway do Claude Desktop com `https://redsystems.ddns.net/redproxypro`.
- `Preparar-Claude-RED-Proxy-Normal.ps1`: grava a configuracao 3P/gateway do Claude Desktop com `https://redsystems.ddns.net/proxy`, preservando sessoes e storage local e usando os IDs crus do catalogo publico de `/proxy/v1/models`.
- `Iniciar-Claude-RED-Proxy-Normal-Sem-VMP.cmd`: aplica o preparo do proxy normal completo e abre o Claude RED portatil.
- `Preparar-Claude-RED-NIM5050.ps1`: grava a configuracao 3P/gateway do Claude Desktop com `https://redsystems.ddns.net:5050`, usando somente o catalogo direto do `rednimclaude`.
- `Iniciar-Claude-RED-NIM5050-Sem-VMP.cmd`: aplica o preparo do gateway NIM direto e abre o Claude RED portatil.
- `Preparar-Claude-RED-Lightning5051.ps1`: grava a configuracao 3P/gateway do Claude Desktop com `https://redsystems.ddns.net:5051`, usando somente os modelos validados do `redlightningclaude`.
- `Iniciar-Claude-RED-Lightning5051-Sem-VMP.cmd`: aplica o preparo do gateway Lightning direto e abre o Claude RED portatil.
- `Preparar-Claude-RED-Alibaba5052.ps1`: grava a configuracao 3P/gateway do Claude Desktop com `https://redsystems.ddns.net:5052`, usando somente os modelos curados do `redalibabaclaude`.
- `Iniciar-Claude-RED-Alibaba5052-Sem-VMP.cmd`: aplica o preparo do gateway Alibaba multi-regiao e abre o Claude RED portatil.
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
C:\Users\Ronyd\Desktop\Claude RED NIM 5050.cmd
C:\Users\Ronyd\Desktop\Claude RED Lightning 5051.cmd
C:\Users\Ronyd\Desktop\Claude RED Alibaba 5052.cmd
```

Esse modo serve para chat/modelos customizados pelo RED Proxy Pro ou pelo proxy normal. Ele nao entrega workspace/Code real do Claude Desktop, porque essa parte depende do backend local/sandbox que exige VMP.

Os launchers do proxy normal e do RED Claude Proxy nao movem `Local Storage`, `Session Storage`, `IndexedDB`, `WebStorage`, `blob_storage`, `claude-code-sessions` nem `local-agent-mode-sessions`. Eles fazem backup dos JSONs de configuracao e trocam apenas o gateway/modelos.

## Modelos

A lista principal do RED Proxy Pro vem de `/redproxypro/v1/models`.

A lista do proxy normal completo vem de `/proxy/v1/models`, igual ao catalogo publico usado por clientes genericos como Page Assist.

A lista da ponte Claude vem de `/redclaudeproxy/v1/models`, que importa dinamicamente os modelos `claude-red-*` publicados pelo proxy normal.

A lista do gateway NIM direto vem de `https://redsystems.ddns.net:5050/v1/models`, sem passar por nginx nem pelo proxy normal.

A lista do gateway Lightning direto vem de `https://redsystems.ddns.net:5051/v1/models`, sem passar por nginx e publicada apenas com os modelos que passaram em texto, stream e tool calling.

A lista do gateway Alibaba direto vem de `https://redsystems.ddns.net:5052/v1/models`, publicada com nomes amigaveis sem `ALI` e filtrando `reasoning_content` para manter a UI do Claude limpa.

Sempre que atualizar modelos fixos, revise `Preparar-Claude-RED-Chat.ps1`, `Configurar-Claude-RED-ProxyPro.cmd` e os fallbacks dos scripts do proxy normal. O `Preparar-Claude-RED-ClaudeProxy.ps1` prefere o catalogo vivo de `/redclaudeproxy/v1/models`.
