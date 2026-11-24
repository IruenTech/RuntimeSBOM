# Phase 19: component provenance and release evidence

## Objective

Retain the Phase 18 ASM-based Java Agent while eliminating repeated full scans
of all event keys per component and exposing unbound events rather than silently
claiming these method calls originated from an unrelated third-party JAR.

### Attribution algorithm

A transformer emits a signature `sourceURL|loader=<id>|binary.Class#method(desc)`
after it has checked that the target loader can resolve the same `Recorder`
class as the Agent. Phase 19 builds an index:

1. Build the set of observed source URL + loader keys.
2. Snapshot the method-entry counters (`LongAdder.sum()` is non-atomic across
   concurrent updates and must not be treated as exact audit data).
3. Parse each method signature, optionally use an existing class-resource
   relocation observed within the same outer archive, and link it to one exact
   source+loader key. Invalid, unknown, or missing references remain unbound.
4. Aggregate entries/distinct method keys per source+loader in O(E+C) expected
   lookup operations, where E is method-event keys and C is components.
5. Resolve each unique source's Maven metadata and SHA-256 once per snapshot.
   Flag same-PURL/different-SHA conflicts separately from normal loader clones.

**Important:** A class-loader key based on `System.identityHashCode` remains an
in-process identifier only. It is not a durable global process identity and can
in theory collide. Stable cross-restart asset identity is a separate concern.

### Confidence and interpretation

- `METHOD_EXECUTED` means an inserted probe ran for one or more methods in a
  particular source+loader component.
- `CLASS_LOADED` means the JVM observed code loading but has no successful
  method-entry probe; an isolated classloader may execute code without a probe.
- `PRELOADED` means observed when attaching to a running JVM and not necessarily
  retransformable or traced.
- `unattributedMethodEntries` > 0 means source binding should be investigated;
  it must **never** be divided among known libraries to make the report appear
  complete.
- `purlHasDifferentHashes` is a supply-chain **investigation flag**, not proof
  of compromise, because legitimate repackaging can produce different bytes.

### Locally executed evidence, 2026-11-24

| Check | Observed | Status |
| --- | --- | --- |
| JDK21 internal ASM real method entry | 12/12 | PASS |
| Same PURL but two different SHA-256 JARs | 2 digests | PASS |
| Same-PURL four loader instances | 4 unique BOM refs | PASS |
| Executed + recorded method entries | 9 | PASS |
| Isolated loader method calls | 5 actual, 0 claimed | PASS |
| Incorrectly attributed method entries | 0 | PASS |
| Original multi-loader and nested archive fixtures | 3 instances; 2 archive formats | PASS |
| Real loopback HTTP ASM/loaded-only | Verified; not a real WAS | PASS |
| Official ASM shaded JAR | Maven/repository unavailable | NOT RUN |
| Real Spring Boot 2/3 and Tomcat 9/10.1 | Dependencies / server unavailable | NOT RUN |
| JDK 8/11/17 full runtime matrix | Only JDK21 available | NOT RUN |
| JEUS, WebLogic, AIX | Vendor environment unavailable | NOT RUN |

### CI and release qualification

`.github/workflows/phase19-official-asm.yml` builds one exact official Maven
shaded binary on a JDK 8 runner, then tests the same build artifact on
JDK 8/11/17/21 and on actual loopback Spring Boot 2 and 3 applications.
JUnit-style tests for fake evidence exist in `tests/test_phase18_approval.py`.
Tomcat requires preapproved installations and is deliberately not claimed as
fully covered by hosted CI. JAAS/security-manager restrictions, child-first
vendor class loaders and AIX proprietary JVMs need on-site tests.

**Go/no-go:** No production rollout based on these results. Official ASM,
real application evidence and operator-reviewed performance baselines remain
mandatory. The acceptance tool always leaves `productionDeployment=HOLD`.
