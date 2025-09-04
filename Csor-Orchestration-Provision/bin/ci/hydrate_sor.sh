#!/bin/bash
set -e

flags() {
    while test $# -gt 0
    do
        case "$1" in
        (-e|--environment)
            shift
            ENVIRONMENT_JSON="../environments/$1.json"
            export ENVIRONMENT_JSON
            shift;;
        *)
            shift;;
        esac
    done
}

flags "$@"

pip install -r ../bin/scripts/hydrate_sor/requirements.txt
python ../bin/scripts/hydrate_sor/hydrate_sor.py
