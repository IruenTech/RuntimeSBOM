#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
[ -f target/offline-validation/classes/com/iruen/runtimesbom/DurableDeliveryQueue.class ] || sh scripts/validate-offline.sh
javac --release 8 -cp target/offline-validation/classes -d target/offline-validation/classes \
  src/test/java/com/iruen/runtimesbom/Phase17ShutdownDrainTest.java
java -cp target/offline-validation/classes com.iruen.runtimesbom.Phase17ShutdownDrainTest
