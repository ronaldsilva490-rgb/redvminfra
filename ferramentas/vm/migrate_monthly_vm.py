#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import posixpath
import shlex
import sys
from dataclasses import dataclass
from typing import Iterable

import paramiko


sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


BASE_PACKAGES = [
    "git",
    "rsync",
    "curl",
    "nginx",
    "ufw",
    "python3",
    "python3-venv",
    "python3-pip",
    "nodejs",
    "npm",
    "ffmpeg",
    "sqlite3",
    "jq",
    "php-cli",
    "build-essential",
    "ca-certificates",
]

SERVICE_ORDER_STOP = [
    "red-seb-webhook",
    "red-seb-monitor",
    "red-openclaw",
    "red-iq-vision-bridge",
    "red-proxy-lab",
    "redtrader",
    "redia",
    "red-sebia",
    "rapidleech",
    "red-dashboard",
    "red-ollama-proxy",
    "nginx",
]

SERVICE_ORDER_START = [
    "red-ollama-proxy",
    "red-dashboard",
    "redia",
    "redtrader",
    "red-proxy-lab",
    "red-iq-vision-bridge",
    "red-openclaw",
    "red-seb-webhook",
    "red-seb-monitor",
    "red-sebia",
    "rapidleech",
    "nginx",
]

ENV_FILES = [
    "/etc/redvm-dashboard.env",
    "/etc/red-ollama-proxy.env",
    "/opt/redia/.env",
    "/etc/redtrader.env",
    "/etc/red-iq-vision-bridge.env",
    "/etc/red-openclaw.env",
    "/etc/red-seb-monitor.env",
    "/etc/red-seb-webhook.env",
    "/etc/red-sebia.env",
    "/etc/red-rapidleech.env",
]

SYSTEMD_FILES = [
    "/etc/systemd/system/red-dashboard.service",
    "/etc/systemd/system/red-ollama-proxy.service",
    "/etc/systemd/system/redia.service",
    "/etc/systemd/system/redtrader.service",
    "/etc/systemd/system/red-proxy-lab.service",
    "/etc/systemd/system/red-iq-vision-bridge.service",
    "/etc/systemd/system/red-openclaw.service",
    "/etc/systemd/system/red-seb-monitor.service",
    "/etc/systemd/system/red-seb-webhook.service",
    "/etc/systemd/system/red-sebia.service",
    "/etc/systemd/system/rapidleech.service",
]

NGINX_FILES = [
    "/etc/nginx/conf.d/red-dashboard.conf",
    "/etc/nginx/redvm-routes/red-friendly-paths.nginx.conf",
]

TARGET_PREP_COMMANDS = [
    "id -u openclaw >/dev/null 2>&1 || useradd -m -s /bin/bash openclaw",
    "mkdir -p /etc/nginx/redvm-routes /var/www/red-portal /opt/seb-remote-view /root/migration-cache",
    "rm -f /etc/nginx/sites-enabled/default /etc/nginx/conf.d/default.conf",
    "ufw allow 22/tcp || true",
    "ufw allow 80/tcp || true",
    "ufw allow 2580/tcp || true",
    "ufw --force enable || true",
]

PUBLIC_URLS = [
    "http://127.0.0.1/",
    "http://127.0.0.1/dashboard/",
    "http://127.0.0.1/proxy/",
    "http://127.0.0.1/redia/",
    "http://127.0.0.1/trader/healthz",
    "http://127.0.0.1/proxy-lab/healthz",
    "http://127.0.0.1/iq-bridge/healthz",
    "http://127.0.0.1/openclaw/",
    "http://127.0.0.1/rapidleech/",
    "http://127.0.0.1/redsebia/",
    "http://127.0.0.1/redseb/",
    "http://127.0.0.1/download",
    "http://127.0.0.1:2580/",
]


@dataclass(frozen=True)
class SyncGroup:
    name: str
    includes: tuple[str, ...]
    excludes: tuple[str, ...] = ()


