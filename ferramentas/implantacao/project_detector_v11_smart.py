#!/usr/bin/env python3
"""
Project Detector V11 - SMART & MINIMAL
Detecta TUDO automaticamente e envia só o essencial pra IA.
Validação rigorosa para cada tipo de erro.
"""

import os
import json
import logging
import requests
import re
from pathlib import Path

logger = logging.getLogger(__name__)

AI_BASE_URL = "http://localhost:8080"
AI_MODEL = "qwen3-coder-next"
AI_TIMEOUT = 120
AI_TEMPERATURE = 0.1

EXCLUDE_DIRS = {
    "node_modules", ".git", "dist", "build", "__pycache__",
    ".next", ".nuxt", "target", "vendor", ".cache", "coverage",
    ".turbo", "out", ".expo", ".svelte-kit"
}

# ============ SMART DETECTOR ============

class SmartDetector:
    def __init__(self, project_path: str):
        self.path = Path(project_path)
    
    def analyze(self) -> dict:
        """Detecta TUDO automaticamente"""
        result = {
            "type": "unknown",
            "language": "unknown",
            "framework": None,
            "has_frontend": False,
            "has_backend": False,
            "frontend": {},
            "backend": {},
            "build_info": {}
        }
        
        # Detectar estrutura
        frontend_dir = self.path / "frontend"
        backend_dir = self.path / "backend"
        
        if frontend_dir.is_dir() and backend_dir.is_dir():
            result["type"] = "fullstack_split"
            result["has_frontend"] = True
            result["has_backend"] = True
            result["frontend"] = self._analyze_dir(frontend_dir)
            result["backend"] = self._analyze_dir(backend_dir)
        elif (self.path / "package.json").is_file():
            pkg = self._read_json(self.path / "package.json")
            deps = str(pkg.get("dependencies", {})) + str(pkg.get("devDependencies", {}))
            
            is_frontend = any(x in deps for x in ["vite", "next", "react", "vue", "angular", "svelte"])
            is_backend = any(x in deps for x in ["express", "fastify", "koa", "hapi", "@nestjs"])
            
            if is_frontend and is_backend:
                result["type"] = "fullstack_mixed"
                result["has_frontend"] = True
                result["has_backend"] = True
                result["frontend"] = self._analyze_dir(self.path)
                result["backend"] = self._analyze_dir(self.path)
            elif is_frontend:
                result["type"] = "frontend"
                result["has_frontend"] = True
                result["frontend"] = self._analyze_dir(self.path)
            elif is_backend:
                result["type"] = "backend"
                result["has_backend"] = True
                result["backend"] = self._analyze_dir(self.path)
        elif (self.path / "go.mod").is_file():
            result["type"] = "backend"
            result["language"] = "go"
            result["has_backend"] = True
            result["backend"] = self._analyze_go(self.path)
        elif (self.path / "requirements.txt").is_file() or (self.path / "pyproject.toml").is_file():
            result["type"] = "backend"
            result["language"] = "python"
            result["has_backend"] = True
            result["backend"] = self._analyze_python(self.path)
        
        return result
    
    def _analyze_dir(self, path: Path) -> dict:
        """Analisa um diretório Node.js"""
        info = {
            "language": "nodejs",
            "framework": "unknown",
            "port": 3000,
            "entry": "index.js",
            "build_cmd": None,
            "build_dir": "dist"
        }
        
        pkg_file = path / "package.json"
        if not pkg_file.is_file():
            return info
        
        pkg = self._read_json(pkg_file)
        deps = str(pkg.get("dependencies", {})) + str(pkg.get("devDependencies", {}))
        scripts = pkg.get("scripts", {})
        
        # Detectar framework
        if "next" in deps:
            info["framework"] = "nextjs"
            info["build_cmd"] = "npm run build"
            info["build_dir"] = ".next"
        elif "vite" in deps:
            info["framework"] = "vite"
            info["build_cmd"] = "npm run build"
            info["build_dir"] = "dist"
        elif "@angular" in deps:
            info["framework"] = "angular"
            info["build_cmd"] = "npm run build"
            info["build_dir"] = "dist"
        elif "vue" in deps and "vite" not in deps:
            info["framework"] = "vue"
            info["build_cmd"] = "npm run build"
            info["build_dir"] = "dist"
        elif "express" in deps:
            info["framework"] = "express"
        elif "fastify" in deps:
            info["framework"] = "fastify"
        elif "@nestjs" in deps:
            info["framework"] = "nestjs"
            info["build_cmd"] = "npm run build"
        
        # Detectar porta
        info["port"] = self._detect_port(path)
        
        # Detectar entry point
        if "main" in pkg:
            info["entry"] = pkg["main"]
        elif (path / "server.js").is_file():
            info["entry"] = "server.js"
        elif (path / "index.js").is_file():
            info["entry"] = "index.js"
        elif (path / "src/index.js").is_file():
            info["entry"] = "src/index.js"
        elif (path / "src/main.ts").is_file():
            info["entry"] = "src/main.ts"
        
        return info
    
    def _detect_port(self, path: Path) -> int:
        """Detecta porta do backend"""
        # Tentar package.json
        pkg_file = path / "package.json"
        if pkg_file.is_file():
            try:
                pkg = json.loads(pkg_file.read_text(encoding="utf-8", errors="ignore"))
                scripts = str(pkg.get("scripts", {}))
                m = re.search(r'PORT[=:](\d+)', scripts)
                if m:
                    return int(m.group(1))
            except:
                pass
        
        # Tentar server.js
        for filename in ["server.js", "index.js", "src/server.js", "src/index.js"]:
            file_path = path / filename
            if file_path.is_file():
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    # PORT = process.env.PORT || 4000
                    m = re.search(r'PORT\s*=\s*process\.env\.PORT\s*\|\|\s*(\d+)', content)
                    if m:
                        return int(m.group(1))
                    # .listen(4000
                    m = re.search(r'\.listen\((\d+)', content)
                    if m:
                        return int(m.group(1))
                except:
                    pass
        
        return 3000
    
    def _analyze_go(self, path: Path) -> dict:
        """Analisa projeto Go"""
        info = {
            "language": "go",
            "framework": "standard",
            "port": 8080,
            "entry": "main.go"
        }
        
        # Detectar porta em main.go
        main_file = path / "main.go"
        if main_file.is_file():
            try:
                content = main_file.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r':(\d+)', content)
                if m:
                    info["port"] = int(m.group(1))
            except:
                pass
        
        return info
    
    def _analyze_python(self, path: Path) -> dict:
        """Analisa projeto Python"""
        info = {
            "language": "python",
            "framework": "unknown",
            "port": 8000,
            "entry": "main.py"
        }
        
        # Detectar framework
        req_file = path / "requirements.txt"
        if req_file.is_file():
            try:
                content = req_file.read_text()
                if "fastapi" in content.lower():
                    info["framework"] = "fastapi"
                elif "flask" in content.lower():
                    info["framework"] = "flask"
                elif "django" in content.lower():
                    info["framework"] = "django"
            except:
                pass
        
        # Detectar entry point
        for filename in ["main.py", "app.py", "server.py", "manage.py"]:
            if (path / filename).is_file():
                info["entry"] = filename
                break
        
        return info
    
    def _read_json(self, path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except:
            return {}


# ============ SMART AI ANALYZER ============

class SmartAIAnalyzer:
    def __init__(self, base_url: str = AI_BASE_URL):
        self.base_url = base_url.rstrip("/")
    
    def analyze(self, detection: dict, app_name: str, copy_path: str) -> dict:
        """Gera Dockerfile com IA + validação rigorosa"""
        
        # Tentar IA
        result = self._try_ai(detection, app_name, copy_path)
        
        if not result:
            logger.warning("IA falhou, usando fallback")
            return self._fallback(detection, copy_path)
        
        # Sanitizar
        result["dockerfile"] = self._sanitize(result["dockerfile"])
        
        # Validar
        errors = self._validate(result["dockerfile"], detection)
        
        if not errors:
            logger.info("✅ Dockerfile válido")
            return result
        
        # Corrigir
        logger.warning(f"Erros: {errors}")
        corrected = self._fix(result["dockerfile"], errors, detection, copy_path)
        
        if corrected:
            corrected["dockerfile"] = self._sanitize(corrected["dockerfile"])
            new_errors = self._validate(corrected["dockerfile"], detection)
            
            if not new_errors:
                logger.info("✅ IA corrigiu")
                return corrected
        
        # Fallback
        logger.warning("Usando fallback")
        return self._fallback(detection, copy_path)
    
    def _try_ai(self, detection: dict, app_name: str, copy_path: str) -> dict | None:
        """Prompt CURTO e DIRETO"""
        try:
            prompt = self._build_prompt(detection, app_name, copy_path)
            
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": AI_MODEL,
                    "messages": [
                        {"role": "system", "content": "Especialista Docker. Responda APENAS JSON válido."},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False,
                    "options": {"temperature": AI_TEMPERATURE}
                },
                timeout=AI_TIMEOUT
            )
            
            if resp.status_code != 200:
                return None
            
            content = resp.json().get("message", {}).get("content", "")
            m = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', content, re.DOTALL)
            if m:
                content = m.group(1).strip()
            
            parsed = json.loads(content)
            
            if not parsed.get("dockerfile"):
                return None
            
            return {
                "dockerfile": parsed["dockerfile"],
                "internal_port": parsed.get("internal_port", 80),
                "notes": parsed.get("notes", "")
            }
        
        except Exception as e:
            logger.warning(f"IA falhou: {e}")
            return None
    
    def _build_prompt(self, detection: dict, app_name: str, copy_path: str) -> str:
        """Prompt MÍNIMO - só o essencial"""
        
        dtype = detection["type"]
        
        if dtype == "fullstack_split":
            fe = detection["frontend"]
            be = detection["backend"]
            
            return f"""Gere Dockerfile para: {app_name}

ESTRUTURA: Fullstack separado
- Frontend: {copy_path}/frontend/ ({fe['framework']})
- Backend: {copy_path}/backend/ ({be['framework']}, porta {be['port']})

REGRAS:
1. Multi-stage: frontend-builder, backend-prep, final
2. Final: nginx:alpine + nodejs
3. Nginx proxy /api -> localhost:{be['port']} (SEM barra no final do proxy_pass)
4. Script /start.sh: PORT={be['port']} node {be['entry']} & + nginx
5. EXPOSE 80
6. Use heredoc para configs (cat > arquivo << 'EOF')

JSON: {{"dockerfile": "...", "internal_port": 80}}"""
        
        elif dtype == "frontend":
            fe = detection["frontend"]
            
            return f"""Gere Dockerfile para: {app_name}

ESTRUTURA: Frontend puro
- Tech: {fe['framework']}
- Build: {fe['build_cmd']}
- Dist: {fe['build_dir']}

REGRAS:
1. Multi-stage: builder (node:20-alpine), final (nginx:alpine)
2. Builder: npm install && {fe['build_cmd']}
3. Nginx: servir {fe['build_dir']}, SPA config (try_files)
4. EXPOSE 80

JSON: {{"dockerfile": "...", "internal_port": 80}}"""
        
        elif dtype == "backend":
            be = detection["backend"]
            lang = be["language"]
            
            if lang == "nodejs":
                return f"""Gere Dockerfile para: {app_name}

ESTRUTURA: Backend Node.js
- Framework: {be['framework']}
- Porta: {be['port']}
- Entry: {be['entry']}

REGRAS:
1. FROM node:20-alpine
2. npm install
3. EXPOSE {be['port']}
4. CMD ["node", "{be['entry']}"]

JSON: {{"dockerfile": "...", "internal_port": {be['port']}}}"""
            
            elif lang == "go":
                return f"""Gere Dockerfile para: {app_name}

ESTRUTURA: Backend Go
- Porta: {be['port']}

REGRAS:
1. Multi-stage: builder (golang:alpine), final (alpine)
2. Builder: go build -o main
3. Final: copiar binário, EXPOSE {be['port']}, CMD ["./main"]

JSON: {{"dockerfile": "...", "internal_port": {be['port']}}}"""
            
            elif lang == "python":
                return f"""Gere Dockerfile para: {app_name}

ESTRUTURA: Backend Python
- Framework: {be['framework']}
- Porta: {be['port']}

REGRAS:
1. FROM python:3.11-alpine
2. pip install -r requirements.txt
3. EXPOSE {be['port']}
4. CMD apropriado para {be['framework']}

JSON: {{"dockerfile": "...", "internal_port": {be['port']}}}"""
        
        return "Estrutura não reconhecida"
    
    def _sanitize(self, dockerfile: str) -> str:
        """Remove comandos perigosos"""
        lines = dockerfile.split('\n')
        sanitized = []
        
        for line in lines:
            stripped = line.strip()
            
            # Remove RUN rm de configs
            if stripped.startswith('RUN') and 'rm' in stripped and any(x in stripped for x in ['default.conf', 'nginx.conf']):
                continue
            
            # Remove RUN echo com \n
            if stripped.startswith('RUN') and 'echo' in stripped and '\\n' in stripped:
                continue
            
            sanitized.append(line)
        
        return '\n'.join(sanitized).strip()
    
    def _validate(self, dockerfile: str, detection: dict) -> list:
        """Validação RIGOROSA por tipo"""
        errors = []
        
        if not dockerfile or len(dockerfile) < 20:
            errors.append("Dockerfile vazio")
            return errors
        
        if not re.search(r'^FROM\s+\S+', dockerfile, re.MULTILINE):
            errors.append("Falta FROM")
        
        if 'EXPOSE' not in dockerfile:
            errors.append("Falta EXPOSE")
        
        dtype = detection["type"]
        
        # Validação específica por tipo
        if dtype == "fullstack_split":
            be_port = detection["backend"]["port"]
            
            if 'frontend-builder' not in dockerfile.lower():
                errors.append("Falta stage frontend-builder")
            
            if 'backend-prep' not in dockerfile.lower() and 'backend' not in dockerfile.lower():
                errors.append("Falta stage backend")
            
            if 'node server.js' not in dockerfile and 'node index.js' not in dockerfile:
                errors.append("Backend não está sendo executado")
            
            if '/api' not in dockerfile or 'proxy_pass' not in dockerfile:
                errors.append("Falta proxy /api")
            
            # CRÍTICO: Verificar barra no proxy_pass
            if f'proxy_pass http://localhost:{be_port}/' in dockerfile:
                errors.append(f"proxy_pass com barra no final - vai remover /api! Use: proxy_pass http://localhost:{be_port};")
            
            if f'localhost:{be_port}' not in dockerfile:
                errors.append(f"Porta {be_port} não está sendo usada")
            
            if f'PORT={be_port}' not in dockerfile:
                errors.append(f"Backend não está usando PORT={be_port}")
        
        elif dtype == "frontend":
            if 'nginx' not in dockerfile.lower():
                errors.append("Frontend deve usar nginx")
            
            if 'npm run build' not in dockerfile and 'npm build' not in dockerfile:
                errors.append("Falta build do frontend")
        
        elif dtype == "backend":
            be = detection["backend"]
            lang = be["language"]
            port = be["port"]
            
            if f'EXPOSE {port}' not in dockerfile:
                errors.append(f"Falta EXPOSE {port}")
            
            if lang == "nodejs":
                if 'npm install' not in dockerfile:
                    errors.append("Falta npm install")
                
                if 'CMD' not in dockerfile and 'ENTRYPOINT' not in dockerfile:
                    errors.append("Falta CMD ou ENTRYPOINT")
            
            elif lang == "go":
                if 'go build' not in dockerfile:
                    errors.append("Falta go build")
            
            elif lang == "python":
                if 'pip install' not in dockerfile:
                    errors.append("Falta pip install")
        
        return errors
    
    def _fix(self, broken: str, errors: list, detection: dict, copy_path: str) -> dict | None:
        """Pede IA para corrigir - prompt CURTO"""
        try:
            error_list = "\n".join(f"- {e}" for e in errors)
            
            prompt = f"""CORRIJA este Dockerfile:

ERROS:
{error_list}

Dockerfile quebrado:
```dockerfile
{broken}
```

Tipo: {detection['type']}

REGRAS CRÍTICAS:
1. proxy_pass SEM barra no final
2. Incluir frontend E backend
3. Usar porta detectada: {detection.get('backend', {}).get('port', 3000)}
4. Heredoc para configs

JSON: {{"dockerfile": "...", "internal_port": 80}}"""
            
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": AI_MODEL,
                    "messages": [
                        {"role": "system", "content": "Especialista Docker. Corrija erros. Responda APENAS JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False,
                    "options": {"temperature": 0.05}
                },
                timeout=AI_TIMEOUT
            )
            
            if resp.status_code != 200:
                return None
            
            content = resp.json().get("message", {}).get("content", "")
            m = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', content, re.DOTALL)
            if m:
                content = m.group(1).strip()
            
            parsed = json.loads(content)
            
            if not parsed.get("dockerfile"):
                return None
            
            return {
                "dockerfile": parsed["dockerfile"],
                "internal_port": parsed.get("internal_port", 80),
                "notes": "Corrigido pela IA"
            }
        
        except Exception as e:
            logger.warning(f"Correção falhou: {e}")
            return None
    
    def _fallback(self, detection: dict, copy_path: str) -> dict:
        """Fallback INTELIGENTE por tipo"""
        
        dtype = detection["type"]
        
        if dtype == "fullstack_split":
            fe = detection["frontend"]
            be = detection["backend"]
            
            dockerfile = f"""FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY {copy_path}/frontend/ .
RUN npm install && npm run build

FROM node:20-alpine AS backend-prep
WORKDIR /app/backend
COPY {copy_path}/backend/ .
RUN npm install

FROM nginx:alpine
RUN apk add --no-cache nodejs npm
COPY --from=frontend-builder /app/frontend/{fe['build_dir']} /usr/share/nginx/html
COPY --from=backend-prep /app/backend /app
RUN cat > /etc/nginx/conf.d/default.conf << 'EOF'
server {{
    listen 80;
    root /usr/share/nginx/html;
    index index.html;
    location / {{
        try_files $uri $uri/ /index.html;
    }}
    location /api {{
        proxy_pass http://localhost:{be['port']};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }}
}}
EOF
WORKDIR /app
RUN cat > /start.sh << 'EOF'
#!/bin/sh
PORT={be['port']} node {be['entry']} &
nginx -g 'daemon off;'
EOF
RUN chmod +x /start.sh
EXPOSE 80
CMD ["/start.sh"]"""
            return {"dockerfile": dockerfile, "internal_port": 80, "notes": "Fallback fullstack"}
        
        elif dtype == "frontend":
            fe = detection["frontend"]
            
            dockerfile = f"""FROM node:20-alpine AS builder
WORKDIR /app
COPY {copy_path}/ .
RUN npm install && npm run build

FROM nginx:alpine
RUN cat > /etc/nginx/conf.d/default.conf << 'EOF'
server {{
    listen 80;
    root /usr/share/nginx/html;
    index index.html;
    location / {{
        try_files $uri $uri/ /index.html;
    }}
}}
EOF
COPY --from=builder /app/{fe['build_dir']} /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]"""
            return {"dockerfile": dockerfile, "internal_port": 80, "notes": "Fallback frontend"}
        
        elif dtype == "backend":
            be = detection["backend"]
            lang = be["language"]
            
            if lang == "nodejs":
                dockerfile = f"""FROM node:20-alpine
WORKDIR /app
COPY {copy_path}/ .
RUN npm install
EXPOSE {be['port']}
CMD ["node", "{be['entry']}"]"""
                return {"dockerfile": dockerfile, "internal_port": be['port'], "notes": "Fallback backend nodejs"}
            
            elif lang == "go":
                dockerfile = f"""FROM golang:alpine AS builder
WORKDIR /app
COPY {copy_path}/ .
RUN go build -o main .

FROM alpine
WORKDIR /app
COPY --from=builder /app/main .
EXPOSE {be['port']}
CMD ["./main"]"""
                return {"dockerfile": dockerfile, "internal_port": be['port'], "notes": "Fallback backend go"}
            
            elif lang == "python":
                dockerfile = f"""FROM python:3.11-alpine
WORKDIR /app
COPY {copy_path}/ .
RUN pip install -r requirements.txt
EXPOSE {be['port']}
CMD ["python", "{be['entry']}"]"""
                return {"dockerfile": dockerfile, "internal_port": be['port'], "notes": "Fallback backend python"}
        
        # Fallback genérico
        dockerfile = f"""FROM node:20-alpine
WORKDIR /app
COPY {copy_path}/ .
RUN npm install || true
EXPOSE 3000
CMD ["node", "index.js"]"""
        return {"dockerfile": dockerfile, "internal_port": 3000, "notes": "Fallback genérico"}

