#!/bin/bash

set -o pipefail

pip install -r bin/scripts/requirements.txt
export PYTHONPATH="${PYTHONPATH}:${WORKSPACE:-$(pwd)}/bin/scripts"
pytest bin/scripts/test/test_lambda_changes.py -v
