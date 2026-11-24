package com.iruen.runtimesbom;

import java.io.*;
import java.net.*;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermission;
import java.security.SecureRandom;
import java.util.*;
import java.util.concurrent.atomic.*;

/**
 * Persistent, bounded, FIFO SBOM delivery spool. Queue files are immutable.
 * Each filename contains the submission ID and encoded asset identifier so
 * delivery survives Agent restarts and even changes to the configured assetId.
 * The server deduplicates by (tenant, asset, deliveryId), not by SBOM digest.
 * Queue is single-process owned; do not point multiple Agent JVMs at the same dir.
 */
final class DurableDeliveryQueue {
  private static final long MAX_SNAPSHOT_BYTES = 8L * 1024 * 1024;
  private static final String EXT = ".json";
  private final Path directory;
  private final int maxFiles;
  private final long maxBytes;
  private final AtomicBoolean draining = new AtomicBoolean();
  final AtomicLong enqueued = new AtomicLong(), delivered = new AtomicLong();
  final AtomicLong enqueueRejected = new AtomicLong(), deliveryFailures = new AtomicLong();
  private final SecureRandom random = new SecureRandom();

  DurableDeliveryQueue(File directory, int maxFiles, long maxBytes) throws IOException {
    this.directory = directory.getAbsoluteFile().toPath();
    this.maxFiles = Math.max(1, Math.min(10000, maxFiles));
    this.maxBytes = Math.max(MAX_SNAPSHOT_BYTES, Math.min(1024L * 1024 * 1024, maxBytes));
    if (Files.isSymbolicLink(this.directory)) throw new IOException("Queue directory cannot be symlink");
    boolean created = !Files.exists(this.directory);
    Files.createDirectories(this.directory);
    if (!Files.isDirectory(this.directory) || Files.isSymbolicLink(this.directory))
      throw new IOException("Invalid queue directory");
    if (created) securePermissions(this.directory, true);
  }

  private static void securePermissions(Path p, boolean directory) {
    try {
      Set<PosixFilePermission> perms = directory ?
        EnumSet.of(PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE, PosixFilePermission.OWNER_EXECUTE) :
        EnumSet.of(PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE);
      Files.setPosixFilePermissions(p, perms);
    } catch (UnsupportedOperationException ignored) {
      // Windows/AIX permissions depend on filesystem and process umask/ACL.
    } catch (IOException ignored) {
      System.err.println("[RuntimeSBOM] cannot enforce spool file permissions: " + p.getFileName());
    }
  }

  private List<Path> entries() throws IOException {
    List<Path> entries = new ArrayList<Path>();
    try (DirectoryStream<Path> files = Files.newDirectoryStream(directory, "*" + EXT)) {
      for (Path p : files) if (Files.isRegularFile(p, LinkOption.NOFOLLOW_LINKS) && decode(p) != null) entries.add(p);
    }
    Collections.sort(entries, new Comparator<Path>() {
      @Override public int compare(Path a, Path b) { return a.getFileName().toString().compareTo(b.getFileName().toString()); }
    });
    return entries;
  }

  synchronized int pendingFiles() { try { return entries().size(); } catch (IOException ex) { return -1; } }

  synchronized long pendingBytes() {
    try { long sum = 0; for (Path p : entries()) sum += Files.size(p); return sum; }
    catch (IOException ex) { return -1; }
  }

