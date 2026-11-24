#!/bin/sh
# Strict synthetic *fixture* identity, provenance, loader and execution tests.
# Neither mode by itself proves live Tomcat/Spring Boot performance or inventory completeness.
set -eu
cd "$(dirname "$0")/.."
MODE=${1:-jdk-internal}
OUT=results/phase20
mkdir -p "$OUT"
case "$MODE" in
  jdk-internal)
    [ "$(java -version 2>&1 | head -1 | sed -n 's/.*version "\([0-9][0-9]*\).*/\1/p')" = '21' ] || { echo 'internal ASM validation requires JDK 21' >&2;exit 2; }
    sh scripts/verify-jdk-asm.sh
    ;;
  official)
    JAR=target/runtime-sbom-agent-1.0.0-rc16.jar
    [ -f "$JAR" ] || { echo 'Official release JAR unavailable. Build with Maven first.' >&2;exit 2; }
    python3 scripts/phase18-audit-jar.py "$JAR" --out "$OUT/official-jar-audit.json"
    ;;
  *) echo 'Usage: phase20-fixture-gate.sh jdk-internal|official' >&2;exit 2;;
esac
sh scripts/phase19-provenance-test.sh "$MODE"
sh scripts/verify-nested-archives.sh "$MODE"
python3 scripts/phase20-make-truth.py --out-dir "$OUT"
for kind in provenance boot war;do
  if [ "$kind" = 'provenance' ];then sbom=target/phase19-provenance/sbom.json;else sbom=target/phase9-nested/$kind.json;fi
  python3 scripts/phase20-accuracy.py --truth "$OUT/truth-$kind.json" --sbom "$sbom" \
    --out "$OUT/accuracy-$MODE-$kind.json" --require-perfect
done
python3 scripts/phase20-static-inventory.py target/phase9-nested/boot-application.jar \
  --sbom target/phase9-nested/boot.json --out "$OUT/static-boot-$MODE.json"
python3 scripts/phase20-static-inventory.py target/phase9-nested/sample.war \
  --sbom target/phase9-nested/war.json --out "$OUT/static-war-$MODE.json"
python3 - "$MODE" <<'STATIC_CHECK'
import json,sys
from pathlib import Path
out=Path('results/phase20')
for typ in ('boot','war'):
    x=json.loads((out/f'static-{typ}-{sys.argv[1]}.json').read_text())
    assert x['archiveComponents']==1 and x['statusCounts'].get('OBSERVED_EXACT_IDENTITY')==1, x
print('PASS: static archive inventories agree with runtime identities; packaged-only not treated as FN')
STATIC_CHECK
python3 - "$MODE" <<'PY'
import hashlib, json, sys
from pathlib import Path
mode=sys.argv[1]
out=Path('results/phase20'); docs=[json.loads((out/f'accuracy-{mode}-{k}.json').read_text()) for k in ('provenance','boot','war')]
summary={'stage':20,'mode':mode,'scope':'six synthetic fixture class-loader instances, not real WAS',
         'groundTruthMethod':'JAR file digests + independent fixture call plan, not SBOM-derived',
         'testFixtureInstances':sum(x['expectedInstances'] for x in docs),
         'TP':sum(x['truePositives'] for x in docs),'FP':sum(x['falsePositives'] for x in docs),
         'FN':sum(x['falseNegatives'] for x in docs),
         'executionAttributionCorrect':all(x['executionEvidenceExact'] for x in docs),
         'distinctLoaders':all(x['classLoaderTokensDistinct'] for x in docs),
         'strictFixturePass':all(x['strictFixturePass'] for x in docs)}
if mode=='official':
 p=Path('target/runtime-sbom-agent-1.0.0-rc16.jar')
 summary['officialJarSha256']=hashlib.sha256(p.read_bytes()).hexdigest()
else:summary['officialJarSha256']=None
(out/f'fixture-summary-{mode}.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
assert summary['strictFixturePass']
PY
