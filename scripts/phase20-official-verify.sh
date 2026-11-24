#!/bin/sh
# Must be performed on an authorized host with Maven and Central (or a trusted internal mirror).
# Refuse to substitute JDK-internal ASM for the distribution build.
set -eu
cd "$(dirname "$0")/.."
command -v mvn >/dev/null 2>&1 || { echo 'HOLD: Maven not installed; official ASM build NOT RUN' >&2;exit 2; }
mvn -B -DskipTests clean package
JAR=target/runtime-sbom-agent-1.0.0-rc16.jar
[ -f "$JAR" ] || { echo 'HOLD: official shaded JAR was not generated' >&2;exit 2; }
python3 scripts/phase18-audit-jar.py "$JAR" --out results/phase20/official-jar-audit.json
sh scripts/phase18-verify-official-binary.sh "$JAR"
sh scripts/phase20-fixture-gate.sh official
printf '%s\n' 'PASS: official ASM shaded JAR structural + local real-JVM fixture checks (NOT live WAS acceptance)'
