package com.iruen.runtimesbom;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;

/** Self-contained test of genuine nested JAR bytes; no Maven or network required. */
public final class Phase26SpringBoot3MetadataTest {
  private static int passed;
  private static void check(boolean condition, String message) {
    if (!condition) throw new AssertionError(message);
    passed++;
  }
  private static void add(JarOutputStream jar, String name, byte[] bytes) throws IOException {
    jar.putNextEntry(new JarEntry(name));
    jar.write(bytes);
    jar.closeEntry();
  }
  private static byte[] makeInner() throws IOException {
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    try (JarOutputStream jar = new JarOutputStream(out)) {
      add(jar, "META-INF/maven/org.apache.commons/commons-lang3/pom.properties",
          "groupId=org.apache.commons\nartifactId=commons-lang3\nversion=3.14.0\n".getBytes(StandardCharsets.UTF_8));
      add(jar, "org/apache/commons/lang3/StringUtils.class", new byte[] {1,2,3,4});
    }
    return out.toByteArray();
  }
  private static byte[] makeOuter(String name, byte[] inner) throws IOException {
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    try (JarOutputStream jar = new JarOutputStream(out)) {
      add(jar, name, inner);
    }
    return out.toByteArray();
  }
  private static String sha256(byte[] content) throws Exception {
    byte[] hash = MessageDigest.getInstance("SHA-256").digest(content);
    StringBuilder out = new StringBuilder();
    for (byte b : hash) out.append(String.format("%02x", b & 0xff));
    return out.toString();
  }
  private static void assertMaven(JarMetadata metadata, String hash) {
    check("org.apache.commons".equals(metadata.group), "groupId not detected: " + metadata.group);
    check("commons-lang3".equals(metadata.name), "artifactId not detected: " + metadata.name);
    check("3.14.0".equals(metadata.version), "version not detected: " + metadata.version);
    check("pom.properties".equals(metadata.confidence), "metadata confidence should be pom.properties");
    check(hash.equals(metadata.sha256), "SHA-256 must cover the exact inner JAR bytes");
  }
  public static void main(String[] args) throws Exception {
    Path folder = Files.createTempDirectory("runtime sbom nested regression ");
    byte[] inner = makeInner();
    String expectedHash = sha256(inner);
    String entry = "BOOT-INF/lib/commons-lang3-3.14.0.jar";
    String warEntry = "WEB-INF/lib/commons-lang3-3.14.0.jar";
    Path archive = folder.resolve("sbom-spring-demo-1.0.0.jar");
    Path war = folder.resolve("sbom-demo.war");
    Path standalone = folder.resolve("commons-lang3-3.14.0.jar");
    Files.write(archive, makeOuter(entry, inner));
    Files.write(war, makeOuter(warEntry, inner));
    Files.write(standalone, inner);

    // Exactly the URL shape reported by Spring Boot 3 on the user's CI runner.
    String boot3 = "jar:nested:" + archive.toUri().getRawPath() + "/!" + entry + "!/";
    assertMaven(JarMetadata.resolve(boot3), expectedHash);
    System.out.println("PASS: Boot 3 jar:nested: Maven PURL and inner SHA-256");

    String boot2 = "jar:" + archive.toUri().toASCIIString() + "!/" + entry + "!/";
    assertMaven(JarMetadata.resolve(boot2), expectedHash);
    System.out.println("PASS: Boot 2 jar:file: regression");

    String nestedWar = "jar:nested:" + war.toUri().getRawPath() + "/!" + warEntry + "!/";
    assertMaven(JarMetadata.resolve(nestedWar), expectedHash);
    System.out.println("PASS: Boot 3 embedded WAR nested dependency");

    assertMaven(JarMetadata.resolve(standalone.toUri().toASCIIString()), expectedHash);
    System.out.println("PASS: exploded WAR / standalone JAR handling");

    String res = boot3 + "org/apache/commons/lang3/StringUtils.class";
    String origin = ResourceResolver.origin(res, "org.apache.commons.lang3.StringUtils");
    check(origin != null, "ResourceResolver did not determine library origin");
    assertMaven(JarMetadata.resolve(origin), expectedHash);
    System.out.println("PASS: class resource URL fallback provenance");

    JarMetadata fallback = JarMetadata.resolve("jar:nested:/unavailable/app.jar/!" + entry + "!/");
    check("commons-lang3-3.14.0".equals(fallback.name), "fallback must not say unknown");
    check(fallback.group == null && fallback.version == null, "fallback must not invent Maven identity");
    System.out.println("PASS: missing archive safely reports filename only");

    JarMetadata traversal = JarMetadata.resolve("jar:nested:" + archive.toUri().getRawPath() +
        "/!BOOT-INF/lib/../commons-lang3-3.14.0.jar!/");
    check(traversal.group == null, "traversal entry must not produce Maven metadata");
    System.out.println("PASS: unsafe nested entry rejected");
    System.out.println("PASS: " + passed + " assertions");
  }
}