PRESEED_GROUPS = [
    SyncGroup("dashboard", ("/opt/redvm-dashboard",)),
    SyncGroup("proxy", ("/opt/redvm-proxy",)),
    SyncGroup("redia", ("/opt/redia",)),
    SyncGroup("redtrader", ("/opt/redtrader",)),
    SyncGroup("proxy-lab", ("/opt/red-proxy-lab",)),
    SyncGroup(
        "iq-bridge",
        ("/opt/red-iq-vision-bridge",),
        (
            "opt/red-iq-vision-bridge/data/iq_vision_bridge.sqlite",
            "opt/red-iq-vision-bridge/data/frames",
            "opt/red-iq-vision-bridge/data/bridge.db",
        ),
    ),
    SyncGroup("openclaw-runtime", ("/opt/red-openclaw",)),
    SyncGroup("openclaw-state", ("/home/openclaw/.openclaw", "/home/openclaw/openclaw-skills")),
    SyncGroup("seb-monitor", ("/opt/red-seb-monitor",)),
    SyncGroup("redsebia", ("/opt/redsebia",)),
    SyncGroup("rapidleech", ("/opt/rapidleech",)),
    SyncGroup("repo", ("/opt/redvm-repo",)),
    SyncGroup("projects", ("/opt/redvm-projects",)),
    SyncGroup("portal", ("/var/www/red-portal",)),
]

