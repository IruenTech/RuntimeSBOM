#!/bin/sh
# Build official ASM 9.7.1 agent using Maven. No JDK-internal ASM fallback.
set -eu
cd "$(dirname "$0")/.."
OUT=results/phase22
JAR=target/runtime-sbom-agent-1.0.0-rc16.jar
mkdir -p "$OUT"
if ! command -v mvn >/dev/null 2>&1; then
  printf '%s\n' 'HOLD: Maven not installed, official Agent was NOT built' >&2
  exit 2
fi
if ! command -v javac >/dev/null 2>&1; then
  echo 'HOLD: JDK unavailable' >&2; exit 2
fi
mvn -B -ntp -DskipTests clean package > "$OUT/maven-package.log" 2>&1 || {
  echo 'HOLD: Maven package FAILED (see results/phase22/maven-package.log)' >&2; exit 2;
}
mvn -B -ntp dependency:tree -Dincludes=org.ow2.asm:asm -DoutputType=text > "$OUT/asm-dependency-tree.log" 2>&1 || {
  echo 'HOLD: unable to resolve ASM dependency tree' >&2; exit 2;
}
python3 scripts/phase22-binary-audit.py --agent "$JAR" --out "$OUT/binary-audit.json"
python3 - "$JAR" "$OUT/asm-dependency-tree.log" "$OUT/build.json" <<'PY'
import hashlib,json,pathlib,re,sys,datetime
jar=pathlib.Path(sys.argv[1]); tree=pathlib.Path(sys.argv[2]).read_text()
# Ensure one resolved ASM version, not merely a POM declaration.
matches=re.findall(r'org\.ow2\.asm:asm:jar:([^:\s]+):(?:compile|runtime)',tree)
if matches!=['9.7.1']:
    raise SystemExit('HOLD: expected only org.ow2.asm:asm:jar:9.7.1, saw '+str(matches))
report={'stage':22,'version':'1.0.0-rc16','status':'PASS',
        'mavenPackageSucceeded':True,'asmDependency':'org.ow2.asm:asm:jar:9.7.1',
        'artifactSha256':hashlib.sha256(jar.read_bytes()).hexdigest(),
        'builtAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'limitations':'Maven dependency resolution + structural audit; authenticity needs signed provenance'}
pathlib.Path(sys.argv[3]).write_text(json.dumps(report,indent=2)+'\n')
print('PASS official ASM Maven build and shaded JAR structural audit',report['artifactSha256'])
PY
