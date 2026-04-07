#!/usr/bin/env python3
"""
Webhook Listener v3 — AI-Powered Deploy System
Flask porta 9000. Recebe webhooks do GitHub, analisa projetos com IA
e faz deploy automático com rollback, lock e health check.

Sem templates de Dockerfile. A IA decide tudo.
"""

import hmac
import hashlib
import subprocess
import json
import os
import sys
import threading
import requests
import time
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
import logging

# ============ PATH DO DETECTOR V3 ============
sys.path.insert(0, '/root/red-deploy/smart-deploy')
try:
    from project_detector_v3 import analyze_project
except ImportError:
    # Fallback: tentar path alternativo
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'smart-deploy'))
    from project_detector_v3 import analyze_project

from flask import Flask, request, jsonify

app = Flask(__name__)

# ============ CONFIGURAÇÃO ============
WEBHOOK_SECRET = os.getenv("RED_WEBHOOK_SECRET", "change-me")
REPO_PATH = os.getenv("RED_DEPLOY_REPO_PATH", "/root/Tapp")
LOG_PATH = os.getenv("RED_DEPLOY_LOG_PATH", "/var/log/red-deploy")
CONFIG_PATH = os.getenv("RED_DEPLOY_CONFIG_PATH", "/root/red-deploy/config")
PORT_MAPPING_FILE = os.getenv("RED_DEPLOY_PORT_MAPPING_FILE", "/root/red-deploy/port_mapping.json")
BASE_PORT_START = int(os.getenv("RED_DEPLOY_BASE_PORT", "2580"))
DB_PASSWORD = os.getenv("RED_DEPLOY_DB_PASSWORD", "change-me")

# ============ LOGGING COM ROTAÇÃO ============
os.makedirs(LOG_PATH, exist_ok=True)
os.makedirs(CONFIG_PATH, exist_ok=True)

logger = logging.getLogger("red-deploy")
logger.setLevel(logging.INFO)

_handler = RotatingFileHandler(
    os.path.join(LOG_PATH, "deploy.log"),
    maxBytes=5 * 1024 * 1024,  # 5MB
    backupCount=3,
    encoding="utf-8"
)
_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))

_console = logging.StreamHandler(sys.stdout)
_console.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))

logger.addHandler(_handler)
logger.addHandler(_console)


def log(msg: str):
    logger.info(msg)


# ============ DEPLOY LOCK ============
class DeployLock:
    """Mutex por container. Impede builds concorrentes no mesmo container."""

    def __init__(self):
        self._locks: dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()

    def _get_lock(self, container_name: str) -> threading.Lock:
        with self._meta_lock:
            if container_name not in self._locks:
                self._locks[container_name] = threading.Lock()
            return self._locks[container_name]

    def acquire(self, container_name: str, timeout: float = 5.0) -> bool:
        lock = self._get_lock(container_name)
        acquired = lock.acquire(blocking=True, timeout=timeout)
        return acquired

    def release(self, container_name: str):
        lock = self._get_lock(container_name)
        try:
            lock.release()
        except RuntimeError:
            pass  # Já estava liberado


deploy_lock = DeployLock()