FINAL_SYNC_GROUPS = [
    SyncGroup("redia-data", ("/opt/redia/data",)),
    SyncGroup("redtrader-data", ("/opt/redtrader/data",)),
    SyncGroup(
        "proxy-lab-data",
        ("/opt/red-proxy-lab/data", "/opt/red-proxy-lab/results", "/opt/red-proxy-lab/results_official"),
    ),
    SyncGroup("iq-motor-configs", ("/opt/red-iq-vision-bridge/data/motor_configs",)),
    SyncGroup("openclaw-state", ("/home/openclaw/.openclaw", "/home/openclaw/openclaw-skills")),
    SyncGroup("seb-downloads", ("/opt/red-seb-monitor/data/downloads",)),
    SyncGroup("redsebia-data", ("/opt/redsebia/data",)),
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
            timeout=30,
            banner_timeout=30,
            auth_timeout=30,
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


def make_remote(prefix: str, args: argparse.Namespace) -> Remote:
    return Remote(
        getattr(args, f"{prefix}_host"),
        getattr(args, f"{prefix}_port"),
        getattr(args, f"{prefix}_user"),
        getattr(args, f"{prefix}_password"),
    )


def file_exists(remote: Remote, path: str) -> bool:
    try:
        remote.sftp.stat(path)
        return True
    except FileNotFoundError:
        return False


def tar_stream(source: Remote, target: Remote, group: SyncGroup) -> None:
    target.ensure_dir("/root/migration-cache")
    archive_path = f"/root/migration-cache/{group.name}.tar"
    exclude_args = " ".join(f"--exclude={shlex.quote(pattern)}" for pattern in group.excludes)
    includes = " ".join(shlex.quote(path.lstrip("/")) for path in group.includes)
    command = f"tar -C / -cf - {exclude_args} {includes}".strip()
    print(f"\nStreaming {group.name} from {source.host} to {target.host}")
    stdin, stdout, stderr = source.client.exec_command(command, timeout=None)
    stdout.channel.settimeout(None)
    stderr.channel.settimeout(None)
    with target.sftp.open(archive_path, "wb") as remote_out:
        transferred = 0
        while True:
            chunk = stdout.channel.recv(1024 * 1024)
            if not chunk:
                break
            remote_out.write(chunk)
            transferred += len(chunk)
            if transferred and transferred % (256 * 1024 * 1024) < len(chunk):
                print(f"  {group.name}: {transferred / (1024 ** 3):.2f} GiB")
    stderr_text = stderr.read().decode("utf-8", errors="replace")
    exit_code = stdout.channel.recv_exit_status()
    if stderr_text.strip():
        print(stderr_text.rstrip(), file=sys.stderr)
    if exit_code != 0:
        raise RuntimeError(f"Falha ao criar stream tar do grupo {group.name} em {source.host}")
    target.run(f"tar -C / -xf {shlex.quote(archive_path)}", timeout=0)


def copy_files(source: Remote, target: Remote, paths: Iterable[str]) -> None:
    for path in paths:
        if not file_exists(source, path):
            print(f"[skip] {path} nao existe na origem")
            continue
        print(f"Copying {path}")
        data = source.read_file(path)
        target.write_file(path, data)


def install_base_packages(target: Remote) -> None:
    packages = " ".join(BASE_PACKAGES)
    target.run(
        "export DEBIAN_FRONTEND=noninteractive; "
        f"apt-get update && apt-get install -y {packages}",
        timeout=0,
    )
    for command in TARGET_PREP_COMMANDS:
        target.run(command)


def stop_services(remote: Remote, services: Iterable[str]) -> None:
    for service in services:
        remote.run(f"systemctl stop {service}", check=False)


def start_services(remote: Remote, services: Iterable[str]) -> None:
    for service in services:
        remote.run(f"systemctl enable {service}", check=False)
        remote.run(f"systemctl start {service}", check=False)


def finalize_target(remote: Remote) -> None:
    remote.run("ln -sfn /opt/red-seb-monitor/data/downloads /opt/seb-remote-view/downloads", check=False)
    remote.run("systemctl daemon-reload")
    remote.run("nginx -t")


def phase_preseed(source: Remote, target: Remote) -> None:
    install_base_packages(target)
    stop_services(target, SERVICE_ORDER_START)
    for group in PRESEED_GROUPS:
        tar_stream(source, target, group)
    copy_files(source, target, ENV_FILES)
    copy_files(source, target, SYSTEMD_FILES)
    copy_files(source, target, NGINX_FILES)
    copy_files(source, target, ["/etc/sudoers.d/openclaw", "/usr/local/bin/openclaw"])
    target.run("chmod +x /usr/local/bin/openclaw", check=False)
    target.run("chown -R openclaw:openclaw /home/openclaw", check=False)
    finalize_target(target)
    print("\nPreseed concluido. A origem continua online.")


def phase_cutover(source: Remote, target: Remote) -> None:
    stop_services(source, SERVICE_ORDER_STOP)
    stop_services(target, SERVICE_ORDER_START)
    for group in FINAL_SYNC_GROUPS:
        tar_stream(source, target, group)
    copy_files(source, target, ENV_FILES)
    copy_files(source, target, SYSTEMD_FILES)
    copy_files(source, target, NGINX_FILES)
    target.run("chmod +x /usr/local/bin/openclaw", check=False)
    target.run("chown -R openclaw:openclaw /home/openclaw", check=False)
    finalize_target(target)
    start_services(target, SERVICE_ORDER_START)
    verify_target(target)
    print(
        "\nCutover tecnico concluido. Se a validacao acima estiver limpa, o proximo passo manual e trocar o No-IP "
        "de redsystems.ddns.net para o IP da nova VM."
    )


def verify_target(remote: Remote) -> None:
    remote.run(
        "systemctl is-active "
        "red-dashboard red-ollama-proxy redia redtrader red-proxy-lab "
        "red-iq-vision-bridge red-openclaw red-seb-monitor red-seb-webhook "
        "red-sebia rapidleech nginx"
    )
    for url in PUBLIC_URLS:
        remote.run(f"curl -fsS -o /dev/null {shlex.quote(url)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migracao mensal da stack RED entre VMs.")
    parser.add_argument("phase", choices=["preseed", "cutover", "verify"])
    for prefix in ("source", "target"):
        parser.add_argument(f"--{prefix}-host", required=(prefix == "target"))
        parser.add_argument(f"--{prefix}-port", type=int, default=22)
        parser.add_argument(f"--{prefix}-user", default="root")
        parser.add_argument(f"--{prefix}-password", required=(prefix == "target"))
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.phase in {"preseed", "cutover"}:
        missing = [
            name
            for name in ("source_host", "source_password")
            if not getattr(args, name)
        ]
        if missing:
            missing_flags = ", ".join("--" + item.replace("_", "-") for item in missing)
            parser.error(f"faltam argumentos obrigatorios para a fase {args.phase}: {missing_flags}")

    source = None
    target = None
    try:
        if args.phase in {"preseed", "cutover"}:
            source = make_remote("source", args)
        target = make_remote("target", args)
        if args.phase == "preseed":
            phase_preseed(source, target)
        elif args.phase == "cutover":
            phase_cutover(source, target)
        else:
            verify_target(target)
        return 0
    finally:
        if source is not None:
            source.close()
        if target is not None:
            target.close()


if __name__ == "__main__":
    raise SystemExit(main())
