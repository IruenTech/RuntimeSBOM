#!/bin/sh
# Set JAVA_HOME to a JDK 8,11,17,21 before calling this script.
set -eu
cd "$(dirname "$0")/.."
printf 'JVM: '; java -version 2>&1 | head -n 1
sh scripts/verify-official-asm.sh
python3 -m unittest discover -s collector/tests -q
