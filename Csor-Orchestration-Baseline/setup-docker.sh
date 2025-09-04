#!/bin/bash

set -Eeuo pipefail

ROLE_ARN="$1"
REGISTRY="$2"

sts=( $(
    aws sts assume-role \
    --role-arn "${ROLE_ARN}" \
    --role-session-name docker-session \
    --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' \
    --output text
) )

AWS_ACCESS_KEY_ID=${sts[0]} AWS_SECRET_ACCESS_KEY=${sts[1]} AWS_SESSION_TOKEN=${sts[2]} aws ecr get-login-password --region us-east-2 \
    | docker login --username AWS --password-stdin "${REGISTRY}"
