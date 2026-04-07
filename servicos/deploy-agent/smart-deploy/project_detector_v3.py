#!/usr/bin/env python3
"""
Project Detector v3 — AI-Powered Infrastructure Analyzer
Escaneia o projeto, coleta contexto e usa IA para decidir a infraestrutura Docker ideal.
Sem templates estáticos. Sem lógica Docker interna. Só análise e inferência.
"""

import os
import json
import logging
import requests
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# ============ CONSTANTES ============

AI_BASE_URL = "http://localhost:8080"
AI_PRIMARY_MODEL = "qwen3-coder-next"
AI_FALLBACK_MODEL = "qwen3-coder-next"  # Mesmo modelo, segunda tentativa sem format schema
AI_TIMEOUT = 120
AI_TEMPERATURE = 0.2

MAX_FILE_BYTES = 8 * 1024  # 8KB por arquivo de config
MAX_TREE_DEPTH = 3

EXCLUDE_DIRS = {
    "node_modules", ".git", "dist", "build", "__pycache__",
    ".next", ".nuxt", "target", "vendor", ".cache", "coverage",
    ".turbo", "out", ".expo", ".svelte-kit"
}

# Arquivos de configuração que a IA precisa ver
CONFIG_FILES = [
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "go.mod",
    "go.sum",
    "Cargo.toml",
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "composer.json",
    "Gemfile",
    "pom.xml",
    "build.gradle",
    "tsconfig.json",
    "vite.config.ts",
    "vite.config.js",
    "next.config.js",
    "next.config.ts",
    "nuxt.config.ts",
    "svelte.config.js",
    "astro.config.mjs",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".env.example",
    ".env.sample",
    "nginx.conf",
    "Caddyfile",
    "Makefile",
    ".node-version",
    ".nvmrc",
    "prisma/schema.prisma",
]

# JSON Schema que a IA deve retornar — sem enums para não confundir modelos pequenos
# A normalização de valores é feita no _validate()
AI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "project_type": {"type": "string"},
        "language": {"type": "string"},
        "framework": {"type": "string"},
        "runtime": {"type": "string"},
        "dockerfile": {"type": "string"},
        "internal_port": {"type": "integer"},
        "start_command": {"type": "string"},
        "build_command": {"type": "string"},
        "env_vars": {
            "type": "object",
            "additionalProperties": {"type": "string"}
        },
        "health_check": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "interval_seconds": {"type": "integer"},
                "timeout_seconds": {"type": "integer"},
                "start_period_seconds": {"type": "integer"}
            }
        },
        "notes": {"type": "string"},
        "depends_on": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": [
        "project_type", "language", "framework", "runtime",
        "dockerfile", "internal_port"
    ]
}

# ============ PROJECT SCANNER ============

class ProjectScanner:
    """
    Escaneia a pasta do projeto e coleta contexto para a IA.
    Zero lógica de infraestrutura — só leitura de arquivos.
    """

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)

    def scan(self) -> dict:
        """
        Retorna:
          - file_tree: árvore de diretórios (max depth 3, sem pastas excluídas)
          - config_files: conteúdo dos arquivos de config encontrados
          - language_hints: extensões de arquivo mais frequentes
          - existing_dockerfile: conteúdo do Dockerfile se existir
        """
        file_tree = self._build_tree(self.project_path, depth=0)
        config_contents = self._collect_configs()
        language_hints = self._detect_extensions()
        existing_dockerfile = config_contents.pop("Dockerfile", None)

        return {
            "file_tree": file_tree,
            "config_files": config_contents,
            "language_hints": language_hints,
            "existing_dockerfile": existing_dockerfile,
        }

    def _build_tree(self, path: Path, depth: int) -> list:
        if depth > MAX_TREE_DEPTH:
            return []
        entries = []
        try:
            for item in sorted(path.iterdir()):
                if item.is_dir():
                    if item.name in EXCLUDE_DIRS or item.name.startswith("."):
                        continue
                    children = self._build_tree(item, depth + 1)
                    entries.append({"name": item.name + "/", "children": children})
                else:
                    entries.append({"name": item.name})
        except PermissionError:
            pass
        return entries

    def _collect_configs(self) -> dict:
        found = {}
        for cfg in CONFIG_FILES:
            cfg_path = self.project_path / cfg
            if cfg_path.is_file():
                try:
                    content = cfg_path.read_text(encoding="utf-8", errors="replace")
                    if len(content) > MAX_FILE_BYTES:
                        content = content[:MAX_FILE_BYTES] + "\n... (truncated)"
                    found[cfg] = content
                except Exception:
                    pass
        return found

    def _detect_extensions(self) -> dict:
        counts = {}
        try:
            for root, dirs, files in os.walk(self.project_path):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
                for f in files:
                    ext = Path(f).suffix.lower()
                    if ext:
                        counts[ext] = counts.get(ext, 0) + 1
        except Exception:
            pass
        # Retorna top 10 extensões
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10])


# ============ AI ANALYZER ============

