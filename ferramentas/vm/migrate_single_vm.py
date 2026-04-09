#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import os
import posixpath
import shlex
import socket
import sys
import time
from pathlib import Path

import paramiko


sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


REPO_URL = "https://github.com/ronaldsilva490-rgb/redvminfra.git"
BRANCH = "main"
REPO_ROOT = Path(__file__).resolve().parents[2]

SOURCE1_ARCHIVES = [
    ("source1-runtime.tar", [
        "/opt/redvm-dashboard/data",
        "/var/lib/redvm-proxy",
        "/opt/redvm-projects",
        "/opt/redvm-samples",
        "/var/www/red-portal",
        "/opt/rapidleech",
    ]),
]

SOURCE2_ARCHIVES = [
    ("source2-app-data.tar", [
        "/opt/redia/data",
        "/opt/redtrader/data",
        "/opt/red-proxy-lab/data",
        "/opt/red-proxy-lab/results",
        "/opt/red-proxy-lab/results_official",
    ]),
]

ENV_COPIES = [
    ("source1", "/etc/redvm-dashboard.env", "/etc/redvm-dashboard.env"),
    ("source1", "/etc/red-ollama-proxy.env", "/etc/red-ollama-proxy.env"),
    ("source2", "/opt/redia/.env", "/opt/redia/.env"),
    ("source2", "/etc/redtrader.env", "/etc/redtrader.env"),
    ("source2", "/etc/red-iq-vision-bridge.env", "/etc/red-iq-vision-bridge.env"),
]

LOCAL_SYNC_MAP = [
    ("servicos/dashboard", "/opt/redvm-dashboard"),
    ("servicos/proxy", "/opt/redvm-proxy"),
    ("servicos/redia", "/opt/redia"),
    ("servicos/redtrader", "/opt/redtrader"),
    ("servicos/proxy-lab", "/opt/red-proxy-lab"),
    ("servicos/extensao-iq-demo/bridge", "/opt/red-iq-vision-bridge"),
]

SYSTEMD_FILES = [
    "red-dashboard.service",
    "red-ollama-proxy.service",
    "redia.service",
    "redtrader.service",
    "red-proxy-lab.service",
    "red-iq-vision-bridge.service",
    "rapidleech.service",
]


