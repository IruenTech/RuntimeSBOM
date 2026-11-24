# Live environment scripts

Run only against an isolated test host. A successful script demonstrates the example application and Agent agree for `commons-lang3 3.14.0`. It does not validate other libraries or WAS versions. Do not expose test server ports outside the test network.

- `verify-live-spring-boot2.sh`: requires working Maven repository access, official shaded Agent built in `target`, Java 8+, free TCP port 18769. It builds a Boot 2.7.18 executable JAR, launches it, calls `/health/sbom`, stops it and tests evidence in `target/live-spring-boot2/sbom.json`.
- `verify-live-tomcat9.sh`: additionally requires `CATALINA_HOME` pointing to Tomcat 9, port 8080 free; builds servlet WAR, uses isolated `CATALINA_BASE`, calls `/sbom-demo/health/sbom`, stops it and checks evidence.
- `check-real-was-evidence.py`: requires an exact `pkg:maven/org.apache.commons/commons-lang3@3.14.0` PURL, `METHOD_EXECUTED`, and positive method count.

A real Boot/WAR test may reveal a missing nested-JAR CodeSource or other classloader limitations; such failures should be fixed rather than bypassed.
