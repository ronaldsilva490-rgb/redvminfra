#!/usr/bin/env python3
"""Reescreve o arquivo nginx conf da VM com a rota /modelos/ adicionada corretamente."""
import paramiko

HOST = "redsystems.ddns.net"
PORT = 22
USER = "root"
PASSWORD = "2580"

# Conteúdo completo e correto do arquivo
CONTENT = r'''# Include usado dentro do server :80 principal da VM RED Systems.
# Arquitetura consolidada em uma unica VM: tudo aponta para localhost.

location = /dashboard {
    return 301 /dashboard/;
}

location = / {
    root /var/www/red-portal;
    try_files /index.html =404;
}

location /portal-assets/ {
    alias /var/www/red-portal/assets/;
}

location = /modelo1 {
    return 301 /modelo1/;
}

location /modelo1/ {
    alias /var/www/modelo1/;
    index index.html;
    try_files $uri $uri/ /modelo1/index.html;
}

location = /modelo2 {
    return 301 /modelo2/;
}

location /modelo2/ {
    alias /var/www/modelo2/;
    index index.html;
    try_files $uri $uri/ /modelo2/index.html;
}

# Galeria de mockups Total Empresarial (8 modelos)
location = /modelos {
    return 301 /modelos/;
}

location /modelos/ {
    alias /var/www/modelos/;
    index index.html;
    try_files $uri $uri/ /modelos/index.html;
}

location = /msredpdf {
    return 301 /msredpdf/;
}

location /msredpdf/ {
    client_max_body_size 80m;
    proxy_pass http://127.0.0.1:3142/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /msredpdf;
    proxy_buffering off;
    proxy_request_buffering off;
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location /dashboard/ {
    proxy_pass http://127.0.0.1:9001/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /dashboard;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location /hooks/ {
    proxy_pass http://127.0.0.1:9001/hooks/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location = /trader {
    return 301 /trader/;
}

location = /redia {
    return 301 /redia/;
}

location = /proxy {
    return 301 /proxy/;
}

location = /redproxypro {
    return 301 /redproxypro/;
}

location = /redclaudeproxy {
    return 301 /redclaudeproxy/;
}

location = /search {
    return 301 /search/;
}

location = /ollama {
    return 301 /ollama/;
}

location = /rapidleech {
    return 301 /rapidleech/;
}

location = /redseb {
    return 301 /redseb/;
}

location = /redsebia {
    return 301 /redsebia/;
}

location = /download/ {
    return 301 /download;
}

location = /download {
    proxy_pass http://127.0.0.1:2580/download;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /download;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location /download/ {
    rewrite ^/download/(.*)$ /$1 break;
    proxy_pass http://127.0.0.1:2580;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /download;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location /redseb/ {
    rewrite ^/redseb/(.*)$ /$1 break;
    proxy_pass http://127.0.0.1:2580;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /redseb;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location /redsebia/ {
    proxy_pass http://127.0.0.1:3130/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /redsebia;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_buffering off;
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location /trader/ {
    proxy_pass http://127.0.0.1:3100/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /trader;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location /redia/ {
    proxy_pass http://127.0.0.1:3099/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /redia;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_buffering off;
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location = /proxy-lab {
    return 301 /proxy-lab/;
}

location = /proxy-lab/ {
    return 302 /proxy-lab/healthz;
}

location ^~ /proxy-lab/admin/ {
    allow 127.0.0.1;
    allow ::1;
    deny all;
    proxy_pass http://127.0.0.1:8090/admin/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /proxy-lab;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_buffering off;
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location /proxy-lab/ {
    proxy_pass http://127.0.0.1:8090/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /proxy-lab;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_buffering off;
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location /redproxypro/ {
    if ($request_method = OPTIONS) {
        add_header Access-Control-Allow-Origin "*" always;
        add_header Access-Control-Allow-Methods "GET, POST, PUT, PATCH, DELETE, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Authorization, X-API-Key, api-key, apikey, Content-Type, Accept, Origin, X-Requested-With, OpenAI-Beta, Anthropic-Beta, Anthropic-Version" always;
        add_header Access-Control-Max-Age 86400 always;
        add_header Content-Length 0;
        add_header Content-Type text/plain;
        return 204;
    }
    add_header Access-Control-Allow-Origin "*" always;
    add_header Access-Control-Allow-Methods "GET, POST, PUT, PATCH, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Authorization, X-API-Key, api-key, apikey, Content-Type, Accept, Origin, X-Requested-With, OpenAI-Beta, Anthropic-Beta, Anthropic-Version" always;
    add_header Access-Control-Expose-Headers "Content-Type, X-Request-Id, X-RedProxyPro-Key, X-RedProxyPro-Attempts" always;
    proxy_pass http://127.0.0.1:8095/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /redproxypro;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-API-Key $http_x_api_key;
    proxy_set_header api-key $http_api_key;
    proxy_set_header apikey $http_apikey;
    proxy_buffering off;
    proxy_request_buffering off;
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location /redclaudeproxy/ {
    if ($request_method = OPTIONS) {
        add_header Access-Control-Allow-Origin "*" always;
        add_header Access-Control-Allow-Methods "GET, POST, PUT, PATCH, DELETE, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Authorization, X-API-Key, api-key, apikey, Content-Type, Accept, Origin, X-Requested-With, OpenAI-Beta, Anthropic-Beta, Anthropic-Version" always;
        add_header Access-Control-Max-Age 86400 always;
        add_header Content-Length 0;
        add_header Content-Type text/plain;
        return 204;
    }
    add_header Access-Control-Allow-Origin "*" always;
    add_header Access-Control-Allow-Methods "GET, POST, PUT, PATCH, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Authorization, X-API-Key, api-key, apikey, Content-Type, Accept, Origin, X-Requested-With, OpenAI-Beta, Anthropic-Beta, Anthropic-Version" always;
    add_header Access-Control-Expose-Headers "Content-Type, X-Request-Id, X-RedClaudeProxy-Key, X-RedClaudeProxy-Attempts" always;
    proxy_pass http://127.0.0.1:8096/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /redclaudeproxy;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-API-Key $http_x_api_key;
    proxy_set_header api-key $http_api_key;
    proxy_set_header apikey $http_apikey;
    proxy_buffering off;
    proxy_request_buffering off;
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location /search/ {
    proxy_pass http://127.0.0.1:8088;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /search;
    proxy_buffering off;
    proxy_read_timeout 120;
    proxy_send_timeout 120;
}

location = /iq-bridge {
    return 301 /iq-bridge/;
}

location = /iq-bridge/ {
    return 302 /iq-bridge/healthz;
}

location /iq-bridge/ {
    proxy_pass http://127.0.0.1:3115/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_buffering off;
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location /rapidleech/ {
    gzip off;
    add_header X-Accel-Buffering no always;
    proxy_pass http://127.0.0.1:2581/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /rapidleech;
    proxy_buffering off;
    proxy_request_buffering off;
    proxy_max_temp_file_size 0;
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location = /openclaw {
    proxy_pass http://127.0.0.1:18789/openclaw/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /openclaw;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_buffering off;
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location = /openclaw/ {
    return 302 /openclaw/chat?session=main&gatewayUrl=ws://redsystems.ddns.net/openclaw/;
}

location = /openclaw/chat {
    if ($arg_gatewayUrl = "") {
        return 302 /openclaw/chat?session=$arg_session&gatewayUrl=ws://redsystems.ddns.net/openclaw/;
    }
    proxy_pass http://127.0.0.1:18789;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /openclaw;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_buffering off;
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location /openclaw/ {
    proxy_pass http://127.0.0.1:18789;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /openclaw;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_buffering off;
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location /__openclaw__/ {
    proxy_pass http://127.0.0.1:18789;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_buffering off;
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location /proxy/ {
    if ($request_method = OPTIONS) {
        add_header Access-Control-Allow-Origin "*" always;
        add_header Access-Control-Allow-Methods "GET, POST, PUT, PATCH, DELETE, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Authorization, X-API-Key, api-key, apikey, Content-Type, Accept, Origin, X-Requested-With" always;
        add_header Access-Control-Max-Age 86400 always;
        add_header Content-Length 0;
        add_header Content-Type text/plain;
        return 204;
    }
    add_header Access-Control-Allow-Origin "*" always;
    add_header Access-Control-Allow-Methods "GET, POST, PUT, PATCH, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Authorization, X-API-Key, api-key, apikey, Content-Type, Accept, Origin, X-Requested-With" always;
    add_header Access-Control-Expose-Headers "Content-Type, X-Request-Id" always;
    proxy_pass http://127.0.0.1:8080/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-API-Key $http_x_api_key;
    proxy_set_header api-key $http_api_key;
    proxy_set_header apikey $http_apikey;
    proxy_buffering off;
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}

location /ollama/ {
    if ($request_method = OPTIONS) {
        add_header Access-Control-Allow-Origin "*" always;
        add_header Access-Control-Allow-Methods "GET, POST, PUT, PATCH, DELETE, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Authorization, X-API-Key, api-key, apikey, Content-Type, Accept, Origin, X-Requested-With" always;
        add_header Access-Control-Max-Age 86400 always;
        add_header Content-Length 0;
        add_header Content-Type text/plain;
        return 204;
    }
    add_header Access-Control-Allow-Origin "*" always;
    add_header Access-Control-Allow-Methods "GET, POST, PUT, PATCH, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Authorization, X-API-Key, api-key, apikey, Content-Type, Accept, Origin, X-Requested-With" always;
    add_header Access-Control-Expose-Headers "Content-Type, X-Request-Id" always;
    proxy_pass http://127.0.0.1:8080/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-API-Key $http_x_api_key;
    proxy_set_header api-key $http_api_key;
    proxy_set_header apikey $http_apikey;
    proxy_buffering off;
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
}
'''


def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASSWORD)

    # Escrever o arquivo corrigido via SFTP
    sftp = client.open_sftp()
    remote_path = "/etc/nginx/redvm-routes/red-enabled-paths.conf"
    with sftp.open(remote_path, 'w') as f:
        f.write(CONTENT)
    sftp.close()
    print("Arquivo nginx conf reescrito com sucesso.")

    # Testar e recarregar nginx
    stdin, stdout, stderr = client.exec_command("nginx -t && systemctl reload nginx")
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    exit_code = stdout.channel.recv_exit_status()

    print(f"Exit code: {exit_code}")
    if out:
        print(f"STDOUT: {out}")
    if err:
        print(f"STDERR: {err}")

    client.close()

    if exit_code == 0:
        print("Nginx recarregado com sucesso!")
    else:
        print("ERRO ao recarregar nginx!")


if __name__ == "__main__":
    main()
