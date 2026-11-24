# Phase 13 operational acceptance plan

## Scope and current evidence

- Local HTTP fixture: real loopback requests with a Java built-in HttpServer. **NOT Tomcat or Spring Boot**.
- JDK 21 internal ASM: TEST-ONLY transformation, not official ASM artifact.
- Official ASM 9.7.1 shaded Maven build: UNVERIFIED in offline runtime.
- Actual Tomcat 9, Spring Boot 2.7, JEUS, WebLogic, AIX: UNVERIFIED.
- Java 8 / 11 / 17 / 21 runtime matrix: UNVERIFIED except JDK 21.

## Test procedure on an authorized staging host

1. Install Maven, a verified ASM artifact, JDKs 8/11/17/21, Tomcat 9, Spring Boot demo dependencies.
2. Build and verify `mvn -B clean verify`; verify ASM shading / manifest / SHA-256 and bytecode version 52.
3. Run `scripts/verify-official-asm.sh`, `scripts/verify-live-spring-boot2.sh`, `scripts/verify-live-tomcat9.sh` and preserve logs.
4. Perform 3+ interleaved baseline/load/trace runs at steady state under the SAME JVM and host limits. At least 10 minutes per mode; then 24h sustained soak for GC/RSS leak trends.
5. Capture TPS, HTTP errors, P50/P95/P99, host CPU, JVM CPU, heap peak, RSS, allocation rate, GC pause totals, startup, Agent error counters, identified PURLs and SHA-256 against known ground truth.
6. Repeat for each supported JDK and app server version. Test multiple class loaders, app redeploy, shutdown and JVM attach policy, if applicable.

## Proposed staging acceptance thresholds (not measured or approved)

- No Agent-caused application crash or test regression.
- No transform verification errors or unhandled exceptions. Agent fails open.
- Trace enabled steady-state throughput regression <= 5%, P95 regression <= 10%, P99 regression <= 10%, HTTP errors <= 0.1 percentage points above baseline, subject to an agreed workload.
- Heap and RSS drift statistically bounded over >= 24 h; final targets must be agreed with the WAS owner.
- Library identification precision >= 99%, recall >= 95% on curated known-component fixtures; unresolved components are explicitly flagged, not invented.
- Before approval, verify tenant auth, TLS, file permissions, credentials, and change management.

These targets are proposed gates, not claims about current performance. A single synthetic benchmark cannot meet them.

## Report interpretation

`python3 scripts/phase13-gate.py` marks the release HOLD until independent official ASM and live-system reports are supplied. It accepts JSON reports tagged PASS but does not cryptographically attest them. Test owners must independently verify logs, provenance and signed artifacts before approval.
