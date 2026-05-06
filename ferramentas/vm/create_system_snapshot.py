#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import os
import shlex
import sys
from datetime import datetime

import paramiko


sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


SNAPSHOT_ROOT = "/root/backups"

ARCHIVES = [
    (
        "redvm-opt-runtime.tar.gz",
        [
            "/opt/redvm-dashboard",
            "/opt/redvm-proxy",
            "/opt/redia",
            "/opt/redtrader",
            "/opt/red-openclaw",
            "/opt/rapidleech",
            "/opt/red-seb-monitor",
            "/opt/red-proxy-lab",
            "/opt/red-iq-vision-bridge",
            "/opt/redvm-projects",
            "/opt/redvm-samples",
        ],
    ),
    (
        "redvm-web-and-var-data.tar.gz",
        [
            "/var/www/red-portal",
            "/var/lib/redvm-proxy",
        ],
    ),
    (
        "redvm-etc-config.tar.gz",
        [
            "/etc/nginx",
            "/etc/systemd/system/red-dashboard.service",
            "/etc/systemd/system/red-ollama-proxy.service",
            "/etc/systemd/system/redia.service",
            "/etc/systemd/system/redtrader.service",
            "/etc/systemd/system/red-openclaw.service",
            "/etc/systemd/system/rapidleech.service",
            "/etc/systemd/system/red-seb-monitor.service",
            "/etc/systemd/system/red-proxy-lab.service",
            "/etc/systemd/system/red-iq-vision-bridge.service",
            "/etc/redvm-dashboard.env",
            "/etc/red-ollama-proxy.env",
            "/etc/redtrader.env",
            "/etc/red-openclaw.env",
            "/etc/red-seb-monitor.env",
            "/etc/red-proxy-lab.env",
            "/etc/red-iq-vision-bridge.env",
            "/etc/letsencrypt",
            "/etc/cron.d",
        ],
    ),
]

INVENTORY_COMMANDS = [
    ("hostnamectl.txt", "hostnamectl || true"),
    ("os-release.txt", "cat /etc/os-release || true"),
    ("uname.txt", "uname -a || true"),
    ("date.txt", "date -Is && date -u -Is"),
    ("df.txt", "df -hT || true"),
    ("lsblk.txt", "lsblk -f || true"),
    ("mounts.txt", "findmnt || true"),
    ("ip-address.txt", "ip addr show || true"),
    ("routes.txt", "ip route show || true"),
    ("ports.txt", "ss -lntup || true"),
    ("systemd-red-units.txt", "systemctl list-units 'red*' --all --no-pager || true"),
    ("systemd-services.txt", "systemctl list-unit-files --type=service --no-pager || true"),
    ("systemd-failed.txt", "systemctl --failed --no-pager || true"),
    ("nginx-test.txt", "nginx -t 2>&1 || true"),
    ("nginx-enabled.txt", "find /etc/nginx -maxdepth 3 -type f -print | sort || true"),
    ("apt-manual.txt", "apt-mark showmanual 2>/dev/null | sort || true"),
    ("dpkg-packages.txt", "dpkg-query -W -f='${Package}\\t${Version}\\n' 2>/dev/null | sort || true"),
    ("python-processes.txt", "ps -eo pid,ppid,user,cmd --sort=cmd | grep -E 'python|node|nginx|redis|red' | grep -v grep || true"),
    ("crontab-root.txt", "crontab -l 2>&1 || true"),
    ("ufw-status.txt", "ufw status verbose 2>&1 || true"),
    ("docker.txt", "docker ps -a 2>&1 || true"),
]

RESTORE_NOTES = """# RED VM system snapshot restore notes

This directory is a runtime snapshot of the current VM state.

Recommended restore target:
- Fresh Ubuntu VM with the same major release, equal or larger disk, and root SSH access.
- Restore into a disposable VM first, validate services, then point DNS or traffic at it.

Basic restore flow:

1. Copy this snapshot directory to the target VM under /root/backups/.
2. Inspect inventory/*.txt and compare OS, disk layout, ports, and services.
3. Install base packages listed in inventory/apt-manual.txt as needed.
4. Extract the archives from /:

   tar -C / -xpf redvm-etc-config.tar.gz
   tar -C / -xpf redvm-opt-runtime.tar.gz
   tar -C / -xpf redvm-web-and-var-data.tar.gz

5. Run:

   systemctl daemon-reload
   nginx -t
   systemctl restart nginx

6. Restart only the RED services you intend to bring up.
7. Validate HTTP routes, systemd state, logs, and secrets/env files.

Important:
- This is a filesystem/application snapshot, not a bootable disk image.
- It intentionally captures secrets inside env/config files because the goal is restore fidelity.
- Keep it encrypted or on a trusted machine only.
- For an exact disk-level clone, use the VPS provider snapshot/image feature or a block image workflow.
"""


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


