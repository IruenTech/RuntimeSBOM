#!/bin/sh
# End-to-end RELEASE build: Maven official ASM dependency + shaded executable agent.
set -eu
cd "$(dirname "$0")/.."
command -v mvn >/dev/null || { echo 'ERROR: Maven is required' >&2; exit 2; }
command -v javac >/dev/null || { echo 'ERROR: JDK required' >&2; exit 2; }
mvn -B -DskipTests clean package
OUT=target/official-asm-verification
mkdir -p "$OUT/app"
if javac -version 2>&1 | grep -Eq 'javac 1\.8(\.|$)'; then
  javac -source 8 -target 8 -d "$OUT/app" src/test/java/example/*.java
else
  javac --release 8 -d "$OUT/app" src/test/java/example/*.java
fi
java "-javaagent:target/runtime-sbom-agent-1.0.0-rc16.jar=output=$OUT/sbom.json,interval=0,resourceProbe=false,tracePackages=example" \
  -cp "$OUT/app" example.InstrumentationSmoke > "$OUT/app.log" 2> "$OUT/agent.log"
python3 scripts/verify-instrumentation.py "$OUT/sbom.json" "$OUT/app.log"
jar tf target/runtime-sbom-agent-1.0.0-rc16.jar | grep '^com/iruen/shaded/asm/ClassReader.class$' >/dev/null || { echo 'ERROR: ASM not relocated' >&2; exit 3; }
if jar tf target/runtime-sbom-agent-1.0.0-rc16.jar | grep '^org/objectweb/asm/ClassReader.class$' >/dev/null; then echo 'ERROR: ASM unshaded' >&2; exit 3; fi
javap -verbose -classpath target/runtime-sbom-agent-1.0.0-rc16.jar com.iruen.runtimesbom.AsmTransformer | grep 'major version: 52' >/dev/null || { echo 'ERROR: not Java 8 bytecode' >&2; exit 3; }
sh scripts/verify-nested-archives.sh official
echo 'PASS: Official ASM 9.7.1 shaded agent + execution + nested archive evidence'
python3 scripts/phase16-official-evidence.py
