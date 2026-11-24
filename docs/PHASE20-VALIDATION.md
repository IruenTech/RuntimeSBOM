# Phase 20 — Independent SBOM Ground Truth & Official Release Path

## Scope and guarantees

This phase adds evidence **accuracy measurement**, not a claim of general enterprise OSS detection completeness.
The Java Agent continues to use ASM 9.7.1 when packaged with the official Maven build. No production Agent binary was built locally, because Maven and the official ASM JAR repository were inaccessible in the authoring environment. All observed ASM transformation tests below used **JDK 21 internal ASM, test-only**.

**Distribution gate remains `HOLD`.** Java 8 compatibility is a source/compiler target, NOT confirmation of running on an installed Java 8 JVM. The local environment has only JDK 21. JEUS, WebLogic, AIX, Spring Boot and Tomcat are not certified by the fixture tests.

## Independent truth and metrics

`scripts/phase20-make-truth.py` takes fixture JAR SHA-256 directly from the fixture JAR **files** and expected invocation counts from the Java fixture source, without inspecting the runtime SBOM. It creates:

- `truth-provenance.json`: old JAR, two loader instances (3 and 2 observed calls); new JAR, two loader instances (4 observed, 5 actually executed but *unobserved* in an isolated loader). Expected `METHOD_EXECUTED` counts: 3, 2, 4; `CLASS_LOADED`: 0.
- `truth-boot.json`: synthetic `BOOT-INF/lib/...jar`, expected 7 observed calls.
- `truth-war.json`: synthetic `WEB-INF/lib/...jar`, expected 7 observed calls.

`phase20-accuracy.py` compares a *multiset of component instances* on exact `(Maven PURL, SHA-256, expected source suffix)` instead of collapsing class loader duplicates. It independently validates class-loader-token uniqueness, loading-vs-execution state and invocation counts. It reports:

- **TP:** number of precisely matching component instances.
- **FP:** detected in-scope component instances not present in the independent truth list (including wrong versions, SHA, origins).
- **FN:** expected in-scope instances not precisely matched.
- **Precision = TP/(TP+FP), Recall = TP/(TP+FN), F1** (all *fixture-scoped*).
- **Strict pass:** exact instance identity, state/count distribution, unique loader tokens, zero unattributed method entries.

**Do not compare these numbers to production inventory discovery rates.** The controlled workload invokes known classes; actual workloads may leave present libraries unloaded. Uninstrumented JDK classes, hidden dynamic loading and isolated class loaders may produce observation gaps.

### Reproduce on JDK 21 test-only ASM

```sh
sh scripts/phase20-fixture-gate.sh jdk-internal
python3 -m unittest discover -s tests -p 'test_phase20_*.py' -v
python3 scripts/phase20-release-gate.py
```

The full release-gate script runs extra Collector and HTTP tests and expects official/live evidence to be missing. The final production status stays `HOLD` even when all local checks pass.

### Independent static inventory cross-check

`phase20-static-inventory.py` parses embedded JAR bytes in `BOOT-INF/lib` or `WEB-INF/lib`, reads their Maven pom.properties, and computes SHA-256. It compares against a runtime SBOM as:

- `OBSERVED_EXACT_IDENTITY` — Maven PURL, hash and deployment source agree.
- `OBSERVED_IDENTITY_MISMATCH` — archive source was seen but identity differs.
- `PACKAGED_NOT_OBSERVED` — archive contains a library which was not seen in this runtime trace.

`PACKAGED_NOT_OBSERVED` is **not a runtime false negative** unless the test independently proves that it was loaded. This is an important distinction for risk review.

```sh
python3 scripts/phase20-static-inventory.py app.jar --sbom runtime-sbom.json --out inventory-review.json
python3 scripts/phase20-static-inventory.py app.war --sbom runtime-sbom.json --out war-review.json
```

### Official ASM shaded JAR on an authorized Maven build host

```sh
sh scripts/phase20-official-verify.sh
# Builds target/runtime-sbom-agent-1.0.0-rc11.jar and executes tests.
```

It performs a structural manifest / relocated ASM / bytecode check, a real Agent launch, and the same independent fixture accuracy checks using the **official shaded JAR**. This command was **not** executed successfully in the current environment; it requires Maven and a trusted repository with the declared ASM dependency.

To record the exact binary SHA for deployment evidence:

```sh
sha256sum target/runtime-sbom-agent-1.0.0-rc11.jar
```

Structural scanning alone does **not** prove the provenance of an official ASM binary. Trusted dependency checksums and a trusted build pipeline are additional controls.

### JDK and live WAS staging

`.github/workflows/phase20-accuracy-official.yml` describes CI for Java 8/11/17/21, same binary SHA, official shaded fixture checks, Spring Boot 2 and 3 staging apps. It is provided but **not run**. Tomcat 9 and 10.1 need explicitly supplied local installations; vendor JEUS/WebLogic and AIX IBM/OpenJ9 need separate vendor-specific test hosts.

Examples on authorized staging hosts:

```sh
python3 scripts/phase14-live-was.py --app spring-boot2 --out-dir results/phase20/live --duration 15 --concurrency 8
python3 scripts/phase14-live-was.py --app spring-boot3 --out-dir results/phase20/live --duration 15 --concurrency 8
python3 scripts/phase14-live-was.py --app tomcat9 --tomcat-home /approved/staging/tomcat9 --out-dir results/phase20/live
python3 scripts/phase14-live-was.py --app tomcat10 --tomcat-home /approved/staging/tomcat10 --out-dir results/phase20/live
```

The acceptance script requires an audited exact official JAR SHA, individual JDK smoke evidence, actual live WAS traces, and performance requirements. It never grants production permission by itself:

```sh
python3 scripts/phase18-acceptance.py \
 --agent target/runtime-sbom-agent-1.0.0-rc11.jar \
 --jdk-dir results/phase20/jdk-matrix \
 --live-dir results/phase20/live \
 --out results/phase20/acceptance.json
```

**HOLD conditions:** missing official binary, untrusted evidence, missing JDK/WAS matrix, mismatched PURL or SHA, execution not observed, class-loader collision, inaccurate runtime attribution, unacceptable real service P95/TPS, unverified recovery and rollback.

## Local verification evidence

- `results/phase20/fixture-summary-jdk-internal.json`: 6/6 in-scope instances match exactly, FP=0, FN=0; exact method calls and distinct loader tokens.
- `results/phase20/static-boot-jdk-internal.json`, `static-war-jdk-internal.json`: one embedded JAR each, exact PURL/SHA/source match.
- `results/phase20/accuracy-negative-controls.log`: 14 Phase-20 Python tests including deliberate corrupted PURL/hash, missing components, spurious entries, event misattribution and inventory scenarios.
- `results/phase20/collector-and-delivery.log`: existing 14 Collector Python tests, JVM event concurrency and durable delivery recovery checks.
- `results/phase20/loader-regression-isolated.log`: real JVM custom loader isolation test.
- `results/phase20/loopback-http-proof.json`: Java built-in HTTP server with no errors, loading-only 0 method entries, ASM mode positive; not actual Tomcat or Spring Boot.
- `results/phase20/acceptance.json`: mandatory official and live results missing; `HOLD`.

An all-in-one automated release-gate run exceeded the authoring execution limit. The listed sub-tests were rerun separately; no claim is made that one uninterrupted full gate completed.
