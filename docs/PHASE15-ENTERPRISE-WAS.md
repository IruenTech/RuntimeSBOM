# Phase 15 Enterprise WAS / AIX Validation Runbook

## Supported scope vs. evidence
- Proven here: Java 8 target compilation on JDK 21; isolated/delegated loader visibility; local HTTP fault injection; bounded retries; process restart and CycloneDX JSON output with the **offline ASM stub**.
- Not proven here: official shaded ASM agent build; real JEUS/WebLogic/AIX runtime; Tomcat/Spring Boot live app; JDK 8/11/17 runtime execution. The release gate MUST stay HOLD.

## Before deployment (staging only)
1. Obtain exact JVM vendor/version and WAS version, supported Instrumentation flags, class loader delegation and application/shared library structure.
2. Build shaded Agent with `mvn clean package`; inspect shaded relocation and manifest; run `scripts/verify-official-asm.sh` and validate against actual JVM.
3. Enable only `-javaagent:/absolute/path/...jar=output=/secure/path/sbom.json,interval=60,tracePackages=one.narrow.package,maxTransformedClasses=1000,maxTransformErrors=10,sampleEvery=100`.
4. In a staging environment, start with `tracePackages` absent (loading evidence only), compare class loader identities and SBOM against deployed WAR/EAR contents. Enable method tracing one package at a time.
5. Verify the target app sees identical `com.iruen.runtimesbom.Recorder` Class instance; otherwise the transformer MUST skip instrumentation. Do not copy Recorder classes into deployed application packages.
6. Repeat with parent-first and parent-last loader policies; test redeployment, multiple apps with same dependency, shared libraries, EAR and WAR, and isolated loaders.
7. For AIX, verify IBM Semeru/OpenJ9 or applicable vendor JVM and supported Java 8 bytecode APIs, filesystem paths, SSL truststore, and native thread/GC behavior. Never assume Linux JDK test success applies to AIX.
8. Test collector down, 503/429 recovery, 401 rejection, JVM restart, read-only output directory, disk full, and safe startup if Agent configuration fails. Validate application continuity.
9. Capture TPS/P95/P99, RSS, heap, GC pause, thread counts, startup time, timeouts under consistent prewarmed workloads with and without Agent. Define application-specific SLO thresholds before rollout.
10. Rollback: remove the `-javaagent` JVM flag and restart the affected WAS instance. Creating the kill-switch file only disables new events; it does **not** reverse transformed classes. Ensure the central collector is TLS protected and bearer credentials remain outside JVM launch arguments.

## Collector outage behavior
The Phase15 HTTP client makes at most three short sequential attempts for 408/429/500/502/503/504 or I/O errors. It never retries 401/403/4xx (except 408/429), and never sends remote plain HTTP. A failed upload increments `uploadFailures`; the local SBOM remains on disk. There is **no durable multi-file retry queue**. A future scheduled snapshot may supersede older snapshot data, so this mechanism is not guaranteed event delivery.

## Required acceptance evidence
- Exact WAS / OS / JVM / vendor build identifiers, official ASM jar sha256, configuration flags, service topology, plugin versions
- Results JSON/logs from the official build and run tests; reproducible HTTP requests
- Per-component PURL/sha256 precision and recall vs. independent deployed JAR inventory
- Evidence that crash-free execution and scoped class loader fallback are preserved
- P95/P99/TPS, CPU/GC/heap under representative duration and traffic
- Approval by WAS owner, application owner and platform/security staff
