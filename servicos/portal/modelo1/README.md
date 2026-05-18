# Modelo 1

Landing estatica servida publicamente em `/modelo1/`.

## Origem

O `index.html` atual foi importado de:

`C:\Users\Ronyd\Desktop\testekimi\index.html`

## Deploy

Na VM, o nginx ja aponta `/modelo1/` para:

`/var/www/modelo1/`

Para publicar uma nova versao, copie o conteudo desta pasta para `/var/www/modelo1/` e valide:

```bash
nginx -t
curl -I http://127.0.0.1/modelo1/
curl -I http://redsystems.ddns.net/modelo1/
```
