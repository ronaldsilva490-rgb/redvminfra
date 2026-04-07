#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import os
import sys

import paramiko


sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa um comando remoto via Paramiko usando variaveis de ambiente.")
    parser.add_argument("command", help="Comando para executar na VM")
    parser.add_argument("--host", default=env("REDSYSTEMS_HOST"))
    parser.add_argument("--port", type=int, default=int(env("REDSYSTEMS_SSH_PORT", "22") or "22"))
    parser.add_argument("--user", default=env("REDSYSTEMS_SSH_USER", "root"))
    parser.add_argument("--password", default=env("REDSYSTEMS_SSH_PASSWORD"))
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    if not args.host or not args.user or not args.password:
        parser.error("Defina REDSYSTEMS_HOST, REDSYSTEMS_SSH_USER e REDSYSTEMS_SSH_PASSWORD ou passe via parametros.")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(args.host, port=args.port, username=args.user, password=args.password, timeout=args.timeout)
    try:
        _stdin, stdout, stderr = client.exec_command(args.command, timeout=args.timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if out:
            print(out, end="" if out.endswith("\n") else "\n")
        if err:
            print(err, file=sys.stderr, end="" if err.endswith("\n") else "\n")
        return int(stdout.channel.recv_exit_status())
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
