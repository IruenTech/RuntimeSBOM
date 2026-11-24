# Phase 18 Local Test Evidence

- Date: 2026-11-24 UTC (local test container)
- Java: OpenJDK 21.0.12.1, **JDK-internal ASM test-only adapter**
- Maven: absent. ASM 9.7.1 binary not available in local Maven repository, network fetch failed.
- Release: `1.0.0-rc9`, deployment decision `HOLD`.

## Executed local tests

`python3 scripts/phase18-local-gate.py`: **6/6 groups PASS**:

1. Java method entry smoke (`scripts/verify-jdk-asm.sh`) — 12 expected method entries from a Java fixture;
2. HTTP server test (`scripts/phase18-http-proof.py`) — ASM 177,760 `Worker.compute` method entries, loaded-only 0, 0 HTTP errors;
3. Class loader separation (`scripts/phase17-loader-test.sh jdk-internal`) — observed 3+5 entries; isolated 7 invocations not falsely attributed;
4. Durable delivery queue / Collector (`scripts/phase16-queue-tests.sh`) — Python 14/14 tests pass plus queue Java test;
5. Phase18 artifact audit/acceptance tests (`python3 -m unittest discover -s tests -p test_phase18_approval.py`) — 8/8 tests pass;
6. Without an official shaded jar and live WAS evidence (`scripts/phase18-acceptance.py`) — **HOLD** as required.

Additional negative-control: attempting to audit `target/jdk-asm-verification/agent-test-only.jar` returns `FAIL`, as it must. This prevents accidentally labeling the internal-ASM fixture as an official distribution.

## Short loopback HTTP performance results

| Mode | Success TPS | P95 (ms) | P99 (ms) | Observed fixture method entries |
|---|---:|---:|---:|---:|
| No Agent | 3668.29 | 2.072 | 4.272 | N/A |
| Loading only | 3294.65 | 2.716 | 5.123 | 0 |
| ASM traced | 3701.60 | 2.265 | 4.498 | 177,760 |

**No performance conclusion:** short sequential measurements of a synthetic JDK HttpServer workload, different startup timing, noisy environment. Does not prove Agent improved or slowed production processing. Preserve raw results in `results/phase18/http-loopback`.

## Unverified release acceptance requirements

- Official ASM 9.7.1 Maven build and actual *shaded* binary execution
- Java runtime tests on 8, 11, 17
- Real Spring Boot 2 / 3, Tomcat 9 / 10.1 tests
- JEUS, WebLogic, IBM AIX vendor JVM staging tests
- Independent supply-chain provenance and real-workload performance sign-off

The Phase18 acceptance gate remains HOLD until full vendor and customer staging review.