# ============ PORT MAPPING ============
def load_port_mapping() -> dict:
    if os.path.exists(PORT_MAPPING_FILE):
        try:
            with open(PORT_MAPPING_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_port_mapping(mapping: dict):
    os.makedirs(os.path.dirname(PORT_MAPPING_FILE), exist_ok=True)
    with open(PORT_MAPPING_FILE, "w") as f:
        json.dump(mapping, f, indent=2)


def get_next_available_port(port_mapping: dict) -> int:
    if not port_mapping:
        return BASE_PORT_START
    used_ports = [info["base_port"] for info in port_mapping.values()]
    return max(used_ports) + 10


# ============ FIREWALL ============
def open_firewall_port(port: int):
    try:
        subprocess.run(["ufw", "allow", str(port)], capture_output=True, timeout=10)
        log(f"Firewall: porta {port} aberta")
    except Exception as e:
        log(f"Aviso: não foi possível abrir porta {port} no firewall: {e}")


# ============ DATABASE ============
def ensure_database_exists(dev_name: str):
    try:
        result = subprocess.run(
            ["sudo", "-u", "postgres", "psql", "-tAc",
             f"SELECT 1 FROM pg_database WHERE datname='{dev_name}'"],
            capture_output=True, text=True, timeout=15
        )
        if "1" not in result.stdout:
            log(f"Criando database PostgreSQL: {dev_name}")
            subprocess.run(
                ["sudo", "-u", "postgres", "psql", "-c",
                 f"CREATE USER {dev_name} WITH PASSWORD '{DB_PASSWORD}';"],
                capture_output=True, timeout=15
            )
            subprocess.run(
                ["sudo", "-u", "postgres", "psql", "-c",
                 f"CREATE DATABASE {dev_name} OWNER {dev_name};"],
                capture_output=True, timeout=15
            )
            log(f"Database {dev_name} criado")
    except Exception as e:
        log(f"Aviso: erro ao criar database {dev_name}: {e}")


# ============ APP DISCOVERY ============
def discover_apps() -> dict:
    """
    Escaneia apps/ no repo, aloca portas novas, limpa apps removidas.
    Retorna dict: { "apps/driver": { dev, base_port, ... }, ... }
    """
    apps_path = os.path.join(REPO_PATH, "apps")
    if not os.path.exists(apps_path):
        return {}

    port_mapping = load_port_mapping()
    folders = sorted([
        f for f in os.listdir(apps_path)
        if os.path.isdir(os.path.join(apps_path, f))
    ])

    # Limpar apps removidas
    removed = [name for name in list(port_mapping.keys()) if name not in folders]
    for name in removed:
        _cleanup_removed_app(name, port_mapping[name])
        del port_mapping[name]

    # Alocar portas para novas apps
    new_apps = [f for f in folders if f not in port_mapping]
    for folder in new_apps:
        base_port = get_next_available_port(port_mapping)
        port_mapping[folder] = {
            "base_port": base_port,
            "allocated_at": datetime.now().isoformat()
        }
        open_firewall_port(base_port)
        log(f"Nova app detectada: {folder} -> porta {base_port}")

    if new_apps or removed:
        save_port_mapping(port_mapping)

    # Montar dict de retorno
    discovered = {}
    for folder in folders:
        base_port = port_mapping[folder]["base_port"]
        discovered[f"apps/{folder}"] = {
            "dev": folder.lower(),
            "base_port": base_port,
        }

    return discovered


def _cleanup_removed_app(app_name: str, port_info: dict):
    dev = app_name.lower()
    container = f"{dev}-app"
    log(f"App removida: {app_name} — limpando recursos")
    subprocess.run(["docker", "stop", container], capture_output=True, timeout=30)
    subprocess.run(["docker", "rm", container], capture_output=True, timeout=30)
    subprocess.run(["docker", "rmi", container], capture_output=True, timeout=30)
    config_file = os.path.join(CONFIG_PATH, f"{dev}.json")
    if os.path.exists(config_file):
        os.remove(config_file)


# ============ DOCKER ROLLBACK ============
def tag_previous_image(container_name: str) -> bool:
    """Salva a imagem atual como :rollback antes do novo build."""
    result = subprocess.run(
        ["docker", "image", "inspect", f"{container_name}:latest"],
        capture_output=True
    )
    if result.returncode != 0:
        return False  # Não existe imagem anterior

    subprocess.run(
        ["docker", "tag", f"{container_name}:latest", f"{container_name}:rollback"],
        capture_output=True
    )
    log(f"Imagem anterior salva como {container_name}:rollback")
    return True


def rollback(container_name: str, port: int, internal_port: int, env_vars: dict) -> bool:
    """Tenta restaurar a versão anterior do container."""
    result = subprocess.run(
        ["docker", "image", "inspect", f"{container_name}:rollback"],
        capture_output=True
    )
    if result.returncode != 0:
        log(f"Sem imagem :rollback para {container_name}")
        return False

    log(f"Iniciando rollback para {container_name}...")
    subprocess.run(["docker", "stop", container_name], capture_output=True, timeout=30)
    subprocess.run(["docker", "rm", container_name], capture_output=True, timeout=30)

    run_cmd = _build_docker_run_cmd(container_name, f"{container_name}:rollback", port, internal_port, env_vars)
    result = subprocess.run(run_cmd, capture_output=True, text=True)

    if result.returncode == 0:
        log(f"Rollback OK: {container_name} restaurado")
        return True
    else:
        log(f"Rollback FALHOU: {result.stderr[:200]}")
        return False


# ============ HEALTH CHECK ============
def health_check_container(container_name: str, port: int, path: str = "/health",
                            retries: int = 3, wait_between: int = 5) -> bool:
    """Faz HTTP GET com retries. Retorna True se container responder OK."""
    url = f"http://localhost:{port}{path}"
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code < 500:
                log(f"Health check OK: {url} -> {resp.status_code}")
                return True
        except requests.exceptions.ConnectionError:
            pass
        except Exception:
            pass
        if attempt < retries:
            log(f"Health check tentativa {attempt}/{retries} falhou, aguardando {wait_between}s...")
            time.sleep(wait_between)

    log(f"Health check FALHOU após {retries} tentativas: {url}")
    return False


# ============ DOCKER RUN ============
def _build_docker_run_cmd(container_name: str, image: str, port: int,
                          internal_port: int, env_vars: dict) -> list:
    cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "-p", f"{port}:{internal_port}",
        "--add-host=host.docker.internal:host-gateway",
        "--restart", "unless-stopped",
    ]
    for key, val in env_vars.items():
        cmd += ["-e", f"{key}={val}"]
    cmd.append(image)
    return cmd


