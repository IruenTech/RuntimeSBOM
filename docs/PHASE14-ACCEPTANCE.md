# Phase 14 Acceptance / Release Candidate Criteria (v1.0.0-rc5)

| Gate | Required evidence | Tested here? |
|---|---|---|
| Official ASM 9.7.1 shaded JAR | `mvn clean package`, embedded relocated ASM, Java 8 major=52, actual bytecode transformation & `Worker.compute()` 12 calls, zero transform errors | **NO** — Maven/offline dependency unavailable |
| JDK 8/11/17/21 | official agent executes smoke per JDK, exact source test; separate CI artifacts consolidated | **NO** — only JDK 21 present |
| Spring Boot 2.7 | live HTTP baseline/loaded/ASM in local test JVM; exact PURL and method execution | **NO** — Maven/Boot dependencies unavailable |
| Spring Boot 3.3 | same, JDK 17+ | **NO** |
| Tomcat 9 | same, isolated CATALINA_BASE | **NO** — Tomcat absent |
| Tomcat 10.1 | same, Java 11+ and Jakarta servlet | **NO** — Tomcat absent |
| Reference local HTTP fixture | Java built-in HttpServer with JDK-internal ASM only | See actual stored outputs |
| Central collector | Python unit tests | See actual stored outputs |
| JEUS / WebLogic / AIX | vendor-supplied runtime, loader visibility, restart/failure-recovery and memory/leak checks | **NO** |

## Proposed internal staging gates (tunable)

- Test only on private, isolated staging systems. A passing PURL without actual `METHOD_EXECUTED` is a failure. Missing or stale evidence fails closed.
- All three HTTP modes must return zero errors. ASM versus no-agent baseline: successful TPS drop **no more than 10%**, P95 latency increase **no more than 20%**. These are initial project targets and are not a claim of production SLA.
- Capture duration, concurrency, workload type, JDK and WAS versions, process RSS, CPU time, heap/GC if available. Repeat tests (at least 5 iterations after warm-up) and add 1–24 hour soak on real application load before release review.
- No instrumentation of JDK/agent classes; opt-in package allowlist, failure-open at class transform level, kill switch, and bounded events are prerequisites. On a class loader that cannot resolve the `Recorder` hook, skip modification.
- Official ASM classfile parser not tested on the latest bytecode versions beyond available runtime; class/version compatibility requires independent tests.
- Validate that app startup remains possible with Agent **disabled**, enabled, and when the collector is down. Check bounded network timeouts and acceptable resource usage.

## Known limitations and operating risks

1. Nested JAR identification depends on application class loader / CodeSource behavior. `CodeSource` may point to the outer archive and resource probing can be incomplete; compare with the real application dependency lockfile.
2. Counters represent observed or sampled method entrances; they are not a transaction log. `LongAdder` snapshots are approximate under contention.
3. Existing classes are not automatically retransformed on attach. Preloaded evidence is not equal to a traced call.
4. Server templates must be checked by the runtime owner; the Tomcat harness rejects unexpected `server.xml` rather than modifying an unknown server config.
5. Linux `/proc` metrics are not supported on AIX. For AIX plan `svmon`, `ps`, `vmstat`, vendor JVM monitoring; do not extrapolate Linux figures.
6. The gate consumes unsigned local JSON evidence and therefore is a development gate, **not** third-party certification or tamper-evident release attestation.

## Unblock official build

On a staging machine with Maven Central access or an approved artifact repository, execute `sh scripts/verify-official-asm.sh`. Preserve its stdout/stderr, JAR SHA-256, generated SBOM and `results/phase14/official-asm.json`. Next run live Boot/Tomcat harnesses and JDK matrix. Keep `productionDeploymentDecision=NOT_APPROVED` until each required vendor environment is independently qualified.
