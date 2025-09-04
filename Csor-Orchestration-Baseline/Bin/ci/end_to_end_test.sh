#!/bin/bash
set -e

flags() {
    while test $# -gt 0
    do
        case "$1" in
        (-e|--environment)
            shift
            ENVIRONMENT_JSON="environments/$1.json"
            export ENVIRONMENT_JSON
            shift;;
        (-r|--region)
            shift
            REGION="$1"
            export REGION
            shift;;
        *)
            shift;;
        esac
    done
}

ENVIRONMENT_JSON=internal-dev
flags "$@"

echo "Region for run E2E Test: ${REGION}"

pip install -r lambdas/test/end_to_end/requirements-test.txt
python lambdas/test/end_to_end/test_end_to_end.py --region "${REGION}"
