# Site Esports Teste

Projeto estatico publicado na VM RED Systems em `/teste/`.

## Estrutura

```text
teste/
  index.html
  src/
```

## Publicacao nginx

```nginx
location = /teste {
    return 301 /teste/;
}

location /teste/ {
    alias /var/www/teste/;
    index index.html;
    try_files $uri $uri/ /teste/index.html;
}
```

## Deploy na VM

Arquivos sincronizados para `/var/www/teste/`.

Validacao:

```bash
nginx -t
systemctl reload nginx
curl -I http://127.0.0.1/teste/
curl -I https://redsystems.ddns.net/teste/
```

## Observacao

O projeto usa React, ReactDOM e Babel via CDN diretamente no navegador, entao nao precisa build nem runtime Node na VM.
