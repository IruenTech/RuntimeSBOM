#!/bin/sh
# Requires extracted Tomcat 9 at CATALINA_HOME. It uses a test-only CATALINA_BASE.
set -eu
cd "$(dirname "$0")/.."
: "${CATALINA_HOME:?Set CATALINA_HOME to an extracted Tomcat 9 installation}"
[ -f target/runtime-sbom-agent-1.0.0-rc16.jar ] || { echo 'Build Agent first: mvn clean package' >&2;exit 2; }
(cd integration/apps/tomcat9-war && mvn -B -DskipTests clean package)
OUT=$(pwd)/target/live-tomcat9
rm -rf "$OUT"; mkdir -p "$OUT/base/conf" "$OUT/base/logs" "$OUT/base/temp" "$OUT/base/webapps" "$OUT/base/work"
cp -R "$CATALINA_HOME"/conf/. "$OUT/base/conf/"
cp integration/apps/tomcat9-war/target/sbom-demo.war "$OUT/base/webapps/"
# Avoid modifying target install or reusing production CATALINA_BASE.
AGENT=$(pwd)/target/runtime-sbom-agent-1.0.0-rc16.jar
export CATALINA_BASE="$OUT/base"
export CATALINA_OPTS="${CATALINA_OPTS:-} -javaagent:$AGENT=output=$OUT/sbom.json,interval=1,resourceProbe=true,tracePackages=org.apache.commons.lang3"
"$CATALINA_HOME/bin/catalina.sh" run >"$OUT/app.log" 2>&1 &
PID=$!
trap 'kill "$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true' EXIT INT TERM
READY=0
for attempt in $(seq 1 60); do
  if curl -fsS --max-time 2 http://127.0.0.1:8080/sbom-demo/health/sbom >"$OUT/response.txt" 2>/dev/null;then READY=1;break;fi
  sleep 1
done
[ "$READY" -eq 1 ] || { echo 'FAIL: Tomcat endpoint did not start' >&2;exit 3; }
grep -Fxq 'mobs-emitnur' "$OUT/response.txt" || { echo 'FAIL: unexpected Tomcat response' >&2;exit 3; }
kill "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true
trap - EXIT INT TERM
python3 scripts/check-real-was-evidence.py "$OUT/sbom.json"
echo 'PASS: live Tomcat 9 WAR integration'
