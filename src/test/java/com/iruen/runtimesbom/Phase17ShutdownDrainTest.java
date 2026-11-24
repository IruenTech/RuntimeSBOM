package com.iruen.runtimesbom;

import com.sun.net.httpserver.HttpServer;
import java.io.File;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/** Regression for shutdown losing its drain slot to the periodic worker. */
public final class Phase17ShutdownDrainTest {
  public static void main(String[] args)throws Exception {
    final Path directory=Files.createTempDirectory("phase17-queue-race");
    Path source=directory.resolve("snapshot.json");
    Files.write(source,"{\"bomFormat\":\"CycloneDX\"}".getBytes("UTF-8"));
    final DurableDeliveryQueue q=new DurableDeliveryQueue(directory.resolve("spool").toFile(),4,16L*1024*1024);
    if(!q.enqueue(source.toFile(),"server-A") || !q.enqueue(source.toFile(),"server-A"))
      throw new AssertionError("enqueue failed");
    final CountDownLatch receivedFirst=new CountDownLatch(1);
    final AtomicInteger requests=new AtomicInteger();
    HttpServer server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
    server.createContext("/api/v1/sbom", exchange -> {
      try (InputStream in=exchange.getRequestBody()) {
        byte[] buf=new byte[1024];while(in.read(buf)!=-1){}
      }
      if (requests.incrementAndGet()==1) {
        receivedFirst.countDown();
        try { Thread.sleep(325L); }catch(InterruptedException ignored){}
      }
      exchange.sendResponseHeaders(201,-1);exchange.close();
    });
    server.start();
    final String endpoint="http://127.0.0.1:"+server.getAddress().getPort()+"/api/v1/sbom";
    Thread periodic=new Thread(() -> q.drain(endpoint,"PHASE17_UNSET_TOKEN",2000,1));
    try {
      periodic.start();
      if(!receivedFirst.await(5,TimeUnit.SECONDS))throw new AssertionError("first request never started");
      q.drainForShutdown(endpoint,"PHASE17_UNSET_TOKEN",2000,8);
      periodic.join(5000L);
      if(periodic.isAlive() || q.pendingFiles()!=0 || requests.get()!=2)
        throw new AssertionError("shutdown drain race pending="+q.pendingFiles()+" received="+requests.get());
      System.out.println("PASS shutdown waits for concurrent drain, delivered=2, pending=0");
    }finally{server.stop(0);}
  }
}
