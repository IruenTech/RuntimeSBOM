#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p target/phase11-bench
javac --release 8 -d target/phase11-bench src/test/java/com/iruen/runtimesbom/CounterBenchmark.java
java -cp target/phase11-bench com.iruen.runtimesbom.CounterBenchmark
