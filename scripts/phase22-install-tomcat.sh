#!/bin/sh
# Staging ONLY. Version-pinned Apache archive download with SHA-512 check.
# Does not imply the archived release is patched or safe for production.
set -eu
if [ "$#" -ne 2 ]; then echo 'Usage: phase22-install-tomcat.sh <9.0.107|10.1.43> <destination>' >&2; exit 2; fi
VERSION=$1
DEST=$2
case "$VERSION" in 9.0.107) MAJOR=9 ;; 10.1.43) MAJOR=10 ;; *) echo 'HOLD: unsupported/unpinned Tomcat version' >&2; exit 2 ;; esac
command -v curl >/dev/null 2>&1 || { echo 'curl required' >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo 'python3 required' >&2; exit 2; }
BASE="https://archive.apache.org/dist/tomcat/tomcat-${MAJOR}/v${VERSION}/bin/apache-tomcat-${VERSION}.tar.gz"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
curl -fsSL --retry 3 --max-time 120 "$BASE" -o "$TMP/tomcat.tar.gz"
curl -fsSL --retry 3 --max-time 30 "$BASE.sha512" -o "$TMP/tomcat.sha512"
python3 - "$TMP/tomcat.tar.gz" "$TMP/tomcat.sha512" <<'PY'
import hashlib,pathlib,re,sys
p=pathlib.Path(sys.argv[1]); expected=pathlib.Path(sys.argv[2]).read_text().strip()
expected_hash=re.search(r'\b[0-9a-fA-F]{128}\b',expected)
if not expected_hash or hashlib.sha512(p.read_bytes()).hexdigest()!=expected_hash.group().lower():
 raise SystemExit('HOLD: Tomcat release archive SHA-512 mismatch')
print('PASS Tomcat tarball SHA-512 match')
PY
mkdir -p "$DEST"
tar -xzf "$TMP/tomcat.tar.gz" -C "$DEST" --strip-components=1
[ -f "$DEST/bin/catalina.sh" ] || { echo 'HOLD: Tomcat installation missing' >&2; exit 2; }
echo "Tomcat staging installation prepared: $DEST"
