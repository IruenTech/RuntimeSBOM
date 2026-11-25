#!/bin/sh
# Regress Spring Boot 3 nested JAR URLs plus Boot 2 and WAR with real ZIP entry bytes.
# No remote dependencies or ASM required; Java 8 source + bytecode compatibility.
set -eu
cd "$(dirname "$0")/.."
OUT="target/phase26-nested-metadata"
mkdir -p "$OUT"
if javac -version 2>&1 | grep -Eq 'javac 1\.8(\.|$)'; then
  javac -source 8 -target 8 -d "$OUT" \
    src/main/java/com/iruen/runtimesbom/JarMetadata.java \
    src/main/java/com/iruen/runtimesbom/ResourceResolver.java \
    src/test/java/com/iruen/runtimesbom/Phase26SpringBoot3MetadataTest.java
else
  javac --release 8 -d "$OUT" \
    src/main/java/com/iruen/runtimesbom/JarMetadata.java \
    src/main/java/com/iruen/runtimesbom/ResourceResolver.java \
    src/test/java/com/iruen/runtimesbom/Phase26SpringBoot3MetadataTest.java
fi
java -cp "$OUT" com.iruen.runtimesbom.Phase26SpringBoot3MetadataTest