class AIAnalyzer:
    """
    Envia contexto do projeto para a IA e retorna config de infraestrutura.
    Tenta modelo primário, depois fallback. Schema JSON enforced pelo Ollama.
    """

    def __init__(self, base_url: str = AI_BASE_URL):
        self.base_url = base_url.rstrip("/")

    def analyze(self, scan_result: dict, app_name: str, base_port: int, copy_path: str = ".") -> dict | None:
        """
        Retorna dict com toda a config de infraestrutura, ou None se ambos os modelos falharem.
        copy_path: caminho relativo dentro do repo para o COPY no Dockerfile (ex: apps/driver)
        Tentativa 1: modelo primário COM format schema
        Tentativa 2: mesmo modelo SEM format schema (mais flexível)
        """
        self._copy_path = copy_path
        prompt = self._build_prompt(scan_result, app_name, base_port, copy_path)

        # Tentativa 1: com format schema (structured output)
        result = self._call_model(AI_PRIMARY_MODEL, prompt, use_format=True)
        if result:
            logger.info(f"IA ({AI_PRIMARY_MODEL}) gerou config para {app_name} (structured)")
            return result
        logger.warning(f"Tentativa 1 (structured) falhou para {app_name}")

        # Tentativa 2: sem format schema (modelo retorna JSON livre, mais confiável)
        result = self._call_model(AI_FALLBACK_MODEL, prompt, use_format=False)
        if result:
            logger.info(f"IA ({AI_FALLBACK_MODEL}) gerou config para {app_name} (freeform)")
            return result
        logger.warning(f"Tentativa 2 (freeform) falhou para {app_name}")

        return None

    def _build_prompt(self, scan_result: dict, app_name: str, base_port: int, copy_path: str) -> str:
        tree_str = self._render_tree(scan_result["file_tree"])

        configs_str = ""
        for filename, content in scan_result["config_files"].items():
            configs_str += f"\n=== {filename} ===\n{content}\n"

        if scan_result.get("existing_dockerfile"):
            configs_str += f"\n=== Dockerfile (existente, usar como referência) ===\n{scan_result['existing_dockerfile']}\n"

        hints = scan_result.get("language_hints", {})
        hints_str = ", ".join(f"{ext}({n})" for ext, n in hints.items()) if hints else "não detectado"

        # Monorepo context — so incluir se o app usa workspace:* (Node.js monorepo deps)
        monorepo = scan_result.get("monorepo", {})
        monorepo_str = ""
        # Verificar se o package.json do app tem "workspace:" nas deps
        app_pkg = scan_result.get("config_files", {}).get("package.json", "")
        uses_workspace = "workspace:" in app_pkg
        if monorepo and uses_workspace:
            pm = monorepo.get("package_manager", "npm")
            lockfile = monorepo.get("lockfile", "")
            pkgs = monorepo.get("workspace_packages", [])
            pkg_list = ", ".join(p["name"] for p in pkgs) if pkgs else "nenhum"

            monorepo_str = f"""
## CONTEXTO MONOREPO (CRÍTICO)
Este projeto faz parte de um monorepo com workspaces.
- Package manager: {pm}
- Lockfile no root: {lockfile}
- Packages compartilhados: {pkg_list}
"""
            if monorepo.get("root_package_json"):
                monorepo_str += f"\n=== ROOT package.json ===\n{monorepo['root_package_json']}\n"
            if monorepo.get("pnpm_workspace_yaml"):
                monorepo_str += f"\n=== pnpm-workspace.yaml ===\n{monorepo['pnpm_workspace_yaml']}\n"
            if monorepo.get("turbo_json"):
                monorepo_str += f"\n=== turbo.json ===\n{monorepo['turbo_json']}\n"

        return f"""Você é um especialista em DevOps e Docker. Analise o projeto abaixo e gere a configuração de infraestrutura ideal.

# Projeto: {app_name}
# Porta externa do host: {base_port}
# Path do projeto no repo: {copy_path}

## Estrutura de arquivos do app:
{tree_str}

## Extensões mais frequentes: {hints_str}

## Arquivos de configuração do app:
{configs_str}
{monorepo_str}

## Instruções obrigatórias para o Dockerfile:
0. IMPORTANTE: Se o app é Python, Go, Rust, PHP ou Ruby, ele é INDEPENDENTE.
   NÃO instale pnpm, npm, node, corepack, ou dependências JavaScript.
   Ignore completamente o contexto de monorepo Node.js. Trate o app isoladamente.
   Use APENAS o runtime da linguagem do app.
1. Use multi-stage builds quando houver etapa de build (ex: npm run build)
2. Use imagens base alpine ou slim (ex: node:20-alpine, python:3.12-slim)
3. NUNCA use dev servers em produção (nada de vite dev, vite preview, next dev)
4. O Dockerfile será executado com `docker build` no ROOT do repo (não dentro de {copy_path})
5. Detecte a porta que a aplicação REALMENTE escuta em produção.
   - Para frontends com nginx: internal_port = 80 (nginx default listen)
   - Para backends Node.js: procure em server.listen(), variável PORT, etc.
   - Portas de dev server (vite dev port, etc.) NÃO são portas de produção
   - Se não conseguir detectar, use 3000 como fallback
   - O EXPOSE no Dockerfile DEVE usar essa mesma porta
6. Inclua HEALTHCHECK no Dockerfile usando a porta de produção
7. Para apps frontend compiladas (Vite, Next.js estático, React):
   - Use nginx:alpine no stage final
   - COPIE os arquivos de dist para /usr/share/nginx/html
   - EXPOSE 80, internal_port = 80
   - Gere a config do nginx INLINE com RUN echo '...' > /etc/nginx/conf.d/default.conf
   - NUNCA tente COPY de nginx.conf do projeto — ele pode não existir
   - Ignore o outDir customizado do vite.config — no Docker o build output fica em /app/{copy_path}/dist
   - Exemplo de nginx config para SPA: server {{ listen 80; root /usr/share/nginx/html; index index.html; location / {{ try_files $uri $uri/ /index.html; }} }}
8. NUNCA use COPY para copiar arquivos que podem não existir no projeto (nginx.conf, .env, etc.)
   Se precisar de um arquivo de configuração, gere-o inline com RUN echo ou heredoc.
9. Para Node.js: use pnpm se pnpm-lock.yaml existir, yarn se yarn.lock, npm caso contrário
10. Inclua apenas ENV vars essenciais — DATABASE_URL e NODE_ENV serão injetados externamente
11. Se o projeto usa dependências "workspace:*" (monorepo):
    - WORKDIR /app (sempre do root)
    - COPIE: package.json, lockfile, pnpm-workspace.yaml, turbo.json PRIMEIRO
    - COPIE packages/ inteiro (dependências compartilhadas)
    - COPIE {copy_path}/ inteiro
    - RUN corepack enable pnpm && pnpm install --frozen-lockfile (do root!)
    - Se turbo.json existir, use turbo para build:
      pnpm turbo build --filter=NOME_DO_PACKAGE
      ATENÇÃO: o filtro do turbo usa o NOME do package (campo "name" do package.json do app),
      NÃO o path da pasta. Ex: se package.json tem "name": "@tapp/driver", use --filter=@tapp/driver
      Turbo resolve automaticamente a ordem de build das dependências (^build)
    - Se turbo.json NÃO existir: pnpm --filter ./{copy_path} build
    - NUNCA use npm install isolado — workspace:* só funciona com pnpm
    - NUNCA mude WORKDIR para dentro do app antes do install — pnpm install DEVE rodar do root
    - Em multi-stage builds, CADA stage que roda pnpm ou turbo PRECISA ter o package.json do root
      Copie package.json e lockfile em TODOS os stages que precisam dele

Responda APENAS com o JSON estruturado. Nenhum texto adicional.
Use EXATAMENTE estes nomes de campo: project_type, language, framework, runtime, dockerfile, internal_port, start_command, build_command, env_vars, health_check, notes, depends_on."""

    def _render_tree(self, tree: list, prefix: str = "") -> str:
        lines = []
        for i, entry in enumerate(tree):
            is_last = i == len(tree) - 1
            connector = "└── " if is_last else "├── "
            lines.append(prefix + connector + entry["name"])
            if "children" in entry:
                extension = "    " if is_last else "│   "
                lines.append(self._render_tree(entry["children"], prefix + extension))
        return "\n".join(lines)

    @staticmethod
    def _strip_markdown(content: str) -> str:
        """Remove markdown code fences da resposta da IA."""
        import re
        content = content.strip()
        # Remove ```json ... ``` ou ``` ... ```
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', content, re.DOTALL)
        if m:
            return m.group(1).strip()
        # Remove leading/trailing ``` sem language tag
        if content.startswith('```'):
            content = content[3:]
        if content.endswith('```'):
            content = content[:-3]
        return content.strip()

    def _call_model(self, model: str, prompt: str, use_format: bool = True) -> dict | None:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Você é um especialista em DevOps Docker. "
                        "Responda APENAS com JSON válido. Sem texto adicional, sem markdown, sem explicações. "
                        "Os campos obrigatórios são: project_type, language, framework, runtime, "
                        "dockerfile, internal_port, start_command, build_command, env_vars, "
                        "health_check, notes, depends_on."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "stream": False,
            "options": {
                "temperature": AI_TEMPERATURE,
                "num_predict": 4096,
            },
        }

        # Apenas usar format schema na primeira tentativa
        if use_format:
            payload["format"] = AI_RESPONSE_SCHEMA

        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=AI_TIMEOUT
            )
            if resp.status_code != 200:
                logger.warning(f"IA retornou HTTP {resp.status_code} com modelo {model}")
                return None

            data = resp.json()
            content = data.get("message", {}).get("content", "")
            if not content:
                logger.warning(f"IA retornou conteúdo vazio com modelo {model}")
                return None

            # Strip markdown fences caso o modelo ignore o format param
            content = self._strip_markdown(content)
            logger.info(f"Resposta da IA ({model}): {content[:200]}...")

            parsed = json.loads(content)
            return self._validate(parsed)

        except requests.exceptions.Timeout:
            logger.warning(f"Timeout ({AI_TIMEOUT}s) com modelo {model}")
            return None
        except requests.exceptions.ConnectionError:
            logger.warning(f"Proxy IA indisponível ({self.base_url})")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"JSON inválido da IA ({model}): {e} — conteúdo: {content[:300]}")
            return None
        except Exception as e:
            logger.warning(f"Erro inesperado com modelo {model}: {e}")
            return None

    @staticmethod
    def _normalize_enum(value: str, valid_values: list, default: str) -> str:
        """Normaliza valor da IA para um dos valores válidos do enum."""
        if not value or not isinstance(value, str):
            return default
        value_lower = value.lower().strip()

        # Match exato
        if value_lower in valid_values:
            return value_lower

        # Match parcial — ex: "Vite React" -> "frontend", "Express API" -> "backend"
        type_keywords = {
            "frontend": ["frontend", "vite", "react", "vue", "angular", "svelte", "static", "spa", "ui"],
            "backend": ["backend", "api", "server", "express", "fastify", "gin", "flask", "django", "spring"],
            "fullstack": ["fullstack", "full-stack", "full stack", "monolith"],
            "api": ["api", "rest", "graphql", "grpc"],
            "static": ["static", "html", "landing"],
        }
        lang_keywords = {
            "typescript": ["typescript", "ts"],
            "javascript": ["javascript", "js", "node"],
            "python": ["python", "py"],
            "go": ["go", "golang"],
            "rust": ["rust"],
            "php": ["php", "laravel"],
            "ruby": ["ruby", "rails"],
            "java": ["java", "spring", "kotlin"],
        }
        runtime_keywords = {
            "node": ["node", "npm", "pnpm", "yarn", "bun"],
            "nginx": ["nginx", "static"],
            "python": ["python", "pip", "uvicorn", "gunicorn"],
            "go": ["go", "golang"],
            "rust": ["rust", "cargo"],
            "php": ["php", "composer"],
            "ruby": ["ruby", "gem", "bundle"],
            "java": ["java", "maven", "gradle"],
        }

        # Escolher keyword map baseado nos valid_values
        keyword_map = {}
        if "frontend" in valid_values:
            keyword_map = type_keywords
        elif "typescript" in valid_values:
            keyword_map = lang_keywords
        elif "nginx" in valid_values:
            keyword_map = runtime_keywords

        for valid, keywords in keyword_map.items():
            if valid in valid_values:
                for kw in keywords:
                    if kw in value_lower:
                        return valid

        logger.warning(f"Não foi possível normalizar '{value}' para {valid_values}, usando default '{default}'")
        return default

    @staticmethod
    def _infer_from_dockerfile(dockerfile: str) -> dict:
        """Infere campos ausentes analisando o Dockerfile gerado."""
        inferred = {}
        df_lower = dockerfile.lower()

        # Inferir runtime
        if "nginx" in df_lower and ("dist" in df_lower or "html" in df_lower):
            inferred["project_type"] = "frontend"
            inferred["runtime"] = "nginx"
        elif "node:" in df_lower or "pnpm" in df_lower or "npm" in df_lower:
            inferred["runtime"] = "node"
        elif "python:" in df_lower or "pip" in df_lower:
            inferred["runtime"] = "python"
        elif "golang:" in df_lower or "go build" in df_lower:
            inferred["runtime"] = "go"
        elif "rust:" in df_lower or "cargo" in df_lower:
            inferred["runtime"] = "rust"
        elif "php:" in df_lower:
            inferred["runtime"] = "php"

        # Inferir linguagem
        if "typescript" in df_lower or "tsx" in df_lower or "tsconfig" in df_lower:
            inferred["language"] = "typescript"
        elif "node:" in df_lower or "npm" in df_lower:
            inferred["language"] = "javascript"
        elif "python:" in df_lower:
            inferred["language"] = "python"
        elif "golang:" in df_lower:
            inferred["language"] = "go"
        elif "rust:" in df_lower:
            inferred["language"] = "rust"

        # Inferir porta do EXPOSE
        import re
        expose_match = re.search(r'EXPOSE\s+(\d+)', dockerfile)
        if expose_match:
            port = int(expose_match.group(1))
            if 1 <= port <= 65535:
                inferred["internal_port"] = port

        return inferred

    def _sanitize_dockerfile(self, dockerfile: str, copy_path: str) -> str:
        """Corrige problemas comuns em Dockerfiles gerados pela IA."""
        import re

        lines = dockerfile.split('\n')
        sanitized = []
        for line in lines:
            stripped = line.strip()

            # 1. Remove COPY de arquivos que podem não existir (nginx.conf, .env, etc)
            if stripped.startswith('COPY') and '--from=' not in stripped:
                if any(f in stripped for f in ['nginx.conf', '.env', 'Caddyfile', 'docker-compose']):
                    logger.warning(f"Sanitize: removido COPY suspeito: {stripped}")
                    continue

            sanitized.append(line)

        result = '\n'.join(sanitized)

        # 2. Fix turbo filter: path -> package name
        turbo_path_match = re.search(r'--filter[= ]apps/(\w+)', result)
        if turbo_path_match:
            app_folder = turbo_path_match.group(1)
            pkg_name = self._get_package_name(copy_path)
            if pkg_name:
                result = result.replace(turbo_path_match.group(0), f"--filter={pkg_name}")
                logger.info(f"Sanitize: turbo filter -> --filter={pkg_name}")

        # 3. Fix build output path para frontends com vite outDir customizado
        #    Vite pode fazer build para ../api/public/nome em vez de dist/
        app_name = os.path.basename(copy_path.rstrip('/'))
        real_out = self._detect_vite_outdir(copy_path, app_name)
        if real_out:
            # Substituir qualquer COPY --from=builder que referencia /dist pelo path real
            wrong_paths = [
                f'/app/{copy_path}/dist',
                f'/app/apps/{app_name}/dist',
            ]
            for wrong in wrong_paths:
                if wrong in result:
                    result = result.replace(wrong, real_out)
                    logger.info(f"Sanitize: output path {wrong} -> {real_out}")

        # 4. Se tem nginx mas não tem config SPA, adicionar
        if 'nginx:alpine' in result.lower() and '/etc/nginx/conf.d/' not in result:
            nginx_conf = (
                "RUN echo 'server { listen 80; root /usr/share/nginx/html; "
                "index index.html; location / { try_files $uri $uri/ /index.html; } }' "
                "> /etc/nginx/conf.d/default.conf"
            )
            result = re.sub(r'(EXPOSE\s+\d+)', f'{nginx_conf}\n\\1', result, count=1)

        # 5. Fix multi-stage que usa pnpm/turbo sem package.json do root
        #    Se algum stage tem "RUN pnpm" mas não tem "COPY package.json",
        #    adicionar o COPY antes do RUN
        stages = re.split(r'(FROM\s+\S+)', result)
        fixed_stages = []
        for i, stage in enumerate(stages):
            if 'pnpm' in stage and 'turbo' in stage and 'COPY package.json' not in stage and 'COPY --from=' in stage:
                # Stage de build sem root package.json — injetar antes do primeiro RUN pnpm
                inject = "COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json ./\n"
                stage = re.sub(r'(RUN\s+pnpm)', inject + r'\1', stage, count=1)
                logger.info("Sanitize: injetado package.json em stage de build")
            fixed_stages.append(stage)
        result = ''.join(fixed_stages)

        return result

    def _get_package_name(self, copy_path: str) -> str | None:
        """Lê o campo 'name' do package.json do app."""
        import json as _json
        for base in ["/root/Tapp", "."]:
            p = os.path.join(base, copy_path, "package.json")
            try:
                if os.path.isfile(p):
                    with open(p, 'r') as f:
                        return _json.load(f).get("name")
            except Exception:
                pass
        return None

    def _detect_vite_outdir(self, copy_path: str, app_name: str) -> str | None:
        """Detecta o outDir real do vite.config se existir."""
        import re
        for base in ["/root/Tapp", "."]:
            for cfg_name in ["vite.config.ts", "vite.config.js"]:
                cfg_path = os.path.join(base, copy_path, cfg_name)
                try:
                    if os.path.isfile(cfg_path):
                        with open(cfg_path, 'r') as f:
                            content = f.read()
                        m = re.search(r"outDir\s*:\s*['\"]([^'\"]+)['\"]", content)
                        if m:
                            out_dir = m.group(1)
                            # Resolver path relativo: ../api/public/driver -> apps/api/public/driver
                            if out_dir.startswith('..'):
                                # Relativo a apps/{nome} -> resolver
                                parts = copy_path.rstrip('/').split('/')
                                # Ex: copy_path=apps/driver, outDir=../api/public/driver
                                # -> apps + driver + ../api/public/driver = apps/api/public/driver
                                resolved = os.path.normpath(os.path.join(copy_path, out_dir))
                                return f"/app/{resolved}"
                            elif not out_dir.startswith('/'):
                                return f"/app/{copy_path}/{out_dir}"
                except Exception:
                    pass
        return None

    @staticmethod
    def _normalize_field_names(result: dict) -> dict:
        """Mapeia nomes alternativos de campos para os nomes esperados."""
        aliases = {
            "dockerfile": ["dockerfile_content", "docker_file", "Dockerfile", "dockerFile"],
            "project_type": ["project_name", "type", "projectType", "app_type"],
            "internal_port": ["port", "app_port", "listen_port", "container_port"],
            "start_command": ["start_cmd", "cmd", "command", "run_command", "startCommand"],
            "build_command": ["build_cmd", "build", "buildCommand"],
            "health_check": ["healthcheck", "health", "healthCheck"],
            "env_vars": ["environment", "env", "envVars", "environment_variables"],
            "depends_on": ["dependencies", "deps", "dependsOn"],
        }
        for canonical, alt_names in aliases.items():
            if canonical not in result or result[canonical] is None:
                for alt in alt_names:
                    if alt in result and result[alt] is not None:
                        result[canonical] = result[alt]
                        break
        return result

    def _validate(self, result: dict) -> dict | None:
        # Normalizar nomes de campos (IA pode usar nomes diferentes)
        result = self._normalize_field_names(result)

        # O único campo realmente obrigatório é o dockerfile
        if not isinstance(result.get("dockerfile"), str) or len(result.get("dockerfile", "")) < 20:
            logger.warning("Dockerfile gerado pela IA é muito curto ou inválido")
            return None

        # Sanitizar Dockerfile — corrigir problemas comuns da IA
        result["dockerfile"] = self._sanitize_dockerfile(
            result["dockerfile"], getattr(self, '_copy_path', '.')
        )

        # Inferir campos ausentes do Dockerfile
        inferred = self._infer_from_dockerfile(result["dockerfile"])
        for key, val in inferred.items():
            if not result.get(key) or result.get(key) in (None, "", "other", "unknown"):
                result[key] = val
                logger.info(f"Campo '{key}' inferido do Dockerfile: {val}")

        # Preencher campos ausentes com defaults em vez de rejeitar
        result.setdefault("project_type", "backend")
        result.setdefault("language", "other")
        result.setdefault("runtime", "other")
        result.setdefault("framework", "unknown")
        result.setdefault("internal_port", 3000)
        result.setdefault("start_command", "")
        result.setdefault("build_command", "")
        result.setdefault("env_vars", {})
        result.setdefault("health_check", {})
        result.setdefault("notes", "")
        result.setdefault("depends_on", [])

        # Normalizar enums — aceitar valores aproximados da IA
        valid_types = ["frontend", "backend", "fullstack", "api", "static", "build-only"]
        valid_langs = ["javascript", "typescript", "go", "rust", "python", "php", "ruby", "java", "other"]
        valid_runtimes = ["node", "go", "python", "rust", "php", "ruby", "java", "nginx", "other"]

        result["project_type"] = self._normalize_enum(result["project_type"], valid_types, "backend")
        result["language"] = self._normalize_enum(result["language"], valid_langs, "other")
        result["runtime"] = self._normalize_enum(result["runtime"], valid_runtimes, "other")

        # Normalizar porta
        if not isinstance(result["internal_port"], int):
            try:
                result["internal_port"] = int(result["internal_port"])
            except (ValueError, TypeError):
                result["internal_port"] = 3000

        if not (1 <= result["internal_port"] <= 65535):
            result["internal_port"] = 3000

        # Garantir health_check tem todos os campos
        hc = result.get("health_check", {})
        if not isinstance(hc, dict):
            hc = {}
        result["health_check"] = {
            "path": hc.get("path", "/"),
            "interval_seconds": hc.get("interval_seconds", 30),
            "timeout_seconds": hc.get("timeout_seconds", 5),
            "start_period_seconds": hc.get("start_period_seconds", 30),
        }

        if not isinstance(result.get("env_vars"), dict):
            result["env_vars"] = {}

        if not isinstance(result.get("depends_on"), list):
            result["depends_on"] = []

        logger.info(f"Validação OK: type={result['project_type']}, lang={result['language']}, "
                     f"runtime={result['runtime']}, port={result['internal_port']}")
        return result