  /** Enqueue file with atomic rename; never overwrite an existing snapshot. */
  synchronized boolean enqueue(File source, String assetId) {
    Path temp = null;
    try {
      if (assetId == null || !assetId.matches("[a-zA-Z0-9._:-]{1,128}")) throw new IOException("Invalid asset ID");
      if (!source.isFile() || source.length() < 2 || source.length() > MAX_SNAPSHOT_BYTES)
        throw new IOException("SBOM missing or oversized");
      List<Path> current = entries();
      long total = 0; for (Path p : current) total += Files.size(p);
      if (current.size() >= maxFiles || total + source.length() > maxBytes) {
        enqueueRejected.incrementAndGet();
        System.err.println("[RuntimeSBOM] queue capacity exhausted; local output remains: " + source.getName());
        return false;
      }
      // Millisecond sort key + secure random ID ensures stable FIFO across process restarts.
      byte[] rand = new byte[16]; random.nextBytes(rand);
      StringBuilder id = new StringBuilder(32);
      for (byte b : rand) id.append(Character.forDigit((b >> 4) & 15, 16)).append(Character.forDigit(b & 15, 16));
      String encoded = Base64.getUrlEncoder().withoutPadding().encodeToString(assetId.getBytes("UTF-8"));
      long lastTimestamp = 0L;
      if (!current.isEmpty()) {
        try { lastTimestamp = Long.parseLong(current.get(current.size() - 1).getFileName().toString().substring(0, 13)); }
        catch (NumberFormatException ignored) {}
      }
      long orderedTimestamp = Math.max(System.currentTimeMillis(), lastTimestamp + 1L);
      String name = String.format(Locale.ROOT, "%013d-%s-%s.json", orderedTimestamp, id.toString(), encoded);
      temp = Files.createTempFile(directory, ".queue-", ".part");
      securePermissions(temp, false);
      Files.copy(source.toPath(), temp, StandardCopyOption.REPLACE_EXISTING);
      try (FileChannel ch = FileChannel.open(temp, StandardOpenOption.WRITE)) { ch.force(true); }
      try { Files.move(temp, directory.resolve(name), StandardCopyOption.ATOMIC_MOVE); }
      catch (AtomicMoveNotSupportedException ex) { Files.move(temp, directory.resolve(name)); }
      enqueued.incrementAndGet();
      return true;
    } catch (Exception ex) {
      enqueueRejected.incrementAndGet();
      System.err.println("[RuntimeSBOM] queue enqueue failed: " + ex.getClass().getSimpleName() + ": " + ex.getMessage());
      return false;
    } finally {
      if (temp != null) try { Files.deleteIfExists(temp); } catch (IOException ignored) {}
    }
  }

  private static final class Entry {
    final String id, assetId;
    Entry(String id, String assetId) { this.id = id; this.assetId = assetId; }
  }

  private static Entry decode(Path p) {
    String filename = p.getFileName().toString();
    // Avoid reading unexpected files in a shared directory, including symlinks.
    if (!filename.matches("\\d{13}-[0-9a-f]{32}-[A-Za-z0-9_-]+\\.json")) return null;
    int first = filename.indexOf('-'), second = filename.indexOf('-', first + 1);
    String id = filename.substring(first + 1, second);
    try {
      String asset = new String(Base64.getUrlDecoder().decode(filename.substring(second + 1, filename.length() - 5)), "UTF-8");
      if (!asset.matches("[a-zA-Z0-9._:-]{1,128}")) return null;
      return new Entry(id, asset);
    } catch (Exception ex) { return null; }
  }

  /** Send only a bounded batch. A failure preserves the item and FIFO ordering. */
  void drain(String endpoint, String tokenEnv, int timeoutMs, int batch) {
    drainInternal(endpoint, tokenEnv, timeoutMs, batch, false);
  }

  /** Shutdown must not lose its final drain to a concurrent periodic worker.
   *  Wait only a bounded time to acquire the drain slot; delivery remains best-effort.
   */
  void drainForShutdown(String endpoint, String tokenEnv, int timeoutMs, int batch) {
    drainInternal(endpoint, tokenEnv, timeoutMs, batch, true);
  }

  private void drainInternal(String endpoint, String tokenEnv, int timeoutMs, int batch, boolean shutdown) {
    if (endpoint == null || endpoint.isEmpty()) return;
    if (shutdown) {
      long deadline = System.nanoTime() + java.util.concurrent.TimeUnit.SECONDS.toNanos(8);
      while (!draining.compareAndSet(false, true)) {
        if (System.nanoTime() >= deadline) {
          System.err.println("[RuntimeSBOM] shutdown drain timed out acquiring slot; disk queue retained");
          return;
        }
        try { Thread.sleep(25L); }
        catch (InterruptedException ex) { Thread.currentThread().interrupt(); return; }
      }
    } else if (!draining.compareAndSet(false, true)) return;
    try {
      int remaining = Math.max(1, Math.min(100, batch));
      for (Path p : entries()) {
        if (remaining-- == 0) break;
        Entry entry = decode(p);
        if (entry == null) continue;
        if (!CollectorClient.send(p.toFile(), endpoint, tokenEnv, entry.assetId, timeoutMs, entry.id)) {
          deliveryFailures.incrementAndGet();
          break; // Never skip an older failed item or silently discard a 4xx response.
        }
        try { Files.delete(p); delivered.incrementAndGet(); }
        catch (IOException ex) { // Next retry is idempotent at the receiving collector.
          deliveryFailures.incrementAndGet();
          System.err.println("[RuntimeSBOM] delivered but could not remove queued file: " + ex.getMessage());
          break;
        }
      }
    } catch (IOException ex) {
      deliveryFailures.incrementAndGet();
      System.err.println("[RuntimeSBOM] queue drain failed: " + ex.getMessage());
    } finally { draining.set(false); }
  }
}
