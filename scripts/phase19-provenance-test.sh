#!/bin/sh
# Synthetic real-JVM multi-archive loader test. Requires JDK; JDK-internal ASM is TEST ONLY.
set -eu
cd "$(dirname "$0")/.."
MODE=${1:-jdk-internal}
OUT=target/phase19-provenance
rm -rf "$OUT"
mkdir -p "$OUT/old-classes" "$OUT/new-classes" "$OUT/oldjar/META-INF/maven/com.example.fixture/fixture-core" "$OUT/newjar/META-INF/maven/com.example.fixture/fixture-core" "$OUT/runner" results/phase19
if javac -version 2>&1 | grep -Eq 'javac 1\.8(\.|$)'; then JAVAC_FLAGS='-source 8 -target 8'; else JAVAC_FLAGS='--release 8'; fi
# shellcheck disable=SC2086
javac $JAVAC_FLAGS -d "$OUT/old-classes" integration/fixture-src/fixture/lib/Helper.java
cp integration/fixture-src/fixture/lib/HelperAlternate.java.template "$OUT/Helper.java"
# shellcheck disable=SC2086
javac $JAVAC_FLAGS -d "$OUT/new-classes" "$OUT/Helper.java"
for variant in old new; do
  cp integration/fixture-src/META-INF/maven/com.example.fixture/fixture-core/pom.properties "$OUT/${variant}jar/META-INF/maven/com.example.fixture/fixture-core/pom.properties"
  cp -r "$OUT/${variant}-classes/fixture" "$OUT/${variant}jar/"
  jar cf "$OUT/${variant}-fixture.jar" -C "$OUT/${variant}jar" .
done
# shellcheck disable=SC2086
javac $JAVAC_FLAGS -d "$OUT/runner" integration/Phase19ProvenanceWorkload.java
if [ "$MODE" = 'jdk-internal' ];then
  AGENT=target/jdk-asm-verification/agent-test-only.jar
  [ -f "$AGENT" ] || sh scripts/verify-jdk-asm.sh
  EXPORT='--add-exports=java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED'
elif [ "$MODE" = 'official' ];then
  AGENT=target/runtime-sbom-agent-1.0.0-rc16.jar
  EXPORT=''
  [ -f "$AGENT" ] || { echo 'Official ASM shaded JAR missing; use Maven first.' >&2; exit 2; }
  python3 scripts/phase18-audit-jar.py "$AGENT" --out results/phase19/official-binary-audit.json
else
  echo 'Choose jdk-internal|official' >&2; exit 2
fi
# shellcheck disable=SC2086
java $EXPORT "-javaagent:$AGENT=output=$OUT/sbom.json,interval=0,resourceProbe=false,tracePackages=fixture.lib" \
  -cp "$OUT/runner" Phase19ProvenanceWorkload "$OUT/old-fixture.jar" "$OUT/new-fixture.jar" \
  > "$OUT/app.log" 2> "$OUT/agent.log"
python3 scripts/phase19-verify-provenance.py "$OUT/sbom.json" "$OUT/old-fixture.jar" "$OUT/new-fixture.jar" \
  --out "results/phase19/provenance-$MODE.json"
