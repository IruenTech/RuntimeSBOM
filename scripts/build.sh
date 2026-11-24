#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
command -v mvn >/dev/null 2>&1 || { echo 'Maven required: ASM 9.7.1 cannot be resolved by this offline build script.' >&2; exit 1; }
mvn -B -DskipTests package
