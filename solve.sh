#!/bin/bash
# Simple wrapper to run the solver

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export PYTHONPATH="$SCRIPT_DIR/src"

exec python3 -m csp.cli "$@"
