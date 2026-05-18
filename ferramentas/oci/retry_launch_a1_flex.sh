#!/usr/bin/env bash
set -euo pipefail

# OCI A1 Flex retry launcher.
# Requires OCI CLI installed and configured on the machine running the script.

OCI_BIN="${OCI_BIN:-oci}"
OCI_PROFILE="${OCI_PROFILE:-DEFAULT}"
OCI_CONFIG_FILE="${OCI_CONFIG_FILE:-$HOME/.oci/config}"
ENV_FILE="${ENV_FILE:-}"
WAIT_SECONDS="${WAIT_SECONDS:-60}"
OCI_REQUEST_TIMEOUT_SECONDS="${OCI_REQUEST_TIMEOUT_SECONDS:-180}"
OCI_RATE_LIMIT_WAIT_SECONDS="${OCI_RATE_LIMIT_WAIT_SECONDS:-300}"
DISPLAY_NAME="${DISPLAY_NAME:-minha-vm-a1}"
SHAPE="${SHAPE:-VM.Standard.A1.Flex}"
OCPUS="${OCPUS:-4}"
MEMORY_GB="${MEMORY_GB:-24}"
BOOT_VOLUME_GB="${BOOT_VOLUME_GB:-200}"
ASSIGN_PUBLIC_IP="${ASSIGN_PUBLIC_IP:-true}"

if [[ -n "$ENV_FILE" ]]; then
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "ENV_FILE not found: $ENV_FILE" >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

: "${COMPARTMENT_ID:?set COMPARTMENT_ID}"
: "${AVAILABILITY_DOMAIN:?set AVAILABILITY_DOMAIN}"
: "${SUBNET_ID:?set SUBNET_ID}"
: "${IMAGE_ID:?set IMAGE_ID}"
: "${SSH_KEY_FILE:?set SSH_KEY_FILE}"

if [[ ! -f "$SSH_KEY_FILE" ]]; then
  echo "SSH_KEY_FILE not found: $SSH_KEY_FILE" >&2
  exit 1
fi

echo "=================================================="
echo " OCI A1 Flex retry launcher"
echo " display_name: $DISPLAY_NAME"
echo " interval: ${WAIT_SECONDS}s"
echo " request_timeout: ${OCI_REQUEST_TIMEOUT_SECONDS}s"
echo " rate_limit_wait: ${OCI_RATE_LIMIT_WAIT_SECONDS}s"
echo " shape: $SHAPE"
echo " profile: $OCI_PROFILE"
echo " config: $OCI_CONFIG_FILE"
echo "=================================================="

attempt=1
while true; do
  echo "[$(date '+%H:%M:%S')] tentativa #$attempt"

  output="$(
    timeout "$OCI_REQUEST_TIMEOUT_SECONDS" "$OCI_BIN" compute instance launch \
      --compartment-id "$COMPARTMENT_ID" \
      --availability-domain "$AVAILABILITY_DOMAIN" \
      --shape "$SHAPE" \
      --shape-config "{\"ocpus\": ${OCPUS}, \"memoryInGBs\": ${MEMORY_GB}}" \
      --image-id "$IMAGE_ID" \
      --subnet-id "$SUBNET_ID" \
      --ssh-authorized-keys-file "$SSH_KEY_FILE" \
      --boot-volume-size-in-gbs "$BOOT_VOLUME_GB" \
      --display-name "$DISPLAY_NAME" \
      --assign-public-ip "$ASSIGN_PUBLIC_IP" \
      --config-file "$OCI_CONFIG_FILE" \
      --profile "$OCI_PROFILE" \
      --output json 2>&1
  )" || true

  if grep -qiE 'timed out|terminated|killed' <<<"$output" || [[ -z "$output" ]]; then
    echo "Chamada OCI sem resposta dentro de ${OCI_REQUEST_TIMEOUT_SECONDS}s. Aguardando ${WAIT_SECONDS}s..."
    attempt=$((attempt + 1))
    sleep "$WAIT_SECONDS"
    continue
  fi

  if grep -qiE 'TooManyRequests|status"[[:space:]]*:[[:space:]]*429|status:[[:space:]]*429|too many requests for the user' <<<"$output"; then
    echo "Rate limit OCI (429). Aguardando ${OCI_RATE_LIMIT_WAIT_SECONDS}s..."
    attempt=$((attempt + 1))
    sleep "$OCI_RATE_LIMIT_WAIT_SECONDS"
    continue
  fi

  if grep -qiE '"lifecycle-state"[[:space:]]*:[[:space:]]*"PROVISIONING"' <<<"$output"; then
    echo "SUCESSO: instancia criada"
    OCI_OUTPUT="$output" python3 - <<'PY'
import json
import os

data = json.loads(os.environ["OCI_OUTPUT"])
selected = {
    "id": data.get("data", {}).get("id"),
    "lifecycle_state": data.get("data", {}).get("lifecycle-state"),
    "display_name": data.get("data", {}).get("display-name"),
    "availability_domain": data.get("data", {}).get("availability-domain"),
    "time_created": data.get("data", {}).get("time-created"),
}
print(json.dumps(selected, ensure_ascii=False, indent=2))
PY
    exit 0
  fi

  if grep -qiE 'Out of capacity|InsufficientServiceCapacity|Capacity|limit exceeded' <<<"$output"; then
    echo "Sem capacidade ainda. Aguardando ${WAIT_SECONDS}s..."
  else
    echo "Erro inesperado:"
    echo "$output"
    exit 1
  fi

  attempt=$((attempt + 1))
  sleep "$WAIT_SECONDS"
done
