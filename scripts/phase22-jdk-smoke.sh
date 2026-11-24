#!/bin/sh
# Run same already-built Agent under a single active JDK. Used separately on 8/11/17/21.
set -eu
cd "$(dirname "$0")/.."
JAR=target/runtime-sbom-agent-1.0.0-rc16.jar
[ -f "$JAR" ] || { echo 'HOLD: required release binary missing' >&2; exit 2; }
sh scripts/phase18-verify-official-binary.sh "$JAR"
JDK=$(python3 - <<'PY'
import re,subprocess
s=subprocess.run(['java','-version'],capture_output=True,text=True,check=True)
m=re.search(r'version "(?:1\.)?(\d+)',s.stderr+s.stdout)
if m is None:raise SystemExit('HOLD: cannot parse Java version')
print(m.group(1))
PY
)
case "$JDK" in 8|11|17|21) ;; *) echo 'HOLD: unqualified JDK' >&2; exit 2 ;; esac
mkdir -p results/phase22/jdk
cp results/phase18/jdk-evidence.json "results/phase22/jdk/jdk-${JDK}.json"
cp target/phase18-official-verification/sbom.json "results/phase22/jdk/jdk-${JDK}-sbom.json"
printf '%s\n' "PASS actual official binary on JDK $JDK"
