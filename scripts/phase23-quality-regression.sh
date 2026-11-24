#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p target/phase23-test results/phase23
javac --release 8 -d target/phase23-test src/main/java/com/iruen/runtimesbom/ObservationQuality.java src/test/java/com/iruen/runtimesbom/ObservationQualityTest.java
java -cp target/phase23-test com.iruen.runtimesbom.ObservationQualityTest
python3 -m unittest discover -s tests -p 'test_phase23_*.py' -v
sh scripts/verify-jdk-asm.sh
python3 scripts/phase23-sbom-quality.py target/jdk-asm-verification/sbom.json --require-method --out results/phase23/observability.json
