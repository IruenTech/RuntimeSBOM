#!/bin/sh
# Requires Maven, Java, Python and local HTTP access. Run on a test host, not production.
set -eu
cd "$(dirname "$0")/.."
[ -f target/runtime-sbom-agent-1.0.0-rc16.jar ] || { echo 'Build Agent first: mvn clean package' >&2;exit 2; }
(cd integration/apps/spring-boot2 && mvn -B -DskipTests clean package)
OUT=target/live-spring-boot2
mkdir -p "$OUT"
AGENT=$(pwd)/target/runtime-sbom-agent-1.0.0-rc16.jar
APP=$(pwd)/integration/apps/spring-boot2/target/sbom-spring-demo-1.0.0.jar
java "-javaagent:$AGENT=output=$OUT/sbom.json,interval=1,resourceProbe=true,tracePackages=org.apache.commons.lang3" -jar "$APP" --server.port=18769 >"$OUT/app.log" 2>&1 &
PID=$!
trap 'kill "$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true' EXIT INT TERM
READY=0
for attempt in $(seq 1 60); do
  if curl -fsS --max-time 2 http://127.0.0.1:18769/health/sbom >"$OUT/response.txt" 2>/dev/null; then READY=1;break;fi
  sleep 1
done
[ "$READY" -eq 1 ] || { echo 'FAIL: Spring Boot endpoint did not start' >&2; exit 3; }
grep -Fxq 'mobs-emitnur' "$OUT/response.txt" || { echo 'FAIL: unexpected Spring response' >&2;exit 3; }
kill "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true
trap - EXIT INT TERM
python3 scripts/check-real-was-evidence.py "$OUT/sbom.json"
echo 'PASS: live Spring Boot 2 application integration'
