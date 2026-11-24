# Phase 22 verification report (2026-11-24)

## Objective

Move from JDK-internal ASM PoC evidence to an official ASM 9.7.1 release candidate qualification process. **No unsupported release claims.** The highest-priority deliverable is a reproducible, fail-closed CI pipeline testing one identical Agent artifact across four JDKs and four real WAS variants.

## What was actually executed locally

1. 14 Phase 22 unit tests, including negative cases: missing version-scoped JDK evidence, wrong/absent binary hash, wrong ASM dependency, false loaded-only method execution, archive identity mismatch, exceeded P95 limit, NaN metric, missing JAR, Java 17 classfile in a Java 8 artifact, duplicate ZIP member.
2. `sh scripts/verify-jdk-asm.sh`: JDK 21 internal ASM test-only Agent, actual `Worker.compute()` 12 times and transform failure count zero. Java 8 targeted test application compiled by installed JDK 21.
3. `python3 scripts/phase21-http-provenance.py --mode jdk-internal --requests 48 --concurrency 6 --out-dir results/phase22/local-http`: real loopback HTTP with 48 successful requests per mode. Both modes TP=3, FP=0, FN=0 for the controlled fixture. Tested duplicate PURL with two different JAR hashes and an isolated loader with no false execution claim.
4. Python Collector regression suite: 14 tests executed, 12 passing and 2 intentionally skipped.
5. `python3 scripts/phase22-evidence-gate.py`: exact-binary staging acceptance correctly rejected with `HOLD` due to missing official Maven Agent, build evidence, 4 JDK proofs and 4 actual staged WAS proofs.

Recorded output: `results/phase22/local-gate.json` and the individual `.log` files. `phase22-local-gate.py` returned five PASS groups, including the **expected HOLD negative test**, not five staging approvals.

## Why official verification is pending

This environment has OpenJDK 21, but no `mvn` executable or cached official ASM 9.7.1 JAR. DNS cannot resolve `repo.maven.apache.org`. Spring Boot/Tomcat application artifacts and four tested JDK runtimes are likewise unavailable. No build or live WAS evidence was invented. Only execution on CI / staging hosts with those dependencies can complete the acceptance matrix.

## Approval decision

- Local functional regression: **PASS**
- Official ASM binary build/execution: **NOT RUN**
- JDK 8/11/17/21 on same binary: **NOT RUN**
- Spring Boot 2/3 & Tomcat 9/10.1 HTTP: **NOT RUN**
- JEUS/WebLogic/AIX: **NOT RUN**
- Staging review eligibility: **HOLD**
- Production deployment: **HOLD**

The CI pipeline fails when its artifact SHA links or file/evidence claims do not match. Passing the gate would still only qualify for a human review of staging evidence, not a production release.
