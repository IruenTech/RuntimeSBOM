#!/bin/sh
# End-to-end bytecode instrumentation with a Spring Boot 3 jar:nested: CodeSource.
# jdk-internal mode is test-only; use official for Maven-built shaded ASM JAR.
set -eu
cd "$(dirname "$0")/.."
MODE=${1:-jdk-internal}
OUT=target/phase26-boot3-agent
mkdir -p "$OUT/runner"
sh scripts/verify-nested-archives.sh "$MODE"
if javac -version 2>&1 | grep -Eq 'javac 1\.8(\.|$)'; then TARGET='-source 8 -target 8';else TARGET='--release 8';fi
# shellcheck disable=SC2086
javac $TARGET -d "$OUT/runner" \
  integration/fixture-src/integration/NestedArchiveSmoke.java \
  integration/fixture-src/integration/Phase26Boot3Smoke.java
case "$MODE" in
  jdk-internal)
    AGENT=target/jdk-asm-verification/agent-test-only.jar
    EXPORT='--add-exports=java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED'
    [ -f "$AGENT" ] || { echo 'Run sh scripts/verify-jdk-asm.sh first' >&2;exit 2; }
    ;;
  official)
    AGENT=target/runtime-sbom-agent-1.0.0-rc16.jar
    EXPORT=''
    [ -f "$AGENT" ] || { echo 'Build official shaded ASM Agent first' >&2;exit 2; }
    ;;
  *)echo 'Usage: sh scripts/phase26-boot3-agent-smoke.sh jdk-internal|official' >&2;exit 2;;
esac
# shellcheck disable=SC2086
java $EXPORT "-javaagent:$AGENT=output=$OUT/sbom.json,interval=0,resourceProbe=false,tracePackages=fixture.lib" \
  -cp "$OUT/runner" integration.Phase26Boot3Smoke \
  target/phase9-nested/boot-application.jar 'BOOT-INF/lib/fixture-core-1.2.3.jar' 7 \
  > "$OUT/app.log" 2> "$OUT/agent.log"
python3 scripts/verify-nested-evidence.py "$OUT/sbom.json" "$OUT/app.log" \
  target/phase9-nested/fixture-core-1.2.3.jar 'BOOT-INF/lib/fixture-core-1.2.3.jar'
python3 - "$OUT/sbom.json" <<'PY'
import json,sys
bom=json.load(open(sys.argv[1]))
matches=[c for c in bom['components'] if c.get('purl')=='pkg:maven/com.example.fixture/fixture-core@1.2.3']
assert len(matches)==1,matches
prop={p['name']:p['value'] for p in matches[0]['properties']}
assert prop['runtimeSbom:source'].startswith('jar:nested:'),prop
assert prop['runtimeSbom:observedMethodEntryCount']=='7',prop
print('PASS: real Agent execution -> Spring Boot 3 nested URL -> exact Maven PURL, SHA-256 and 7 calls')
PY
