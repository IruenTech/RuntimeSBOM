#!/bin/sh
# Uses JDK 21's internal ASM ONLY in a disposable validation build.
# Not a redistributable agent and not proof of the official Maven/shaded ASM build.
set -eu
cd "$(dirname "$0")/.."
OUT=target/jdk-asm-verification
rm -rf "$OUT"; mkdir -p "$OUT/classes" "$OUT/app" "$OUT/work"
find src/main/java -name '*.java' ! -name AsmTransformer.java > "$OUT/sources.txt"
sed 's/org.objectweb.asm/jdk.internal.org.objectweb.asm/g' src/main/java/com/iruen/runtimesbom/AsmTransformer.java > "$OUT/work/AsmTransformer.java"
javac --add-exports java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED -cp "$OUT/classes" -d "$OUT/classes" @"$OUT/sources.txt" "$OUT/work/AsmTransformer.java" 2> "$OUT/javac-internal.log"
jar cfm "$OUT/agent-test-only.jar" MANIFEST.MF -C "$OUT/classes" .
javac --release 8 -d "$OUT/app" src/test/java/example/*.java
# The main class is loaded from code-source directory, not from ASM.
java --add-exports java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED \
  "-javaagent:$OUT/agent-test-only.jar=output=$OUT/sbom.json,interval=0,resourceProbe=false,tracePackages=example,sampleEvery=1" \
  -cp "$OUT/app" example.InstrumentationSmoke > "$OUT/app.log" 2> "$OUT/agent.log"
python3 scripts/verify-instrumentation.py "$OUT/sbom.json" "$OUT/app.log"
# Verify failure-safe operation on malformed class bytes directly using a Java test class.
javac --release 8 -cp "$OUT/classes" -d "$OUT/classes" src/test/java/com/iruen/runtimesbom/OperationalSafetyTest.java
java -cp "$OUT/classes" com.iruen.runtimesbom.OperationalSafetyTest
printf '%s\n' 'JDK21 internal ASM validation PASS (NOT official ASM release build)'
