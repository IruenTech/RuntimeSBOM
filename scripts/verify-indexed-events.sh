#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
sh scripts/validate-offline.sh > /dev/null 2> /dev/null
javac --release 8 -cp target/offline-validation/classes -d target/offline-validation/classes src/test/java/com/iruen/runtimesbom/IndexedEventTest.java
java -cp target/offline-validation/classes com.iruen.runtimesbom.IndexedEventTest
