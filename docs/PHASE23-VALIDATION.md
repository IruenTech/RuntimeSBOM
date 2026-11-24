# Phase 23 validation and deployment decision

| Evidence | Status |
|---|---|
| Java 8-compatible observability classifier | Implemented; compiled with `javac --release 8` |
| Independent CycloneDX evidence validator | Tests for malformed/contradictory/missing data |
| 3-loader JDK21 internal ASM fixture | Runs with 3, 5 and 0 *observed* method entries; third loader executes but is not instrumentable |
| Quality downgrade for isolated loader | `DEGRADED`, reason `ISOLATED_CLASSLOADERS` |
| Loopback HTTP fixture | Loading-only vs ASM-traced; ground truth and source JAR SHA-256 compared |
| Central collector idempotent delivery | Regression suite executed |
| Exact-binary staging review | HOLD without official build and 8 JDK/WAS results |
| Production approval | HOLD, requires vendor/JVM qualification and change control |

Unobserved methods **cannot** be classified as unused methods. The labels describe observational limitations only. They do not establish total detection precision or guarantee a runtime exploit is reachable.

Connected CI needs Maven, access to Maven Central, an approved JDK version matrix and downloaded staging Tomcat distributions. The local machine for this development has JDK 21 only and no Maven/repository DNS. Production JEUS/WebLogic/AIX cannot be tested in this environment. The official artifact must pass all staged tests before any rollout consideration.