class Remote:
    def __init__(self, host: str, port: int, user: str, password: str) -> None:
        self.host = host
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(
            host,
            port=port,
            username=user,
            password=password,
            timeout=25,
            banner_timeout=25,
            auth_timeout=25,
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
        _stdin, stdout, stderr = self.client.exec_command(command, timeout=exec_timeout)
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
            raise RuntimeError(f"Remote command failed with exit code {code}")
        return out

    def write_text(self, remote_path: str, text: str) -> None:
        with self.sftp.open(remote_path, "w") as fh:
            fh.write(text)


def shell_quote_many(paths: list[str]) -> str:
    return " ".join(shlex.quote(path) for path in paths)


def make_snapshot(remote: Remote, name: str) -> str:
    snapshot_dir = f"{SNAPSHOT_ROOT}/{name}"
    inventory_dir = f"{snapshot_dir}/inventory"

    remote.run(f"mkdir -p {shlex.quote(inventory_dir)}")
    remote.write_text(f"{snapshot_dir}/RESTORE.md", RESTORE_NOTES)

    for filename, command in INVENTORY_COMMANDS:
        output_path = f"{inventory_dir}/{filename}"
        remote.run(f"({command}) > {shlex.quote(output_path)}", timeout=300, check=False)

    for archive, paths in ARCHIVES:
        archive_path = f"{snapshot_dir}/{archive}"
        existing = " ".join(
            f"[ -e {shlex.quote(path)} ] && printf '%s\\0' {shlex.quote(path)};"
            for path in paths
        )
        create_command = (
            f"tmpfile=$(mktemp); "
            f"{existing} "
            f"> \"$tmpfile\"; "
            f"if [ -s \"$tmpfile\" ]; then "
            f"tar --null -T \"$tmpfile\" --xattrs --acls --warning=no-file-changed "
            f"--ignore-failed-read -C / -czpf {shlex.quote(archive_path)}; "
            f"else touch {shlex.quote(archive_path)}; fi; "
            f"rm -f \"$tmpfile\""
        )
        remote.run(create_command, timeout=0)

    manifest_command = (
        f"cd {shlex.quote(snapshot_dir)} && "
        "find . -maxdepth 3 -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS && "
        "du -sh . > SIZE.txt && "
        "find . -maxdepth 2 -type f -printf '%p\\t%s bytes\\n' | sort > FILES.txt"
    )
    remote.run(manifest_command, timeout=600)
    remote.run(f"ls -lh {shlex.quote(snapshot_dir)} && cat {shlex.quote(snapshot_dir)}/SIZE.txt")
    return snapshot_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Cria snapshot restauravel do estado real da VM RED.")
    parser.add_argument("--host", default=env("REDSYSTEMS_HOST"))
    parser.add_argument("--port", type=int, default=int(env("REDSYSTEMS_SSH_PORT", "22") or "22"))
    parser.add_argument("--user", default=env("REDSYSTEMS_SSH_USER", "root"))
    parser.add_argument("--password", default=env("REDSYSTEMS_SSH_PASSWORD"))
    parser.add_argument("--name", default=f"redvm-system-snapshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    args = parser.parse_args()

    if not args.host or not args.user or not args.password:
        parser.error("Defina REDSYSTEMS_HOST, REDSYSTEMS_SSH_USER e REDSYSTEMS_SSH_PASSWORD.")

    remote = Remote(args.host, args.port, args.user, args.password)
    try:
        snapshot_dir = make_snapshot(remote, args.name)
        print(f"\nSnapshot criado em: {snapshot_dir}")
        return 0
    finally:
        remote.close()


if __name__ == "__main__":
    raise SystemExit(main())
