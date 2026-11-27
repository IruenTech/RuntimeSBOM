package com.iruen.runtimesbom;

import java.nio.file.*;
import java.io.File;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

/** Test enqueue when successful drains unlink older queue files concurrently. */
public final class Phase29QueueDrainRaceTest {
  public static void main(String[] args) throws Exception {
    Path base = Files.createTempDirectory("phase29-concurrent-drain-");
    Path payload = base.resolve("snapshot.json");
    Files.write(payload, "{\"bomFormat\":\"CycloneDX\",\"specVersion\":\"1.6\",\"components\":[]}".getBytes("UTF-8"));
    Path spool = base.resolve("spool");
    final DurableDeliveryQueue queue = new DurableDeliveryQueue(spool.toFile(), 10000, 32 * 1024 * 1024);
    final AtomicBoolean running = new AtomicBoolean(true);
    final AtomicReference<Throwable> failure = new AtomicReference<Throwable>();
    Thread successfulDrainer = new Thread(new Runnable() {
      public void run() {
        try {
          while (running.get()) {
            try (DirectoryStream<Path> files = Files.newDirectoryStream(spool, "*.json")) {
              for (Path f : files) {
                Files.deleteIfExists(f); // Model a successfully delivered queued item.
              }
            }
            Thread.yield();
          }
        } catch (Throwable ex) { failure.set(ex); }
      }
    }, "simulated-acknowledged-drain");
    successfulDrainer.start();
    int attempted = 1400;
    try {
      for (int i=0;i<attempted;i++) {
        if (!queue.enqueue(payload.toFile(), "asset"+i)) {
          throw new AssertionError("Unexpected enqueue rejection at "+i+"; exceptions can drop SBOM snapshots");
        }
      }
    } finally {
      running.set(false);
      successfulDrainer.join(15000);
    }
    if (successfulDrainer.isAlive() || failure.get()!=null)
      throw new AssertionError("Drainer thread did not complete cleanly: "+failure.get());
    if (queue.enqueueRejected.get()!=0 || queue.enqueued.get()!=attempted)
      throw new AssertionError("Data loss: enqueued="+queue.enqueued.get()+" rejected="+queue.enqueueRejected.get());
    System.out.println("PASS queue concurrent acknowledged deletes vs 1400 enqueues; none lost");
  }
}
