#!/bin/bash

set -o pipefail

lambda_name=$1

source_req=lambdas/src/${lambda_name}/requirements.txt
test_req=lambdas/test/${lambda_name}/requirements-test.txt

pip install --requirement $source_req --requirement $test_req

export PYTHONPATH=lambdas/src/${lambda_name}

pytest lambdas/test/${lambda_name}