# ============ API ============

def analyze_project(project_path: str, app_name: str, base_port: int, copy_path: str = None) -> dict:
    if copy_path is None:
        copy_path = os.path.basename(project_path.rstrip("/\\"))
    
    logger.info(f"🔍 Analisando {app_name}")
    
    detector = SmartDetector(project_path)
    detection = detector.analyze()
    
    logger.info(f"📊 Tipo: {detection['type']}")
    if detection['has_backend']:
        be = detection['backend']
        logger.info(f"🔌 Backend: {be['language']}/{be.get('framework', 'unknown')} porta {be['port']}")
    if detection['has_frontend']:
        fe = detection['frontend']
        logger.info(f"🎨 Frontend: {fe.get('framework', 'unknown')}")
    
    analyzer = SmartAIAnalyzer()
    result = analyzer.analyze(detection, app_name, copy_path)
    
    return result

# ============ CLI ============

if __name__ == "__main__":
    import sys
    import argparse
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    parser = argparse.ArgumentParser(description="Detector V11 - SMART")
    parser.add_argument("project_path", help="Caminho do app")
    parser.add_argument("--name", required=True, help="Nome do app")
    parser.add_argument("--port", type=int, required=True, help="Porta VM")
    parser.add_argument("--copy-path", required=True, help="Path para COPY")
    args = parser.parse_args()
    
    result = analyze_project(args.project_path, args.name, args.port, args.copy_path)
    
    print("\n" + "="*70)
    print(f"🎯 {args.name}")
    print("="*70)
    print(f"Porta: {result['internal_port']}")
    print(f"Notas: {result['notes']}")
    print("\n--- Dockerfile ---")
    print(result["dockerfile"])
    print("\n" + "="*70)
