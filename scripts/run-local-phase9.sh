#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
echo '=== Collector regression ==='
python3 -m unittest discover -s collector/tests -v
echo '=== Class loader identity regression ==='
sh scripts/test-classloader-offline.sh
echo '=== Official ASM release check (Maven required) ==='
sh scripts/verify-official-asm.sh
