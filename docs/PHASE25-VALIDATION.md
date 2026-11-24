# Phase 25: official ASM build diagnostics and staging evidence

## What was directly executed

- Preflight of POM config and toolchain: ASM 9.7.1, Maven Shade relocation, `maven.compiler.release=8`, premain manifest requirements; Maven was absent so the toolchain gate correctly returned HOLD.
- Attempt to run `sh scripts/phase22-official-build.sh`: returned exit code 2 and emitted "Maven not installed, official Agent was NOT built".
- `phase25-ci-diagnose.py` classified the actual build attempt as `MAVEN_MISSING`. No substitute third-party ASM or test-only JDK-internal ASM was presented as an official binary.
- Phase25 new tests: 17/17 passed. Phase24 unit/negative tests: 16/16 passed after fixing a version-upgrade test literal.
- JDK 21 built-in ASM test-only instrumentation: 12/12 method entries recorded and zero transform failures.
- 3-class-loader separation: 3 and 5 observed hits from visible loaders; the isolated loader was `CLASS_LOADED` only.
- Python Collector regression: 14 total, 12 passed, 2 skipped.
- Phase25 fast gate: 5 groups passed. Full gate has an interrupted rerun and is *not* claimed as successful. During the initial attempt, the predecessor Phase23 regression reported 9/9 groups passed.

## Evidence locations

- `results/phase25/build-preflight.json` — actual Maven/JDK toolchain capability check
- `results/phase25/official-build-attempt.json` + `.log` — real attempted build and failure
- `results/phase25/ci-diagnostics.json` — diagnosed failure and source log SHA-256
- `results/phase25/actual-jdk-asm.log`, `actual-loader.log` — test-only instrumentation
- `results/phase25/collector-regression.log` — Collector tests
- `results/phase25/local-gate.json` — fast gate, scoped appropriately
- `results/phase25/release-review.json` — HOLD status and missing evidence

## CI quality controls

1. Pin ASM 9.7.1 and verify the resolved dependency tree.
2. Shade `org.objectweb.asm` to `com.iruen.shaded.asm`; verify binary class versions do not exceed Java 8 major 52.
3. Reuse the exact same artifact SHA-256 for all JDK and WAS tests; reject mismatched version, SHA, PURL and source archive identity.
4. Check actual HTTP evidence from Spring Boot 2/3 and Tomcat 9/10.1; staging success is not proof of production TPS/P95 performance.
5. Collect diagnostics even on a failed build, without concealing build failure.
6. Require explicit human release review. Never auto-deploy to any runtime.

## Release blockers

- Official Maven build not executed successfully, so shaded ASM packaging and Java 8 link compatibility are still unproven.
- JDK 8/11/17/21 CI and Spring Boot 2/3/Tomcat 9/10.1 live results are not yet available.
- JEUS, WebLogic and AIX JDK/WAS compatibility requires independently provisioned environments and signed-off acceptance evidence.
- Software supply-chain provenance is a log/sha-linked manifest, not a signed artifact attestation.

## Result

**OFFLINE TESTS: scoped PASS. OFFICIAL RELEASE BUILD: HOLD. STAGING REVIEW: HOLD. PRODUCTION DEPLOYMENT: HOLD.**
