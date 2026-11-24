# RuntimeSBOM v1.0.0-rc1 — evidence-based acceptance matrix

| Target | Test | Status in this environment | Acceptance criteria |
|---|---|---|---|
| JDK 21 internal ASM test-only build | actual instrumented Worker.compute | PASS | 12 exact entries; 0 transform failures |
| JDK 21 internal ASM test-only build | Boot-like nested JAR fixture | PASS | exact PURL/hash/source and 7 entries |
| JDK 21 internal ASM test-only build | WAR-like nested JAR fixture | PASS | exact PURL/hash/source and 7 entries |
| Core Java/collector | class loader isolation and Python regression | PASS | 2 separate origins; collector 10/10 |
| JDK 8,11,17,21 official ASM 9.7.1 | Maven Shade + execution | NOT RUN | `scripts/verify-official-asm.sh` each JDK green |
| Spring Boot 2.7.18 | real embedded Tomcat HTTP endpoint | NOT RUN | `scripts/verify-live-spring-boot2.sh` green |
| Tomcat 9, exploded WAR | real HTTP servlet endpoint | NOT RUN | `scripts/verify-live-tomcat9.sh` green |
| Spring Boot 3.x | actual application | NOT PROVIDED | verify nested-jar URL and Java 17 support |
| JEUS/WebLogic | commercial WAS, parent/child classloaders | NOT RUN | evidence accuracy and no service disruption |
| AIX Java 8 | actual OpenJ9/vendor runtime | NOT RUN | startup, instrumentation, resource limits, correctness |
| Performance | equivalent workload Agent OFF/ON | NOT RUN | agree SLO on p95, p99, TPS, CPU, RSS, GC, startup latency |

## Synthetic fixture metrics

Constructed nested libraries: 2. Expected Maven coordinates correctly recognized: 2/2. Expected SHA-256 and source paths correctly recognized: 2/2. Expected method calls correctly counted: 2/2. This is a deterministic test oracle with a known library and **cannot establish field accuracy, false positive rate, or coverage of real-world SBOMs**.

## Required production gates

- Classloader/provenance: missing CodeSource, multiple versions, parent-first/child-first, Tomcat shared libs, Spring Boot 3 URL forms, code generated at runtime.
- ASM safety: constructors, exceptions, lambdas, proxies, hot paths, nonstandard JVM bytecode, thrown errors, Recorder visibility.
- Operations: JVM startup fail-open, unbounded origin map, bounded file output, kill switch, temporary collector outage, disk full, agent JAR isolation.
- Security: HTTPS/mTLS, signed agent artifacts, per-tenant authorization, transport authentication, audit logging, secret rotation, source disclosure review.
- Accuracy: manually labeled truth set and precision/recall by archive type, package, classloader and Java version; unknown state must remain explicit.
