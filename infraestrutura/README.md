# Infraestrutura

Arquivos para reproduzir uma VM:

```text
systemd/  Units de servicos.
nginx/    Reverse proxy.
docker/   Compose auxiliares.
scripts/  Automacao de instalacao/sync/deploy.
```

Antes de aplicar qualquer unit ou config em uma VM, valide caminhos, usuario, portas e variaveis de ambiente.

## Atalhos públicos

Na VM principal, `infraestrutura/nginx/red-friendly-paths.nginx.conf` expõe os serviços sem precisar digitar porta:

```text
/dashboard   Dashboard RED principal
/redia       Painel REDIA WhatsApp AI
/trader      Painel RED Trader
/proxy       Proxy IA Ollama/NVIDIA
/ollama      Alias do proxy IA
/evolution   Evolution API do WhatsApp
```