# ============ LOCAL FALLBACK DETECTOR ============

class LocalFallbackDetector:
    """
    Detector de emergência: heurísticas simples quando a IA estiver completamente offline.
    Retorna o mesmo schema que a IA — sem quebrar o fluxo do deploy.
    """

    @staticmethod
    def _detect_port_from_configs(cfg: dict) -> int:
        """Tenta detectar a porta interna a partir dos config files."""
        import re

        # 1. package.json scripts — procurar --port XXXX ou PORT=XXXX
        pkg = cfg.get("package.json", "")
        if pkg:
            # "start": "node server.js --port 7680"
            # "start": "PORT=8080 node server.js"
            # "dev": "vite --port 5173"
            for pattern in [
                r'--port\s+(\d{2,5})',
                r'PORT[=:]\s*(\d{2,5})',
                r'-p\s+(\d{2,5})',
                r'listen\((\d{2,5})\)',
            ]:
                m = re.search(pattern, pkg)
                if m:
                    port = int(m.group(1))
                    if 1024 <= port <= 65535:
                        return port

        # 2. .env.example — PORT=XXXX
        for env_file in (".env.example", ".env.sample"):
            env = cfg.get(env_file, "")
            m = re.search(r'^\s*PORT\s*=\s*(\d{2,5})', env, re.MULTILINE)
            if m:
                port = int(m.group(1))
                if 1024 <= port <= 65535:
                    return port

        # 3. Dockerfile existente — EXPOSE XXXX
        dockerfile = cfg.get("Dockerfile", "")
        if dockerfile:
            m = re.search(r'EXPOSE\s+(\d{2,5})', dockerfile)
            if m:
                port = int(m.group(1))
                if 1024 <= port <= 65535:
                    return port

        # 4. nginx.conf — listen XXXX
        nginx = cfg.get("nginx.conf", "")
        if nginx:
            m = re.search(r'listen\s+(\d{2,5})', nginx)
            if m:
                port = int(m.group(1))
                if 1024 <= port <= 65535:
                    return port

        # 5. Go — ":8080" pattern em go.mod path ou common ports
        if "go.mod" in cfg:
            return 8080  # Go convention

        return 3000  # Default fallback

    def detect(self, scan_result: dict, app_name: str, base_port: int, copy_path: str = ".") -> dict:
        cfg = scan_result["config_files"]
        hints = scan_result.get("language_hints", {})
        self._monorepo = scan_result.get("monorepo", {})

        # Detectar linguagem/runtime
        if "go.mod" in cfg:
            return self._go_config(app_name, copy_path, cfg)
        elif "Cargo.toml" in cfg:
            return self._rust_config(app_name, copy_path, cfg)
        elif "requirements.txt" in cfg or "pyproject.toml" in cfg:
            return self._python_config(app_name, copy_path, cfg)
        elif "composer.json" in cfg:
            return self._php_config(app_name, copy_path, cfg)
        elif "package.json" in cfg:
            return self._node_config(app_name, copy_path, cfg)
        else:
            # Fallback genérico baseado em extensões
            top_ext = list(hints.keys())[0] if hints else ""
            if top_ext in (".py",):
                return self._python_config(app_name, copy_path, cfg)
            elif top_ext in (".go",):
                return self._go_config(app_name, copy_path, cfg)
            return self._node_config(app_name, copy_path, cfg)

    def _node_config(self, app_name: str, copy_path: str, cfg: dict) -> dict:
        has_vite = any(k.startswith("vite.config") for k in cfg)
        has_next = "next.config.js" in cfg or "next.config.ts" in cfg
        port = self._detect_port_from_configs(cfg)

        # Monorepo detection
        mono = getattr(self, '_monorepo', {})
        is_monorepo = bool(mono)
        pm = mono.get("package_manager", "npm") if is_monorepo else (
            "pnpm" if "pnpm-lock.yaml" in cfg else ("yarn" if "yarn.lock" in cfg else "npm")
        )

        is_frontend = has_vite or has_next

        if is_monorepo:
            # === MONOREPO BUILD ===
            has_turbo = bool(mono.get("turbo_json"))

            install_cmd = {
                "pnpm": "corepack enable pnpm && pnpm install --frozen-lockfile",
                "yarn": "yarn install --frozen-lockfile",
                "npm": "npm ci",
            }.get(pm, "npm ci")

            lockfile_copy = {
                "pnpm": "COPY pnpm-lock.yaml pnpm-workspace.yaml ./",
                "yarn": "COPY yarn.lock ./",
                "npm": "COPY package-lock.json ./",
            }.get(pm, "")

            # Detectar nome do package do package.json do app
            pkg_name = None
            try:
                pkg_json_str = cfg.get("package.json", "")
                if pkg_json_str:
                    import json as _json
                    pkg_name = _json.loads(pkg_json_str).get("name")
            except Exception:
                pass

            # Use turbo if available (handles ^build dependency order)
            if has_turbo and pkg_name:
                filter_build = f"pnpm turbo build --filter={pkg_name}"
            elif has_turbo:
                filter_build = f"pnpm turbo build --filter=./{copy_path}"
            else:
                filter_build = {
                    "pnpm": f"pnpm --filter ./{copy_path} build",
                    "yarn": f"yarn workspace @tapp/{app_name} build",
                    "npm": f"npm run build --workspace={copy_path}",
                }.get(pm, f"{pm} run build")

            turbo_copy = "COPY turbo.json ./" if has_turbo else ""

            if is_frontend:
                # Detectar onde o build output vai parar de verdade
                out_path = f"/app/{copy_path}/dist"
                try:
                    import re as _re
                    for vf in ["vite.config.ts", "vite.config.js"]:
                        vp = os.path.join("/root/Tapp", copy_path, vf)
                        if os.path.isfile(vp):
                            with open(vp, 'r') as _f:
                                _m = _re.search(r"outDir\s*:\s*['\"]([^'\"]+)['\"]", _f.read())
                                if _m:
                                    resolved = os.path.normpath(os.path.join(copy_path, _m.group(1)))
                                    out_path = f"/app/{resolved}"
                            break
                except Exception:
                    pass

                dockerfile = f"""FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json ./
{lockfile_copy}
{turbo_copy}
COPY packages/ ./packages/
COPY {copy_path}/ ./{copy_path}/
RUN {install_cmd}
RUN {filter_build}

FROM nginx:alpine
COPY --from=builder {out_path} /usr/share/nginx/html
RUN echo 'server {{ listen 80; root /usr/share/nginx/html; index index.html; location / {{ try_files $$uri $$uri/ /index.html; }} }}' > /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD wget -qO- http://localhost:80/ || exit 1
CMD ["nginx", "-g", "daemon off;"]"""
                return self._make_config("frontend", "typescript", "vite" if has_vite else "next",
                                         "nginx", dockerfile, filter_build, "nginx -g 'daemon off;'", app_name, 80)
            else:
                # Backend: detectar porta real
                dockerfile = f"""FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json ./
{lockfile_copy}
{turbo_copy}
COPY packages/ ./packages/
COPY {copy_path}/ ./{copy_path}/
RUN {install_cmd}
RUN {filter_build}

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/{copy_path}/dist ./dist
COPY --from=builder /app/{copy_path}/package.json .
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/{copy_path}/node_modules ./node_modules 2>/dev/null || true
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD wget -qO- http://localhost:{port}/health || exit 1
CMD ["node", "dist/server.js"]"""
                return self._make_config("backend", "typescript", "node", "node",
                                         dockerfile, filter_build, "node dist/server.js", app_name, port)
        else:
            # === STANDALONE BUILD ===
            has_pnpm = "pnpm-lock.yaml" in cfg
            if is_frontend:
                build_cmd = f"{pm} run build"
                dockerfile = f"""FROM node:20-alpine AS builder
WORKDIR /app
COPY {copy_path}/package*.json ./
{'COPY ' + copy_path + '/pnpm-lock.yaml ./' if has_pnpm else ''}
RUN {'npm install -g pnpm && pnpm install --frozen-lockfile' if has_pnpm else (pm + ' install')}
COPY {copy_path} .
RUN {build_cmd}

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE {port}
RUN echo 'server {{ listen {port}; root /usr/share/nginx/html; index index.html; location / {{ try_files $uri $uri/ /index.html; }} }}' > /etc/nginx/conf.d/default.conf
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD wget -qO- http://localhost:{port}/ || exit 1
CMD ["nginx", "-g", "daemon off;"]"""
                return self._make_config("frontend", "typescript", "vite" if has_vite else "next",
                                         "nginx", dockerfile, build_cmd, "nginx -g 'daemon off;'", app_name, port)
            else:
                dockerfile = f"""FROM node:20-alpine AS builder
WORKDIR /app
COPY {copy_path}/package*.json ./
{'COPY ' + copy_path + '/pnpm-lock.yaml ./' if has_pnpm else ''}
RUN {'npm install -g pnpm && pnpm install --frozen-lockfile' if has_pnpm else (pm + ' install')}
COPY {copy_path} .
RUN {pm} run build 2>/dev/null || true

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist 2>/dev/null || true
COPY --from=builder /app/package.json .
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD wget -qO- http://localhost:{port}/health || exit 1
CMD ["node", "dist/index.js"]"""
                return self._make_config("backend", "typescript", "node", "node",
                                         dockerfile, f"{pm} run build", "node dist/index.js", app_name, port)

    def _go_config(self, app_name: str, copy_path: str, cfg: dict) -> dict:
        port = self._detect_port_from_configs(cfg)

        dockerfile = f"""FROM golang:1.23-alpine AS builder
WORKDIR /app
COPY {copy_path}/go.mod {copy_path}/go.sum ./
RUN go mod download
COPY {copy_path} .
RUN CGO_ENABLED=0 GOOS=linux go build -o server ./...

FROM alpine:3.20
WORKDIR /app
RUN apk --no-cache add ca-certificates
COPY --from=builder /app/server .
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD wget -qO- http://localhost:{port}/health || exit 1
CMD ["./server"]"""
        return self._make_config("backend", "go", "gin", "go",
                                 dockerfile, "go build -o server ./...", "./server", app_name, port)

    def _rust_config(self, app_name: str, copy_path: str, cfg: dict = None) -> dict:
        port = self._detect_port_from_configs(cfg or {})

        dockerfile = f"""FROM rust:1.77-alpine AS builder
WORKDIR /app
RUN apk add --no-cache musl-dev
COPY {copy_path}/Cargo.toml {copy_path}/Cargo.lock ./
RUN mkdir src && echo 'fn main(){{}}' > src/main.rs && cargo build --release && rm -rf src
COPY {copy_path}/src ./src
RUN cargo build --release

FROM alpine:3.20
WORKDIR /app
RUN apk --no-cache add ca-certificates
COPY --from=builder /app/target/release/{app_name} .
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD wget -qO- http://localhost:{port}/health || exit 1
CMD ["./{app_name}"]"""
        return self._make_config("backend", "rust", "axum", "rust",
                                 dockerfile, "cargo build --release", f"./{app_name}", app_name, port)

    def _python_config(self, app_name: str, copy_path: str, cfg: dict) -> dict:
        port = self._detect_port_from_configs(cfg)
        has_fastapi = "fastapi" in cfg.get("requirements.txt", "").lower()
        has_django = "django" in cfg.get("requirements.txt", "").lower()

        req_file = "pyproject.toml" if "pyproject.toml" in cfg else "requirements.txt"
        framework = "fastapi" if has_fastapi else ("django" if has_django else "flask")
        start_cmd = f"uvicorn main:app --host 0.0.0.0 --port {port}" if has_fastapi else "python main.py"

        dockerfile = f"""FROM python:3.12-slim
WORKDIR /app
COPY {copy_path}/{req_file} ./
RUN pip install --no-cache-dir -r {req_file}
COPY {copy_path} .
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD curl -f http://localhost:{port}/health || exit 1
CMD ["{start_cmd.split()[0]}", {", ".join('"' + a + '"' for a in start_cmd.split()[1:])}]"""
        return self._make_config("backend", "python", framework, "python",
                                 dockerfile, "", start_cmd, app_name, port)

    def _php_config(self, app_name: str, copy_path: str, cfg: dict = None) -> dict:
        port = self._detect_port_from_configs(cfg or {})

        dockerfile = f"""FROM php:8.3-fpm-alpine
WORKDIR /app
RUN apk add --no-cache nginx
COPY {copy_path} .
RUN if [ -f composer.json ]; then curl -sS https://getcomposer.org/installer | php && php composer.phar install --no-dev; fi
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD curl -f http://localhost:{port}/ || exit 1
CMD ["php", "-S", "0.0.0.0:{port}", "-t", "public"]"""
        return self._make_config("backend", "php", "laravel", "php",
                                 dockerfile, "composer install --no-dev", f"php -S 0.0.0.0:{port} -t public", app_name, port)

    def _make_config(self, project_type: str, language: str, framework: str,
                     runtime: str, dockerfile: str, build_cmd: str, start_cmd: str,
                     app_name: str, internal_port: int = 3000) -> dict:
        return {
            "project_type": project_type,
            "language": language,
            "framework": framework,
            "runtime": runtime,
            "dockerfile": dockerfile,
            "internal_port": internal_port,
            "start_command": start_cmd,
            "build_command": build_cmd,
            "env_vars": {"NODE_ENV": "production"},
            "health_check": {
                "path": "/health",
                "interval_seconds": 30,
                "timeout_seconds": 5,
                "start_period_seconds": 30,
            },
            "notes": f"Configuração gerada por fallback local (IA offline) para {app_name}",
            "depends_on": [],
        }