# ============ DEPLOY PIPELINE ============
def deploy_app(folder: str) -> bool:
    """
    Pipeline completo de deploy para uma app.
    1. Lock por container
    2. analyze_project() — IA decide a infra
    3. Escreve Dockerfile gerado pela IA
    4. Tag :rollback da imagem atual
    5. docker build
    6. docker stop/rm + docker run
    7. Health check (3 retries)
    8. Se falhar: rollback automático
    9. Salva config em disco
    10. Release lock
    """
    developers = discover_apps()
    if folder not in developers:
        log(f"Pasta {folder} não encontrada no repo")
        return False

    dev_info = developers[folder]
    dev = dev_info["dev"]
    base_port = dev_info["base_port"]
    container_name = f"{dev}-app"
    project_path = os.path.join(REPO_PATH, folder)

    # Verificar se a pasta existe de fato
    if not os.path.isdir(project_path):
        log(f"Pasta {project_path} não existe no disco")
        return False

    # --- Acquire lock ---
    if not deploy_lock.acquire(container_name, timeout=5):
        log(f"Deploy de {dev} ignorado: outro deploy já em andamento")
        return False

    try:
        log(f"=== DEPLOY {dev.upper()} ({folder}) porta {base_port} ===")

        # Garantir database
        ensure_database_exists(dev)

        # --- 1. Análise com IA ---
        log(f"Analisando projeto com IA...")
        config = analyze_project(
            project_path=project_path,
            app_name=dev,
            base_port=base_port,
            copy_path=folder
        )
        source = config.pop("_source", "unknown")
        log(f"Config gerada por: {source} | tipo: {config.get('project_type')} | "
            f"linguagem: {config.get('language')} | framework: {config.get('framework')}")
        if config.get("notes"):
            log(f"IA: {config['notes']}")

        # --- 2. Escrever Dockerfile ---
        dockerfile_content = config.get("dockerfile", "")
        if not dockerfile_content:
            log("Dockerfile vazio — abortando deploy")
            return False

        dockerfile_path = os.path.join(REPO_PATH, f"Dockerfile.{dev}")
        with open(dockerfile_path, "w", encoding="utf-8") as f:
            f.write(dockerfile_content)
        log(f"Dockerfile salvo: {dockerfile_path}")

        # --- 3. Tag imagem como rollback ---
        had_previous = tag_previous_image(container_name)

        # --- 4. Docker build (git pull ja foi feito no run_deploys) ---
        log(f"docker build (pode levar alguns minutos)...")
        result = subprocess.run(
            ["docker", "build", "--no-cache", "-f", dockerfile_path, "-t", container_name, "."],
            cwd=REPO_PATH,
            capture_output=True, text=True, timeout=600
        )
        if result.returncode != 0:
            log(f"Build FALHOU:\n{result.stderr[-500:]}")
            return False
        log(f"Build OK: {container_name}")

        # --- 6. Stop/remove container antigo ---
        subprocess.run(["docker", "stop", container_name], capture_output=True, timeout=30)
        subprocess.run(["docker", "rm", container_name], capture_output=True, timeout=30)

        # --- 7. Iniciar novo container ---
        internal_port = config.get("internal_port", 3000)
        env_vars = {
            "DATABASE_URL": f"postgresql://{dev}:{DB_PASSWORD}@host.docker.internal:5432/{dev}",
            "NODE_ENV": "production",
            "PORT": str(internal_port),
        }
        # Adicionar env_vars extras sugeridas pela IA (sem sobrescrever as críticas)
        for k, v in config.get("env_vars", {}).items():
            if k not in ("DATABASE_URL",):
                env_vars[k] = v

        log(f"Mapeamento de porta: {base_port} (VM) -> {internal_port} (container)")
        run_cmd = _build_docker_run_cmd(container_name, container_name, base_port, internal_port, env_vars)
        result = subprocess.run(run_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log(f"docker run FALHOU: {result.stderr[:300]}")
            if had_previous:
                rollback(container_name, base_port, internal_port, env_vars)
            return False

        log(f"Container iniciado: porta {base_port} -> {internal_port}")

        # --- 8. Health check ---
        hc = config.get("health_check", {})
        hc_path = hc.get("path", "/health")
        start_period = hc.get("start_period_seconds", 30)

        log(f"Aguardando {start_period}s para container iniciar...")
        time.sleep(start_period)

        if not health_check_container(container_name, base_port, hc_path, retries=3, wait_between=5):
            log(f"Health check falhou — iniciando rollback...")
            _save_dashboard_files(dev, config, source, container_name, base_port, had_previous,
                                  "failed", "Health check failed after 3 retries")
            if had_previous:
                subprocess.run(["docker", "stop", container_name], capture_output=True, timeout=30)
                subprocess.run(["docker", "rm", container_name], capture_output=True, timeout=30)
                rollback(container_name, base_port, internal_port, env_vars)
            return False

        # --- 9. Limpar imagem :rollback (sucesso) ---
        if had_previous:
            subprocess.run(
                ["docker", "rmi", f"{container_name}:rollback"],
                capture_output=True
            )

        # --- 10. Salvar config ---
        os.makedirs(CONFIG_PATH, exist_ok=True)
        config_file = os.path.join(CONFIG_PATH, f"{dev}.json")
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump({
                "folder": folder,
                "dev": dev,
                "base_port": base_port,
                "container": container_name,
                "config": config,
                "deployed_at": datetime.now().isoformat(),
                "source": source,
            }, f, indent=2)

        # --- 11. Salvar análise IA e report para o dashboard ---
        _save_dashboard_files(dev, config, source, container_name, base_port, had_previous, "success")

        log(f"=== DEPLOY {dev.upper()} CONCLUIDO COM SUCESSO (porta {base_port}) ===")
        return True

    except Exception as e:
        log(f"Erro inesperado no deploy de {dev}: {e}")
        _save_dashboard_files(dev, config if 'config' in dir() else {}, source if 'source' in dir() else "unknown",
                              container_name, base_port, False, "failed", str(e))
        return False
    finally:
        deploy_lock.release(container_name)


def _save_dashboard_files(dev: str, config: dict, source: str, container_name: str,
                          base_port: int, had_previous: bool, status: str, error: str = ""):
    """Gera os arquivos _ai_analysis.json e _deploy_report.json para o dashboard."""
    try:
        os.makedirs(CONFIG_PATH, exist_ok=True)
        now = datetime.now().isoformat()

        ai_analysis = {
            "type": config.get("project_type", "unknown"),
            "language": config.get("language", "unknown"),
            "framework": config.get("framework", "unknown"),
            "runtime": config.get("runtime", "unknown"),
            "entry_points": config.get("start_command", ""),
            "build_command": config.get("build_command", ""),
            "dependencies": ", ".join(config.get("depends_on", [])),
            "internal_port": config.get("internal_port", 3000),
            "health_check_path": config.get("health_check", {}).get("path", "/health"),
            "env_vars": config.get("env_vars", {}),
            "notes": config.get("notes", ""),
            "source": source,
            "recommendations": config.get("notes", ""),
            "analyzed_at": now,
        }
        with open(os.path.join(CONFIG_PATH, f"{dev}_ai_analysis.json"), "w") as f:
            json.dump(ai_analysis, f, indent=2)

        deploy_report = {
            "status": status,
            "container": container_name,
            "port": base_port,
            "dockerfile_generated": f"Dockerfile.{dev}",
            "source": source,
            "deployed_at": now,
            "health_check": "passed" if status == "success" else "failed",
            "rollback_available": had_previous,
            "error": error,
        }
        with open(os.path.join(CONFIG_PATH, f"{dev}_deploy_report.json"), "w") as f:
            json.dump(deploy_report, f, indent=2)

    except Exception as e:
        log(f"Aviso: erro ao salvar arquivos do dashboard para {dev}: {e}")


# ============ ANTI-LOOP ============
def is_auto_fix_commit(commits: list) -> bool:
    """
    Retorna True se TODOS os commits tiverem o prefixo [auto-deploy].
    Evita loop infinito quando o sistema faz git push.
    """
    if not commits:
        return False
    return all(
        c.get("message", "").startswith("[auto-deploy]")
        for c in commits
    )


# ============ WEBHOOK ROUTES ============

def verify_signature(payload_body: bytes, signature_header: str) -> bool:
    if not signature_header:
        return False
    mac = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256
    )
    expected = "sha256=" + mac.hexdigest()
    return hmac.compare_digest(expected, signature_header)


