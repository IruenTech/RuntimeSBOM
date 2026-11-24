#!/bin/sh
# Offline Java agent transport validation only; ASM instrumentation is intentionally excluded.
set -eu
cd "$(dirname "$0")/.."
mkdir -p target/offline-validation/com/iruen/runtimesbom target/offline-validation/classes
cat > target/offline-validation/com/iruen/runtimesbom/AsmTransformer.java <<'JAVA'
package com.iruen.runtimesbom;
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
/** Offline stub: this does not perform ASM instrumentation. */
public final class AsmTransformer implements ClassFileTransformer {
  public byte[] transform(ClassLoader l,String n,Class<?> c,ProtectionDomain d,byte[] b){return null;}
}
JAVA
find src/main/java -name '*.java' ! -name 'AsmTransformer.java' > target/offline-validation/sources.txt
printf '%s\n' target/offline-validation/com/iruen/runtimesbom/AsmTransformer.java >> target/offline-validation/sources.txt
javac --release 8 -d target/offline-validation/classes @target/offline-validation/sources.txt
jar cfm target/offline-validation/agent-validation-only.jar MANIFEST.MF -C target/offline-validation/classes .
javac --release 8 -d target/offline-validation/classes src/test/java/example/*.java
jar cf target/offline-validation/demo.jar -C target/offline-validation/classes example
python3 -m unittest discover -s collector/tests -v

# Safe-control tests compile and execute against Agent classes; ASM is stubbed.
javac --release 8 -cp target/offline-validation/classes -d target/offline-validation/classes src/test/java/com/iruen/runtimesbom/OperationalSafetyTest.java src/test/java/com/iruen/runtimesbom/RecorderBench.java src/test/java/com/iruen/runtimesbom/ConcurrencyStressTest.java
java -cp target/offline-validation/classes com.iruen.runtimesbom.OperationalSafetyTest

java -cp target/offline-validation/classes com.iruen.runtimesbom.ConcurrencyStressTest