class Remote:
    def __init__(self, host: str, port: int, user: str, password: str) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(
            host,
            port=port,
            username=user,
            password=password,
            timeout=20,
            banner_timeout=20,
            auth_timeout=20,
        )
        self.sftp = self.client.open_sftp()

    def close(self) -> None:
        try:
            self.sftp.close()
        finally:
            self.client.close()

    def run(self, command: str, *, timeout: int = 1800, check: bool = True) -> str:
        print(f"\n[{self.host}]$ {command}")
        exec_timeout = None if timeout <= 0 else timeout
        stdin, stdout, stderr = self.client.exec_command(command, timeout=exec_timeout)
        stdout.channel.settimeout(exec_timeout)
        stderr.channel.settimeout(exec_timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        if out.strip():
            print(out.rstrip())
        if err.strip():
            print(err.rstrip(), file=sys.stderr)
        if check and code != 0:
            raise RuntimeError(f"{self.host}: comando falhou ({code})")
        return out

    def read_file(self, remote_path: str) -> bytes:
        with self.sftp.open(remote_path, "rb") as fh:
            return fh.read()

    def write_file(self, remote_path: str, data: bytes) -> None:
        self.ensure_dir(posixpath.dirname(remote_path))
        with self.sftp.open(remote_path, "wb") as fh:
            fh.write(data)

    def ensure_dir(self, remote_dir: str) -> None:
        if not remote_dir or remote_dir == "/":
            return
        parts = []
        current = remote_dir
        while current not in ("", "/"):
            parts.append(current)
            current = posixpath.dirname(current)
        for path in reversed(parts):
            try:
                self.sftp.stat(path)
            except FileNotFoundError:
                self.sftp.mkdir(path)


def stream_tar_between_remotes(source: Remote, target: Remote, archive_name: str, paths: list[str]) -> None:
    target_cache = f"/root/migration-cache/{archive_name}"
    target.ensure_dir("/root/migration-cache")
    quoted = " ".join(shlex.quote(path.lstrip("/")) for path in paths)
    command = f"tar -C / -cf - {quoted}"
    print(f"\nStreaming {archive_name} from {source.host} to {target.host} ...")
    stdin, stdout, stderr = source.client.exec_command(command, timeout=None)
    stdout.channel.settimeout(None)
    stderr.channel.settimeout(None)
    with target.sftp.open(target_cache, "wb") as remote_out:
        transferred = 0
        while True:
            chunk = stdout.channel.recv(1024 * 1024)
            if not chunk:
                break
            remote_out.write(chunk)
            transferred += len(chunk)
            if transferred and transferred % (256 * 1024 * 1024) < len(chunk):
                print(f"  {archive_name}: {transferred / (1024 ** 3):.2f} GiB")
    stderr_text = stderr.read().decode("utf-8", errors="replace")
    exit_code = stdout.channel.recv_exit_status()
    if stderr_text.strip():
        print(stderr_text.rstrip(), file=sys.stderr)
    if exit_code != 0:
        raise RuntimeError(f"Falha ao criar stream tar {archive_name} em {source.host}")
    target.run(f"tar -C / -xf {shlex.quote(target_cache)}", timeout=0)


def upload_file(target: Remote, local_path: Path, remote_path: str) -> None:
    data = local_path.read_bytes()
    print(f"Uploading {local_path} -> {remote_path}")
    target.write_file(remote_path, data)


def patch_env_file(target: Remote, remote_path: str, updates: dict[str, str]) -> None:
    raw = target.read_file(remote_path).decode("utf-8", errors="replace").splitlines()
    found: set[str] = set()
    result: list[str] = []
    for line in raw:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            result.append(line)
            continue
        key, _value = line.split("=", 1)
        if key in updates:
            result.append(f"{key}={updates[key]}")
            found.add(key)
        else:
            result.append(line)
    for key, value in updates.items():
        if key not in found:
            result.append(f"{key}={value}")
    target.write_file(remote_path, ("\n".join(result).rstrip() + "\n").encode("utf-8"))


def read_redtrader_unit_env(source2: Remote) -> dict[str, str]:
    output = source2.run(
        "grep -E '^Environment=REDTRADER_(PASSWORD|SECRET)=' /etc/systemd/system/redtrader.service",
        timeout=120,
    )
    values: dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("Environment=REDTRADER_"):
            continue
        payload = line[len("Environment="):]
        key, value = payload.split("=", 1)
        values[key] = value
    return values


def install_packages(target: Remote) -> None:
    target.run(
        "export DEBIAN_FRONTEND=noninteractive; "
        "apt-get update && apt-get install -y "
        "git rsync nginx nodejs npm sqlite3 ffmpeg php-cli "
        "python3-venv python3-pip build-essential pkg-config ca-certificates curl",
        timeout=0,
    )
    target.run(
        "NODE_MAJOR=$(node -v 2>/dev/null | sed 's/^v//' | cut -d. -f1 || echo 0); "
        "if [ \"${NODE_MAJOR:-0}\" -lt 20 ]; then "
        "curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && "
        "export DEBIAN_FRONTEND=noninteractive && apt-get install -y nodejs; "
        "fi",
        timeout=0,
    )


def backup_target(target: Remote) -> None:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target.run(
        "mkdir -p /root/backups && "
        f"mkdir -p /root/backups/redvm-pre-migration-{stamp} && "
        f"tar -C / -czf /root/backups/redvm-pre-migration-{stamp}/system.tar.gz "
        "etc/systemd/system etc/nginx 2>/dev/null || true",
        timeout=0,
        check=False,
    )


def checkout_repo(target: Remote) -> None:
    target.run(
        "if [ -d /opt/redvm-repo/.git ]; then "
        f"git -C /opt/redvm-repo fetch origin {BRANCH} && git -C /opt/redvm-repo reset --hard origin/{BRANCH}; "
        f"else git clone --branch {BRANCH} {shlex.quote(REPO_URL)} /opt/redvm-repo; fi",
        timeout=0,
    )


def sync_repo_runtime(target: Remote) -> None:
    for local_rel, remote_dir in LOCAL_SYNC_MAP:
        repo_dir = f"/opt/redvm-repo/{local_rel.replace(os.sep, '/')}"
        exclude = [
            "--exclude", ".venv",
            "--exclude", "node_modules",
            "--exclude", "__pycache__",
            "--exclude", ".pytest_cache",
            "--exclude", ".codex-backups",
            "--exclude", "data",
            "--exclude", "results",
            "--exclude", "results_official",
        ]
        target.run(f"mkdir -p {shlex.quote(remote_dir)}", check=False)
        target.run(
            "rsync -a --delete "
            + " ".join(exclude)
            + f" {shlex.quote(repo_dir)}/ {shlex.quote(remote_dir)}/",
            timeout=0,
        )
    target.run("mkdir -p /var/www/red-portal /etc/nginx/redvm-routes")
    target.run(
        "install -m 0644 /opt/redvm-repo/infraestrutura/nginx/red-dashboard.nginx.conf "
        "/etc/nginx/conf.d/red-dashboard.conf"
    )
    target.run(
        "install -m 0644 /opt/redvm-repo/infraestrutura/nginx/red-friendly-paths.nginx.conf "
        "/etc/nginx/redvm-routes/friendly-paths.conf"
    )
    for unit in SYSTEMD_FILES:
        target.run(
            f"install -m 0644 /opt/redvm-repo/infraestrutura/systemd/{shlex.quote(unit)} "
            f"/etc/systemd/system/{shlex.quote(unit)}"
        )


def setup_runtime(target: Remote) -> None:
    target.run("rm -f /etc/nginx/sites-enabled/default", check=False)
    target.run("python3 -m venv /opt/redvm-dashboard/.venv && /opt/redvm-dashboard/.venv/bin/pip install --upgrade pip setuptools wheel && /opt/redvm-dashboard/.venv/bin/pip install -r /opt/redvm-dashboard/requirements.txt", timeout=0)
    target.run("python3 -m venv /opt/redvm-proxy/.venv && /opt/redvm-proxy/.venv/bin/pip install --upgrade pip setuptools wheel && /opt/redvm-proxy/.venv/bin/pip install -r /opt/redvm-proxy/requirements.txt", timeout=0)
    target.run("python3 -m venv /opt/redtrader/.venv && /opt/redtrader/.venv/bin/pip install --upgrade pip setuptools wheel && /opt/redtrader/.venv/bin/pip install -r /opt/redtrader/requirements.txt", timeout=0)
    target.run("python3 -m venv /opt/red-proxy-lab/.venv && /opt/red-proxy-lab/.venv/bin/pip install --upgrade pip setuptools wheel && /opt/red-proxy-lab/.venv/bin/pip install -r /opt/red-proxy-lab/requirements.txt", timeout=0)
    target.run("python3 -m venv /opt/red-iq-vision-bridge/.venv && /opt/red-iq-vision-bridge/.venv/bin/pip install --upgrade pip setuptools wheel && /opt/red-iq-vision-bridge/.venv/bin/pip install -r /opt/red-iq-vision-bridge/requirements.txt", timeout=0)
    target.run("cd /opt/redia && npm install --omit=dev", timeout=0)
    target.run("mkdir -p /opt/redia/data /opt/redtrader/data /opt/red-proxy-lab/data /opt/red-proxy-lab/results /opt/red-proxy-lab/results_official /opt/red-iq-vision-bridge/data /var/lib/redvm-proxy /opt/redvm-projects /var/www/red-portal")


def enable_services(target: Remote) -> None:
    target.run("systemctl daemon-reload")
    target.run("systemctl enable nginx red-dashboard.service red-ollama-proxy.service redia.service redtrader.service red-proxy-lab.service red-iq-vision-bridge.service rapidleech.service", timeout=0)
    target.run("nginx -t", timeout=120)
    target.run("systemctl restart nginx red-dashboard.service red-ollama-proxy.service redia.service redtrader.service red-proxy-lab.service red-iq-vision-bridge.service rapidleech.service", timeout=0)


def validate(target: Remote) -> None:
    target.run(
        "systemctl --no-pager --full status "
        "nginx red-dashboard.service red-ollama-proxy.service redia.service redtrader.service "
        "red-proxy-lab.service red-iq-vision-bridge.service rapidleech.service | sed -n '1,220p'",
        timeout=0,
        check=False,
    )
    target.run(
        "curl -fsS http://127.0.0.1:9001/ >/dev/null && echo dashboard=ok; "
        "curl -fsS http://127.0.0.1:8080/api/tags >/dev/null && echo proxy=ok; "
        "curl -fsS http://127.0.0.1:3099/ >/dev/null && echo redia=ok; "
        "curl -fsS http://127.0.0.1:3100/healthz >/dev/null && echo redtrader=ok; "
        "curl -fsS http://127.0.0.1:3115/healthz >/dev/null && echo iqbridge=ok; "
        "curl -fsS http://127.0.0.1:8090/healthz >/dev/null && echo proxylab=ok",
        timeout=300,
        check=False,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Migra RED Systems para uma VM unica.")
    p.add_argument("--source1-host", required=True)
    p.add_argument("--source1-port", type=int, required=True)
    p.add_argument("--source1-user", required=True)
    p.add_argument("--source1-password", required=True)
    p.add_argument("--source2-host", required=True)
    p.add_argument("--source2-port", type=int, required=True)
    p.add_argument("--source2-user", required=True)
    p.add_argument("--source2-password", required=True)
    p.add_argument("--target-host", required=True)
    p.add_argument("--target-port", type=int, required=True)
    p.add_argument("--target-user", required=True)
    p.add_argument("--target-password", required=True)
    return p


def main() -> int:
    args = build_parser().parse_args()

    source1 = Remote(args.source1_host, args.source1_port, args.source1_user, args.source1_password)
    source2 = Remote(args.source2_host, args.source2_port, args.source2_user, args.source2_password)
    target = Remote(args.target_host, args.target_port, args.target_user, args.target_password)
    try:
        backup_target(target)
        install_packages(target)
        checkout_repo(target)
        sync_repo_runtime(target)
        setup_runtime(target)

        redtrader_unit_env = read_redtrader_unit_env(source2)
        source2.run(
            "systemctl stop redia.service redtrader.service red-proxy-lab.service red-iq-vision-bridge.service",
            timeout=300,
            check=False,
        )

        for archive_name, paths in SOURCE1_ARCHIVES:
            stream_tar_between_remotes(source1, target, archive_name, paths)
        for archive_name, paths in SOURCE2_ARCHIVES:
            stream_tar_between_remotes(source2, target, archive_name, paths)

        for source_name, source_path, target_path in ENV_COPIES:
            remote = source1 if source_name == "source1" else source2
            print(f"Copying env {source_path} -> {target_path}")
            target.write_file(target_path, remote.read_file(source_path))

        patch_env_file(target, "/opt/redia/.env", {"REDIA_PROXY_URL": "http://127.0.0.1:8080"})
        patch_env_file(
            target,
            "/etc/redtrader.env",
            {
                "REDIA_NOTIFY_URL": "http://127.0.0.1:3099/api/internal/notify-whatsapp",
                "REDTRADER_PASSWORD": redtrader_unit_env.get("REDTRADER_PASSWORD", ""),
                "REDTRADER_SECRET": redtrader_unit_env.get("REDTRADER_SECRET", ""),
            },
        )

        enable_services(target)
        validate(target)
        print("\nMigracao concluida.")
        return 0
    finally:
        for remote in (source1, source2, target):
            remote.close()


if __name__ == "__main__":
    raise SystemExit(main())
