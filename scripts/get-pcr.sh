#!/usr/bin/env bash
set -e

# Retrieve PCR measurements from the sandboxed container operator's dm-verity image.
# These measurements are required for the pcrStash secret used by Trustee for attestation.
# Run this before ./pattern.sh make load-secrets.

OUTPUT_DIR="${HOME}/.config/validated-patterns/trustee"

# 1. Locate pull secret
PULL_SECRET_PATH="${HOME}/pull-secret.json"
if [ ! -f "$PULL_SECRET_PATH" ]; then
    if [ -n "${PULL_SECRET}" ]; then
        PULL_SECRET_PATH="${PULL_SECRET}"
        if [ ! -f "$PULL_SECRET_PATH" ]; then
            echo "ERROR: Pull secret file not found at path specified in PULL_SECRET: $PULL_SECRET_PATH"
            exit 1
        fi
    else
        echo "ERROR: Pull secret not found at ~/pull-secret.json"
        echo "Please either place your pull secret at ~/pull-secret.json or set the PULL_SECRET environment variable"
        exit 1
    fi
fi

echo "Using pull secret: $PULL_SECRET_PATH"

# 2. Check for required tools
for cmd in yq skopeo jq podman; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "ERROR: $cmd is required but not installed"
        exit 1
    fi
done

# 3. Check values-global.yaml exists
if [ ! -f "values-global.yaml" ]; then
    echo "ERROR: values-global.yaml not found in current directory"
    echo "Please run this script from the root directory of the project"
    exit 1
fi

# 4. Get the active clusterGroupName from values-global.yaml
CLUSTER_GROUP_NAME=$(yq eval '.main.clusterGroupName' values-global.yaml)

if [ -z "$CLUSTER_GROUP_NAME" ] || [ "$CLUSTER_GROUP_NAME" == "null" ]; then
    echo "ERROR: Could not determine clusterGroupName from values-global.yaml"
    echo "Expected: main.clusterGroupName to be set"
    exit 1
fi

echo "Active clusterGroup: $CLUSTER_GROUP_NAME"

# 5. Locate the values file for the active clusterGroup
VALUES_FILE="values-${CLUSTER_GROUP_NAME}.yaml"

if [ ! -f "$VALUES_FILE" ]; then
    echo "ERROR: Values file for clusterGroup not found: $VALUES_FILE"
    exit 1
fi

# 6. Get the sandboxed container operator CSV from the clusterGroup values
SANDBOX_CSV=$(yq eval '.clusterGroup.subscriptions.sandbox.csv // .clusterGroup.subscriptions.sandboxed.csv' "$VALUES_FILE")

if [ -z "$SANDBOX_CSV" ] || [ "$SANDBOX_CSV" == "null" ]; then
    echo "ERROR: No sandboxed container operator CSV found in $VALUES_FILE"
    echo "The subscription clusterGroup.subscriptions.sandbox.csv (or .sandboxed.csv) is not defined"
    exit 1
fi

# Extract version from CSV (e.g., "sandboxed-containers-operator.v1.11.0" -> "1.11.0")
SANDBOX_VERSION="${SANDBOX_CSV##*.v}"

echo "Sandboxed container operator CSV: $SANDBOX_CSV"
echo "Version: $SANDBOX_VERSION"

VERITY_IMAGE=registry.redhat.io/openshift-sandboxed-containers/osc-dm-verity-image

TAG=$(skopeo inspect --authfile "$PULL_SECRET_PATH" "docker://${VERITY_IMAGE}:${SANDBOX_VERSION}" | jq -r .Digest)

IMAGE=${VERITY_IMAGE}@${TAG}

echo "IMAGE: $IMAGE"

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

# Clean up any existing measurement files
rm -f "$OUTPUT_DIR/measurements-raw.json" "$OUTPUT_DIR/measurements.json"

# Download the measurements using podman cp
podman pull --authfile "$PULL_SECRET_PATH" "$IMAGE"

cid=$(podman create --entrypoint /bin/true "$IMAGE")
echo "CID: ${cid}"
podman cp "$cid:/image/measurements.json" "$OUTPUT_DIR/measurements-raw.json"
podman rm "$cid"

# Trim leading "0x" from all measurement values
jq 'walk(if type == "string" and startswith("0x") then .[2:] else . end)' \
    "$OUTPUT_DIR/measurements-raw.json" > "$OUTPUT_DIR/measurements.json"

echo "Measurements saved to $OUTPUT_DIR/measurements.json (0x prefixes removed)"
