#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
OUT=target/phase19-index-unit
mkdir -p "$OUT"
if javac -version 2>&1 | grep -Eq 'javac 1\.8(\.|$)'; then OPTS='-source 8 -target 8'; else OPTS='--release 8'; fi
# shellcheck disable=SC2086
javac $OPTS -d "$OUT" src/main/java/com/iruen/runtimesbom/AttributionIndex.java src/test/java/com/iruen/runtimesbom/AttributionIndexTest.java
java -cp "$OUT" com.iruen.runtimesbom.AttributionIndexTest
