from __future__ import annotations

import json
import os
import re
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ANALYZER_VERSION = "2026.04.04"
IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "__pycache__",
    ".next",
    ".nuxt",
    ".turbo",
    ".vercel",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".venv",
    "venv",
    "vendor",
    "tmp",
    "temp",
}
MANIFEST_NAMES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}
ENV_HINT_FILES = (
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.local.example",
)
README_FILES = ("README.md", "README.txt", "readme.md", "readme.txt")
ROOT_PROBE_FILES = (
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "Cargo.toml",
    "Dockerfile",
    ".env.example",
    "README.md",
    "vite.config.ts",
    "vite.config.js",
    "next.config.js",
    "next.config.mjs",
    "main.py",
    "app.py",
    "server.py",
    "main.go",
    "src/main.rs",
)
PORT_PATTERNS = (
    re.compile(r"\bPORT\s*[=:]\s*[\"']?(\d{2,5})\b", re.IGNORECASE),
    re.compile(r"--port(?:=|\s+)(\d{2,5})\b", re.IGNORECASE),
    re.compile(r"\blisten\s*\(\s*(\d{2,5})\s*[,)]", re.IGNORECASE),
    re.compile(r"\bEXPOSE\s+(\d{2,5})\b", re.IGNORECASE),
)
FRONTEND_DEPS = {
    "react",
    "react-dom",
    "next",
    "vite",
    "vue",
    "nuxt",
    "svelte",
    "@angular/core",
    "@remix-run/react",
    "astro",
}
BACKEND_DEPS = {
    "fastify",
    "express",
    "koa",
    "hapi",
    "@nestjs/core",
    "hono",
    "elysia",
    "flask",
    "django",
    "fastapi",
    "uvicorn",
    "gunicorn",
}
WORKER_DEPS = {"bullmq", "agenda", "celery", "rq", "dramatiq"}
FRONTEND_DIR_HINTS = {"frontend", "front", "web", "client", "site", "admin", "app"}
BACKEND_DIR_HINTS = {"backend", "back", "api", "server", "service"}
WORKER_DIR_HINTS = {"worker", "workers", "jobs", "queue", "cron"}
LIBRARY_DIR_HINTS = {"packages", "libs", "shared", "ui", "config", "core"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str, *, fallback: str = "project") -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or fallback


