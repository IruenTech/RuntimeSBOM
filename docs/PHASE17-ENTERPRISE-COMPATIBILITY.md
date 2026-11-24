# Phase 17 — Enterprise WAS / IBM AIX field validation and rollback

## Evidence hierarchy

1. **Actual official ASM 9.7.1 shaded JAR** (NOT JDK-internal ASM): `mvn -B clean package`, `sh scripts/verify-official-asm.sh`, `sh scripts/phase17-loader-test.sh official`.
2. **Java runtime matrix:** official shaded JAR execution on each of Java **8, 11, 17, 21**. The GitHub Actions file `.github/workflows/phase17-validation.yml` specifies these environments; creating a workflow does **not** constitute executing it.
3. **Real Tomcat/Spring Boot:** `python3 scripts/phase14-live-was.py --app spring-boot2` and similarly `spring-boot3`, `tomcat9`, `tomcat10`. These require externally provisioned Maven/Tomcat installation and appropriate JDKs. Logs and performance statistics are stored for manual review.
4. **JEUS / WebLogic / IBM AIX vendor JVM:** test only on customer-authorized staging installations, with documented JVM vendor, build, server version, deployment model, and asset ID.

## Staging deployment protocol (generic)

- Choose an isolated non-production node and a **narrow** `tracePackages` scope. Keep a baseline measurement without Agent. Do not attach to an existing process with assumptions that prior class loading will be instrumented.
- Ensure a writable per-JVM `queueDir` with restricted permissions and a TLS-only `collectorUrl`; preserve local JSON and spool during collector downtime. Do not share a spool directory across JVM processes.
- Add the official Agent's `-javaagent:/path/to/runtime-sbom-agent-1.0.0-rc8.jar=...` to the actual JVM startup flags, **not** to the OS service shell unless the shell propagates JVM options. Use the WAS's vendor-supported mechanism for specifying JVM options.
- Start with `tracePackages=...` restricted to a tested third-party package, `maxTransformErrors=20`, `maxTransformedClasses=1000`, `sampleEvery=10`, an explicit `killSwitchFile`, and `interval=60`. No claims of guaranteed low overhead are made from these values.
- Generate real HTTP requests that invoke a known vulnerable/non-vulnerable fixture or reference library. Confirm the PURL/version, SHA-256, loader chain, and `METHOD_EXECUTED` vs `CLASS_LOADED` status.
- Capture Agent log, WAS log (hash as evidence), SBOM JSON, TPS, P95/P99, JVM heap/GC, queue pending files, and rollback time.
- To disable **new recording**, create the configured kill-switch file. This does not undo already transformed classes. To remove the Agent's code, **roll back JVM flags and restart** the staging JVM.
- Stop rollout on: verification errors, hard JVM crashes, duplicated server classes, unsupported vendor flags, sustained TPS/P95 degradation above locally approved thresholds, or incomplete SBOM evidence.

## JEUS / WebLogic specifics

Class-loader hierarchy is vendor/version/configuration dependent. Measure shared-domain libraries separately from WAR/EAR modules and any parent-first/child-first delegation policies. Confirm that third-party `Recorder` bridge access is to the *same* class identity. Agent skips isolated classloaders rather than inserting a call which would cause `NoClassDefFoundError`.

## IBM AIX JVM specifics

Do **not** infer support from Java class major version alone. Before enabling instrumentation, check the actual vendor-provided JVM build, instrumentation agent support, supported architecture, filesystem semantics, startup options, and vendor recommendations. Use `java -version`, verify the actual Java executable invoked by the WAS, and perform a canary with the shaded official Agent. No IBM AIX test has been performed in this execution environment.

## Field evidence capture

On an approved staging machine, after running the real HTTP workload, collect the Agent and SBOM:

```sh
python3 scripts/phase17-field-evidence.py \
  --was WebLogic --asset weblogic-staging-1 \
  --java /path/to/vendor/java \
  --agent target/runtime-sbom-agent-1.0.0-rc8.jar \
  --sbom /var/lib/runtimesbom/latest.json \
  --expected-purl 'pkg:maven/org.apache.commons/commons-lang3@<verified-version>' \
  --server-log /var/log/your-was/server.log \
  --out results/phase17/weblogic-staging-evidence.json
```

Replace placeholders with verified local values; the script does not independently attest the environment. It validates the Agent JAR structure, checks the SBOM for the requested PURL, and preserves file SHA-256 hashes, not raw server-log secrets. The resulting report is `EVIDENCE_CAPTURED_PENDING_REVIEW`, **not a production approval**.

## Status

`PRODUCTION = HOLD` until a real shaded ASM build, JDK matrix, live WAS tests and vendor-specific staging tests have passed review. Synthetic loader tests do not substitute for JEUS/WebLogic/AIX testing.
