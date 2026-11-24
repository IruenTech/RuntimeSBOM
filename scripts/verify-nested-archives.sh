#!/bin/sh
# A real transformed fixture class and synthetic container CodeSource; NOT a Tomcat/Boot runtime.
set -eu
cd "$(dirname "$0")/.."
MODE=${1:-jdk-internal}
OUT=target/phase9-nested
rm -rf "$OUT"
mkdir -p "$OUT"/fixture-classes "$OUT"/runner "$OUT"/jar-root/META-INF/maven/com.example.fixture/fixture-core
if javac -version 2>&1 | grep -Eq 'javac 1\.8(\.|$)'; then JAVAC_TARGET="-source 8 -target 8"; else JAVAC_TARGET="--release 8"; fi
# shellcheck disable=SC2086
javac $JAVAC_TARGET -d "$OUT/fixture-classes" integration/fixture-src/fixture/lib/Helper.java
cp integration/fixture-src/META-INF/maven/com.example.fixture/fixture-core/pom.properties "$OUT"/jar-root/META-INF/maven/com.example.fixture/fixture-core/
mkdir -p "$OUT"/jar-root/fixture/lib
cp "$OUT"/fixture-classes/fixture/lib/Helper.class "$OUT"/jar-root/fixture/lib/
jar cf "$OUT/fixture-core-1.2.3.jar" -C "$OUT/jar-root" .
python3 - "$OUT" <<'PY'
import sys,zipfile
from pathlib import Path
out=Path(sys.argv[1]); payload=(out/'fixture-core-1.2.3.jar').read_bytes()
for archive,location in [('boot-application.jar','BOOT-INF/lib/fixture-core-1.2.3.jar'),('sample.war','WEB-INF/lib/fixture-core-1.2.3.jar')]:
    with zipfile.ZipFile(out/archive,'w') as z: z.writestr(location,payload)
PY
# shellcheck disable=SC2086
javac $JAVAC_TARGET -d "$OUT/runner" integration/fixture-src/integration/NestedArchiveSmoke.java
if [ "$MODE" = 'jdk-internal' ];then
    AGENT=target/jdk-asm-verification/agent-test-only.jar
    [ -f "$AGENT" ] || { echo 'Run scripts/verify-jdk-asm.sh first' >&2;exit 2; }
    EXPORT='--add-exports=java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED'
elif [ "$MODE" = 'official' ];then
    AGENT=target/runtime-sbom-agent-1.0.0-rc16.jar
    EXPORT=''
    [ -f "$AGENT" ] || { echo 'Run mvn clean package first' >&2;exit 2; }
else
    echo 'Usage: verify-nested-archives.sh jdk-internal|official' >&2;exit 2
fi
for type in boot war;do
    if [ "$type" = boot ];then archive="$OUT/boot-application.jar"; nested='BOOT-INF/lib/fixture-core-1.2.3.jar';else archive="$OUT/sample.war";nested='WEB-INF/lib/fixture-core-1.2.3.jar';fi
    # shellcheck disable=SC2086
    java $EXPORT "-javaagent:$AGENT=output=$OUT/$type.json,interval=0,resourceProbe=false,tracePackages=fixture.lib" -cp "$OUT/runner" integration.NestedArchiveSmoke "$archive" "$nested" 7 >"$OUT/$type.app.log" 2>"$OUT/$type.agent.log"
    python3 scripts/verify-nested-evidence.py "$OUT/$type.json" "$OUT/$type.app.log" "$OUT/fixture-core-1.2.3.jar" "$nested"
done
echo "PASS: synthetic nested JAR provenance and live ASM calls ($MODE)"
