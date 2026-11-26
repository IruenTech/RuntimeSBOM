# RuntimeSBOM Agent — Phase 26 (rc16 CI hardening)

**Project state:** The user reports that the previous Spring Boot 3 GitHub Actions hotfix succeeded. This package carries forward that fix and adds independently diagnosable Spring Boot 2 Maven builds and CI evidence handling. The GitHub run has **not** been executed from this container; no fresh official shaded Agent binary is bundled.

**New Phase26 deliverables**

- `scripts/phase26-ci-diagnostics.py`: captures real Maven errors (dependencies, Java release, compilation, packaging) and separates `MISSING_PURL` from `MISSING_METHOD_EXECUTION`. It never declares unexecuted builds successful.
- `scripts/phase14-live-was.py` and `scripts/phase21-staging-live.py`: preserve and display actionable build/execution failure diagnoses instead of only a generic Python traceback.
- `.github/workflows/phase26-staging.yml`: the official ASM JAR is built once and used across the JDK/WAS matrix. A new independent JDK 8 Spring Boot 2 compile job publishes logs even when the main matrix fails. `review` remains fail-closed and never deploys.
- `.github/workflows/phase25-official-asm.yml`: previous workflow is now manual-only to prevent duplicate workflows on a push.
- `tests/test_phase26_diagnostics.py` and `scripts/phase26-local-gate.py`: new regression tests and a truthful local test report.
- Detailed directions: `docs/PHASE26-BUILD-AND-CI-DIAGNOSTICS.md`.

**Actual local verification (2026-11-26):** 18/18 new unit tests, Spring Boot 3 nested URL 29 assertions, ASM JDK21 test-only smoke, real nested-JAR fixture method entries, Phase25 short regression and Collector tests (12 passing, 2 skipped). Five Phase26 local validation groups passed. Official ASM/GitHub and Java8/11/17 real builds were **not executed locally**, and Spring Boot 2's earlier Maven failure cause is **unknown without its actual `build.log`**.

```bash
python3 scripts/phase26-local-gate.py
```

To run official validation, push to `main` and select **Phase26 official ASM exact-binary WAS diagnostics (never auto-deploy)** in GitHub Actions (or check the automatically triggered run). If Spring Boot 2 fails, download `phase26-boot2-isolated-build-log` and inspect `diagnostics.json`/`build.log`. The official release approval remains a human decision after complete evidence.

---

## Historical Phase25 README (retained for context)

# RuntimeSBOM Agent — Phase 25 (v1.0.0-rc16)

Java 8 API-compatible Java Instrumentation agent, ASM method-entry tracking, class loader/JAR provenance, CycloneDX 1.6, durable SBOM upload queue, SQLite Collector, and dashboard. Phase 25 focuses on **official release build troubleshooting and reproducible CI evidence**, not unsupported claims of a production-ready release.

## What changed in Phase 25

1. **Official build preflight**: `scripts/phase25-build-preflight.py` checks the real OW2 ASM 9.7.1 Maven coordinate, Java 8 release target, Shade relocation, Agent manifest, and local Maven/Java availability. A passing POM configuration check is **not** proof a binary was built.
2. **CI failure root-cause classification**: `scripts/phase25-ci-diagnose.py` classifies missing Maven, DNS/repository failures, compiler/JDK errors, ASM linkage, VerifyError, startup failure, timeouts, and artifact SHA mismatches. It publishes the SHA-256 of actual logs without copying arbitrary log lines or potential credentials into the summary.
3. **CI workflow**: `.github/workflows/phase25-official-asm.yml` builds once with real ASM 9.7.1, reuses exactly the same Agent SHA-256 for JDK 8/11/17/21 and Spring Boot 2/3 + Tomcat 9/10.1 staging tests, runs failure diagnostics even if Maven exits unsuccessfully, and collects review results. *It never automatically deploys to production.* The old phase24 workflow remains manual-only.
4. **Fail-closed release review**: `scripts/phase25-review.py` summarizes exact-binary evidence and diagnoses; absence of official build/test evidence remains `HOLD`. A complete, matching CI matrix can only reach `ELIGIBLE_FOR_HUMAN_REVIEW`, never automatic production approval.
5. **Negative tests and offline gate**: `tests/test_phase25_pipeline.py` (17 tests) and `scripts/phase25-local-gate.py`. All Java Agent and Collector source is inherited and versioned rc16; test-only JDK-internal ASM remains separate from the official distribution path.