# ============ PUBLIC API ============

def _scan_monorepo_root(project_path: str) -> dict:
    """
    Detecta se o projeto está dentro de um monorepo e coleta contexto do root.
    Retorna dict com info do monorepo ou {} se não for monorepo.
    """
    monorepo = {}
    # Subir a partir do project_path até encontrar pnpm-workspace.yaml ou root package.json com workspaces
    current = Path(project_path).resolve()
    for _ in range(5):  # Max 5 níveis acima
        parent = current.parent
        if parent == current:
            break
        current = parent

        workspace_yaml = current / "pnpm-workspace.yaml"
        root_pkg = current / "package.json"

        if workspace_yaml.is_file() or (root_pkg.is_file()):
            try:
                if root_pkg.is_file():
                    pkg_content = root_pkg.read_text(encoding="utf-8", errors="replace")
                    if "workspaces" not in pkg_content and not workspace_yaml.is_file():
                        continue
                    monorepo["root_package_json"] = pkg_content[:MAX_FILE_BYTES]
            except Exception:
                pass

            try:
                if workspace_yaml.is_file():
                    monorepo["pnpm_workspace_yaml"] = workspace_yaml.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

            # Turbo config
            turbo = current / "turbo.json"
            if turbo.is_file():
                try:
                    monorepo["turbo_json"] = turbo.read_text(encoding="utf-8", errors="replace")[:MAX_FILE_BYTES]
                except Exception:
                    pass

            # Lockfile check
            if (current / "pnpm-lock.yaml").is_file():
                monorepo["lockfile"] = "pnpm-lock.yaml"
                monorepo["package_manager"] = "pnpm"
            elif (current / "yarn.lock").is_file():
                monorepo["lockfile"] = "yarn.lock"
                monorepo["package_manager"] = "yarn"
            elif (current / "package-lock.json").is_file():
                monorepo["lockfile"] = "package-lock.json"
                monorepo["package_manager"] = "npm"

            monorepo["root_path"] = str(current)

            # Listar packages/ para contexto
            packages_dir = current / "packages"
            if packages_dir.is_dir():
                pkgs = []
                for p in sorted(packages_dir.iterdir()):
                    if p.is_dir() and (p / "package.json").is_file():
                        try:
                            pkg_json = json.loads((p / "package.json").read_text())
                            pkgs.append({"name": pkg_json.get("name", p.name), "dir": p.name})
                        except Exception:
                            pkgs.append({"name": p.name, "dir": p.name})
                monorepo["workspace_packages"] = pkgs

            break

    return monorepo


