#!/usr/bin/env python3
"""
Sync local repo to VM /opt/redvm-repo/ using tar + sftp.
Uploads entire servicos directory as tarball, then extracts on VM.
"""
import os
import sys
import paramiko
import tarfile
import io

# Config
HOST = os.environ.get('VM_HOST', 'redsystems.ddns.net')
PORT = int(os.environ.get('VM_PORT', '22'))
USER = os.environ.get('VM_USER', 'root')
PASSWORD = os.environ.get('VM_PASSWORD', '')

if not PASSWORD:
    print("Set VM_PASSWORD env var")
    sys.exit(1)

LOCAL_SERVICOS = os.path.join(os.path.dirname(__file__), '..', '..', 'servicos')

def main():
    # Create tarball in memory
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode='w:gz') as tar:
        tar.add(LOCAL_SERVICOS, arcname='servicos')
    tar_buf.seek(0)

    print(f"Created tarball: {len(tar_buf.getvalue())} bytes")

    # Connect via SSH
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD)

    # Upload tarball
    sftp = ssh.open_sftp()
    remote_tar = '/tmp/redvm-repo-sync.tar.gz'
    sftp.putfo(tar_buf, remote_tar)
    sftp.close()

    print(f"Uploaded to {remote_tar}")

    # Extract on VM
    stdin, stdout, stderr = ssh.exec_command(
        f"tar -xzf {remote_tar} -C /opt/redvm-repo/ --overwrite"
    )
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()

    if exit_code != 0:
        print(f"Error: {err}")
    else:
        print("Extracted successfully!")
        if out:
            print(out)

    # Cleanup
    ssh.exec_command(f"rm -f {remote_tar}")
    ssh.close()

    print("Sync complete!")

if __name__ == '__main__':
    main()