## Actual validation in this environment (2026-11-24)

Environment: **JDK 21**, Python, **no Maven executable**, and **Maven Central DNS unavailable**. The official ASM Maven build was attempted and returned exit code **2** (`MAVEN_MISSING`). There is **no officially built rc16 Agent JAR** in this package and **no actual Spring Boot/Tomcat/JEUS/WebLogic/AIX integration result**.

| Test | Actual observation |
| --- | --- |
| New Phase25 unit/negative tests | 17/17 passed |
| Rechecked Phase24 unit/negative tests | 16/16 passed |
| Phase25 *fast* local gate | 5/5 groups passed (does **not** include prior Java/Collector regression) |
| Phase23 regression run during first Phase25 full-gate attempt | 9/9 predecessor groups passed; full Phase25 run was interrupted, so it is **not** labeled passed |
| JDK 21 built-in ASM smoke test | 12/12 method entries observed; transform failures 0 |
| Isolated class loader test | 3 loaders; observed 3 and 5 entries; third loader loading-only |
| Collector regression | 14 tests run, 12 passed + 2 skipped |
| Official ASM 9.7.1 Maven release build | HOLD — Maven not installed |
| Real JDK 8/11/17 matrix and Spring Boot/Tomcat live tests | NOT EXECUTED |
| JEUS/WebLogic/AIX product compatibility | NOT EXECUTED |

Results and logs are preserved under `results/phase25/`. The test-only JDK 21 ASM path must never be described as the official shaded release Agent.

## Reproduce the tests

```sh
python3 scripts/phase25-local-gate.py --fast
python3 -m unittest discover -s tests -p 'test_phase25_*.py' -v
python3 scripts/phase25-build-preflight.py --require-toolchain
python3 scripts/phase25-ci-diagnose.py --log results/phase25/official-build-attempt.log
python3 scripts/phase25-review.py
```

The latter two **do not** create build evidence. Official build preflight and review return exit code `3` when the required environment/evidence is unavailable.

## Run the real official ASM CI

1. Upload the entire project, **including hidden `.github/`**, into a **private GitHub repository**.
2. In **Actions**, run **Phase25 official ASM build diagnostics and staging (never auto-deploy)** or push to `main`.
3. Inspect `official-build` (Maven package log and dependency tree), `jdk-matrix`, `was-matrix`, then `review`. Download `phase25-official-exact-binary`, per-JDK and per-WAS artifacts, and `phase25-exact-binary-review-report`.
4. If a job fails, inspect `results/phase25/ci-diagnostics.json` for classified causes and the raw job logs. Correct those causes before retrying; never replace ASM with `jdk.internal.org.objectweb.asm` in a release.
5. Treat `ELIGIBLE_FOR_HUMAN_REVIEW` as a **staging review outcome only**. Independent security, performance, rollout/rollback and vendor WAS validation remain required for production.

## Project layout

- `src/main/java/com/iruen/runtimesbom`: Java 8-compatible Agent (ASM transformer and provenance)
- `pom.xml`: real ASM 9.7.1 / Maven Shade release configuration
- `collector/`: Collector, database, dashboard and regression tests
- `integration/apps/`: actual staging web applications (requires Maven and, for Tomcat, a test installation)
- `.github/workflows/phase25-official-asm.yml`: active official build and staging CI
- `scripts/phase25-*.py`: preflight, diagnostic, review, offline gate
- `docs/PHASE25-VALIDATION.md`: observed results, limitations and release acceptance checklist
- `results/phase25/`: **actual local** diagnostic reports and logs

**Production deployment remains `HOLD`.**
