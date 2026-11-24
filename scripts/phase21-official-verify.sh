#!/bin/sh
# Authorized staging host only. Never falls back to JDK internal ASM.
set -eu
cd "$(dirname "$0")/.."
command -v mvn >/dev/null 2>&1 || { echo 'HOLD: Maven unavailable; official ASM build NOT RUN' >&2; exit 2; }
command -v javac >/dev/null 2>&1 || { echo 'HOLD: JDK unavailable' >&2; exit 2; }
mvn -B -DskipTests clean package
JAR=target/runtime-sbom-agent-1.0.0-rc16.jar
[ -f "$JAR" ] || { echo 'HOLD: official shaded JAR not generated' >&2; exit 2; }
python3 scripts/phase18-audit-jar.py "$JAR" --out results/phase21/official-jar-audit.json
sh scripts/phase18-verify-official-binary.sh "$JAR"
# HTTP provenance fixture requires Java 9+ due to use of javac --release.
java -version 2>&1 | grep -Eq '"(1\.8|8\.)' || \
  python3 scripts/phase21-http-provenance.py --mode official --requests 80 --concurrency 8 \
    --out-dir results/phase21/http-provenance-official
printf '%s\n' 'PASS: official shaded JAR and actual current-JDK tests; this is NOT live WAS approval'
