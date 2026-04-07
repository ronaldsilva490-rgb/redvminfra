# V10 - TODOS OS PROMPTS

## 🎯 MUDANÇAS DO V9 PARA V10

### ❌ V9 - HARDCODED (ERRADO)
- `NGINX_SPA_CONFIG` constante com `localhost:3000`
- Prompts com `PORT=3000` fixo
- Fallback com porta 3000 hardcoded

### ✅ V10 - DINÂMICO (CORRETO)
- `get_nginx_spa_config(backend_port)` função dinâmica
- Prompts usam `{backend_port}` variável
- Fallback usa porta detectada
- Detecção automática de porta em `_detect_backend_port()`

---

## 📍 DETECÇÃO DE PORTA

```python
def _detect_backend_port(self, backend_path: Path) -> int:
    """Detecta porta do backend lendo package.json ou server.js"""
    
    # 1. Tenta package.json
    # Procura: PORT=4000 ou PORT:4000 nos scripts
    
    # 2. Tenta server.js
    # Procura: PORT = process.env.PORT || 4000
    # Procura: .listen(4000
    
    # 3. Tenta index.js
    # Procura: PORT = process.env.PORT || 5000
    
    # 4. Default: 3000
```

**Exemplos:**
- `apps/teste/server.js` → `PORT || 3000` → **3000**
- `apps/tasks/backend/server.js` → `PORT || 4000` → **4000**
- `apps/notes/backend/server.js` → `PORT || 5000` → **5000**

---

## 📝 PROMPT 1: ANÁLISE INICIAL (IA)

### Fullstack Split (frontend/ + backend/)

```
Analise este projeto e gere um Dockerfile CORRETO.

App: tasks
Porta VM: 2641
Copy Path: tasks
Tipo: fullstack_split

Estrutura Detectada:
- Frontend e backend em pastas separadas
- Backend porta: 4000

🎯 ESTRUTURA: FULLSTACK COM FRONTEND E BACKEND SEPARADOS

⚠️  ATENÇÃO: Você DEVE montar FRONTEND E BACKEND - AMBOS são OBRIGATÓRIOS!

Frontend: tasks/frontend/ (vite)
Backend: tasks/backend/ (express)
Backend Porta: 4000

INSTRUÇÕES OBRIGATÓRIAS:
1. Use multi-stage build com 3 estágios:
   - Stage 1 (frontend-builder): Builda o frontend
     COPY tasks/frontend/ para /app/frontend
     npm install && npm run build
     
   - Stage 2 (backend-prep): Prepara o backend
     COPY tasks/backend/ para /app/backend
     npm install
     
   - Stage 3 (final): nginx + node rodando JUNTOS
     FROM nginx:alpine
     Instalar nodejs npm
     Copiar frontend dist para /usr/share/nginx/html
     Copiar backend para /app
     Criar script /start.sh que roda:
       PORT=4000 node server.js &
       nginx -g 'daemon off;'

2. Nginx DEVE ter proxy /api -> localhost:4000

3. EXPOSE 80 (nginx na frente)

4. NÃO IGNORE O BACKEND! Ele é ESSENCIAL para o app funcionar!

REGRAS CRÍTICAS:
1. NUNCA use RUN echo com \n - use heredoc (cat > arquivo << 'EOF')
2. NUNCA delete configs depois de criar
3. NUNCA ignore frontend OU backend - monte OS DOIS se existirem
4. Para fullstack, nginx na frente (porta 80) + backend atrás (porta 4000)
5. Use supervisor ou script para rodar múltiplos processos se necessário
6. App é INDEPENDENTE - sem monorepo, workspace, turbo
7. Backend porta detectada: 4000 - USE ESSA PORTA!

Responda APENAS JSON:
{"dockerfile": "...", "internal_port": 80, "notes": "..."}
```

### Backend Puro

```
🎯 ESTRUTURA: BACKEND PURO

Tech: express
Backend Porta: 3000

INSTRUÇÕES:
1. FROM node:20-alpine (ou imagem apropriada)
2. COPY teste/ para /app
3. npm install
4. EXPOSE 3000
5. CMD ["node", "server.js"] (ou entry point detectado)

REGRAS CRÍTICAS:
...
7. Backend porta detectada: 3000 - USE ESSA PORTA!
```