def get_changed_folders(commits: list) -> list:
    """Detecta quais subpastas de apps/ foram alteradas."""
    changed = set()
    for commit in commits:
        all_files = (
            commit.get("added", []) +
            commit.get("modified", []) +
            commit.get("removed", [])
        )
        for file_path in all_files:
            if file_path.startswith("apps/"):
                parts = file_path.split("/")
                if len(parts) >= 2 and parts[1]:
                    changed.add(f"apps/{parts[1]}")
    return list(changed)


@app.route("/webhook", methods=["POST"])
def webhook():
    # 1. Verificar HMAC
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_signature(request.data, signature):
        log("Webhook recebido com assinatura inválida!")
        return jsonify({"error": "Invalid signature"}), 401

    payload = request.json
    if not payload:
        return jsonify({"error": "Empty payload"}), 400

    # 2. Só processar push events
    event_type = request.headers.get("X-GitHub-Event")
    if event_type != "push":
        return jsonify({"message": "Event ignored"}), 200

    # 3. Extrair info do push
    ref = payload.get("ref", "")
    branch = ref.split("/")[-1] if ref else ""
    commits = payload.get("commits", [])
    pusher = payload.get("pusher", {}).get("name", "unknown")

    log(f"Webhook: branch={branch}, pusher={pusher}, commits={len(commits)}")

    # 4. Só processar branch main
    if branch != "main":
        log(f"Branch {branch} ignorada")
        return jsonify({"message": "Branch ignored"}), 200

    # 5. Anti-loop: ignorar commits com prefixo [auto-deploy]
    if is_auto_fix_commit(commits):
        log("Commits auto-deploy detectados — ignorando para evitar loop")
        return jsonify({"message": "Auto-deploy commits ignored"}), 200

    # 6. Identificar pastas alteradas
    changed_folders = get_changed_folders(commits)
    if not changed_folders:
        log("Nenhuma pasta em apps/ foi alterada")
        return jsonify({"message": "No monitored folders changed"}), 200

    log(f"Pastas alteradas: {', '.join(changed_folders)}")

    # 7. Deploy em background (responder 200 imediatamente)
    def run_deploys():
        # Git pull PRIMEIRO — antes de discover_apps, senao pastas novas nao existem no disco
        log("git pull...")
        result = subprocess.run(
            ["git", "pull"], cwd=REPO_PATH,
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            log(f"git pull falhou: {result.stderr[:300]}")
            return
        log("git pull OK")

        for folder in changed_folders:
            deploy_app(folder)

    thread = threading.Thread(target=run_deploys, daemon=True)
    thread.start()

    return jsonify({
        "message": "Deploy triggered",
        "folders": changed_folders
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "Red Deploy Webhook v3",
        "version": "3.0.0"
    }), 200


@app.route("/status", methods=["GET"])
def status():
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}"],
            capture_output=True, text=True, timeout=15
        )
        containers = []
        for line in result.stdout.strip().splitlines():
            if line:
                parts = line.split("\t")
                if len(parts) >= 2:
                    containers.append({
                        "name": parts[0],
                        "status": parts[1],
                        "ports": parts[2] if len(parts) > 2 else ""
                    })

        # Adicionar info das apps mapeadas
        port_mapping = load_port_mapping()

        return jsonify({
            "containers": containers,
            "port_mapping": port_mapping
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/deploy/<app_name>", methods=["POST"])
def manual_deploy(app_name: str):
    """Deploy manual — apenas localhost por segurança."""
    source_ip = request.remote_addr
    if source_ip not in ("127.0.0.1", "::1"):
        return jsonify({"error": "Forbidden"}), 403

    folder = f"apps/{app_name}"
    log(f"Deploy manual solicitado: {folder} (IP: {source_ip})")

    # Rodar em background
    thread = threading.Thread(
        target=deploy_app,
        args=(folder,),
        daemon=True
    )
    thread.start()

    return jsonify({"message": f"Deploy de {app_name} iniciado"}), 200


# ============ MAIN ============
if __name__ == "__main__":
    log("=== Red Deploy Webhook v3 iniciando ===")

    # Descobrir apps ao iniciar
    apps = discover_apps()
    if apps:
        log(f"Apps descobertas: {', '.join(apps.keys())}")
    else:
        log("Nenhuma app descoberta ainda (aguardando push)")

    app.run(host="0.0.0.0", port=9000, debug=False, threaded=True)
