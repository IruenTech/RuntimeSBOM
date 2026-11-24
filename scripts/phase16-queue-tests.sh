#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# This offline executable tests the new queue and collector transport ONLY.
# validate-offline.sh intentionally builds a non-instrumenting ASM stub.
sh scripts/validate-offline.sh
javac --release 8 -cp target/offline-validation/classes -d target/offline-validation/classes \
  src/test/java/com/iruen/runtimesbom/Phase16QueueTest.java
java -cp target/offline-validation/classes com.iruen.runtimesbom.Phase16QueueTest
