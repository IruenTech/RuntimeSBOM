#!/bin/sh
# Test a single, already-built *official* shaded agent binary on the active JDK.
# Builds only test fixtures, never recompiles or silently replaces the release agent.
set -eu
cd "$(dirname "$0")/.."
AGENT=${1:-target/runtime-sbom-agent-1.0.0-rc16.jar}
[ -f "$AGENT" ] || { echo "Missing official Agent: $AGENT" >&2;exit 2; }
python3 scripts/phase18-audit-jar.py "$AGENT" --out results/phase18/official-jar-audit.json
OUT=target/phase18-official-verification
mkdir -p "$OUT/app" results/phase18
if javac -version 2>&1 | grep -Eq 'javac 1\.8(\.|$)'; then
  javac -source 8 -target 8 -d "$OUT/app" src/test/java/example/*.java
else
  javac --release 8 -d "$OUT/app" src/test/java/example/*.java
fi
java "-javaagent:$AGENT=output=$OUT/sbom.json,interval=0,resourceProbe=false,tracePackages=example,sampleEvery=1" \
  -cp "$OUT/app" example.InstrumentationSmoke > "$OUT/app.log" 2> "$OUT/agent.log"
python3 scripts/verify-instrumentation.py "$OUT/sbom.json" "$OUT/app.log"
# Exact official binary should be used by all downstream tests, not JDK-internal ASM.
sh scripts/phase17-loader-test.sh official
sh scripts/verify-nested-archives.sh official
python3 scripts/phase18-jdk-evidence.py --jar "$AGENT" --out results/phase18/jdk-evidence.json
