#!/bin/bash

set -e
set -x

# Minimal logging for Jenkins visibility (all to stderr)
>&2 echo "[FALCON] Starting patch script"
>&2 echo "[FALCON] Input: $1"
>&2 echo "[FALCON] Output: $2"

# Validate required parameters
if [[ -z "$1" ]] || [[ -z "$2" ]]; then
    >&2 echo "[FALCON] ERROR: Missing required parameters"
    >&2 echo "[FALCON] Usage: $0 <input_file> <output_file>"
    exit 1
fi

# Get FALCON_CID from environment variable (set by Jenkins credential)
if [[ -z "$FALCON_CID" ]]; then
    >&2 echo "[FALCON] ERROR: FALCON_CID environment variable not set"
    exit 1
fi
>&2 echo "[FALCON] Using Falcon CID: ${FALCON_CID:0:10}..."

IMAGE_PULL_TOKEN=$(echo "{\"auths\":{\"782759316251.dkr.ecr.us-east-2.amazonaws.com\":
{\"auth\":\"$(echo AWS:$(aws ecr get-login-password --region us-east-2)|base64 -w 0)\"}}}" | base64 -w 0)

>&2 echo "[FALCON] Running docker command with AWS credentials"

docker run \
--rm 782759316251.dkr.ecr.us-east-2.amazonaws.com/bt/falcon-sensor:7.24.0-6302 \
-cid "$FALCON_CID" \
-image 782759316251.dkr.ecr.us-east-2.amazonaws.com/bt/falcon-sensor:7.24.0-6302 \
-pulltoken "$IMAGE_PULL_TOKEN" \
-ecs-spec "$(cat "$1" | jq -r .)" | \
jq -r .containerDefinitions > $2

>&2 echo "[FALCON] Patch script complete"

>&2 echo "[FALCON] Validating output file: $2"
if [[ ! -f "$2" ]] || [[ ! -s "$2" ]]; then
    >&2 echo "[FALCON] ERROR: Output file $2 is missing or empty!"
    exit 1
fi
>&2 echo "[FALCON] Output file size: $(stat -c%s "$2") bytes"

# Only this line goes to stdout for Terraform external data source, a JSON object with string keys/values
echo "{\"filename\":\"${2}\"}"