def analyze_project(project_path: str, app_name: str, base_port: int, copy_path: str = None) -> dict:
    """
    API pública: escaneia projeto e retorna config de infraestrutura.
    Tenta: IA primária → IA fallback → detector local.
    Nunca levanta exceção — sempre retorna um dict válido.

    Args:
        project_path: caminho absoluto para a pasta do projeto no filesystem
        app_name: nome do app (ex: 'driver', 'admin')
        base_port: porta externa no host (ex: 2610)
        copy_path: path relativo no repo para COPY no Dockerfile (ex: 'apps/driver')
                   Se None, usa o nome da pasta
    """
    if copy_path is None:
        copy_path = os.path.basename(project_path.rstrip("/\\"))

    logger.info(f"Analisando projeto {app_name} em {project_path}")

    # 1. Escanear projeto
    try:
        scanner = ProjectScanner(project_path)
        scan_result = scanner.scan()
        logger.info(
            f"Scan concluído: {len(scan_result['config_files'])} config files, "
            f"{len(scan_result['language_hints'])} tipos de extensão"
        )
    except Exception as e:
        logger.error(f"Erro ao escanear projeto {app_name}: {e}")
        scan_result = {"file_tree": [], "config_files": {}, "language_hints": {}, "existing_dockerfile": None}

    # 1b. Detectar monorepo
    try:
        monorepo = _scan_monorepo_root(project_path)
        if monorepo:
            scan_result["monorepo"] = monorepo
            logger.info(f"Monorepo detectado: {monorepo.get('package_manager', '?')} "
                        f"com {len(monorepo.get('workspace_packages', []))} packages")
    except Exception as e:
        logger.warning(f"Erro ao detectar monorepo: {e}")

    # 2. Tentar IA
    try:
        analyzer = AIAnalyzer(AI_BASE_URL)
        result = analyzer.analyze(scan_result, app_name, base_port, copy_path)
        if result:
            result["_source"] = "ai"
            return result
    except Exception as e:
        logger.error(f"Erro inesperado no AIAnalyzer: {e}")

    # 3. Fallback local
    logger.warning(f"IA indisponível para {app_name} — usando detector local de emergência")
    fallback = LocalFallbackDetector()
    result = fallback.detect(scan_result, app_name, base_port, copy_path)
    result["_source"] = "fallback"
    return result


