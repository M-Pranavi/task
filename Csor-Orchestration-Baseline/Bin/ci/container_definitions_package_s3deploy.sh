#!/bin/bash

set -eo pipefail

env=$1
account=$2

echo "Uploading container definitions to S3"

WORKSPACE=$(pwd)

# Process task-definitions directory
echo "Processing task-definitions container definitions..."
cd ${WORKSPACE}/infrastructure/task-definitions/container-definitions

# Upload each Falcon-patched container definition file
for falcon_file in *_falcon_patched.json.tfpl; do
  if [[ -f "$falcon_file" ]]; then
    echo "Prepared $falcon_file for S3 upload"
  fi
done

# Process framework-task-definitions directory - only one file
echo "Processing framework-task-definitions container definition..."
cd ${WORKSPACE}/infrastructure/framework-task-definitions/container-definitions

# There's only one patched file in this directory 
framework_file="deployer_framework_falcon_patched.json.tfpl"
if [[ -f "$framework_file" ]]; then
  echo "Prepared $framework_file for S3 upload"
else
  echo "Warning: $framework_file not found in framework-task-definitions directory"
fi

echo "Container definitions packaging complete for both task-definitions and framework-task-definitions"
