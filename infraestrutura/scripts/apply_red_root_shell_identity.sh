#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${BASE_DIR}/shell/red-root"
STAMP="${STAMP:-$(date +%Y%m%d-%H%M%S)}"
TARGET_HOSTNAME="${TARGET_HOSTNAME:-red}"

require_file() {
    local path="$1"
    if [[ ! -f "$path" ]]; then
        echo "[erro] arquivo ausente: $path" >&2
        exit 1
    fi
}

backup_if_exists() {
    local path="$1"
    if [[ -e "$path" ]]; then
        cp -a "$path" "${path}.bak-${STAMP}"
    fi
}

require_file "${SRC_DIR}/root.bashrc"
require_file "${SRC_DIR}/root.bash_profile"
require_file "${SRC_DIR}/root.profile"
require_file "${SRC_DIR}/00-red-header"
require_file "${SRC_DIR}/redpainel"

backup_if_exists /root/.bashrc
backup_if_exists /root/.bash_profile
backup_if_exists /root/.profile
backup_if_exists /usr/local/bin/redpainel
backup_if_exists /etc/update-motd.d/00-red-header
backup_if_exists /etc/hostname
backup_if_exists /etc/hosts

install -m 0644 "${SRC_DIR}/root.bashrc" /root/.bashrc
install -m 0644 "${SRC_DIR}/root.bash_profile" /root/.bash_profile
install -m 0644 "${SRC_DIR}/root.profile" /root/.profile
install -m 0755 "${SRC_DIR}/00-red-header" /etc/update-motd.d/00-red-header
install -m 0755 "${SRC_DIR}/redpainel" /usr/local/bin/redpainel

touch /etc/motd

if command -v hostnamectl >/dev/null 2>&1; then
    hostnamectl set-hostname "${TARGET_HOSTNAME}"
else
    printf '%s\n' "${TARGET_HOSTNAME}" > /etc/hostname
    hostname "${TARGET_HOSTNAME}"
fi

cat > /etc/hosts <<EOF
127.0.0.1 localhost
127.0.1.1 ${TARGET_HOSTNAME}

# The following lines are desirable for IPv6 capable hosts
::1     ip6-localhost ip6-loopback
fe00::0 ip6-localnet
ff00::0 ip6-mcastprefix
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
EOF

if [[ -d /etc/update-motd.d ]]; then
    while IFS= read -r -d '' file; do
        if [[ "$(basename "$file")" == "00-red-header" ]]; then
            chmod 0755 "$file"
        else
            chmod 0644 "$file"
        fi
    done < <(find /etc/update-motd.d -maxdepth 1 -type f -print0)
fi

for path in \
    /etc/profile.d/lish.sh \
    /etc/profile.d/Z99-cloudinit-warnings.sh \
    /etc/profile.d/Z99-cloud-locale-test.sh
do
    if [[ -f "$path" ]]; then
        mv "$path" "${path}.disabled-red"
    fi
done

echo "[ok] shell root RED aplicado em ${TARGET_HOSTNAME}"
echo "[ok] MOTD ativo:"
run-parts /etc/update-motd.d || true
