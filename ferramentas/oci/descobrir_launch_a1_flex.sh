#!/usr/bin/env bash
set -euo pipefail

# Helper to collect the OCI values needed by retry_launch_a1_flex.sh.
# Requires OCI CLI configured with a valid profile.

OCI_BIN="${OCI_BIN:-oci}"
PROFILE="${OCI_PROFILE:-DEFAULT}"

get_config_value() {
  local key="$1"
  local config="${OCI_CONFIG_FILE:-$HOME/.oci/config}"
  awk -v profile="$PROFILE" -v key="$key" '
    BEGIN { in_profile = 0 }
    /^\[/ {
      in_profile = ($0 == "[" profile "]")
      next
    }
    in_profile && $0 ~ "^[[:space:]]*" key "[[:space:]]*=" {
      sub("^[[:space:]]*" key "[[:space:]]*=[[:space:]]*", "")
      gsub(/^[[:space:]]+|[[:space:]]+$/, "")
      print
      exit
    }
  ' "$config"
}

TENANCY_ID="$(get_config_value tenancy)"

if [[ -z "$TENANCY_ID" ]]; then
  echo "Could not read tenancy OCID from OCI config profile '$PROFILE'." >&2
  echo "Set OCI_CONFIG_FILE or fix ~/.oci/config." >&2
  exit 1
fi

echo "=== OCI CLI ==="
"$OCI_BIN" --version
echo

echo "=== Tenancy / Compartments ==="
"$OCI_BIN" iam compartment list --compartment-id-in-subtree true --compartment-id "$TENANCY_ID" --all --profile "$PROFILE" --output table
echo

echo "=== Availability Domains ==="
"$OCI_BIN" iam availability-domain list --compartment-id "$TENANCY_ID" --profile "$PROFILE" --output table
echo

echo "=== VCNs ==="
"$OCI_BIN" network vcn list --compartment-id "$TENANCY_ID" --profile "$PROFILE" --output table
echo

echo "=== Subnets ==="
"$OCI_BIN" network subnet list --compartment-id "$TENANCY_ID" --profile "$PROFILE" --output table
echo

echo "=== Ubuntu 24.04 ARM Images ==="
"$OCI_BIN" compute image list --compartment-id "$TENANCY_ID" --operating-system Ubuntu --operating-system-version 24.04 --shape VM.Standard.A1.Flex --all --profile "$PROFILE" --output table
echo

cat <<'EOF'

Copy these values into retry_launch_a1_flex.sh:

COMPARTMENT_ID=ocid1.compartment....
AVAILABILITY_DOMAIN=hoqT:SA-SAOPAULO-1-AD-1
SUBNET_ID=ocid1.subnet....
IMAGE_ID=ocid1.image....
SSH_KEY_FILE=$HOME/.ssh/id_rsa.pub

Then run:

COMPARTMENT_ID=...
AVAILABILITY_DOMAIN=...
SUBNET_ID=...
IMAGE_ID=...
SSH_KEY_FILE=...
./retry_launch_a1_flex.sh
EOF
