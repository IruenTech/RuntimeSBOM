# Phase 18: official ASM release and live-WAS qualification

## Scope

The distributable agent is built with **official ASM 9.7.1** and shaded to `com.iruen.shaded.asm`.
JDK 21-internal ASM is used *only* in local development tests and must not be distributed or accepted as release evidence.
The build machine for this package cannot access Maven Central and has no Maven binary; the official build is therefore **unverified here**.

## Check the actual official release binary

Build a single binary once with Maven on JDK 8 or later:

```bash
mvn -B -DskipTests clean package
python3 scripts/phase18-audit-jar.py target/runtime-sbom-agent-1.0.0-rc9.jar --out results/phase18/official-jar-audit.json
```

The audit checks jar integrity, shaded ASM, manifest, Java 8 class-file major <= 52, and an SHA-256. It does **not** authenticate Maven Central or independently verify the dependency supply chain. Pin artifact checksums / use a trusted artifact repository for that requirement.

On **each** JDK (8, 11, 17, 21) run the **same file**:

```bash
sh scripts/phase18-verify-official-binary.sh
cp results/phase18/jdk-evidence.json results/phase18/jdk-matrix/jdk-8.json # adjust version
```

Keep the same `target/runtime-sbom-agent-1.0.0-rc9.jar` bytes across runs. The GitHub workflow builds once and downloads this exact artifact into downstream jobs.

## Live application integration

Supported staging commands:

```bash
python3 scripts/phase14-live-was.py --app spring-boot2 --duration 30 --concurrency 8 --out-dir results/phase18/live
python3 scripts/phase14-live-was.py --app spring-boot3 --duration 30 --concurrency 8 --out-dir results/phase18/live
python3 scripts/phase14-live-was.py --app tomcat9 --tomcat-home /opt/apache-tomcat-9 --duration 30 --concurrency 8 --out-dir results/phase18/live
python3 scripts/phase14-live-was.py --app tomcat10 --tomcat-home /opt/apache-tomcat-10.1 --duration 30 --concurrency 8 --out-dir results/phase18/live
```

Tomcat installations must be supplied by the authorized operator; this project **does not** ship or automatically download Tomcat. Live tests are **not verified** in the local build environment. Loopback workloads contain no real user data.

### Acceptance thresholds

Defaults for **this RC gate only**: max 15% successful TPS regression, max 25% P95 response-time increase relative to the no-agent baseline; these are illustrative gating defaults, not customer SLAs. The summary must include the exact shaded-JAR SHA-256, exact PURL `pkg:maven/org.apache.commons/commons-lang3@3.14.0`, and nonzero `METHOD_EXECUTED` evidence.

```bash
python3 scripts/phase18-acceptance.py --agent target/runtime-sbom-agent-1.0.0-rc9.jar --jdk-dir results/phase18/jdk-matrix --live-dir results/phase18/live
```

Required: four JDK evidence files and four real application results. Missing, synthetic, stale or wrong-JAR evidence => `HOLD`. Even a complete set only yields `ELIGIBLE_FOR_HUMAN_REVIEW`; `productionDeployment` is always `HOLD` pending independent engineering approval and vendor-hosted tests.

## Enterprise vendor field procedure

For JEUS, WebLogic and IBM AIX vendor JVM:

1. Validate an approved exact Java executable and vendor-supported Instrumentation API with a designated staging instance.
2. Run `python3 scripts/phase17-field-evidence.py` with a locally produced CycloneDX SBOM and known PURL, capture JVM vendor/version, server logs and exact agent digest.
3. Check classloader isolation, APP/SHARED library duplicates, actual entry counts, bounded event memory, queue restart, shutdown behavior, and rollback.
4. Run 30-minute steady-state and restart tests at fixed synthetic load; capture p50/p95/p99, CPU, GC, RSS/heap and verification counters.
5. Review logs and artifacts with the customer. Do not claim vendor certification from synthetic Java URLClassLoader tests or local Linux CI.

## Known limitations

- Offline tests do not validate an official shaded ASM package.
- A SHA-256 links test evidence to an artifact; it is not an authenticity proof.
- Java 8 `javac` must use `-source 8 -target 8`; `--release 8` requires Java 9+.
- Some locked-down class loaders cannot resolve the Agent Recorder. Those are intentionally tracked as loaded rather than executed.
- Running Jar/WAR tests in CI is not a substitute for a customer staging environment.
- CycloneDX properties represent observed method entries; lack of a count does not demonstrate non-use of code.
