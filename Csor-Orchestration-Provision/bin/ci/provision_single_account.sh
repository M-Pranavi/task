#! /bin/bash

set -o pipefail

env=$1
account=$2
name=$3
user=$4
region=$5

pip install -r src/requirements.txt

python src/provision_single_account.py --env "$env" --account "$account" --account-name "$name" --user "$user" --region "$region"
