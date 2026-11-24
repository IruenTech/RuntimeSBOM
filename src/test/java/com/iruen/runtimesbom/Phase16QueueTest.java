package com.iruen.runtimesbom;

import com.sun.net.httpserver.HttpServer;
import java.io.*;
import java.net.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.atomic.*;

/** Real HTTP fault injection + immutable disk spool; compiled with Java 8 target. */
public final class Phase16QueueTest {
  static void check(boolean p, String desc) { if (!p) throw new AssertionError(desc); }
  public static void main(String[] args) throws Exception {
    Path root = Files.createTempDirectory("runtimesbom-phase16-");
    File sbom = root.resolve("latest.json").toFile();
    Files.write(sbom.toPath(), "{\"bomFormat\":\"CycloneDX\"}".getBytes("UTF-8"));
    final AtomicInteger response = new AtomicInteger(503), requests = new AtomicInteger();
    final List<String> ids = Collections.synchronizedList(new ArrayList<String>());
    final List<String> assets = Collections.synchronizedList(new ArrayList<String>());
    HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
    server.createContext("/api/v1/sbom", exchange -> {
      try (InputStream in = exchange.getRequestBody()) { byte[] buf = new byte[512]; while(in.read(buf) != -1) {} }
      requests.incrementAndGet();
      ids.add(exchange.getRequestHeaders().getFirst("X-RuntimeSBOM-Delivery-ID"));
      assets.add(exchange.getRequestHeaders().getFirst("X-RuntimeSBOM-Asset"));
      exchange.sendResponseHeaders(response.get(), -1); exchange.close();
    });
    server.start();
    String url = "http://127.0.0.1:" + server.getAddress().getPort() + "/api/v1/sbom";
    try {
      DurableDeliveryQueue first = new DurableDeliveryQueue(root.resolve("spool").toFile(), 2, 8L*1024*1024);
      check(first.enqueue(sbom,"original-asset"),"enqueue initial");
      first.drain(url,"TEST_TOKEN_NONE",1000,8);
      check(first.pendingFiles()==1,"503 must leave durable item on disk");
      check(requests.get()==3,"503 bounded retry (3 attempts)");
      check(ids.get(0)!=null && ids.get(0).matches("[0-9a-f]{32}"),"delivery ID header present");
      check(ids.get(0).equals(ids.get(1)) && ids.get(1).equals(ids.get(2)),"retries must preserve ID");
      // Simulate second JVM: create independent queue object from the same disk path.
      DurableDeliveryQueue resumed = new DurableDeliveryQueue(root.resolve("spool").toFile(), 2, 8L*1024*1024);
      response.set(201);
      resumed.drain(url,"TEST_TOKEN_NONE",1000,8);
      check(resumed.pendingFiles()==0,"restart recovery deletes acknowledged item");
      check("original-asset".equals(assets.get(3)),"asset identity persists across restarts");
      check(ids.get(0).equals(ids.get(3)),"stable delivery ID after restart");
      check(resumed.enqueue(sbom,"a"),"first item");
      check(resumed.enqueue(sbom,"b"),"second item");
      check(!resumed.enqueue(sbom,"c"),"queue file count bound");
      check(resumed.pendingFiles()==2 && resumed.enqueueRejected.get()==1,"rejected item not silently stored");
      response.set(401); requests.set(0);
      resumed.drain(url,"TEST_TOKEN_NONE",1000,8);
      check(requests.get()==1 && resumed.pendingFiles()==2,"401 no retry, no queue deletion");
      response.set(201);
      resumed.drain(url,"TEST_TOKEN_NONE",1000,8);
      check(resumed.pendingFiles()==0,"FIFO delivery resumes when credentials restored");
      // Independent byte-quota check (two 5 MiB snapshots cannot fit an 8 MiB queue).
      DurableDeliveryQueue byteQuota = new DurableDeliveryQueue(root.resolve("byte-bound").toFile(), 10, 8L*1024*1024);
      byte[] large = new byte[5*1024*1024];
      Arrays.fill(large,(byte)'x');
      File payload = root.resolve("large.json").toFile();
      Files.write(payload.toPath(),large);
      check(byteQuota.enqueue(payload,"a"),"first large entry must fit");
      check(!byteQuota.enqueue(payload,"b"),"second large entry exceeds byte quota");
      check(byteQuota.pendingFiles()==1 && byteQuota.enqueueRejected.get()==1,"byte quota enforced");
      System.out.println("PASS 503 recovery; stable delivery ID; restart persistence; per-item asset; file+byte bounds; 401 hold; FIFO resume");
    } finally { server.stop(0); }
  }
}
