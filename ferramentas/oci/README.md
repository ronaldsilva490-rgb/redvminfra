# OCI CLI and A1 Flex retry launcher

This folder contains the helper for launching an Oracle Cloud `A1 Flex`
instance with retry logic.

## VM status

The OCI CLI is installed on the RED VM at:

```text
/opt/oracle-cli/bin/oci
```

A convenience symlink can be created at `/usr/local/bin/oci` so scripts can use
`oci` directly.

## Script

`retry_launch_a1_flex.sh` runs on the RED VM and retries
`oci compute instance launch` until Oracle returns a provisioning response or
until a non-capacity error occurs.

The recommended VM flow is:

```bash
cd /opt/redvm-repo/ferramentas/oci
cp launch-a1.env.example launch-a1.env
nano launch-a1.env
ENV_FILE=launch-a1.env ./retry_launch_a1_flex.sh
```

`descobrir_launch_a1_flex.sh` prints the values you need from OCI after your
CLI profile is configured:

```bash
./descobrir_launch_a1_flex.sh
```

It lists compartments, availability domains, VCNs, subnets, and Ubuntu 24.04
ARM images for the tenancy defined in the selected OCI profile.

Required environment variables:

```text
COMPARTMENT_ID
AVAILABILITY_DOMAIN
SUBNET_ID
IMAGE_ID
SSH_KEY_FILE
```

Optional environment variables:

```text
OCI_BIN=/opt/oracle-cli/bin/oci
OCI_PROFILE=DEFAULT
OCI_CONFIG_FILE=/root/.oci/config
ENV_FILE=launch-a1.env
WAIT_SECONDS=60
DISPLAY_NAME=minha-vm-a1
SHAPE=VM.Standard.A1.Flex
OCPUS=4
MEMORY_GB=24
BOOT_VOLUME_GB=200
ASSIGN_PUBLIC_IP=true
```

Example:

```bash
export COMPARTMENT_ID=ocid1.compartment.oc1..xxxx
export AVAILABILITY_DOMAIN=hoqT:SA-SAOPAULO-1-AD-1
export SUBNET_ID=ocid1.subnet.oc1..xxxx
export IMAGE_ID=ocid1.image.oc1..xxxx
export SSH_KEY_FILE="$HOME/.ssh/id_rsa.pub"
./retry_launch_a1_flex.sh
```