def safe_read_text(path: Path, limit: int = 64_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_toml(path: Path) -> dict[str, Any]:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def path_depth(root: Path, target: Path) -> int:
    try:
        return len(target.relative_to(root).parts)
    except ValueError:
        return 0


def relative_path(root: Path, target: Path) -> str:
    try:
        result = target.relative_to(root).as_posix()
    except ValueError:
        result = target.as_posix()
    return result or "."


def detect_package_manager(root: Path) -> str:
    if (root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    if (root / "bun.lockb").exists() or (root / "bun.lock").exists():
        return "bun"
    if (root / "package-lock.json").exists():
        return "npm"
    return "npm"


def build_script_command(package_manager: str, script_name: str, rel_path: str) -> str:
    prefix = {
        "pnpm": "pnpm",
        "yarn": "yarn",
        "bun": "bun run",
        "npm": "npm run",
    }.get(package_manager, "npm run")
    if rel_path == ".":
        return f"{prefix} {script_name}"
    if package_manager == "pnpm":
        return f"pnpm --dir {rel_path} {script_name}"
    if package_manager == "yarn":
        return f"cd {rel_path} && yarn {script_name}"
    if package_manager == "bun":
        return f"cd {rel_path} && bun run {script_name}"
    return f"cd {rel_path} && npm run {script_name}"


def parse_env_hints(component_root: Path) -> list[str]:
    hints: list[str] = []
    for filename in ENV_HINT_FILES:
        candidate = component_root / filename
        if not candidate.exists():
            continue
        for line in safe_read_text(candidate).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name = stripped.split("=", 1)[0].strip()
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
                hints.append(name)
    return sorted(dict.fromkeys(hints))[:30]


def read_readme(root: Path) -> dict[str, str]:
    for filename in README_FILES:
        candidate = root / filename
        if not candidate.exists():
            continue
        content = safe_read_text(candidate, limit=20_000)
        if not content.strip():
            continue
        title = ""
        paragraph = ""
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if not title and stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                continue
            if not paragraph and len(stripped) > 30 and not stripped.startswith(("!", "[", "```")):
                paragraph = stripped
            if title and paragraph:
                break
        return {
            "file": filename,
            "title": title,
            "summary": paragraph,
            "excerpt": content[:3000],
        }
    return {"file": "", "title": "", "summary": "", "excerpt": ""}


def guess_port_from_texts(texts: list[str]) -> int | None:
    for text in texts:
        if not text:
            continue
        for pattern in PORT_PATTERNS:
            match = pattern.search(text)
            if match:
                try:
                    value = int(match.group(1))
                except (TypeError, ValueError):
                    continue
                if 1 <= value <= 65535:
                    return value
    return None


def collect_probe_texts(component_root: Path) -> list[str]:
    texts: list[str] = []
    for filename in ROOT_PROBE_FILES:
        candidate = component_root / filename
        if candidate.exists() and candidate.is_file():
            texts.append(safe_read_text(candidate))

    src_dir = component_root / "src"
    if src_dir.exists() and src_dir.is_dir():
        seen = 0
        for candidate in sorted(src_dir.rglob("*")):
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() not in {".js", ".ts", ".tsx", ".jsx", ".py", ".go", ".rs"}:
                continue
            texts.append(safe_read_text(candidate, limit=8_000))
            seen += 1
            if seen >= 6:
                break
    return texts


def component_public_default(component_type: str, frameworks: list[str]) -> bool:
    if component_type == "frontend":
        return True
    if component_type == "fullstack":
        return True
    if component_type == "backend":
        return "fastapi" not in frameworks and "django" not in frameworks
    return False


def default_container_port(component_type: str, frameworks: list[str], detected_port: int | None) -> int | None:
    if detected_port:
        return detected_port
    if component_type == "frontend":
        if "next" in frameworks or "nuxt" in frameworks:
            return 3000
        return 80
    if component_type == "fullstack":
        return 3000
    if component_type == "backend":
        if "fastify" in frameworks:
            return 3333
        if "fastapi" in frameworks or "flask" in frameworks or "django" in frameworks:
            return 8000
        return 3000
    if component_type == "worker":
        return None
    return 8080


def detect_health_path(component_root: Path, component_type: str) -> str:
    if component_type == "frontend":
        return "/"
    texts = collect_probe_texts(component_root)
    for text in texts:
        lower = text.lower()
        if "/healthz" in lower:
            return "/healthz"
        if "/health" in lower:
            return "/health"
        if "/status" in lower:
            return "/status"
    return "/" if component_type in {"fullstack", "frontend"} else "/health"


def append_diagnostic(
    rows: list[dict[str, Any]],
    *,
    scope: str,
    severity: str,
    code: str,
    summary: str,
    suggestion: str = "",
    evidence: list[str] | None = None,
) -> None:
    rows.append(
        {
            "scope": scope,
            "severity": severity,
            "code": code,
            "summary": summary,
            "suggestion": suggestion,
            "evidence": evidence or [],
        }
    )


def discover_candidate_roots(root: Path, max_depth: int = 4) -> list[Path]:
    candidates: set[Path] = set()
    if any((root / name).exists() for name in MANIFEST_NAMES):
        candidates.add(root)

    for current_root, dirs, files in os.walk(root):
        current_path = Path(current_root)
        depth = path_depth(root, current_path)
        dirs[:] = [
            item
            for item in dirs
            if item not in IGNORE_DIRS and not item.startswith(".cache")
        ]
        if depth > max_depth:
            dirs[:] = []
            continue
        if current_path != root and any(name in files for name in MANIFEST_NAMES):
            candidates.add(current_path)
            dirs[:] = []

    return sorted(candidates, key=lambda item: (path_depth(root, item), relative_path(root, item)))


def analyze_package_json(component_root: Path, root: Path, package_manager: str) -> dict[str, Any]:
    package = load_json(component_root / "package.json")
    dependencies = {}
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        value = package.get(key)
        if isinstance(value, dict):
            dependencies.update({str(name): str(version) for name, version in value.items()})
    scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
    name = str(package.get("name") or component_root.name or root.name)
    rel_path = relative_path(root, component_root)
    lower_name = name.lower()
    frameworks: list[str] = []
    for candidate in sorted(FRONTEND_DEPS | BACKEND_DEPS | WORKER_DEPS):
        if candidate in dependencies:
            frameworks.append(candidate)

    path_name = component_root.name.lower()
    frontend_signal = bool(set(dependencies).intersection(FRONTEND_DEPS)) or path_name in FRONTEND_DIR_HINTS
    backend_signal = bool(set(dependencies).intersection(BACKEND_DEPS)) or path_name in BACKEND_DIR_HINTS
    worker_signal = bool(set(dependencies).intersection(WORKER_DEPS)) or path_name in WORKER_DIR_HINTS
    workspaces = package.get("workspaces")
    has_workspace_config = isinstance(workspaces, (list, dict))
    has_dockerfile = (component_root / "Dockerfile").exists()
    has_compose = any((component_root / filename).exists() for filename in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"))
    library_signal = (
        path_name in LIBRARY_DIR_HINTS
        or lower_name.endswith(("/ui", "-ui", "/shared", "-shared", "/config", "-config"))
        or ("build" in scripts and not any(item in scripts for item in ("start", "serve", "preview", "dev")))
    )

    if has_workspace_config and component_root == root and not (frontend_signal or backend_signal or worker_signal):
        component_type = "orchestrator"
    elif frontend_signal and backend_signal:
        component_type = "fullstack"
    elif frontend_signal:
        component_type = "frontend"
    elif backend_signal:
        component_type = "backend"
    elif worker_signal:
        component_type = "worker"
    elif library_signal:
        component_type = "library"
    else:
        component_type = "service"

    deployable = component_type in {"frontend", "backend", "fullstack", "worker", "service"} and (
        has_dockerfile or any(key in scripts for key in ("start", "serve", "preview", "build", "dev"))
    )

    probe_texts = collect_probe_texts(component_root)
    detected_port = guess_port_from_texts(
        [
            json.dumps(scripts, ensure_ascii=False),
            json.dumps(package, ensure_ascii=False),
            *probe_texts,
        ]
    )
    health_path = detect_health_path(component_root, component_type)
    if "next" in frameworks:
        entry_strategy = "node_server"
    elif component_type == "frontend" and "vite" in frameworks:
        entry_strategy = "static_build"
    elif component_type == "backend":
        entry_strategy = "node_server"
    elif component_type == "worker":
        entry_strategy = "worker_process"
    elif has_dockerfile:
        entry_strategy = "repo_dockerfile"
    else:
        entry_strategy = "service_process"

    build_command = ""
    for script_name in ("build", "compile"):
        if script_name in scripts:
            build_command = build_script_command(package_manager, script_name, rel_path)
            break
    start_command = ""
    for script_name in ("start", "serve", "preview", "dev"):
        if script_name in scripts:
            start_command = build_script_command(package_manager, script_name, rel_path)
            break

    return {
        "id": slugify(f"{rel_path}-{component_type}", fallback="component"),
        "name": name,
        "path": str(component_root),
        "rel_path": rel_path,
        "language": "node",
        "runtime": "node",
        "package_manager": package_manager,
        "frameworks": frameworks,
        "type": component_type,
        "deployable": deployable,
        "public": component_public_default(component_type, frameworks),
        "detected_port": detected_port,
        "container_port": default_container_port(component_type, frameworks, detected_port),
        "health_path": health_path,
        "entry_strategy": entry_strategy,
        "build_command": build_command,
        "start_command": start_command,
        "has_dockerfile": has_dockerfile,
        "has_compose": has_compose,
        "has_lockfile": any((component_root / filename).exists() for filename in ("pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lockb", "bun.lock")),
        "scripts": sorted(str(key) for key in scripts.keys()),
        "dependencies_count": len(dependencies),
        "env_hints": parse_env_hints(component_root),
        "evidence": [f"package.json em {rel_path}"],
    }


def analyze_python_project(component_root: Path, root: Path) -> dict[str, Any]:
    rel_path = relative_path(root, component_root)
    pyproject = load_toml(component_root / "pyproject.toml")
    project_section = pyproject.get("project") if isinstance(pyproject.get("project"), dict) else {}
    poetry_section = (
        pyproject.get("tool", {}).get("poetry")
        if isinstance(pyproject.get("tool"), dict) and isinstance(pyproject.get("tool", {}).get("poetry"), dict)
        else {}
    )
    requirements_text = safe_read_text(component_root / "requirements.txt")
    dependency_source = []
    for row in project_section.get("dependencies", []) if isinstance(project_section.get("dependencies"), list) else []:
        dependency_source.append(str(row))
    if isinstance(poetry_section.get("dependencies"), dict):
        dependency_source.extend(str(item) for item in poetry_section.get("dependencies", {}).keys())
    dependency_source.extend(re.findall(r"^([A-Za-z0-9_.-]+)", requirements_text, flags=re.MULTILINE))
    dependency_blob = " ".join(dependency_source).lower()
    frameworks = []
    for candidate in ("fastapi", "uvicorn", "flask", "django", "celery", "rq"):
        if candidate in dependency_blob:
            frameworks.append(candidate)

    path_name = component_root.name.lower()
    if "celery" in frameworks or "rq" in frameworks or path_name in WORKER_DIR_HINTS:
        component_type = "worker"
    else:
        component_type = "backend"

    probe_texts = collect_probe_texts(component_root)
    detected_port = guess_port_from_texts([requirements_text, json.dumps(pyproject, ensure_ascii=False), *probe_texts])
    health_path = detect_health_path(component_root, component_type)
    container_port = default_container_port(component_type, frameworks, detected_port)
    has_dockerfile = (component_root / "Dockerfile").exists()

    if "fastapi" in frameworks:
        start_command = f"cd {rel_path} && uvicorn app:app --host 0.0.0.0 --port {container_port or 8000}"
    elif "flask" in frameworks:
        start_command = f"cd {rel_path} && flask run --host 0.0.0.0 --port {container_port or 8000}"
    elif "django" in frameworks:
        start_command = f"cd {rel_path} && python manage.py runserver 0.0.0.0:{container_port or 8000}"
    else:
        start_command = f"cd {rel_path} && python main.py"

    return {
        "id": slugify(f"{rel_path}-{component_type}", fallback="python-service"),
        "name": str(project_section.get("name") or poetry_section.get("name") or component_root.name),
        "path": str(component_root),
        "rel_path": rel_path,
        "language": "python",
        "runtime": "python",
        "package_manager": "pip",
        "frameworks": frameworks,
        "type": component_type,
        "deployable": bool(has_dockerfile or dependency_source or (component_root / "main.py").exists() or (component_root / "app.py").exists()),
        "public": component_type == "backend",
        "detected_port": detected_port,
        "container_port": container_port,
        "health_path": health_path,
        "entry_strategy": "python_service" if component_type == "backend" else "worker_process",
        "build_command": f"cd {rel_path} && python -m pip install -r requirements.txt" if (component_root / "requirements.txt").exists() else f"cd {rel_path} && python -m pip install .",
        "start_command": start_command,
        "has_dockerfile": has_dockerfile,
        "has_compose": any((component_root / filename).exists() for filename in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")),
        "has_lockfile": (component_root / "requirements.txt").exists(),
        "scripts": [],
        "dependencies_count": len(dependency_source),
        "env_hints": parse_env_hints(component_root),
        "evidence": [f"projeto Python em {rel_path}"],
    }


def analyze_go_project(component_root: Path, root: Path) -> dict[str, Any]:
    rel_path = relative_path(root, component_root)
    go_mod = safe_read_text(component_root / "go.mod")
    probe_texts = collect_probe_texts(component_root)
    detected_port = guess_port_from_texts([go_mod, *probe_texts])
    frameworks = []
    if "gin-gonic" in go_mod:
        frameworks.append("gin")
    if "fiber" in go_mod:
        frameworks.append("fiber")
    return {
        "id": slugify(f"{rel_path}-go-service", fallback="go-service"),
        "name": component_root.name,
        "path": str(component_root),
        "rel_path": rel_path,
        "language": "go",
        "runtime": "go",
        "package_manager": "go",
        "frameworks": frameworks,
        "type": "backend",
        "deployable": True,
        "public": True,
        "detected_port": detected_port,
        "container_port": default_container_port("backend", frameworks, detected_port),
        "health_path": detect_health_path(component_root, "backend"),
        "entry_strategy": "compiled_service",
        "build_command": f"cd {rel_path} && go build ./...",
        "start_command": "",
        "has_dockerfile": (component_root / "Dockerfile").exists(),
        "has_compose": any((component_root / filename).exists() for filename in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")),
        "has_lockfile": (component_root / "go.sum").exists(),
        "scripts": [],
        "dependencies_count": max(len(go_mod.splitlines()) - 1, 0),
        "env_hints": parse_env_hints(component_root),
        "evidence": [f"go.mod em {rel_path}"],
    }


def analyze_rust_project(component_root: Path, root: Path) -> dict[str, Any]:
    rel_path = relative_path(root, component_root)
    cargo = load_toml(component_root / "Cargo.toml")
    deps = cargo.get("dependencies") if isinstance(cargo.get("dependencies"), dict) else {}
    frameworks = [name for name in ("axum", "actix-web", "rocket", "tokio") if name in deps]
    probe_texts = collect_probe_texts(component_root)
    detected_port = guess_port_from_texts([json.dumps(cargo, ensure_ascii=False), *probe_texts])
    return {
        "id": slugify(f"{rel_path}-rust-service", fallback="rust-service"),
        "name": str(cargo.get("package", {}).get("name") if isinstance(cargo.get("package"), dict) else component_root.name),
        "path": str(component_root),
        "rel_path": rel_path,
        "language": "rust",
        "runtime": "rust",
        "package_manager": "cargo",
        "frameworks": frameworks,
        "type": "backend",
        "deployable": True,
        "public": True,
        "detected_port": detected_port,
        "container_port": default_container_port("backend", frameworks, detected_port),
        "health_path": detect_health_path(component_root, "backend"),
        "entry_strategy": "compiled_service",
        "build_command": f"cd {rel_path} && cargo build --release",
        "start_command": "",
        "has_dockerfile": (component_root / "Dockerfile").exists(),
        "has_compose": any((component_root / filename).exists() for filename in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")),
        "has_lockfile": (component_root / "Cargo.lock").exists(),
        "scripts": [],
        "dependencies_count": len(deps),
        "env_hints": parse_env_hints(component_root),
        "evidence": [f"Cargo.toml em {rel_path}"],
    }


def analyze_unknown_project(component_root: Path, root: Path) -> dict[str, Any]:
    rel_path = relative_path(root, component_root)
    return {
        "id": slugify(f"{rel_path}-unknown", fallback="unknown"),
        "name": component_root.name or root.name,
        "path": str(component_root),
        "rel_path": rel_path,
        "language": "unknown",
        "runtime": "unknown",
        "package_manager": "",
        "frameworks": [],
        "type": "service",
        "deployable": (component_root / "Dockerfile").exists(),
        "public": False,
        "detected_port": None,
        "container_port": guess_port_from_texts(collect_probe_texts(component_root)),
        "health_path": "/",
        "entry_strategy": "repo_dockerfile" if (component_root / "Dockerfile").exists() else "manual",
        "build_command": "",
        "start_command": "",
        "has_dockerfile": (component_root / "Dockerfile").exists(),
        "has_compose": any((component_root / filename).exists() for filename in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")),
        "has_lockfile": False,
        "scripts": [],
        "dependencies_count": 0,
        "env_hints": parse_env_hints(component_root),
        "evidence": [f"manifestos nao reconhecidos em {rel_path}"],
    }


def analyze_component(component_root: Path, root: Path, package_manager: str) -> dict[str, Any]:
    if (component_root / "package.json").exists():
        return analyze_package_json(component_root, root, package_manager)
    if (component_root / "pyproject.toml").exists() or (component_root / "requirements.txt").exists():
        return analyze_python_project(component_root, root)
    if (component_root / "go.mod").exists():
        return analyze_go_project(component_root, root)
    if (component_root / "Cargo.toml").exists():
        return analyze_rust_project(component_root, root)
    return analyze_unknown_project(component_root, root)


def classify_repo_kind(components: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    deployable = [item for item in components if item.get("deployable")]
    frontends = [item for item in deployable if item.get("type") == "frontend"]
    backends = [item for item in deployable if item.get("type") == "backend"]
    fullstacks = [item for item in deployable if item.get("type") == "fullstack"]
    workers = [item for item in deployable if item.get("type") == "worker"]
    support = [item for item in components if item.get("type") in {"library", "orchestrator"}]
    monorepo = bool((root / "pnpm-workspace.yaml").exists() or (root / "turbo.json").exists() or any(item.get("type") == "orchestrator" for item in components))

    if monorepo:
        repo_kind = "monorepo"
    elif fullstacks or (frontends and backends):
        repo_kind = "fullstack"
    elif len(deployable) > 1:
        repo_kind = "multi-service"
    elif frontends:
        repo_kind = "frontend-only"
    elif backends:
        repo_kind = "backend-only"
    elif workers and len(deployable) == 1:
        repo_kind = "worker-only"
    else:
        repo_kind = "service"

    primary_stack = sorted({item.get("language", "unknown") for item in deployable}) or ["unknown"]
    return {
        "repo_kind": repo_kind,
        "monorepo": monorepo,
        "deployable_components": len(deployable),
        "support_packages": len(support),
        "primary_stack": primary_stack,
    }


def derive_brief(project_name: str, repo_path: Path, readme: dict[str, str], classification: dict[str, Any], components: list[dict[str, Any]]) -> dict[str, str]:
    deployable = [item for item in components if item.get("deployable")]
    component_summary = ", ".join(
        f"{item.get('type')} {item.get('name')}" for item in deployable[:4]
    ) or "nenhum componente claramente implantavel"
    primary_stack = "/".join(classification.get("primary_stack") or ["unknown"])
    repo_kind = classification.get("repo_kind", "service")
    headline = f"Repositorio {repo_kind} em {primary_stack}."
    if readme.get("title"):
        headline = readme["title"]
    what_it_is = f"{project_name or repo_path.name} parece ser um repositorio {repo_kind} com {classification.get('deployable_components', 0)} componente(s) implantaveis."
    what_it_does = f"Componentes detectados: {component_summary}."
    purpose = readme.get("summary") or "Nao houve descricao suficiente no README; o objetivo foi inferido pela estrutura do codigo."
    return {
        "headline": headline,
        "what_it_is": what_it_is,
        "what_it_does": what_it_does,
        "purpose": purpose,
    }


def detect_root_manifest(root: Path) -> dict[str, bool]:
    return {
        "git": (root / ".git").exists(),
        "pnpm_workspace": (root / "pnpm-workspace.yaml").exists(),
        "turbo": (root / "turbo.json").exists(),
        "dockerfile": (root / "Dockerfile").exists(),
        "compose": any((root / filename).exists() for filename in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")),
        "readme": any((root / filename).exists() for filename in README_FILES),
    }


def build_files_summary(root: Path, candidate_roots: list[Path]) -> dict[str, Any]:
    top_level_entries = []
    try:
        top_level_entries = sorted(item.name for item in root.iterdir())[:80]
    except OSError:
        top_level_entries = []
    return {
        "top_level_entries": top_level_entries,
        "candidate_roots": [relative_path(root, item) for item in candidate_roots],
        "manifests": detect_root_manifest(root),
    }


def assign_ports(
    components: list[dict[str, Any]],
    *,
    port_base: int,
) -> list[dict[str, Any]]:
    next_offset = 0
    assigned: list[dict[str, Any]] = []
    for component in components:
        item = dict(component)
        if item.get("deployable") and item.get("container_port"):
            item["host_port"] = port_base + next_offset
            next_offset += 1
        else:
            item["host_port"] = None
        assigned.append(item)
    return assigned


def build_routes(components: list[dict[str, Any]], default_domain: str, default_base_path: str) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    base_path = default_base_path or "/"
    base_path = base_path if base_path.startswith("/") else f"/{base_path}"
    for component in components:
        if not component.get("deployable") or not component.get("public"):
            continue
        component_type = component.get("type")
        rel_path = component.get("rel_path", ".")
        route_path = base_path
        if component_type == "backend" and base_path == "/":
            route_path = "/api"
        elif component_type not in {"frontend", "fullstack"} and base_path == "/":
            route_path = f"/{slugify(component.get('name') or rel_path, fallback='service')}"
        routes.append(
            {
                "component_id": component.get("id"),
                "component_name": component.get("name"),
                "domain": default_domain,
                "path": route_path,
                "target_host_port": component.get("host_port"),
                "health_path": component.get("health_path"),
            }
        )
    return routes


def build_deployment_plan(
    project_id: str,
    components: list[dict[str, Any]],
    *,
    port_base: int,
    default_domain: str,
    default_base_path: str,
) -> dict[str, Any]:
    services: list[dict[str, Any]] = []
    for component in components:
        if not component.get("deployable"):
            continue
        services.append(
            {
                "service_name": f"{project_id}-{slugify(component.get('name') or component.get('rel_path', 'service'))}",
                "component_id": component.get("id"),
                "build_context": component.get("rel_path"),
                "entry_strategy": component.get("entry_strategy"),
                "language": component.get("language"),
                "runtime": component.get("runtime"),
                "container_port": component.get("container_port"),
                "host_port": component.get("host_port"),
                "public": component.get("public"),
                "health_path": component.get("health_path"),
                "build_command": component.get("build_command"),
                "start_command": component.get("start_command"),
                "env_hints": component.get("env_hints"),
                "has_dockerfile": component.get("has_dockerfile"),
            }
        )

    return {
        "port_base": port_base,
        "services": services,
        "routes": build_routes(components, default_domain, default_base_path),
        "reverse_proxy_required": any(service.get("public") for service in services),
        "compose_recommended": len(services) > 1,
    }


def analyze_vm_fit(
    diagnostics: list[dict[str, Any]],
    deployment_plan: dict[str, Any],
    vm_context: dict[str, Any] | None,
) -> None:
    if not vm_context:
        return

    if not vm_context.get("docker_available", True):
        append_diagnostic(
            diagnostics,
            scope="vm",
            severity="error",
            code="docker_unavailable",
            summary="Docker nao esta disponivel na VM para este projeto.",
            suggestion="Ative o servico Docker antes de tentar montar ou subir os containers.",
        )
    if not vm_context.get("proxy_active", True):
        append_diagnostic(
            diagnostics,
            scope="vm",
            severity="warning",
            code="proxy_inactive",
            summary="O proxy IA nao esta ativo; enriquecimento e analises assistidas podem falhar.",
            suggestion="Suba o red-ollama-proxy antes de depender de analises por IA.",
        )
    if vm_context.get("disk_free_bytes", 0) and vm_context["disk_free_bytes"] < 4 * 1024 * 1024 * 1024:
        append_diagnostic(
            diagnostics,
            scope="vm",
            severity="warning",
            code="low_disk_space",
            summary="A VM esta com pouco espaco livre para builds e imagens.",
            suggestion="Libere disco ou mova imagens antigas antes dos proximos deploys.",
        )

    occupied_ports = set(int(item) for item in vm_context.get("listening_ports", []) if str(item).isdigit())
    allowed_ports = set(int(item) for item in vm_context.get("allowed_ports", []) if str(item).isdigit())
    for service in deployment_plan.get("services", []):
        host_port = service.get("host_port")
        if host_port and host_port in occupied_ports and host_port not in allowed_ports:
            append_diagnostic(
                diagnostics,
                scope="vm",
                severity="error",
                code="port_conflict",
                summary=f"A porta {host_port} ja esta ocupada na VM.",
                suggestion="Troque o range de portas do projeto ou libere a porta antes do deploy.",
                evidence=[service.get("service_name", "")],
            )


def analyze_repo(
    repo_path: str | Path,
    *,
    project_name: str = "",
    project_id: str = "",
    port_base: int = 3000,
    default_domain: str = "",
    default_base_path: str = "/",
    vm_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(repo_path).expanduser().resolve(strict=False)
    diagnostics: list[dict[str, Any]] = []

    if not root.exists():
        append_diagnostic(
            diagnostics,
            scope="repository",
            severity="error",
            code="repo_missing",
            summary="O caminho do repositorio nao existe na VM.",
            suggestion="Corrija o caminho local do projeto antes de ativar o webhook.",
            evidence=[str(root)],
        )
        return {
            "analysis_version": ANALYZER_VERSION,
            "generated_at": utc_now_iso(),
            "status": "blocked",
            "repository": {
                "path": str(root),
                "exists": False,
            },
            "classification": {
                "repo_kind": "unknown",
                "monorepo": False,
                "deployable_components": 0,
                "support_packages": 0,
                "primary_stack": ["unknown"],
            },
            "brief": {
                "headline": project_name or root.name or "Projeto",
                "what_it_is": "Repositorio ausente.",
                "what_it_does": "Nao foi possivel analisar o projeto.",
                "purpose": "Corrija o caminho local para continuar.",
            },
            "components": [],
            "support_packages": [],
            "files": {"top_level_entries": [], "candidate_roots": [], "manifests": {}},
            "deployment_plan": {
                "port_base": port_base,
                "services": [],
                "routes": [],
                "reverse_proxy_required": False,
                "compose_recommended": False,
            },
            "diagnostics": diagnostics,
        }

    package_manager = detect_package_manager(root)
    candidate_roots = discover_candidate_roots(root)
    readme = read_readme(root)
    components = [analyze_component(candidate, root, package_manager) for candidate in candidate_roots]
    components = assign_ports(components, port_base=port_base)
    support_packages = [item for item in components if item.get("type") in {"library", "orchestrator"}]
    deployable_components = [item for item in components if item.get("deployable")]
    classification = classify_repo_kind(components, root)
    brief = derive_brief(project_name or root.name, root, readme, classification, components)
    deployment_plan = build_deployment_plan(
        project_id or slugify(project_name or root.name, fallback="project"),
        components,
        port_base=port_base,
        default_domain=default_domain,
        default_base_path=default_base_path,
    )

    if not detect_root_manifest(root).get("git"):
        append_diagnostic(
            diagnostics,
            scope="repository",
            severity="warning",
            code="missing_git_metadata",
            summary="O diretorio analisado nao parece ser um clone Git completo.",
            suggestion="Confirme se a VM esta apontando para um checkout valido do repositorio.",
        )
    if not readme.get("file"):
        append_diagnostic(
            diagnostics,
            scope="repository",
            severity="info",
            code="missing_readme",
            summary="Nao foi encontrado README util para explicar o projeto.",
            suggestion="Adicionar README melhora onboarding, diagnostico e a camada de IA do dashboard.",
        )
    if not deployable_components:
        append_diagnostic(
            diagnostics,
            scope="repository",
            severity="error",
            code="no_deployable_components",
            summary="Nenhum componente claramente implantavel foi identificado.",
            suggestion="Adicione scripts de build/start, Dockerfile ou um manifesto .redvm/project.json para orientar o sistema.",
        )

    for component in components:
        if component.get("type") == "frontend" and component.get("deployable") and not component.get("build_command") and not component.get("has_dockerfile"):
            append_diagnostic(
                diagnostics,
                scope="repository",
                severity="error",
                code="frontend_without_build",
                summary=f"O componente {component.get('name')} parece frontend, mas nao tem build claro nem Dockerfile.",
                suggestion="Adicione script build ou Dockerfile no componente frontend.",
                evidence=[component.get("rel_path", ".")],
            )
        if component.get("type") == "backend" and component.get("deployable") and not component.get("start_command") and not component.get("has_dockerfile"):
            append_diagnostic(
                diagnostics,
                scope="repository",
                severity="warning",
                code="backend_without_start",
                summary=f"O componente {component.get('name')} nao expoe comando de start claro.",
                suggestion="Defina script start ou Dockerfile para tornar o deploy mais deterministico.",
                evidence=[component.get("rel_path", ".")],
            )
        if component.get("language") == "node" and component.get("deployable") and not component.get("has_lockfile"):
            append_diagnostic(
                diagnostics,
                scope="repository",
                severity="warning",
                code="node_without_lockfile",
                summary=f"O componente {component.get('name')} nao trouxe lockfile proximo do contexto de build.",
                suggestion="Mantenha lockfile versionado para builds reproduziveis.",
                evidence=[component.get("rel_path", ".")],
            )
        if component.get("deployable") and not component.get("env_hints"):
            append_diagnostic(
                diagnostics,
                scope="repository",
                severity="info",
                code="missing_env_example",
                summary=f"O componente {component.get('name')} nao expoe .env.example claro.",
                suggestion="Adicionar arquivo de exemplo ajuda a distinguir erro de repo versus erro de montagem.",
                evidence=[component.get("rel_path", ".")],
            )

    analyze_vm_fit(diagnostics, deployment_plan, vm_context)

    error_count = sum(1 for item in diagnostics if item.get("severity") == "error")
    warning_count = sum(1 for item in diagnostics if item.get("severity") == "warning")
    status = "ready"
    if error_count:
        status = "blocked"
    elif warning_count:
        status = "needs-attention"

    return {
        "analysis_version": ANALYZER_VERSION,
        "generated_at": utc_now_iso(),
        "status": status,
        "repository": {
            "path": str(root),
            "exists": True,
            "name": root.name,
            "package_manager": package_manager,
            "readme": readme,
        },
        "classification": classification,
        "brief": brief,
        "components": components,
        "support_packages": support_packages,
        "files": build_files_summary(root, candidate_roots),
        "deployment_plan": deployment_plan,
        "diagnostics": diagnostics,
        "scores": {
            "errors": error_count,
            "warnings": warning_count,
            "deployable_components": len(deployable_components),
        },
    }


def bundle_yaml_quote(value: Any) -> str:
    text = str(value if value is not None else "")
    return json.dumps(text, ensure_ascii=False)


def bundle_install_command(component: dict[str, Any]) -> str:
    override = str(component.get("override_install_command", "") or "").strip()
    if override:
        return override
    runtime = component.get("runtime")
    manager = component.get("package_manager")
    if runtime == "node":
        if manager == "pnpm":
            return "corepack enable && pnpm install --frozen-lockfile"
        if manager == "yarn":
            return "corepack enable && yarn install --frozen-lockfile"
        if manager == "bun":
            return "bun install --frozen-lockfile"
        return "npm ci"
    if runtime == "python":
        if "requirements.txt" in component.get("evidence", []):
            return "python -m pip install -r requirements.txt"
        return component.get("build_command") or "python -m pip install ."
    return ""


def bundle_static_output(component: dict[str, Any]) -> str:
    rel_path = component.get("rel_path", ".")
    if "next" in component.get("frameworks", []):
        return f"/workspace/{rel_path}/.next"
    if "react-scripts" in component.get("frameworks", []):
        return f"/workspace/{rel_path}/build"
    return f"/workspace/{rel_path}/dist"


def generate_component_dockerfile(component: dict[str, Any], repo_path: str) -> tuple[str, str]:
    rel_path = component.get("rel_path", ".")
    runtime = component.get("runtime")
    frameworks = component.get("frameworks", [])
    install_command = bundle_install_command(component)
    build_command = component.get("build_command", "")
    start_command = component.get("start_command", "")
    port = component.get("container_port")

    if runtime == "node" and component.get("type") == "frontend" and "next" not in frameworks:
        lines = [
            "FROM node:20-alpine AS build",
            "WORKDIR /workspace",
            "COPY . .",
        ]
        if install_command:
            lines.append(f"RUN {install_command}")
        if build_command:
            lines.append(f"RUN {build_command}")
        lines.extend(
            [
                "FROM nginx:1.27-alpine",
                f"COPY --from=build {bundle_static_output(component)} /usr/share/nginx/html",
                "EXPOSE 80",
                'CMD ["nginx", "-g", "daemon off;"]',
            ]
        )
        return ("\n".join(lines) + "\n", "generated")

    if runtime == "node":
        lines = [
            "FROM node:20-alpine",
            "WORKDIR /workspace",
            "COPY . .",
        ]
        if install_command:
            lines.append(f"RUN {install_command}")
        if build_command:
            lines.append(f"RUN {build_command}")
        if port:
            lines.append(f"EXPOSE {port}")
        lines.append(f'CMD ["sh", "-lc", {json.dumps(start_command or "node .")}]')
        return ("\n".join(lines) + "\n", "generated")

    if runtime == "python":
        lines = [
            "FROM python:3.12-slim",
            "WORKDIR /workspace",
            "COPY . .",
            "RUN python -m pip install --upgrade pip",
        ]
        if (Path(repo_path) / rel_path / "requirements.txt").exists():
            lines.append(f"RUN cd {rel_path} && python -m pip install -r requirements.txt")
        else:
            lines.append(f"RUN cd {rel_path} && python -m pip install .")
        if port:
            lines.append(f"EXPOSE {port}")
        lines.append(f'CMD ["sh", "-lc", {json.dumps(start_command or f"cd {rel_path} && python main.py")}]')
        return ("\n".join(lines) + "\n", "generated")

    if runtime == "go":
        lines = [
            "FROM golang:1.24-alpine AS build",
            "WORKDIR /workspace",
            "COPY . .",
            f"RUN cd {rel_path} && go build -o /tmp/app .",
            "FROM alpine:3.20",
            "WORKDIR /app",
            "COPY --from=build /tmp/app /app/app",
        ]
        if port:
            lines.append(f"EXPOSE {port}")
        lines.append('CMD ["/app/app"]')
        return ("\n".join(lines) + "\n", "generated")

    if runtime == "rust":
        lines = [
            "FROM rust:1.87-slim AS build",
            "WORKDIR /workspace",
            "COPY . .",
            f"RUN cd {rel_path} && cargo build --release",
            "FROM debian:bookworm-slim",
            "WORKDIR /app",
            f"COPY --from=build /workspace/{rel_path}/target/release/{component.get('name') or 'app'} /app/app",
        ]
        if port:
            lines.append(f"EXPOSE {port}")
        lines.append('CMD ["/app/app"]')
        return ("\n".join(lines) + "\n", "generated")

    lines = [
        "FROM alpine:3.20",
        "WORKDIR /workspace",
        "COPY . .",
        'CMD ["sh", "-lc", "echo Ajuste este Dockerfile gerado manualmente para o componente. && sleep infinity"]',
    ]
    return ("\n".join(lines) + "\n", "manual")


def build_compose_content(project: dict[str, Any], analysis: dict[str, Any], bundle_root: str) -> str:
    services = analysis.get("deployment_plan", {}).get("services", [])
    project_id = slugify(str(project.get("id") or project.get("name") or "project"), fallback="project")
    lines = ['services:']
    for service in services:
        component = next((item for item in analysis.get("components", []) if item.get("id") == service.get("component_id")), {})
        dockerfile_path = f"{bundle_root}/dockerfiles/{service.get('service_name')}.Dockerfile"
        context_path = str(Path(project.get("repo_path", "")).resolve(strict=False))
        image_name = f"redvm/{project_id}/{service.get('service_name')}:${{REDVM_RELEASE_ID:-manual}}"
        lines.append(f"  {service.get('service_name')}:")
        lines.append(f"    container_name: {service.get('service_name')}")
        lines.append(f"    image: {bundle_yaml_quote(image_name)}")
        lines.append("    build:")
        lines.append(f"      context: {bundle_yaml_quote(context_path)}")
        if component.get("has_dockerfile"):
            native_path = str((Path(project.get("repo_path", "")) / component.get("rel_path", ".") / "Dockerfile").resolve(strict=False))
            lines.append(f"      dockerfile: {bundle_yaml_quote(native_path)}")
        else:
            lines.append(f"      dockerfile: {bundle_yaml_quote(dockerfile_path)}")
        lines.append(f"    restart: unless-stopped")
        if service.get("host_port") and service.get("container_port"):
            port_mapping = f"127.0.0.1:{service.get('host_port')}:{service.get('container_port')}"
            lines.append("    ports:")
            lines.append(f"      - {bundle_yaml_quote(port_mapping)}")
        env_hints = service.get("env_hints") or []
        if env_hints:
            lines.append("    environment:")
            for env_name in env_hints:
                lines.append(f"      {env_name}: ${{{env_name}:-}}")
        health_path = service.get("health_path")
        if health_path and service.get("container_port"):
            health_command = f"curl -fsS http://127.0.0.1:{service.get('container_port')}{health_path} || exit 1"
            lines.append("    healthcheck:")
            lines.append(f"      test: {bundle_yaml_quote(health_command)}")
            lines.append("      interval: 20s")
            lines.append("      timeout: 5s")
            lines.append("      retries: 3")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_env_example_content(analysis: dict[str, Any]) -> str:
    names: list[str] = []
    for component in analysis.get("components", []):
        for env_name in component.get("env_hints", []):
            names.append(str(env_name))
    names = sorted(dict.fromkeys(names))
    if not names:
        names = ["APP_ENV", "LOG_LEVEL"]
    lines = ["# Variaveis sugeridas para este projeto"]
    lines.extend(f"{name}=" for name in names)
    return "\n".join(lines).rstrip() + "\n"


def build_nginx_content(project: dict[str, Any], analysis: dict[str, Any]) -> str:
    routes = analysis.get("deployment_plan", {}).get("routes", [])
    domain = project.get("default_domain") or "_"
    lines = ["server {", "    listen 80;", f"    server_name {domain};", ""]
    if not routes:
        lines.extend(["    location / {", "        return 404;", "    }", "}"])
        return "\n".join(lines) + "\n"

    for route in routes:
        path = route.get("path") or "/"
        port = route.get("target_host_port")
        if not port:
            continue
        lines.extend(
            [
                f"    location {path} {{",
                f"        proxy_pass http://127.0.0.1:{port};",
                "        proxy_set_header Host $host;",
                "        proxy_set_header X-Real-IP $remote_addr;",
                "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
                "        proxy_set_header X-Forwarded-Proto $scheme;",
                "    }",
                "",
            ]
        )
    lines.append("}")
    return "\n".join(lines).rstrip() + "\n"


def build_webhook_instruction_content(project: dict[str, Any], public_base_url: str) -> str:
    webhook_path = project.get("webhook", {}).get("path") or f"/hooks/github/{project.get('id')}"
    webhook_url = project.get("webhook", {}).get("url") or f"{public_base_url.rstrip('/')}{webhook_path}"
    secret = project.get("webhook", {}).get("secret") or project.get("webhook_secret", "")
    repo_url = project.get("repo_url", "")
    branch = project.get("branch", "main")
    return (
        "Configuracao recomendada do webhook GitHub\n"
        f"- Repositorio: {repo_url or 'preencher no GitHub'}\n"
        f"- URL: {webhook_url}\n"
        "- Content-Type: application/json\n"
        f"- Secret: {secret}\n"
        "- Eventos: Just the push event\n"
        f"- Branch monitorada na VM: {branch}\n"
    )


def build_manifest_content(project: dict[str, Any], analysis: dict[str, Any]) -> str:
    payload = {
        "project_id": project.get("id"),
        "name": project.get("name"),
        "repo_path": project.get("repo_path"),
        "branch": project.get("branch"),
        "default_domain": project.get("default_domain"),
        "default_base_path": project.get("default_base_path"),
        "port_base": project.get("port_base"),
        "components": [
            {
                "id": item.get("id"),
                "rel_path": item.get("rel_path"),
                "type": item.get("type"),
                "language": item.get("language"),
                "host_port": item.get("host_port"),
                "container_port": item.get("container_port"),
            }
            for item in analysis.get("components", [])
            if item.get("deployable")
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def generate_deploy_bundle(project: dict[str, Any], analysis: dict[str, Any], *, bundle_root: str, public_base_url: str = "") -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    repo_path = str(project.get("repo_path", ""))
    for service in analysis.get("deployment_plan", {}).get("services", []):
        component = next((item for item in analysis.get("components", []) if item.get("id") == service.get("component_id")), {})
        if component.get("has_dockerfile"):
            source_path = str((Path(repo_path) / component.get("rel_path", ".") / "Dockerfile").resolve(strict=False))
            artifacts.append(
                {
                    "kind": "dockerfile",
                    "name": f"{service.get('service_name')}.Dockerfile",
                    "path_hint": source_path,
                    "mode": "native",
                    "content": safe_read_text(Path(source_path), limit=120_000),
                }
            )
            continue
        content, mode = generate_component_dockerfile(component, repo_path)
        artifacts.append(
            {
                "kind": "dockerfile",
                "name": f"{service.get('service_name')}.Dockerfile",
                "path_hint": f"{bundle_root}/dockerfiles/{service.get('service_name')}.Dockerfile",
                "mode": mode,
                "content": content,
            }
        )

    compose_content = build_compose_content(project, analysis, bundle_root)
    nginx_content = build_nginx_content(project, analysis)
    env_content = build_env_example_content(analysis)
    webhook_content = build_webhook_instruction_content(project, public_base_url)
    manifest_content = build_manifest_content(project, analysis)

    artifacts.extend(
        [
            {
                "kind": "compose",
                "name": "docker-compose.generated.yml",
                "path_hint": f"{bundle_root}/docker-compose.generated.yml",
                "mode": "generated",
                "content": compose_content,
            },
            {
                "kind": "nginx",
                "name": "nginx.generated.conf",
                "path_hint": f"{bundle_root}/nginx.generated.conf",
                "mode": "generated",
                "content": nginx_content,
            },
            {
                "kind": "env",
                "name": ".env.example",
                "path_hint": f"{bundle_root}/.env.example",
                "mode": "generated",
                "content": env_content,
            },
            {
                "kind": "manifest",
                "name": "project.generated.json",
                "path_hint": f"{bundle_root}/project.generated.json",
                "mode": "generated",
                "content": manifest_content,
            },
            {
                "kind": "webhook",
                "name": "webhook.github.txt",
                "path_hint": f"{bundle_root}/webhook.github.txt",
                "mode": "generated",
                "content": webhook_content,
            },
        ]
    )

    return {
        "generated_at": utc_now_iso(),
        "bundle_root": bundle_root,
        "artifacts": artifacts,
        "summary": {
            "compose_services": len(analysis.get("deployment_plan", {}).get("services", [])),
            "public_routes": len(analysis.get("deployment_plan", {}).get("routes", [])),
            "dockerfiles_generated": sum(1 for item in artifacts if item.get("kind") == "dockerfile" and item.get("mode") == "generated"),
            "dockerfiles_native": sum(1 for item in artifacts if item.get("kind") == "dockerfile" and item.get("mode") == "native"),
        },
        "install_steps": [
            f"Criar diretorio de bundle em {bundle_root}",
            "Gravar os arquivos gerados do bundle nesse diretorio",
            f"Revisar as variaveis em {bundle_root}/.env.example",
            f"Subir com docker compose -f {bundle_root}/docker-compose.generated.yml up -d --build",
            f"Publicar {bundle_root}/nginx.generated.conf no Nginx central",
            "Adicionar o webhook no GitHub com o secret gerado pelo dashboard",
        ],
    }
