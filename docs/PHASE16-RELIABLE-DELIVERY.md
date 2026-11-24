# Phase 16: Persistent delivery and duplicate-safe collector — operations runbook

## Delivery semantics

1. The Agent completes an atomic replacement of `output=latest.json`.
2. If a collector URL is configured, it creates a separate immutable queue copy. It first
   writes a private temporary `.part` file and renames within the same spool directory.
3. A dedicated daemon worker periodically sends oldest queue entries first. The queue
   filename stores the original asset ID and a random 128-bit delivery ID (reused verbatim
   on retries and after JVM restart).
4. Collector transactionally inserts a snapshot with a unique `(tenant,asset,delivery_id)`
   key. Identical requests receive the original snapshot ID, without a new history row.
5. An HTTP 2xx acknowledgment permits the sender to delete the queued copy. Loss of the
   HTTP acknowledgment or failure to delete simply causes the same ID to be replayed.

## Common incidents and response

| Incident | Expected behavior | Operator response |
| --- | --- | --- |
| Collector unreachable | Queue remains; bounded immediate retries then periodic retry | Restore network/TLS and check pending file count |
| HTTP 503/429 | Up to 3 immediate attempts and repeat on next drain | Stabilize collector/quotas; check errors and capacity |
| HTTP 401/403 | No immediate retry; file retained; later drain can retry | Fix token/permissions; verify latest files eventually clear |
| HTTP 409 | Conflicting content for a reused delivery ID; file retained | Investigate identity collision/corruption; do not discard silently |
| Queue reaches count/byte limit | New queue entry rejected, latest local SBOM still written | Expand protected storage; monitor `runtimeSbom:queueRejected` |
| JVM restart | Restarted worker replays existing immutable files in order | Reuse prior JVM's spool only after old JVM stopped |
| Power loss during temp write | `.part` may remain (not valid queue entry) | Inspect/remove orphaned `.part` after stopping JVM |
| Server restart | SQLite persists snapshots and unique delivery IDs | Restore using safe SQLite WAL backup or SQLite online backup |

## Monitoring and alerting

The following CycloneDX metadata property names are available:
`runtimeSbom:queuePendingFiles`, `runtimeSbom:queuePendingBytes`,
`runtimeSbom:queueEnqueued`, `runtimeSbom:queueDelivered`,
`runtimeSbom:queueRejected`, `runtimeSbom:queueDeliveryFailures`.
Snapshot-level counters represent the local JVM point-in-time view, **not a live
centralized availability monitor**. Alert on persistent queue growth or non-zero rejected
snapshots. After restart, pending entries persist but in-memory cumulative counters reset.

## Security and deployment

- Use HTTPS and TLS verification on real networks. HTTP is accepted **only** for loopback.
- Use a unique protected spool path per JVM; do not share it among running agents.
- Ensure filesystem permissions/ACLs deny untrusted users read access to SBOM payloads.
  Newly created POSIX directories are set to owner-only access if supported; preexisting
  paths and AIX/Windows ACLs must be audited independently.
- Keep token only in a protected environment variable; never embed it in agent arguments.
- Rotate credentials and test 401 recovery. Keep sufficient filesystem free space.
- Rollback: stop JVM, remove `-javaagent` (requires JVM restart), and retain spool/SQLite
  for evidence. Do not delete pending data before reconciling delivered IDs.
- Do not deploy to production JEUS/WebLogic/AIX until vendor JVM and real-WAS tests pass.

## Acceptance evidence

**Executed in this build environment**
- Java 8 target bytecode compiled by JDK 21 (not Java 8 runtime execution).
- Actual loopback fault injection and source-level queue recovery after process restart.
- Python collector idempotency/concurrent duplicate/migration tests.
- JDK 21 internal ASM smoke (not official redistributable ASM).
- Synthetic nested JAR and WAR metadata identification.

**Still required**
- `mvn clean package` and `scripts/verify-official-asm.sh` using the official ASM 9.7.1.
- Genuine JDK 8/11/17/21 runtime test matrix for the shaded release JAR.
- Spring Boot 2/3 and Tomcat 9/10.1 HTTP integration on vendor-specific runtime.
- JEUS/WebLogic/AIX class loader and instrumentation test, CPU/Heap/GC/TPS stress,
  power-loss recovery on actual AIX/production storage, and security review.

**Current production release decision: HOLD**.
