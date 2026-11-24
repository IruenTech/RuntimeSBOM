#!/bin/sh
# JDK21 internal ASM is test-only. 'official' mode requires real shaded Maven jar.
set -eu
cd "$(dirname "$0")/.."
MODE=${1:-jdk-internal}
OUT=target/phase17-loader
mkdir -p "$OUT/fixture" "$OUT/runner" "$OUT/meta/META-INF/maven/com.example.fixture/fixture-core" results/phase17
if javac -version 2>&1 | grep -Eq 'javac 1\.8(\.|$)'; then JAVAC_TARGET='-source 8 -target 8'; else JAVAC_TARGET='--release 8'; fi
# shellcheck disable=SC2086
javac $JAVAC_TARGET -d "$OUT/fixture" integration/fixture-src/fixture/lib/Helper.java
cp integration/fixture-src/META-INF/maven/com.example.fixture/fixture-core/pom.properties "$OUT/meta/META-INF/maven/com.example.fixture/fixture-core/pom.properties"
cp -r "$OUT/fixture/fixture" "$OUT/meta/"
jar cf "$OUT/fixture-core-1.2.3.jar" -C "$OUT/meta" .
# shellcheck disable=SC2086
javac $JAVAC_TARGET -d "$OUT/runner" integration/Phase17LoaderWorkload.java
if [ "$MODE" = jdk-internal ]; then
  AGENT=target/jdk-asm-verification/agent-test-only.jar
  EXPORT='--add-exports=java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED'
  [ -f "$AGENT" ] || sh scripts/verify-jdk-asm.sh
elif [ "$MODE" = official ]; then
  AGENT=target/runtime-sbom-agent-1.0.0-rc16.jar
  EXPORT=''
  [ -f "$AGENT" ] || { echo 'FAIL: official shaded release jar missing. Run mvn package.' >&2; exit 2; }
else
  echo 'Usage: phase17-loader-test.sh jdk-internal|official' >&2; exit 2
fi
# shellcheck disable=SC2086
java $EXPORT "-javaagent:$AGENT=output=$OUT/loader-sbom.json,interval=0,resourceProbe=false,tracePackages=fixture.lib" \
    -cp "$OUT/runner" Phase17LoaderWorkload "$OUT/fixture-core-1.2.3.jar" >"$OUT/app.log" 2>"$OUT/agent.log"
python3 scripts/phase17-verify-loader.py "$OUT/loader-sbom.json" "$OUT/fixture-core-1.2.3.jar" \
    --out "results/phase17/loader-$MODE.json"
