#!/bin/bash

set -o pipefail

lambda_name=$1
env=$2
account=$3
lambda_tag=$4
bucket="csor-baseline-${account}-lambda-artifacts"

var_file="infrastructure/tfvars/${env}.tfvars"


if [[ ! -n $lambda_tag ]]; then
  lambda_tag=latest
fi

echo "Using lambda tag $lambda_tag"

WORKSPACE=$(pwd)
cd ${WORKSPACE}/lambdas/src/${lambda_name}
pip install --requirement requirements.txt --target package
cd package
zip -r ../${lambda_name}.zip .
cd ..
zip ${lambda_name}.zip *.py

aws s3 cp ./${lambda_name}.zip s3://$bucket/$lambda_name/${lambda_name}-${lambda_tag}.zip

zip_hash=$(shasum -a 256 ${lambda_name}.zip | awk '{print $1}')

echo -n "{\"tag\": \"${lambda_tag}\", \"hash\": \"${zip_hash}\"}" > version.json
aws s3 cp version.json s3://$bucket/$lambda_name/version.json
