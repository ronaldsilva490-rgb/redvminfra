# Infraestrutura

Arquivos para reproduzir uma VM:

```text
systemd/  Units de servicos.
nginx/    Reverse proxy.
docker/   Compose auxiliares.
scripts/  Automacao de instalacao/sync/deploy.
```

Antes de aplicar qualquer unit ou config em uma VM, valide caminhos, usuario, portas e variaveis de ambiente.
