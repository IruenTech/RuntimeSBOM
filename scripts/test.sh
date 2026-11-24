#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# This is the official artifact verification; requires Maven and external dependencies.
sh scripts/verify-official-asm.sh
python3 -m unittest discover -s collector/tests -v
python3 -m unittest discover -s tests -v
python3 scripts/phase14-release-gate.py  # exits 3 while release is HOLD