# ============ CLI / TESTE ============

if __name__ == "__main__":
    import sys
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    parser = argparse.ArgumentParser(description="Analisa um projeto e gera config de infraestrutura")
    parser.add_argument("project_path", help="Caminho para a pasta do projeto")
    parser.add_argument("--name", default=None, help="Nome do app (default: nome da pasta)")
    parser.add_argument("--port", type=int, default=3000, help="Porta externa no host")
    parser.add_argument("--copy-path", default=None, help="Path relativo no repo para COPY no Dockerfile")
    parser.add_argument("--no-ai", action="store_true", help="Pular IA e usar apenas detector local")
    args = parser.parse_args()

    app_name = args.name or os.path.basename(args.project_path.rstrip("/\\"))

    if args.no_ai:
        scanner = ProjectScanner(args.project_path)
        scan_result = scanner.scan()
        fallback = LocalFallbackDetector()
        result = fallback.detect(scan_result, app_name, args.port, args.copy_path or app_name)
        result["_source"] = "fallback"
    else:
        result = analyze_project(args.project_path, app_name, args.port, args.copy_path)

    print("\n" + "="*60)
    print(f"RESULTADO para {app_name} (fonte: {result.get('_source', '?')})")
    print("="*60)
    print(f"Tipo:       {result.get('project_type')} / {result.get('language')} / {result.get('framework')}")
    print(f"Runtime:    {result.get('runtime')}")
    print(f"Porta:      {result.get('internal_port')}")
    print(f"Build:      {result.get('build_command')}")
    print(f"Start:      {result.get('start_command')}")
    print(f"Health:     {result.get('health_check', {}).get('path')}")
    print(f"Notas:      {result.get('notes')}")
    print(f"Depende de: {result.get('depends_on', [])}")
    print("\n--- Dockerfile ---")
    print(result.get("dockerfile", "(vazio)"))
    print("\n--- ENV vars ---")
    for k, v in result.get("env_vars", {}).items():
        print(f"  {k}={v}")
