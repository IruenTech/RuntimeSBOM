# Phase 10 / RuntimeSBOM v1.0.0-rc1 — release candidate acceptance policy

## Observed local facts

Environment: OpenJDK 21 only. Maven and the official OW2 ASM artifact not available. The tests use a **test-only agent** built against JDK 21 internal ASM; this agent MUST NOT be distributed or deployed. In the recorded offline run, method-entry instrumentation, synthetic nested Boot/WAR archives and classloader separation passed. The offline Java compilation/transport fixture preparation (`validate-offline.sh`) runs before the Python collector suite. All 10 Python regression tests passed during a separate direct test run. The aggregated rerun timed out and has not produced a newer complete RC report.

Performance diagnostic: `results/phase10/benchmark-internal-asm.json` captures five separate JVM executions per mode, 60,000 synthetic method calls per run, and raw process and workload times. This is not a statistically validated production benchmark. It cannot justify a performance SLA.

## Required proof before a production release

1. Official ASM 9.7.1 shaded JAR builds and verification gate passes on JDK 8 / 11 / 17 / 21 (all four required). Ensure Maven compiler source/target 8 works under JDK 8; inspect bytecode class-file major=52 and relocated ASM.
2. Real Spring Boot 2.7.18 and Tomcat 9 HTTP tests pass using the actual official Agent JAR. Cover Spring Boot 3.x on Java 17 separately (not supplied here).
3. JEUS and WebLogic vendor-supported deployments: shared libraries, parent-first and child-first loaders, JPMS and custom CodeSource, memory and fail-open behavior. AIX must be tested on its actual vendor JVM, not inferred from OpenJDK/Linux.
4. Real application accuracy truth set: collect expected (group, artifact, version, JAR origin, loader) inventory independently; report TP/FP/FN, precision and recall separately for static packages, loaded classes and executed methods. Detection during a finite observation window has incomplete coverage by nature.
5. Three-mode A/B performance test in a nonproduction workload: without agent, loading-only, ASM traced. Record p50/p95/p99 HTTP response, throughput, CPU, RSS, heap and GC, JIT warm-up, startup cost, deployment platform and confidence intervals; agree bounds with customer before claiming readiness.
6. Security review: collector TLS, token storage, logging sensitivity, output destination permissions, account segregation, library metadata trust boundaries, SBOM file confidentiality, agent sign/reproducible SHA, and failure-on-disk-full procedures.
7. Operational soak/leak tests: sustained service calls, dynamic loaders, redeploy, large dependency graphs, collector unavailable, disk pressure, high concurrent method counts, kill switch verification, bounded provenance map.

Current release decision is **HOLD**: only synthetic/local aspects are verified. A `PASS` in a fixture is not proof of the vendor runtime.
