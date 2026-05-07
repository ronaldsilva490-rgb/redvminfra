#!/usr/bin/env python3
"""Upload dos mockups Total Empresarial para a VM via SFTP/Paramiko."""
from __future__ import annotations

import os
import sys
import paramiko

HOST = "redsystems.ddns.net"
PORT = 22
USER = "root"
PASSWORD = "2580"
REMOTE_DIR = "/var/www/modelos"
LOCAL_DIR = r"C:\xampp\htdocs\totalempresarial-mockups"


def upload_dir(sftp, local_dir, remote_dir):
    """Recursivamente faz upload de todos os arquivos de local_dir para remote_dir."""
    sftp.mkdir(remote_dir) if not dir_exists(sftp, remote_dir) else None
    for item in os.listdir(local_dir):
        local_path = os.path.join(local_dir, item)
        remote_path = f"{remote_dir}/{item}"
        if os.path.isdir(local_path):
            upload_dir(sftp, local_path, remote_path)
        else:
            print(f"  Uploading {item}...")
            sftp.put(local_path, remote_path)


def dir_exists(sftp, path):
    try:
        sftp.stat(path)
        return True
    except FileNotFoundError:
        return False


def main():
    transport = paramiko.Transport((HOST, PORT))
    transport.connect(username=USER, password=PASSWORD)
    sftp = paramiko.SFTPClient.from_transport(transport)

    print(f"Conectado a {HOST}:{PORT}")
    print(f"Uploading de {LOCAL_DIR} para {REMOTE_DIR}...")

    # Limpar remoto primeiro
    try:
        for item in sftp.listdir(REMOTE_DIR):
            remote_path = f"{REMOTE_DIR}/{item}"
            if sftp.stat(remote_path).st_mode & 0o40000:  # é diretório
                for sub in sftp.listdir(remote_path):
                    sftp.remove(f"{remote_path}/{sub}")
                sftp.rmdir(remote_path)
            else:
                sftp.remove(remote_path)
    except FileNotFoundError:
        pass

    upload_dir(sftp, LOCAL_DIR, REMOTE_DIR)

    sftp.close()
    transport.close()
    print("Upload concluído!")


if __name__ == "__main__":
    main()
