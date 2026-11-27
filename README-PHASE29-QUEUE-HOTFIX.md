# RuntimeSBOM Phase29 — Collector queue drain/enqueue race hotfix

## Observed root cause

An intermittent `phase29_outage_backlog_replay` failure was reproduced locally.
The **unmodified rc16 official JAR** produced:

```
[RuntimeSBOM] queue enqueue failed: NoSuchFileException: .../queue/<already-delivered-id>.json
```

The periodic sender deletes an acknowledged spool file while the Agent shutdown
hook is checking existing queue entries' sizes. `DurableDeliveryQueue.enqueue`
previously interpreted that expected race as an I/O failure, and the new SBOM
was not enqueued. The Collector could then contain only the three older
snapshots even though the queue had become empty.

This is a product concurrency bug, not a failed HTTP health check. An earlier
Phase26 artifact containing the bug **must not be reused** to validate the fix.

## Changes

1. `DurableDeliveryQueue.java`: skip `NoSuchFileException` for entries already
   successfully removed, while preserving strict handling of other I/O errors
   and queue size quotas. `pendingBytes()` has the same treatment.
2. `Phase29QueueDrainRaceTest.java`: stress 1,400 enqueues against concurrent
   acknowledged spool deletions; old code fails while changed source passed.
3. `phase29-outage-replay.py`: hold the offline port reservation to prevent CI
   port reuse, print the exact failure stage, keep limited Agent log tails in JSON.
4. `phase29-local-gate.py`: show the underlying failed step details in Actions.
5. `phase26-staging.yml`: rebuild the ASM JAR from modified source **and** run
   the queue race regression test before publishing an artifact.
6. `phase29-bind-agent-proof.py` + `phase29-was-lifecycle.yml`: derive the SHA
   from the **new, successful Phase26 build artifact**, checking `build.json`,
   `binary-audit.json`, and actual JAR bytes. The cross-job review uses the
   same SHA. No production deployment is enabled.

## Required GitHub execution order

1. Apply these files on a clean `main` working tree, commit and push.
2. Wait for the new **Phase26 official ASM exact-binary WAS diagnostics** run
   to complete successfully. Record that **NEW** GitHub run ID.
3. Open **Phase29 official rc16 WAS lifecycle and outage rehearsal** and enter
   the new Phase26 run ID (NOT the old 45763042301). Set `run_live_was=yes`.
4. Verify `phase29_outage_backlog_replay`, the four live WAS jobs, and review.
5. Retain the build, audit, `outage-replay.json`, `local-gate.json`, and review
   artifacts. A successful staging review is not production approval.

## If it still fails

Download `phase29-official-local-rehearsal` and inspect
`outage-replay.json` (`failureStage`, `error`, `agentLogTails`), plus
`local-gate.json` (`checks[].outputTail`). Do **not** disable the review gate.

## Verification scope

Checked syntax and Python/Java tests locally. Modified Java source tested
using Java 8-target bytecode with JDK 21; **official shaded ASM JAR must be
rebuilt by GitHub Maven CI**. Production deployment stays HOLD.
