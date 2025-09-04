#!/bin/bash

set -eo pipefail

env=$1
account=$2
bucket="csor-provision-${account}-container-definitions"

var_file="infrastructure/tfvars/${env}.tfvars"
role_arn=$(grep provider_aws_assume_role_arn $var_file | cut -d' ' -f2- | tr -d '[ ="]')

echo "Uploading container definitions to S3"

export $(printf "AWS_ACCESS_KEY_ID=%s AWS_SECRET_ACCESS_KEY=%s AWS_SESSION_TOKEN=%s" \
$(aws sts assume-role \
--role-arn $role_arn \
--role-session-name Jenkins \
--query "Credentials.[AccessKeyId,SecretAccessKey,SessionToken]" \
--output text))

WORKSPACE=$(pwd)
cd ${WORKSPACE}/infrastructure/task-definitions/container-definitions

# Upload each Falcon-patched container definition file
for falcon_file in *_falcon_patched.json.tfpl; do
  if [[ -f "$falcon_file" ]]; then
    echo "Uploading $falcon_file to s3://$bucket/$falcon_file"
    # No need to check return code, set -e will fail the script if this fails
    aws s3 cp "$falcon_file" "s3://$bucket/$falcon_file" --content-type text/template
    
    echo "Successfully uploaded $falcon_file"
  fi
done

echo "Container definitions packaging complete"

# Process framework-task-definitions directory - only one file
echo "Processing framework-task-definitions container definition..."
cd ${WORKSPACE}/infrastructure/framework-task-definitions/container-definitions

# There's only one patched file in this directory
framework_file="deployer_framework_falcon_patched.json.tfpl"
if [[ -f "$framework_file" ]]; then
  echo "Uploading $framework_file to s3://$bucket/$framework_file"
  aws s3 cp "$framework_file" "s3://$bucket/$framework_file" --content-type text/template
  echo "Successfully uploaded $framework_file"
else
  echo "Warning: $framework_file not found in framework-task-definitions directory"
fi

echo "Container definitions packaging complete for both task-definitions and framework-task-definitions"
