#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -f target/offline-validation/classes/com/iruen/runtimesbom/RecorderBench.class ]; then
  sh scripts/validate-offline.sh >/dev/null
fi
java -Xms256m -Xmx256m -cp target/offline-validation/classes com.iruen.runtimesbom.RecorderBench "${1:-1000000}"
