# Phase 24 — Test Evidence and Release Decision

Date: 2026-11-24
Version: 1.0.0-rc15

## Verification performed

| Item | Local result | Evidence |
|---|---|---|
| JDK21 internal ASM transformation | PASS (test-only) | `results/phase23/quality-java-python-asm.log` |
| Isolated/visible class-loader evidence | PASS | `results/phase23/classloader-3-instances.log` |
| HTTP loading-only vs. actual method calls | PASS | `results/phase23/http-loading-vs-execution.log` |
| Collector regressions | PASS | `results/phase23/collector-regression.log` |
| New Phase24 negative/unit tests | 16 PASS | `results/phase24/new-24-unit-tests.log` |
| GitHub workflow static contract | PASS | `results/phase24/ci-contract.json` |
| Official ASM shaded JAR build | NOT RUN | `results/phase24/binary-preflight.json` (HOLD) |
| Actual Spring Boot/Tomcat | NOT RUN | `results/phase24/staging-manifest.json` (HOLD) |
| Java 8/11/17 runtime | NOT RUN | Only JDK21 available |
| JEUS/WebLogic/AIX runtime | NOT RUN | Vendor WAS/JVM unavailable |

Local gate: `results/phase24/local-gate.json`. The local gate **passes** when the unperformed official test correctly yields HOLD; it does not claim an official artifact was produced.

## CI evidence requirements

| Step | Required | Acceptance semantics |
|---|---|---|
| `official-build` | Maven package + ASM 9.7.1 resolution + shaded ASM + Java 8 bytecode SHA | Same exact JAR for all downstream tests |
| JDK 8/11/17/21 | Each JVM actually executes official `-javaagent` + emits quality-assessed SBOM | All four SBOM + JSON reports must exist |
| Spring Boot 2/3 | Start actual application, run baseline/load-only/ASM modes | PURL and embedded JAR SHA, executed entry evidence, HTTP SLO |
| Tomcat 9/10.1 | Start local staging Tomcat with test WAR | Same evidence as Spring Boot |
| Review | Hash-indexed manifest, strict pass/fail | Missing, mismatch, sample/drop, weak provenance => HOLD |

The manifest's SHA-256 entries *detect changes*, but they are not signed attestations and cannot authenticate an untrusted runner. Protect workflows and artifact permissions. `ELIGIBLE_FOR_HUMAN_REVIEW` is not a production deployment authorization.

## Known restrictions and risks

1. Official Maven/ASM deployment build could not be executed: `mvn` absent; Maven Central DNS unavailable.
2. Cannot infer not-used from no `METHOD_EXECUTED`: class loader isolation and incomplete coverage remain explicitly reported.
3. JDK21 internal ASM smoke is a *test harness*, not a release JAR; do not distribute `target/jdk-asm-verification/agent-test-only.jar`.
4. Test duration/performance in CI is staging-only; production P95/P99, GC and CPU require representative production-like load.
5. SHA-256 ties test artifacts to a binary **but does not replace signing, immutable CI logs or independent approval**.
6. `--release 8` ensures Java 8 library API availability at compile time under JDK21; JDK8 runtime still requires an actual JDK8 smoke test.
7. Historical `.github` workflows are archived under `docs/historical-workflows` to prevent duplicate triggers and accidental version mixups.

## Verdict

**Local validation: PASS (5/5 groups). Official binary/staging review: HOLD. Production deployment: HOLD.**
