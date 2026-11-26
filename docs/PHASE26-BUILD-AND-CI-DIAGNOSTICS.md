# Phase 26: Official ASM and Spring Boot 2/3 CI follow-through

## Scope

Phase 26 preserves v1.0.0-rc16 and the previous Spring Boot 3 `jar:nested:` provenance hotfix. This is **not a new, locally-certified Agent binary**. The official ASM build and GitHub Actions must run in the project's actual CI; local JDK21 ASM tests are for regression only.

### What is new

1. `scripts/phase26-ci-diagnostics.py` redacts common credentials in surfaced error excerpts and separates **Maven dependency/compilation/JDK failures** from **PURL missing** and **METHOD_EXECUTED missing**. It records error excerpts and SHA-256 of the source logs. Diagnostics never convert a failed job into PASS.
2. `scripts/phase14-live-was.py` prints the actual Maven error lines to CI when the application fails to build and writes `phase26-build-diagnostic.json`.
3. `scripts/phase21-staging-live.py` writes `phase26-staging-failure.json` if the live test fails, including the server and JVM evidence.
4. `.github/workflows/phase26-staging.yml` runs the **same official shaded JAR**, JDK 8/11/17/21 matrix, and Spring Boot 2/3 + Tomcat 9/10 matrix. It also **compiles Spring Boot 2 separately on JDK 8** to isolate the original Maven build issue.
5. The previous Phase25 workflow remains available manually; automatic pushes now invoke Phase26, avoiding duplicate expensive matrix jobs.

## How to run on GitHub

1. Copy the updated source files into the Git repository. Verify `pom.xml` and `.github/workflows/phase26-staging.yml` are at the repository root.
2. Commit/push to `main` or manually select **Phase26 official ASM exact-binary WAS diagnostics (never auto-deploy)** in Actions.
3. Confirm `official-build`, `boot2-build-isolation`, `jdk-matrix`, `was-matrix`, and `review` statuses. A failing review is expected until all individual jobs pass and the complete evidence checks pass.
4. If `boot2-build-isolation` fails, download **phase26-boot2-isolated-build-log**. The actual Maven error will be in `build.log` and categorized in `diagnostics.json`.
5. If `was-matrix` fails, download **phase26-was-<app>**, containing `phase26-diagnostic.json`, `build.log`, `phase21-live-command.log`, and any produced `asm-traced/sbom.json`/`server.log`.
6. If all tests pass, `review` may say `ELIGIBLE_FOR_HUMAN_REVIEW`—this is not a production deployment approval. Actual JEUS/WebLogic/AIX testing remains unperformed by GitHub's matrix.

## Local offline validation

`python3 scripts/phase26-local-gate.py`

The local gate tests the updated diagnostics, nested-JAR metadata, ASM execution with JDK21's **test-only ASM**, and Phase25 regression. It does **not** claim that a real Spring Boot/Tomcat server was started.

## CI troubleshooting

- **Dependency/POM failure:** inspect earliest `Non-resolvable parent POM` or `[ERROR] Failed to execute goal` in `build.log`; do not assume a Java Agent issue.
- **PURL missing, but execution count positive:** nested JAR Maven metadata/inner JAR extraction issue (the Spring Boot 3 hotfix addresses this previously observed failure).
- **PURL present, METHOD_EXECUTED absent:** investigate transformer, tracePackages, class loader isolation and Recorder event attribution.
- **Archive SHA mismatch:** verify the `commons-lang3` bytes extracted from BOOT-INF/lib or WEB-INF/lib match the runtime component hash; never accept filename-only metadata as a match.
- **Review HOLD:** read `results/phase24/staging-manifest.json` and `results/phase25/release-review.json`; do not force or skip release checks.

## Unverified items

No official ASM dependencies/Maven toolchain are available in this analysis environment. The reported success of the user-run GitHub job is a user report, not a result re-executed here. Spring Boot 2's earlier build failure root cause cannot be established without the isolated Maven `build.log`.
