#!/bin/sh
# Requires a trusted Maven repository and Java 8+ distribution. Produces actual official evidence.
set -eu
cd "$(dirname "$0")/.."
command -v mvn >/dev/null 2>&1 || { echo 'Maven unavailable: official build NOT RUN' >&2; exit 2; }
mvn -B -DskipTests clean package
JAR=target/runtime-sbom-agent-1.0.0-rc16.jar
python3 scripts/phase18-audit-jar.py "$JAR" --out results/phase19/official-binary-audit.json
sh scripts/phase18-verify-official-binary.sh "$JAR"
sh scripts/phase19-provenance-test.sh official
printf '%s\n' 'PASS: official ASM shaded binary smoke + provenance (not live Spring Boot/Tomcat approval)'