---

## 📝 PROMPT 2: CORREÇÃO (IA)

```
CORRIJA este Dockerfile que tem ERROS CRÍTICOS:

- Fullstack sem stage de backend - IA IGNOROU O BACKEND!
- Fullstack sem comando para rodar backend

Dockerfile QUEBRADO:
...

Estrutura: fullstack_split
Frontend: True
Backend: True
Backend Porta: 4000

🚨 ATENÇÃO CRÍTICA - FULLSTACK:
Você DEVE incluir FRONTEND E BACKEND no Dockerfile!

Frontend: tasks/frontend/
Backend: tasks/backend/
Backend Porta: 4000

ESTRUTURA OBRIGATÓRIA:
1. Stage frontend-builder: Builda o frontend
2. Stage backend-prep: Prepara o backend  
3. Stage final: nginx + node rodando JUNTOS

O backend DEVE rodar com: PORT=4000 node server.js &
O nginx DEVE ter proxy /api -> localhost:4000

NÃO IGNORE O BACKEND! Ele é ESSENCIAL!

REGRAS OBRIGATÓRIAS:
1. NUNCA use RUN echo com \n - use heredoc (cat > arquivo << 'EOF')
2. NUNCA delete configs depois de criar
3. Para fullstack: Monte frontend E backend - AMBOS são obrigatórios!
4. Use multi-stage build com stages separados
5. Backend deve rodar na porta 4000
6. Nginx deve ter proxy /api -> localhost:4000

Responda APENAS JSON:
{"dockerfile": "...", "internal_port": 80, "notes": "corrigido com frontend+backend"}
```

---

## 📝 FALLBACK: TEMPLATES DINÂMICOS

### Fullstack Split

```dockerfile
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY tasks/frontend/ .
RUN npm install && npm run build

FROM node:20-alpine AS backend-prep
WORKDIR /app/backend
COPY tasks/backend/ .
RUN npm install

FROM nginx:alpine
RUN apk add --no-cache nodejs npm
RUN cat > /etc/nginx/conf.d/default.conf << 'EOF'
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;
    }
    location /api {
        proxy_pass http://localhost:4000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
EOF
COPY --from=frontend-builder /app/frontend/dist /usr/share/nginx/html
COPY --from=backend-prep /app/backend /app
WORKDIR /app
RUN cat > /start.sh << 'EOF'
#!/bin/sh
cd /app
PORT=4000 node server.js &
nginx -g 'daemon off;'
EOF
RUN chmod +x /start.sh
EXPOSE 80
CMD ["/bin/sh", "/start.sh"]
```

**Nota:** Porta `4000` é injetada dinamicamente via `{backend_port}`

### Backend Puro

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY teste/ .
RUN npm install
EXPOSE 3000
CMD ["node", "server.js"]
```

**Nota:** Porta `3000` é injetada dinamicamente via `{backend_port}`

---

## 🔍 VALIDAÇÃO

```python
def _validate(self, dockerfile: str, structure: dict) -> list:
    # ...
    
    backend_port = structure.get("backend_port", 3000)
    
    if struct_type == "fullstack_split":
        # Verificar se usa a porta correta
        if f'localhost:{backend_port}' not in dockerfile and backend_port != 3000:
            errors.append(f"Fullstack não usa porta detectada {backend_port}")
```

---

## ✅ RESUMO

### ZERO Hardcoding
- ❌ Nenhum `3000` fixo
- ❌ Nenhum `localhost:3000` fixo
- ✅ Tudo detectado dinamicamente

### Detecção Automática
1. Scanner detecta porta em `_detect_backend_port()`
2. Porta vai para `structure["backend_port"]`
3. Prompts usam `{backend_port}` variável
4. Nginx config gerado com `get_nginx_spa_config(backend_port)`
5. Fallback usa porta detectada

### Funciona Para
- `apps/teste` → porta 3000
- `apps/tasks` → porta 4000
- `apps/notes` → porta 5000
- Qualquer outro app com porta diferente
