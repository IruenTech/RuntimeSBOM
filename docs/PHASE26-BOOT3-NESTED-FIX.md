# RuntimeSBOM Spring Boot 3 nested JAR fix (rc16 source hotfix)

## Confirmed cause from real CI `sbom.json`

- `jar:nested:/.../sbom-spring-demo-1.0.0.jar/!BOOT-INF/lib/commons-lang3-3.14.0.jar!/`
- Runtime method entry evidence for `StringUtils.reverse`: **65,526**; `METHOD_EXECUTED` correctly attributed.
- Missing `purl`, `version`, `hashes`; `name=unknown`, `metadataConfidence=filename-only`.
- `resourceProbes=3575`, `resourceResolved=0` is not needed to explain the direct CodeSource metadata failure.
- Actual server starts and runs in Spring Boot 3.3.5 on JDK 17.0.21.

## Root cause

`JarMetadata.resolve()` removed `jar:` but did not recognize the Spring Boot 3 `nested:` scheme and `/!` archive boundary. `new File(new URI("nested:/..."))` throws and the catch returns `fallback(...)`. The fallback incorrectly selected the empty string after trailing `!/` and returned `unknown`.

## Code changes

- Normalize only Spring Boot 3 `nested:/...outer.jar/!BOOT-INF/lib/inner.jar!/` into the equivalent `file:/...outer.jar!/BOOT-INF/lib/inner.jar!/` lookup representation.
- Reuse the existing ZIP entry reader (64 MiB cap), `pom.properties` parser, and inner-byte SHA-256 calculation.
- Correct the no-metadata fallback basename while **never guessing Maven group or version**.
- Keep Spring Boot 2, WAR, and standalone JAR behavior unchanged.
- Run the regression suite in GitHub Actions `official-build` after packaging and binary audit.

## Test locally

```sh
sh scripts/phase26-springboot3-metadata-test.sh
sh scripts/verify-jdk-asm.sh
sh scripts/phase26-boot3-agent-smoke.sh jdk-internal
```

`jdk-internal` is a **test-only** build, not the official 9.7.1 shaded release.

## Test with official ASM in CI

```sh
mvn -B -DskipTests clean package
sh scripts/phase26-springboot3-metadata-test.sh
sh scripts/phase26-boot3-agent-smoke.sh official
python3 scripts/phase21-staging-live.py --app spring-boot3 --out-dir results/phase22/live --duration 12 --concurrency 8
```

Official integration validation must confirm `name=commons-lang3`, `version=3.14.0`, `purl=pkg:maven/org.apache.commons/commons-lang3@3.14.0`, inner JAR `SHA-256`, `runtimeEvidenceState=METHOD_EXECUTED`, and observed count > 0.

## Limits

- This fix addresses nested JAR metadata mapping, not all forms of class loader compatibility.
- SHA-256 is only available when the actual outer archive is present and readable (relative or missing artifacts cannot be recovered from the old SBOM).
- Other future Boot loader URI formats still need specific testing.
- The official Maven/ASM build and user CI rerun are **not executed in this local sandbox**; release approval remains on HOLD.
